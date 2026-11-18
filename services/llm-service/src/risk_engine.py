"""Explainable, deterministic file risk scoring.

Six signals, each capped before weighting so the score stays 0-100 and every point can be traced:

| Signal              | Max | Meaning                                                            |
|---------------------|-----|--------------------------------------------------------------------|
| change frequency    | 30  | how often the file changed in the window                           |
| churn               | 25  | lines added + removed by those changes                             |
| complexity          | 15  | branching (if/for/while/...) added by those changes                |
| test gap            | 15  | no matching test file, or changes that did not touch any test      |
| blast radius        | 10  | how many other files import this one                               |
| dependency churn    |  5  | changed in the same commit as a dependency manifest/lockfile       |

Past bug fixes in the window are recorded too (`past_fixes`). They are not part of this fixed score, so
its numbers stay comparable over time; the learned model (learned_risk.py) uses them.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import PurePosixPath
from typing import Callable

from .domain import RepositorySnapshot

_TEST_DIRS = {"test", "tests", "__tests__", "spec", "specs"}
_TEST_NAME = re.compile(r"^test_.+|.+_test\.\w+$|.+\.(test|spec)\.\w+$|.+Tests?\.\w+$")
_GENERIC_STEMS = {"index", "main", "init", "__init__", "mod", "lib", "app"}
_FIX = re.compile(r"\b(fix(es|ed)?|bug|regression|revert|crash(es)?|broken)\b", re.IGNORECASE)
_NOT_A_CODE_FIX = re.compile(r"\b(typo|docs?|readme|changelog|spelling|ci|lint|mypy|tests?)\b", re.IGNORECASE)
_NOT_TESTABLE = {".md", ".mdx", ".txt", ".rst", ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".sql", ".sh"}


def is_bug_fix(message: str) -> bool:
    """A commit that fixes a bug in code (not docs, typos, CI or tests), judged from its first line."""
    subject = message.splitlines()[0] if message else ""
    return bool(_FIX.search(subject)) and not _NOT_A_CODE_FIX.search(subject)


def is_testable(path: str) -> bool:
    """Code that unit tests can cover (not docs, config or scripts)."""
    return PurePosixPath(path).suffix.lower() not in _NOT_TESTABLE


def is_test_path(path: str) -> bool:
    pure = PurePosixPath(path)
    return any(part.lower() in _TEST_DIRS for part in pure.parts[:-1]) or bool(_TEST_NAME.match(pure.name))


def module_name(path: str) -> str:
    """The name other files use to import this one (parent dir for index/__init__ files)."""
    pure = PurePosixPath(path)
    return pure.parent.name if pure.stem.lower() in _GENERIC_STEMS and pure.parent.name else pure.stem


def covered_module(path: str) -> str:
    """'tests/test_payment.py' -> 'payment', 'src/cart.spec.ts' -> 'cart', 'PaymentTest.java' -> 'payment'."""
    name = PurePosixPath(path).name.lower()
    name = re.sub(r"\.(test|spec)(?=\.\w+$)", "", name)
    stem = PurePosixPath(name).stem
    stem = re.sub(r"^test_|_test$|tests?$", "", stem)
    return stem.strip("_")


@dataclass(frozen=True)
class RiskResult:
    path: str
    score: int
    level: str
    recent_changes: int
    churn: int
    complexity_delta: int
    reasons: tuple[str, ...]
    has_tests: bool = False
    test_touch_ratio: float = 0.0  # share of this file's changes that also changed a test
    dependents: int = 0  # other files that import this one
    dependency_changes: int = 0  # changes made together with a dependency update
    testable: bool = True  # docs/config have no test-gap signal
    past_fixes: int = 0  # bug-fix commits that touched this file in the window

    def breakdown(self) -> dict[str, int]:
        """Points per signal, for the UI."""
        return {
            "frequency": round(min(self.recent_changes / 10, 1) * 30),
            "churn": round(min(self.churn / 500, 1) * 25),
            "complexity": round(min(self.complexity_delta / 50, 1) * 15),
            "testGap": _test_gap_points(self.has_tests, self.test_touch_ratio) if self.testable else 0,
            "blastRadius": round(min(self.dependents / 10, 1) * 10),
            "dependencies": 5 if self.dependency_changes else 0,
        }


def _test_gap_points(has_tests: bool, touch_ratio: float) -> int:
    # No test file at all is the full gap; a tested file loses points only for untested changes.
    return 15 if not has_tests else round(7 * (1 - touch_ratio))


def _import_counts(sources: dict[str, str], targets: set[str]) -> dict[str, int]:
    """For each target path: how many other source files reference its module name in an import line."""
    names: dict[str, list[str]] = defaultdict(list)
    for path in targets:
        name = module_name(path)
        if len(name) >= 3:
            names[name].append(path)
    if not names:
        return {}
    import_line = re.compile(r"^\s*(?:import|from|using|require|include|#include)\b.*$|require\(.*?\)|import\(.*?\)",
                             re.MULTILINE)
    word = re.compile(r"[A-Za-z_][A-Za-z0-9_-]*")
    counts: Counter[str] = Counter()
    for path, text in sources.items():
        referenced = {token for line in import_line.findall(text) for token in word.findall(line)}
        for name in referenced & names.keys():
            for target in names[name]:
                if target != path:
                    counts[target] += 1
    return counts


class RiskEngine:
    def score_files(self, snapshot: RepositorySnapshot, now: datetime, window_days: int = 7,
                    include: Callable[[str], bool] | None = None) -> list[RiskResult]:
        """Score files changed in the window. `include` limits which files are scored (e.g. production code);
        tests and dependency files still count as evidence either way."""
        cutoff = now - timedelta(days=window_days)
        recent = [commit for commit in snapshot.commits if commit.authored_at >= cutoff]
        frequency: Counter[str] = Counter(
            path for commit in recent for path in commit.files
            if not is_test_path(path) and (include is None or include(path)))

        known_paths = {document.path for document in snapshot.documents} | {
            path for commit in snapshot.commits for path in commit.files}
        tested = {covered_module(path) for path in known_paths if is_test_path(path)}
        # Test folders named after a module also count: tests/test_utils/test_x.py covers "utils".
        tested |= {covered_module(part + ".x") for path in known_paths if is_test_path(path)
                   for part in PurePosixPath(path).parts[:-1] if _TEST_NAME.match(part + ".x")}
        sources: dict[str, str] = defaultdict(str)
        for document in snapshot.documents:
            if document.source_type == "code":
                sources[document.path] += document.content + "\n"
        dependents = _import_counts(sources, set(frequency))

        results: list[RiskResult] = []
        for path, changes in frequency.items():
            touching = [commit for commit in recent if path in commit.files]
            churn = sum(commit.additions + commit.deletions for commit in touching)
            complexity = sum(commit.complexity_delta for commit in touching)
            stem = PurePosixPath(path).stem.lower()
            has_tests = stem in tested or module_name(path).lower() in tested
            with_tests = sum(1 for commit in touching if any(is_test_path(item) for item in commit.files))
            touch_ratio = round(with_tests / len(touching), 2) if touching else 0.0
            dependency_changes = sum(1 for commit in touching if commit.dependency_files)
            past_fixes = sum(1 for commit in touching if is_bug_fix(commit.message))
            result = RiskResult(path, 0, "low", changes, churn, complexity, (), has_tests, touch_ratio,
                                dependents.get(path, 0), dependency_changes, is_testable(path))
            score = sum(result.breakdown().values())
            level = "high" if score >= 70 else "medium" if score >= 40 else "low"
            reasons = [
                f"{changes} change{'s' if changes != 1 else ''} in the last {window_days} days",
                f"{churn} lines added or removed",
                f"complexity increased by {complexity}",
            ]
            if result.testable:
                reasons.append("no matching test file" if not has_tests else
                               f"tests changed in {with_tests} of {len(touching)} changes")
            if result.dependents:
                reasons.append(f"imported by {result.dependents} other file{'s' if result.dependents != 1 else ''}")
            if dependency_changes:
                reasons.append(f"changed alongside a dependency update {dependency_changes} time"
                               f"{'s' if dependency_changes != 1 else ''}")
            if past_fixes:
                reasons.append(f"{past_fixes} bug fix{'es' if past_fixes != 1 else ''} in the last {window_days} days")
            results.append(RiskResult(path, score, level, changes, churn, complexity, tuple(reasons), has_tests,
                                      touch_ratio, result.dependents, dependency_changes, result.testable, past_fixes))
        return sorted(results, key=lambda result: result.score, reverse=True)
