"""Repository-aware hybrid retrieval: semantic vector score plus lexical match score."""

from __future__ import annotations

from dataclasses import dataclass

from .domain import EmbeddingProvider, VectorRecord
from .embeddings import InMemoryVectorStore, tokenize


@dataclass(frozen=True)
class RetrievedEvidence:
    path: str
    content: str
    score: float
    source_type: str = "code"


class RepositoryRetriever:
    def __init__(self, embedder: EmbeddingProvider, store: InMemoryVectorStore):
        self.embedder = embedder
        self.store = store

    def retrieve(self, query: str, limit: int = 3) -> list[RetrievedEvidence]:
        query_terms = set(tokenize(query))
        vector = self.embedder.embed(query)
        candidates = self.store.similarity_search(vector, limit=max(limit * 10, 30))
        ranked: list[tuple[float, VectorRecord]] = []
        for record in candidates:
            semantic = sum(a * b for a, b in zip(vector, record.embedding))
            terms = set(tokenize(record.content))
            path_terms = set(tokenize(record.metadata["path"]))
            lexical = len(query_terms & terms) / max(len(query_terms), 1)
            path_match = len(query_terms & path_terms) / max(len(query_terms), 1)
            ranked.append((0.55 * semantic + 0.3 * lexical + 0.15 * path_match, record))
        return [
            RetrievedEvidence(item.metadata["path"], item.content, round(score, 3),
                              item.metadata.get("source_type", "code"))
            for score, item in sorted(ranked, reverse=True, key=lambda value: value[0])[:limit]
        ]
