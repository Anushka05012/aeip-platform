import os

import pytest

# Deterministic, fast tests: the hashing embedder unless a test opts into the semantic model.
os.environ.setdefault("AEIP_EMBEDDINGS", "hashing")
os.environ.setdefault("AEIP_VECTOR_STORE", "memory")


@pytest.fixture(autouse=True)
def no_network_git_history(monkeypatch):
    """Tests never clone from GitHub; tests that need history inject a loader."""
    import src.web_api as web_api
    monkeypatch.setattr(web_api, "git_history_loader", lambda cache_dir: None)
