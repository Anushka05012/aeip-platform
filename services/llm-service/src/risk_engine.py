"""Explainable, deterministic file risk scoring."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta

from .domain import RepositorySnapshot


@dataclass(frozen=True)
class RiskResult:
    path: str
    score: int
    level: str
    recent_changes: int
    churn: int
    complexity_delta: int
    reasons: tuple[str, ...]


class RiskEngine:
    def score_files(self, snapshot: RepositorySnapshot, now: datetime) -> list[RiskResult]:
        cutoff = now - timedelta(days=7)
        recent = [commit for commit in snapshot.commits if commit.authored_at >= cutoff]
        frequency: Counter[str] = Counter(path for commit in recent for path in commit.files)
        results: list[RiskResult] = []
        for path, changes in frequency.items():
            touching = [commit for commit in recent if path in commit.files]
            churn = sum(commit.additions + commit.deletions for commit in touching)
            complexity = sum(commit.complexity_delta for commit in touching)
            # Each component is capped before weighting, keeping the result 0-100.
            frequency_points = min(changes / 10, 1) * 40
            churn_points = min(churn / 500, 1) * 35
            complexity_points = min(complexity / 50, 1) * 25
            score = round(frequency_points + churn_points + complexity_points)
            level = "high" if score >= 70 else "medium" if score >= 40 else "low"
            reasons = (
                f"{changes} changes in the last 7 days",
                f"{churn} lines added or removed",
                f"complexity increased by {complexity}",
            )
            results.append(RiskResult(path, score, level, changes, churn, complexity, reasons))
        return sorted(results, key=lambda result: result.score, reverse=True)
