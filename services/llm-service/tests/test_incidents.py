import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.domain import Commit, RepositorySnapshot
from src.events import make_event
from src.incidents import _paths_match, ai_narrative, build_timeline, detect_incidents
from src.web_api import IntelligenceDemoService

T0 = datetime(2026, 9, 20, 12, tzinfo=timezone.utc)


def at(minutes):
    return (T0 + timedelta(minutes=minutes)).isoformat()


def commit(sha, minutes, files, message=""):
    return Commit(sha, T0 + timedelta(minutes=minutes), tuple(files), 20, 5, 1, message)


def error(minutes, title="KeyError: 'total'", files=("src/cart.py",), service="shop", source="app"):
    return make_event({"source": source, "kind": "error", "time": at(minutes), "title": title, "severity": "error",
                       "service": service, "files": list(files)})


def deploy(minutes, sha, service="shop"):
    return make_event({"source": "deploy", "kind": "deploy.succeeded", "time": at(minutes), "title": f"deploy {sha}",
                       "service": service, "environment": "production", "commit": sha})


def snapshot(commits):
    return RepositorySnapshot("acme/shop", tuple(commits), (), ())


def test_paths_from_stack_traces_match_repository_paths():
    assert _paths_match("/app/src/cart.py", "src/cart.py") and _paths_match("src/cart.py", "cart.py")
    assert not _paths_match("src/cart.py", "src/carts.py")


def test_errors_are_grouped_into_incidents_by_quiet_gaps():
    events = [error(0), error(10), error(30), error(200), error(210)]
    incidents = detect_incidents(snapshot([]), events)
    assert [item.summary()["errorCount"] for item in incidents] == [2, 3]  # newest first


def test_the_deploy_that_shipped_the_failing_file_is_the_likely_cause():
    commits = [commit("c1", -300, ["src/search.py"]), commit("c2", -60, ["src/cart.py"], "Refactor cart totals"),
               commit("c3", -50, ["docs/readme.md"])]
    events = [deploy(-240, "c1"), deploy(-10, "c3"), make_event({
        "source": "deploy", "kind": "deploy.succeeded", "time": at(-120), "title": "other service", "service": "billing",
        "commit": "c1"}), error(0), error(5), error(12)]
    incident = detect_incidents(snapshot(commits), events)[0]
    top = incident.candidates[0]
    assert top.title.startswith("Deploy of c3") and top.score >= 0.5
    assert {item.sha for item in top.commits} == {"c2", "c3"}  # everything since the previous shop deploy
    assert top.implicated == ["src/cart.py"]
    assert any("stack traces of 3 errors" in line for line in top.evidence)


def test_rollback_that_stops_the_errors_is_recovery_evidence():
    commits = [commit("good", -500, ["src/cart.py"]), commit("bad", -30, ["src/cart.py"])]
    events = [deploy(-400, "good"), deploy(-5, "bad"), error(0), error(10), deploy(20, "good"), error(25)]
    incident = detect_incidents(snapshot(commits), events)[0]
    top = incident.candidates[0]
    assert top.scores.get("recovery") == 1.0 and top.rolled_back_at is not None
    assert not any("Roll back" in step for step in incident.next_steps)  # already rolled back


def test_migration_before_database_errors_is_suspected():
    events = [make_event({"source": "database", "kind": "migration", "time": at(-5), "title": "Applying migration 0009",
                          "service": "db"}),
              error(0, "deadlock detected", (), "db", "database"), error(8, "deadlock detected", (), "db", "database"),
              make_event({"source": "database", "kind": "migration", "time": at(15), "title": "Migration 0009 finished",
                          "service": "db"})]
    incident = detect_incidents(snapshot([]), events)[0]
    assert incident.candidates[0].kind == "migration" and incident.candidates[0].scores["type"] == 1.0
    assert "CONCURRENTLY" in incident.next_steps[0]


def test_without_deploy_events_commits_are_the_suspects():
    commits = [commit("c1", -20, ["src/cart.py"])]
    incident = detect_incidents(snapshot(commits), [error(0), error(3)])[0]
    assert incident.candidates[0].kind == "commit"


def test_no_change_before_the_incident_points_outside_the_codebase():
    incident = detect_incidents(snapshot([]), [error(0, files=())])[0]
    assert incident.candidates == [] and "outside the codebase" in incident.narrative


def test_alert_resolution_ends_the_incident_and_preview_errors_are_ignored():
    events = [make_event({"source": "alert", "kind": "alert.firing", "time": at(0), "title": "Error rate high",
                          "severity": "critical", "fingerprint": "rate"}),
              make_event({"source": "alert", "kind": "alert.resolved", "time": at(30), "title": "Error rate high",
                          "fingerprint": "rate"}),
              make_event({"source": "app", "kind": "error", "time": at(500), "title": "preview only", "severity": "error",
                          "environment": "preview"})]
    incidents = detect_incidents(snapshot([]), events)
    assert len(incidents) == 1
    assert incidents[0].status == "resolved" and incidents[0].summary()["durationMinutes"] == 30
    assert incidents[0].title == "Error rate high"


def test_unresolved_alert_is_ongoing():
    events = [make_event({"source": "alert", "kind": "alert.firing", "time": at(0), "title": "API down",
                          "severity": "critical", "fingerprint": "down"})]
    assert detect_incidents(snapshot([]), events)[0].status == "ongoing"


def test_timeline_merges_commits_ci_and_events_in_time_order():
    commits = [commit("c1", -10, ["src/a.py"], "Add a")]
    items = build_timeline(snapshot(commits), [error(0), deploy(-5, "c1")])
    assert [item.source for item in items] == ["vcs", "deploy", "app"]


class FakeChat:
    def chat(self, messages, **kwargs):
        assert "<untrusted" in messages[1]["content"]
        return "The deploy of a6 caused gateway timeouts."


def test_ai_narrative_uses_the_evidence_as_untrusted_data():
    service = IntelligenceDemoService(cache_dir=None)
    entry, found = service._incidents(None)
    assert ai_narrative(found[0], FakeChat()).startswith("The deploy of a6")


def test_demo_incidents_find_the_deploy_and_the_migration():
    service = IntelligenceDemoService(cache_dir=None)
    listing = service.incidents()["incidents"]
    assert [item["rootCause"]["kind"] for item in listing] == ["deploy", "migration"]
    assert all(item["rootCause"]["confidence"] == "likely" and item["status"] == "resolved" for item in listing)
    detail = service.incident(listing[0]["id"])
    assert detail["rootCause"]["title"].startswith("Deploy of a6")
    assert {"vcs", "deploy", "app", "database", "alert"} <= {item["source"] for item in detail["timeline"]}
    assert service.overview()["incidents"][0]["id"] == listing[0]["id"]
