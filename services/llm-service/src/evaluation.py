"""Measured evaluation of AEIP's four judgements.

1. Retrieval: Recall@5, Hit@5 and MRR of ask-the-codebase on labelled questions over a real repository.
2. CI failure verdicts: accuracy, macro-F1, confusion matrix and harmful flips on labelled failures.
3. Incident root cause: top-1/top-3 accuracy and MRR on generated incidents with a known cause,
   against the "most recent change" heuristic engineers use by default.
4. Change risk vs later bugs: on real git history, does a file's risk score at time T predict a
   bug-fix commit touching it in the following 90 days? (ROC AUC, precision@3, against baselines.)

Everything here is deterministic (seeded) so results are reproducible; scripts/evaluate.py runs it.
"""

from __future__ import annotations

import json
import random
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Sequence

from .chunker import get_chunker_for_file
from .domain import Commit, Deployment, Document, RepositorySnapshot
from .embeddings import EmbeddingWorker, InMemoryVectorStore
from .events import OpsEvent, make_event
from .failure_analysis import build_evidence, correlate
from .git_history import GitCommit, to_commit
from .git_history import read_history as git_history
from .github_source import is_source_code
from .incidents import detect_incidents
from .rag import RepositoryRetriever
from .risk_engine import RiskEngine, is_bug_fix

# -- metrics ---------------------------------------------------------------------------------------


def ranked_unique(paths: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(paths))


def recall_at_k(ranked: Sequence[str], relevant: set[str], k: int) -> float:
    return len(set(ranked[:k]) & relevant) / len(relevant) if relevant else 0.0


def reciprocal_rank(ranked: Sequence[str], relevant: set[str]) -> float:
    return next((1 / (index + 1) for index, item in enumerate(ranked) if item in relevant), 0.0)


def roc_auc(scores: Sequence[float], labels: Sequence[bool]) -> float | None:
    """Probability that a random positive outranks a random negative (ties count half)."""
    positives = [score for score, label in zip(scores, labels) if label]
    negatives = [score for score, label in zip(scores, labels) if not label]
    if not positives or not negatives:
        return None
    wins = sum(1.0 if p > n else 0.5 if p == n else 0.0 for p in positives for n in negatives)
    return wins / (len(positives) * len(negatives))


def classification_report(expected: Sequence[str], predicted: Sequence[str], labels: Sequence[str]) -> dict[str, Any]:
    confusion = {truth: {guess: 0 for guess in labels} for truth in labels}
    for truth, guess in zip(expected, predicted):
        confusion[truth][guess] += 1
    per_class = {}
    for label in labels:
        tp = confusion[label][label]
        fp = sum(confusion[other][label] for other in labels if other != label)
        fn = sum(confusion[label][other] for other in labels if other != label)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        per_class[label] = {"precision": round(precision, 3), "recall": round(recall, 3), "f1": round(f1, 3),
                            "support": tp + fn}
    accuracy = sum(1 for truth, guess in zip(expected, predicted) if truth == guess) / max(len(expected), 1)
    return {"accuracy": round(accuracy, 3), "macroF1": round(sum(item["f1"] for item in per_class.values()) / len(labels), 3),
            "perClass": per_class, "confusion": confusion}


# -- 1. retrieval ------------------------------------------------------------------------------------


def git_documents(repo: Path, ref: str, prefix: str) -> list[Document]:
    """Chunked source files of a local git checkout at `ref` (read with git, never executed)."""
    names = subprocess.run(["git", "-C", str(repo), "ls-tree", "-r", "--name-only", ref, *([prefix] if prefix else [])],
                           capture_output=True, text=True, check=True).stdout.split()
    documents: list[Document] = []
    for name in names:
        if not name.endswith((".py", ".md", ".rst", ".ts", ".js")):
            continue
        text = subprocess.run(["git", "-C", str(repo), "show", f"{ref}:{name}"], capture_output=True,
                              text=True, encoding="utf-8", errors="ignore", check=True).stdout
        for chunk in get_chunker_for_file(name).chunk(text, source_path=name):
            documents.append(Document(name, chunk.content, chunk.source_type))
    return documents


def evaluate_retrieval(documents: Sequence[Document], questions: Sequence[dict[str, Any]],
                       embedder: Any, k: int = 5) -> dict[str, Any]:
    store = InMemoryVectorStore()
    EmbeddingWorker(embedder, store).index(documents)
    retriever = RepositoryRetriever(embedder, store)
    rows = []
    for item in questions:
        relevant = set(item["relevant"])
        ranked = ranked_unique([hit.path for hit in retriever.retrieve(item["q"], limit=60)])
        rows.append({"q": item["q"], "relevant": sorted(relevant), "top5": ranked[:k],
                     "recall": recall_at_k(ranked, relevant, k), "hit": bool(set(ranked[:k]) & relevant),
                     "rr": reciprocal_rank(ranked, relevant)})
    count = max(len(rows), 1)
    return {"questions": len(rows), "chunks": len(documents),
            f"recall@{k}": round(sum(row["recall"] for row in rows) / count, 3),
            f"hit@{k}": round(sum(row["hit"] for row in rows) / count, 3),
            "hit@1": round(sum(row["rr"] == 1.0 for row in rows) / count, 3),
            "mrr": round(sum(row["rr"] for row in rows) / count, 3), "rows": rows}


# -- 2. failure verdicts -------------------------------------------------------------------------------


def evaluate_verdicts(cases: Sequence[dict[str, Any]]) -> dict[str, Any]:
    when = datetime(2026, 9, 1, tzinfo=timezone.utc)
    expected, predicted, rows = [], [], []
    for case in cases:
        run = Deployment(f"run-{case['id']}", when, "c1", "failure", name="CI", branch="main",
                         event=case.get("event", "push"), log=case.get("log", ""))
        commit = Commit("c1", when - timedelta(minutes=5), tuple(case["changed"]), 20, 5) if case["changed"] is not None else None
        history = [run, Deployment("run-ok", when + timedelta(minutes=9), "c1", "success", name="CI")] \
            if case.get("passed_on_same_commit") else [run]
        verdict, confidence, category, _, _ = correlate(build_evidence(run, commit, [], history=history), commit is not None)
        expected.append(case["expected"])
        predicted.append(verdict)
        rows.append({"id": case["id"], "expected": case["expected"], "predicted": verdict,
                     "confidence": confidence, "category": category, "correct": verdict == case["expected"]})
    report = classification_report(expected, predicted, ["related", "unrelated", "uncertain"])
    harmful = [row["id"] for row in rows if {row["expected"], row["predicted"]} == {"related", "unrelated"}]
    return report | {"cases": len(rows), "harmfulFlips": harmful, "rows": rows}


# -- 3. incident root cause on generated incidents -------------------------------------------------------


@dataclass
class Scenario:
    snapshot: RepositorySnapshot
    events: list[OpsEvent]
    cause_ref: str
    cause_kind: str
    onset: datetime
    stack_trace_names_cause: bool
    decoy_after_cause: bool
    rolled_back: bool


def generate_scenario(rng: random.Random, index: int) -> Scenario:
    """One incident with a known cause among realistic decoys.

    A day of deploys across three services, each shipping 1-3 commits; then exactly one change
    (a deploy, a database migration or a feature-flag change) breaks production. Errors may or
    may not carry stack traces naming the changed file, decoy deploys may land between the cause
    and the first error, and the cause may or may not be rolled back.
    """
    t0 = datetime(2026, 6, 1, 12, tzinfo=timezone.utc) + timedelta(days=index)
    services = ["api", "web", "worker"]
    files = {service: [f"src/{service}/module_{i}.py" for i in range(25)] for service in services}
    commits: list[Commit] = []
    events: list[OpsEvent] = []
    last_commit: dict[str, str] = {}
    counter = 0

    def ship(service: str, when: datetime, forced_file: str | None = None) -> tuple[str, list[str]]:
        nonlocal counter
        shipped: list[str] = []
        for position in range(rng.randint(1, 3)):
            counter += 1
            sha = f"{index:04d}{counter:04d}" + "0" * 32
            changed = rng.sample(files[service], rng.randint(1, 3))
            if forced_file and position == 0:
                changed = [forced_file] + [path for path in changed if path != forced_file][:2]
            commits.append(Commit(sha, when - timedelta(minutes=rng.randint(15, 240)), tuple(changed), 40, 10))
            shipped += changed
        deploy = make_event({"source": "deploy", "kind": "deploy.succeeded", "time": when.isoformat(), "service": service,
                             "environment": "production", "commit": commits[-1].sha, "title": f"Deploy {service}",
                             "id": f"deploy-{index}-{counter}"})
        events.append(deploy)
        last_commit[service] = commits[-1].sha
        return deploy.id, shipped

    background = sorted(t0 - timedelta(minutes=rng.randint(180, 24 * 60)) for _ in range(rng.randint(2, 6)))
    for when in background:
        ship(rng.choice(services), when)

    kind = rng.choices(["deploy", "migration", "config"], weights=[70, 15, 15])[0]
    service = rng.choice(services)
    lead = timedelta(minutes=rng.randint(2, 90))
    cause_time = t0 - lead
    onset = t0
    bad_file = rng.choice(files[service])
    previous = last_commit.get(service)
    if kind == "deploy":
        cause_ref, _ = ship(service, cause_time, forced_file=bad_file)
    elif kind == "migration":
        cause_ref = f"migration-{index}"
        events.append(make_event({"source": "database", "kind": "migration", "time": cause_time.isoformat(), "id": cause_ref,
                                  "service": "db", "title": f"Applying migration {index:04d}_alter_table"}))
    else:
        cause_ref = f"flag-{index}"
        events.append(make_event({"source": "app", "kind": "flag.changed", "time": cause_time.isoformat(), "id": cause_ref,
                                  "service": service, "title": f"Feature flag new_flow_{index} enabled"}))

    decoy_after = rng.random() < 0.4 and lead > timedelta(minutes=6)
    if decoy_after:  # an unrelated deploy lands between the cause and the first error
        ship(rng.choice([item for item in services if item != service] or services),
             cause_time + (lead * rng.uniform(0.3, 0.9)))

    names_cause = kind == "deploy" and rng.random() < 0.7
    duration = timedelta(minutes=rng.randint(10, 60))
    count = rng.randint(5, 30)
    # Repeats of an error share a stack trace: 1-3 trace variants per incident, each with two frames
    # from the service (framework, handlers) and, when the deploy is the cause, the changed file.
    traces = []
    for _ in range(rng.randint(1, 3)):
        frames = rng.sample(files[service], 2)
        if names_cause:
            frames.insert(rng.randint(0, 2), bad_file)
        traces.append(frames)
    for i in range(count):
        when = onset + duration * (i / count)
        if kind == "migration":
            events.append(make_event({"source": "database", "kind": rng.choice(["lock_timeout", "deadlock"]),
                                      "time": when.isoformat(), "service": "db", "severity": "error",
                                      "title": "canceling statement due to lock timeout", "id": f"e-{index}-{i}"}))
            continue
        events.append(make_event({"source": "app", "kind": "error", "time": when.isoformat(), "service": service,
                                  "severity": "error", "title": "RuntimeError: request failed", "id": f"e-{index}-{i}",
                                  "files": rng.choice(traces)}))
    rolled_back = kind == "deploy" and previous is not None and rng.random() < 0.5
    if rolled_back:
        events.append(make_event({"source": "deploy", "kind": "deploy.succeeded", "service": service, "environment": "production",
                                  "time": (onset + duration + timedelta(minutes=2)).isoformat(), "commit": previous,
                                  "title": f"Rollback {service}", "id": f"rollback-{index}"}))
    elif kind == "migration" and rng.random() < 0.6:
        events.append(make_event({"source": "database", "kind": "migration", "service": "db",
                                  "time": (onset + duration + timedelta(minutes=3)).isoformat(),
                                  "title": f"Migration {index:04d}_alter_table finished", "id": f"mig-done-{index}"}))
    snapshot = RepositorySnapshot(f"synthetic/incident-{index}", tuple(commits), (), ())
    return Scenario(snapshot, events, cause_ref, kind, onset, names_cause, decoy_after, rolled_back)


def most_recent_change(scenario: Scenario) -> str | None:
    changes = [event for event in scenario.events if event.time < scenario.onset and (
        event.kind == "deploy.succeeded" or event.kind == "migration" or event.kind.startswith("flag."))]
    return max(changes, key=lambda event: event.time).id if changes else None


def evaluate_incidents(count: int = 300, seed: int = 7) -> dict[str, Any]:
    rng = random.Random(seed)
    rows = []
    for index in range(count):
        scenario = generate_scenario(rng, index)
        incidents = detect_incidents(scenario.snapshot, scenario.events)
        incident = min(incidents, key=lambda item: abs((item.start - scenario.onset).total_seconds()))
        refs = [candidate.ref for candidate in incident.candidates]
        rank = refs.index(scenario.cause_ref) + 1 if scenario.cause_ref in refs else None
        rows.append({"kind": scenario.cause_kind, "rank": rank, "trace": scenario.stack_trace_names_cause,
                     "decoy": scenario.decoy_after_cause, "rollback": scenario.rolled_back,
                     "baseline": most_recent_change(scenario) == scenario.cause_ref,
                     "topConfidence": incident.candidates[0].score if incident.candidates else 0.0})

    def summary(subset: list[dict[str, Any]]) -> dict[str, Any]:
        n = max(len(subset), 1)
        return {"n": len(subset), "top1": round(sum(row["rank"] == 1 for row in subset) / n, 3),
                "top3": round(sum(row["rank"] is not None and row["rank"] <= 3 for row in subset) / n, 3),
                "mrr": round(sum(1 / row["rank"] for row in subset if row["rank"]) / n, 3),
                "baselineTop1": round(sum(row["baseline"] for row in subset) / n, 3)}

    return {"overall": summary(rows),
            "byCause": {kind: summary([row for row in rows if row["kind"] == kind]) for kind in ("deploy", "migration", "config")},
            "deployWithStackTrace": summary([row for row in rows if row["kind"] == "deploy" and row["trace"]]),
            "deployWithoutStackTrace": summary([row for row in rows if row["kind"] == "deploy" and not row["trace"]]),
            "decoyBetweenCauseAndErrors": summary([row for row in rows if row["decoy"]]),
            "seed": seed}


def evaluate_incident_calibration(count: int = 300, fit_seed: int = 7, test_seed: int = 8) -> dict[str, Any]:
    """Are the evidence labels and scores of the top suggestion calibrated? Fit on one generated set, test
    on another. Only meaningful for incidents that do have a change as their cause (the generator's case)."""
    from .calibration import IsotonicCalibrator, brier_score, expected_calibration_error, reliability
    from .incidents import confidence_label

    def top_suggestions(seed: int) -> list[tuple[float, bool]]:
        rng = random.Random(seed)
        out = []
        for index in range(count):
            scenario = generate_scenario(rng, index)
            incident = min(detect_incidents(scenario.snapshot, scenario.events),
                           key=lambda item: abs((item.start - scenario.onset).total_seconds()))
            if incident.candidates:
                out.append((incident.candidates[0].score, incident.candidates[0].ref == scenario.cause_ref))
        return out

    fitted, tested = top_suggestions(fit_seed), top_suggestions(test_seed)
    by_label: dict[str, dict[str, Any]] = {}
    for name, rows in (("fit", fitted), ("test", tested)):
        for score, correct in rows:
            item = by_label.setdefault(confidence_label(score), {"fit": [0, 0], "test": [0, 0]})[name]
            item[0] += 1
            item[1] += correct
    calibrator = IsotonicCalibrator.fit([score for score, _ in fitted], [correct for _, correct in fitted])
    labels = [correct for _, correct in tested]
    return {
        "byLabel": {label: {split: {"n": n, "correct": round(hits / n, 3)} for split, (n, hits) in item.items() if n}
                    for label, item in by_label.items()},
        "eceScoreAsProbability": expected_calibration_error([score for score, _ in tested], labels),
        "eceIsotonic": expected_calibration_error([calibrator(score) for score, _ in tested], labels),
        "brierScoreAsProbability": brier_score([score for score, _ in tested], labels),
        "brierIsotonic": brier_score([calibrator(score) for score, _ in tested], labels),
        "reliabilityScore": reliability([score for score, _ in tested], labels, 5),
        "n": len(tested), "fitSeed": fit_seed, "testSeed": test_seed,
    }


# -- 4. change risk vs later bug fixes on real history ---------------------------------------------------

def _snapshot_at(repo: Path, history: Sequence[GitCommit], cutoff: datetime, window: timedelta) -> RepositorySnapshot:
    commits = tuple(to_commit(item) for item in history if cutoff - window <= item.time < cutoff)
    head = [item for item in history if item.time < cutoff][-1].sha
    return RepositorySnapshot("history", commits, (), tuple(_tree_documents(repo, head)))


def _tree_documents(repo: Path, sha: str) -> list[Document]:
    """Files at a commit: Python source with its text (for import counts), everything else by name only.
    Blob contents are read in one `git cat-file --batch` call."""
    listing = subprocess.run(["git", "-C", str(repo), "ls-tree", "-r", sha], capture_output=True, check=True).stdout
    entries = []
    for line in listing.decode("utf-8", errors="ignore").splitlines():
        meta, _, name = line.partition("\t")
        parts = meta.split()
        if len(parts) == 3 and parts[1] == "blob":
            entries.append((name, parts[2]))
    wanted = [(name, blob) for name, blob in entries if is_source_code(name) and name.endswith(".py")]
    texts: dict[str, str] = {}
    if wanted:
        out = subprocess.run(["git", "-C", str(repo), "cat-file", "--batch"], capture_output=True, check=True,
                             input="".join(f"{blob}\n" for _, blob in wanted).encode()).stdout
        position = 0
        for name, _ in wanted:
            header_end = out.index(b"\n", position)
            size = int(out[position:header_end].split()[2])
            texts[name] = out[header_end + 1:header_end + 1 + size].decode("utf-8", errors="ignore")
            position = header_end + 1 + size + 1
    return [Document(name, texts[name], "code") if name in texts else Document(name, "", "doc") for name, _ in entries]


def evaluate_risk_history(repo: Path, cutoffs: int = 12, every_days: int = 120, window_days: int = 90,
                          horizon_days: int = 90) -> dict[str, Any]:
    history = git_history(repo)
    latest = history[-1].time - timedelta(days=horizon_days)
    window, horizon = timedelta(days=window_days), timedelta(days=horizon_days)
    engine = RiskEngine()
    rows = []
    for step in range(cutoffs):
        cutoff = latest - timedelta(days=every_days * step)
        snapshot = _snapshot_at(repo, history, cutoff, window)
        risks = engine.score_files(snapshot, cutoff, window_days, is_source_code)
        later_fixes = [item for item in history if cutoff <= item.time < cutoff + horizon and is_bug_fix(item.subject)]
        buggy = {path for item in later_fixes for path, _, _ in item.files}
        if len(risks) < 4:
            continue
        labels = [risk.path in buggy for risk in risks]
        if not any(labels) or all(labels):
            continue
        by_score = [risk.score for risk in risks]
        by_churn = [risk.churn for risk in risks]
        by_changes = [risk.recent_changes for risk in risks]
        top = sorted(risks, key=lambda item: item.score, reverse=True)[:3]
        top_churn = sorted(risks, key=lambda item: item.churn, reverse=True)[:3]
        rows.append({"cutoff": cutoff.date().isoformat(), "files": len(risks), "buggy": sum(labels),
                     "aucRisk": roc_auc(by_score, labels), "aucChurn": roc_auc(by_churn, labels),
                     "aucChanges": roc_auc(by_changes, labels),
                     "precision@3": sum(item.path in buggy for item in top) / len(top),
                     "precision@3Churn": sum(item.path in buggy for item in top_churn) / len(top_churn),
                     "baseRate": round(sum(labels) / len(labels), 3)})

    def mean(key: str) -> float | None:
        values = [row[key] for row in rows if row[key] is not None]
        return round(sum(values) / len(values), 3) if values else None

    return {"cutoffsUsed": len(rows), "windowDays": window_days, "horizonDays": horizon_days,
            "meanAucRisk": mean("aucRisk"), "meanAucChurnOnly": mean("aucChurn"), "meanAucChangeCountOnly": mean("aucChanges"),
            "meanPrecision@3": mean("precision@3"), "meanPrecision@3ChurnOnly": mean("precision@3Churn"),
            "meanBaseRate": mean("baseRate"), "rows": rows}


# -- 5. learned per-repository risk vs fixed weights (temporal, no future data) ----------------------------

def recall_at_fraction(scores: Sequence[float], labels: Sequence[bool], fraction: float) -> float | None:
    """Share of the buggy files caught when reviewers check only the riskiest `fraction` of files
    (the gating metric of Meta's Diff Risk Score paper)."""
    total = sum(labels)
    if not total:
        return None
    flagged = max(1, round(len(scores) * fraction))
    order = sorted(range(len(scores)), key=lambda index: scores[index], reverse=True)[:flagged]
    return sum(labels[index] for index in order) / total


def evaluate_learned_risk(repo: Path, every_days: int = 60, window_days: int = 90, horizon_days: int = 90,
                          limit: int = 40) -> dict[str, Any]:
    """At each past date T (oldest first): fit the model on dates whose horizon ended by T, then rank the
    files changed before T and check them against bug fixes in the horizon after T."""
    from .calibration import IsotonicCalibrator
    from .learned_risk import FEATURES, TrainingRow, features, fit
    unanchored = [name for name in FEATURES if name != "fixedScore"]

    history = git_history(repo)
    latest = history[-1].time - timedelta(days=horizon_days)
    window, horizon = timedelta(days=window_days), timedelta(days=horizon_days)
    engine = RiskEngine()
    dated: list[tuple[datetime, list[TrainingRow], list[int]]] = []
    cutoff = latest
    while cutoff - window > history[0].time and len(dated) < limit:
        snapshot = _snapshot_at(repo, history, cutoff, window)
        risks = engine.score_files(snapshot, cutoff, window_days, is_source_code)
        fixed = {path for item in history if cutoff <= item.time < cutoff + horizon and is_bug_fix(item.subject)
                 for path, _, _ in item.files}
        rows = [TrainingRow(risk.path, cutoff, features(risk), risk.path in fixed, "bug fix" if risk.path in fixed else "")
                for risk in risks]
        dated.append((cutoff, rows, [risk.score for risk in risks]))
        cutoff -= timedelta(days=every_days)
    dated.reverse()

    evaluations = []
    # Calibration: (cutoff, probability, label) of every past learned prediction; a date is calibrated
    # with the predictions whose 90-day outcome was known by then.
    predicted: list[tuple[datetime, float, bool]] = []
    raw_pairs: list[tuple[float, bool]] = []
    calibrated_pairs: list[tuple[float, bool]] = []
    for index, (cutoff, rows, fixed_scores) in enumerate(dated):
        labels = [row.label for row in rows]
        if len(rows) < 4 or not any(labels) or all(labels):
            continue
        training = [row for earlier, earlier_rows, _ in dated[:index] if earlier + horizon <= cutoff for row in earlier_rows]
        model = fit(training)
        plain = fit(training, l2=1.0, names=unanchored)  # the first, unanchored design (kept for the report)
        scores = {
            "fixed": [float(score) for score in fixed_scores],
            "changes": [row.x["changes"] for row in rows],
            "pastFixes": [row.x["pastFixes"] + row.x["changes"] / 100 for row in rows],  # ties broken by changes
        }
        if model:
            scores["learned"] = [model.probability(row.x) for row in rows]
            known = [(p, y) for at, p, y in predicted if at + horizon <= cutoff]
            if len(known) >= CALIBRATION_MIN_POINTS and sum(y for _, y in known) >= 20:
                calibrator = IsotonicCalibrator.fit([p for p, _ in known], [y for _, y in known])
                raw_pairs += list(zip(scores["learned"], labels))
                calibrated_pairs += [(calibrator(p), y) for p, y in zip(scores["learned"], labels)]
            predicted += [(cutoff, p, y) for p, y in zip(scores["learned"], labels)]
        if plain:
            scores["learnedUnanchored"] = [plain.probability(row.x) for row in rows]
        evaluations.append({
            "cutoff": cutoff.date().isoformat(), "files": len(rows), "buggy": sum(labels),
            "trainingPositives": sum(row.label for row in training),
            "auc": {name: roc_auc(values, labels) for name, values in scores.items()},
            "recall@20%": {name: recall_at_fraction(values, labels, 0.2) for name, values in scores.items()},
        })

    def mean_over(rows: list[dict[str, Any]], metric: str, name: str) -> float | None:
        values = [row[metric][name] for row in rows if row[metric].get(name) is not None]
        return round(sum(values) / len(values), 3) if values else None

    learned_rows = [row for row in evaluations if "learned" in row["auc"]]
    methods = ("learned", "learnedUnanchored", "fixed", "changes", "pastFixes")
    # Cold start: how the advantage over fixed weights grows with the labels available for training.
    buckets = [(10, 49), (50, 149), (150, 499), (500, 10**9)]
    cold_start = []
    for low, high in buckets:
        in_bucket = [row for row in learned_rows if low <= row["trainingPositives"] <= high]
        if in_bucket:
            cold_start.append({"positives": f"{low}-{high}" if high < 10**9 else f"{low}+", "dates": len(in_bucket),
                               "aucLearned": mean_over(in_bucket, "auc", "learned"),
                               "aucUnanchored": mean_over(in_bucket, "auc", "learnedUnanchored"),
                               "aucFixed": mean_over(in_bucket, "auc", "fixed")})
    final_model = fit([row for _, rows, _ in dated for row in rows])
    return {
        "datesEvaluated": len(learned_rows), "datesTotal": len(evaluations), "everyDays": every_days,
        "windowDays": window_days, "horizonDays": horizon_days,
        "auc": {name: mean_over(learned_rows, "auc", name) for name in methods},
        "recall@20%": {name: mean_over(learned_rows, "recall@20%", name) for name in methods},
        "learnedWins": sum(1 for row in learned_rows if row["auc"]["learned"] > row["auc"]["fixed"]),
        "coldStart": cold_start,
        "calibration": _calibration_report(raw_pairs, calibrated_pairs),
        "weights": final_model.to_json()["weights"] if final_model else None,
        "rows": evaluations,
    }


CALIBRATION_MIN_POINTS = 200


def _calibration_report(raw: Sequence[tuple[float, bool]], calibrated: Sequence[tuple[float, bool]]) -> dict[str, Any]:
    from .calibration import brier_score, expected_calibration_error, reliability
    if not raw:
        return {"predictions": 0}
    labels = [y for _, y in raw]
    return {
        "predictions": len(raw), "baseRate": round(sum(labels) / len(labels), 3),
        "eceRaw": expected_calibration_error([p for p, _ in raw], labels),
        "eceCalibrated": expected_calibration_error([p for p, _ in calibrated], labels),
        "brierRaw": brier_score([p for p, _ in raw], labels),
        "brierCalibrated": brier_score([p for p, _ in calibrated], labels),
        "reliabilityRaw": reliability([p for p, _ in raw], labels, 5),
        "reliabilityCalibrated": reliability([p for p, _ in calibrated], labels, 5),
        "pairs": {"raw": [(round(p, 4), y) for p, y in raw], "calibrated": [(round(p, 4), y) for p, y in calibrated]},
    }


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))

