import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.web_api import IntelligenceDemoService


def test_overview_exposes_calculated_intelligence_data():
    overview = IntelligenceDemoService().overview()
    assert overview["repository"] == "acme/payments-api"
    assert overview["indexedDocuments"] == 3
    assert overview["metrics"][2]["value"] == "50.0"
    assert overview["riskItems"][0]["file"] == "src/payment_service.py"


def test_assistant_returns_answer_and_repository_evidence_without_groq():
    result = IntelligenceDemoService().ask("What should we test before payment deployment?")
    assert result["mode"] == "offline"
    assert result["evidence"]
    assert "Evidence:" in result["answer"]
