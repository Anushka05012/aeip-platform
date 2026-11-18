# llm-service

Anushka's module — Intelligence, Risk & Analytics Layer (Engine & RAG).

This folder covers the Groq RAG pipeline pieces from the sprint plan:
**Groq client integration** and **chunking logic** for repository code and
documentation (Sept 10 deliverable). Embedding generation, risk scoring,
and the full RAG retriever come next per the sprint roadmap — see
"Where this goes next" below.


## Setup

```bash
cd services/llm-services
python3 -m venv .venv
source .venv/bin/activate     
# Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# then edit .env and paste in a key from https://console groq.com/keys

```

## What's in here

```
llm-services/
├── src/
│   ├── config.py        # loads GROQ_API_KEY, model name, chunk sizes from .env
│   ├── groq_client.py    # thin wrapper around the groq SDK, retries on transient errors
│   └── chunker.py        # splits code/doc files into embedding-ready chunks
├── tests/
│   └── test_chunker.py   # unit tests for chunking (no API key needed)
├── scripts/
│   └── demo_chunk_and_test_groq.py   # run this to see it work end to end
├── requirements.txt
└── .env.example
```

## Live demo: analyze any GitHub repository

1. `python scripts/serve.py` (API on :8001) and `npm run dev` in `frontend/` (UI on :3000).
2. Open **Repositories**, enter `owner/repo` or a GitHub URL, click **Analyze repository**.
   The service fetches commits (with per-file churn and complexity), GitHub Actions
   runs and the source zipball, then chunks, embeds, scores risk and computes DORA.
3. The repository becomes active: Overview, Risk, Failures and the Assistant all use it.

Terminal equivalent: `python scripts/analyze_github.py owner/repo "your question"`.

**Database (PostgreSQL).** Each analysis also asks the ingestion service
(`ingestion/webhook-listener.ts`, port 4000) to store the repository's commits
and pull requests in PostgreSQL through Prisma. Start it from the repo root with
`DATABASE_URL` set: `npx tsx ingestion/webhook-listener.ts`. If it isn't
running, the pipeline log records the step as skipped and analysis continues.
Analyses are cached in `data/cache/`, so they survive restarts and network loss.
Set `GITHUB_TOKEN` in `.env` (anonymous GitHub allows ~1 analysis per hour) and
`GROQ_API_KEY` for LLM-written answers (otherwise answers are extractive).

## CI/CD failure intelligence

On the **Failures** page, **Explain** answers "was this failure caused by its triggering
commit?" (`src/failure_analysis.py`, `POST /api/failures/explain`):

1. Fetch the failed jobs, failed steps, check annotations and (with `GITHUB_TOKEN`) the job log.
2. Redact secrets, extract the error lines, and classify the failure (test, build, lint/type,
   dependency, or infrastructure/flaky).
3. Deterministic correlation: changed files named in the error output, infrastructure
   markers, scheduled triggers, and the risk scores of the changed files.
4. Groq reasons over that evidence plus RAG-retrieved code. Logs and code are passed as
   untrusted data, so instructions inside them are ignored.
5. Verdict (related / unrelated / uncertain) with a confidence. When the rules and the LLM
   disagree, confidence is capped, and anything under 0.6 is flagged for human review.
   Next steps are suggestions only; nothing is executed.

## Operational events: deploys, app logs, databases, alerts

AEIP lines up events from the rest of your tooling with commits and CI runs
(`src/events.py`). Every source becomes one event shape (`source`, `kind`, `time`, `title`,
`severity`, `service`, `environment`, `commit`, `files`, ...). Text is secret-redacted, repeated
errors share a `fingerprint`, and file paths in stack traces are extracted so they can be
matched to the commits that changed them.

| Endpoint | Accepts |
|---|---|
| `POST /api/events?repository=owner/name` | generic event, list, or `{"events": [...]}` |
| `POST /api/events/logs?repository=...&source=app\|database&service=...` | raw text or JSON-lines logs (stack traces grouped; Postgres deadlocks, connection exhaustion, slow queries, lock timeouts and migrations recognised) |
| `POST /api/events/vercel` · `/render` · `/sentry` · `/github` · `/alertmanager` | the webhook payloads those tools already send |
| `GET /api/events?repository=...&source=...` | stored events and counts per source |

Set `AEIP_INGEST_KEY` to require a key on the ingest routes (`X-AEIP-Key` header, `Bearer`
token, or `?key=` for webhook senders that cannot set headers). Events are stored in
`data/cache/events/`. To send a file by hand:

```bash
python scripts/send_events.py --repository acme/shop --logs app.log --source app --service api
python scripts/send_events.py --repository acme/shop --events alert.json --format alertmanager
```

The demo repository ships with two incidents' worth of events (`data/demo_events.json`).

## Run it locally

Run the tests (fast, no API key required):

```bash
python -m pytest tests/ -v
```

Run the complete local DORA -> risk -> RAG demo. It needs no API key,
database, or team integration:

```bash
python scripts/demo_intelligence_flow.py
```

Add `--ai` to generate the final risk summary with Groq rather than the
built-in evidence-grounded fallback:

```bash
python scripts/demo_intelligence_flow.py --ai
```

Start the local API used by the Next.js dashboard (no Groq key is required for
the default offline/evidence-grounded mode):

```bash
python scripts/serve.py
```

In a second terminal, start the frontend:

```bash
cd ../../frontend
npm install
npm run dev
```

Open `http://localhost:3000`. The overview, risk, failures, repository page,
and assistant now consume `http://localhost:8001`. Set
`NEXT_PUBLIC_INTELLIGENCE_API_URL` if the service runs elsewhere. The assistant
uses the deterministic offline summary by default; Groq remains an optional
server-side enhancement for a later authenticated control.

Ask a repository question and see the exact RAG sources used:

```bash
python scripts/ask_repository.py "What should we test before payment deployment?"
```

For a Groq-written answer strictly grounded in those retrieved sources:

```bash
python scripts/ask_repository.py --ai "Why is payment_service risky?"
```

The pipeline uses `JsonSeedDataSource` and `data/demo_repository.json` now.
When ingestion is ready, implement the `AnalyticsDataSource` contract in
`src/domain.py` as a Supabase adapter and pass its `RepositorySnapshot` to the
same pipeline. The risk, DORA, embedding, retrieval, and summary code stay the
same.

## How the chunker works

- `CodeChunker` and `MarkdownChunker` both do **recursive splitting**: try
  the "nicest" boundary first (class/function for code, headers for docs),
  fall back to paragraphs, then lines, then a hard token-window split if a
  section still won't fit.
- Adjacent chunks are packed together up to `CHUNK_MAX_TOKENS`, and a small
  `CHUNK_OVERLAP_TOKENS` window is carried from one chunk into the next so
  retrieval doesn't lose context right at a boundary.
- `chunk_file(path)` — chunk one file.
- `chunk_repository(root_dir)` — walk a directory and chunk every code/doc
  file it finds (this is what the ingestion pipeline will call once a repo
  is pulled down locally).
- Token counts are approximate (used only to size chunks consistently, not
  to match Llama's exact tokenizer).

## How the Groq client works

`GroqClient.chat(messages, ...)` wraps `groq.Groq().chat.completions.create`
with automatic retry (exponential backoff, 4 attempts) for rate limits and
transient network errors. `GroqClient.ping()` is a one-line credentials/
connectivity check.

```python
from src.config import Settings
from src.groq_client import GroqClient

client = GroqClient(Settings.load())
reply = client.chat([{"role": "user", "content": "Say hi in 5 words."}])
print(reply)
```

**Model name note:** `.env.example` defaults to `openai/gpt-oss-120b`.
Groq's available model IDs change fairly often — double check
https://console.groq.com/docs/models before the demo/review if things
look off.

## Where this goes next (per the sprint plan)

- **Sept 11** — embedding generation worker: take `Chunk` objects from this
  module, embed them, and write them into Supabase pgvector (depends on
  Snehal's DB schema).
- **Sept 12** — deterministic risk scoring (churn, file-change frequency,
  complexity) — independent of this module, same layer.
- **Sept 14** — RAG retrieval pipeline: similarity search over pgvector
  with hybrid re-ranking, built on top of the embeddings above.
- **Sept 15** — merge deterministic risk scores with LLM reasoning
  (`GroqClient.chat`) into evidence-grounded risk summaries.

## Branching

Per the plan's convention, push this on `feature/rag-engine-anushka` and
open a PR — no direct pushes to `main`.
