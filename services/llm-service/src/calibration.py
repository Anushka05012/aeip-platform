"""Calibration: when AEIP says "80%", it should be right about 80% of the time.

* `IsotonicCalibrator`: maps raw scores to observed frequencies with the pool-adjacent-violators
  algorithm (monotonic: a higher score never gets a lower probability). Pure Python.
* `expected_calibration_error`: the average gap between stated confidence and observed frequency,
  weighted by how many predictions fall in each confidence bin (0 = perfectly calibrated).
* `brier_score`: mean squared error of the probabilities (lower is better; rewards calibration and
  ranking together).
* `reliability`: the per-bin table behind a reliability diagram.

Calibrators are always fitted on predictions made *before* the ones they are applied to (or on a
separate set), never on the predictions they are scored on.
"""

from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass
from typing import Any, Sequence


@dataclass
class IsotonicCalibrator:
    thresholds: list[float]  # upper score of each block, ascending
    values: list[float]  # calibrated probability of each block, non-decreasing
    points: int = 0
    positives: int = 0

    @classmethod
    def fit(cls, scores: Sequence[float], labels: Sequence[bool]) -> "IsotonicCalibrator":
        pairs = sorted(zip(scores, labels), key=lambda item: item[0])
        blocks: list[list[float]] = []  # [sum of labels, count, highest score]
        for score, label in pairs:
            blocks.append([1.0 if label else 0.0, 1.0, score])
            while len(blocks) > 1 and blocks[-2][0] / blocks[-2][1] >= blocks[-1][0] / blocks[-1][1]:
                total, count, top = blocks.pop()
                blocks[-1][0] += total
                blocks[-1][1] += count
                blocks[-1][2] = top
        return cls([block[2] for block in blocks], [block[0] / block[1] for block in blocks],
                   len(pairs), sum(1 for _, label in pairs if label))

    def __call__(self, score: float) -> float:
        if not self.values:
            return score
        # The first block whose highest score reaches this score (scores above every block get the last).
        return self.values[min(bisect_left(self.thresholds, score), len(self.values) - 1)]

    def to_json(self) -> dict[str, Any]:
        return {"thresholds": [round(value, 6) for value in self.thresholds],
                "values": [round(value, 4) for value in self.values], "points": self.points, "positives": self.positives}

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "IsotonicCalibrator":
        return cls(list(data["thresholds"]), list(data["values"]), data.get("points", 0), data.get("positives", 0))


def reliability(probabilities: Sequence[float], labels: Sequence[bool], bins: int = 10) -> list[dict[str, Any]]:
    rows = []
    for index in range(bins):
        low, high = index / bins, (index + 1) / bins
        members = [(p, y) for p, y in zip(probabilities, labels)
                   if low <= p < high or (index == bins - 1 and p == 1.0)]
        if members:
            rows.append({"bin": f"{low:.1f}-{high:.1f}", "n": len(members),
                         "stated": round(sum(p for p, _ in members) / len(members), 3),
                         "observed": round(sum(1 for _, y in members if y) / len(members), 3)})
    return rows


def expected_calibration_error(probabilities: Sequence[float], labels: Sequence[bool], bins: int = 10) -> float | None:
    if not probabilities:
        return None
    total = len(probabilities)
    return round(sum(row["n"] / total * abs(row["stated"] - row["observed"])
                     for row in reliability(probabilities, labels, bins)), 4)


def brier_score(probabilities: Sequence[float], labels: Sequence[bool]) -> float | None:
    if not probabilities:
        return None
    return round(sum((p - (1.0 if y else 0.0)) ** 2 for p, y in zip(probabilities, labels)) / len(probabilities), 4)
