import pytest

from src.change_guard import file_kind
from src.web_api import IntelligenceDemoService
from tests.test_git_history import FakeSource, _live_snapshot, _long_history

EXAMPLE = ["src/payment_service.py", "db/migrations/0043_refund_status.sql", "requirements.txt",
           "tests/test_routes.py", "src/routes.py", ".github/workflows/deploy.yml"]


def test_file_kinds():
    assert file_kind("src/pay.py") == "code"
    assert file_kind("tests/test_pay.py") == "test"
    assert file_kind("prisma/migrations/2026_init/migration.sql") == "migration"
    assert file_kind("alembic/versions/abc_add_index.py") == "migration"
    assert file_kind("package-lock.json") == "dependency"
    assert file_kind(".github/workflows/ci.yml") == "config"
    assert file_kind("docs/runbook.md") == "docs"


def test_tests_are_matched_by_module_name_anywhere_in_a_test_path():
    from src.change_guard import _tests_changed_for
    assert _tests_changed_for("src/black/ranges.py", ["tests/data/cases/line_ranges_fmt_skip_async.py"])  # psf/black #5703
    assert _tests_changed_for("src/cart.ts", ["src/cart.spec.ts"])
    assert not _tests_changed_for("src/pay.py", ["tests/test_routes.py"])


def test_demo_change_touching_an_incident_file_is_high_risk():
    service = IntelligenceDemoService(cache_dir=None)
    report = service.assess_change(None, files=EXAMPLE)
    files = {entry["path"]: entry for entry in report["files"]}
    assert report["level"] == "high"
    assert report["files"][0]["path"] == "src/payment_service.py"  # most concerning first
    assert files["src/payment_service.py"]["suspectedIn"]
    assert files["src/payment_service.py"]["tests"] == "other tests changed"  # tests/test_routes.py is not its test
    assert files["src/routes.py"]["tests"] == "changed"  # tests/test_routes.py is in the change
    assert ".github/workflows/deploy.yml" in files and files[".github/workflows/deploy.yml"]["kind"] == "config"
    assert [item["name"] for item in report["reviewers"]] == ["priya", "rahul", "meera"]
    assert any("does not undo the migration" in step for step in report["rollback"])
    assert any("requirements.txt" in step for step in report["rollback"])
    assert report["rollback"][0].startswith("Redeploy the last good release")
    assert any("suspected causes" in finding for finding in report["findings"])
    assert not report["model"]["active"] and "not a probability that this change" in report["model"]["meaning"]


def test_a_docs_only_change_is_low_risk():
    report = IntelligenceDemoService(cache_dir=None).assess_change(None, files="docs/payments.md\n")
    assert report["level"] == "low" and report["findings"] == []
    assert not report["files"][0]["suspectedIn"]  # the suspected deploy touched it, but docs cannot break production
    assert not any("migration" in step for step in report["rollback"])


def test_bad_requests_are_refused():
    service = IntelligenceDemoService(cache_dir=None)
    with pytest.raises(ValueError):
        service.assess_change(None, files=[])
    with pytest.raises(ValueError, match="not on GitHub"):
        service.assess_change(None, pull_request=12)
    with pytest.raises(ValueError):
        service.assess_change(None, pull_request="twelve", files=["src/a.py"])


def test_cli_reports_on_a_git_branch_and_never_fails_by_default(tmp_path):
    import subprocess
    import sys
    from pathlib import Path

    repo = tmp_path / "repo"
    repo.mkdir()

    def git(*args, when="2026-01-01T10:00:00+00:00"):
        env = {"GIT_AUTHOR_DATE": when, "GIT_COMMITTER_DATE": when, "GIT_AUTHOR_NAME": "ana",
               "GIT_AUTHOR_EMAIL": "ana@example.com", "GIT_COMMITTER_NAME": "ana", "GIT_COMMITTER_EMAIL": "ana@example.com"}
        import os
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, env={**os.environ, **env})

    git("init", "-q", "-b", "main")
    (repo / "src").mkdir()
    for day in range(1, 6):
        (repo / "src" / "pay.py").write_text(f"VALUE = {day}\n")
        git("add", ".")
        git("commit", "-q", "-m", "fix refund bug" if day % 2 else "tweak", when=f"2026-01-0{day}T10:00:00+00:00")
    git("checkout", "-q", "-b", "feature")
    (repo / "src" / "pay.py").write_text("VALUE = 99\nif VALUE:\n    pass\n")
    (repo / "migrations").mkdir()
    (repo / "migrations" / "0002_add_column.sql").write_text("ALTER TABLE pay ADD COLUMN note text;\n")
    git("add", ".")
    git("commit", "-q", "-m", "rework payments", when="2026-01-07T10:00:00+00:00")

    script = Path(__file__).resolve().parents[1] / "scripts" / "change_guard.py"
    summary = tmp_path / "summary.md"
    result = subprocess.run([sys.executable, str(script), "--repo", str(repo), "--base", "main", "--head", "feature"],
                            capture_output=True, text=True, encoding="utf-8", env={**__import__("os").environ,
                                                                                   "GITHUB_STEP_SUMMARY": str(summary)})
    assert result.returncode == 0, result.stderr
    assert "AEIP change guard" in result.stdout and "does not undo the migration" in result.stdout
    assert "`src/pay.py`" in result.stdout and summary.read_text(encoding="utf-8") == result.stdout.rstrip("\n") + "\n"
    failing = subprocess.run([sys.executable, str(script), "--repo", str(repo), "--base", "main", "--head", "feature",
                              "--fail-on", "medium"], capture_output=True, text=True, encoding="utf-8")
    assert failing.returncode == 1  # opt-in only


class PullRequestSource(FakeSource):
    def fetch_pull_request(self, repository, number):
        return {"number": number, "title": "Rework module 1", "state": "open", "merged": False, "author": "dev-0",
                "url": f"https://github.com/{repository}/pull/{number}", "base": "main", "head": "abc",
                "files": [{"path": "src/mod1.py", "status": "modified", "additions": 40, "deletions": 10},
                          {"path": "src/mod11.py", "status": "modified", "additions": 5, "deletions": 1}]}


def test_pull_request_is_scored_with_the_learned_model(tmp_path):
    history = [commit.__class__(**{**commit.__dict__, "author": f"dev-{index % 3}"})
               for index, commit in enumerate(_long_history())]
    service = IntelligenceDemoService(cache_dir=tmp_path, github_factory=lambda: PullRequestSource(_live_snapshot()),
                                      database_sync=None, history_loader=lambda repository, refresh: history)
    service.analyze_repository("acme/shop", refresh=True)
    report = service.assess_change("acme/shop", pull_request="#7")
    assert report["change"]["number"] == 7 and report["change"]["title"] == "Rework module 1"
    assert report["model"]["active"]
    learned = {entry["path"]: entry["learned"] for entry in report["files"]}
    assert learned["src/mod1.py"]["probability"] > learned["src/mod11.py"]["probability"]  # mod1 keeps needing fixes
    assert "dev-0" not in [item["name"] for item in report["reviewers"]]  # the author does not review themselves
