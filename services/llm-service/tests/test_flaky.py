import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.domain import Commit, Deployment
from src.failure_analysis import build_evidence, correlate
from src.flaky import detect_flaky
from src.seed_data import snapshot_from_json, snapshot_to_json
from src.web_api import IntelligenceDemoService


def run(run_id, hour, status, sha, name="Tests", attempt=1, log=""):
    return Deployment(run_id, datetime(2026, 9, 1, hour), sha, status, name=name, branch="main", event="push",
                      log=log, run_attempt=attempt)


def by_name(reports):
    return {item.workflow: item for item in reports}


def test_same_commit_failing_and_passing_is_flaky():
    report = by_name(detect_flaky([run("1", 1, "success", "aaa"), run("2", 2, "failure", "bbb"),
                                   run("3", 3, "success", "bbb")]))["Tests"]
    assert report.level == "flaky"
    assert report.flaky_failure_ids == ["2"]
    assert report.events[0]["kind"] == "same commit, mixed results"


def test_success_on_a_later_attempt_is_flaky():
    report = detect_flaky([run("1", 1, "success", "aaa", attempt=2)])[0]
    assert report.level == "flaky" and report.events[0]["kind"] == "passed on re-run"


def test_a_real_break_and_fix_is_not_flaky():
    # Failed on one commit, fixed by a different commit: the code changed, so nothing proves flakiness.
    reports = detect_flaky([run("1", 1, "success", "a"), run("2", 2, "failure", "b"), run("3", 3, "success", "c")])
    assert reports[0].level == "stable"


def test_alternating_results_on_different_commits_are_only_suspected():
    statuses = ["success", "failure", "success", "failure", "success"]
    report = detect_flaky([run(str(i), i, status, f"c{i}") for i, status in enumerate(statuses)])[0]
    assert report.level == "suspected" and report.flip_rate == 1.0


def test_workflows_are_judged_separately():
    reports = by_name(detect_flaky([run("1", 1, "failure", "x", name="Lint"), run("2", 2, "success", "x", name="Tests")]))
    assert reports["Lint"].level == "stable" and reports["Tests"].level == "stable"


def test_failure_that_passed_on_the_same_commit_is_unrelated_to_the_change():
    failed = run("2", 2, "failure", "bbb", log="FAILED tests/test_checkout.py::test_timeout - AssertionError")
    history = [failed, run("3", 3, "success", "bbb")]
    commit = Commit("bbb", datetime(2026, 9, 1), ("src/billing.py",), 5, 1)
    verdict, confidence, _, signals, _ = correlate(build_evidence(failed, commit, [], history=history), True)
    assert (verdict, confidence) == ("unrelated", 0.75)
    assert any("passed on this exact commit" in signal for signal in signals)


def test_flaky_failure_in_a_changed_file_stays_uncertain():
    failed = run("2", 2, "failure", "bbb", log="FAILED tests/test_api.py - error in src/api.py line 4")
    commit = Commit("bbb", datetime(2026, 9, 1), ("src/api.py",), 5, 1)
    verdict, _, _, _, _ = correlate(build_evidence(failed, commit, [], history=[failed, run("3", 3, "success", "bbb")]), True)
    assert verdict == "uncertain"


def test_run_attempt_survives_the_snapshot_cache():
    service = IntelligenceDemoService(cache_dir=None)
    data = snapshot_to_json(service._get(None).snapshot)
    data["deployments"][0]["run_attempt"] = 3
    assert snapshot_from_json(data).deployments[0].run_attempt == 3


def test_overview_reports_flaky_workflows_and_flags_runs():
    overview = IntelligenceDemoService(cache_dir=None).overview()
    assert overview["flaky"] == []  # the demo fixture has no flaky history
    assert all(item["flaky"] is False for item in overview["failures"])
