"""Change guard for CI: report what a pull request could break, from the repository's own git history.

Runs on a checkout with full history and needs no AEIP server and no packages beyond Python 3.11:

    python services/llm-service/scripts/change_guard.py --repo . --base origin/main

It prints a Markdown report and, inside GitHub Actions, appends it to the job summary. It only reports:
the exit code is 0 whatever the risk, so it never blocks a merge (use --fail-on high to change that).
Incidents and engineers' verdicts live on the AEIP server, so this report covers history-based risk,
tests, reviewers and the rollback plan.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.change_guard import Change, ChangedFile, assess_change  # noqa: E402
from src.domain import RepositorySnapshot  # noqa: E402
from src.git_history import HISTORY_YEARS, read_history, to_commit, tree_documents  # noqa: E402
from src.github_source import is_source_code  # noqa: E402
from src.learned_risk import learn  # noqa: E402

LEVEL_ORDER = {"low": 0, "medium": 1, "high": 2}


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8",
                          errors="ignore", check=True).stdout


def changed_files(repo: Path, base: str, head: str) -> list[ChangedFile]:
    statuses = {}
    for line in git(repo, "diff", "--name-status", f"{base}...{head}").splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            code = parts[0][:1]
            statuses[parts[-1]] = {"A": "added", "D": "removed", "R": "renamed"}.get(code, "modified")
    files = []
    for line in git(repo, "diff", "--numstat", f"{base}...{head}").splitlines():
        parts = line.split("\t")
        if len(parts) == 3:
            adds, dels, path = parts
            path = path.split(" => ")[-1].replace("{", "").replace("}", "") if " => " in path else path
            files.append(ChangedFile(path, statuses.get(path, "modified"),
                                     int(adds) if adds.isdigit() else 0, int(dels) if dels.isdigit() else 0))
    return files


def render(report: dict) -> str:
    level = report["level"]
    icon = {"high": "🔴", "medium": "🟠", "low": "🟢"}[level]
    lines = [f"## {icon} AEIP change guard: {level} risk", "",
             f"{report['change']['files']} files changed (+{report['change']['additions']} −{report['change']['deletions']}). "
             f"{report['model']['message']}.", ""]
    if report["findings"]:
        lines += ["**What could break**", ""] + [f"- {item}" for item in report["findings"]] + [""]
    if report["checks"]:
        lines += ["**Before merging**", ""] + [f"{index}. {item}" for index, item in enumerate(report["checks"], 1)] + [""]
    if report["reviewers"]:
        lines += ["**Suggested reviewers:** " + ", ".join(
            f"{item['name']} ({item['commits']} commits to {', '.join(item['files'])})" for item in report["reviewers"]), ""]
    lines += ["**Rollback plan**", ""] + [f"{index}. {item}" for index, item in enumerate(report["rollback"], 1)] + [""]
    scored = [item for item in report["files"] if item.get("score") is not None]
    if scored:
        lines += ["| File | Risk | Learned | Tests |", "|---|---|---|---|"]
        for item in scored[:15]:
            learned = f"{round(item['learned']['probability'] * 100)}%" if item.get("learned") else "–"
            lines.append(f"| `{item['path']}` | {item['score']}/100 | {learned} | {item.get('tests', '–')} |")
        lines.append("")
    lines.append(f"<sub>{report['model']['meaning']} AEIP only reports; it never blocks or changes the pull request.</sub>")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", type=Path, default=Path("."), help="checkout with full history (fetch-depth: 0)")
    parser.add_argument("--base", default="origin/main", help="branch or commit the change will merge into")
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--title", default="")
    parser.add_argument("--fail-on", choices=("high", "medium"), help="exit 1 at this risk level or above")
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):  # Windows consoles default to a legacy code page
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    repo = args.repo.resolve()

    files = changed_files(repo, args.base, args.head)
    if not files:
        print("AEIP change guard: no changed files.")
        return 0
    base_sha = git(repo, "merge-base", args.base, args.head).strip()
    history = [to_commit(item) for item in read_history(repo) if item.sha]
    by_sha = {commit.sha: commit for commit in history}
    if base_sha in by_sha:  # judge the change against the history up to where it branched off
        cutoff = by_sha[base_sha].authored_at
        history = [commit for commit in history if commit.authored_at <= cutoff]
    now = max(commit.authored_at for commit in history)
    history = [commit for commit in history if commit.authored_at >= now - timedelta(days=365 * HISTORY_YEARS)]
    snapshot = RepositorySnapshot(repo.name, tuple(history), (), tuple(tree_documents(repo, base_sha)))
    learning = learn(snapshot, now, include=is_source_code, history_source="git history")
    title = args.title or git(repo, "log", "-1", "--format=%s", args.head).strip()
    author = git(repo, "log", "-1", "--format=%an", args.head).strip()
    report = assess_change(Change(repo.name, files, title, author=author), snapshot, now, history, learning)

    text = render(report)
    print(text)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as handle:
            handle.write(text)
    if args.fail_on and LEVEL_ORDER[report["level"]] >= LEVEL_ORDER[args.fail_on]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
