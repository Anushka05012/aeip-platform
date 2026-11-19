"""A repository's commit history from git itself, for learning (learned_risk.py) and evaluation.

The GitHub API needs one request per commit for file statistics, so a live analysis fetches only the
latest few dozen commits: too little for the risk model to learn from. Instead AEIP keeps a bare,
read-only copy of the repository's recent history and reads it with `git log --numstat`:

* `--bare`: no working tree; nothing from the repository is checked out, built or executed;
* `--filter=blob:limit=512k`: file contents over 512 KB are left on the server;
* `--shallow-since`: only the last few years (enough for the training windows);
* the token, when given, travels in an HTTP header set through git's environment, not the command line
  or the stored remote URL.

The evaluation (evaluation.py, section 6) reads history with the same functions, so the product learns
the way it was measured.
"""

from __future__ import annotations

import base64
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .domain import Commit, Document
from .github_source import is_dependency_file, is_source_code, parse_repository

HISTORY_YEARS = 5  # enough dated windows for the model (click needs ~5 years to reach 50 labels)
CLONE_TIMEOUT_SECONDS = 300
MAX_CLONE_BYTES = 500_000_000


class HistoryError(RuntimeError):
    """The history could not be fetched or read; callers fall back to the API's recent commits."""


@dataclass
class GitCommit:
    sha: str
    time: datetime
    subject: str
    files: list[tuple[str, int, int]] = field(default_factory=list)  # (path, lines added, lines deleted)
    author: str = ""


def read_history(repo: Path, token: str | None = None) -> list[GitCommit]:
    """Non-merge commits, oldest first, with per-file line counts. Files left out of a filtered copy are
    fetched on demand, which for a private repository needs the token."""
    out = subprocess.run(["git", "-C", str(repo), "log", "--no-merges", "--numstat", "--format=@@%H|%aI|%an|%s"],
                         capture_output=True, text=True, encoding="utf-8", errors="ignore", check=True,
                         env=_git_env(token)).stdout
    commits: list[GitCommit] = []
    for line in out.splitlines():
        if line.startswith("@@"):
            sha, when, author, subject = line[2:].split("|", 3)
            try:
                moment = datetime.fromisoformat(when).astimezone(timezone.utc)
            except ValueError:  # a few old commits carry corrupt time zones such as "+518:00"
                moment = datetime.fromisoformat(when[:19]).replace(tzinfo=timezone.utc)
            commits.append(GitCommit(sha, moment, subject, author=author))
        elif line.strip() and commits:
            parts = line.split("\t")
            if len(parts) == 3:
                adds, dels, path = parts
                commits[-1].files.append((path, int(adds) if adds.isdigit() else 0, int(dels) if dels.isdigit() else 0))
    return sorted(commits, key=lambda item: item.time)


def to_commit(item: GitCommit) -> Commit:
    """As the risk engine sees it: churn counts source code only; manifests and lockfiles are listed apart."""
    return Commit(item.sha, item.time,
                  tuple(path for path, _, _ in item.files if not is_dependency_file(path)),
                  sum(adds for path, adds, _ in item.files if is_source_code(path)),
                  sum(dels for path, _, dels in item.files if is_source_code(path)), 0, item.subject,
                  tuple(path for path, _, _ in item.files if is_dependency_file(path)), item.author)


def _git_env(token: str | None = None) -> dict[str, str]:
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_ASKPASS": "", "GCM_INTERACTIVE": "never"}
    if token:
        basic = base64.b64encode(f"x-access-token:{token}".encode()).decode()
        env |= {"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "http.https://github.com/.extraheader",
                "GIT_CONFIG_VALUE_0": f"Authorization: Basic {basic}"}
    return env


def _size(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def clone_history(repository: str, directory: Path, token: str | None = None, years: int = HISTORY_YEARS) -> Path:
    """Create or update the bare history copy of github.com/<owner>/<name>; returns its path."""
    repository = parse_repository(repository)
    target = directory / (repository.replace("/", "__") + ".git")
    since = f"--shallow-since={years} years ago"
    env = _git_env(token)
    try:
        if (target / "HEAD").exists():
            subprocess.run(["git", "-C", str(target), "fetch", "--quiet", "--filter=blob:limit=512k", since, "origin",
                            "+HEAD:refs/heads/aeip-history"], check=True, capture_output=True,
                           timeout=CLONE_TIMEOUT_SECONDS, env=env)
            subprocess.run(["git", "-C", str(target), "symbolic-ref", "HEAD", "refs/heads/aeip-history"],
                           check=True, capture_output=True, env=env)
        else:
            directory.mkdir(parents=True, exist_ok=True)
            shutil.rmtree(target, ignore_errors=True)
            subprocess.run(["git", "clone", "--quiet", "--bare", "--filter=blob:limit=512k", since,
                            f"https://github.com/{repository}.git", str(target)], check=True, capture_output=True,
                           timeout=CLONE_TIMEOUT_SECONDS, env=env)
    except FileNotFoundError as exc:
        raise HistoryError("git is not installed on the server") from exc
    except subprocess.TimeoutExpired as exc:
        shutil.rmtree(target, ignore_errors=True)
        raise HistoryError(f"fetching the history took longer than {CLONE_TIMEOUT_SECONDS}s") from exc
    except subprocess.CalledProcessError as exc:
        message = (exc.stderr or b"").decode("utf-8", errors="ignore").strip().splitlines()
        raise HistoryError(message[-1] if message else "git could not fetch the repository") from exc
    if _size(target) > MAX_CLONE_BYTES:
        shutil.rmtree(target, ignore_errors=True)
        raise HistoryError("the repository history is larger than 500 MB")
    return target


def load_history(repository: str, directory: Path, token: str | None = None,
                 refresh: bool = True) -> list[Commit]:
    """The repository's recent history as commits. `refresh=False` reads an existing copy without network."""
    target = directory / (parse_repository(repository).replace("/", "__") + ".git")
    if refresh or not (target / "HEAD").exists():
        target = clone_history(repository, directory, token)
    try:
        return [to_commit(item) for item in read_history(target, token)]
    except subprocess.CalledProcessError as exc:
        raise HistoryError("git could not read the history copy") from exc


def tree_documents(repo: Path, sha: str) -> list[Document]:
    """Files at a commit: Python source with its text (for import counts), everything else by name only.
    Blob contents are read in one `git cat-file --batch` call."""
    listing = subprocess.run(["git", "-C", str(repo), "ls-tree", "-r", sha], capture_output=True, check=True).stdout
    entries = []
    for line in listing.decode("utf-8", errors="ignore").splitlines():
        meta, _, name = line.partition("\t")
        parts = meta.split()
        if len(parts) == 3 and parts[1] == "blob":
            entries.append((name, parts[2]))
    wanted = [(name, blob) for name, blob in entries if is_source_code(name) and name.endswith(".py")]
    texts: dict[str, str] = {}
    if wanted:
        out = subprocess.run(["git", "-C", str(repo), "cat-file", "--batch"], capture_output=True, check=True,
                             input="".join(f"{blob}\n" for _, blob in wanted).encode()).stdout
        position = 0
        for name, _ in wanted:
            header_end = out.index(b"\n", position)
            size = int(out[position:header_end].split()[2])
            texts[name] = out[header_end + 1:header_end + 1 + size].decode("utf-8", errors="ignore")
            position = header_end + 1 + size + 1
    return [Document(name, texts[name], "code") if name in texts else Document(name, "", "doc") for name, _ in entries]
