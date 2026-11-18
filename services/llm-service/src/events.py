"""Operational events from tools beyond GitHub: deploys, application logs, databases and alerts.

Every source is normalised into one `OpsEvent` shape so the incident engine can line them up with
commits and CI runs on a single timeline. Adapters accept the webhook payloads the tools already
send (Vercel, Render, Sentry, GitHub deployments, Prometheus Alertmanager), a generic JSON format,
and raw log text. All text is secret-redacted before it is stored.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from .failure_analysis import redact_secrets

SOURCES = {"deploy", "app", "database", "alert", "ci", "vcs", "infra"}
SEVERITIES = ("debug", "info", "warning", "error", "critical")
MAX_EVENTS_PER_REPOSITORY = 5000
MAX_TEXT = 4000

_PATH = re.compile(r"(?<![\w/.-])((?:[\w.-]+/)*[\w.-]+\.(?:py|js|jsx|ts|tsx|go|rb|rs|java|kt|cs|php|sql|c|cpp))\b")
_VOLATILE = re.compile(r"0x[0-9a-f]+|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|\b[0-9a-f]{12,}\b|\d+",
                       re.IGNORECASE)
_QUOTED = re.compile(r"'[^']*'|\"[^\"]*\"")


def as_utc(value: datetime) -> datetime:
    """Snapshot times may be naive (demo fixture); treat those as UTC."""
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def parse_time(value: Any) -> datetime:
    if isinstance(value, datetime):
        return as_utc(value)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value / 1000 if value > 1e11 else value, tz=timezone.utc)
    if isinstance(value, str) and value.strip():
        text = value.strip().replace("Z", "+00:00")
        if re.fullmatch(r"\d+(\.\d+)?", text):
            return parse_time(float(text))
        return as_utc(datetime.fromisoformat(text.replace(" ", "T", 1) if "T" not in text else text))
    raise ValueError("Every event needs a time (ISO 8601 or epoch).")


def fingerprint(text: str) -> str:
    """Groups repeats of one error: numbers, ids and quoted values are masked before hashing."""
    first = text.strip().splitlines()[0] if text.strip() else ""
    normalised = _VOLATILE.sub("#", _QUOTED.sub("'?'", first.lower()))
    return hashlib.sha1(normalised.encode()).hexdigest()[:10]


def files_in(text: str) -> list[str]:
    found: list[str] = []
    for match in _PATH.findall(text):
        path = match.lstrip("./")
        if path not in found and "site-packages" not in path and "node_modules" not in path:
            found.append(path)
    return found[:20]


def _severity(value: Any, default: str = "info") -> str:
    text = str(value or "").lower()
    aliases = {"warn": "warning", "err": "error", "fatal": "critical", "crit": "critical", "panic": "critical",
               "emergency": "critical", "alert": "critical", "notice": "info", "trace": "debug", "page": "critical"}
    text = aliases.get(text, text)
    return text if text in SEVERITIES else default


@dataclass(frozen=True)
class OpsEvent:
    id: str
    source: str  # deploy | app | database | alert | ci | vcs | infra
    kind: str  # e.g. deploy.succeeded, deploy.failed, error, migration, slow_query, alert.firing
    time: datetime
    title: str
    severity: str = "info"
    service: str = ""
    environment: str = ""
    message: str = ""
    commit: str = ""
    url: str = ""
    fingerprint: str = ""
    files: tuple[str, ...] = ()
    attributes: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        data = asdict(self)
        data["time"] = self.time.isoformat()
        data["files"] = list(self.files)
        return data

    @staticmethod
    def from_json(data: dict[str, Any]) -> "OpsEvent":
        return make_event(data)


def make_event(data: dict[str, Any], default_source: str = "app") -> OpsEvent:
    """Validate and normalise one generic event (the documented JSON format)."""
    if not isinstance(data, dict):
        raise ValueError("Each event must be a JSON object.")
    source = str(data.get("source") or default_source).lower()
    if source not in SOURCES:
        raise ValueError(f"Unknown event source {source!r}; use one of {', '.join(sorted(SOURCES))}.")
    title = redact_secrets(str(data.get("title") or data.get("message") or data.get("kind") or "event"))[:300]
    message = redact_secrets(str(data.get("message") or ""))[:MAX_TEXT]
    kind = str(data.get("kind") or ("error" if source == "app" else "event")).lower()[:60]
    severity = _severity(data.get("severity") or data.get("level"),
                         "error" if kind.endswith(("failed", "error")) or kind == "error" else "info")
    time = parse_time(data.get("time") or data.get("timestamp"))
    files = tuple(data.get("files") or files_in(f"{title}\n{message}"))
    attributes = data.get("attributes") if isinstance(data.get("attributes"), dict) else {}
    raw_id = data.get("id") or f"{source}|{kind}|{time.isoformat()}|{title}|{data.get('service', '')}"
    return OpsEvent(
        id=str(raw_id)[:120] if data.get("id") else hashlib.sha1(str(raw_id).encode()).hexdigest()[:16],
        source=source, kind=kind, time=time, title=title, severity=severity,
        service=str(data.get("service") or "")[:100], environment=str(data.get("environment") or "")[:50],
        message=message, commit=str(data.get("commit") or "")[:40], url=str(data.get("url") or "")[:500],
        fingerprint=str(data.get("fingerprint") or (fingerprint(title) if severity in ("error", "critical") else "")),
        files=tuple(str(item)[:300] for item in files)[:20],
        attributes={str(key)[:60]: value for key, value in list(attributes.items())[:30]})


# -- adapters for payloads that tools already send ------------------------------------------------

def from_vercel(payload: dict[str, Any]) -> list[OpsEvent]:
    kind = str(payload.get("type", ""))
    status = {"deployment.succeeded": "succeeded", "deployment.ready": "succeeded", "deployment.error": "failed",
              "deployment.canceled": "canceled", "deployment.created": "started"}.get(kind)
    if not status:
        return []
    body = payload.get("payload", {})
    deployment = body.get("deployment", {})
    meta = deployment.get("meta", {})
    target = body.get("target") or "preview"
    return [make_event({
        "id": f"vercel-{deployment.get('id', '')}-{status}" if deployment.get("id") else None,
        "source": "deploy", "kind": f"deploy.{status}", "time": payload.get("createdAt"),
        "title": f"Vercel deploy {status}: {body.get('name') or deployment.get('name') or 'project'} ({target})",
        "service": body.get("name") or deployment.get("name") or "", "environment": target,
        "commit": meta.get("githubCommitSha", ""), "url": deployment.get("url", ""),
        "message": meta.get("githubCommitMessage", ""), "severity": "error" if status == "failed" else "info",
        "attributes": {"provider": "vercel", "branch": meta.get("githubCommitRef", "")}})]


def from_render(payload: dict[str, Any]) -> list[OpsEvent]:
    kind, data = str(payload.get("type", "")), payload.get("data", {})
    if kind not in ("deploy_started", "deploy_ended", "server_failed", "server_available"):
        return []
    status = str(data.get("status", "")).lower()
    name = data.get("serviceName") or data.get("serviceId") or "service"
    if kind == "deploy_ended":
        state = "succeeded" if status in ("succeeded", "live", "success") else "canceled" if status == "canceled" else "failed"
        event_kind, title = f"deploy.{state}", f"Render deploy {state}: {name}"
    elif kind == "deploy_started":
        event_kind, title = "deploy.started", f"Render deploy started: {name}"
    else:
        event_kind = "infra.down" if kind == "server_failed" else "infra.up"
        title = f"Render service {'failed' if kind == 'server_failed' else 'available'}: {name}"
    return [make_event({
        "id": f"render-{data.get('id', '')}-{kind}" if data.get("id") else None,
        "source": "infra" if kind.startswith("server") else "deploy", "kind": event_kind,
        "time": payload.get("timestamp"), "title": title, "service": name, "environment": "production",
        "commit": data.get("commitId", ""), "severity": "error" if event_kind in ("deploy.failed", "infra.down") else "info",
        "attributes": {"provider": "render"}})]


def from_sentry(payload: dict[str, Any]) -> list[OpsEvent]:
    data = payload.get("data", {})
    item = data.get("event") or data.get("issue") or {}
    if not item:
        return []
    frames = [frame for value in (item.get("exception") or {}).get("values", [])
              for frame in (value.get("stacktrace") or {}).get("frames", [])]
    files = [frame.get("filename") or frame.get("abs_path") for frame in reversed(frames) if frame.get("in_app", True)]
    stack = "\n".join(f"  at {frame.get('function', '?')} ({frame.get('filename') or frame.get('abs_path')}:{frame.get('lineno', '?')})"
                      for frame in reversed(frames))
    project = item.get("project")
    return [make_event({
        "id": f"sentry-{item.get('event_id') or item.get('id')}" if (item.get("event_id") or item.get("id")) else None,
        "source": "app", "kind": "error", "time": item.get("timestamp") or item.get("datetime") or item.get("firstSeen")
        or item.get("lastSeen"),
        "title": item.get("title") or item.get("message") or "Sentry error", "severity": item.get("level") or "error",
        "service": project.get("slug", "") if isinstance(project, dict) else str(project or ""),
        "environment": item.get("environment", ""), "commit": item.get("release", "") if re.fullmatch(
            r"[0-9a-f]{7,40}", str(item.get("release", ""))) else "",
        "message": f"{item.get('culprit', '')}\n{stack}".strip(), "url": item.get("web_url") or item.get("permalink") or "",
        "files": [path for path in files if path][:20], "attributes": {"provider": "sentry"}})]


def from_github_deployment(payload: dict[str, Any]) -> list[OpsEvent]:
    status, deployment = payload.get("deployment_status") or {}, payload.get("deployment") or {}
    state = str(status.get("state", ""))
    mapped = {"success": "succeeded", "failure": "failed", "error": "failed", "in_progress": "started"}.get(state)
    if not mapped:
        return []
    environment = status.get("environment") or deployment.get("environment") or ""
    return [make_event({
        "id": f"gh-deploy-{status.get('id', '')}" if status.get("id") else None,
        "source": "deploy", "kind": f"deploy.{mapped}", "time": status.get("created_at") or status.get("updated_at"),
        "title": f"GitHub deployment {mapped} ({environment or 'unknown environment'})", "environment": environment,
        "commit": deployment.get("sha", ""), "url": status.get("target_url") or status.get("log_url") or "",
        "message": status.get("description") or "", "severity": "error" if mapped == "failed" else "info",
        "service": (payload.get("repository") or {}).get("name", ""), "attributes": {"provider": "github"}})]


def from_alertmanager(payload: dict[str, Any]) -> list[OpsEvent]:
    events = []
    for alert in payload.get("alerts", []):
        labels, notes = alert.get("labels", {}), alert.get("annotations", {})
        firing = alert.get("status") == "firing"
        events.append(make_event({
            "id": f"alert-{alert.get('fingerprint') or labels.get('alertname')}-{'firing' if firing else 'resolved'}-"
                  f"{alert.get('startsAt') if firing else alert.get('endsAt')}",
            "source": "alert", "kind": "alert.firing" if firing else "alert.resolved",
            "time": alert.get("startsAt") if firing else (alert.get("endsAt") or alert.get("startsAt")),
            "title": notes.get("summary") or labels.get("alertname") or "alert",
            "message": notes.get("description", ""), "severity": (labels.get("severity") or "warning") if firing else "info",
            "service": labels.get("service") or labels.get("job") or "", "environment": labels.get("env") or labels.get("environment") or "",
            "url": alert.get("generatorURL", ""), "fingerprint": alert.get("fingerprint") or labels.get("alertname", ""),
            "attributes": {"provider": "alertmanager", "alertname": labels.get("alertname", "")}}))
    return events


ADAPTERS: dict[str, Callable[[dict[str, Any]], list[OpsEvent]]] = {
    "vercel": from_vercel, "render": from_render, "sentry": from_sentry,
    "github": from_github_deployment, "alertmanager": from_alertmanager,
}


# -- raw logs ------------------------------------------------------------------------------------

_TIMESTAMP = re.compile(r"^\[?(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?)\]?(?:\s+(?:UTC|GMT))?\s*")
_LEVEL = re.compile(r"\b(DEBUG|INFO|NOTICE|WARN(?:ING)?|ERROR|ERR|FATAL|CRITICAL|PANIC|LOG)\b:?")
_CONTINUATION = re.compile(r"^(\s+|Traceback|Caused by|\s*at\s|\s*File \"|During handling)")
_DATABASE_KINDS = [
    ("deadlock", re.compile(r"(?i)deadlock detected")),
    ("connection_error", re.compile(r"(?i)too many (connections|clients)|could not connect|connection (refused|reset|terminated)|"
                                    r"remaining connection slots|pool (exhausted|timeout)")),
    ("slow_query", re.compile(r"(?i)duration: (\d{4,}|[5-9]\d{2})(\.\d+)? ms|slow query")),
    ("migration", re.compile(r"(?i)applying migration|migrat(e|ion) (applied|started|finished|failed)|alter table|create index")),
    ("lock_timeout", re.compile(r"(?i)lock timeout|canceling statement due to (lock|statement) timeout")),
]


def parse_log_text(text: str, source: str = "app", service: str = "", environment: str = "",
                   default_time: datetime | None = None, min_severity: str = "warning") -> list[OpsEvent]:
    """Plain or JSON-lines logs -> events. Stack-trace lines attach to the entry above them."""
    if source not in SOURCES:
        raise ValueError(f"Unknown log source {source!r}.")
    entries: list[dict[str, Any]] = []
    for line in text.splitlines()[:20000]:
        if not line.strip():
            continue
        if line.lstrip().startswith("{"):
            try:
                record = json.loads(line)
                entries.append({"time": record.get("time") or record.get("timestamp") or record.get("ts") or record.get("@timestamp"),
                                "level": record.get("level") or record.get("severity") or record.get("lvl"),
                                "text": str(record.get("msg") or record.get("message") or line),
                                "extra": str(record.get("stack") or record.get("error") or "")})
                continue
            except json.JSONDecodeError:
                pass
        if entries and _CONTINUATION.match(line):
            entries[-1]["extra"] += "\n" + line.rstrip()
            continue
        stamp = _TIMESTAMP.match(line)
        rest = line[stamp.end():] if stamp else line
        level = _LEVEL.search(rest[:60])
        if level and level.start() <= 2:  # "ERROR: message" -> "message"
            rest = rest[level.end():]
        entries.append({"time": stamp.group(1) if stamp else None, "level": level.group(1) if level else None,
                        "text": rest.strip(), "extra": ""})

    floor = SEVERITIES.index(_severity(min_severity, "warning"))
    events, last_time = [], default_time
    seen: dict[str, int] = {}
    for entry in entries:
        text_body = f"{entry['text']}\n{entry['extra']}".strip()
        kind = "error"
        if source == "database":
            kind = next((name for name, pattern in _DATABASE_KINDS if pattern.search(text_body)), "log")
        severity = _severity(entry["level"], "info")
        if kind in ("deadlock", "connection_error", "lock_timeout") and SEVERITIES.index(severity) < 3:
            severity = "error"
        elif kind in ("slow_query", "migration") and SEVERITIES.index(severity) < 2:
            severity = "warning"
        if source == "app" and severity in ("debug", "info") and "Traceback" in text_body:
            severity = "error"
        try:
            when = parse_time(entry["time"]) if entry["time"] else last_time
        except ValueError:
            when = last_time
        if when is None:
            raise ValueError("Log lines need timestamps (or pass a default time).")
        last_time = when
        if SEVERITIES.index(severity) < floor and kind not in ("migration",):
            continue
        if source == "app":
            kind = "error" if severity in ("error", "critical") else "warning" if severity == "warning" else "log"
        # Identical lines at the same instant are separate occurrences; re-uploading the same text is not.
        key = f"{source}|{service}|{when.isoformat()}|{entry['text']}"
        seen[key] = seen.get(key, 0) + 1
        events.append(make_event({
            "id": hashlib.sha1(f"{key}|{seen[key]}".encode()).hexdigest()[:16],
            "source": source, "kind": kind, "time": when, "title": entry["text"][:300], "severity": severity,
            "service": service, "environment": environment, "message": entry["extra"].strip()}))
    return events


# -- storage -------------------------------------------------------------------------------------

class EventStore:
    """Per-repository events in memory, persisted as one JSON-lines file per repository."""

    def __init__(self, directory: Path | None = None) -> None:
        self.directory = directory
        self._events: dict[str, dict[str, OpsEvent]] = {}
        self._lock = threading.Lock()
        if directory and directory.exists():
            for path in directory.glob("*.jsonl"):
                repository = path.stem.replace("__", "/")
                for line in path.read_text(encoding="utf-8").splitlines():
                    try:
                        event = OpsEvent.from_json(json.loads(line))
                        self._events.setdefault(repository.lower(), {})[event.id] = event
                    except (ValueError, json.JSONDecodeError):
                        continue

    def add(self, repository: str, events: Iterable[OpsEvent], persist: bool = True) -> int:
        key = repository.lower()
        added = []
        with self._lock:
            bucket = self._events.setdefault(key, {})
            for event in events:
                if event.id not in bucket:
                    added.append(event)
                bucket[event.id] = event
            if len(bucket) > MAX_EVENTS_PER_REPOSITORY:  # keep the newest
                keep = sorted(bucket.values(), key=lambda item: item.time)[-MAX_EVENTS_PER_REPOSITORY:]
                self._events[key] = {item.id: item for item in keep}
                self._rewrite(repository)
            elif added and self.directory and persist:
                self.directory.mkdir(parents=True, exist_ok=True)
                with self._file(repository).open("a", encoding="utf-8") as handle:
                    for event in added:
                        handle.write(json.dumps(event.to_json()) + "\n")
        return len(added)

    def list(self, repository: str) -> list[OpsEvent]:
        with self._lock:
            return sorted(self._events.get(repository.lower(), {}).values(), key=lambda item: item.time)

    def clear(self, repository: str) -> None:
        with self._lock:
            self._events.pop(repository.lower(), None)
            if self.directory and self._file(repository).exists():
                self._file(repository).unlink()

    def _file(self, repository: str) -> Path:
        assert self.directory is not None
        return self.directory / f"{repository.lower().replace('/', '__')}.jsonl"

    def _rewrite(self, repository: str) -> None:
        if not self.directory:
            return
        self.directory.mkdir(parents=True, exist_ok=True)
        lines = [json.dumps(item.to_json()) for item in sorted(self._events[repository.lower()].values(), key=lambda e: e.time)]
        self._file(repository).write_text("\n".join(lines) + "\n", encoding="utf-8")
