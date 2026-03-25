from briefbox.app.models import AgentStage, Category, ExtractedEntities, Lane, TriageStageOutput
from briefbox.app.ollama_client import ModelTimeoutError, StageResult
from briefbox.app.orchestrator import TriageOrchestrator
from briefbox.app.store import DuplicateRunError, InMemoryRunStore


class FakeModelClient:
    def __init__(self, *, fail_message_ids: set[str] | None = None) -> None:
        self.fail_message_ids = fail_message_ids or set()

    def run_stage(self, message, stage: AgentStage) -> StageResult:
        if message.message_id in self.fail_message_ids:
            raise ModelTimeoutError(f"Ollama stage '{stage}' timed out")

        outputs = {
            AgentStage.CLASSIFY: TriageStageOutput(
                category=Category.ACTION_REQUIRED if message.message_id == "msg-001" else Category.TRACKING,
                confidence=0.82,
            ),
            AgentStage.SUMMARIZE: TriageStageOutput(
                summary=f"Model summary for {message.subject}",
                entities=ExtractedEntities(
                    deadlines=["2026-03-25"] if message.message_id == "msg-001" else [],
                    events=["travel"] if message.message_id == "msg-015" else [],
                    shipments=["tracking"] if message.message_id == "msg-013" else [],
                ),
            ),
            AgentStage.PRIORITIZE: TriageStageOutput(
                priority_score=95 if message.message_id == "msg-001" else 65,
                score_rationale="Model priority rationale.",
                suggested_lane=Lane.DO_NOW if message.message_id == "msg-001" else Lane.TRACK,
            ),
            AgentStage.EXTRACT_ACTIONS: TriageStageOutput(
                action="review_and_reply" if message.message_id == "msg-001" else "monitor",
                action_deadline="2026-03-25" if message.message_id == "msg-001" else None,
                unsubscribe_candidate=message.message_id == "msg-029",
            ),
        }
        return StageResult(output=outputs[stage], latency_ms=12)


def test_process_run_completes_with_model_outputs() -> None:
    store = InMemoryRunStore()
    orchestrator = TriageOrchestrator(store=store, model_client=FakeModelClient(), batch_size=10)
    run = store.create_run("valid-fixture")

    orchestrator.process_run(run.run_id, fixture_id="valid-fixture")

    result = store.get_result(run.run_id)
    assert result.status == "completed"
    assert result.summary_stats.messages == 2
    assert result.board.do_now[0].summary.startswith("Model summary")
    assert result.trace[0].agent_steps[0].agent_name == "classify"


def test_process_run_marks_partial_when_model_falls_back() -> None:
    store = InMemoryRunStore()
    orchestrator = TriageOrchestrator(
        store=store,
        model_client=FakeModelClient(fail_message_ids={"msg-001"}),
        batch_size=10,
    )
    run = store.create_run("valid-fixture")

    orchestrator.process_run(run.run_id, fixture_id="valid-fixture")

    status = store.get_status(run.run_id)
    result = store.get_result(run.run_id)
    assert status.status == "partial"
    assert result.fallback_used is True
    assert result.errors
    assert result.trace[0].agent_steps[0].fallback_used is True


def test_duplicate_run_for_same_fixture_is_rejected() -> None:
    store = InMemoryRunStore()
    store.create_run("valid-fixture")

    try:
        store.create_run("valid-fixture")
    except DuplicateRunError:
        pass
    else:  # pragma: no cover
        raise AssertionError("Expected duplicate run creation to be rejected")


def test_process_run_fails_for_missing_fixture() -> None:
    store = InMemoryRunStore()
    orchestrator = TriageOrchestrator(store=store, model_client=FakeModelClient())
    run = store.create_run("missing-fixture")

    orchestrator.process_run(run.run_id, fixture_id="missing-fixture")

    status = store.get_status(run.run_id)
    assert status.status == "failed"
    assert "was not found" in status.errors[0]
