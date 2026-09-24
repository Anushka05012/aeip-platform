"""Stable domain objects shared by local demos and future ingestion adapters."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, Sequence


@dataclass(frozen=True)
class Commit:
    sha: str
    authored_at: datetime
    files: tuple[str, ...]
    additions: int
    deletions: int
    complexity_delta: int = 0
    message: str = ""


@dataclass(frozen=True)
class Deployment:
    id: str
    deployed_at: datetime
    commit_sha: str
    status: str  # "success" or "failure"
    name: str = ""
    branch: str = ""
    event: str = ""  # what triggered the CI run: "push", "schedule", "pull_request", ...
    log: str = ""  # stored CI log text, when the source provides it (demo fixture)


@dataclass(frozen=True)
class Document:
    path: str
    content: str
    source_type: str = "code"


@dataclass(frozen=True)
class RepositorySnapshot:
    repository: str
    commits: tuple[Commit, ...]
    deployments: tuple[Deployment, ...]
    documents: tuple[Document, ...]
    default_branch: str = ""


class AnalyticsDataSource(Protocol):
    """Contract Snehal's adapter will implement after ingestion is available."""

    def load_snapshot(self, repository: str) -> RepositorySnapshot:
        """Return commits, deployments and searchable code/docs for one repository."""


class EmbeddingProvider(Protocol):
    def embed(self, text: str) -> list[float]: ...


class VectorStore(Protocol):
    def upsert(self, records: Sequence["VectorRecord"]) -> None: ...

    def similarity_search(self, query_embedding: Sequence[float], limit: int) -> list["VectorRecord"]: ...


@dataclass(frozen=True)
class VectorRecord:
    id: str
    content: str
    embedding: tuple[float, ...]
    metadata: dict[str, str]
