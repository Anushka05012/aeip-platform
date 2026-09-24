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
_SUBWORD = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|[0-9]+")
_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "can", "do", "does", "for", "from", "how", "i",
    "in", "is", "it", "of", "on", "or", "should", "that", "the", "this", "to", "we", "what", "when",
    "where", "which", "who", "why", "with", "you", "me", "tell", "about", "there", "any", "our", "my",
}


def _stem(term: str) -> str:
    """Tiny suffix stemmer so "signatures"/"verified" match "signature"/"verify"."""
    if len(term) > 4 and term.endswith(("ies", "ied")):
        return term[:-3] + "y"
    if len(term) > 3 and term.endswith("s") and not term.endswith("ss"):
        return term[:-1]
    if len(term) > 5 and term.endswith("ing"):
        return term[:-3]
    if len(term) > 4 and term.endswith("ed"):
        return term[:-2]
    return term


def tokenize(text: str) -> list[str]:
    """Code-aware terms: `getUserName` / `get_user_name` also yield `get`, `user`, `name`."""
    terms: list[str] = []
    for token in _TERM.findall(text):
        lowered = token.lower()
        parts = [part.lower() for piece in token.split("_") for part in _SUBWORD.findall(piece)]
        for term in {_stem(word) for word in (lowered, *parts)}:
            if len(term) > 1 and term not in _STOPWORDS:
                terms.append(term)
    return terms


class HashingEmbedder:
    """A deterministic offline embedding provider; never sends repository code away."""

    def __init__(self, dimensions: int = 1024):
        self.dimensions = dimensions

    def embed(self, text: str) -> list[float]:
        values = [0.0] * self.dimensions
        for term, count in Counter(tokenize(text)).items():
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
        # A file can contribute several chunks, so the id includes the position.
        # The path is embedded too, letting "payment service" match payment_service.py.
        records = [
            VectorRecord(
                id=f"{document.path}#{index}",
                content=document.content,
                embedding=tuple(self.embedder.embed(f"{document.path}\n{document.content}")),
                metadata={"path": document.path, "source_type": document.source_type},
            )
            for index, document in enumerate(documents)
        ]
        self.store.upsert(records)
        return len(records)
