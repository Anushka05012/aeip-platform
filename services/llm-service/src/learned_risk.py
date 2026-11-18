"""A per-repository risk model that learns from what actually broke.

The fixed risk score (risk_engine.py) uses the same weights for every repository. This module learns
the weights for one repository from its own past:

* features: the risk signals of a file over a window (changes, churn, complexity, test gap, blast
  radius, dependency updates) plus its past bug fixes and past incidents;
* label: did the file need a bug fix, or was it part of a change confirmed as an incident's cause, in
  the following horizon? Confirmed incident causes come from engineers' feedback on AEIP's own incident
  attribution (feedback.py), so labels are grounded in production, not only in commit messages;
* model: logistic regression on standardised features, fitted with Newton's method. It is *anchored*
  on the fixed score: that score is an unpenalised input, and every other signal's weight is pulled
  towards zero (L2). With few labels the model therefore ranks like the fixed score; as labels
  accumulate, it learns the corrections this repository needs. (Without the anchor the model overfit
  on repositories with few bug fixes; see docs/EVALUATION.md.) Pure Python, deterministic, and small
  enough to explain: each prediction is a sum of weight x signal contributions shown to the engineer.

Training rows are only ever built from windows whose horizon has fully passed before the moment being
scored, so the model never sees the future.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Iterable, Sequence

from .domain import Commit, RepositorySnapshot
from .events import as_utc
from .risk_engine import RiskEngine, RiskResult, is_bug_fix

FEATURES = ("fixedScore", "changes", "churn", "complexity", "testGap", "blastRadius", "dependencies", "pastFixes",
            "pastIncidents")
UNPENALISED = ("fixedScore",)
LABELS = {
    "fixedScore": "AEIP's base risk score",
    "changes": "recent changes", "churn": "lines changed", "complexity": "complexity added",
    "testGap": "test gap", "blastRadius": "files that import it", "dependencies": "dependency updates",
    "pastFixes": "past bug fixes", "pastIncidents": "past incidents",
}
MIN_POSITIVES = 10  # the least a fit is attempted with (the evaluation reports the whole curve from here)
# AEIP uses the learned ranking only from this many labelled files. On eight real repositories, with 50+
# labels the learned model averaged AUC 0.737 against 0.647 for the fixed score (never behind on average in any
# repository; tied on two), while below 50 it was a coin toss (docs/EVALUATION.md, section 6).
# Until then the fixed score is shown with "learning: N of 50".
USE_FROM_POSITIVES = 50
L2 = 20.0  # pull towards the fixed score; chosen before the held-out repositories were scored


def features(result: RiskResult, past_incidents: int = 0) -> dict[str, float]:
    return {
        "fixedScore": result.score / 100,
        "changes": math.log1p(result.recent_changes),
        "churn": math.log1p(result.churn),
        "complexity": math.log1p(max(result.complexity_delta, 0)),
        "testGap": result.breakdown()["testGap"] / 15,
        "blastRadius": math.log1p(result.dependents),
        "dependencies": 1.0 if result.dependency_changes else 0.0,
        "pastFixes": math.log1p(result.past_fixes),
        "pastIncidents": math.log1p(past_incidents),
    }


@dataclass(frozen=True)
class TrainingRow:
    path: str
    at: datetime  # the moment the features describe; the label covers the horizon after it
    x: dict[str, float]
    label: bool
    source: str = ""  # "bug fix", "incident" or "" for negatives


@dataclass
class LearnedRiskModel:
    weights: dict[str, float]
    bias: float
    means: dict[str, float]
    scales: dict[str, float]
    rows: int
    positives: int
    incident_labels: int = 0
    trained_at: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def _z(self, x: dict[str, float]) -> dict[str, float]:
        return {name: (x.get(name, 0.0) - self.means[name]) / self.scales[name] for name in self.weights}

    def probability(self, x: dict[str, float]) -> float:
        z = self._z(x)
        return _sigmoid(self.bias + sum(self.weights[name] * z[name] for name in self.weights))

    def contributions(self, x: dict[str, float]) -> list[tuple[str, float]]:
        """Log-odds each signal adds compared with an average file, largest effect first."""
        z = self._z(x)
        parts = [(name, self.weights[name] * z[name]) for name in self.weights if self.weights[name] * z[name] != 0]
        return sorted(parts, key=lambda item: abs(item[1]), reverse=True)

    def explain(self, x: dict[str, float], top: int = 3) -> list[str]:
        return [f"{LABELS[name]} {'raise' if value > 0 else 'lower'} the risk"
                for name, value in self.contributions(x)[:top] if abs(value) >= 0.1]

    def to_json(self) -> dict[str, Any]:
        return {"weights": {name: round(value, 4) for name, value in self.weights.items()}, "bias": round(self.bias, 4),
                "means": self.means, "scales": self.scales, "rows": self.rows, "positives": self.positives,
                "incidentLabels": self.incident_labels, "trainedAt": self.trained_at, **self.extra}

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "LearnedRiskModel":
        return cls(data["weights"], data["bias"], data["means"], data["scales"], data["rows"], data["positives"],
                   data.get("incidentLabels", 0), data.get("trainedAt", ""))


def _sigmoid(value: float) -> float:
    if value >= 0:
        return 1 / (1 + math.exp(-value))
    exp = math.exp(value)
    return exp / (1 + exp)


def _solve(matrix: list[list[float]], vector: list[float]) -> list[float]:
    """Gaussian elimination with partial pivoting (the system is tiny: one row per feature + bias)."""
    size = len(vector)
    a = [row[:] + [vector[index]] for index, row in enumerate(matrix)]
    for col in range(size):
        pivot = max(range(col, size), key=lambda row: abs(a[row][col]))
        a[col], a[pivot] = a[pivot], a[col]
        if abs(a[col][col]) < 1e-12:
            continue
        for row in range(size):
            if row != col:
                factor = a[row][col] / a[col][col]
                for k in range(col, size + 1):
                    a[row][k] -= factor * a[col][k]
    return [a[row][size] / a[row][row] if abs(a[row][row]) >= 1e-12 else 0.0 for row in range(size)]


def fit(rows: Sequence[TrainingRow], l2: float = L2, iterations: int = 25,
        names: Sequence[str] = FEATURES) -> LearnedRiskModel | None:
    """Fit the model; None when there are too few positive (or negative) examples to learn from."""
    positives = sum(row.label for row in rows)
    if positives < MIN_POSITIVES or positives == len(rows):
        return None
    means = {name: sum(row.x[name] for row in rows) / len(rows) for name in names}
    scales = {}
    for name in names:
        variance = sum((row.x[name] - means[name]) ** 2 for row in rows) / len(rows)
        scales[name] = math.sqrt(variance) or 1.0
    data = [[1.0] + [(row.x[name] - means[name]) / scales[name] for name in names] for row in rows]
    labels = [1.0 if row.label else 0.0 for row in rows]
    size = len(names) + 1
    beta = [0.0] * size
    base = positives / len(rows)
    beta[0] = math.log(base / (1 - base))
    for _ in range(iterations):
        gradient = [0.0] * size
        hessian = [[0.0] * size for _ in range(size)]
        for x, y in zip(data, labels):
            p = _sigmoid(sum(b * v for b, v in zip(beta, x)))
            weight = p * (1 - p)
            for i in range(size):
                gradient[i] += (y - p) * x[i]
                for j in range(i, size):
                    hessian[i][j] += weight * x[i] * x[j]
        for i in range(1, size):  # no penalty on the intercept or the anchor
            if names[i - 1] not in UNPENALISED:
                gradient[i] -= l2 * beta[i]
                hessian[i][i] += l2
        for i in range(size):
            for j in range(i):
                hessian[i][j] = hessian[j][i]
        step = _solve(hessian, gradient)
        beta = [b + s for b, s in zip(beta, step)]
        if max(abs(s) for s in step) < 1e-6:
            break
    return LearnedRiskModel({name: beta[index + 1] for index, name in enumerate(names)}, beta[0], means, scales,
                            len(rows), positives, sum(1 for row in rows if row.source == "incident"))


# -- training rows from a repository's own history ---------------------------------------------------------

@dataclass(frozen=True)
class IncidentLabel:
    """A change an engineer confirmed as an incident's cause: the files it touched broke production."""
    at: datetime
    files: tuple[str, ...]


def rows_at(snapshot: RepositorySnapshot, cutoff: datetime, window_days: int, horizon_days: int,
            incidents: Sequence[IncidentLabel] = (), include: Callable[[str], bool] | None = None,
            engine: RiskEngine | None = None) -> list[TrainingRow]:
    """Features of every file changed in the window before `cutoff`, labelled by what happened in the
    horizon after it. Call only with cutoffs whose horizon has passed."""
    before = RepositorySnapshot(snapshot.repository, tuple(c for c in snapshot.commits if c.authored_at < cutoff),
                                (), snapshot.documents)
    results = (engine or RiskEngine()).score_files(before, cutoff, window_days, include)
    end = cutoff + timedelta(days=horizon_days)
    fixed_later = {path for commit in snapshot.commits if cutoff <= commit.authored_at < end and is_bug_fix(commit.message)
                   for path in commit.files}
    broke_later = {path for label in incidents if as_utc(cutoff) <= as_utc(label.at) < as_utc(end) for path in label.files}
    window_start = cutoff - timedelta(days=window_days)
    rows = []
    for result in results:
        past = sum(1 for label in incidents
                   if as_utc(window_start) <= as_utc(label.at) < as_utc(cutoff) and result.path in label.files)
        source = "incident" if result.path in broke_later else "bug fix" if result.path in fixed_later else ""
        rows.append(TrainingRow(result.path, cutoff, features(result, past), bool(source), source))
    return rows


def training_cutoffs(commits: Iterable[Commit], now: datetime, horizon_days: int, every_days: int,
                     limit: int = 24) -> list[datetime]:
    """Past moments whose horizon ended before `now`, newest first, back to the first commit."""
    first = min((commit.authored_at for commit in commits), default=now)
    cutoffs = []
    cutoff = now - timedelta(days=horizon_days)
    while cutoff > first and len(cutoffs) < limit:
        cutoffs.append(cutoff)
        cutoff -= timedelta(days=every_days)
    return cutoffs


@dataclass
class RiskLearning:
    """What AEIP has learned for one repository, and whether it is trusted enough to use."""
    model: LearnedRiskModel | None
    rows: int
    positives: int
    incident_labels: int
    window_days: int

    @property
    def active(self) -> bool:
        return self.model is not None and self.positives >= USE_FROM_POSITIVES

    def past_incidents(self, path: str, incidents: Sequence[IncidentLabel], now: datetime) -> int:
        start = now - timedelta(days=self.window_days)
        return sum(1 for label in incidents if as_utc(start) <= as_utc(label.at) < as_utc(now) and path in label.files)

    def assess(self, result: RiskResult, past_incidents: int = 0) -> dict[str, Any] | None:
        """Probability and the signals behind it, when the model is active."""
        if not self.active or self.model is None:
            return None
        x = features(result, past_incidents)
        return {"probability": round(self.model.probability(x), 3), "drivers": self.model.explain(x)}

    def status(self, saved_causes: int = 0) -> dict[str, Any]:
        """`saved_causes`: confirmed incident causes on record, including ones too recent to train on yet."""
        weights = self.model.to_json()["weights"] if self.model else {}
        if self.active:
            message = (f"Learned from {self.positives} files that later broke "
                       f"({self.incident_labels} from confirmed incidents)")
        else:
            message = f"Learning: {self.positives} of {USE_FROM_POSITIVES} labelled files"
            if saved_causes:
                message += f"; {saved_causes} confirmed incident cause{'s' if saved_causes != 1 else ''} saved"
            message += ("; the history is too short to learn from yet" if not self.rows else "") + \
                "; using the fixed score until then"
        return {
            "active": self.active, "labels": self.positives, "incidentLabels": self.incident_labels,
            "bugFixLabels": self.positives - self.incident_labels, "examples": self.rows,
            "needed": USE_FROM_POSITIVES, "savedCauses": saved_causes, "message": message,
            "weights": [{"signal": LABELS[name], "weight": round(value, 3)}
                        for name, value in sorted(weights.items(), key=lambda item: -abs(item[1]))],
        }


def learn(snapshot: RepositorySnapshot, now: datetime, window_days: int = 90, horizon_days: int = 60,
          every_days: int = 30, incidents: Sequence[IncidentLabel] = (),
          include: Callable[[str], bool] | None = None) -> RiskLearning:
    """Train on the repository's own history (no data after `now - horizon`)."""
    engine = RiskEngine()
    rows = [row for cutoff in training_cutoffs(snapshot.commits, now, horizon_days, every_days)
            for row in rows_at(snapshot, cutoff, window_days, horizon_days, incidents, include, engine)]
    model = fit(rows)
    if model:
        model.trained_at = now.isoformat()
    return RiskLearning(model, len(rows), sum(row.label for row in rows),
                        sum(1 for row in rows if row.source == "incident"), window_days)
