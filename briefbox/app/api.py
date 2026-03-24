from __future__ import annotations

from fastapi import FastAPI, HTTPException

from briefbox.app.fixtures import FixtureError, summarize_fixture
from briefbox.app.models import FixtureSummary, HealthResponse

app = FastAPI(title="BriefBox Demo API", version="0.1.0")


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse()


@app.get("/fixtures/{fixture_id}", response_model=FixtureSummary)
def get_fixture_summary(fixture_id: str) -> FixtureSummary:
    try:
        return summarize_fixture(fixture_id)
    except FixtureError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
