"""Change guard: before a change is merged, what could it break, who should look, and how to undo it.

For a pull request (or any list of changed files) it reports, from evidence AEIP already has:

* per file: the fixed risk score and, once the repository's model is active, the learned chance that the
  file needs a bug fix within 90 days, with the model's own track record. The proposed change is added to
  the history first, so the scores describe the repository *after* this change;
* files that were part of a change confirmed as an incident's cause, and current incidents that suspect them;
* code changed without its tests;
* suggested reviewers: the people who changed these files most in the last year;
* a rollback plan: the last good release, and what a revert does not undo (migrations, dependencies,
  configuration).

It never comments on, blocks or changes the pull request; it only reports. The learned probability is
about files needing a fix soon after changing (what the model was evaluated on, docs/EVALUATION.md
section 6), not a probability that this pull request causes an outage.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from pathlib import PurePosixPath
from typing import Any, Iterable, Sequence

from .domain import Commit, Deployment, RepositorySnapshot
from .events import as_utc
from .failure_analysis import is_config_file
from .github_source import is_dependency_file, is_source_code
from .learned_risk import IncidentLabel, RiskLearning
from .risk_engine import RiskEngine, RiskResult, covered_module, is_test_path, module_name

WINDOW_DAYS = 90  # same window as the learned model
REVIEWER_DAYS = 365
MAX_FILES = 200
_MIGRATION = re.compile(r"(^|/)(migrations?|migrate|alembic/versions|db/changes)/|\.sql$", re.IGNORECASE)
_DOCS = {".md", ".mdx", ".rst", ".txt"}
_DATA_DIR = re.compile(r"(^|/)(data|fixtures?|samples?|examples?|testdata)/", re.IGNORECASE)  # JSON/YAML there is data


@dataclass(frozen=True)
class ChangedFile:
    path: str
    status: str = "modified"  # added | modified | removed | renamed
    additions: int = 0
    deletions: int = 0


@dataclass
class Change:
    repository: str
    files: list[ChangedFile]
    title: str = ""
    number: int | None = None
    author: str = ""
    url: str = ""
    state: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


def file_kind(path: str) -> str:
    if is_test_path(path):
        return "test"
    if _MIGRATION.search(path):
        return "migration"
    if is_dependency_file(path):
        return "dependency"
    if path.startswith(".github/") or (is_config_file(path) and not _DATA_DIR.search(path)):
        return "config"
    if PurePosixPath(path).suffix.lower() in _DOCS or path.startswith("docs/"):
        return "docs"
    if is_source_code(path):
        return "code"
    return "other"


def _tests_changed_for(path: str, test_paths: Iterable[str]) -> bool:
    """A test in the change covers this file: test_pay.py / pay.test.ts, or the module name as a word in a test
    path (tests/data/cases/line_ranges_x.py covers ranges.py)."""
    names = {module_name(path).lower(), PurePosixPath(path).stem.lower()} - {""}
    for test in test_paths:
        words = set(re.split(r"[^a-z0-9]+", test.lower()))
        if covered_module(test) in names or names & words:
            return True
    return False


def _last_good_release(releases: Sequence[Deployment], now: datetime) -> dict[str, Any] | None:
    good = [item for item in releases if item.status == "success" and as_utc(item.deployed_at) <= as_utc(now)]
    if not good:
        return None
    last = max(good, key=lambda item: as_utc(item.deployed_at))
    return {"commit": last.commit_sha, "time": as_utc(last.deployed_at).isoformat(), "name": last.name or last.id}


def _reviewers(history: Sequence[Commit], paths: set[str], now: datetime, exclude: str) -> list[dict[str, Any]]:
    since = as_utc(now) - timedelta(days=REVIEWER_DAYS)
    commits: Counter[str] = Counter()
    known: dict[str, set[str]] = defaultdict(set)
    for commit in history:
        author = commit.author.strip()
        if not author or author.lower() == exclude.lower() or author.endswith("[bot]") or as_utc(commit.authored_at) < since:
            continue
        touched = paths & set(commit.files)
        if touched:
            commits[author] += 1
            known[author] |= touched
    return [{"name": name, "commits": count, "files": sorted(known[name])[:3]} for name, count in commits.most_common(3)]


def assess_change(change: Change, snapshot: RepositorySnapshot, now: datetime, history: Sequence[Commit] = (),
                  learning: RiskLearning | None = None, incident_labels: Sequence[IncidentLabel] = (),
                  incidents: Sequence[Any] = (), releases: Sequence[Deployment] = ()) -> dict[str, Any]:
    if not change.files:
        raise ValueError("The change has no files.")
    files = change.files[:MAX_FILES]
    kinds = {item.path: file_kind(item.path) for item in files}
    present = [item for item in files if item.status != "removed"]
    tests_in_change = [item.path for item in present if kinds[item.path] == "test"]
    # Fixture data may carry naive times; compare everything in UTC.
    commits = tuple(replace(commit, authored_at=as_utc(commit.authored_at)) for commit in (tuple(history) or snapshot.commits))

    # Score the repository as it would be with this change merged.
    scored_paths = tuple(item.path for item in present if kinds[item.path] not in ("test", "dependency", "docs"))
    proposed = Commit("proposed-change", as_utc(now), scored_paths,
                      sum(item.additions for item in present if kinds[item.path] == "code"),
                      sum(item.deletions for item in present if kinds[item.path] == "code"), 0, change.title,
                      tuple(item.path for item in present if kinds[item.path] == "dependency"), change.author)
    after = RepositorySnapshot(change.repository, tuple(commits) + (proposed,), (), snapshot.documents)
    results: dict[str, RiskResult] = {
        result.path: result for result in RiskEngine().score_files(after, as_utc(now) + timedelta(seconds=1), WINDOW_DAYS)}

    window_start = as_utc(now) - timedelta(days=WINDOW_DAYS)
    report_files = []
    for item in files:
        kind = kinds[item.path]
        confirmed = sorted((as_utc(label.at) for label in incident_labels if item.path in label.files), reverse=True)
        suspected = [{"id": incident.id, "title": incident.title, "start": as_utc(incident.start).isoformat()}
                     for incident in incidents if kind not in ("docs", "test")  # cannot break production
                     and any(item.path in candidate.files or any(item.path in commit.files for commit in candidate.commits)
                            for candidate in incident.candidates[:3])]
        entry: dict[str, Any] = {"path": item.path, "status": item.status, "kind": kind,
                                 "additions": item.additions, "deletions": item.deletions,
                                 "confirmedIncidents": len(confirmed),
                                 "lastConfirmedIncident": confirmed[0].isoformat() if confirmed else None,
                                 "suspectedIn": suspected[:3]}
        result = results.get(item.path)
        # Docs, tests and lockfiles get no risk score; the learned model was trained and evaluated on code only.
        if result and item.status != "removed" and kind not in ("docs", "test", "dependency"):
            past = sum(1 for at in confirmed if at >= window_start)
            entry |= {"score": result.score, "level": result.level, "reasons": list(result.reasons),
                      "pastFixes": result.past_fixes, "dependents": result.dependents,
                      "learned": learning.assess(result, past, as_given=True) if learning and kind == "code" else None}
            if kind == "code" and result.testable:
                entry["tests"] = ("changed" if _tests_changed_for(item.path, tests_in_change)
                                  else "other tests changed" if tests_in_change
                                  else "not changed" if result.has_tests else "none")
        report_files.append(entry)

    def concern(entry: dict[str, Any]) -> int:
        learned = (entry.get("learned") or {}).get("probability")
        if entry["confirmedIncidents"] or (learned is not None and learned >= 0.6) or entry.get("score", 0) >= 70:
            return 2
        if (learned is not None and learned >= 0.4) or entry.get("score", 0) >= 40 or entry["kind"] == "migration" \
                or entry.get("tests") == "none" or entry["suspectedIn"]:
            return 1
        return 0

    report_files.sort(key=lambda entry: (concern(entry), (entry.get("learned") or {}).get("probability", 0),
                                         entry.get("score", 0)), reverse=True)
    worst = max((concern(entry) for entry in report_files), default=0)
    level = ("high", "medium", "low")[2 - worst]

    findings: list[str] = []
    for entry in report_files:
        if entry["confirmedIncidents"]:
            findings.append(f"{entry['path']} was part of a change confirmed as an incident's cause "
                            f"({entry['confirmedIncidents']} time{'s' if entry['confirmedIncidents'] != 1 else ''}, "
                            f"last {entry['lastConfirmedIncident'][:10]}).")
        if entry["suspectedIn"]:
            findings.append(f"{entry['path']} is among the suspected causes of: "
                            + "; ".join(incident["title"] for incident in entry["suspectedIn"]) + ".")
    for entry in report_files:
        learned = entry.get("learned")
        if learned and learned["probability"] >= 0.4:
            findings.append(f"{entry['path']}: {round(learned['probability'] * 100)}% chance of needing a bug fix "
                            f"within 90 days ({', '.join(learned['drivers'][:2])}).")
        elif not learned and entry.get("score", 0) >= 40:
            findings.append(f"{entry['path']}: risk score {entry['score']}/100 ({'; '.join(entry['reasons'][:2])}).")
    untested = [entry["path"] for entry in report_files if entry.get("tests") in ("none", "not changed")]
    if untested:
        findings.append(f"{len(untested)} code file{'s' if len(untested) != 1 else ''} changed without "
                        f"{'its' if len(untested) == 1 else 'their'} tests: {', '.join(untested[:4])}"
                        f"{'…' if len(untested) > 4 else ''}.")
    migrations = [entry["path"] for entry in report_files if entry["kind"] == "migration"]
    dependencies = [entry["path"] for entry in report_files if entry["kind"] == "dependency"]
    configs = [entry["path"] for entry in report_files if entry["kind"] == "config"]
    if migrations:
        findings.append(f"Includes a database migration: {', '.join(migrations[:3])}.")

    # Reviewers who know the code that changed; changelogs and tests are touched by everyone.
    substantive = {item.path for item in present if kinds[item.path] not in ("docs", "test")}
    reviewers = _reviewers(commits, substantive or {item.path for item in present}, now, change.author)
    release = _last_good_release(releases, now)
    rollback = []
    if release:
        rollback.append(f"Redeploy the last good release: commit {release['commit'][:12]} "
                        f"({release['name']}, {release['time'][:16].replace('T', ' ')} UTC).")
    rollback.append("Revert the merge commit (git revert -m 1 <merge commit>) and let CI deploy the revert.")
    if migrations:
        rollback.append("Reverting the code does not undo the migration. Before merging, make sure a down migration "
                        "or a backup exists and that the previous release still works with the new schema.")
    if dependencies:
        rollback.append(f"Dependency files change ({', '.join(dependencies[:3])}): a revert restores the previous "
                        "lockfile; rebuild without the dependency cache.")
    if configs:
        rollback.append(f"Configuration changes ({', '.join(configs[:3])}): environment variables, flags or CI "
                        "settings applied outside the repository must be rolled back separately.")

    checks = []
    if untested:
        checks.append(f"Add or update tests for {', '.join(untested[:3])}.")
    if reviewers and worst:
        names = " or ".join(item["name"] for item in reviewers[:2])
        checks.append(f"Ask {names} to review: they changed these files most in the last year.")
    if migrations:
        checks.append("Run the migration against a copy of production data and time it.")
    if any(entry["confirmedIncidents"] or entry["suspectedIn"] for entry in report_files):
        checks.append("Read the linked incidents and check this change does not repeat them.")
    if worst == 2:
        checks.append("Deploy when someone can watch errors for the first hour, and keep the rollback plan at hand.")

    return {
        "repository": change.repository,
        "change": {"title": change.title, "number": change.number, "author": change.author, "url": change.url,
                   "state": change.state, "files": len(change.files), "shown": len(files),
                   "additions": sum(item.additions for item in change.files),
                   "deletions": sum(item.deletions for item in change.files)},
        "level": level,
        "findings": findings[:8],
        "files": report_files,
        "reviewers": reviewers,
        "rollback": rollback,
        "checks": checks,
        "model": {"active": bool(learning and learning.active),
                  "message": learning.status()["message"] if learning else "no learned model",
                  "meaning": "Learned chance that the file needs a bug fix within 90 days of changing; "
                             "not a probability that this change causes an outage."},
    }
