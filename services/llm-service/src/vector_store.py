"""Vector storage: in memory by default, PostgreSQL + pgvector when configured.

pgvector keeps every repository's chunks across restarts, searches with an HNSW cosine index,
and lets several API instances share one index. Tables live in their own `aeip` schema so they
never collide with the Prisma-managed tables in `public`.

    AEIP_VECTOR_STORE=pgvector  DATABASE_URL=postgresql://...   (Supabase works: pgvector is built in)
"""

from __future__ import annotations

import os
from typing import Any, Sequence

from .domain import VectorRecord
from .embeddings import InMemoryVectorStore


def _vector_literal(values: Sequence[float]) -> str:
    return "[" + ",".join(f"{value:.6f}" for value in values) + "]"


class PgVectorStore:
    """One table per embedding size (HNSW needs a fixed dimension), rows scoped by repository and model."""

    def __init__(self, url: str, repository: str, model: str, dimensions: int, connect: Any = None):
        import psycopg  # optional dependency

        self.repository, self.model, self.dimensions = repository.lower(), model, dimensions
        self.table = f"aeip.chunks_{dimensions}"
        self._connect = connect or (lambda: psycopg.connect(url, autocommit=True, prepare_threshold=None))
        with self._connect() as conn:
            conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            conn.execute("CREATE SCHEMA IF NOT EXISTS aeip")
            conn.execute(f"""CREATE TABLE IF NOT EXISTS {self.table} (
                repository text NOT NULL, model text NOT NULL, id text NOT NULL,
                path text NOT NULL, source_type text NOT NULL, content text NOT NULL,
                embedding vector({dimensions}) NOT NULL, updated_at timestamptz NOT NULL DEFAULT now(),
                PRIMARY KEY (repository, model, id))""")
            conn.execute(f"CREATE INDEX IF NOT EXISTS chunks_{dimensions}_hnsw ON {self.table} "
                         "USING hnsw (embedding vector_cosine_ops)")
            conn.execute(f"CREATE INDEX IF NOT EXISTS chunks_{dimensions}_repo ON {self.table} (repository, model)")

    def upsert(self, records: Sequence[VectorRecord]) -> None:
        if not records:
            return
        rows = [(self.repository, self.model, record.id, record.metadata.get("path", ""),
                 record.metadata.get("source_type", "code"), record.content, _vector_literal(record.embedding))
                for record in records]
        with self._connect() as conn, conn.cursor() as cursor:
            cursor.executemany(f"""INSERT INTO {self.table} (repository, model, id, path, source_type, content, embedding)
                VALUES (%s, %s, %s, %s, %s, %s, %s::vector)
                ON CONFLICT (repository, model, id) DO UPDATE SET path = EXCLUDED.path,
                    source_type = EXCLUDED.source_type, content = EXCLUDED.content,
                    embedding = EXCLUDED.embedding, updated_at = now()""", rows)

    def replace_all(self, records: Sequence[VectorRecord]) -> None:
        """A re-analysis replaces the repository's chunks, so deleted files stop being retrieved."""
        with self._connect() as conn:
            conn.execute(f"DELETE FROM {self.table} WHERE repository = %s AND model = %s", (self.repository, self.model))
        self.upsert(records)

    def similarity_search(self, query_embedding: Sequence[float], limit: int) -> list[VectorRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                f"""SELECT id, content, path, source_type, embedding::text FROM {self.table}
                    WHERE repository = %s AND model = %s
                    ORDER BY embedding <=> %s::vector LIMIT %s""",
                (self.repository, self.model, _vector_literal(query_embedding), limit)).fetchall()
        return [VectorRecord(row[0], row[1], tuple(float(value) for value in row[4].strip("[]").split(",")),
                             {"path": row[2], "source_type": row[3]}) for row in rows]

    def count(self) -> int:
        with self._connect() as conn:
            return conn.execute(f"SELECT count(*) FROM {self.table} WHERE repository = %s AND model = %s",
                                (self.repository, self.model)).fetchone()[0]


def make_vector_store(repository: str, model: str, dimensions: int):
    """Returns (store, note for the pipeline log). Falls back to memory if pgvector is unreachable."""
    if os.environ.get("AEIP_VECTOR_STORE", "memory").lower() == "pgvector" and os.environ.get("DATABASE_URL"):
        try:
            return PgVectorStore(os.environ["DATABASE_URL"], repository, model, dimensions), "pgvector (HNSW)"
        except Exception as exc:
            print(f"[vector-store] pgvector unavailable ({type(exc).__name__}: {exc}); using in-memory vectors")
            return InMemoryVectorStore(), "in-memory (pgvector unreachable)"
    return InMemoryVectorStore(), "in-memory"
