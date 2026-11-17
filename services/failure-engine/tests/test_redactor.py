from src.parser import parse_log
from src.redactor import redact_secrets


def test_redacts_common_credentials() -> None:
    log = (
        "ERROR: token=abc123\n"
        "Authorization: Bearer bearer-value\n"
        "GITHUB_TOKEN=ghp_0123456789abcdef\n"
        "AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE"
    )

    redacted = redact_secrets(log)

    assert "abc123" not in redacted
    assert "bearer-value" not in redacted
    assert "ghp_0123456789abcdef" not in redacted
    assert "AKIAIOSFODNN7EXAMPLE" not in redacted
    assert "[REDACTED_SECRET]" in redacted
    assert "[REDACTED_TOKEN]" in redacted
    assert "[REDACTED_GITHUB_TOKEN]" in redacted
    assert "[REDACTED_AWS_KEY]" in redacted


def test_parser_only_exposes_sanitized_evidence() -> None:
    parsed_log = parse_log("ERROR: password=super-secret")

    assert parsed_log.evidence == ["ERROR: password=[REDACTED_SECRET]"]
    assert "super-secret" not in parsed_log.raw_log
