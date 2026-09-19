"""JSON fixture adapter. Replace this with a Supabase adapter without changing engines."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .domain import Commit, Deployment, Document, RepositorySnapshot


class JsonSeedDataSource:
    def __init__(self, fixture_path: str | Path):
        self.fixture_path = Path(fixture_path)

    def load_snapshot(self, repository: str) -> RepositorySnapshot:
        raw = json.loads(self.fixture_path.read_text(encoding="utf-8"))
        if raw["repository"] != repository:
            raise ValueError(f"Fixture contains {raw['repository']!r}, not {repository!r}")
        commits = tuple(
            Commit(
                sha=item["sha"],
                authored_at=datetime.fromisoformat(item["authored_at"]),
                files=tuple(item["files"]),
                additions=item["additions"],
                deletions=item["deletions"],
                complexity_delta=item.get("complexity_delta", 0),
            )
            for item in raw["commits"]
        )
        deployments = tuple(
            Deployment(
                id=item["id"], deployed_at=datetime.fromisoformat(item["deployed_at"]),
                commit_sha=item["commit_sha"], status=item["status"])
            for item in raw["deployments"]
        )
        documents = tuple(Document(**item) for item in raw["documents"])
        return RepositorySnapshot(raw["repository"], commits, deployments, documents)
