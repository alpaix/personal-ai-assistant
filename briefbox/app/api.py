from __future__ import annotations

from fastapi import BackgroundTasks, FastAPI, HTTPException

from briefbox.app.actions import UnsubscribeExecutor
from briefbox.app.fixtures import FixtureError, load_fixture, summarize_fixture
from briefbox.app.models import (
    FixtureSummary,
    HealthResponse,
    MessageActionRequest,
    MessageActionResponse,
    RunCreatedResponse,
    RunRequest,
    RunResultResponse,
    RunStatusResponse,
    UnsubscribeRequest,
    UnsubscribeResponse,
)
from briefbox.app.orchestrator import TriageOrchestrator
from briefbox.app.store import (
    DuplicateRunError,
    InMemoryRunStore,
    MessageNotFoundError,
    RunNotFoundError,
)


def create_app(
    *,
    store: InMemoryRunStore | None = None,
    orchestrator: TriageOrchestrator | None = None,
    unsubscribe_executor: UnsubscribeExecutor | None = None,
) -> FastAPI:
    app = FastAPI(title="BriefBox Demo API", version="0.1.0")
    app.state.store = store or InMemoryRunStore()
    app.state.orchestrator = orchestrator or TriageOrchestrator(store=app.state.store)
    app.state.unsubscribe_executor = unsubscribe_executor or UnsubscribeExecutor()

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
            load_fixture(payload.fixture_id)
        except FixtureError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

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

    @app.post("/actions/message", response_model=MessageActionResponse)
    def post_message_action(payload: MessageActionRequest) -> MessageActionResponse:
        try:
            return app.state.store.apply_message_action(
                payload.run_id,
                message_id=payload.message_id,
                action=payload.action,
            )
        except RunNotFoundError as exc:
            raise HTTPException(status_code=404, detail=f"Run '{payload.run_id}' was not found") from exc
        except MessageNotFoundError as exc:
            raise HTTPException(status_code=404, detail=f"Message '{payload.message_id}' was not found") from exc

    @app.post("/actions/unsubscribe", response_model=UnsubscribeResponse)
    def post_unsubscribe(payload: UnsubscribeRequest) -> UnsubscribeResponse:
        try:
            message = app.state.store.get_message(payload.run_id, payload.message_id)
            fixture = load_fixture(app.state.store.get_run(payload.run_id).source_fixture_id)
        except RunNotFoundError as exc:
            raise HTTPException(status_code=404, detail=f"Run '{payload.run_id}' was not found") from exc
        except MessageNotFoundError as exc:
            raise HTTPException(status_code=404, detail=f"Message '{payload.message_id}' was not found") from exc
        except FixtureError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

        raw_message = next((item for item in fixture.messages if item.message_id == payload.message_id), None)
        if raw_message is None:
            raise HTTPException(status_code=404, detail=f"Message '{payload.message_id}' was not found")

        result = app.state.unsubscribe_executor.execute(
            run_id=payload.run_id,
            message=message,
            raw_headers={key: str(value) for key, value in raw_message.headers.items()},
        )
        updated_message = app.state.store.update_unsubscribe_result(
            payload.run_id,
            message_id=payload.message_id,
            method=result.method,
            status=result.status,
            user_message=result.user_message,
        )
        return UnsubscribeResponse(
            run_id=payload.run_id,
            message_id=payload.message_id,
            performed=result.performed,
            method=result.method,
            status=result.status,
            user_message=result.user_message,
            message=updated_message,
        )

    return app


app = create_app()
