from pathlib import Path
from typing import Protocol


class LogProvider(Protocol):
    """Common interface for services that retrieve CI/CD logs."""

    def fetch_log(self, run_id: str) -> str:
        """Return the raw log for a CI/CD run."""
        ...


class SampleLogProvider:
    """Local provider used until a GitHub or Bitbucket adapter is added."""

    def __init__(self, samples_dir: Path) -> None:
        self.samples_dir = samples_dir

    def fetch_log(self, run_id: str) -> str:
        sample_path = self.samples_dir / run_id
        if not sample_path.is_file():
            raise FileNotFoundError(f"Sample log not found: {run_id}")
        return sample_path.read_text(encoding="utf-8")
