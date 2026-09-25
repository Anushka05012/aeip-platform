# AEIP: AI Engineering Intelligence Platform

Software engineering analytics and CI/CD failure intelligence. Point AEIP at a GitHub
repository and it pulls the commits, pull requests, CI runs and source code, then shows:

- **Delivery health**: DORA metrics (deployment frequency, lead time, change failure rate)
- **Change risk**: which files are most likely to break, and why
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

## Run the tests

```bash
cd services/llm-service && python -m pytest tests     # intelligence service
npx tsx --test ingestion/signature.test.ts             # webhook signature checks (from the project root)
```

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
