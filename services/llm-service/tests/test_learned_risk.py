import random
from datetime import datetime, timedelta, timezone

import pytest

from src.domain import Commit, RepositorySnapshot
from src.evaluation import recall_at_fraction, roc_auc
from src.feedback import FeedbackStore
from src.learned_risk import (FEATURES, IncidentLabel, LearnedRiskModel, RiskLearning, TrainingRow, fit, learn,
                              rows_at)
from src.web_api import IntelligenceDemoService

NOW = datetime(2026, 9, 1, tzinfo=timezone.utc)


def _row(rng: random.Random, broke: bool) -> TrainingRow:
    x = {name: rng.random() for name in FEATURES}
    x["pastFixes"] = rng.random() + (1.5 if broke else 0.0)  # past fixes carry the signal
    return TrainingRow("f.py", NOW, x, broke, "bug fix" if broke else "")


def test_the_model_learns_which_signal_predicts_breakage():
    rng = random.Random(3)
    rows = [_row(rng, index % 4 == 0) for index in range(400)]
    model = fit(rows)
    assert model is not None
    assert max(model.weights, key=lambda name: model.weights[name]) == "pastFixes"
    test = [_row(rng, index % 4 == 0) for index in range(200)]
    assert roc_auc([model.probability(row.x) for row in test], [row.label for row in test]) > 0.9
    assert model.contributions(test[0].x)[0][0] == "pastFixes"


def test_too_few_labels_means_no_model():
    rng = random.Random(1)
    assert fit([_row(rng, index < 5) for index in range(100)]) is None


def test_model_round_trips_through_json():
    rng = random.Random(2)
    model = fit([_row(rng, index % 3 == 0) for index in range(90)])
    restored = LearnedRiskModel.from_json(model.to_json())
    row = _row(rng, True)
    assert abs(restored.probability(row.x) - model.probability(row.x)) < 1e-3


def _commit(sha: str, days: float, files: tuple[str, ...], message: str) -> Commit:
    return Commit(sha, NOW + timedelta(days=days), files, 40, 10, 0, message)


def test_training_rows_never_use_the_future_for_features():
    commits = (
        _commit("a", -20, ("src/pay.py",), "add refunds"),
        _commit("b", -10, ("src/cart.py",), "add coupons"),
        _commit("c", 5, ("src/pay.py",), "fix refund rounding bug"),   # after the cutoff: label only
        _commit("d", 6, ("src/pay.py", "src/cart.py"), "rework checkout"),
    )
    snapshot = RepositorySnapshot("acme/shop", commits, (), ())
    rows = {row.path: row for row in rows_at(snapshot, NOW, window_days=30, horizon_days=30)}
    assert set(rows) == {"src/pay.py", "src/cart.py"}
    assert rows["src/pay.py"].label and rows["src/pay.py"].source == "bug fix"
    assert not rows["src/cart.py"].label
    assert rows["src/pay.py"].x["changes"] == rows["src/cart.py"].x["changes"]  # one change each before NOW
    assert rows["src/pay.py"].x["pastFixes"] == 0.0


def test_confirmed_incidents_label_files_and_count_as_past_incidents():
    commits = (_commit("a", -40, ("src/pay.py",), "add refunds"), _commit("b", -5, ("src/pay.py",), "tweak"))
    snapshot = RepositorySnapshot("acme/shop", commits, (), ())
    incidents = [IncidentLabel(NOW - timedelta(days=30), ("src/pay.py",)),
                 IncidentLabel(NOW + timedelta(days=3), ("src/pay.py",))]
    rows = rows_at(snapshot, NOW, window_days=60, horizon_days=30, incidents=incidents)
    assert rows[0].source == "incident" and rows[0].x["pastIncidents"] > 0


def test_learning_is_used_only_with_enough_labels():
    rng = random.Random(4)
    model = fit([_row(rng, index % 4 == 0) for index in range(100)])  # 25 labels
    learning = RiskLearning(model, 100, 25, 0, 90)
    assert not learning.active and "25 of 50" in learning.status()["message"]
    learning = RiskLearning(model, 400, 60, 6, 90)
    assert learning.active and "6 from confirmed incidents" in learning.status()["message"]


def test_learn_on_a_quiet_history_falls_back_to_the_fixed_score():
    snapshot = RepositorySnapshot("acme/shop", (_commit("a", -3, ("src/pay.py",), "init"),), (), ())
    learning = learn(snapshot, NOW)
    assert learning.model is None and not learning.active


def test_recall_at_fraction_counts_buggy_files_in_the_flagged_share():
    assert recall_at_fraction([0.9, 0.8, 0.1, 0.2, 0.3], [True, False, True, False, False], 0.2) == 0.5
    assert recall_at_fraction([0.9, 0.1], [False, False], 0.5) is None


def test_feedback_store_keeps_the_newest_verdict_and_persists(tmp_path):
    store = FeedbackStore(tmp_path)
    store.record("acme/shop", "inc-1", "deploy-7", "rejected", NOW, ["src/a.py"], "ana")
    store.record("acme/shop", "inc-1", "deploy-7", "confirmed", NOW, ["src/a.py", "src/b.py"], "ana")
    reloaded = FeedbackStore(tmp_path)
    assert reloaded.for_incident("acme/shop", "inc-1") == {"deploy-7": "confirmed"}
    assert reloaded.labels("ACME/shop") == [IncidentLabel(NOW, ("src/a.py", "src/b.py"))]
    with pytest.raises(ValueError):
        store.record("acme/shop", "inc-1", "deploy-7", "maybe", NOW, [])


def test_confirming_a_demo_incident_cause_becomes_a_training_label(tmp_path):
    service = IntelligenceDemoService(cache_dir=tmp_path)
    incident = service.incidents()["incidents"][0]
    detail = service.incident(incident["id"])
    assert detail["feedback"] == {}
    top = detail["candidates"][0]
    result = service.record_feedback(None, incident["id"], top["ref"], "confirmed", "ana")
    assert result["feedback"] == {top["ref"]: "confirmed"} and result["files"]
    assert result["riskModel"]["incidentLabels"] >= 0  # demo history is short: still learning
    assert service.incident(incident["id"])["feedback"] == {top["ref"]: "confirmed"}
    assert len(service.feedback.labels(service.risk_model()["repository"])) == 1
    with pytest.raises(KeyError):
        service.record_feedback(None, incident["id"], "no-such-change", "confirmed")
