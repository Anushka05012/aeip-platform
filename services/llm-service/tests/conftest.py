import os

# Deterministic, fast tests: the hashing embedder unless a test opts into the semantic model.
os.environ.setdefault("AEIP_EMBEDDINGS", "hashing")
os.environ.setdefault("AEIP_VECTOR_STORE", "memory")
