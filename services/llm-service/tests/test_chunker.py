import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.chunker import CodeChunker, MarkdownChunker, count_tokens, get_chunker_for_file


def test_small_text_returns_single_chunk():
    chunker = MarkdownChunker(max_tokens=500, overlap_tokens=50)
    chunks = chunker.chunk("# Title\n\nJust a short doc.", source_path="README.md")
    assert len(chunks) == 1
    assert chunks[0].source_type == "doc"
    assert chunks[0].token_count > 0


def test_large_markdown_splits_on_headers():
    body = "\n\n".join(f"Paragraph {i} " + ("word " * 200) for i in range(3))
    text = f"## Section A\n\n{body}\n\n## Section B\n\n{body}"
    chunker = MarkdownChunker(max_tokens=150, overlap_tokens=20)
    chunks = chunker.chunk(text, source_path="docs/guide.md")

    assert len(chunks) > 1
    # chunks should stay in the right ballpark; overlap + fallback tokenizer
    # rounding means we allow some slack rather than a hard ceiling
    assert all(c.token_count <= (150 + 20) * 1.5 for c in chunks)


def test_large_code_splits_and_stays_under_budget():
    functions = "\n\n".join(f"def func_{i}():\n    " + ("x = 1\n    " * 50) for i in range(5))
    chunker = CodeChunker(max_tokens=100, overlap_tokens=10)
    chunks = chunker.chunk(functions, source_path="src/app.py")

    assert len(chunks) > 1
    for c in chunks:
        assert c.token_count <= (100 + 10) * 1.5


def test_chunks_have_sequential_index_and_metadata_defaults():
    chunker = CodeChunker(max_tokens=50, overlap_tokens=5)
    text = "def a():\n    pass\n\ndef b():\n    pass\n\ndef c():\n    pass\n" * 10
    chunks = chunker.chunk(text, source_path="src/thing.py")

    indices = [c.chunk_index for c in chunks]
    assert indices == list(range(len(chunks)))
    for c in chunks:
        assert c.source_path == "src/thing.py"
        assert c.metadata == {}


def test_get_chunker_for_file_picks_by_extension():
    assert isinstance(get_chunker_for_file("docs/readme.md"), MarkdownChunker)
    assert isinstance(get_chunker_for_file("src/index.ts"), CodeChunker)
    assert isinstance(get_chunker_for_file("scripts/run.sh"), CodeChunker)


def test_count_tokens_is_positive_and_monotonic_ish():
    short = count_tokens("hello world")
    longer = count_tokens("hello world " * 20)
    assert short > 0
    assert longer > short


def test_no_chunk_is_empty():
    chunker = MarkdownChunker(max_tokens=80, overlap_tokens=10)
    text = "\n\n".join(["Some text here."] * 40)
    chunks = chunker.chunk(text, source_path="docs/x.md")
    assert all(c.content.strip() for c in chunks)
