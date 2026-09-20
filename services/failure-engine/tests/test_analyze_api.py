from fastapi.testclient import TestClient

from src.main import app


client = TestClient(app)


def test_analyze_dependency_failure() -> None:
    response = client.post(
        "/analyze",
        json={"log": "npm ERR! code ERESOLVE\nnpm ERR! unable to resolve dependency tree"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "category": "DEPENDENCY_ERROR",
        "severity": "HIGH",
        "rootCause": "Incompatible or unresolved dependency versions caused the build to fail.",
        "evidence": [
            "npm ERR! code ERESOLVE",
            "npm ERR! unable to resolve dependency tree",
        ],
        "suggestedFix": "Review package versions and update the dependency constraints.",
        "confidence": 0.85,
    }


def test_analyze_rejects_empty_log() -> None:
    response = client.post("/analyze", json={"log": ""})

    assert response.status_code == 422


def test_analyze_includes_ci_metadata() -> None:
    response = client.post(
        "/analyze",
        json={
            "provider": "github",
            "repository": "owner/repository",
            "branch": "main",
            "commit": "abc123",
            "runId": "987",
            "log": "npm ERR! code ERESOLVE",
        },
    )

    assert response.status_code == 200
    assert response.json()["metadata"] == {
        "provider": "github",
        "repository": "owner/repository",
        "branch": "main",
        "commit": "abc123",
        "runId": "987",
    }
