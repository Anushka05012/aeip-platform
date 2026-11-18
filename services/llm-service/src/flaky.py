"""Flaky CI detection from run history alone (no extra GitHub calls, no logs).

A workflow is flaky when it gives different results for the same code. Two signals prove that:

- **Same commit, mixed results**: the workflow both failed and passed on one commit.
- **Passed on re-run**: GitHub reports ``run_attempt > 1`` for a successful run, so an earlier
  attempt of that same run (same commit, same workflow) did not pass.

A high pass/fail flip rate is also reported, but only as a weaker hint: code changes between runs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

from .domain import Deployment


@dataclass
class FlakyWorkflow:
    workflow: str
    runs: int
    failures: int
    flips: int  # pass->fail or fail->pass transitions between consecutive runs
    events: list[dict[str, Any]] = field(default_factory=list)
    flaky_failure_ids: list[str] = field(default_factory=list)  # failed runs proven non-deterministic

    @property
    def flip_rate(self) -> float:
        return round(self.flips / (self.runs - 1), 2) if self.runs > 1 else 0.0

    @property
    def level(self) -> str:
        if self.events:
            return "flaky"
        # Without proof, an unstable history (alternating results) is only a suspicion.
        return "suspected" if self.runs >= 4 and self.failures >= 2 and self.flip_rate >= 0.5 else "stable"

    def to_json(self) -> dict[str, Any]:
        return {"workflow": self.workflow, "runs": self.runs, "failures": self.failures, "flips": self.flips,
                "flipRate": self.flip_rate, "level": self.level, "events": self.events}


def detect_flaky(deployments: Sequence[Deployment]) -> list[FlakyWorkflow]:
    """Per-workflow flakiness, flaky first, then suspected, then the rest."""
    by_workflow: dict[str, list[Deployment]] = {}
    for run in deployments:
        if run.status in ("success", "failure"):
            by_workflow.setdefault(run.name or "workflow", []).append(run)

    results = []
    for name, runs in by_workflow.items():
        runs = sorted(runs, key=lambda item: item.deployed_at)
        report = FlakyWorkflow(
            workflow=name, runs=len(runs), failures=sum(1 for item in runs if item.status == "failure"),
            flips=sum(1 for before, after in zip(runs, runs[1:]) if before.status != after.status))

        by_commit: dict[str, list[Deployment]] = {}
        for run in runs:
            by_commit.setdefault(run.commit_sha, []).append(run)
        for sha, same in by_commit.items():
            failed = [item for item in same if item.status == "failure"]
            passed = [item for item in same if item.status == "success"]
            if failed and passed:
                report.events.append({
                    "kind": "same commit, mixed results", "commit": sha,
                    "failedRuns": [item.id for item in failed], "passedRuns": [item.id for item in passed],
                    "detail": f"{len(failed)} failed and {len(passed)} passed run(s) on commit {sha[:7]}"})
                report.flaky_failure_ids.extend(item.id for item in failed)

        for run in runs:
            if run.status == "success" and run.run_attempt > 1:
                report.events.append({
                    "kind": "passed on re-run", "commit": run.commit_sha, "failedRuns": [], "passedRuns": [run.id],
                    "detail": f"run {run.id} passed on attempt {run.run_attempt} after an earlier attempt did not"})
        results.append(report)

    order = {"flaky": 0, "suspected": 1, "stable": 2}
    return sorted(results, key=lambda item: (order[item.level], -len(item.events), -item.failures, item.workflow))


def passing_runs_on_same_commit(failed: Deployment, deployments: Sequence[Deployment]) -> list[str]:
    """Ids of successful runs of the same workflow on the failed run's exact commit."""
    return [item.id for item in deployments
            if item.status == "success" and item.commit_sha == failed.commit_sha
            and (item.name or "workflow") == (failed.name or "workflow") and item.id != failed.id]
