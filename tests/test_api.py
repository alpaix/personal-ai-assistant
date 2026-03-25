from fastapi.testclient import TestClient

from briefbox.app.api import create_app
from briefbox.app.models import AgentStage, Category, ExtractedEntities, Lane, TriageStageOutput
from briefbox.app.ollama_client import StageResult
from briefbox.app.store import InMemoryRunStore


class FakeModelClient:
    def run_stage(self, message, stage: AgentStage) -> StageResult:
        outputs = {
            AgentStage.CLASSIFY: TriageStageOutput(category=Category.ACTION_REQUIRED, confidence=0.83),
            AgentStage.SUMMARIZE: TriageStageOutput(
                summary=f"Summary for {message.subject}",
                entities=ExtractedEntities(deadlines=["2026-03-25"] if "Approval" in message.subject else []),
            ),
            AgentStage.PRIORITIZE: TriageStageOutput(
                priority_score=90,
                score_rationale="Synthetic API test rationale.",
                suggested_lane=Lane.DO_NOW if "Approval" in message.subject else Lane.TRACK,
            ),
            AgentStage.EXTRACT_ACTIONS: TriageStageOutput(
                action="review_and_reply",
                action_deadline="2026-03-25",
                unsubscribe_candidate=False,
            ),
        }
        return StageResult(output=outputs[stage], latency_ms=5)


store = InMemoryRunStore()
app = create_app(store=store)
app.state.orchestrator.model_client = FakeModelClient()
client = TestClient(app)


def test_health_endpoint_returns_ok() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"ok": True, "service": "briefbox-api"}


def test_create_triage_run_and_fetch_status_and_result() -> None:
    response = client.post("/triage/run", json={"fixture_id": "valid-fixture"})

    assert response.status_code == 202
    run_id = response.json()["run_id"]

    status_response = client.get(f"/triage/status/{run_id}")
    result_response = client.get(f"/triage/result/{run_id}")

    assert status_response.status_code == 200
    assert result_response.status_code == 200
    assert status_response.json()["status"] == "completed"
    assert result_response.json()["summary_stats"]["messages"] == 2


def test_create_triage_run_rejects_duplicate_active_fixture() -> None:
    local_store = InMemoryRunStore()
    local_app = create_app(store=local_store)
    local_app.state.store.create_run("valid-fixture")
    local_client = TestClient(local_app)

    response = local_client.post("/triage/run", json={"fixture_id": "valid-fixture"})

    assert response.status_code == 409


def test_missing_run_returns_404() -> None:
    response = client.get("/triage/result/run_missing")

    assert response.status_code == 404
