# AEIP Failure Intelligence Engine

The Failure Intelligence Engine accepts CI/CD logs, classifies the failure with deterministic rules, and returns structured diagnostic information.

## Current Flow

```text
CI/CD log -> Parser -> Classifier -> Analyzer -> JSON response
```

The current version does not call an LLM. Groq integration can be added later for deeper root-cause analysis.

## Setup

From the repository root:

```powershell
Set-Location services/failure-engine
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

The virtual environment only needs to be created once.

## Run the API

From `services/failure-engine`:

```powershell
.\.venv\Scripts\python.exe -m uvicorn src.main:app --reload
```

The server runs at `http://127.0.0.1:8000`.

Interactive API documentation is available at:

```text
http://127.0.0.1:8000/docs
```

## Endpoints

### Health check

```http
GET /health
```

Response:

```json
{
  "status": "ok"
}
```

### Analyze a failure

```http
POST /analyze
```

Request:

```json
{
  "log": "npm ERR! code ERESOLVE\nnpm ERR! unable to resolve dependency tree"
}
```

Response:

```json
{
  "category": "DEPENDENCY_ERROR",
  "severity": "HIGH",
  "rootCause": "Incompatible or unresolved dependency versions caused the build to fail.",
  "evidence": [
    "npm ERR! code ERESOLVE",
    "npm ERR! unable to resolve dependency tree"
  ],
  "suggestedFix": "Review package versions and update the dependency constraints.",
  "confidence": 0.85
}
```

The endpoint expects a non-empty `log` value.

## Supported Categories

- `DEPENDENCY_ERROR`
- `COMPILATION_ERROR`
- `TEST_FAILURE`
- `LINT_ERROR`
- `TYPE_ERROR`
- `DOCKER_ERROR`
- `ENVIRONMENT_ERROR`
- `UNKNOWN`

## Run Tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

The `samples/` directory contains representative CI/CD logs used by the tests. These are test fixtures; production logs will eventually come from GitHub, Bitbucket, GitLab, Jenkins, or another CI provider through an ingestion connector.

## Provider Boundary

The `src/providers.py` module defines the small interface that a CI/CD connector must provide:

```python
def fetch_log(run_id: str) -> str:
  ...
```

`SampleLogProvider` currently reads a local sample file. A future GitHub, Bitbucket, GitLab, or Jenkins provider can implement the same method by downloading a log through that platform's API. The parser and classifier do not need to know where the log came from.

## Groq Integration Handoff

The current analyzer is deterministic and does not call an LLM. Anushka's RAG branch provides the reusable `GroqClient` in `services/llm-service/src/groq_client.py`. Its main method is:

```python
GroqClient.chat(messages) -> str
```

The future AI adapter should be added after deterministic classification:

```text
raw log -> redaction -> parser -> classifier -> GroqClient -> final response
```

The adapter should send the model the category, severity, matched evidence, and sanitized log context. It should then validate the model response before returning it from `/analyze`.

The integration should reuse Anushka's `Settings` and `GroqClient` rather than duplicate the Groq SDK setup. It requires the `GROQ_API_KEY` environment variable and the dependencies listed by the LLM service. Credentials must remain in environment variables or deployment secrets, never in source files.

Until this adapter is implemented, the deterministic analyzer remains the fallback. If the key is missing, Groq times out, or the response is invalid, `/analyze` should still return the current rule-based root cause and suggested fix. Actual Groq integration is therefore a follow-up implementation task, not part of the current deterministic MVP.

## Plain-English Summary

This folder contains Neeraj's part of the AEIP project: the Failure Intelligence Engine.

In simple terms, this service reads a failed build or deployment log and explains what probably went wrong. For example, if a log says that npm could not resolve package versions, the service identifies it as a dependency error and suggests checking the package versions.

The service works like this:

1. A log is sent to the `POST /analyze` API.
2. The redactor removes common passwords, tokens, and keys so they are not exposed.
3. The parser cleans the log and selects useful error lines as evidence.
4. The classifier checks known patterns and assigns a failure category.
5. The analyzer creates a severity, explanation, suggested fix, and confidence score.
6. The API returns the result as JSON.

The current service can recognize dependency, compilation, test, lint, type, Docker, environment, and unknown failures. It uses clear rules instead of AI at this stage. This makes the result fast, predictable, inexpensive, and easy to test.

The `samples/` folder contains fake but realistic logs used for automated tests. These files are not the final source of production data. Later, a GitHub, Bitbucket, GitLab, Jenkins, or other CI connector will download a real failed-run log and send its text to the same analysis flow.

The `providers.py` file prepares for this future connection. It separates the job of getting a log from the job of understanding a log. A provider will fetch a log; this service will analyze it. Because of this separation, the classifier does not need separate logic for every CI platform.

The service also accepts optional information about the source of a log, such as the provider, repository, branch, commit, and run ID. This allows a future dashboard or backend to connect an analysis to the exact failed build.

This branch currently provides a complete standalone deterministic MVP. It includes the API, parser, classifier, analyzer, secret redaction, provider boundary, sample logs, tests, and setup documentation. The test suite currently passes all 21 tests.

The main future task is to connect Anushka's `GroqClient` so the service can provide deeper AI-assisted explanations. That integration should be added after the deterministic result is created, and the deterministic result should remain as a fallback if Groq is unavailable. Database storage, real CI connectors, backend integration, and frontend integration are later project stages.
