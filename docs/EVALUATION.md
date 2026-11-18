# AEIP evaluation

Measured 2026-11-18 with `services/llm-service/scripts/evaluate.py`; raw numbers in
`services/llm-service/data/evaluation/results.json`. Every run is deterministic (fixed data and seeds).

## Summary

| Question | Result | Compared with |
|---|---|---|
| Is a CI failure caused by its commit? (39 labelled failures) | accuracy 97.4%, macro-F1 0.962, 0 harmful flips | before the fixes below: 89.7%, 1 harmful flip |
| Which change caused this incident? (300 generated incidents) | top-1 84.3%, top-3 98.3% | "most recent change" heuristic: top-1 63.0% |
| Can ask-the-codebase find the implementing file? (25 questions, 100 files) | Hit@5 80.0%, MRR 0.544 (semantic) | hashing Hit@5 68.0%; random ≈7% |
| Does risk predict later bug fixes? (real history) | click: AUC 0.628, P@3 40.0%; black: AUC 0.609, P@3 52.1% | random AUC 0.5; click: change count AUC 0.654, base rate 31.7%; black: change count AUC 0.730, base rate 31.2% |

## 1. CI failure verdicts

Data: `data/evaluation/failure_verdicts.json`. Four cases reproduce the PayFlow demo repository's scripted
failures; the rest are written from common real CI failure patterns (pytest, Jest, tsc, ESLint, Go, Java, Rust,
mypy, npm/pip network errors, rate limits, lost runners, full disks, scheduled runs, flaky reruns, dependency
bumps, Dockerfile and workflow changes). Labels were written before the analyser ran. Rule-based mode only
(no LLM), so the numbers are reproducible.

| | precision | recall | F1 | cases |
|---|---|---|---|---|
| related | 0.952 | 1.000 | 0.976 | 20 |
| unrelated | 1.000 | 1.000 | 1.000 | 13 |
| uncertain | 1.000 | 0.833 | 0.909 | 6 |

A *harmful flip* is calling a failure caused by the change when it was not, or the reverse; an
"uncertain" answer is a safe miss because it is sent for human review.

**What the benchmark changed.** The first run scored 89.7% with one harmful flip and found two real gaps,
both fixed: a commit that only changed `requirements.txt` was treated as documentation-only (so the
dependency failure it caused was called unrelated), and "connection refused" in plain words was not
recognised as an infrastructure error. Because those fixes were found on this same set, the after-fix
number is optimistic; a held-out set of real labelled failures is the next step.

Remaining disagreements: `test-fails-unchanged-module` (expected uncertain, got related).

## 2. Incident root cause

300 incidents are generated with a fixed seed (`generate_scenario` in `src/evaluation.py`). Each has a
day of deploys across three services (1-3 commits each), exactly one breaking change (a deploy 70%, a database
migration 15%, a feature-flag change 15%), 5-30 errors that share 1-3 stack-trace variants, an optional decoy
deploy between the cause and the first error (40%), and an optional rollback (50% of deploy causes). For deploy
causes, 70% of incidents have stack traces that name the changed file.
The baseline is what engineers do by default: blame the most recent change before the first error.

| Slice | n | top-1 | top-3 | MRR | baseline top-1 |
|---|---|---|---|---|---|
| All incidents | 300 | 84.3% | 98.3% | 0.910 | 63.0% |
| Cause: deploy | 200 | 82.5% | 98.5% | 0.900 | 60.5% |
| Cause: migration | 42 | 100.0% | 100.0% | 1.000 | 69.0% |
| Cause: config | 58 | 79.3% | 96.6% | 0.879 | 67.2% |
| Deploy, stack trace names the file | 132 | 84.8% | 97.7% | 0.915 | 61.4% |
| Deploy, no file in stack trace | 68 | 77.9% | 100.0% | 0.873 | 58.8% |
| Decoy deploy between cause and errors | 111 | 75.7% | 97.3% | 0.863 | 0.0% |

**What the benchmark changed.** The first version scored feature-flag causes at 26.5% top-1, below the
baseline: file overlap counted any changed file seen in any stack trace, so a decoy deploy touching a file
that appeared once in passing outscored the real cause. Overlap is now weighted by the share of error traces
that contain the file. The generator was made more realistic at the same time (repeats of an error share a
stack trace instead of drawing random frames).

Limits: the incidents are synthetic. They test the ranking logic against controlled decoys, not the messiness
of real production telemetry; the two demo incidents (`data/demo_events.json`) are the end-to-end check.

## 3. Ask the codebase: retrieval

The real `pallets/click` repository at tag 8.1.7: 100 files (491 chunks)
including tests, docs and examples, indexed exactly as AEIP indexes a repository. 25 developer questions
(`data/evaluation/retrieval_click.json`) each list the source files that implement the answer, checked
with `git grep`. A question counts as found when one of those files is in the top 5 distinct files.

| Embeddings | Hit@5 | Recall@5 | Hit@1 | MRR |
|---|---|---|---|---|
| Hashing (keyword vectors) | 68.0% | 60.0% | 36.0% | 0.515 |
| Semantic: bge-small-en-v1.5, local | 80.0% | 70.7% | 36.0% | 0.544 |
| Random files | ≈7% | | | |

Most remaining misses rank the matching documentation page first (for example `docs/testing.rst` for
"how do I test a command"). That is often a useful answer, but the labels count only implementing code.

## 4. Change risk vs later bug fixes (real history)

At up to 16 past dates, 120 days apart, each repository's files are scored from the previous 90 days of
commits only. A file is *buggy* if a bug-fix commit (subject matches fix/bug/regression/revert/crash,
excluding docs/typo/CI/test-only messages) touches it in the next 90 days. Scored with ROC AUC (0.5 = random)
and precision of the top 3 files. Complexity growth is not available from `git log --numstat`, so that
signal is zero here.

| Repository | dates | AEIP risk AUC | churn-only AUC | change-count AUC | AEIP P@3 | churn-only P@3 | base rate |
|---|---|---|---|---|---|---|---|
| click | 10 | 0.628 | 0.604 | 0.654 | 40.0% | 40.0% | 31.7% |
| black | 16 | 0.609 | 0.634 | 0.730 | 52.1% | 41.7% | 31.2% |

Reading: the risk score ranks future bug-fix files above the rest more often than chance and puts more
of them in its top 3 than churn alone, but on these two repositories the number of recent changes on its
own ranks slightly better by AUC. Measured per signal, change frequency was the strongest predictor on
both repositories (consistent with Graves et al., 2000), blast radius and churn helped a little, test gap
was inconsistent, and dependency updates carried no signal. Re-weighting toward frequency helped one
repository and hurt the other, so the weights were left unchanged; learning them from many more
repositories is future work.

## Not yet measured

- Verdict accuracy on ~100 labelled failures from real team pipelines (needs labelled production data).
- Time saved compared with switching between GitHub, CI, deploy, log and database tools (needs a user study).
