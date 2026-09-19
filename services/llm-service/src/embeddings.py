"""Dependency-free local embeddings and vector store for demos and tests.

The interfaces in domain.py intentionally match a production embedding API and
pgvector store, so either can replace these classes later.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from typing import Sequence

from .domain import Document, EmbeddingProvider, VectorRecord

_TERM = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]*")


class HashingEmbedder:
    """A deterministic offline embedding provider; never sends repository code away."""

    def __init__(self, dimensions: int = 128):
        self.dimensions = dimensions

    def embed(self, text: str) -> list[float]:
        values = [0.0] * self.dimensions
        for term, count in Counter(token.lower() for token in _TERM.findall(text)).items():
            digest = hashlib.sha256(term.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            values[index] += count * (1 if digest[4] % 2 else -1)
        length = math.sqrt(sum(value * value for value in values))
        return [value / length for value in values] if length else values


class InMemoryVectorStore:
    def __init__(self):
        self.records: list[VectorRecord] = []

    def upsert(self, records: Sequence[VectorRecord]) -> None:
        by_id = {record.id: record for record in self.records}
        by_id.update({record.id: record for record in records})
        self.records = list(by_id.values())

    def similarity_search(self, query_embedding: Sequence[float], limit: int) -> list[VectorRecord]:
        return sorted(
            self.records,
            key=lambda record: sum(a * b for a, b in zip(record.embedding, query_embedding)),
            reverse=True,
        )[:limit]


class EmbeddingWorker:
    def __init__(self, embedder: EmbeddingProvider, store: InMemoryVectorStore):
        self.embedder = embedder
        self.store = store

    def index(self, documents: Sequence[Document]) -> int:
        records = [
            VectorRecord(
                id=document.path,
                content=document.content,
                embedding=tuple(self.embedder.embed(document.content)),
                metadata={"path": document.path, "source_type": document.source_type},
            )
            for document in documents
        ]
        self.store.upsert(records)
        return len(records)
