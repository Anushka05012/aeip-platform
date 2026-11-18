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

## Run it with Docker (one command)

```bash
docker compose up --build
```

Dashboard on http://localhost:3000, with PostgreSQL + pgvector, the intelligence API and the ingestion
service. Keys and sign-in are optional: copy [.env.docker.example](.env.docker.example) to `.env.docker`.
Hosting on Supabase + Render + Vercel: [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

## Run it locally (without Docker)

You need **Python 3.11+**, **Node.js 20+** and **git**.

### 1. Get the code

```bash
git clone https://github.com/SnehalBawanthade/aeip-platform.git
cd aeip-platform
```

### 2. Start the intelligence service (port 8001)

```bash
cd services/llm-service
python -m venv .venv
# Windows:       .venv\Scripts\activate
# macOS / Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # Windows: copy .env.example .env
```

Open `services/llm-service/.env` and fill in:

| Variable | Needed? | Where to get it |
|---|---|---|
| `GROQ_API_KEY` | Recommended: AI-written answers and explanations (without it AEIP uses rule-based mode) | https://console.groq.com/keys |
| `GITHUB_TOKEN` | Recommended: full CI logs and 5,000 GitHub requests/hour instead of 60 | GitHub → Settings → Developer settings → Personal access tokens |

Then start it and leave this terminal running:

```bash
python scripts/serve.py
```

### 3. Start the dashboard (port 3000)

In a second terminal, from the project root:

```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:3000**.

### 4. Try it

1. Go to **Repositories**, enter a GitHub repository (for example `Anushka05012/payflow-demo`) and click **Analyse**.
2. Open **Overview**, **Change risk**, **CI failures** (click **Explain** on a failed run) and **Ask the codebase**.

`Anushka05012/payflow-demo` is a demo repository whose CI history contains known failures;
see [demo/README.md](demo/README.md). The bundled `acme/payments-api` demo data works offline.

### 5. Optional: store data in PostgreSQL (port 4000)

The ingestion service stores commits and pull requests in PostgreSQL (Supabase) through
Prisma. AEIP works without it; the Repositories page then shows the database as unavailable.

From the project root, create a `.env` file containing `DATABASE_URL=<your PostgreSQL URL>`
(plus `GITHUB_TOKEN`, and `GITHUB_WEBHOOK_SECRET` if you use webhooks), then:

```bash
npm install
npx prisma generate
npx tsx ingestion/webhook-listener.ts
```

## Evaluation

Measured results (CI verdicts, incident root cause, retrieval on a real repository, risk vs later bug
fixes on real history) are in [docs/EVALUATION.md](docs/EVALUATION.md). Reproduce them with
`python services/llm-service/scripts/evaluate.py --repos <folder with clones of pallets/click and psf/black>`.

## Run the tests

```bash
cd services/llm-service && python -m pytest tests     # intelligence service
npx tsx --test ingestion/signature.test.ts             # webhook signature checks (from the project root)
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
