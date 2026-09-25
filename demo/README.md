# Demo repository: PayFlow

`build_demo_repo.py` creates **PayFlow**, a small payments service whose history is scripted
so every AEIP feature has something real to show: commits, CI/CD runs on GitHub Actions,
pull requests, failures with known causes, a risky hotspot file, and docs for RAG.

| Step | What happens in CI | What AEIP should show |
|---|---|---|
| c1–c3 | green | DORA deployments, commit history |
| c4 `refactor: extract retry loop…` | tests fail with `KeyError` raised in `service.py` | **Caused by the change**; `service.py` in error output |
| c5 fix | green | lead time for a fix |
| c6 `chore: deploy to the new container registry` | deploy fails: registry DNS | **Caused by the change**: a network error, but right after a config change (misconfiguration) |
| c7–c11 | green | risk scoring (`service.py` changed most) |
| c12 `docs: add on-call notes…` (docs only) | sandbox smoke test times out (simulated outage, stated in the test's docstring) | **Not caused by the change** (infrastructure) |
| c13 | green | recovery |
| PR *Support partial refunds* (open) | tests fail in `refunds.py` | failure **linked to the pull request** |
| PR *Reject dashboard tokens right after expiry* | green, merged | merged PR, merge commit deploy |
| PR *Format amounts with currency symbols* (open) | green | open PR |

## 1. Build locally (tests every step)

```powershell
python demo/build_demo_repo.py build C:\Users\<you>\Desktop\payflow-demo
```

The script runs the test suite and deploy step at every commit and stops if any outcome
differs from the plan.

## 2. Publish to GitHub

Either create a **classic personal access token** with scopes **`repo`** and **`workflow`**
(the script then creates the repository itself), or create an **empty** public repository
on github.com (no README) and use a **fine-grained token** that can access it with
*Contents*, *Workflows* and *Pull requests* set to **Read and write**. Then:

```powershell
$env:GITHUB_TOKEN = "<token>"
python demo/build_demo_repo.py publish C:\Users\<you>\Desktop\payflow-demo payflow-demo
```

It creates a public repository on your account, pushes each commit separately (so each
gets its own CI run), opens the three pull requests and merges one. The token is passed
per command and never stored in the repository.

## 3. Analyse it in AEIP

Wait about 5 minutes for GitHub Actions to finish, put the same token in
`services/llm-service/.env` as `GITHUB_TOKEN` (so AEIP can read full CI logs), then
analyse `<your-username>/payflow-demo` on the Repositories page.

Note: all CI runs happen on the day you publish, so the "CI runs per day" chart shows
one tall bar. Publishing a few days before the review, then pushing a small change each
day, spreads it out.
