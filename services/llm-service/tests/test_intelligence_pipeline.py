import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.dora import calculate_dora
from src.embeddings import EmbeddingWorker, HashingEmbedder, InMemoryVectorStore
from src.pipeline import IntelligencePipeline
from src.rag import RepositoryRetriever
from src.risk_engine import RiskEngine
from src.seed_data import JsonSeedDataSource

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime.fromisoformat("2026-09-16T12:00:00")
START = datetime.fromisoformat("2026-09-09T12:00:00")


def snapshot():
    return JsonSeedDataSource(ROOT / "data" / "demo_repository.json").load_snapshot("acme/payments-api")


def test_seed_fixture_is_a_valid_standalone_data_source():
    data = snapshot()
    assert data.repository == "acme/payments-api"
    assert len(data.commits) == 6
    assert len(data.documents) == 3


def test_embedding_worker_and_retriever_return_payment_evidence():
    data = snapshot()
    embedder, store = HashingEmbedder(), InMemoryVectorStore()
    assert EmbeddingWorker(embedder, store).index(data.documents) == 3
    results = RepositoryRetriever(embedder, store).retrieve("payment deployment gateway test")
    assert results
    assert any(item.path in {"src/payment_service.py", "docs/payments.md"} for item in results)


def test_risk_engine_makes_frequently_changed_payment_service_high_risk():
    result = RiskEngine().score_files(snapshot(), NOW)[0]
    assert result.path == "src/payment_service.py"
    assert result.level == "high"
    assert result.score >= 70


def test_dora_metrics_are_calculated_from_fixture_events():
    metrics = calculate_dora(snapshot(), START, NOW)
    assert metrics.deployment_frequency_per_week == 4.0
    assert metrics.change_failure_rate_percent == 50.0
    assert metrics.lead_time_hours is not None


def test_pipeline_runs_without_a_groq_key_or_any_team_integration():
    pipeline = IntelligencePipeline()
    data = snapshot()
    pipeline.prepare(data)
    dora, risk, evidence, summary = pipeline.analyze(
        data, "src/payment_service.py", "What should we test before payment deployment?", NOW, START
    )
    assert dora.change_failure_rate_percent == 50.0
    assert risk.level == "high"
    assert evidence
    assert "Evidence:" in summary


def test_time_to_restore_is_the_median_failure_to_recovery_per_workflow():
    metrics = calculate_dora(snapshot(), START, NOW)
    # "Tests" failed on Sep 12 and passed on Sep 14; "Deploy" failed on Sep 15 and has not recovered.
    assert metrics.time_to_restore_hours == 48.0
    assert (metrics.restored_incidents, metrics.open_incidents) == (1, 1)


def test_time_to_restore_counts_a_failure_streak_once_and_ignores_other_workflows():
    from src.domain import Deployment
    from src.dora import restore_times

    def run(hour, status, name):
        return Deployment(f"{name}{hour}", datetime(2026, 9, 1, hour), "c", status, name=name)

    runs = [run(1, "failure", "deploy"), run(2, "failure", "deploy"), run(3, "success", "lint"),
            run(5, "success", "deploy"), run(6, "failure", "lint"), run(8, "success", "lint")]
    durations, still_open = restore_times(runs)
    assert sorted(durations) == [2.0, 4.0] and still_open == 0
