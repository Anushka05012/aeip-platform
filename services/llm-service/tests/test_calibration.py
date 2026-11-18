import random
from datetime import datetime, timedelta, timezone

from src.calibration import IsotonicCalibrator, brier_score, expected_calibration_error, reliability
from src.learned_risk import FEATURES, RiskLearning, TrainingRow, backtest, fit
from src.risk_engine import RiskResult
from src.web_api import IntelligenceDemoService


def test_isotonic_calibration_is_monotonic_and_matches_frequencies():
    scores = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]
    labels = [False, True, False, False, True, True, False, True]
    calibrator = IsotonicCalibrator.fit(scores, labels)
    mapped = [calibrator(score) for score in scores]
    assert mapped == sorted(mapped)  # never lower for a higher score
    assert calibrator(0.0) == mapped[0] and calibrator(1.0) == mapped[-1]
    assert abs(sum(mapped) / len(mapped) - sum(labels) / len(labels)) < 1e-9  # pools keep the mean
    restored = IsotonicCalibrator.from_json(calibrator.to_json())
    assert [restored(score) for score in scores] == [round(value, 4) for value in mapped]


def test_calibration_error_and_brier_on_known_cases():
    assert expected_calibration_error([0.8] * 10, [True] * 8 + [False] * 2) == 0.0
    assert expected_calibration_error([0.9] * 10, [True] * 5 + [False] * 5) == 0.4
    assert brier_score([1.0, 0.0], [True, False]) == 0.0 and brier_score([0.5], [True]) == 0.25
    table = reliability([0.05, 0.15, 0.95], [False, True, True], bins=10)
    assert [row["bin"] for row in table] == ["0.0-0.1", "0.1-0.2", "0.9-1.0"]


def test_isotonic_recalibrates_an_underconfident_score():
    rng = random.Random(5)
    scores = [rng.random() * 0.5 for _ in range(2000)]
    labels = [rng.random() < min(1.0, score * 1.8) for score in scores]  # truth is ~1.8x the stated score
    calibrator = IsotonicCalibrator.fit(scores[:1000], labels[:1000])
    raw = expected_calibration_error(scores[1000:], labels[1000:])
    fixed = expected_calibration_error([calibrator(score) for score in scores[1000:]], labels[1000:])
    assert raw > 0.15 and fixed < raw / 3


NOW = datetime(2026, 9, 1, tzinfo=timezone.utc)


def _dated(dates: int = 12, files: int = 60):
    rng = random.Random(9)
    out = []
    for index in range(dates):
        at = NOW - timedelta(days=60 * (dates - index))
        rows = []
        for _ in range(files):
            x = {name: rng.random() for name in FEATURES}
            rows.append(TrainingRow("f.py", at, x, rng.random() < 0.15 + 0.6 * x["pastFixes"]))
        out.append((at, rows))
    return out


def test_backtest_reports_stated_and_observed_per_band_from_past_models_only():
    record, predictions = backtest(_dated(), horizon_days=90)
    assert predictions > 0 and record
    assert sum(band["n"] for band in record) == predictions
    for band in record:
        assert band["low"] <= band["stated"] < band["high"]
        assert abs(band["stated"] - band["observed"]) < 0.2  # the synthetic signal is learnable
    assert backtest(_dated(dates=2), horizon_days=90) == ([], 0)  # nothing earlier to learn from


def test_assessment_quotes_the_repository_track_record():
    rows = [row for _, rows in _dated() for row in rows]
    model = fit(rows)
    record, predictions = backtest(_dated(), horizon_days=90)
    learning = RiskLearning(model, len(rows), sum(row.label for row in rows), 0, 90,
                            track_record=record, backtest_predictions=predictions)
    result = RiskResult("src/pay.py", 50, "medium", 3, 120, 0, (), past_fixes=2)
    assessed = learning.assess(result)
    assert assessed["trackRecord"].startswith("When AEIP said") and "files broke" not in assessed["trackRecord"][:10]
    assert learning.status()["backtestPredictions"] == predictions


def test_incident_track_record_counts_engineers_verdicts(tmp_path):
    service = IntelligenceDemoService(cache_dir=tmp_path)
    found = service.incidents()
    assert found["trackRecord"] == {"reviewed": 0, "top1": 0, "top3": 0, "byEvidence": {}}
    first, second = found["incidents"][0]["id"], found["incidents"][1]["id"]
    top = service.incident(first)["candidates"][0]
    service.record_feedback(None, first, top["ref"], "confirmed")
    candidates = service.incident(second)["candidates"]
    service.record_feedback(None, second, candidates[0]["ref"], "rejected")
    record = service.incidents()["trackRecord"]
    assert record["reviewed"] == 2 and record["top1"] == 1
    assert sum(item["reviewed"] for item in record["byEvidence"].values()) == 2
    if len(candidates) > 1:
        service.record_feedback(None, second, candidates[1]["ref"], "confirmed")
        assert service.incidents()["trackRecord"]["top3"] == 2
