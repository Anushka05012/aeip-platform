"""Evaluation on public, externally labelled datasets (not written by the AEIP team).

LogChunks (Brandt, Panichella, Zaidman, Beller; MSR 2020; CC-BY 4.0; doi:10.5281/zenodo.3632351):
797 real Travis CI build logs from 80 GitHub repositories in 29 languages. For each failed log the
authors labelled the chunk that says why the build failed, and checked a sample with the developers
who caused the failure. We measure how much of that chunk AEIP's extractor puts in front of the
engineer (and the LLM), against simple baselines with the same 40-line budget.

The repositories are split in half by a hash of their name: improvements were developed on the
"dev" half only, and the "test" half is reported separately as the held-out result.

Get the data (read-only; nothing in it is executed):
    https://zenodo.org/records/3632351  ->  unzip into <datasets>/logchunks/
"""

from __future__ import annotations

import hashlib
import re
import statistics
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator, Sequence

from .failure_analysis import _ERROR_LINE, _TIMESTAMP, extract_error_lines

# Matches escape sequences with or without the ESC byte: the labelled chunks were stored without it.
_ANSI_LOOSE = re.compile(r"(\x1b)?\[[0-9;?]*[A-Za-z]")
BUDGET = 40


@dataclass(frozen=True)
class LabelledLog:
    repository: str
    log_path: str
    text: str
    chunk_lines: tuple[str, ...]
    split: str


def _normalise(line: str) -> str:
    return re.sub(r"\s+", " ", _ANSI_LOOSE.sub("", line)).strip()


def split_for(file_stem: str) -> str:
    """Hash of the dataset's file name ("owner@repo"); fixed so the held-out half never changes."""
    return "test" if int(hashlib.sha256(file_stem.encode()).hexdigest(), 16) % 2 else "dev"


def logchunks_root(datasets: Path) -> Path | None:
    for candidate in (datasets / "logchunks" / "LogChunks", datasets / "LogChunks", datasets / "logchunks"):
        if (candidate / "build-failure-reason").is_dir():
            return candidate
    return None


def load_logchunks(root: Path) -> Iterator[LabelledLog]:
    for xml_file in sorted((root / "build-failure-reason").glob("*/*.xml")):
        repository = xml_file.stem.replace("@", "/")
        for example in ET.parse(xml_file).getroot():
            log_path = example.findtext("Log") or ""
            chunk = [_normalise(line) for line in (example.findtext("Chunk") or "").splitlines()]
            chunk = [line for line in chunk if line]
            log_file = root / "logs" / log_path
            if not chunk or not log_file.is_file():
                continue
            yield LabelledLog(repository, log_path, log_file.read_text(encoding="utf-8", errors="replace"),
                              tuple(chunk), split_for(xml_file.stem))


def chunk_coverage(selected: Sequence[str], chunk: Sequence[str]) -> float:
    """Share of the labelled chunk's lines that appear in the selected lines."""
    shown = [_normalise(line) for line in selected]
    found = sum(1 for line in chunk if any(line in item or (len(item) > 8 and item in line) for item in shown))
    return found / len(chunk)


def tail_lines(log: str, budget: int = BUDGET) -> list[str]:
    """Baseline: the last lines of the log, which is where engineers look first."""
    return [line for line in log.splitlines() if line.strip()][-budget:]


def previous_extractor(log: str, budget: int = BUDGET) -> list[str]:
    """AEIP's extractor before the LogChunks evaluation (kept to report the before/after)."""
    lines = [_TIMESTAMP.sub("", line).rstrip() for line in log.splitlines()]
    lines = [line for line in lines if line.strip() and not line.startswith("##[group]")]
    keep: list[int] = []
    for index, line in enumerate(lines):
        if _ERROR_LINE.search(line):
            keep.extend(range(max(index - 1, 0), min(index + 2, len(lines))))
    selected, seen = [], set()
    for index in sorted(set(keep)):
        text = lines[index].replace("##[error]", "ERROR: ").strip()
        if text not in seen:
            seen.add(text)
            selected.append(text[:400])
    return (selected or lines)[-budget:]


METHODS: dict[str, Callable[[str], list[str]]] = {
    "aeip": lambda log: extract_error_lines(log, max_lines=BUDGET),
    "aeipPrevious": previous_extractor,
    "tail40": tail_lines,
}


def _summary(scores: Sequence[float], sizes: Sequence[int]) -> dict[str, float]:
    return {"n": len(scores),
            "lineRecall": round(statistics.mean(scores), 3),
            "anyLineFound": round(sum(score > 0 for score in scores) / len(scores), 3),
            "wholeChunkFound": round(sum(score >= 0.999 for score in scores) / len(scores), 3),
            "meanLinesShown": round(statistics.mean(sizes), 1)}


def evaluate_logchunks(root: Path) -> dict:
    scores: dict[str, dict[str, list[float]]] = {}
    sizes: dict[str, dict[str, list[int]]] = {}
    repositories: set[str] = set()
    for item in load_logchunks(root):
        repositories.add(item.repository)
        for name, method in METHODS.items():
            selected = method(item.text)
            for split in (item.split, "all"):
                scores.setdefault(split, {}).setdefault(name, []).append(chunk_coverage(selected, item.chunk_lines))
                sizes.setdefault(split, {}).setdefault(name, []).append(len(selected))
    return {"dataset": "LogChunks (MSR 2020)", "repositories": len(repositories), "budget": BUDGET,
            **{split: {name: _summary(values, sizes[split][name]) for name, values in by_method.items()}
               for split, by_method in scores.items()}}
