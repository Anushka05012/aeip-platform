"""Metric correctness, plus regression guards so measured quality cannot silently drop."""

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.evaluation import (classification_report, evaluate_incidents, evaluate_verdicts, is_bug_fix, load_json,
                            recall_at_k, reciprocal_rank, roc_auc)

DATA = Path(__file__).resolve().parents[1] / "data" / "evaluation"


def test_ranking_metrics():
    ranked = ["a.py", "b.py", "c.py"]
    assert recall_at_k(ranked, {"b.py", "z.py"}, 2) == 0.5
    assert reciprocal_rank(ranked, {"c.py"}) == 1 / 3 and reciprocal_rank(ranked, {"z.py"}) == 0.0


def test_roc_auc():
    assert roc_auc([3, 2, 1], [True, False, False]) == 1.0
    assert roc_auc([1, 2, 3], [True, False, False]) == 0.0
    assert roc_auc([1, 1], [True, False]) == 0.5
    assert roc_auc([1, 2], [True, True]) is None


def test_classification_report():
    report = classification_report(["a", "a", "b"], ["a", "b", "b"], ["a", "b"])
    assert report["accuracy"] == round(2 / 3, 3) and report["perClass"]["a"]["recall"] == 0.5
    assert report["confusion"]["a"]["b"] == 1


def test_bug_fix_detection():
    assert is_bug_fix("Fix crash when option has no default") and is_bug_fix("Revert \"speed up parser\"")
    assert not is_bug_fix("fix typo in docs") and not is_bug_fix("Add progress bar colours")


def test_verdict_quality_does_not_regress():
    result = evaluate_verdicts(load_json(DATA / "failure_verdicts.json")["cases"])
    assert result["accuracy"] >= 0.95 and result["harmfulFlips"] == []


def test_incident_ranking_beats_the_most_recent_change_heuristic():
    overall = evaluate_incidents(count=80, seed=11)["overall"]
    assert overall["top1"] >= 0.75 and overall["top1"] > overall["baselineTop1"] + 0.1 and overall["top3"] >= 0.9
