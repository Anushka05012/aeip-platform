"""Live GitHub adapter implementing the AnalyticsDataSource contract.

Pulls everything the intelligence engines need for one public (or token-
accessible) repository using only the GitHub REST API:

- recent commits, with per-file churn and a complexity delta from the patch
- GitHub Actions workflow runs, used as the deployment / CI signal
- the source tree (one zipball download), chunked for RAG

Standard library only, so the service stays dependency-light. Set
GITHUB_TOKEN in .env to raise the API limit from 60 to 5,000 requests/hour.
"""

from __future__ import annotations

import io
import json
import os
import re
import time
import urllib.error
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import PurePosixPath
from typing import Any, Callable

from .chunker import CODE_EXTENSIONS, DOC_EXTENSIONS, get_chunker_for_file
from .domain import Commit, Deployment, Document, PullRequest, RepositorySnapshot

API = "https://api.github.com"
_REPO_PATTERN = re.compile(r"^[A-Za-z0-9-]{1,39}/[A-Za-z0-9._-]{1,100}$")
_BRANCHING = re.compile(r"\b(if|elif|else if|for|while|case|catch|except)\b|&&|\|\||\?\s")
IGNORED_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", "vendor",
                ".next", "coverage", "target", "out", ".idea", ".vscode"}
IGNORED_FILES = {"package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "Cargo.lock",
                 "composer.lock", "Gemfile.lock", "go.sum"}
MAX_FILE_BYTES = 150_000
MAX_ZIP_BYTES = 80_000_000


class GitHubError(RuntimeError):
    """A GitHub failure with a message that is safe to show in the UI."""


def parse_repository(value: str) -> str:
    """Accept `owner/repo`, `https://github.com/owner/repo(.git)` or `github.com/owner/repo/tree/...`."""
    text = value.strip()
    text = re.sub(r"^(https?://)?(www\.)?github\.com/", "", text, flags=re.IGNORECASE)
    parts = [part for part in text.split("/") if part]
    if len(parts) < 2:
        raise ValueError("Enter a repository as owner/repo or a github.com URL.")
    repository = f"{parts[0]}/{parts[1].removesuffix('.git')}"
    if not _REPO_PATTERN.match(repository):
        raise ValueError(f"{value!r} is not a valid GitHub repository name.")
    return repository


def is_analyzable(path: str) -> bool:
    pure = PurePosixPath(path)
    if any(part in IGNORED_DIRS for part in pure.parts[:-1]) or pure.name in IGNORED_FILES:
        return False
    if pure.name.endswith((".min.js", ".min.css", ".map")):
        return False
    return pure.suffix.lower() in CODE_EXTENSIONS or pure.suffix.lower() in DOC_EXTENSIONS


def is_source_code(path: str) -> bool:
    """Files that count toward risk: code, not docs, config, or dependency manifests."""
    suffix = PurePosixPath(path).suffix.lower()
    return suffix in CODE_EXTENSIONS and suffix not in {".json", ".yaml", ".yml"}


def complexity_delta(patch: str) -> int:
    """Added minus removed branching constructs: a cheap, explainable complexity signal."""
    delta = 0
    for line in patch.splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            delta += len(_BRANCHING.findall(line))
        elif line.startswith("-") and not line.startswith("---"):
            delta -= len(_BRANCHING.findall(line))
    return delta


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


@dataclass
class FetchReport:
    """Per-stage log shown in the UI so the audience can see the pipeline run."""

    stages: list[dict[str, Any]] = field(default_factory=list)

    def add(self, name: str, detail: str, started: float) -> None:
        self.stages.append({"stage": name, "detail": detail, "ms": round((time.perf_counter() - started) * 1000)})


class _DropAuthOnRedirect(urllib.request.HTTPRedirectHandler):
    """Log and archive downloads redirect to signed storage URLs that reject a GitHub token."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        request = super().redirect_request(req, fp, code, msg, headers, newurl)
        if request is not None:
            request.remove_header("Authorization")
        return request


@dataclass
class FailedJob:
    name: str
    failed_steps: list[str]
    annotations: list[str]
    log: str = ""  # raw job log; only downloadable with a GITHUB_TOKEN


class GitHubDataSource:
    def __init__(self, token: str | None = None, max_commits: int = 40, max_runs: int = 60,
                 max_files: int = 500, max_prs: int = 50, opener: Callable[..., Any] | None = None):
        self.token = token if token is not None else os.getenv("GITHUB_TOKEN", "")
        self.max_commits = max_commits
        self.max_runs = max_runs
        self.max_prs = max_prs
        self.max_files = max_files
        self._open = opener or urllib.request.build_opener(_DropAuthOnRedirect()).open
        self.report = FetchReport()

    # -- HTTP -----------------------------------------------------------------
    def _request(self, url: str, accept: str = "application/vnd.github+json") -> bytes:
        headers = {"Accept": accept, "User-Agent": "aeip-intelligence", "X-GitHub-Api-Version": "2022-11-28"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        try:
            with self._open(urllib.request.Request(url, headers=headers), timeout=60) as response:
                return response.read(MAX_ZIP_BYTES + 1)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise GitHubError("Repository not found (or it is private and GITHUB_TOKEN has no access).") from exc
            if exc.code in (403, 429):
                raise GitHubError(
                    "GitHub rate limit reached. Add GITHUB_TOKEN to services/llm-service/.env and restart."
                ) from exc
            raise GitHubError(f"GitHub API returned HTTP {exc.code}.") from exc
        except urllib.error.URLError as exc:
            raise GitHubError("Could not reach GitHub. Check the internet connection.") from exc

    def _json(self, path: str) -> Any:
        return json.loads(self._request(f"{API}{path}"))

    # -- CI failure context ------------------------------------------------------
    def fetch_failed_jobs(self, repository: str, run_id: str, max_jobs: int = 3) -> list[FailedJob]:
        """Failed jobs of one workflow run: failed steps, check annotations and (with a token) the log tail."""
        jobs = self._json(f"/repos/{repository}/actions/runs/{run_id}/jobs?filter=latest&per_page=50").get("jobs", [])
        failed: list[FailedJob] = []
        for job in [item for item in jobs if item.get("conclusion") == "failure"][:max_jobs]:
            steps = [step["name"] for step in job.get("steps", []) if step.get("conclusion") == "failure"]
            try:
                annotations = [
                    f"{item.get('path', '')}:{item.get('start_line', '')} {item.get('title') or ''} {item.get('message', '')}".strip()
                    for item in self._json(f"/repos/{repository}/check-runs/{job['id']}/annotations")
                ]
            except GitHubError:
                annotations = []
            log = ""
            if self.token:  # GitHub only serves raw job logs to authenticated callers
                try:
                    raw = self._request(f"{API}/repos/{repository}/actions/jobs/{job['id']}/logs", accept="*/*")
                    log = raw.decode("utf-8", errors="ignore")[-60_000:]
                except GitHubError:
                    log = ""
            failed.append(FailedJob(job.get("name", "job"), steps, annotations, log))
        return failed

    # -- AnalyticsDataSource ----------------------------------------------------
    def load_snapshot(self, repository: str) -> RepositorySnapshot:
        repository = parse_repository(repository)
        self.report = FetchReport()

        started = time.perf_counter()
        meta = self._json(f"/repos/{repository}")
        repository = meta["full_name"]
        branch = meta["default_branch"]
        self.report.add("Connect", f"{repository} · default branch {branch}", started)

        commits = self._commits(repository, branch)
        deployments = self._workflow_runs(repository)
        pull_requests = self._pull_requests(repository)
        documents = self._documents(repository, branch)
        documents += self._history_documents(commits, deployments, pull_requests)
        return RepositorySnapshot(repository, tuple(commits), tuple(deployments), tuple(documents), branch,
                                  tuple(pull_requests))

    def _pull_requests(self, repository: str) -> list[PullRequest]:
        started = time.perf_counter()
        listing = self._json(f"/repos/{repository}/pulls?state=all&sort=updated&direction=desc&per_page={self.max_prs}")
        pull_requests = [
            PullRequest(
                number=item["number"], title=item["title"],
                state="merged" if item.get("merged_at") else item["state"],
                head_branch=item["head"]["ref"], base_branch=item["base"]["ref"],
                created_at=_parse_time(item["created_at"]),
                merged_at=_parse_time(item["merged_at"]) if item.get("merged_at") else None,
            )
            for item in listing
        ]
        merged = sum(1 for item in pull_requests if item.state == "merged")
        self.report.add("Pull requests", f"{len(pull_requests)} pull requests ({merged} merged)", started)
        return pull_requests

    def _commits(self, repository: str, branch: str) -> list[Commit]:
        started = time.perf_counter()
        listing = self._json(f"/repos/{repository}/commits?sha={branch}&per_page={self.max_commits}")
        # The list endpoint has no per-file stats, so fetch each commit's detail in parallel.
        with ThreadPoolExecutor(max_workers=8) as pool:
            details = list(pool.map(lambda item: self._json(f"/repos/{repository}/commits/{item['sha']}"), listing))
        commits = [self._to_commit(detail) for detail in details]
        self.report.add("Commits", f"{len(commits)} commits with per-file churn and complexity", started)
        return commits

    @staticmethod
    def _to_commit(detail: dict[str, Any]) -> Commit:
        files = [entry for entry in detail.get("files", []) if is_analyzable(entry["filename"])]
        return Commit(
            sha=detail["sha"],
            authored_at=_parse_time(detail["commit"]["author"]["date"]),
            files=tuple(entry["filename"] for entry in files),
            additions=sum(entry.get("additions", 0) for entry in files),
            deletions=sum(entry.get("deletions", 0) for entry in files),
            complexity_delta=max(sum(complexity_delta(entry.get("patch", "")) for entry in files), 0),
            message=detail["commit"]["message"].strip(),
        )

    def fetch_commit(self, repository: str, sha: str) -> Commit:
        """One commit (e.g. a PR-branch commit outside the default-branch history)."""
        return self._to_commit(self._json(f"/repos/{repository}/commits/{sha}"))

    def _workflow_runs(self, repository: str) -> list[Deployment]:
        started = time.perf_counter()
        runs = self._json(f"/repos/{repository}/actions/runs?per_page={self.max_runs}").get("workflow_runs", [])
        deployments = [
            Deployment(
                id=str(run["id"]),
                deployed_at=_parse_time(run["updated_at"]),
                commit_sha=run["head_sha"],
                status=run["conclusion"],
                name=run.get("name") or "workflow",
                branch=run.get("head_branch") or "",
                event=run.get("event") or "",
            )
            for run in runs
            if run.get("status") == "completed" and run.get("conclusion") in ("success", "failure")
        ]
        failed = sum(1 for item in deployments if item.status == "failure")
        detail = f"{len(deployments)} completed CI runs ({failed} failed)" if deployments else \
            "no GitHub Actions runs found (DORA metrics will be empty)"
        self.report.add("CI/CD runs", detail, started)
        return deployments

    def _documents(self, repository: str, branch: str) -> list[Document]:
        started = time.perf_counter()
        archive = self._request(f"{API}/repos/{repository}/zipball/{branch}")
        if len(archive) > MAX_ZIP_BYTES:
            raise GitHubError("Repository archive is too large for the live demo (over 80 MB).")
        documents: list[Document] = []
        files = 0
        with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
            for info in bundle.infolist():
                # Zipball entries are prefixed with "<owner>-<repo>-<sha>/".
                path = info.filename.split("/", 1)[-1]
                if info.is_dir() or not path or info.file_size > MAX_FILE_BYTES or not is_analyzable(path):
                    continue
                if files >= self.max_files:
                    break
                text = bundle.read(info).decode("utf-8", errors="ignore")
                if not text.strip():
                    continue
                files += 1
                for chunk in get_chunker_for_file(path).chunk(text, source_path=path):
                    documents.append(Document(path, chunk.content, chunk.source_type))
        self.report.add("Source + chunking", f"{files} files downloaded, split into {len(documents)} chunks", started)
        return documents

    @staticmethod
    def _history_documents(commits: list[Commit], deployments: list[Deployment],
                           pull_requests: list[PullRequest] = ()) -> list[Document]:
        """Commit, PR and CI history as searchable text, so RAG can answer "what changed" questions."""
        documents: list[Document] = []
        for start in range(0, len(commits), 10):
            lines = [
                f"Commit {item.sha[:7]} on {item.authored_at:%Y-%m-%d}: {item.message.splitlines()[0] if item.message else ''}"
                f" | files: {', '.join(item.files[:8]) or 'none'} | +{item.additions}/-{item.deletions}"
                for item in commits[start:start + 10]
            ]
            documents.append(Document("history/commits", "Recent commit history\n" + "\n".join(lines), "history"))
        failures = [item for item in deployments if item.status == "failure"]
        if failures:
            by_sha = {item.sha: item for item in commits}
            lines = [
                f"CI failure: workflow '{item.name}' failed on branch {item.branch} at {item.deployed_at:%Y-%m-%d %H:%M}"
                f" for commit {item.commit_sha[:7]}"
                + (f" ({by_sha[item.commit_sha].message.splitlines()[0]})" if item.commit_sha in by_sha and by_sha[item.commit_sha].message else "")
                for item in failures[:25]
            ]
            documents.append(Document("history/ci-failures", "CI/CD build failures\n" + "\n".join(lines), "history"))
        for start in range(0, len(pull_requests), 15):
            lines = [
                f"Pull request #{item.number} [{item.state}] {item.title} ({item.head_branch} -> {item.base_branch}),"
                f" opened {item.created_at:%Y-%m-%d}" + (f", merged {item.merged_at:%Y-%m-%d}" if item.merged_at else "")
                for item in pull_requests[start:start + 15]
            ]
            documents.append(Document("history/pull-requests", "Pull requests\n" + "\n".join(lines), "history"))
        return documents
