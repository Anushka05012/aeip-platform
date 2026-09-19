"""Ask a repository question through the local RAG retriever.

Examples:
    python scripts/ask_repository.py "What should we test before payment deployment?"
    python scripts/ask_repository.py --ai "Why is payment_service risky?"
"""

from __future__ import annotations

import argparse
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
    parser = argparse.ArgumentParser(description="Ask the AEIP repository-aware RAG demo.")
    parser.add_argument("question", help="Question about the repository, code, or deployment risks.")
    parser.add_argument("--ai", action="store_true", help="Use Groq to write the final answer (requires GROQ_API_KEY).")
    args = parser.parse_args()

    snapshot = JsonSeedDataSource(ROOT / "data" / "demo_repository.json").load_snapshot("acme/payments-api")
    pipeline = IntelligencePipeline()
    pipeline.prepare(snapshot)
    evidence = pipeline.retriever.retrieve(args.question)

    print(f"Question: {args.question}\n")
    print("RAG retrieved these repository sources:")
    for item in evidence:
        print(f"\n[{item.path}] (hybrid relevance: {item.score})\n{item.content}")

    if not args.ai:
        print("\nAnswer mode: evidence-only. Add --ai for a Groq-generated answer grounded in these sources.")
        return

    from src.config import Settings
    from src.groq_client import GroqClient

    context = "\n\n".join(f"[{item.path}]\n{item.content}" for item in evidence)
    answer = GroqClient(Settings.load()).chat([
        {"role": "system", "content": "Answer only from the supplied repository context. If it is insufficient, say so."},
        {"role": "user", "content": f"Question: {args.question}\n\nRepository context:\n{context}"},
    ], temperature=0.1, max_tokens=350)
    print(f"\nGrounded AI answer:\n{answer}")


if __name__ == "__main__":
    main()
