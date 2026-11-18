"""SEC-01/02/03: only the dashboard (service token) may call the API, roles gate actions, actions are audited."""

import json
import os
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import src.web_api as web_api
from src.web_api import IntelligenceDemoService
from tests.test_events import _serve


def call(url, method="GET", body=None, headers=None):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, method=method,
                                     headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(request) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def dashboard(role, user="octocat"):
    return {"X-AEIP-Service-Token": "svc", "X-AEIP-User": user, "X-AEIP-Role": role}


def test_api_is_open_for_local_development_without_a_service_token(monkeypatch):
    monkeypatch.delenv("AEIP_SERVICE_TOKEN", raising=False)
    server, base = _serve(IntelligenceDemoService(cache_dir=None))
    try:
        assert call(f"{base}/api/incidents")[0] == 200
    finally:
        server.shutdown()


def test_service_token_and_roles_are_enforced(monkeypatch, tmp_path):
    monkeypatch.setenv("AEIP_SERVICE_TOKEN", "svc")
    monkeypatch.setattr(web_api, "CACHE_DIR", tmp_path)
    server, base = _serve(IntelligenceDemoService(cache_dir=None))
    try:
        assert call(f"{base}/health")[0] == 200  # health checks stay public
        assert call(f"{base}/api/incidents")[0] == 401  # browser or script without the token
        assert call(f"{base}/api/incidents", headers={**dashboard("viewer"), "X-AEIP-Service-Token": "wrong"})[0] == 401
        assert call(f"{base}/api/incidents", headers=dashboard("viewer"))[0] == 200
        assert call(f"{base}/api/incidents", headers=dashboard("intruder"))[0] == 403

        ask = {"question": "What should we test?"}
        assert call(f"{base}/api/assistant", "POST", ask, dashboard("viewer"))[0] == 403
        status, body = call(f"{base}/api/assistant", "POST", ask, dashboard("member"))
        assert status == 200 and body["answer"]
        incident_id = call(f"{base}/api/incidents", headers=dashboard("viewer"))[1]["incidents"][0]["id"]
        assert call(f"{base}/api/incidents?id={incident_id}&ai=1", headers=dashboard("viewer"))[0] == 403
        assert call(f"{base}/api/incidents?id={incident_id}", headers=dashboard("viewer"))[0] == 200
    finally:
        server.shutdown()

    records = [json.loads(line) for line in (tmp_path / "audit.jsonl").read_text().splitlines()]
    assert any(r["action"] == "assistant.ask" and r["allowed"] and r["user"] == "octocat" and r["role"] == "member"
               for r in records)
    assert any(r["action"] == "assistant.ask" and not r["allowed"] and r["role"] == "viewer" for r in records)
    assert any(r["action"] == "incident.ai-summary" and not r["allowed"] for r in records)
