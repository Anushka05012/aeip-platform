import io
import json
import os
import sys
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.github_source import GitHubDataSource, complexity_delta, is_analyzable, parse_repository
from src.web_api import IntelligenceDemoService


def _zipball() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as bundle:
        bundle.writestr("octo-app-abc123/src/auth/login.py", "def validate_token(token):\n    if not token:\n        raise ValueError('missing token')\n    return token.startswith('ok')\n")
        bundle.writestr("octo-app-abc123/README.md", "# Octo app\n\nLogin uses signed tokens.\n")
        bundle.writestr("octo-app-abc123/node_modules/pkg/index.js", "module.exports = 1")
        bundle.writestr("octo-app-abc123/package-lock.json", "{}")
    return buffer.getvalue()


RESPONSES = {
    "/repos/octo/app": {"full_name": "octo/app", "default_branch": "main"},
    "/repos/octo/app/commits?sha=main&per_page=40": [{"sha": "c1"}, {"sha": "c2"}],
    "/repos/octo/app/commits/c1": {
        "sha": "c1", "commit": {"author": {"date": "2026-09-20T10:00:00Z"}, "message": "Harden token checks"},
        "files": [{"filename": "src/auth/login.py", "additions": 40, "deletions": 5, "patch": "+    if not token:\n+        raise"},
                  {"filename": "package-lock.json", "additions": 900, "deletions": 900}],
    },
    "/repos/octo/app/commits/c2": {
        "sha": "c2", "commit": {"author": {"date": "2026-09-21T10:00:00Z"}, "message": "Fix login flow"},
        "files": [{"filename": "src/auth/login.py", "additions": 12, "deletions": 3, "patch": "+return x"}],
    },
    "/repos/octo/app/actions/runs?per_page=60": {"workflow_runs": [
        {"id": 1, "name": "CI", "head_branch": "main", "head_sha": "c1", "status": "completed",
         "conclusion": "failure", "updated_at": "2026-09-20T11:00:00Z"},
        {"id": 2, "name": "CI", "head_branch": "main", "head_sha": "c2", "status": "completed",
         "conclusion": "success", "updated_at": "2026-09-21T11:00:00Z"},
        {"id": 3, "name": "CI", "head_branch": "main", "head_sha": "c2", "status": "in_progress", "conclusion": None,
         "updated_at": "2026-09-21T12:00:00Z"},
    ]},
    "/repos/octo/app/actions/runs/1/jobs?filter=latest&per_page=50": {"jobs": [
        {"id": 11, "name": "test", "conclusion": "failure",
         "steps": [{"name": "Checkout", "conclusion": "success"}, {"name": "Run pytest", "conclusion": "failure"}]},
        {"id": 12, "name": "lint", "conclusion": "success", "steps": []},
    ]},
    "/repos/octo/app/check-runs/11/annotations": [
        {"path": "src/auth/login.py", "start_line": 3, "title": "test_login", "message": "AssertionError: missing token not rejected"},
    ],
}


class FakeResponse:
    def __init__(self, body: bytes):
        self.body = body

    def read(self, _limit=None):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def fake_open(request, timeout=None):
    path = request.full_url.removeprefix("https://api.github.com")
    if path == "/repos/octo/app/zipball/main":
        return FakeResponse(_zipball())
    return FakeResponse(json.dumps(RESPONSES[path]).encode())


def source():
    return GitHubDataSource(token="", opener=fake_open)


def test_parse_repository_accepts_urls_and_short_names():
    assert parse_repository("octo/app") == "octo/app"
    assert parse_repository("https://github.com/octo/app.git") == "octo/app"
    assert parse_repository("github.com/octo/app/tree/main/src") == "octo/app"


def test_filters_generated_and_vendored_files():
    assert is_analyzable("src/auth/login.py")
    assert not is_analyzable("node_modules/pkg/index.js")
    assert not is_analyzable("package-lock.json")


def test_complexity_delta_counts_added_minus_removed_branches():
    assert complexity_delta("+if a:\n+for x in y:\n-while z:\n") == 1


def test_github_snapshot_contains_commits_ci_runs_and_chunked_source():
    snapshot = source().load_snapshot("https://github.com/octo/app")
    assert snapshot.repository == "octo/app"
    assert [commit.files for commit in snapshot.commits] == [("src/auth/login.py",), ("src/auth/login.py",)]
    assert [item.status for item in snapshot.deployments] == ["failure", "success"]
    paths = {document.path for document in snapshot.documents}
    assert {"src/auth/login.py", "README.md", "history/commits", "history/ci-failures"} <= paths
    assert not any("node_modules" in path for path in paths)


def test_analyzed_github_repository_supports_risk_and_rag(tmp_path):
    service = IntelligenceDemoService(cache_dir=tmp_path, github_factory=source)
    summary = service.analyze_repository("octo/app")
    assert summary["commits"] == 2
    assert any(stage["stage"] == "Risk scoring" for stage in summary["stages"])
    assert (tmp_path / "octo__app.json").exists()

    overview = service.overview("octo/app")
    assert overview["riskItems"][0]["file"] == "src/auth/login.py"
    assert overview["failures"][0]["cause"].startswith("CI failed for commit c1")

    answer = service.ask("How is the login token validated?", repository="octo/app")
    assert answer["evidence"][0]["path"] == "src/auth/login.py"

    failure = service.explain_failure("1", repository="octo/app")
    assert failure["verdict"] == "related"
    assert failure["failed_jobs"] == [{"name": "test", "failedSteps": ["Run pytest"]}]
    assert failure["log_source"] == "annotations"
    assert (tmp_path / "explanations" / "octo__app__1.json").exists()

    # A restarted service reloads the cached analysis without calling GitHub.
    reloaded = IntelligenceDemoService(cache_dir=tmp_path, github_factory=lambda: None)
    assert reloaded.overview("octo/app")["repository"] == "octo/app"
