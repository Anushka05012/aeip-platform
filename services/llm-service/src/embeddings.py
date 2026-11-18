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
    def __init__(self, embedder: EmbeddingProvider, store: "InMemoryVectorStore | object"):
        self.embedder = embedder
        self.store = store

    def index(self, documents: Sequence[Document]) -> int:
        # A file can contribute several chunks, so the id includes the position.
        # The path is embedded too, letting "payment service" match payment_service.py.
        texts = [f"{document.path}\n{document.content}" for document in documents]
        batch = getattr(self.embedder, "embed_documents", None)
        vectors = batch(texts) if batch else [self.embedder.embed(text) for text in texts]
        records = [
            VectorRecord(
                id=f"{document.path}#{index}",
                content=document.content,
                embedding=tuple(vector),
                metadata={"path": document.path, "source_type": document.source_type},
            )
            for index, (document, vector) in enumerate(zip(documents, vectors))
        ]
        replace = getattr(self.store, "replace_all", None)
        if replace:
            replace(records)
        else:
            self.store.upsert(records)
        return len(records)


# -- semantic embeddings (local ONNX model) ------------------------------------------------------

import os  # noqa: E402
import sqlite3  # noqa: E402
import struct  # noqa: E402
import threading  # noqa: E402
from pathlib import Path  # noqa: E402

DEFAULT_SEMANTIC_MODEL = "BAAI/bge-small-en-v1.5"
_MODELS: dict[str, object] = {}
_MODELS_LOCK = threading.Lock()


class SemanticEmbedder:
    """A real sentence-embedding model (bge-small, 384 dimensions) run locally with ONNX through
    fastembed. Like the hashing embedder it never sends code anywhere; unlike it, it matches
    meaning ("charge the card" finds `process_payment`), not just shared words."""

    def __init__(self, model: str = DEFAULT_SEMANTIC_MODEL, cache: "EmbeddingCache | None" = None):
        from fastembed import TextEmbedding  # optional dependency, imported only when used

        with _MODELS_LOCK:  # one model per process, shared by every repository's pipeline
            if model not in _MODELS:
                _MODELS[model] = TextEmbedding(model)
        self._model = _MODELS[model]
        self.name = model
        self.dimensions = 384 if "small" in model else len(next(iter(self._model.embed(["probe"]))))
        self.cache = cache

    def embed(self, text: str) -> list[float]:
        """Query embedding (bge uses a query instruction prefix)."""
        return [float(value) for value in next(iter(self._model.query_embed([text])))]

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        cached = self.cache.get_many(self.name, texts) if self.cache else {}
        missing = [text for text in dict.fromkeys(texts) if text not in cached]
        if missing:
            fresh = {text: [float(value) for value in vector]
                     for text, vector in zip(missing, self._model.embed(missing, batch_size=64))}
            if self.cache:
                self.cache.put_many(self.name, fresh)
            cached.update(fresh)
        return [cached[text] for text in texts]


class EmbeddingCache:
    """Embeddings keyed by sha256(model + text) in SQLite, so restarts and re-analyses only embed
    chunks that changed."""

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._db.execute("CREATE TABLE IF NOT EXISTS embeddings (key TEXT PRIMARY KEY, vector BLOB)")
        self._lock = threading.Lock()

    @staticmethod
    def _key(model: str, text: str) -> str:
        return hashlib.sha256(f"{model}\n{text}".encode()).hexdigest()

    def get_many(self, model: str, texts: Sequence[str]) -> dict[str, list[float]]:
        keys = {self._key(model, text): text for text in texts}
        found: dict[str, list[float]] = {}
        with self._lock:
            items = list(keys.items())
            for start in range(0, len(items), 500):
                batch = dict(items[start:start + 500])
                rows = self._db.execute(f"SELECT key, vector FROM embeddings WHERE key IN ({','.join('?' * len(batch))})",
                                        list(batch)).fetchall()
                for key, blob in rows:
                    found[batch[key]] = list(struct.unpack(f"{len(blob) // 4}f", blob))
        return found

    def put_many(self, model: str, vectors: dict[str, list[float]]) -> None:
        with self._lock:
            self._db.executemany("INSERT OR REPLACE INTO embeddings VALUES (?, ?)",
                                 [(self._key(model, text), struct.pack(f"{len(vector)}f", *vector))
                                  for text, vector in vectors.items()])
            self._db.commit()


def make_embedder(cache_dir: Path | None = None):
    """AEIP_EMBEDDINGS: "auto" (default: semantic if fastembed is installed and the model loads,
    else hashing), "semantic", or "hashing". Returns (embedder, note for the pipeline log)."""
    mode = os.environ.get("AEIP_EMBEDDINGS", "auto").lower()
    if mode in ("auto", "semantic", "bge"):
        try:
            cache = EmbeddingCache(cache_dir / "embeddings.sqlite") if cache_dir else None
            embedder = SemanticEmbedder(os.environ.get("AEIP_EMBEDDING_MODEL", DEFAULT_SEMANTIC_MODEL), cache)
            return embedder, f"{embedder.name.split('/')[-1]} ({embedder.dimensions}-d, local)"
        except Exception as exc:  # not installed, or the model could not be downloaded
            if mode != "auto":
                raise
            print(f"[embeddings] semantic model unavailable ({type(exc).__name__}); using hashing embeddings")
    return HashingEmbedder(), "hashing (1024-d, offline)"
