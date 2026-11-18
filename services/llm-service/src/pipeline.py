"""One orchestration entry point for the teacher demo and a future API endpoint."""

from __future__ import annotations

from datetime import datetime

from .dora import DoraMetrics, calculate_dora
from .embeddings import EmbeddingWorker, make_embedder
from .vector_store import make_vector_store
from .rag import RepositoryRetriever, RetrievedEvidence
from .risk_engine import RiskEngine, RiskResult
from .risk_summary import ChatClient, RiskSummaryEngine
from .domain import RepositorySnapshot


class IntelligencePipeline:
    def __init__(self, repository: str = "", embedder: object | None = None, embedder_note: str = "") -> None:
        if embedder is None:
            embedder, embedder_note = make_embedder()
        self.embedder = embedder
        model = getattr(embedder, "name", "hashing")
        self.store, store_note = make_vector_store(repository or "local", model, getattr(embedder, "dimensions", 1024))
        self.index_description = f"{embedder_note or model} · {store_note}"
        self.worker = EmbeddingWorker(self.embedder, self.store)
        self.retriever = RepositoryRetriever(self.embedder, self.store)
        self.risk_engine = RiskEngine()
        self.summary_engine = RiskSummaryEngine()

    def prepare(self, snapshot: RepositorySnapshot) -> int:
        return self.worker.index(snapshot.documents)

    def analyze(
        self, snapshot: RepositorySnapshot, path: str, question: str, now: datetime,
        start: datetime, chat_client: ChatClient | None = None,
    ) -> tuple[DoraMetrics, RiskResult, list[RetrievedEvidence], str]:
        risks = self.risk_engine.score_files(snapshot, now)
        risk = next((item for item in risks if item.path == path), None)
        if risk is None:
            raise ValueError(f"No recent risk data for {path}")
        evidence = self.retriever.retrieve(question)
        summary = self.summary_engine.summarize(risk, evidence, chat_client)
        return calculate_dora(snapshot, start, now), risk, evidence, summary
