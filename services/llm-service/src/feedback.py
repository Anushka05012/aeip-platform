"""Engineers' verdicts on AEIP's incident root-cause candidates.

"This was the cause" turns the candidate change into a production-grounded label: the files it
touched broke production at that time. learned_risk.py learns from these labels, so every
confirmed incident makes the next risk ranking more specific to the repository. "Not it" is kept
too (it is evidence for future evaluation), and the newest verdict for a candidate wins.

Stored as one JSON-lines file per repository, like the event store.
"""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .learned_risk import IncidentLabel

VERDICTS = ("confirmed", "rejected")


@dataclass(frozen=True)
class Feedback:
    incident_id: str
    ref: str  # the candidate's reference (deploy id, commit sha, migration or flag name)
    verdict: str
    change_time: str  # when the candidate change went live (ISO 8601)
    files: tuple[str, ...]
    user: str = ""
    recorded_at: str = ""

    def to_json(self) -> dict[str, Any]:
        return asdict(self) | {"files": list(self.files)}

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "Feedback":
        return cls(str(data["incident_id"]), str(data["ref"]), str(data["verdict"]), str(data["change_time"]),
                   tuple(data.get("files", ())), str(data.get("user", "")), str(data.get("recorded_at", "")))


class FeedbackStore:
    def __init__(self, directory: Path | None = None) -> None:
        self.directory = directory
        self._items: dict[str, dict[tuple[str, str], Feedback]] = {}
        self._lock = threading.Lock()
        if directory and directory.exists():
            for path in sorted(directory.glob("*.jsonl")):
                repository = path.stem.replace("__", "/").lower()
                for line in path.read_text(encoding="utf-8").splitlines():
                    try:
                        item = Feedback.from_json(json.loads(line))
                    except (KeyError, ValueError, json.JSONDecodeError):
                        continue
                    self._items.setdefault(repository, {})[(item.incident_id, item.ref)] = item

    def record(self, repository: str, incident_id: str, ref: str, verdict: str, change_time: datetime,
               files: Iterable[str], user: str = "") -> Feedback:
        if verdict not in VERDICTS:
            raise ValueError(f"verdict must be one of {', '.join(VERDICTS)}")
        item = Feedback(incident_id, ref, verdict, change_time.astimezone(timezone.utc).isoformat(),
                        tuple(sorted(set(files))), user, datetime.now(timezone.utc).isoformat())
        with self._lock:
            self._items.setdefault(repository.lower(), {})[(incident_id, ref)] = item
            if self.directory:
                self.directory.mkdir(parents=True, exist_ok=True)
                path = self.directory / (repository.replace("/", "__") + ".jsonl")
                with path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(item.to_json()) + "\n")
        return item

    def for_incident(self, repository: str, incident_id: str) -> dict[str, str]:
        """Candidate ref -> verdict, for showing the buttons' state."""
        with self._lock:
            return {ref: item.verdict for (incident, ref), item in self._items.get(repository.lower(), {}).items()
                    if incident == incident_id}

    def labels(self, repository: str) -> list[IncidentLabel]:
        """Confirmed causes as training labels for the risk model."""
        with self._lock:
            items = list(self._items.get(repository.lower(), {}).values())
        return [IncidentLabel(datetime.fromisoformat(item.change_time), item.files)
                for item in items if item.verdict == "confirmed" and item.files]
