from __future__ import annotations

from fastapi import BackgroundTasks, FastAPI, HTTPException

from briefbox.app.fixtures import FixtureError, summarize_fixture
from briefbox.app.models import (
    FixtureSummary,
    HealthResponse,
    RunCreatedResponse,
    RunRequest,
    RunResultResponse,
    RunStatusResponse,
)
from briefbox.app.orchestrator import TriageOrchestrator
from briefbox.app.store import DuplicateRunError, InMemoryRunStore, RunNotFoundError


def create_app(
    *,
    store: InMemoryRunStore | None = None,
    orchestrator: TriageOrchestrator | None = None,
) -> FastAPI:
    app = FastAPI(title="BriefBox Demo API", version="0.1.0")
    app.state.store = store or InMemoryRunStore()
    app.state.orchestrator = orchestrator or TriageOrchestrator(store=app.state.store)

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse()

    @app.get("/fixtures/{fixture_id}", response_model=FixtureSummary)
    def get_fixture_summary(fixture_id: str) -> FixtureSummary:
        try:
            return summarize_fixture(fixture_id)
        except FixtureError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/triage/run", response_model=RunCreatedResponse, status_code=202)
    def create_triage_run(
        payload: RunRequest,
        background_tasks: BackgroundTasks,
    ) -> RunCreatedResponse:
        try:
            run = app.state.store.create_run(payload.fixture_id)
        except DuplicateRunError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        background_tasks.add_task(
            app.state.orchestrator.process_run,
            run.run_id,
            fixture_id=payload.fixture_id,
            use_cached_on_timeout=payload.use_cached_on_timeout,
        )
        return RunCreatedResponse(run_id=run.run_id, status=run.status)

    @app.get("/triage/status/{run_id}", response_model=RunStatusResponse)
    def get_triage_status(run_id: str) -> RunStatusResponse:
        try:
            return app.state.store.get_status(run_id)
        except RunNotFoundError as exc:
            raise HTTPException(status_code=404, detail=f"Run '{run_id}' was not found") from exc

    @app.get("/triage/result/{run_id}", response_model=RunResultResponse)
    def get_triage_result(run_id: str) -> RunResultResponse:
        try:
            return app.state.store.get_result(run_id)
        except RunNotFoundError as exc:
            raise HTTPException(status_code=404, detail=f"Run '{run_id}' was not found") from exc

    return app


app = create_app()
