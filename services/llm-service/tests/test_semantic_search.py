import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.domain import Document, VectorRecord
from src.embeddings import EmbeddingCache, EmbeddingWorker, HashingEmbedder, InMemoryVectorStore, make_embedder
from src.rag import RepositoryRetriever

DOCS = [
    Document("src/billing/charge.py", "def process_payment(order, gateway):\n    return gateway.charge(order.total)", "code"),
    Document("src/ui/navbar.tsx", "export function Navbar({ user }) { return <nav>{user.name}</nav> }", "code"),
    Document("src/auth/session.py", "def verify_token(token):\n    return hmac.compare_digest(sign(token.body), token.sig)", "code"),
    Document("docs/runbook.md", "If the site is slow, scale the web dynos and check the CDN cache hit rate.", "doc"),
]
# Paraphrases that share (almost) no words with the code they should find.
QUESTIONS = [
    ("where do we bill a customer's credit card?", "src/billing/charge.py"),
    ("how is a login credential validated?", "src/auth/session.py"),
    ("what to do when pages load slowly", "docs/runbook.md"),
]


def semantic_embedder(tmp_path):
    try:
        from src.embeddings import SemanticEmbedder
        return SemanticEmbedder(cache=EmbeddingCache(tmp_path / "embeddings.sqlite"))
    except Exception as exc:  # fastembed missing or the model cannot be downloaded (offline CI)
        pytest.skip(f"semantic model unavailable: {exc}")


def top_hits(embedder):
    store = InMemoryVectorStore()
    EmbeddingWorker(embedder, store).index(DOCS)
    retriever = RepositoryRetriever(embedder, store)
    return [retriever.retrieve(question, limit=1)[0].path for question, _ in QUESTIONS]


def test_semantic_model_finds_code_by_meaning(tmp_path):
    assert top_hits(semantic_embedder(tmp_path)) == [path for _, path in QUESTIONS]


def test_semantic_model_beats_word_hashing_on_paraphrases(tmp_path):
    expected = [path for _, path in QUESTIONS]
    semantic = sum(a == b for a, b in zip(top_hits(semantic_embedder(tmp_path)), expected))
    hashing = sum(a == b for a, b in zip(top_hits(HashingEmbedder()), expected))
    assert semantic > hashing


def test_embedding_cache_avoids_recomputing(tmp_path):
    embedder = semantic_embedder(tmp_path)
    first = embedder.embed_documents(["alpha beta", "gamma"])

    class Exploding:
        def embed(self, *args, **kwargs):
            raise AssertionError("cache miss: the model was called again")

    embedder._model = Exploding()
    assert embedder.embed_documents(["gamma", "alpha beta"]) == [first[1], first[0]]


def test_auto_mode_falls_back_to_hashing_when_the_model_is_missing(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def no_fastembed(name, *args, **kwargs):
        if name == "fastembed":
            raise ImportError("not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setenv("AEIP_EMBEDDINGS", "auto")
    monkeypatch.setattr(builtins, "__import__", no_fastembed)
    from src import embeddings
    monkeypatch.setattr(embeddings, "_MODELS", {})
    embedder, note = make_embedder()
    assert isinstance(embedder, HashingEmbedder) and note.startswith("hashing")


@pytest.mark.skipif(not os.environ.get("AEIP_TEST_DATABASE_URL"), reason="set AEIP_TEST_DATABASE_URL to a pgvector database")
def test_pgvector_store_round_trip():
    from src.vector_store import PgVectorStore

    url = os.environ["AEIP_TEST_DATABASE_URL"]
    store = PgVectorStore(url, "Test/Repo", "unit-test-model", 3)
    other = PgVectorStore(url, "test/other", "unit-test-model", 3)
    store.replace_all([VectorRecord("a#0", "alpha", (1.0, 0.0, 0.0), {"path": "a.py", "source_type": "code"}),
                       VectorRecord("b#0", "beta", (0.0, 1.0, 0.0), {"path": "b.py", "source_type": "code"})])
    other.replace_all([VectorRecord("z#0", "zeta", (1.0, 0.0, 0.0), {"path": "z.py", "source_type": "code"})])
    hits = store.similarity_search((0.9, 0.1, 0.0), 2)
    assert [hit.metadata["path"] for hit in hits] == ["a.py", "b.py"]  # nearest first, other repo excluded
    assert hits[0].embedding == (1.0, 0.0, 0.0)
    store.replace_all([VectorRecord("b#0", "beta", (0.0, 1.0, 0.0), {"path": "b.py", "source_type": "code"})])
    assert store.count() == 1  # re-analysis drops chunks of deleted files
