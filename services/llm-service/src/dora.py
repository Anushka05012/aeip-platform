"""DORA calculations from a snapshot; no UI or database coupling."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .domain import RepositorySnapshot


@dataclass(frozen=True)
class DoraMetrics:
    deployment_frequency_per_week: float
    lead_time_hours: float | None
    change_failure_rate_percent: float


def calculate_dora(snapshot: RepositorySnapshot, start: datetime, end: datetime) -> DoraMetrics:
    deployments = [item for item in snapshot.deployments if start <= item.deployed_at <= end]
    successful = [item for item in deployments if item.status == "success"]
    failures = [item for item in deployments if item.status == "failure"]
    commits = {item.sha: item for item in snapshot.commits}
    lead_times = [
        (item.deployed_at - commits[item.commit_sha].authored_at).total_seconds() / 3600
        for item in successful if item.commit_sha in commits
    ]
    days = max((end - start).total_seconds() / 86400, 1)
    return DoraMetrics(
        deployment_frequency_per_week=round(len(deployments) / days * 7, 2),
        lead_time_hours=round(sum(lead_times) / len(lead_times), 2) if lead_times else None,
        change_failure_rate_percent=round(len(failures) / len(deployments) * 100, 2) if deployments else 0.0,
    )
