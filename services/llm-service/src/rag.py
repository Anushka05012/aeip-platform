"""Repository-aware hybrid retrieval: semantic vector score plus lexical match score."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .domain import EmbeddingProvider, VectorRecord
from .embeddings import InMemoryVectorStore


@dataclass(frozen=True)
class RetrievedEvidence:
    path: str
    content: str
    score: float


class RepositoryRetriever:
    def __init__(self, embedder: EmbeddingProvider, store: InMemoryVectorStore):
        self.embedder = embedder
        self.store = store

    def retrieve(self, query: str, limit: int = 3) -> list[RetrievedEvidence]:
        query_terms = set(re.findall(r"\w+", query.lower()))
        vector = self.embedder.embed(query)
        candidates = self.store.similarity_search(vector, limit=max(limit * 3, 10))
        ranked: list[tuple[float, VectorRecord]] = []
        for record in candidates:
            semantic = sum(a * b for a, b in zip(vector, record.embedding))
            terms = set(re.findall(r"\w+", record.content.lower()))
            lexical = len(query_terms & terms) / max(len(query_terms), 1)
            ranked.append((0.7 * semantic + 0.3 * lexical, record))
        return [RetrievedEvidence(item.metadata["path"], item.content, round(score, 3))
                for score, item in sorted(ranked, reverse=True, key=lambda value: value[0])[:limit]]
