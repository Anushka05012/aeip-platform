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
