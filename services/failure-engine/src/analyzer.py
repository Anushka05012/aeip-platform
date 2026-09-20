from .classifier import Classification
from .parser import ParsedLog


def analyze_failure(
    parsed_log: ParsedLog,
    classification: Classification,
    metadata: dict[str, str | None] | None = None,
) -> dict[str, object]:
    category = classification.category.value
    result: dict[str, object] = {
        "category": category,
        "severity": classification.severity,
        "rootCause": _root_cause(category),
        "evidence": parsed_log.evidence or classification.matched_patterns,
        "suggestedFix": _suggested_fix(category),
        "confidence": classification.confidence,
    }
    supplied_metadata = {
        key: value for key, value in (metadata or {}).items() if value is not None
    }
    if supplied_metadata:
        result["metadata"] = supplied_metadata
    return result


def _root_cause(category: str) -> str:
    causes = {
        "DEPENDENCY_ERROR": "Incompatible or unresolved dependency versions caused the build to fail.",
        "TYPE_ERROR": "The code contains a type mismatch that violates the expected type contract.",
        "TEST_FAILURE": "One or more automated tests produced results different from the expected behavior.",
        "LINT_ERROR": "The code violated one or more configured linting rules.",
        "DOCKER_ERROR": "The Docker image build or Docker command failed.",
        "ENVIRONMENT_ERROR": "The build could not access a required command, file, permission, or service.",
        "COMPILATION_ERROR": "The source code could not be compiled successfully.",
        "UNKNOWN": "The log does not match a known failure pattern.",
    }
    return causes[category]


def _suggested_fix(category: str) -> str:
    fixes = {
        "DEPENDENCY_ERROR": "Review package versions and update the dependency constraints.",
        "TYPE_ERROR": "Check the reported values and align them with the declared types.",
        "TEST_FAILURE": "Inspect the failing test and compare the expected and received values.",
        "LINT_ERROR": "Run the configured linter locally and fix the reported violations.",
        "DOCKER_ERROR": "Inspect the Docker build step, Dockerfile, and command output.",
        "ENVIRONMENT_ERROR": "Verify the required commands, files, permissions, and services in CI.",
        "COMPILATION_ERROR": "Review the compiler errors and correct the reported source code issues.",
        "UNKNOWN": "Review the complete log and add a matching classification rule if needed.",
    }
    return fixes[category]
