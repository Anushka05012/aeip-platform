"""Run from services/llm-service: python scripts/demo_intelligence_flow.py [--ai]."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.pipeline import IntelligencePipeline
from src.seed_data import JsonSeedDataSource

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime.fromisoformat("2026-09-16T12:00:00")
START = datetime.fromisoformat("2026-09-09T12:00:00")


def main() -> None:
    snapshot = JsonSeedDataSource(ROOT / "data" / "demo_repository.json").load_snapshot("acme/payments-api")
    pipeline = IntelligencePipeline()
    indexed = pipeline.prepare(snapshot)
    client = None
    if "--ai" in sys.argv:
        # Keep the default demo completely offline; only import this optional
        # dependency when the user explicitly asks for a live Groq summary.
        from src.config import Settings
        from src.groq_client import GroqClient
        client = GroqClient(Settings.load())
    dora, risk, evidence, summary = pipeline.analyze(
        snapshot=snapshot,
        path="src/payment_service.py",
        question="Why is the payment service risky and what should we test before deployment?",
        now=NOW,
        start=START,
        chat_client=client,
    )
    print(f"AEIP Intelligence Demo | {snapshot.repository}")
    print(f"Indexed documents: {indexed}")
    print("\nDORA metrics")
    print(f"  Deployment frequency: {dora.deployment_frequency_per_week}/week")
    print(f"  Lead time: {dora.lead_time_hours} hours")
    print(f"  Change failure rate: {dora.change_failure_rate_percent}%")
    print(f"\nRisk: {risk.path} -> {risk.level.upper()} ({risk.score}/100)")
    for reason in risk.reasons:
        print(f"  - {reason}")
    print("\nRetrieved evidence")
    for item in evidence:
        print(f"  - {item.path} (hybrid score {item.score})")
    print("\nEvidence-grounded summary")
    print(f"  {summary}")


if __name__ == "__main__":
    main()
