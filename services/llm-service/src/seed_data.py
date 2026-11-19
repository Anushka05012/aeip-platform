"""JSON snapshot adapter, used for the demo fixture and cached GitHub analyses."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .domain import Commit, Deployment, Document, PullRequest, RepositorySnapshot


class JsonSeedDataSource:
    def __init__(self, fixture_path: str | Path):
        self.fixture_path = Path(fixture_path)

    def load_snapshot(self, repository: str) -> RepositorySnapshot:
        raw = json.loads(self.fixture_path.read_text(encoding="utf-8"))
        if raw["repository"] != repository:
            raise ValueError(f"Fixture contains {raw['repository']!r}, not {repository!r}")
        return snapshot_from_json(raw)


def snapshot_from_json(raw: dict[str, Any]) -> RepositorySnapshot:
    commits = tuple(
        Commit(
            sha=item["sha"],
            authored_at=datetime.fromisoformat(item["authored_at"]),
            files=tuple(item["files"]),
            additions=item["additions"],
            deletions=item["deletions"],
            complexity_delta=item.get("complexity_delta", 0),
            message=item.get("message", ""),
            dependency_files=tuple(item.get("dependency_files", ())),
            author=item.get("author", ""),
        )
        for item in raw["commits"]
    )
    deployments = tuple(
        Deployment(
            id=item["id"], deployed_at=datetime.fromisoformat(item["deployed_at"]),
            commit_sha=item["commit_sha"], status=item["status"],
            name=item.get("name", ""), branch=item.get("branch", ""), event=item.get("event", ""), log=item.get("log", ""),
            run_attempt=item.get("run_attempt", 1))
        for item in raw["deployments"]
    )
    documents = tuple(Document(**item) for item in raw["documents"])
    pull_requests = tuple(
        PullRequest(
            number=item["number"], title=item["title"], state=item["state"],
            head_branch=item["head_branch"], base_branch=item["base_branch"],
            created_at=datetime.fromisoformat(item["created_at"]),
            merged_at=datetime.fromisoformat(item["merged_at"]) if item.get("merged_at") else None)
        for item in raw.get("pull_requests", [])
    )
    return RepositorySnapshot(raw["repository"], commits, deployments, documents, raw.get("default_branch", ""),
                              pull_requests)


def snapshot_to_json(snapshot: RepositorySnapshot) -> dict[str, Any]:
    return {
        "repository": snapshot.repository,
        "default_branch": snapshot.default_branch,
        "commits": [
            {
                "sha": item.sha, "authored_at": item.authored_at.isoformat(), "files": list(item.files),
                "additions": item.additions, "deletions": item.deletions,
                "complexity_delta": item.complexity_delta, "message": item.message,
                "dependency_files": list(item.dependency_files), "author": item.author,
            }
            for item in snapshot.commits
        ],
        "deployments": [
            {
                "id": item.id, "deployed_at": item.deployed_at.isoformat(), "commit_sha": item.commit_sha,
                "status": item.status, "name": item.name, "branch": item.branch, "event": item.event, "log": item.log,
                "run_attempt": item.run_attempt,
            }
            for item in snapshot.deployments
        ],
        "documents": [
            {"path": item.path, "content": item.content, "source_type": item.source_type}
            for item in snapshot.documents
        ],
        "pull_requests": [
            {
                "number": item.number, "title": item.title, "state": item.state, "head_branch": item.head_branch,
                "base_branch": item.base_branch, "created_at": item.created_at.isoformat(),
                "merged_at": item.merged_at.isoformat() if item.merged_at else None,
            }
            for item in snapshot.pull_requests
        ],
    }
