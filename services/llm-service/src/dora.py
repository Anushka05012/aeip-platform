"""DORA calculations from a snapshot; no UI or database coupling."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from statistics import median
from typing import Sequence

from .domain import Deployment, RepositorySnapshot


@dataclass(frozen=True)
class DoraMetrics:
    deployment_frequency_per_week: float
    lead_time_hours: float | None
    change_failure_rate_percent: float
    time_to_restore_hours: float | None = None  # median, first failure to the next success of that workflow
    restored_incidents: int = 0
    open_incidents: int = 0  # failures with no later success yet


def restore_times(deployments: Sequence[Deployment]) -> tuple[list[float], int]:
    """Hours from each failure streak's first failure to the next successful run of the same workflow.

    Runs are grouped by workflow name so a passing lint job does not "restore" a failing deploy job.
    Returns the restore durations and the number of streaks that have not been restored yet.
    """
    by_workflow: dict[str, list[Deployment]] = {}
    for item in deployments:
        by_workflow.setdefault(item.name, []).append(item)
    durations: list[float] = []
    open_incidents = 0
    for runs in by_workflow.values():
        failed_since: datetime | None = None
        for run in sorted(runs, key=lambda item: item.deployed_at):
            if run.status == "failure" and failed_since is None:
                failed_since = run.deployed_at
            elif run.status == "success" and failed_since is not None:
                durations.append((run.deployed_at - failed_since).total_seconds() / 3600)
                failed_since = None
        if failed_since is not None:
            open_incidents += 1
    return durations, open_incidents


def calculate_dora(snapshot: RepositorySnapshot, start: datetime, end: datetime) -> DoraMetrics:
    deployments = [item for item in snapshot.deployments if start <= item.deployed_at <= end]
    successful = [item for item in deployments if item.status == "success"]
    failures = [item for item in deployments if item.status == "failure"]
    commits = {item.sha: item for item in snapshot.commits}
    lead_times = [
        (item.deployed_at - commits[item.commit_sha].authored_at).total_seconds() / 3600
        for item in successful if item.commit_sha in commits
    ]
    durations, open_incidents = restore_times(deployments)
    days = max((end - start).total_seconds() / 86400, 1)
    return DoraMetrics(
        deployment_frequency_per_week=round(len(deployments) / days * 7, 2),
        lead_time_hours=round(sum(lead_times) / len(lead_times), 2) if lead_times else None,
        change_failure_rate_percent=round(len(failures) / len(deployments) * 100, 2) if deployments else 0.0,
        time_to_restore_hours=round(median(durations), 2) if durations else None,
        restored_incidents=len(durations),
        open_incidents=open_incidents,
    )
