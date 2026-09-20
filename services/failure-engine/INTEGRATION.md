# Failure Engine Integration Handoff

**Date:** 2026-09-20  
**Owner:** Neeraj  
**Branch:** `feature/failure-engine-neeraj`  
**Current commit:** `3913acf` (`feat: add failure intelligence engine MVP`)

## Purpose

This document explains how to integrate the standalone Failure Intelligence Engine into the current AEIP `main` branch without mixing its Python code with the TypeScript ingestion, Prisma, or frontend code.

The Failure Engine is currently a separate Python FastAPI service. It accepts a CI/CD log and returns a structured failure analysis.

## Current Service Flow

```text
CI/CD log
    -> secret redaction
    -> evidence extraction
    -> deterministic classification
    -> root-cause and fix response
    -> JSON API response
```

The service does not currently call Groq, write to PostgreSQL, or fetch logs from GitHub directly.

## What This Branch Adds

Keep the complete service under:

```text
services/failure-engine/
```

Important files:

- `src/main.py`: FastAPI application and API routes.
- `src/redactor.py`: removes common secrets from logs.
- `src/parser.py`: cleans logs and extracts evidence lines.
- `src/classifier.py`: deterministic failure categories and severity.
- `src/analyzer.py`: root cause, suggested fix, confidence, and metadata response.
- `src/providers.py`: provider interface and local sample provider.
- `samples/`: test log fixtures.
- `tests/`: automated tests.
- `requirements.txt`: Python dependencies.

Do not move these files into `ingestion/`, `backend-api/`, or `frontend/`. The service should remain independently runnable and deployable.

## API Contract

### Health

```http
GET /health
```

Response:

```json
{
  "status": "ok"
}
```

### Analyze a log

```http
POST /analyze
Content-Type: application/json
```

Request fields:

```json
{
  "provider": "github",
  "repository": "owner/repository",
  "branch": "main",
  "commit": "abc123",
  "runId": "987",
  "log": "actual CI/CD log text"
}
```

Only `log` is required. The other fields are optional metadata and should be supplied when the source system has them.

Response fields:

```json
{
  "category": "DEPENDENCY_ERROR",
  "severity": "HIGH",
  "rootCause": "Incompatible or unresolved dependency versions caused the build to fail.",
  "evidence": [
    "npm ERR! code ERESOLVE"
  ],
  "suggestedFix": "Review package versions and update the dependency constraints.",
  "confidence": 0.85,
  "metadata": {
    "provider": "github",
    "repository": "owner/repository",
    "branch": "main",
    "commit": "abc123",
    "runId": "987"
  }
}
```

The `metadata` object is returned only when at least one metadata field is supplied.

## How It Fits With Current `main`

The current `main` branch contains TypeScript GitHub ingestion, a Prisma PostgreSQL schema, and a Next.js dashboard. The intended future flow is:

```text
GitHub webhook or GitHub API
        -> ingestion layer
        -> failed Log.rawLog record
        -> Failure Engine POST /analyze
        -> analysis result
        -> database update
        -> frontend failure view
```

The Prisma `Log` model currently contains fields such as:

```text
repositoryId
commitId
pullRequestId
source
status
jobName
rawLog
errorSummary
startedAt
finishedAt
```

The first integration should use `Log.rawLog` as the input to `/analyze`. The returned `category`, `severity`, `rootCause`, `evidence`, `suggestedFix`, and `confidence` should be stored in a dedicated failure-analysis record or added through a reviewed Prisma migration. Do not silently overload `errorSummary` with the complete JSON response unless the team explicitly agrees to that design.

## Recommended Integration Ownership

### Ingestion layer

The TypeScript ingestion code should:

1. Receive or fetch the CI/CD event.
2. Normalize provider fields into the API request fields.
3. Store the raw log and run metadata.
4. Call the Failure Engine with the sanitized request payload.
5. Persist the returned analysis result.

### Failure Engine

This Python service should:

1. Redact secrets.
2. Parse the log.
3. Classify the failure.
4. Generate the deterministic analysis.
5. Return stable JSON.

It should not contain GitHub-specific webhook handling or Prisma database code.

### Frontend

The Next.js dashboard should read analysis results through the backend/API layer. It should not call the Python service directly from browser code in production.

## Running It During Integration

From the repository root:

```powershell
Set-Location services/failure-engine
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn src.main:app --reload
```

The service is then available at:

```text
http://127.0.0.1:8000
```

The TypeScript integration should use the configured service URL rather than hardcoding it in application logic. For local development, an environment variable such as `FAILURE_ENGINE_URL` is recommended.

## Groq Handoff

Anushka's separate RAG work provides a `GroqClient`. The future AI adapter should run after deterministic classification and redaction:

```text
redacted log
    -> deterministic classification
    -> GroqClient with category and evidence
    -> validated AI explanation
```

Do not duplicate Groq SDK setup in this service. Reuse the agreed shared client or call the LLM service through an internal service boundary. The deterministic result must remain available as a fallback when the API key is missing, Groq is unavailable, or the AI response is invalid.

## Merge Safety Checklist

Before opening the pull request:

- Confirm the branch is `feature/failure-engine-neeraj`.
- Run `python -m pytest -q` using the service virtual environment.
- Confirm all Failure Engine files remain under `services/failure-engine/`.
- Do not commit `.venv/`, `__pycache__/`, or `.pytest_cache/`.
- Do not include the root `README.md` project notes in the Failure Engine commit.
- Do not edit teammate-owned ingestion, frontend, or Prisma files in this integration commit.
- Confirm the API request and response contract above.

After merging:

- Add the service URL to the integration environment configuration.
- Add an ingestion-to-Failure-Engine client in the TypeScript layer.
- Add a reviewed persistence model or migration for structured failure analysis.
- Add an integration test using a known failed log.
- Replace frontend mock failure data only after the backend contract is available.

## Current Limitations

This handoff documents integration; it does not claim that integration is already complete. The current service does not yet:

- Fetch logs from GitHub, Bitbucket, GitLab, or Jenkins.
- Receive webhooks.
- Connect to Prisma or PostgreSQL.
- Call Groq in the analysis path.
- Provide authentication or rate limiting.

Those are follow-up integration tasks after the standalone MVP is merged and the team agrees on the service and database contracts.