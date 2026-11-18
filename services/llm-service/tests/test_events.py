import json
import os
import sys
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.events import EventStore, fingerprint, from_alertmanager, from_github_deployment, from_render, from_sentry, \
    from_vercel, make_event, parse_log_text
from src.web_api import IntelligenceDemoService, IntelligenceRequestHandler


def test_generic_event_is_validated_redacted_and_gets_files():
    event = make_event({"source": "app", "time": "2026-09-15T14:44:00Z", "title": "KeyError in src/cart.py",
                        "message": "token=ghp_abcdefghijklmnopqrstuvwxyz0123 leaked", "severity": "ERROR"})
    assert event.severity == "error" and event.files == ("src/cart.py",)
    assert "ghp_" not in event.message and event.fingerprint
    try:
        make_event({"source": "nope", "time": "2026-09-15T14:44:00Z"})
    except ValueError as exc:
        assert "Unknown event source" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_fingerprint_groups_repeats_of_one_error():
    assert fingerprint("Timeout after 3000 ms (order 1044)") == fingerprint("Timeout after 5000 ms (order 2091)")
    assert fingerprint("Timeout after 3000 ms") != fingerprint("KeyError: 'user'")


def test_python_traceback_lines_attach_to_their_error():
    text = ("2026-09-15T14:44:08Z ERROR GatewayTimeoutError: charge timed out\n"
            "Traceback (most recent call last):\n"
            '  File "src/payment_service.py", line 4, in process_payment\n'
            "2026-09-15T14:45:00Z INFO healthy\n")
    events = parse_log_text(text, "app", "payments-api")
    assert len(events) == 1  # INFO is below the default warning floor
    assert events[0].files == ("src/payment_service.py",) and events[0].title.startswith("GatewayTimeoutError")


def test_json_lines_and_database_patterns():
    text = "\n".join([
        json.dumps({"time": "2026-09-15T10:00:00Z", "level": "error", "msg": "db write failed", "stack": "at save (src/repo.ts:10)"}),
        "2026-09-15 10:01:00 UTC ERROR:  deadlock detected",
        "2026-09-15 10:02:00 UTC LOG:  duration: 4200.1 ms  statement: SELECT 1",
        "2026-09-15 10:03:00 UTC LOG:  Applying migration 0007_add_index",
    ])
    app = parse_log_text(text.splitlines()[0], "app")
    assert app[0].files == ("src/repo.ts",)
    kinds = [event.kind for event in parse_log_text("\n".join(text.splitlines()[1:]), "database")]
    assert kinds == ["deadlock", "slow_query", "migration"]


def test_identical_lines_are_separate_occurrences_but_reuploads_dedupe():
    text = "2026-09-15T10:00:00Z ERROR boom\n2026-09-15T10:00:00Z ERROR boom\n"
    store = EventStore()
    assert store.add("o/r", parse_log_text(text, "app")) == 2
    assert store.add("o/r", parse_log_text(text, "app")) == 0


def test_vercel_render_and_github_deploy_webhooks():
    vercel = from_vercel({"type": "deployment.error", "createdAt": 1789000000000, "payload": {
        "name": "shop", "target": "production",
        "deployment": {"id": "dpl_1", "url": "shop.vercel.app", "meta": {"githubCommitSha": "abc1234"}}}})[0]
    assert (vercel.kind, vercel.commit, vercel.environment, vercel.severity) == ("deploy.failed", "abc1234", "production", "error")
    render = from_render({"type": "deploy_ended", "timestamp": "2026-09-15T10:00:00Z",
                          "data": {"id": "evt1", "serviceName": "api", "status": "succeeded"}})[0]
    assert render.kind == "deploy.succeeded" and render.service == "api"
    github = from_github_deployment({"deployment_status": {"id": 5, "state": "failure", "created_at": "2026-09-15T10:00:00Z",
                                                           "environment": "production"},
                                     "deployment": {"sha": "def5678"}, "repository": {"name": "shop"}})[0]
    assert github.kind == "deploy.failed" and github.commit == "def5678"
    assert from_vercel({"type": "project.created"}) == []


def test_sentry_stack_frames_become_files():
    event = from_sentry({"action": "created", "data": {"event": {
        "event_id": "e1", "title": "ZeroDivisionError: division by zero", "level": "error",
        "timestamp": "2026-09-15T10:00:00Z", "project": "shop", "release": "abc1234",
        "exception": {"values": [{"stacktrace": {"frames": [
            {"filename": "lib/vendor.py", "in_app": False}, {"filename": "src/cart.py", "lineno": 9, "function": "total"}]}}]}}}})[0]
    assert event.files == ("src/cart.py",) and event.commit == "abc1234" and "total" in event.message


def test_alertmanager_firing_and_resolved():
    events = from_alertmanager({"alerts": [
        {"status": "firing", "labels": {"alertname": "HighErrorRate", "severity": "critical", "service": "api"},
         "annotations": {"summary": "Error rate above 5%"}, "startsAt": "2026-09-15T10:00:00Z", "fingerprint": "f1"},
        {"status": "resolved", "labels": {"alertname": "HighErrorRate"}, "annotations": {},
         "startsAt": "2026-09-15T10:00:00Z", "endsAt": "2026-09-15T10:30:00Z", "fingerprint": "f1"}]})
    assert [event.kind for event in events] == ["alert.firing", "alert.resolved"]
    assert events[0].severity == "critical" and events[1].time.minute == 30


def test_event_store_persists_and_reloads(tmp_path):
    store = EventStore(tmp_path)
    store.add("Octo/App", [make_event({"source": "deploy", "kind": "deploy.succeeded", "time": "2026-09-15T10:00:00Z"})])
    assert [event.kind for event in EventStore(tmp_path).list("octo/app")] == ["deploy.succeeded"]


def test_demo_repository_ships_with_cross_tool_events():
    events = IntelligenceDemoService(cache_dir=None).list_events()
    assert set(events["bySource"]) == {"deploy", "database", "alert", "app"}


def _serve(service):
    handler = type("Handler", (IntelligenceRequestHandler,), {"service": service, "log_message": lambda *a: None})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


def _post(url, body, headers=None, content_type="application/json"):
    data = body if isinstance(body, bytes) else json.dumps(body).encode()
    request = urllib.request.Request(url, data=data, method="POST", headers={"Content-Type": content_type, **(headers or {})})
    try:
        with urllib.request.urlopen(request) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def test_http_ingest_requires_the_key_when_configured(monkeypatch):
    monkeypatch.setenv("AEIP_INGEST_KEY", "s3cret")
    server, base = _serve(IntelligenceDemoService(cache_dir=None))
    try:
        event = {"source": "deploy", "kind": "deploy.failed", "time": "2026-09-15T10:00:00Z", "title": "deploy failed"}
        assert _post(f"{base}/api/events?repository=octo/app", event)[0] == 401
        status, body = _post(f"{base}/api/events?repository=octo/app", {"events": [event]}, {"X-AEIP-Key": "s3cret"})
        assert status == 200 and body["added"] == 1
        status, body = _post(f"{base}/api/events/logs?repository=octo/app&source=app&key=s3cret",
                             b"2026-09-15T10:01:00Z ERROR boom in src/a.py\n", content_type="text/plain")
        assert status == 200 and body["added"] == 1
        status, body = _post(f"{base}/api/events/alertmanager?repository=octo/app", {"alerts": []},
                             {"Authorization": "Bearer s3cret"})
        assert status == 200 and body["received"] == 0
        with urllib.request.urlopen(f"{base}/api/events?repository=octo/app") as response:
            assert json.loads(response.read())["total"] == 2
    finally:
        server.shutdown()
