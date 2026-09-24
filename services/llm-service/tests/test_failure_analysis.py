import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.failure_analysis import classify, extract_error_lines, files_mentioned, redact_secrets
from src.web_api import IntelligenceDemoService


def service():
    return IntelligenceDemoService(cache_dir=None)


def test_secrets_are_redacted_before_analysis():
    text = ("token=ghp_abcdefghijklmnopqrstuvwxyz0123 GROQ_API_KEY=gsk_live_0123456789abcdef "
            "Authorization: Bearer abcdefghijklmnopqrstuvwxyz https://user:hunter22@example.com")
    cleaned = redact_secrets(text)
    assert "ghp_" not in cleaned and "gsk_live" not in cleaned and "hunter22" not in cleaned
    assert "abcdefghijklmnopqrstuvwxyz" not in cleaned


def test_error_lines_strip_timestamps_and_keep_errors():
    log = "2026-09-12T17:58:03.5Z collecting\n2026-09-12T17:58:03.5Z E   AssertionError: assert 2 == 1\n2026-09-12T17:58:04Z done"
    lines = extract_error_lines(log, context=0)
    assert lines == ["E   AssertionError: assert 2 == 1"]


def test_classification_and_file_matching():
    assert classify("dial tcp: i/o timeout") == "infrastructure / flaky"
    assert classify("FAILED tests/test_x.py::test_a - AssertionError") == "test failure"
    assert classify("src/app.ts(3,1): error TS2322: Type 'x' is not assignable") == "lint / type check"
    assert files_mentioned("at src/payment_service.py:4", ["src/payment_service.py", "src/routes.py"]) == ["src/payment_service.py"]


def test_test_failure_in_changed_file_is_related_to_the_change():
    result = service().explain_failure("d2")
    assert result["verdict"] == "related"
    assert result["category"] == "test failure"
    assert result["confidence"] >= 0.8 and not result["needs_review"]
    assert any(item["path"] == "src/payment_service.py" and item["mentionedInLog"] for item in result["changed_files"])
    assert "gsk_live" not in json.dumps(result)  # the secret in the fixture log never leaves the service


def test_network_timeout_is_unrelated_to_the_change():
    result = service().explain_failure("d4")
    assert result["verdict"] == "unrelated"
    assert result["category"] == "infrastructure / flaky"


class FakeChat:
    def __init__(self, reply):
        self.reply = reply

    def chat(self, messages, **kwargs):
        assert "<untrusted" in messages[1]["content"]  # logs/code are passed as untrusted data
        return self.reply


def _explain_with(reply):
    demo = service()
    entry = demo._get(None)
    deployment = next(item for item in entry.snapshot.deployments if item.id == "d2")
    commit = next(item for item in entry.snapshot.commits if item.sha == deployment.commit_sha)
    return demo.failure_analyzer.explain(deployment, commit, [], entry.risks, entry.pipeline.retriever, FakeChat(reply))


def test_llm_agreement_keeps_high_confidence():
    result = _explain_with('{"verdict": "related", "category": "test failure", "confidence": 0.9, '
                           '"explanation": "Duplicate charge.", "next_steps": ["Add idempotency key"]}')
    assert result.mode == "groq" and result.verdict == "related" and not result.needs_review
    assert result.next_steps == ["Add idempotency key"]


def test_llm_disagreement_is_flagged_for_human_review():
    result = _explain_with('{"verdict": "unrelated", "confidence": 0.9, "explanation": "Flaky.", "next_steps": []}')
    assert result.needs_review and result.confidence <= 0.55
    assert any("Rule-based correlation" in note for note in result.notes)


def test_unparseable_llm_reply_falls_back_to_rules():
    result = _explain_with("I think it is probably the code.")
    assert result.mode == "offline" and result.verdict == "related"
