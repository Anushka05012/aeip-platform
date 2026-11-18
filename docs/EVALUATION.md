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
| Does a per-repository learned model rank risky files better? (8 real repositories) | with 50+ labels: AUC 0.737, worse than fixed by > 0.02 on 14 of 58 dates | fixed weights 0.647; change count 0.677 |
| Does AEIP show why a real CI build failed? (347 held-out logs, public LogChunks labels) | failure reason found in 83.6%, line recall 0.615 | before: 72.6%; last 40 lines: 62.0% |

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

## 5. Real CI logs: does AEIP show why the build failed? (public dataset)

LogChunks (Brandt et al., MSR 2020, CC-BY 4.0): 797 real Travis CI logs from 80 repositories in 29 languages. The authors labelled
the part of each log that says why the build failed and validated a sample with the developers who broke
the build. Every method gets the same budget of 40 lines, which is also what AEIP passes to the LLM.

- *failure reason found*: at least one labelled line is shown
- *line recall*: share of the labelled lines shown
- *whole reason shown*: every labelled line is shown

The repositories are split in half by a fixed hash of their name. The extractor was improved by studying the
development half only; the held-out half was scored once, afterwards.

| Split | Method | logs | failure reason found | line recall | whole reason shown | lines shown |
|---|---|---|---|---|---|---|
| held-out | AEIP (failing-step anchored) | 347 | 83.6% | 0.615 | 44.1% | 25.9 |
| held-out | AEIP before this benchmark | 347 | 72.6% | 0.466 | 27.4% | 34.6 |
| held-out | Last 40 lines of the log | 347 | 62.0% | 0.516 | 39.5% | 40 |
| development | AEIP (failing-step anchored) | 450 | 78.0% | 0.597 | 42.0% | 27.3 |
| development | AEIP before this benchmark | 450 | 70.0% | 0.423 | 26.2% | 36.4 |
| development | Last 40 lines of the log | 450 | 59.1% | 0.486 | 38.2% | 40 |

**What the benchmark changed.** The previous extractor kept the last 40 error-looking lines of the whole log.
On real logs those are often printed *after* the failure by cleanup, cache or artifact-upload hooks ("failed
to upload ... no such file"), which pushed the real cause out. AEIP now finds the step whose command failed
("The command ... exited with 1", "Process completed with exit code 1", "Job failed: exit code 1"),
searches only that step, keeps the errors nearest the failure with three lines of context for stack traces,
and recognises failure wording without the word "error" (linter rule ids, Elixir throws, exceeded limits,
TAP `not ok`). The verdict benchmark (section 1) is unchanged by this.

Limits: Travis CI logs (the dataset was collected in 2019, before GitHub Actions); the labels mark where the reason is, not whether the commit caused it.

## 6. Learning risk from the repository's own history

`src/learned_risk.py` fits a logistic regression per repository on the fixed score's signals plus past bug
fixes and past confirmed incidents. It is anchored on the fixed score (unpenalised input; every other weight
is pulled towards zero, L2 = 20), so with few labels it ranks like the fixed score. At each past date T,
every 60 days, it is trained only on earlier dates whose 90-day outcome was known by T, then ranks the files changed
in the 90 days before T; a file counts as buggy if a bug-fix commit touches it in the 90 days after T (the
public repositories have no incident history, so only bug-fix labels are used here). *Riskiest 20%*
is the share of buggy files caught when only the riskiest fifth of files is reviewed, the gating metric of
Meta's Diff Risk Score paper.

| Repository | dates | learned AUC | fixed AUC | change-count AUC | first design (unanchored) AUC | riskiest 20%: learned | riskiest 20%: fixed |
|---|---|---|---|---|---|---|---|
| click | 23 | 0.602 | 0.610 | 0.661 | 0.632 | 24.2% | 36.0% |
| black | 32 | 0.770 | 0.663 | 0.745 | 0.774 | 42.3% | 39.1% |
| flask | 19 | 0.636 | 0.603 | 0.596 | 0.638 | 27.4% | 22.1% |
| requests | 4 | 0.776 | 0.765 | 0.749 | 0.703 | 62.5% | 62.5% |
| httpx | 17 | 0.636 | 0.687 | 0.658 | 0.618 | 25.7% | 33.6% |
| jinja (held out) | 8 | 0.463 | 0.545 | 0.523 | 0.460 | 18.3% | 23.7% |
| starlette (held out) | 17 | 0.567 | 0.463 | 0.549 | 0.551 | 33.1% | 16.4% |
| rich (held out) | 28 | 0.720 | 0.655 | 0.658 | 0.729 | 44.0% | 32.6% |

Pooled over all repositories and dates, by how many labelled (later-fixed) files the model had to learn from:

| Labels available | dates | learned AUC | fixed AUC | change-count AUC | dates where learned is worse than fixed by > 0.02 |
|---|---|---|---|---|---|
| 10-49 | 90 | 0.614 | 0.605 | 0.636 | 33 |
| 50+ | 58 | 0.737 | 0.647 | 0.677 | 14 |

**Reading.** The result is mixed and is reported as such. The first design (no anchor, weak L2) was scored on
click, black, flask, requests and httpx: it beat the fixed weights on three and lost on two, almost always when
it had fewer than 50 labels. The anchor was added after that and checked once on three repositories not used
before (jinja, starlette, rich). With fewer than 50 labels the learned model is not reliably better than the
fixed score. With 50 or more it averages AUC 0.737 against 0.647 (fixed) and 0.677 (change count),
though it is still worse than the fixed score on 14 of 58 individual dates. AEIP therefore
uses it only from 50 labelled files (`USE_FROM_POSITIVES`) and otherwise shows the fixed
score with "learning: N of 50". That threshold was read off this table, so it is a finding of this
evaluation, not an independent test. Simple change counts remain a strong baseline, as in the defect-prediction
literature.

In production the labels also include changes that engineers confirm as an incident's cause (`feedback.py`),
which public repositories do not have; that part is tested in `tests/test_learned_risk.py`, not measured here.

## Not yet measured

- Verdict accuracy (related / unrelated to the commit) on labelled failures from real team pipelines. Public data
  labels *where* the failure reason is (section 5) or its category, not whether the commit caused it.
- Time saved compared with switching between GitHub, CI, deploy, log and database tools (needs a user study).
