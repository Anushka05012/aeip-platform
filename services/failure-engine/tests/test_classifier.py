from pathlib import Path

import pytest

from src.classifier import FailureCategory, classify_log
from src.parser import parse_log


SAMPLES_DIR = Path(__file__).parents[1] / "samples"


@pytest.mark.parametrize(
    ("log", "expected_category"),
    [
        ("npm ERR! code ERESOLVE\nnpm ERR! unable to resolve dependency tree", FailureCategory.DEPENDENCY_ERROR),
        ("error TS2322: Type 'string' is not assignable to type 'number'", FailureCategory.TYPE_ERROR),
        ("FAIL src/auth.test.ts\nExpected: 200\nReceived: 500", FailureCategory.TEST_FAILURE),
        ("Docker build failed to solve: process exited with code 1", FailureCategory.DOCKER_ERROR),
        ("some unexpected output", FailureCategory.UNKNOWN),
    ],
)
def test_classifies_log(log: str, expected_category: FailureCategory) -> None:
    classification = classify_log(parse_log(log))

    assert classification.category == expected_category


def test_parser_extracts_evidence() -> None:
    parsed_log = parse_log("Starting build\nERROR: package missing\nFinished")

    assert parsed_log.lines == ["Starting build", "ERROR: package missing", "Finished"]
    assert parsed_log.evidence == ["ERROR: package missing"]


@pytest.mark.parametrize(
    ("sample_name", "expected_category"),
    [
        ("dependency_error.log", FailureCategory.DEPENDENCY_ERROR),
        ("test_failure.log", FailureCategory.TEST_FAILURE),
        ("compilation_error.log", FailureCategory.COMPILATION_ERROR),
        ("type_error.log", FailureCategory.TYPE_ERROR),
        ("docker_error.log", FailureCategory.DOCKER_ERROR),
        ("environment_error.log", FailureCategory.ENVIRONMENT_ERROR),
        ("lint_error.log", FailureCategory.LINT_ERROR),
    ],
)
def test_classifies_sample_log(sample_name: str, expected_category: FailureCategory) -> None:
    log = (SAMPLES_DIR / sample_name).read_text(encoding="utf-8")

    classification = classify_log(parse_log(log))

    assert classification.category == expected_category
