"""Measure AEIP's computational footprint (Environment factor evidence).

    python scripts/measure_environment.py            # offline measurements only
    python scripts/measure_environment.py --llm      # also time live Groq calls

Uses the cached analyses in data/cache (no GitHub calls). Results are printed and
saved to data/measurements/environment_<timestamp>.json.
"""

from __future__ import annotations

import json
import os
import platform
import statistics
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.web_api import IntelligenceDemoService, groq_client_if_configured  # noqa: E402

QUESTIONS = [
    "How are signatures verified?", "Where is the timestamp expiry checked?", "What does this project do?",
    "Which serializer formats are supported?", "Why has CI been failing recently?", "How are keys rotated?",
    "What changed recently?", "How is the salt used when signing?", "Where are exceptions defined?",
    "What should be tested before a release?",
]
ASSUMED_CPU_WATTS = 15.0  # typical laptop CPU package power under load; used only for the energy estimate


class CpuSampler:
    """Samples system-wide CPU utilisation every 0.2 s while a workload runs."""

    def __init__(self):
        self.samples: list[float] = []
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        psutil.cpu_percent(None)
        while not self._stop.wait(0.2):
            self.samples.append(psutil.cpu_percent(None))

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *args):
        self._stop.set()
        self._thread.join()


def mb(value: float) -> float:
    return round(value / 1024 ** 2, 2)


def folder_size(path: Path, skip=("node_modules", ".next", "__pycache__", ".venv", ".git")) -> int:
    total = 0
    for dirpath, dirnames, filenames in os.walk(path):
        dirnames[:] = [name for name in dirnames if name not in skip]
        total += sum((Path(dirpath) / name).stat().st_size for name in filenames)
    return total


def timed(fn, repeat: int = 1) -> tuple[list[float], object]:
    durations, result = [], None
    for _ in range(repeat):
        start = time.perf_counter()
        result = fn()
        durations.append((time.perf_counter() - start) * 1000)
    return durations, result


def summary(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)
    return {"avg_ms": round(statistics.mean(values), 2), "median_ms": round(statistics.median(values), 2), "p95_ms": round(ordered[int(0.95 * (len(ordered) - 1))], 2),
            "min_ms": round(ordered[0], 2), "max_ms": round(ordered[-1], 2), "n": len(values)}


def main() -> None:
    use_llm = "--llm" in sys.argv
    process = psutil.Process()
    results: dict[str, object] = {
        "measured_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "machine": {
            "os": f"{platform.system()} {platform.release()}", "cpu": platform.processor(),
            "physical_cores": psutil.cpu_count(logical=False), "logical_cores": psutil.cpu_count(),
            "ram_total_gb": round(psutil.virtual_memory().total / 1024 ** 3, 1), "python": platform.python_version(),
            "gpu": "not used (no local model)",
        },
    }
    rss_start = process.memory_info().rss
    cpu_start = process.cpu_times()

    (startup_ms,), service = timed(IntelligenceDemoService)
    rss_loaded = process.memory_info().rss
    repos = service.list_repositories()["repositories"]
    target = next((repo["repository"] for repo in repos if repo["source"] != "demo fixture"), "acme/payments-api")
    entry = service._get(target)

    # Re-index the largest repository in isolation to time indexing precisely.
    from src.pipeline import IntelligencePipeline

    index_ms, _ = timed(lambda: IntelligencePipeline().prepare(entry.snapshot), repeat=5)
    risk_ms, _ = timed(lambda: entry.pipeline.risk_engine.score_files(entry.snapshot, entry.now, entry.window_days), repeat=20)

    with CpuSampler() as query_cpu:
        retrieval_ms = [timed(lambda q=q: entry.pipeline.retriever.retrieve(q, limit=6))[0][0] for q in QUESTIONS * 5]
        answer_ms = [timed(lambda q=q: service.ask(q, use_ai=False, repository=target))[0][0] for q in QUESTIONS]
    # Failure explanation needs log text to exercise the full path (the LLM is skipped without it),
    # so time it on a failure that carries its log.
    failure_entry = next((candidate for candidate in (entry, service._get(None))
                          if any(item.status == "failure" and item.log for item in candidate.snapshot.deployments)), None)
    failure = commit = None
    explain_ms = []
    if failure_entry:
        failure = next(item for item in failure_entry.snapshot.deployments if item.status == "failure" and item.log)
        commit = next((item for item in failure_entry.snapshot.commits if item.sha == failure.commit_sha), None)
        explain_ms, _ = timed(lambda: service.failure_analyzer.explain(
            failure, commit, [], failure_entry.risks, failure_entry.pipeline.retriever), repeat=10)

    cpu_end = process.cpu_times()
    results["workload"] = {
        "repository": target, "commits": len(entry.snapshot.commits), "ci_runs": len(entry.snapshot.deployments),
        "indexed_chunks": entry.indexed,
        "recorded_github_fetch_stages": entry.stages,
    }
    results["timings"] = {
        "service_startup_ms": round(startup_ms, 2),
        "index_repository": summary(index_ms),
        "risk_scoring": summary(risk_ms),
        "retrieval_per_query": summary(retrieval_ms),
        "offline_answer_per_query": summary(answer_ms),
        "failure_explanation_offline": summary(explain_ms) if explain_ms else None,
    }

    if use_llm and groq_client_if_configured():
        llm_answer = [timed(lambda q=q: service.ask(q, use_ai=True, repository=target))[0][0] for q in QUESTIONS[:5]]
        llm_explain = []
        if failure:
            client = groq_client_if_configured()
            llm_explain, _ = timed(lambda: service.failure_analyzer.explain(
                failure, commit, [], failure_entry.risks, failure_entry.pipeline.retriever, client), repeat=3)
        results["timings"]["groq_answer_per_query"] = summary(llm_answer)
        if llm_explain:
            results["timings"]["groq_failure_explanation"] = summary(llm_explain)
        results["llm"] = {"provider": "Groq (hosted)", "model": os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")}

    cpu_seconds = (cpu_end.user - cpu_start.user) + (cpu_end.system - cpu_start.system)
    queries = len(retrieval_ms) + len(answer_ms)
    results["resources"] = {
        "process_ram_baseline_mb": mb(rss_start),
        "process_ram_after_loading_repositories_mb": mb(rss_loaded),
        "process_ram_peak_mb": mb(max(rss_loaded, process.memory_info().rss)),
        "system_cpu_during_queries_pct_avg": round(statistics.mean(query_cpu.samples), 1) if query_cpu.samples else None,
        "process_cpu_seconds_total": round(cpu_seconds, 2),
        "gpu_utilisation_pct": 0,
    }
    results["storage"] = {
        "cached_analyses_mb": mb(folder_size(ROOT / "data" / "cache")),
        "cache_per_repository_kb": {
            path.name: round(path.stat().st_size / 1024, 1) for path in (ROOT / "data" / "cache").glob("*.json")
        },
        "intelligence_service_source_mb": mb(folder_size(ROOT)),
        "frontend_source_mb": mb(folder_size(ROOT.parents[1] / "frontend")),
        "local_model_weights_mb": 0,
    }
    energy_wh = cpu_seconds * ASSUMED_CPU_WATTS / 3600
    results["energy_estimate"] = {
        "method": f"process CPU-seconds x {ASSUMED_CPU_WATTS} W assumed CPU power / 3600",
        "local_wh_whole_run": round(energy_wh, 4),
        "local_kwh_per_1000_offline_queries": round(
            (sum(retrieval_ms) + sum(answer_ms)) / 1000 * ASSUMED_CPU_WATTS / 3600 / queries * 1000 / 1000, 5),
        "note": "Local compute only. Energy used by Groq's hosted LLM servers cannot be measured from the client.",
    }

    out_dir = ROOT / "data" / "measurements"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"environment_{datetime.now():%Y%m%d_%H%M%S}.json"
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))
    print(f"\nSaved to {out}")


if __name__ == "__main__":
    main()
