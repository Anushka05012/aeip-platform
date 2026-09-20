import re


_REDACTION_PATTERNS = (
    (
        re.compile(r"\b(?:ghp|gho|ghs|github_pat)_[A-Za-z0-9_]+\b"),
        "[REDACTED_GITHUB_TOKEN]",
    ),
    (
        re.compile(r"(?i)(\bauthorization\s*:\s*bearer\s+)[^\s]+"),
        r"\1[REDACTED_TOKEN]",
    ),
    (
        re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
        "[REDACTED_AWS_KEY]",
    ),
    (
        re.compile(
            r"(?i)(\b(?:password|passwd|secret|token|api[_-]?key)\b\s*[:=]\s*)(\"[^\"]*\"|'[^']*'|[^\s,;]+)"
        ),
        r"\1[REDACTED_SECRET]",
    ),
)


def redact_secrets(text: str) -> str:
    redacted = text
    for pattern, replacement in _REDACTION_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted
