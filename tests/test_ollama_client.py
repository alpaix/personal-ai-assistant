import httpx

from briefbox.app.fixtures import load_fixture
from briefbox.app.models import AgentStage
from briefbox.app.ollama_client import OllamaClient


def test_run_stage_uses_thinking_field_when_response_is_empty() -> None:
    fixture = load_fixture("valid-fixture")
    message = fixture.messages[0]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "response": "",
                "thinking": '{"category":"action_required","confidence":0.91}',
            },
            request=request,
        )

    client = OllamaClient(client=httpx.Client(base_url="http://test", transport=httpx.MockTransport(handler)))

    result = client.run_stage(message, AgentStage.CLASSIFY)

    assert result.output.category == "action_required"
    assert result.output.confidence == 0.91


def test_run_stage_normalizes_common_small_model_output_variants() -> None:
    fixture = load_fixture("valid-fixture")
    message = fixture.messages[0]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "response": "",
                "thinking": (
                    '{"category":"approval_needed","confidence":0.95,'
                    '"entities":[{"name":"invoice"}],'
                    '"priority_score":0.8,'
                    '"suggested_lane":"business_support"}'
                ),
            },
            request=request,
        )

    client = OllamaClient(client=httpx.Client(base_url="http://test", transport=httpx.MockTransport(handler)))

    result = client.run_stage(message, AgentStage.CLASSIFY)

    assert result.output.category == "action_required"
    assert result.output.priority_score == 80
    assert result.output.suggested_lane == "do_now"
    assert result.output.entities.model_dump() == {"deadlines": [], "events": [], "shipments": []}
