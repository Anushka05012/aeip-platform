"""Small dependency-free HTTP API for the AEIP intelligence demo.

This keeps the RAG engine independently runnable while giving the Next.js
frontend a stable contract.  It intentionally uses the local JSON fixture and
in-memory vector store until the ingestion team's database adapter is ready.
"""

from __future__ import annotations

import json
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .pipeline import IntelligencePipeline
from .seed_data import JsonSeedDataSource

ROOT = Path(__file__).resolve().parents[1]
DEMO_REPOSITORY = "acme/payments-api"
START = datetime.fromisoformat("2026-09-09T12:00:00")
NOW = datetime.fromisoformat("2026-09-16T12:00:00")


class IntelligenceDemoService:
    """Adapts the RAG pipeline to frontend-friendly JSON payloads."""

    def __init__(self) -> None:
        self.snapshot = JsonSeedDataSource(ROOT / "data" / "demo_repository.json").load_snapshot(DEMO_REPOSITORY)
        self.pipeline = IntelligencePipeline()
        self.indexed_documents = self.pipeline.prepare(self.snapshot)

    def overview(self) -> dict[str, Any]:
        dora, primary_risk, evidence, summary = self.pipeline.analyze(
            self.snapshot,
            path="src/payment_service.py",
            question="What should we test before payment deployment?",
            now=NOW,
            start=START,
        )
        risks = self.pipeline.risk_engine.score_files(self.snapshot, NOW)
        deployments_by_day: dict[str, int] = {}
        for deployment in self.snapshot.deployments:
            day = deployment.deployed_at.strftime("%b ") + str(deployment.deployed_at.day)
            deployments_by_day[day] = deployments_by_day.get(day, 0) + 1

        return {
            "repository": self.snapshot.repository,
            "indexedDocuments": self.indexed_documents,
            "metrics": [
                {"label": "Deployment frequency", "value": str(dora.deployment_frequency_per_week), "unit": "/week", "delta": "Demo dataset", "up": True},
                {"label": "Lead time for changes", "value": str(dora.lead_time_hours or 0), "unit": "hrs", "delta": "Successful deploys", "up": True},
                {"label": "Change failure rate", "value": str(dora.change_failure_rate_percent), "unit": "%", "delta": "Failed deploys", "up": False},
                {"label": "Highest file risk", "value": str(primary_risk.score), "unit": "/100", "delta": primary_risk.level.upper(), "up": primary_risk.level != "high"},
            ],
            "deployTrend": [{"d": day, "v": count} for day, count in deployments_by_day.items()],
            "riskItems": [
                {"file": item.path, "score": item.score, "reason": "; ".join(item.reasons)}
                for item in risks
            ],
            "failures": [
                {
                    "repo": self.snapshot.repository,
                    "branch": "demo",
                    "cause": f"Deployment {deployment.id} failed for commit {deployment.commit_sha}",
                    "time": deployment.deployed_at.isoformat(),
                    "severity": "high",
                }
                for deployment in self.snapshot.deployments
                if deployment.status == "failure"
            ],
            "summary": summary,
            "evidence": [{"path": item.path, "score": item.score} for item in evidence],
        }

    def ask(self, question: str, use_ai: bool = False) -> dict[str, Any]:
        question = question.strip()
        if not question:
            raise ValueError("A question is required.")
        if len(question) > 2_000:
            raise ValueError("Question must be 2,000 characters or fewer.")

        risks = self.pipeline.risk_engine.score_files(self.snapshot, NOW)
        risk = risks[0]
        evidence = self.pipeline.retriever.retrieve(question)
        client = None
        if use_ai:
            from .config import Settings
            from .groq_client import GroqClient

            client = GroqClient(Settings.load())
        answer = self.pipeline.summary_engine.summarize(risk, evidence, client)
        return {
            "answer": answer,
            "risk": {"file": risk.path, "score": risk.score, "level": risk.level, "reasons": list(risk.reasons)},
            "evidence": [{"path": item.path, "content": item.content, "score": item.score} for item in evidence],
            "mode": "groq" if use_ai else "offline",
        }


class IntelligenceRequestHandler(BaseHTTPRequestHandler):
    service = IntelligenceDemoService()

    def _send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Access-Control-Allow-Origin", "http://localhost:3000")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(encoded)

    def do_OPTIONS(self) -> None:  # noqa: N802 - inherited HTTP method name
        self._send_json(HTTPStatus.NO_CONTENT, {})

    def do_GET(self) -> None:  # noqa: N802 - inherited HTTP method name
        path = urlparse(self.path).path
        if path == "/health":
            self._send_json(HTTPStatus.OK, {"status": "ok", "service": "aeip-intelligence"})
        elif path == "/api/intelligence/demo":
            self._send_json(HTTPStatus.OK, self.service.overview())
        else:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Route not found"})

    def do_POST(self) -> None:  # noqa: N802 - inherited HTTP method name
        if urlparse(self.path).path != "/api/assistant":
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Route not found"})
            return
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            if content_length > 10_000:
                raise ValueError("Request body is too large.")
            body = json.loads(self.rfile.read(content_length) or b"{}")
            if not isinstance(body, dict):
                raise ValueError("Request body must be an object.")
            response = self.service.ask(str(body.get("question", "")), bool(body.get("useAi", False)))
            self._send_json(HTTPStatus.OK, response)
        except (ValueError, json.JSONDecodeError) as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except Exception:
            self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "Unable to answer the question."})

    def log_message(self, format: str, *args: Any) -> None:
        # Keep local demo output readable without hiding server errors.
        print(f"[intelligence-api] {format % args}")


def serve(host: str = "127.0.0.1", port: int = 8001) -> None:
    server = ThreadingHTTPServer((host, port), IntelligenceRequestHandler)
    print(f"AEIP intelligence API listening on http://{host}:{port}")
    server.serve_forever()
