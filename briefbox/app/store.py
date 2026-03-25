from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from briefbox.app.fixtures import project_root
from briefbox.app.models import (
    AgentStage,
    RunBoard,
    RunRecord,
    RunResultResponse,
    RunStatus,
    RunStatusResponse,
    RunSummaryStats,
    TraceRecord,
)


class DuplicateRunError(RuntimeError):
    """Raised when the same fixture already has an active run."""


class RunNotFoundError(KeyError):
    """Raised when a run id cannot be resolved."""


class InMemoryRunStore:
    def __init__(self, *, snapshot_dir: Path | None = None) -> None:
        self._runs: dict[str, RunRecord] = {}
        self._active_fixture_runs: dict[str, str] = {}
        self.snapshot_dir = snapshot_dir or project_root() / "data" / "cached-results" / "runs"

    def create_run(self, fixture_id: str) -> RunRecord:
        active_run_id = self._active_fixture_runs.get(fixture_id)
        if active_run_id:
            existing = self._runs.get(active_run_id)
            if existing and existing.status in {RunStatus.QUEUED, RunStatus.RUNNING}:
                raise DuplicateRunError(f"Fixture '{fixture_id}' already has an active run")

        run_id = f"run_{uuid4().hex[:12]}"
        record = RunRecord(
            run_id=run_id,
            status=RunStatus.QUEUED,
            created_at=datetime.now(UTC),
            source_fixture_id=fixture_id,
        )
        self._runs[run_id] = record
        self._active_fixture_runs[fixture_id] = run_id
        return record

    def start_run(self, run_id: str, *, total_messages: int) -> RunRecord:
        record = self.get_run(run_id)
        record.status = RunStatus.RUNNING
        record.started_at = datetime.now(UTC)
        record.total_messages = total_messages
        return record

    def update_progress(
        self,
        run_id: str,
        *,
        processed_messages: int,
        current_stage: AgentStage | None,
        fallback_used: bool,
        errors: list[str],
    ) -> RunRecord:
        record = self.get_run(run_id)
        record.processed_messages = processed_messages
        record.current_stage = current_stage
        record.fallback_used = fallback_used
        record.errors = list(errors)
        return record

    def finalize_run(
        self,
        run_id: str,
        *,
        status: RunStatus,
        board: RunBoard,
        trace: list[TraceRecord],
        summary_stats: RunSummaryStats,
        fallback_used: bool,
        errors: list[str],
    ) -> RunRecord:
        record = self.get_run(run_id)
        record.status = status
        record.completed_at = datetime.now(UTC)
        record.current_stage = None
        record.board = board
        record.trace = list(trace)
        record.summary_stats = summary_stats
        record.fallback_used = fallback_used
        record.errors = list(errors)
        self._active_fixture_runs.pop(record.source_fixture_id, None)
        self._persist_snapshot(record)
        return record

    def fail_run(self, run_id: str, errors: list[str]) -> RunRecord:
        record = self.get_run(run_id)
        record.status = RunStatus.FAILED
        record.completed_at = datetime.now(UTC)
        record.current_stage = None
        record.errors = list(errors)
        self._active_fixture_runs.pop(record.source_fixture_id, None)
        self._persist_snapshot(record)
        return record

    def get_run(self, run_id: str) -> RunRecord:
        try:
            return self._runs[run_id]
        except KeyError as exc:
            raise RunNotFoundError(run_id) from exc

    def get_status(self, run_id: str) -> RunStatusResponse:
        record = self.get_run(run_id)
        return RunStatusResponse(
            run_id=record.run_id,
            status=record.status,
            processed_messages=record.processed_messages,
            total_messages=record.total_messages,
            current_stage=record.current_stage,
            fallback_used=record.fallback_used,
            errors=record.errors,
        )

    def get_result(self, run_id: str) -> RunResultResponse:
        record = self.get_run(run_id)
        return RunResultResponse(
            run_id=record.run_id,
            status=record.status,
            fallback_used=record.fallback_used,
            board=record.board,
            trace=record.trace,
            summary_stats=record.summary_stats,
            errors=record.errors,
        )

    def _persist_snapshot(self, record: RunRecord) -> None:
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        path = self.snapshot_dir / f"{record.run_id}.json"
        path.write_text(json.dumps(record.model_dump(mode="json"), indent=2, default=str))
