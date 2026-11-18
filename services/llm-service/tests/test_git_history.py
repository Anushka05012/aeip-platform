import base64
import subprocess
from datetime import datetime, timedelta, timezone

import pytest

from src.domain import Commit
from src.git_history import HistoryError, _git_env, read_history, to_commit
from src.web_api import IntelligenceDemoService


def _git(repo, *args, when=None):
    env = None
    if when:
        import os
        env = {**os.environ, "GIT_AUTHOR_DATE": when, "GIT_COMMITTER_DATE": when}
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, env=env)


def test_history_is_read_with_line_counts_and_dependency_files_apart(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "dev@example.com")
    _git(repo, "config", "user.name", "Dev")
    (repo / "src").mkdir()
    (repo / "src" / "pay.py").write_text("a = 1\nb = 2\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "add payments", when="2026-01-01T10:00:00+00:00")
    (repo / "src" / "pay.py").write_text("a = 1\nb = 3\nc = 4\n")
    (repo / "requirements.txt").write_text("requests==2.0\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "fix rounding bug", when="2026-02-01T10:00:00+00:00")

    history = read_history(repo)
    assert [item.subject for item in history] == ["add payments", "fix rounding bug"]  # oldest first
    commit = to_commit(history[1])
    assert commit.files == ("src/pay.py",) and commit.dependency_files == ("requirements.txt",)
    assert (commit.additions, commit.deletions) == (2, 1)  # churn counts source code only
    assert commit.message == "fix rounding bug" and commit.authored_at.tzinfo is not None


def test_token_travels_in_the_environment_not_the_command_line():
    env = _git_env("ghp_example")
    assert env["GIT_TERMINAL_PROMPT"] == "0"
    header = env["GIT_CONFIG_VALUE_0"]
    assert header.startswith("Authorization: Basic ")
    assert base64.b64decode(header.split()[-1]).decode() == "x-access-token:ghp_example"
    assert "GIT_CONFIG_COUNT" not in _git_env(None)


class FakeSource:
    def __init__(self, snapshot):
        from src.github_source import FetchReport
        self.snapshot, self.report = snapshot, FetchReport()

    def load_snapshot(self, repository):
        return self.snapshot


def _live_snapshot():
    from src.domain import Document, RepositorySnapshot
    now = datetime(2026, 9, 1, tzinfo=timezone.utc)
    commits = (Commit("r1", now - timedelta(days=2), ("src/pay.py",), 30, 5, 0, "tweak payments"),)
    return RepositorySnapshot("acme/shop", commits, (), (Document("src/pay.py", "import cart\n", "code"),), "main")


def _long_history():
    """Two years of monthly changes to twelve modules; half of them need a bug fix ten days later."""
    start = datetime(2024, 9, 1, tzinfo=timezone.utc)
    commits = []
    for month in range(24):
        at = start + timedelta(days=30 * month)
        for index in range(12):
            path = f"src/mod{index}.py"
            commits.append(Commit(f"c{month}-{index}", at + timedelta(hours=index), (path,), 10, 2, 0, "change"))
            if index < 6:
                commits.append(Commit(f"f{month}-{index}", at + timedelta(days=10, hours=index), (path,), 3, 1, 0,
                                      "fix crash"))
    return sorted(commits, key=lambda item: item.authored_at)


def test_live_analysis_learns_from_the_git_history(tmp_path):
    calls = []

    def loader(repository, refresh):
        calls.append((repository, refresh))
        return _long_history()

    service = IntelligenceDemoService(cache_dir=tmp_path, github_factory=lambda: FakeSource(_live_snapshot()),
                                      database_sync=None, history_loader=loader)
    described = service.analyze_repository("acme/shop", refresh=True)
    stage = next(item for item in described["stages"] if item["stage"] == "Git history")
    assert stage["detail"].startswith(f"{len(_long_history())} commits")
    status = service.risk_model("acme/shop")
    assert status["historySource"] == "git history" and status["historyCommits"] == len(_long_history())
    assert status["labels"] >= 50 and status["active"]
    assert calls == [("acme/shop", True)]

    # A restart reads the existing copy without fetching again.
    IntelligenceDemoService(cache_dir=tmp_path, github_factory=lambda: None, database_sync=None, history_loader=loader)
    assert calls[-1] == ("acme/shop", False)


def test_without_git_the_analysis_falls_back_to_the_api_commits(tmp_path):
    def broken(repository, refresh):
        raise HistoryError("git is not installed on the server")

    service = IntelligenceDemoService(cache_dir=tmp_path, github_factory=lambda: FakeSource(_live_snapshot()),
                                      database_sync=None, history_loader=broken)
    described = service.analyze_repository("acme/shop", refresh=True)
    stage = next(item for item in described["stages"] if item["stage"] == "Git history")
    assert "git is not installed" in stage["detail"]
    assert service.risk_model("acme/shop")["historySource"] == "GitHub API (recent commits only)"


def test_bad_repository_names_never_reach_git(tmp_path):
    from src.git_history import clone_history
    with pytest.raises(ValueError):
        clone_history("acme/shop; rm -rf /", tmp_path)
