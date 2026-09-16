"""Evidence-grounded risk summaries, with an offline-safe demo fallback."""

from __future__ import annotations

from typing import Protocol, Sequence

from .rag import RetrievedEvidence
from .risk_engine import RiskResult


class ChatClient(Protocol):
    def chat(self, messages: list[dict[str, str]], **kwargs: object) -> str: ...


class RiskSummaryEngine:
    def summarize(self, risk: RiskResult, evidence: Sequence[RetrievedEvidence], client: ChatClient | None = None) -> str:
        sources = ", ".join(item.path for item in evidence) or "no retrieved repository evidence"
        deterministic = (
            f"{risk.path} is {risk.level} risk ({risk.score}/100): "
            f"{'; '.join(risk.reasons)}. Review and test this area before the next deployment. "
            f"Evidence: {sources}."
        )
        if client is None:
            return deterministic
        prompt = (
            "Write a concise engineering risk summary. Use only the supplied calculated facts and "
            "repository evidence; do not invent failures or code details. Include one practical action.\n\n"
            f"CALCULATED RISK:\n{deterministic}\n\n"
            "RETRIEVED EVIDENCE:\n" + "\n\n".join(
                f"[{item.path}]\n{item.content[:900]}" for item in evidence
            )
        )
        return client.chat([
            {"role": "system", "content": "You are a precise software-engineering risk analyst."},
            {"role": "user", "content": prompt},
        ], temperature=0.1, max_tokens=280)
