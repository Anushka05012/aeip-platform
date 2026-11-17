from fastapi import FastAPI
from pydantic import BaseModel, Field

from .analyzer import analyze_failure
from .classifier import classify_log
from .parser import parse_log

app = FastAPI(title="AEIP Failure Intelligence Engine")


class AnalyzeRequest(BaseModel):
    log: str = Field(min_length=1)
    provider: str | None = None
    repository: str | None = None
    branch: str | None = None
    commit: str | None = None
    run_id: str | None = Field(default=None, alias="runId")

    model_config = {"populate_by_name": True}


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/analyze")
def analyze(request: AnalyzeRequest) -> dict[str, object]:
    parsed_log = parse_log(request.log)
    classification = classify_log(parsed_log)
    metadata = {
        "provider": request.provider,
        "repository": request.repository,
        "branch": request.branch,
        "commit": request.commit,
        "runId": request.run_id,
    }
    return analyze_failure(parsed_log, classification, metadata)
