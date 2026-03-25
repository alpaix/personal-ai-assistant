from pathlib import Path

import httpx

from briefbox.app.actions import UnsubscribeExecutor
from briefbox.app.fixtures import load_fixture
from briefbox.app.models import (
    AgentStage,
    Category,
    ExtractedEntities,
    Lane,
    MessageResult,
    TriageStageOutput,
    UnsubscribeStatus,
)
from briefbox.app.ollama_client import StageResult
from briefbox.app.orchestrator import TriageOrchestrator
from briefbox.app.store import InMemoryRunStore


class FakeModelClient:
    def run_stage(self, message, stage: AgentStage) -> StageResult:
        outputs = {
            AgentStage.CLASSIFY: TriageStageOutput(
                category=Category.ACTION_REQUIRED if message.message_id == "msg-001" else Category.TRACKING,
                confidence=0.82,
            ),
            AgentStage.SUMMARIZE: TriageStageOutput(
                summary=f"Model summary for {message.subject}",
                entities=ExtractedEntities(
                    deadlines=["2026-03-25"] if message.message_id == "msg-001" else [],
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


def _completed_run(store: InMemoryRunStore, fixture_id: str = "valid-fixture") -> str:
    orchestrator = TriageOrchestrator(store=store, model_client=FakeModelClient(), batch_size=10)
    run = store.create_run(fixture_id)
    orchestrator.process_run(run.run_id, fixture_id=fixture_id)
    return run.run_id


def test_apply_message_actions_are_idempotent() -> None:
    store = InMemoryRunStore()
    run_id = _completed_run(store)

    archive_once = store.apply_message_action(run_id, message_id="msg-001", action="archive")
    archive_twice = store.apply_message_action(run_id, message_id="msg-001", action="archive")
    pin_once = store.apply_message_action(run_id, message_id="msg-001", action="pin")
    snooze_once = store.apply_message_action(run_id, message_id="msg-001", action="snooze")

    assert archive_once.updated is True
    assert archive_twice.updated is False
    assert pin_once.message.pinned is True
    assert snooze_once.message.snoozed is True


def test_mailto_unsubscribe_writes_to_outbox(tmp_path: Path) -> None:
    executor = UnsubscribeExecutor(outbox_dir=tmp_path)
    message = MessageResult(
        message_id="msg-029",
        sender="Retail Planet",
        subject="Limited time sale ends tonight",
        summary="Promo",
        category="promotion",
        final_lane="ignore",
        confidence=0.9,
        priority_score=20,
        score_rationale="Promo",
    )

    result = executor.execute(
        run_id="run_123",
        message=message,
        raw_headers={"List-Unsubscribe": "<mailto:unsubscribe@retailplanet.example>"},
    )

    assert result.performed is True
    assert result.status == "succeeded"
    assert (tmp_path / "run_123-msg-029.json").exists()


def test_http_unsubscribe_reports_transport_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=500, request=request)

    executor = UnsubscribeExecutor(http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    message = MessageResult(
        message_id="msg-030",
        sender="Founder Weekly",
        subject="Newsletter",
        summary="Digest",
        category="newsletter",
        final_lane="ignore",
        confidence=0.91,
        priority_score=15,
        score_rationale="Digest",
    )

    result = executor.execute(
        run_id="run_124",
        message=message,
        raw_headers={"List-Unsubscribe": "<https://founderweekly.example/unsubscribe>"},
    )

    assert result.performed is False
    assert result.status == UnsubscribeStatus.FAILED


def test_unsupported_unsubscribe_header_is_reported() -> None:
    executor = UnsubscribeExecutor()
    fixture = load_fixture("monday-chaos-v1", base_dir=Path(__file__).resolve().parent.parent)
    message = MessageResult(
        message_id="msg-052",
        sender="Unknown",
        subject="Re: fwd // ???",
        summary="Needs manual review",
        category="noise",
        final_lane="ignore",
        confidence=0.35,
        priority_score=5,
        score_rationale="Ambiguous",
    )

    result = executor.execute(
        run_id="run_125",
        message=message,
        raw_headers=fixture.messages[-1].headers,
    )

    assert result.performed is False
    assert result.status == UnsubscribeStatus.UNSUPPORTED
