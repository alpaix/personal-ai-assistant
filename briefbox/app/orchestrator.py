from __future__ import annotations

from collections.abc import Iterable

from briefbox.app.fixtures import FixtureError, load_fixture
from briefbox.app.models import (
    AgentStage,
    Category,
    ExtractedEntities,
    FallbackTriageResult,
    FixtureMessage,
    Lane,
    MessageResult,
    RunBoard,
    RunStatus,
    RunSummaryStats,
    TraceRecord,
    TraceStep,
    TriageStageOutput,
)
from briefbox.app.ollama_client import ModelResponseError, ModelTimeoutError, OllamaClient
from briefbox.app.rules import triage_message
from briefbox.app.store import InMemoryRunStore


class TriageOrchestrator:
    """
    Triage pipeline
    ================
    fixture -> staged model calls -> merge/fallback -> board/trace -> store snapshot
    """

    def __init__(
        self,
        *,
        store: InMemoryRunStore,
        model_client: OllamaClient | None = None,
        batch_size: int = 8,
    ) -> None:
        self.store = store
        self.model_client = model_client or OllamaClient()
        self.batch_size = batch_size

    def process_run(self, run_id: str, *, fixture_id: str, use_cached_on_timeout: bool = True) -> None:
        errors: list[str] = []
        fallback_used = False
        try:
            fixture = load_fixture(fixture_id)
        except FixtureError as exc:
            self.store.fail_run(run_id, [str(exc)])
            return

        self.store.start_run(run_id, total_messages=len(fixture.messages))
        results: list[MessageResult] = []
        trace_records: list[TraceRecord] = []

        processed_messages = 0
        for batch in self._chunk(fixture.messages, self.batch_size):
            for message in batch:
                message_result, trace_record, message_fallback, message_errors = self._triage_message(
                    message,
                    use_cached_on_timeout=use_cached_on_timeout,
                )
                processed_messages += 1
                results.append(message_result)
                trace_records.append(trace_record)
                fallback_used = fallback_used or message_fallback
                errors.extend(message_errors)
                current_stage = trace_record.agent_steps[-1].agent_name if trace_record.agent_steps else None
                self.store.update_progress(
                    run_id,
                    processed_messages=processed_messages,
                    current_stage=current_stage,
                    fallback_used=fallback_used,
                    errors=errors,
                )

        board = self._build_board(results)
        summary_stats = RunSummaryStats(
            messages=len(results),
            lanes={
                "do_now": len(board.do_now),
                "track": len(board.track),
                "ignore": len(board.ignore),
            },
        )
        final_status = RunStatus.PARTIAL if errors else RunStatus.COMPLETED
        self.store.finalize_run(
            run_id,
            status=final_status,
            board=board,
            trace=trace_records,
            summary_stats=summary_stats,
            fallback_used=fallback_used,
            errors=errors,
        )

    def _triage_message(
        self,
        message: FixtureMessage,
        *,
        use_cached_on_timeout: bool,
    ) -> tuple[MessageResult, TraceRecord, bool, list[str]]:
        fallback = triage_message(message)
        stage_outputs: dict[AgentStage, TriageStageOutput] = {}
        trace_steps: list[TraceStep] = []
        errors: list[str] = []
        fallback_used = False

        for stage in AgentStage:
            try:
                stage_result = self.model_client.run_stage(message, stage)
                stage_outputs[stage] = stage_result.output
                trace_steps.append(
                    TraceStep(
                        agent_name=stage,
                        output=stage_result.output,
                        confidence=stage_result.output.confidence,
                        latency_ms=stage_result.latency_ms,
                    )
                )
            except (ModelTimeoutError, ModelResponseError) as exc:
                fallback_used = True
                if isinstance(exc, ModelTimeoutError) and not use_cached_on_timeout:
                    errors.append(str(exc))
                else:
                    errors.append(f"{message.message_id}: {exc}")
                fallback_output = self._fallback_stage_output(fallback, stage)
                stage_outputs[stage] = fallback_output
                trace_steps.append(
                    TraceStep(
                        agent_name=stage,
                        output=fallback_output,
                        confidence=fallback.confidence,
                        latency_ms=0,
                        fallback_used=True,
                        error=str(exc),
                    )
                )

        result = self._merge_outputs(message, fallback, stage_outputs, trace_steps)
        trace_record = TraceRecord(
            message_id=result.message_id,
            sender=result.sender,
            subject=result.subject,
            agent_steps=trace_steps,
            priority_score=result.priority_score,
            score_rationale=result.score_rationale,
            final_lane=result.final_lane,
            unsubscribe_recommended=result.unsubscribe_candidate,
        )
        return result, trace_record, fallback_used, errors

    def _merge_outputs(
        self,
        message: FixtureMessage,
        fallback: FallbackTriageResult,
        stage_outputs: dict[AgentStage, TriageStageOutput],
        trace_steps: list[TraceStep],
    ) -> MessageResult:
        merged = TriageStageOutput(
            category=fallback.category,
            confidence=fallback.confidence,
            summary=fallback.summary,
            entities=fallback.entities,
            priority_score=self._default_priority(fallback.lane),
            score_rationale=self._default_rationale(fallback.lane, fallback.needs_review),
            suggested_lane=fallback.lane,
            action=None,
            action_deadline=fallback.entities.deadlines[0] if fallback.entities.deadlines else None,
            unsubscribe_candidate=fallback.unsubscribe_candidate,
        )
        for stage in AgentStage:
            merged = self._overlay_output(merged, stage_outputs.get(stage))

        return MessageResult(
            message_id=message.message_id,
            sender=message.sender_name or message.sender_email,
            subject=message.subject,
            summary=merged.summary or fallback.summary,
            entities=merged.entities if merged.entities != ExtractedEntities() else fallback.entities,
            category=merged.category or fallback.category,
            final_lane=merged.suggested_lane or fallback.lane,
            confidence=round(min(max(merged.confidence or fallback.confidence, 0.0), 1.0), 2),
            priority_score=min(max(merged.priority_score or self._default_priority(fallback.lane), 0), 100),
            score_rationale=merged.score_rationale or self._default_rationale(fallback.lane, fallback.needs_review),
            action=merged.action,
            action_deadline=merged.action_deadline,
            unsubscribe_candidate=(
                merged.unsubscribe_candidate
                if merged.unsubscribe_candidate is not None
                else fallback.unsubscribe_candidate
            ),
            needs_review=fallback.needs_review,
            trace_steps=trace_steps,
        )

    def _overlay_output(
        self,
        base: TriageStageOutput,
        overlay: TriageStageOutput | None,
    ) -> TriageStageOutput:
        if overlay is None:
            return base
        return TriageStageOutput(
            category=overlay.category or base.category,
            confidence=overlay.confidence if overlay.confidence is not None else base.confidence,
            summary=overlay.summary or base.summary,
            entities=overlay.entities if overlay.entities != ExtractedEntities() else base.entities,
            priority_score=overlay.priority_score if overlay.priority_score is not None else base.priority_score,
            score_rationale=overlay.score_rationale or base.score_rationale,
            suggested_lane=overlay.suggested_lane or base.suggested_lane,
            action=overlay.action or base.action,
            action_deadline=overlay.action_deadline or base.action_deadline,
            unsubscribe_candidate=(
                overlay.unsubscribe_candidate
                if overlay.unsubscribe_candidate is not None
                else base.unsubscribe_candidate
            ),
        )

    def _fallback_stage_output(
        self,
        fallback: FallbackTriageResult,
        stage: AgentStage,
    ) -> TriageStageOutput:
        defaults = {
            AgentStage.CLASSIFY: TriageStageOutput(
                category=fallback.category,
                confidence=fallback.confidence,
            ),
            AgentStage.SUMMARIZE: TriageStageOutput(
                summary=fallback.summary,
                entities=fallback.entities,
            ),
            AgentStage.PRIORITIZE: TriageStageOutput(
                priority_score=self._default_priority(fallback.lane),
                score_rationale=self._default_rationale(fallback.lane, fallback.needs_review),
                suggested_lane=fallback.lane,
            ),
            AgentStage.EXTRACT_ACTIONS: TriageStageOutput(
                action=self._default_action(fallback.category),
                action_deadline=fallback.entities.deadlines[0] if fallback.entities.deadlines else None,
                unsubscribe_candidate=fallback.unsubscribe_candidate,
            ),
        }
        return defaults[stage]

    def _build_board(self, results: list[MessageResult]) -> RunBoard:
        board = RunBoard()
        for result in results:
            if result.final_lane == Lane.DO_NOW:
                board.do_now.append(result)
            elif result.final_lane == Lane.TRACK:
                board.track.append(result)
            else:
                board.ignore.append(result)
        return board

    def _chunk(self, values: list[FixtureMessage], size: int) -> Iterable[list[FixtureMessage]]:
        for index in range(0, len(values), size):
            yield values[index : index + size]

    def _default_priority(self, lane: Lane) -> int:
        return {
            Lane.DO_NOW: 92,
            Lane.TRACK: 68,
            Lane.IGNORE: 18,
        }[lane]

    def _default_rationale(self, lane: Lane, needs_review: bool) -> str:
        if needs_review:
            return "Fallback path used because the message was ambiguous."
        return {
            Lane.DO_NOW: "Direct ask or deadline signal detected.",
            Lane.TRACK: "Tracking or informational update detected.",
            Lane.IGNORE: "Promotional or low-signal content detected.",
        }[lane]

    def _default_action(self, category: Category) -> str | None:
        return {
            Category.ACTION_REQUIRED: "review_and_reply",
            Category.TRACKING: "monitor",
            Category.UPDATE: "keep_for_reference",
            Category.PROMOTION: "archive",
            Category.NEWSLETTER: "archive",
            Category.NOISE: "review_manually",
        }.get(category)
