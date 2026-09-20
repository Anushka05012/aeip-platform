from dataclasses import dataclass
from enum import StrEnum

from .parser import ParsedLog


class FailureCategory(StrEnum):
    DEPENDENCY_ERROR = "DEPENDENCY_ERROR"
    COMPILATION_ERROR = "COMPILATION_ERROR"
    TEST_FAILURE = "TEST_FAILURE"
    LINT_ERROR = "LINT_ERROR"
    TYPE_ERROR = "TYPE_ERROR"
    DOCKER_ERROR = "DOCKER_ERROR"
    ENVIRONMENT_ERROR = "ENVIRONMENT_ERROR"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class Classification:
    category: FailureCategory
    severity: str
    confidence: float
    matched_patterns: list[str]


_RULES: tuple[tuple[FailureCategory, str, tuple[str, ...]], ...] = (
    (FailureCategory.DEPENDENCY_ERROR, "HIGH", ("eresolve", "unable to resolve dependency", "could not resolve dependencies")),
    (FailureCategory.TYPE_ERROR, "HIGH", ("ts2322", "ts2345", "typeerror", "is not assignable")),
    (FailureCategory.TEST_FAILURE, "HIGH", ("expected:", "received:", "assertionerror", "test failed", "fail ")),
    (FailureCategory.LINT_ERROR, "MEDIUM", ("eslint", "lint error", "flake8", "pylint")),
    (FailureCategory.DOCKER_ERROR, "HIGH", ("failed to solve", "docker build", "dockerfile")),
    (FailureCategory.ENVIRONMENT_ERROR, "HIGH", ("command not found", "permission denied", "no such file or directory", "connection refused")),
    (FailureCategory.COMPILATION_ERROR, "HIGH", ("compilation failed", "compile error", "build failed", "syntaxerror")),
)


def classify_log(parsed_log: ParsedLog) -> Classification:
    searchable_log = parsed_log.raw_log.lower()

    for category, severity, patterns in _RULES:
        matched_patterns = [pattern for pattern in patterns if pattern in searchable_log]
        if matched_patterns:
            return Classification(
                category=category,
                severity=severity,
                confidence=min(0.75 + 0.05 * len(matched_patterns), 0.95),
                matched_patterns=matched_patterns,
            )

    return Classification(
        category=FailureCategory.UNKNOWN,
        severity="LOW",
        confidence=0.25,
        matched_patterns=[],
    )
