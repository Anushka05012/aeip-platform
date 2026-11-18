"""Small dependency-free HTTP API for the AEIP intelligence service.

Serves the bundled demo fixture plus any GitHub repository analyzed at runtime.
Each analysis is cached to data/cache so a restart (or a flaky network during a
live demo) does not lose it.
"""

from __future__ import annotations

import hmac
import json
import os
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

from .assistant import RepositoryAssistant
from .domain import RepositorySnapshot
from .dora import DoraMetrics, calculate_dora
from .embeddings import tokenize
from .failure_analysis import FailureAnalyzer
from .events import ADAPTERS, EventStore, make_event, parse_log_text
from .flaky import detect_flaky
from .github_source import GitHubDataSource, GitHubError, is_source_code, parse_repository
from .pipeline import IntelligencePipeline
from .risk_engine import RiskResult
from .seed_data import JsonSeedDataSource, snapshot_from_json, snapshot_to_json

try:
    from dotenv import load_dotenv

    load_dotenv()  # GITHUB_TOKEN / GROQ_API_KEY from services/llm-service/.env
except ImportError:
    pass

ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "data" / "cache"
DEMO_REPOSITORY = "acme/payments-api"
START = datetime.fromisoformat("2026-09-09T12:00:00")
NOW = datetime.fromisoformat("2026-09-16T12:00:00")
LIVE_WINDOW_DAYS = 30
ALLOWED_ORIGINS = {"http://localhost:3000", "http://127.0.0.1:3000"}
HISTORY_TERMS = set(tokenize("changed recent recently commit history fail failure failing broke build pipeline ci deploy"))


@dataclass
class AnalyzedRepository:
    snapshot: RepositorySnapshot
    releases: RepositorySnapshot  # snapshot restricted to default-branch runs, for DORA
    pipeline: IntelligencePipeline
    indexed: int
    risks: list[RiskResult]
    now: datetime
    start: datetime
    window_days: int
    source: str
    analyzed_at: str
    stages: list[dict[str, Any]] = field(default_factory=list)


def sync_to_database(repository: str) -> dict[str, Any]:
    """Store the repository's commits and PRs in PostgreSQL via the ingestion service (ingestion/).

    Best-effort: analysis never fails because the database layer is down; the pipeline
    log records what happened instead.
    """
    base = os.getenv("INGESTION_API_URL", "http://localhost:4000").rstrip("/")
    owner, repo = repository.split("/", 1)
    request = urllib.request.Request(
        f"{base}/api/repositories", data=json.dumps({"owner": owner, "repo": repo}).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            body = json.loads(response.read() or b"{}")
        detail = (f"{body.get('commitsIngested', 0)} commits and {body.get('pullRequestsIngested', 0)} "
                  "pull requests stored via the ingestion service")
    except urllib.error.HTTPError as exc:
        detail = f"failed: ingestion service returned HTTP {exc.code}"
    except (urllib.error.URLError, OSError):
        detail = f"skipped: ingestion service not running at {base}"
    return {"stage": "Database (PostgreSQL)", "detail": detail, "ms": round((time.perf_counter() - started) * 1000)}


def _restore_delta(dora: DoraMetrics) -> str:
    if not dora.restored_incidents:
        return f"{dora.open_incidents} failure(s) not yet restored" if dora.open_incidents else "no failures to restore"
    text = f"median of {dora.restored_incidents} recover{'y' if dora.restored_incidents == 1 else 'ies'}"
    return text + (f" · {dora.open_incidents} still failing" if dora.open_incidents else "")


def groq_client_if_configured():
    """Return a Groq client when a real key is configured, else None (offline mode)."""
    try:
        from .config import Settings
        from .groq_client import GroqClient

        settings = Settings.load(require_api_key=False)
        if not settings.groq_api_key or settings.groq_api_key.startswith("your_"):
            return None
        return GroqClient(settings)
    except Exception:
        return None


class IntelligenceDemoService:
    """Adapts the RAG pipeline to frontend-friendly JSON payloads."""

    def __init__(self, cache_dir: Path | None = CACHE_DIR,
                 github_factory: Callable[[], GitHubDataSource] = GitHubDataSource,
                 database_sync: Callable[[str], dict[str, Any]] | None = sync_to_database) -> None:
        self.cache_dir = cache_dir
        self.github_factory = github_factory
        self.database_sync = database_sync
        self.assistant = RepositoryAssistant()
        self.failure_analyzer = FailureAnalyzer()
        self.repositories: dict[str, AnalyzedRepository] = {}
        self._lock = threading.Lock()
        self.events = EventStore(cache_dir / "events" if cache_dir else None)
        self._load_demo_events()
        demo = JsonSeedDataSource(ROOT / "data" / "demo_repository.json").load_snapshot(DEMO_REPOSITORY)
        self._register(demo, "demo fixture", [], window=(START, NOW, 7))
        self._load_cache()

    def _load_demo_events(self) -> None:
        path = ROOT / "data" / "demo_events.json"
        if not path.exists():
            return
        raw = json.loads(path.read_text(encoding="utf-8"))
        events = [make_event(item) for item in raw.get("events", [])]
        for log in raw.get("logs", []):
            events += parse_log_text(log["text"], log["source"], log.get("service", ""), log.get("environment", ""))
        self.events.add(DEMO_REPOSITORY, events, persist=False)

    # -- operational events (deploys, app logs, databases, alerts) -------------
    def ingest_events(self, repository: str, payload: Any, adapter: str = "generic") -> dict[str, Any]:
        repository = parse_repository(repository)
        if adapter == "generic":
            items = payload.get("events", [payload]) if isinstance(payload, dict) else payload
            if not isinstance(items, list) or not items:
                raise ValueError('Send an event object, a list of events, or {"events": [...]}.')
            if len(items) > 1000:
                raise ValueError("At most 1000 events per request.")
            events = [make_event(item) for item in items]
        elif adapter in ADAPTERS:
            if not isinstance(payload, dict):
                raise ValueError(f"A {adapter} webhook payload must be a JSON object.")
            events = ADAPTERS[adapter](payload)
        else:
            raise ValueError(f"Unknown event format {adapter!r}; use generic, logs or {', '.join(sorted(ADAPTERS))}.")
        added = self.events.add(repository, events)
        return {"repository": repository, "received": len(events), "added": added}

    def ingest_logs(self, repository: str, text: str, source: str = "app", service: str = "",
                    environment: str = "", min_severity: str = "warning") -> dict[str, Any]:
        repository = parse_repository(repository)
        if not text.strip():
            raise ValueError("Log text is empty.")
        events = parse_log_text(text, source, service, environment, datetime.now().astimezone(), min_severity)
        added = self.events.add(repository, events)
        return {"repository": repository, "received": len(events), "added": added}

    def list_events(self, repository: str | None = None, source: str | None = None, limit: int = 500) -> dict[str, Any]:
        name = repository or DEMO_REPOSITORY
        events = [item for item in self.events.list(name) if not source or item.source == source]
        counts: dict[str, int] = {}
        for item in events:
            counts[item.source] = counts.get(item.source, 0) + 1
        return {"repository": name, "total": len(events), "bySource": counts,
                "events": [item.to_json() for item in events[-max(1, min(limit, 5000)):]]}

    # -- repository registry ---------------------------------------------------
    def _load_cache(self) -> None:
        if not self.cache_dir or not self.cache_dir.exists():
            return
        for path in sorted(self.cache_dir.glob("*.json")):
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                self._register(snapshot_from_json(raw), "GitHub (cached)", raw.get("stages", []),
                               analyzed_at=raw.get("analyzedAt"))
            except Exception as exc:  # a corrupt cache file must not stop the service
                print(f"[intelligence-api] skipped cache {path.name}: {exc}")

    def _register(self, snapshot: RepositorySnapshot, source: str, stages: list[dict[str, Any]],
                  window: tuple[datetime, datetime, int] | None = None,
                  analyzed_at: str | None = None) -> AnalyzedRepository:
        stages = list(stages)
        pipeline = IntelligencePipeline()
        started = time.perf_counter()
        indexed = pipeline.prepare(snapshot)
        stages.append({"stage": "Embedding + vector index", "detail": f"{indexed} chunks embedded for hybrid retrieval",
                       "ms": round((time.perf_counter() - started) * 1000)})

        # DORA counts push-triggered CI runs on the default branch as deployments; PR and
        # scheduled runs are still listed as failures but are not releases.
        releases = replace(snapshot, deployments=tuple(
            item for item in snapshot.deployments
            if (not snapshot.default_branch or item.branch == snapshot.default_branch)
            and item.event in ("", "push")))
        include = None
        if window is None:
            include = is_source_code  # live repositories: score production code only
            # Analyse "as of" the latest activity so quiet repositories still show data, and
            # widen the risk window to cover every fetched commit.
            commit_times = [item.authored_at for item in snapshot.commits]
            risk_now = max(commit_times) if commit_times else datetime.now().astimezone()
            span = (risk_now - min(commit_times)).days + 1 if commit_times else 0
            window_days = min(max(LIVE_WINDOW_DAYS, span), 365)
            release_times = [item.deployed_at for item in releases.deployments] or commit_times
            now = max(release_times) if release_times else risk_now
            start = now - timedelta(days=LIVE_WINDOW_DAYS)
        else:
            start, now, window_days = window
            risk_now = now

        started = time.perf_counter()
        risks = pipeline.risk_engine.score_files(snapshot, risk_now, window_days, include)
        top = f"; highest {risks[0].path} ({risks[0].score}/100)" if risks else ""
        stages.append({"stage": "Risk scoring", "detail": f"{len(risks)} files scored over {window_days} days{top}",
                       "ms": round((time.perf_counter() - started) * 1000)})
        dora = calculate_dora(releases, start, now)
        stages.append({"stage": "DORA metrics", "detail": (
            f"{dora.deployment_frequency_per_week}/week deploys, "
            f"{dora.change_failure_rate_percent}% change failure rate, "
            f"time to restore {dora.time_to_restore_hours if dora.time_to_restore_hours is not None else 'n/a'}h"), "ms": 0})

        entry = AnalyzedRepository(snapshot, releases, pipeline, indexed, risks, now, start, window_days, source,
                                   analyzed_at or datetime.now().astimezone().isoformat(timespec="seconds"), stages)
        with self._lock:
            self.repositories[snapshot.repository] = entry
        return entry

    def _get(self, repository: str | None) -> AnalyzedRepository:
        name = repository or DEMO_REPOSITORY
        with self._lock:
            for key, entry in self.repositories.items():
                if key.lower() == name.lower():
                    return entry
        raise KeyError(f"{name} has not been analyzed yet. Analyze it from the Repositories page.")

    def _describe(self, entry: AnalyzedRepository) -> dict[str, Any]:
        return {
            "repository": entry.snapshot.repository,
            "source": entry.source,
            "indexedDocuments": entry.indexed,
            "commits": len(entry.snapshot.commits),
            "ciRuns": len(entry.snapshot.deployments),
            "pullRequests": len(entry.snapshot.pull_requests),
            "riskyFiles": len(entry.risks),
            "analyzedAt": entry.analyzed_at,
            "stages": entry.stages,
        }

    def list_repositories(self) -> dict[str, Any]:
        with self._lock:
            entries = list(self.repositories.values())
        entries.sort(key=lambda entry: entry.analyzed_at, reverse=True)
        entries.sort(key=lambda entry: entry.source == "demo fixture")  # newest first, demo fixture last
        return {"repositories": [self._describe(entry) for entry in entries]}

    def analyze_repository(self, value: str, refresh: bool = False) -> dict[str, Any]:
        repository = parse_repository(value)
        if not refresh:
            try:
                return self._describe(self._get(repository))
            except KeyError:
                pass
        source = self.github_factory()
        snapshot = source.load_snapshot(repository)
        if self.database_sync:
            source.report.stages.append(self.database_sync(snapshot.repository))
        analyzed_at = datetime.now().astimezone().isoformat(timespec="seconds")
        entry = self._register(snapshot, "GitHub (live)", source.report.stages, analyzed_at=analyzed_at)
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            payload = snapshot_to_json(snapshot) | {"stages": source.report.stages, "analyzedAt": analyzed_at}
            (self.cache_dir / f"{snapshot.repository.replace('/', '__')}.json").write_text(
                json.dumps(payload), encoding="utf-8")
        return self._describe(entry)

    # -- views -----------------------------------------------------------------
    def overview(self, repository: str | None = None) -> dict[str, Any]:
        entry = self._get(repository)
        snapshot, pipeline = entry.snapshot, entry.pipeline
        dora = calculate_dora(entry.releases, entry.start, entry.now)
        primary = entry.risks[0] if entry.risks else None
        if primary:
            evidence = pipeline.retriever.retrieve(f"{primary.path} tests deployment risk")
            summary = pipeline.summary_engine.summarize(primary, evidence)
        else:
            evidence, summary = [], f"No commits touched analyzable files in the last {entry.window_days} days."

        window = [item for item in entry.releases.deployments if entry.start <= item.deployed_at <= entry.now]
        deployments_by_day: dict[str, int] = {}
        for deployment in sorted(window, key=lambda item: item.deployed_at):
            day = deployment.deployed_at.strftime("%b ") + str(deployment.deployed_at.day)
            deployments_by_day[day] = deployments_by_day.get(day, 0) + 1
        commit_messages = {item.sha: item.message.splitlines()[0] for item in snapshot.commits if item.message}
        flaky = detect_flaky(snapshot.deployments)
        flaky_runs = {run_id for item in flaky for run_id in item.flaky_failure_ids}
        label = "Demo dataset" if entry.source == "demo fixture" else f"Last {entry.window_days} days"

        return {
            "repository": snapshot.repository,
            "source": entry.source,
            "indexedDocuments": entry.indexed,
            "metrics": [
                {"label": "Deployment frequency", "value": str(dora.deployment_frequency_per_week), "unit": "/week",
                 "delta": f"{len(window)} runs · {label.lower()}", "up": True},
                {"label": "Lead time for changes", "value": str(dora.lead_time_hours or 0), "unit": "h",
                 "delta": "commit to successful run" if dora.lead_time_hours else "no matching commits", "up": True},
                {"label": "Change failure rate", "value": str(dora.change_failure_rate_percent), "unit": "%",
                 "delta": f"{sum(1 for item in window if item.status == 'failure')} of {len(window)} runs failed", "up": False},
                {"label": "Time to restore", "value": str(dora.time_to_restore_hours if dora.time_to_restore_hours is not None else "n/a"),
                 "unit": "h" if dora.time_to_restore_hours is not None else "",
                 "delta": _restore_delta(dora), "up": dora.open_incidents == 0},
                {"label": "Highest file risk", "value": str(primary.score if primary else 0), "unit": "/100",
                 "delta": f"{primary.level} · {primary.path.rsplit('/', 1)[-1]}" if primary else "no data",
                 "up": not primary or primary.level != "high"},
            ],
            "deployTrend": [{"d": day, "v": count} for day, count in deployments_by_day.items()],
            "riskItems": [
                {"file": item.path, "score": item.score, "reason": "; ".join(item.reasons), "level": item.level,
                 "changes": item.recent_changes, "churn": item.churn, "complexity": item.complexity_delta,
                 "hasTests": item.has_tests, "testTouchRatio": item.test_touch_ratio, "dependents": item.dependents,
                 "dependencyChanges": item.dependency_changes, "breakdown": item.breakdown()}
                for item in entry.risks[:25]
            ],
            "failures": [
                {
                    "id": deployment.id,
                    "commit": deployment.commit_sha,
                    "workflow": deployment.name,
                    "event": deployment.event,
                    "repo": snapshot.repository,
                    "branch": deployment.branch or "demo",
                    "cause": (f"{deployment.name or 'Deployment ' + deployment.id} failed for commit {deployment.commit_sha[:7]}"
                              + (f": {commit_messages[deployment.commit_sha]}" if deployment.commit_sha in commit_messages else "")),
                    "time": deployment.deployed_at.isoformat(),
                    "severity": "high" if deployment.branch in ("", "main", "master") else "medium",
                    "flaky": deployment.id in flaky_runs,
                }
                for deployment in sorted(snapshot.deployments, key=lambda item: item.deployed_at, reverse=True)
                if deployment.status == "failure"
            ][:25],
            "flaky": [item.to_json() for item in flaky if item.level != "stable"],
            "summary": summary,
            "windowDays": entry.window_days,
            "evidence": [{"path": item.path, "score": item.score} for item in evidence],
        }

    def explain_failure(self, run_id: str, repository: str | None = None, use_ai: bool = False,
                        refresh: bool = False) -> dict[str, Any]:
        entry = self._get(repository)
        name = entry.snapshot.repository
        deployment = next((item for item in entry.snapshot.deployments if item.id == str(run_id)), None)
        if deployment is None or deployment.status != "failure":
            raise ValueError(f"No failed run {run_id!r} in {name}.")
        cache_file = (self.cache_dir / "explanations" / f"{name.replace('/', '__')}__{deployment.id}.json"
                      if self.cache_dir else None)
        if not refresh and cache_file and cache_file.exists():
            return json.loads(cache_file.read_text(encoding="utf-8")) | {"cached": True}

        commit = next((item for item in entry.snapshot.commits if item.sha == deployment.commit_sha), None)
        failed_jobs, notes = [], []
        if not deployment.log and entry.source != "demo fixture":
            github = self.github_factory()
            try:
                failed_jobs = github.fetch_failed_jobs(name, deployment.id)
                if commit is None:  # PR-branch runs point at commits outside the fetched history
                    commit = github.fetch_commit(name, deployment.commit_sha)
            except GitHubError as exc:
                notes.append(f"Could not fetch job details from GitHub: {exc}")
        client = groq_client_if_configured() if use_ai else None
        result = self.failure_analyzer.explain(deployment, commit, failed_jobs, entry.risks,
                                               entry.pipeline.retriever, client, entry.snapshot.pull_requests,
                                               entry.snapshot.deployments)
        result.notes = notes + result.notes
        payload = result.to_json()
        if cache_file and not notes:  # don't cache an analysis that was missing GitHub data
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(json.dumps(payload), encoding="utf-8")
        return payload | {"cached": False}

    def ask(self, question: str, use_ai: bool = False, repository: str | None = None) -> dict[str, Any]:
        question = question.strip()
        if not question:
            raise ValueError("A question is required.")
        if len(question) > 2_000:
            raise ValueError("Question must be 2,000 characters or fewer.")

        entry = self._get(repository)
        evidence = entry.pipeline.retriever.retrieve(question, limit=6)
        if HISTORY_TERMS & set(tokenize(question)):
            # "What changed / why did CI fail" questions need the ingested history, not just code.
            history = [item for item in entry.pipeline.retriever.retrieve("recent commit history CI failures", limit=10)
                       if item.source_type == "history" and item not in evidence]
            evidence = history[:2] + evidence[:6 - min(len(history), 2)]
        client = groq_client_if_configured() if use_ai else None
        mode = "groq" if client else "offline"
        try:
            answer = self.assistant.answer(question, entry.snapshot.repository, evidence, entry.risks, client)
        except Exception as exc:  # keep the demo answering even if Groq is down or rate limited
            print(f"[intelligence-api] Groq failed, using offline answer: {exc}")
            mode = "offline"
            answer = self.assistant.answer(question, entry.snapshot.repository, evidence, entry.risks, None)
        risk = entry.risks[0] if entry.risks else None
        return {
            "answer": answer,
            "risk": {"file": risk.path, "score": risk.score, "level": risk.level, "reasons": list(risk.reasons)} if risk else None,
            "evidence": [{"path": item.path, "content": item.content, "score": item.score} for item in evidence],
            "mode": mode,
        }


class IntelligenceRequestHandler(BaseHTTPRequestHandler):
    service = IntelligenceDemoService()

    def _send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        origin = self.headers.get("Origin", "")
        self.send_header("Access-Control-Allow-Origin", origin if origin in ALLOWED_ORIGINS else "http://localhost:3000")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-AEIP-Key")
        self.end_headers()
        self.wfile.write(encoded)

    def _read_raw(self, limit: int) -> bytes:
        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length > limit:
            raise ValueError("Request body is too large.")
        return self.rfile.read(content_length)

    def _read_body(self, limit: int = 10_000, allow_list: bool = False) -> Any:
        body = json.loads(self._read_raw(limit) or b"{}")
        if not isinstance(body, dict) and not (allow_list and isinstance(body, list)):
            raise ValueError("Request body must be an object.")
        return body

    def _ingest_authorized(self, query: dict[str, list[str]]) -> bool:
        """Ingest routes accept writes from outside tools. When AEIP_INGEST_KEY is set, require it
        (X-AEIP-Key header, Bearer token, or ?key= for tools that cannot set headers)."""
        expected = os.environ.get("AEIP_INGEST_KEY", "")
        if not expected:
            return True
        auth = self.headers.get("Authorization", "")
        supplied = (self.headers.get("X-AEIP-Key") or (auth[7:] if auth.lower().startswith("bearer ") else "")
                    or query.get("key", [""])[0])
        return hmac.compare_digest(supplied.encode(), expected.encode())

    def _handle(self, action: Callable[[], dict[str, Any]]) -> None:
        try:
            self._send_json(HTTPStatus.OK, action())
        except KeyError as exc:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": str(exc.args[0])})
        except (ValueError, json.JSONDecodeError) as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except GitHubError as exc:
            self._send_json(HTTPStatus.BAD_GATEWAY, {"error": str(exc)})
        except Exception as exc:
            print(f"[intelligence-api] unexpected error: {exc!r}")
            self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "The intelligence service hit an unexpected error."})

    def do_OPTIONS(self) -> None:  # noqa: N802 - inherited HTTP method name
        self._send_json(HTTPStatus.NO_CONTENT, {})

    def do_GET(self) -> None:  # noqa: N802 - inherited HTTP method name
        url = urlparse(self.path)
        repository = parse_qs(url.query).get("repository", [None])[0]
        if url.path == "/health":
            self._send_json(HTTPStatus.OK, {"status": "ok", "service": "aeip-intelligence",
                                            "llm": "groq" if groq_client_if_configured() else "offline"})
        elif url.path == "/api/intelligence/demo":
            self._handle(lambda: self.service.overview(repository))
        elif url.path == "/api/repositories":
            self._handle(self.service.list_repositories)
        elif url.path == "/api/events":
            query = parse_qs(url.query)
            self._handle(lambda: self.service.list_events(repository, query.get("source", [None])[0],
                                                          int(query.get("limit", ["500"])[0])))
        else:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Route not found"})

    def do_POST(self) -> None:  # noqa: N802 - inherited HTTP method name
        url = urlparse(self.path)
        path, query = url.path, parse_qs(url.query)
        if path.startswith("/api/events"):
            if not self._ingest_authorized(query):
                self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "Missing or wrong ingest key (AEIP_INGEST_KEY)."})
                return
            fmt = path[len("/api/events"):].strip("/") or "generic"
            repository = query.get("repository", [""])[0]

            def ingest() -> dict[str, Any]:
                if fmt == "logs":
                    raw = self._read_raw(5_000_000)
                    if "json" in self.headers.get("Content-Type", ""):
                        body = json.loads(raw or b"{}")
                        return self.service.ingest_logs(body.get("repository") or repository, str(body.get("text", "")),
                                                        body.get("source", "app"), body.get("service", ""),
                                                        body.get("environment", ""), body.get("minSeverity", "warning"))
                    return self.service.ingest_logs(repository, raw.decode("utf-8", errors="replace"),
                                                    query.get("source", ["app"])[0], query.get("service", [""])[0],
                                                    query.get("environment", [""])[0],
                                                    query.get("minSeverity", ["warning"])[0])
                body = self._read_body(2_000_000, allow_list=True)
                target = repository or (body.get("repository", "") if isinstance(body, dict) and fmt == "generic" else "")
                if not target:
                    raise ValueError("Say which repository these events belong to: ?repository=owner/name")
                return self.service.ingest_events(target, body, fmt)
            self._handle(ingest)
        elif path == "/api/assistant":
            def ask() -> dict[str, Any]:
                body = self._read_body()
                return self.service.ask(str(body.get("question", "")), bool(body.get("useAi", True)),
                                        body.get("repository") or None)
            self._handle(ask)
        elif path == "/api/repositories/analyze":
            def analyze() -> dict[str, Any]:
                body = self._read_body()
                return self.service.analyze_repository(str(body.get("repository", "")), bool(body.get("refresh", False)))
            self._handle(analyze)
        elif path == "/api/failures/explain":
            def explain() -> dict[str, Any]:
                body = self._read_body()
                return self.service.explain_failure(str(body.get("runId", "")), body.get("repository") or None,
                                                    bool(body.get("useAi", True)), bool(body.get("refresh", False)))
            self._handle(explain)
        else:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Route not found"})

    def log_message(self, format: str, *args: Any) -> None:
        # Keep local demo output readable without hiding server errors.
        print(f"[intelligence-api] {format % args}")


def serve(host: str = "127.0.0.1", port: int = 8001) -> None:
    server = ThreadingHTTPServer((host, port), IntelligenceRequestHandler)
    print(f"AEIP intelligence API listening on http://{host}:{port}")
    print("LLM mode:", "Groq" if groq_client_if_configured() else "offline (set GROQ_API_KEY in .env for Groq answers)")
    server.serve_forever()
