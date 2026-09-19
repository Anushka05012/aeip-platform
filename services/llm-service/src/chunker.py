"""
Chunking logic for repository code and documentation files.

Scope (Sept 10 sprint task): turn a source file's raw text into a list of
overlapping, token-bounded `Chunk` objects that are ready to be embedded
by the worker Anushka builds next (Sept 11: "vector embedding generation
worker"). This module does NOT call any embedding or LLM API — it's pure
text processing so it's fast, deterministic, and easy to unit test.

Strategy:
- Recursive splitting: try to break on the "nicest" boundary first
  (class/function boundaries for code, headers/paragraphs for docs),
  and only fall back to a hard token-window split if a section is still
  too big.
- Overlap: consecutive chunks share a small tail/head of tokens so
  retrieval doesn't lose context at a chunk boundary.
- Token counts are approximate: we use tiktoken's cl100k_base encoder as
  a consistent, fast proxy for "roughly how big is this chunk", not as
  the exact tokenizer Llama models use internally. That's fine for
  sizing chunks — it doesn't need to be exact, just consistent.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List, Optional

# tiktoken gives a more accurate token count, but it downloads its BPE
# vocab file from the network on first use. In environments without that
# network access (some CI runners, locked-down sandboxes) we fall back to
# a whitespace-based approximate tokenizer. Either way, count_tokens() is
# only used for *relative* chunk sizing, so the fallback's lower accuracy
# doesn't change how the chunker behaves.
try:
    import tiktoken

    _tiktoken_encoder = tiktoken.get_encoding("cl100k_base")

    def _encode(text: str) -> list:
        return _tiktoken_encoder.encode(text, disallowed_special=())

    def _decode(tokens: list) -> str:
        return _tiktoken_encoder.decode(tokens)

except Exception:  # pragma: no cover - exercised when tiktoken can't load its vocab
    import re

    _WORD_RE = re.compile(r"\S+|\s+")

    def _encode(text: str) -> list:
        # crude fallback "tokens": words and whitespace runs, kept separate
        # so _decode can reconstruct the original text exactly.
        return _WORD_RE.findall(text)

    def _decode(tokens: list) -> str:
        return "".join(tokens)

# Extensions we treat as "code" vs "docs". Extend as the repo mix becomes clear.
CODE_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go", ".rb", ".rs",
    ".c", ".cpp", ".h", ".hpp", ".cs", ".php", ".sql", ".sh", ".yaml", ".yml", ".json",
}
DOC_EXTENSIONS = {".md", ".mdx", ".txt", ".rst"}


def count_tokens(text: str) -> int:
    """Approximate token count for a piece of text."""
    return len(_encode(text))


@dataclass
class Chunk:
    """A single chunk ready for embedding + storage in pgvector."""

    source_path: str
    source_type: str  # "code" | "doc"
    content: str
    chunk_index: int
    token_count: int = field(init=False)
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        self.token_count = count_tokens(self.content)


def _split_on_separators(text: str, separators: List[str]) -> List[str]:
    """
    Try each separator in order; use the first one that actually splits
    the text into more than one piece. Falls back to the raw text
    (as a single "piece") if none of the separators apply.
    """
    for sep in separators:
        if sep == "":
            # last resort: no natural separator, caller will hard-split by tokens
            return [text]
        if sep in text:
            parts = text.split(sep)
            # re-attach the separator so we don't lose newlines/structure,
            # except for the first part which never had a leading separator
            rebuilt = [parts[0]] + [sep + p for p in parts[1:]]
            return [p for p in rebuilt if p.strip()]
    return [text]


def _hard_split_by_tokens(text: str, max_tokens: int, overlap_tokens: int) -> List[str]:
    """Fallback: split purely by token windows with overlap, no regard for structure."""
    tokens = _encode(text)
    if len(tokens) <= max_tokens:
        return [text]

    step = max(max_tokens - overlap_tokens, 1)
    pieces = []
    for start in range(0, len(tokens), step):
        window = tokens[start : start + max_tokens]
        pieces.append(_decode(window))
        if start + max_tokens >= len(tokens):
            break
    return pieces


def _recursive_split(text: str, separators: List[str], max_tokens: int, overlap_tokens: int) -> List[str]:
    """
    Core recursive splitter shared by code and doc chunkers.
    Splits on the highest-priority separator, then recurses into any
    piece that's still too big, finally hard-splitting by tokens.
    """
    if count_tokens(text) <= max_tokens:
        return [text] if text.strip() else []

    pieces = _split_on_separators(text, separators)

    if len(pieces) == 1:
        # no separator applied — hard split by tokens
        return _hard_split_by_tokens(text, max_tokens, overlap_tokens)

    results: List[str] = []
    for piece in pieces:
        if count_tokens(piece) <= max_tokens:
            results.append(piece)
        else:
            # still too big: recurse using the same separator hierarchy,
            # which will naturally fall through to lower-priority
            # separators (and eventually the hard token split) since the
            # separator that was just used no longer splits this piece.
            results.extend(_recursive_split(piece, separators, max_tokens, overlap_tokens))

    return _merge_with_overlap(results, max_tokens, overlap_tokens)


def _merge_with_overlap(pieces: List[str], max_tokens: int, overlap_tokens: int) -> List[str]:
    """
    Greedily pack small adjacent pieces together up to max_tokens, and
    prepend a small overlap from the end of the previous chunk so
    context isn't lost at the boundary.
    """
    if not pieces:
        return []

    merged: List[str] = []
    current = ""

    for piece in pieces:
        candidate = current + piece if current else piece
        if count_tokens(candidate) <= max_tokens:
            current = candidate
        else:
            if current:
                merged.append(current)
            current = piece

    if current:
        merged.append(current)

    if overlap_tokens <= 0 or len(merged) <= 1:
        return merged

    overlapped = [merged[0]]
    for prev, curr in zip(merged, merged[1:]):
        prev_tokens = _encode(prev)
        tail = _decode(prev_tokens[-overlap_tokens:]) if len(prev_tokens) > overlap_tokens else prev
        overlapped.append(tail + curr)

    return overlapped


class BaseChunker:
    separators: List[str] = ["\n\n", "\n", " ", ""]
    source_type: str = "doc"

    def __init__(self, max_tokens: int = 500, overlap_tokens: int = 50):
        self.max_tokens = max_tokens
        self.overlap_tokens = overlap_tokens

    def chunk(self, text: str, source_path: str) -> List[Chunk]:
        pieces = _recursive_split(text, self.separators, self.max_tokens, self.overlap_tokens)
        return [
            Chunk(source_path=source_path, source_type=self.source_type, content=piece, chunk_index=i)
            for i, piece in enumerate(pieces)
            if piece.strip()
        ]


class CodeChunker(BaseChunker):
    """
    Chunks source code, preferring to break on class/function boundaries
    before falling back to blank lines, then hard token windows.
    Language-agnostic on purpose (repos are polyglot); a per-language
    AST-aware splitter is a reasonable future upgrade, not needed yet.
    """

    source_type = "code"
    separators = [
        "\nclass ",
        "\ndef ",
        "\nfunction ",
        "\nexport function ",
        "\nexport default ",
        "\n\n",
        "\n",
        " ",
        "",
    ]


class MarkdownChunker(BaseChunker):
    """
    Chunks documentation/markdown, preferring to break on headers before
    falling back to paragraph and line boundaries.
    """

    source_type = "doc"
    separators = [
        "\n## ",
        "\n### ",
        "\n#### ",
        "\n\n",
        "\n",
        " ",
        "",
    ]


def get_chunker_for_file(path: str, max_tokens: int = 500, overlap_tokens: int = 50) -> BaseChunker:
    ext = os.path.splitext(path)[1].lower()
    if ext in DOC_EXTENSIONS:
        return MarkdownChunker(max_tokens=max_tokens, overlap_tokens=overlap_tokens)
    # default to the code chunker for anything else (code or unknown-but-textual)
    return CodeChunker(max_tokens=max_tokens, overlap_tokens=overlap_tokens)


def chunk_file(path: str, max_tokens: int = 500, overlap_tokens: int = 50) -> List[Chunk]:
    """Read a file from disk and return its chunks. Skips binary/unreadable files."""
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
    except (OSError, UnicodeDecodeError):
        return []

    chunker = get_chunker_for_file(path, max_tokens=max_tokens, overlap_tokens=overlap_tokens)
    return chunker.chunk(text, source_path=path)


def chunk_repository(root_dir: str, max_tokens: int = 500, overlap_tokens: int = 50,
                      ignore_dirs: Optional[set] = None) -> List[Chunk]:
    """
    Walk a repository directory and chunk every code/doc file found.
    This is what the Sept 11 ingestion -> embedding worker will call
    once GitHub connector pulls a repo down locally (or via API).
    """
    ignore_dirs = ignore_dirs or {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build"}
    all_chunks: List[Chunk] = []

    for dirpath, dirnames, filenames in os.walk(root_dir):
        dirnames[:] = [d for d in dirnames if d not in ignore_dirs]
        for filename in filenames:
            ext = os.path.splitext(filename)[1].lower()
            if ext not in CODE_EXTENSIONS and ext not in DOC_EXTENSIONS:
                continue
            full_path = os.path.join(dirpath, filename)
            all_chunks.extend(chunk_file(full_path, max_tokens=max_tokens, overlap_tokens=overlap_tokens))

    return all_chunks
