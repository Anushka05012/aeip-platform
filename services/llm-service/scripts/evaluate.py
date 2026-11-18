"""Reproduce AEIP's evaluation and write data/evaluation/results.json + docs/EVALUATION.md.

    python scripts/evaluate.py --repos <dir>          # <dir> holds git clones of pallets/click and psf/black
    python scripts/evaluate.py                        # only the benchmarks that need no clones

Get the clones (read-only; nothing in them is executed):
    git clone https://github.com/pallets/click.git <dir>/click
    git clone https://github.com/psf/black.git <dir>/black
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.embeddings import EmbeddingCache, HashingEmbedder  # noqa: E402
from src.evaluation import (evaluate_incidents, evaluate_retrieval, evaluate_risk_history,  # noqa: E402
                            evaluate_verdicts, git_documents, load_json)

DATA = ROOT / "data" / "evaluation"
REPORT = ROOT.parents[1] / "docs" / "EVALUATION.md"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repos", type=Path, help="folder with clones of pallets/click and psf/black")
    parser.add_argument("--incidents", type=int, default=300)
    parser.add_argument("--skip-semantic", action="store_true", help="skip the semantic-model retrieval run")
    args = parser.parse_args()
    results: dict = {"date": date.today().isoformat()}

    started = time.perf_counter()
    results["verdicts"] = evaluate_verdicts(load_json(DATA / "failure_verdicts.json")["cases"])
    results["incidents"] = evaluate_incidents(args.incidents)
    print(f"verdicts + incidents in {time.perf_counter() - started:.1f}s")

    if args.repos:
        click = args.repos / "click"
        spec = load_json(DATA / "retrieval_click.json")
        documents = git_documents(click, spec["ref"], "")
        retrieval = {"files": len({item.path for item in documents}), "chunks": len(documents),
                     "hashing": evaluate_retrieval(documents, spec["questions"], HashingEmbedder())}
        if not args.skip_semantic:
            try:
                from src.embeddings import SemanticEmbedder
                embedder = SemanticEmbedder(cache=EmbeddingCache(ROOT / "data" / "cache" / "embeddings.sqlite"))
                retrieval["semantic"] = evaluate_retrieval(documents, spec["questions"], embedder)
            except Exception as exc:
                print(f"semantic retrieval skipped: {exc}")
        results["retrieval"] = retrieval
        results["risk"] = {name: evaluate_risk_history(args.repos / name, cutoffs=16, every_days=120)
                           for name in ("click", "black") if (args.repos / name).exists()}
        print(f"all benchmarks in {time.perf_counter() - started:.1f}s")

    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / "results.json").write_text(json.dumps(results, indent=1), encoding="utf-8")
    REPORT.write_text(render(results), encoding="utf-8")
    print(f"wrote {DATA / 'results.json'} and {REPORT}")
    return 0


def pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def render(results: dict) -> str:
    verdicts, incidents = results["verdicts"], results["incidents"]
    overall = incidents["overall"]
    lines = [
        "# AEIP evaluation",
        "",
        f"Measured {results['date']} with `services/llm-service/scripts/evaluate.py`; raw numbers in",
        "`services/llm-service/data/evaluation/results.json`. Every run is deterministic (fixed data and seeds).",
        "",
        "## Summary",
        "",
        "| Question | Result | Compared with |",
        "|---|---|---|",
        f"| Is a CI failure caused by its commit? ({verdicts['cases']} labelled failures) | accuracy {pct(verdicts['accuracy'])}, "
        f"macro-F1 {verdicts['macroF1']:.3f}, {len(verdicts['harmfulFlips'])} harmful flips | before the fixes below: 89.7%, 1 harmful flip |",
        f"| Which change caused this incident? ({overall['n']} generated incidents) | top-1 {pct(overall['top1'])}, "
        f"top-3 {pct(overall['top3'])} | \"most recent change\" heuristic: top-1 {pct(overall['baselineTop1'])} |",
    ]
    if "retrieval" in results:
        retrieval = results["retrieval"]
        best = retrieval.get("semantic", retrieval["hashing"])
        lines.append(f"| Can ask-the-codebase find the implementing file? (25 questions, {retrieval['files']} files) | "
                     f"Hit@5 {pct(best['hit@5'])}, MRR {best['mrr']:.3f} (semantic) | hashing Hit@5 "
                     f"{pct(retrieval['hashing']['hit@5'])}; random ≈7% |")
    if results.get("risk"):
        parts = [f"{name}: AUC {item['meanAucRisk']:.3f}, P@3 {pct(item['meanPrecision@3'])}" for name, item in results["risk"].items()]
        bases = [f"{name}: change count AUC {item['meanAucChangeCountOnly']:.3f}, base rate {pct(item['meanBaseRate'])}"
                 for name, item in results["risk"].items()]
        lines.append(f"| Does risk predict later bug fixes? (real history) | {'; '.join(parts)} | random AUC 0.5; {'; '.join(bases)} |")

    lines += [
        "",
        "## 1. CI failure verdicts",
        "",
        "Data: `data/evaluation/failure_verdicts.json`. Four cases reproduce the PayFlow demo repository's scripted",
        "failures; the rest are written from common real CI failure patterns (pytest, Jest, tsc, ESLint, Go, Java, Rust,",
        "mypy, npm/pip network errors, rate limits, lost runners, full disks, scheduled runs, flaky reruns, dependency",
        "bumps, Dockerfile and workflow changes). Labels were written before the analyser ran. Rule-based mode only",
        "(no LLM), so the numbers are reproducible.",
        "",
        "| | precision | recall | F1 | cases |",
        "|---|---|---|---|---|",
    ]
    for label, item in verdicts["perClass"].items():
        lines.append(f"| {label} | {item['precision']:.3f} | {item['recall']:.3f} | {item['f1']:.3f} | {item['support']} |")
    wrong = [row for row in verdicts["rows"] if not row["correct"]]
    lines += [
        "",
        "A *harmful flip* is calling a failure caused by the change when it was not, or the reverse; an",
        "\"uncertain\" answer is a safe miss because it is sent for human review.",
        "",
        "**What the benchmark changed.** The first run scored 89.7% with one harmful flip and found two real gaps,",
        "both fixed: a commit that only changed `requirements.txt` was treated as documentation-only (so the",
        "dependency failure it caused was called unrelated), and \"connection refused\" in plain words was not",
        "recognised as an infrastructure error. Because those fixes were found on this same set, the after-fix",
        "number is optimistic; a held-out set of real labelled failures is the next step.",
        "",
        "Remaining disagreements: " + ("; ".join(f"`{row['id']}` (expected {row['expected']}, got {row['predicted']})" for row in wrong) or "none") + ".",
        "",
        "## 2. Incident root cause",
        "",
        f"{overall['n']} incidents are generated with a fixed seed (`generate_scenario` in `src/evaluation.py`). Each has a",
        "day of deploys across three services (1-3 commits each), exactly one breaking change (a deploy 70%, a database",
        "migration 15%, a feature-flag change 15%), 5-30 errors that share 1-3 stack-trace variants, an optional decoy",
        "deploy between the cause and the first error (40%), and an optional rollback (50% of deploy causes). For deploy",
        "causes, 70% of incidents have stack traces that name the changed file.",
        "The baseline is what engineers do by default: blame the most recent change before the first error.",
        "",
        "| Slice | n | top-1 | top-3 | MRR | baseline top-1 |",
        "|---|---|---|---|---|---|",
    ]
    slices = [("All incidents", overall)] + [(f"Cause: {kind}", item) for kind, item in incidents["byCause"].items()] + [
        ("Deploy, stack trace names the file", incidents["deployWithStackTrace"]),
        ("Deploy, no file in stack trace", incidents["deployWithoutStackTrace"]),
        ("Decoy deploy between cause and errors", incidents["decoyBetweenCauseAndErrors"])]
    for name, item in slices:
        lines.append(f"| {name} | {item['n']} | {pct(item['top1'])} | {pct(item['top3'])} | {item['mrr']:.3f} | {pct(item['baselineTop1'])} |")
    lines += [
        "",
        "**What the benchmark changed.** The first version scored feature-flag causes at 26.5% top-1, below the",
        "baseline: file overlap counted any changed file seen in any stack trace, so a decoy deploy touching a file",
        "that appeared once in passing outscored the real cause. Overlap is now weighted by the share of error traces",
        "that contain the file. The generator was made more realistic at the same time (repeats of an error share a",
        "stack trace instead of drawing random frames).",
        "",
        "Limits: the incidents are synthetic. They test the ranking logic against controlled decoys, not the messiness",
        "of real production telemetry; the two demo incidents (`data/demo_events.json`) are the end-to-end check.",
    ]
    if "retrieval" in results:
        retrieval = results["retrieval"]
        lines += [
            "",
            "## 3. Ask the codebase: retrieval",
            "",
            f"The real `pallets/click` repository at tag 8.1.7: {retrieval['files']} files ({retrieval['chunks']} chunks)",
            "including tests, docs and examples, indexed exactly as AEIP indexes a repository. 25 developer questions",
            "(`data/evaluation/retrieval_click.json`) each list the source files that implement the answer, checked",
            "with `git grep`. A question counts as found when one of those files is in the top 5 distinct files.",
            "",
            "| Embeddings | Hit@5 | Recall@5 | Hit@1 | MRR |",
            "|---|---|---|---|---|",
        ]
        for name in ("hashing", "semantic"):
            if name in retrieval:
                item = retrieval[name]
                label = "Semantic: bge-small-en-v1.5, local" if name == "semantic" else "Hashing (keyword vectors)"
                lines.append(f"| {label} | {pct(item['hit@5'])} | {pct(item['recall@5'])} | {pct(item['hit@1'])} | {item['mrr']:.3f} |")
        lines += [
            "| Random files | ≈7% | | | |",
            "",
            "Most remaining misses rank the matching documentation page first (for example `docs/testing.rst` for",
            "\"how do I test a command\"). That is often a useful answer, but the labels count only implementing code.",
        ]
    if results.get("risk"):
        lines += [
            "",
            "## 4. Change risk vs later bug fixes (real history)",
            "",
            "At up to 16 past dates, 120 days apart, each repository's files are scored from the previous 90 days of",
            "commits only. A file is *buggy* if a bug-fix commit (subject matches fix/bug/regression/revert/crash,",
            "excluding docs/typo/CI/test-only messages) touches it in the next 90 days. Scored with ROC AUC (0.5 = random)",
            "and precision of the top 3 files. Complexity growth is not available from `git log --numstat`, so that",
            "signal is zero here.",
            "",
            "| Repository | dates | AEIP risk AUC | churn-only AUC | change-count AUC | AEIP P@3 | churn-only P@3 | base rate |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for name, item in results["risk"].items():
            lines.append(f"| {name} | {item['cutoffsUsed']} | {item['meanAucRisk']:.3f} | {item['meanAucChurnOnly']:.3f} | "
                         f"{item['meanAucChangeCountOnly']:.3f} | {pct(item['meanPrecision@3'])} | "
                         f"{pct(item['meanPrecision@3ChurnOnly'])} | {pct(item['meanBaseRate'])} |")
        lines += [
            "",
            "Reading: the risk score ranks future bug-fix files above the rest more often than chance and puts more",
            "of them in its top 3 than churn alone, but on these two repositories the number of recent changes on its",
            "own ranks slightly better by AUC. Measured per signal, change frequency was the strongest predictor on",
            "both repositories (consistent with Graves et al., 2000), blast radius and churn helped a little, test gap",
            "was inconsistent, and dependency updates carried no signal. Re-weighting toward frequency helped one",
            "repository and hurt the other, so the weights were left unchanged; learning them from many more",
            "repositories is future work.",
        ]
    lines += [
        "",
        "## Not yet measured",
        "",
        "- Verdict accuracy on ~100 labelled failures from real team pipelines (needs labelled production data).",
        "- Time saved compared with switching between GitHub, CI, deploy, log and database tools (needs a user study).",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
