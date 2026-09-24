import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.web_api import IntelligenceDemoService


def service():
    return IntelligenceDemoService(cache_dir=None)


def test_overview_exposes_calculated_intelligence_data():
    overview = service().overview()
    assert overview["repository"] == "acme/payments-api"
    assert overview["indexedDocuments"] == 3
    assert overview["metrics"][2]["value"] == "50.0"
    assert overview["riskItems"][0]["file"] == "src/payment_service.py"


def test_assistant_returns_answer_and_repository_evidence_without_groq():
    result = service().ask("What should we test before payment deployment?")
    assert result["mode"] == "offline"
    assert result["evidence"]
    assert "src/payment_service.py" in result["answer"]


def test_unknown_repository_is_reported_not_crashed():
    try:
        service().overview("someone/unknown")
    except KeyError as exc:
        assert "has not been analyzed" in str(exc)
    else:
        raise AssertionError("expected KeyError")
