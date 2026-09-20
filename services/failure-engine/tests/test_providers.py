from pathlib import Path

import pytest

from src.providers import SampleLogProvider


SAMPLES_DIR = Path(__file__).parents[1] / "samples"


def test_sample_provider_fetches_log() -> None:
    provider = SampleLogProvider(SAMPLES_DIR)

    log = provider.fetch_log("dependency_error.log")

    assert "ERESOLVE" in log


def test_sample_provider_rejects_unknown_run() -> None:
    provider = SampleLogProvider(SAMPLES_DIR)

    with pytest.raises(FileNotFoundError):
        provider.fetch_log("missing.log")
