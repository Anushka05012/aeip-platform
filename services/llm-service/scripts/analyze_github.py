"""Run the full pipeline on a GitHub repository from the terminal.

    python scripts/analyze_github.py SnehalBawanthade/aeip-platform
    python scripts/analyze_github.py https://github.com/owner/repo "Where is authentication handled?"

The result is cached in data/cache, so the dashboard (scripts/serve.py) shows
it immediately after a restart.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.github_source import GitHubError
from src.web_api import IntelligenceDemoService


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    service = IntelligenceDemoService()
    try:
        result = service.analyze_repository(sys.argv[1], refresh=True)
    except (GitHubError, ValueError) as exc:
        raise SystemExit(f"Could not analyze {sys.argv[1]}: {exc}")
    print(f"\n== Pipeline for {result['repository']} ==")
    for stage in result["stages"]:
        print(f"  [{stage['ms']:>6} ms] {stage['stage']}: {stage['detail']}")

    overview = service.overview(result["repository"])
    print("\n== DORA ==")
    for metric in overview["metrics"]:
        print(f"  {metric['label']}: {metric['value']}{metric['unit']}")
    print("\n== Top risky files ==")
    for item in overview["riskItems"][:5]:
        print(f"  {item['score']:>3}/100  {item['file']}  ({item['reason']})")

    question = sys.argv[2] if len(sys.argv) > 2 else "What does this project do and where is the main logic?"
    answer = service.ask(question, use_ai=True, repository=result["repository"])
    print(f"\n== Q: {question}  [{answer['mode']}] ==\n{answer['answer']}")


if __name__ == "__main__":
    main()
