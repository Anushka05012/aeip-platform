# AEIP: AI Engineering Intelligence Platform

**The problem.** When production breaks, the first question is always *"what changed?"*, and the
answer is spread across five tools: the repository, CI, the deploy platform, application logs and
the database. Engineers switch between dashboards and line up timestamps by hand while the
incident runs, and CI failures that were never caused by the code (flaky tests, outages, rate
limits) still send people digging through their own commits.

**What AEIP does.** It connects those tools and answers with evidence:

- **Incidents across tools**: deploys, app errors, database events and alerts are grouped into
  incidents on one timeline, and every change that went live before it (a deploy and the exact
  commits it shipped, a migration, a flag change) is ranked as the likely cause, with the
  evidence shown. On 300 test incidents it names the right change first 84% of the time, against
  63% for "blame the most recent change" ([evaluation](docs/EVALUATION.md)).
- **CI failure explanations**: was a failed build caused by its commit, or by flakiness or
  infrastructure? A verdict with confidence, evidence and next steps; flaky workflows are detected.
- **Change risk**: which files are most likely to break, and why (change frequency, churn,
  complexity, test gaps, blast radius, dependency updates). AEIP also **learns from what broke
  this repository before**: past bug fixes, and incident causes engineers confirm with one click
  on the Incidents page. Once it has 50 labelled files it ranks with a per-repository model; on
  eight real repositories that model averaged AUC 0.737 against 0.647 for fixed weights
  ([evaluation](docs/EVALUATION.md), section 6).
- **Delivery health**: all four DORA metrics.
- **Ask the codebase**: plain-English questions answered from the code, docs and history, with
  sources, using a local embedding model (code never leaves your infrastructure).

It is explainable by design: every score is a sum of visible signals, the LLM only rewrites
evidence the rules found, and nothing is changed automatically. Sign-in with roles, an audit
log and secret redaction are built in.

Sources it connects: GitHub (commits, PRs, Actions, deployments), Vercel, Render, Sentry,
Prometheus Alertmanager, and any application or database log (plain text or JSON lines).

## Run it on your machine

There are two ways. **Docker** is one command but needs Docker Desktop. **Without Docker** you run
two programs yourself: the intelligence API (Python) and the dashboard (Next.js). Both work on
Windows, macOS and Linux, and **no keys or accounts are needed to start**: AEIP opens with a bundled
demo repository (`acme/payments-api`) that works offline.

### What you need

| Tool | Version | Check with | Get it |
|---|---|---|---|
| git | any recent | `git --version` | https://git-scm.com/downloads |
| Python | 3.11 or newer | `python --version` (macOS/Linux: `python3 --version`) | https://www.python.org/downloads/ (Windows: tick "Add python.exe to PATH") |
| Node.js | 20 or newer (includes npm) | `node --version` | https://nodejs.org/ (LTS) |
| Docker Desktop | only for option A | `docker --version` | https://www.docker.com/products/docker-desktop/ |

Optional keys (add them later; everything works without them):

| Key | What it unlocks | Where to get it |
|---|---|---|
| `GROQ_API_KEY` | AI-written answers, failure explanations and incident summaries (without it AEIP answers with its rule-based mode) | https://console.groq.com/keys (free) |
| `GITHUB_TOKEN` | analysing your own GitHub repositories with full CI logs (5,000 requests/hour instead of 60) | GitHub > Settings > Developer settings > Personal access tokens > Fine-grained token with read-only access to the repositories |

### Get the code

```bash
git clone https://github.com/SnehalBawanthade/aeip-platform.git
cd aeip-platform
git checkout development
```

### Option A: Docker (one command)

```bash
docker compose up --build
```

The first build takes several minutes (it downloads the embedding model into the image). Then open
**http://localhost:3000**. This starts PostgreSQL with pgvector, the intelligence API, the ingestion
service and the dashboard. To add keys, copy [.env.docker.example](.env.docker.example) to `.env.docker`,
fill in the values you want, and run the command again. Stop with `Ctrl+C`; `docker compose down -v`
also deletes the stored data.

If port 3000, 8001 or 4000 is already used on your machine:
`AEIP_WEB_PORT=3100 AEIP_API_PORT=8101 AEIP_INGESTION_PORT=4100 docker compose up --build`
(Windows PowerShell: set each with `$env:AEIP_WEB_PORT="3100"` first).

### Option B: without Docker

You will keep **two terminals** open: one for the API, one for the dashboard.

**Terminal 1: the intelligence API (port 8001)**

macOS / Linux:

```bash
cd services/llm-service
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python scripts/serve.py
```

Windows (PowerShell):

```powershell
cd services\llm-service
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
python scripts\serve.py
```

If PowerShell refuses to run `Activate.ps1`, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once,
or use Command Prompt with `.venv\Scripts\activate.bat`.

It is ready when it prints `AEIP intelligence API listening on http://127.0.0.1:8001`. Leave it running. The first
start downloads the local embedding model (about 65 MB) once; check it with http://127.0.0.1:8001/health.
Your keys go in `services/llm-service/.env` (`GROQ_API_KEY=...`, `GITHUB_TOKEN=...`); restart the API after
editing it.

**Terminal 2: the dashboard (port 3000)**

From the project folder (`aeip-platform`):

```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:3000**. No `.env.local` is needed for local use: the dashboard finds the API on
port 8001 and runs without sign-in (the top bar says "Login off").

### Try it

1. **Overview**, **Incidents**, **Change risk**, **CI failures** and **Ask the codebase** open on the
   bundled demo repository straight away.
2. On **Incidents**, open an incident: the timeline across tools, the ranked suspected changes with their
   evidence, and the "This was the cause" / "Not it" buttons that teach AEIP.
3. With a `GITHUB_TOKEN`, go to **Repositories**, enter a public repository such as `psf/black` or
   `Anushka05012/payflow-demo` (a demo repository with known CI failures, see [demo/README.md](demo/README.md))
   and click **Analyse**. The first analysis takes one to a few minutes: AEIP downloads the code, embeds it
   locally and reads up to five years of history with git to learn the repository's risk. The
   **Change risk** page then shows what it learned and its track record.

### Common problems

| Problem | Fix |
|---|---|
| `python` not found (Windows) | Reinstall Python with "Add python.exe to PATH" ticked, or use `py -3` instead of `python` |
| Dashboard says "The intelligence service is not running" | Terminal 1 must be running `python scripts/serve.py` |
| Port 8001 already in use | Start the API with another port, e.g. `PORT=8011 python scripts/serve.py` (PowerShell: `$env:PORT="8011"` first), and start the dashboard with `INTELLIGENCE_API_URL=http://localhost:8011 npm run dev` (PowerShell: `$env:INTELLIGENCE_API_URL="http://localhost:8011"` first) |
| Port 3000 already in use | `npm run dev -- -p 3100`, then open http://localhost:3100 |
| "GitHub rate limit" when analysing | Add `GITHUB_TOKEN` to `services/llm-service/.env` and restart the API |
| Little memory (under 2 GB free) or no internet for the model download | Add `AEIP_EMBEDDINGS=hashing` to `services/llm-service/.env` (keyword search instead of the semantic model) |
| Change risk says "the history is too short" | Normal for the demo repository; analyse a real repository (needs `git` installed and on PATH) |

### Optional: store data in PostgreSQL (ingestion service, port 4000)

AEIP works without it; the Repositories page then reports the database as not running. To use it you need a
PostgreSQL database (for example a free Supabase project). In the project folder create a file `.env` with
`DATABASE_URL=<your PostgreSQL connection string>` (and `GITHUB_TOKEN`, plus `GITHUB_WEBHOOK_SECRET` if you
connect GitHub webhooks), then:

```bash
npm install
npx prisma migrate deploy
npx tsx ingestion/webhook-listener.ts
```

### Optional: sign-in and hosting

Sign-in with GitHub and roles: see [Sign-in and roles](#sign-in-and-roles) below. Hosting on
Supabase + Render + Vercel, and connecting Vercel, Render, Sentry and Alertmanager: [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

## Evaluation

Measured results are in [docs/EVALUATION.md](docs/EVALUATION.md): CI verdicts, incident root cause, retrieval
on a real repository, failure-reason extraction on the public LogChunks dataset, risk on real history, the
learned per-repository risk model on eight open-source repositories, and calibration. Reproduce them:

```bash
cd services/llm-service
python scripts/evaluate.py                                   # benchmarks that need no downloads
python scripts/evaluate.py --repos <dir> --datasets <dir>    # everything
```

`<dir>` is any folder holding `git clone`s of pallets/click, psf/black, pallets/flask, psf/requests,
encode/httpx, pallets/jinja, encode/starlette and Textualize/rich, and LogChunks unzipped into
`<dir>/logchunks/` (https://zenodo.org/records/3632351). The script's header lists the exact commands.

## Run the tests

```bash
cd services/llm-service && python -m pytest tests     # intelligence service (with the virtual environment active)
npx tsx --test ingestion/signature.test.ts             # webhook signature checks (from the project root, after npm install)
npx tsx --test frontend/src/lib/auth/session.test.ts   # sessions, roles, redirects
```

## Sign-in and roles

Locally AEIP runs open (the top bar says "Login off"). To require sign-in, create a GitHub
OAuth app (callback `http://localhost:3000/api/auth/callback`) and set `GITHUB_CLIENT_ID`,
`GITHUB_CLIENT_SECRET` and `AUTH_SECRET` in `frontend/.env.local`; see
[frontend/.env.example](frontend/.env.example).

| Role | Can |
|---|---|
| viewer | read every dashboard |
| member | also analyse repositories, explain failures, ask the codebase, request AI summaries |
| admin | also send events from the dashboard |

Roles come from `AEIP_ADMINS` / `AEIP_MEMBERS` / `AEIP_VIEWERS` (GitHub logins); anyone else is
refused unless `AEIP_DEFAULT_ROLE` is set. The browser only talks to the dashboard, which checks
the session and forwards calls to the intelligence API with `AEIP_SERVICE_TOKEN`; the API
rejects calls without it and re-checks the role. Actions are recorded in
`services/llm-service/data/cache/audit.jsonl`.

## Project layout

| Folder | What it is |
|---|---|
| `services/llm-service/` | Python intelligence service: GitHub fetch, event ingestion, incidents, failure analysis, risk, DORA, retrieval, evaluation, REST API |
| `frontend/` | Next.js dashboard, GitHub sign-in and the authenticated API proxy |
| `ingestion/` | Express service: webhooks and PostgreSQL storage (Prisma) |
| `prisma/` | Database schema and migrations |
| `demo/` | Generator for the PayFlow demo repository |
| `docs/` | Evaluation, deployment guide, sprint plan, quality and SDG evidence |
| `docker-compose.yml`, `render.yaml` | One-command local stack; Render blueprint |

More detail on the intelligence service: [services/llm-service/README.md](services/llm-service/README.md).
