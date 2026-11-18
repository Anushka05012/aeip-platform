# AEIP: AI Engineering Intelligence Platform

Software engineering analytics and CI/CD failure intelligence. Point AEIP at a GitHub
repository and it pulls the commits, pull requests, CI runs and source code, then shows:

- **Delivery health**: DORA metrics (deployment frequency, lead time, change failure rate, time to restore)
- **Change risk**: which files are most likely to break, and why (churn, complexity, test gaps, blast radius, dependency updates)
- **CI failure explanations**: was a failed build caused by its commit, with evidence and confidence
- **Ask the codebase**: plain-English questions answered from the repository, with sources

## Run it locally

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
| `services/llm-service/` | Python intelligence service: GitHub fetch, RAG, risk, DORA, failure analysis, REST API |
| `frontend/` | Next.js dashboard |
| `ingestion/` | Express service: webhooks and PostgreSQL storage (Prisma) |
| `prisma/` | Database schema and migrations |
| `demo/` | Generator for the PayFlow demo repository |
| `docs/` | Project documents (sprint plan, quality and SDG evidence) |

More detail on the intelligence service: [services/llm-service/README.md](services/llm-service/README.md).
