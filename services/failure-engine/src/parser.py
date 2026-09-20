from dataclasses import dataclass

from .redactor import redact_secrets


@dataclass(frozen=True)
class ParsedLog:
    raw_log: str
    lines: list[str]
    error_lines: list[str]
    evidence: list[str]


def parse_log(raw_log: str) -> ParsedLog:
    sanitized_log = redact_secrets(raw_log)
    lines = [line.strip() for line in sanitized_log.splitlines() if line.strip()]
    error_lines = [
        line
        for line in lines
        if any(marker in line.lower() for marker in ("error", "err!", "fail", "exception", "fatal"))
    ]

    return ParsedLog(
        raw_log=sanitized_log,
        lines=lines,
        error_lines=error_lines,
        evidence=error_lines[:5],
    )
