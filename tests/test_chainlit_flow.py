import httpx

from briefbox.app.models import RunStatusResponse
from briefbox.ui import BriefBoxAPIClient, UIState, parse_command, render_progress, render_result, render_shell


def test_parse_command_handles_command_and_argument() -> None:
    command, argument = parse_command("pin msg-001")

    assert command == "pin"
    assert argument == "msg-001"


def test_render_shell_includes_fixture_and_commands() -> None:
    rendered = render_shell(UIState(fixture_id="monday-chaos-v1", run_id="run_123"))

    assert "monday-chaos-v1" in rendered
    assert "triage" in rendered
    assert "unsubscribe <message_id>" in rendered


def test_render_progress_shows_processed_and_fallback() -> None:
    status = RunStatusResponse(
        run_id="run_123",
        status="partial",
        processed_messages=10,
        total_messages=52,
        current_stage="prioritize",
        fallback_used=True,
        errors=["msg-001: timeout"],
    )
    progress = render_progress(status)

    assert "10/52" in progress
    assert "Fallback" in progress
    assert "timeout" in progress


def test_api_client_and_render_result_flow() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/triage/run":
            return httpx.Response(202, json={"run_id": "run_123", "status": "queued"}, request=request)
        if request.url.path == "/triage/status/run_123":
            return httpx.Response(
                200,
                json={
                    "run_id": "run_123",
                    "status": "completed",
                    "processed_messages": 2,
                    "total_messages": 2,
                    "current_stage": None,
                    "fallback_used": False,
                    "errors": [],
                },
                request=request,
            )
        if request.url.path == "/triage/result/run_123":
            return httpx.Response(
                200,
                json={
                    "run_id": "run_123",
                    "status": "completed",
                    "fallback_used": False,
                    "board": {
                        "do_now": [
                            {
                                "message_id": "msg-001",
                                "sender": "Alex",
                                "subject": "Approval needed today",
                                "summary": "Approve the invoice today.",
                                "entities": {"deadlines": ["today"], "events": [], "shipments": []},
                                "category": "action_required",
                                "final_lane": "do_now",
                                "confidence": 0.9,
                                "priority_score": 95,
                                "score_rationale": "Direct ask",
                                "action": "review_and_reply",
                                "action_deadline": "today",
                                "unsubscribe_candidate": False,
                                "archived": False,
                                "pinned": True,
                                "snoozed": False,
                                "unsubscribe_status": None,
                                "unsubscribe_method": "none",
                                "unsubscribe_message": None,
                                "needs_review": False,
                                "trace_steps": [],
                            }
                        ],
                        "track": [],
                        "ignore": [],
                    },
                    "trace": [
                        {
                            "message_id": "msg-001",
                            "sender": "Alex",
                            "subject": "Approval needed today",
                            "agent_steps": [
                                {
                                    "agent_name": "classify",
                                    "output": {
                                        "category": "action_required",
                                        "confidence": 0.9,
                                        "summary": None,
                                        "entities": {"deadlines": [], "events": [], "shipments": []},
                                        "priority_score": None,
                                        "score_rationale": None,
                                        "suggested_lane": None,
                                        "action": None,
                                        "action_deadline": None,
                                        "unsubscribe_candidate": None,
                                    },
                                    "confidence": 0.9,
                                    "latency_ms": 5,
                                    "fallback_used": False,
                                    "error": None,
                                }
                            ],
                            "priority_score": 95,
                            "score_rationale": "Direct ask",
                            "final_lane": "do_now",
                            "unsubscribe_recommended": False,
                        }
                    ],
                    "summary_stats": {"messages": 2, "lanes": {"do_now": 1, "track": 0, "ignore": 0}},
                    "errors": [],
                },
                request=request,
            )
        raise AssertionError(f"Unexpected path: {request.url.path}")

    transport = httpx.MockTransport(handler)
    client = BriefBoxAPIClient(client=httpx.AsyncClient(base_url="http://test", transport=transport))

    async def scenario() -> str:
        run = await client.create_run("valid-fixture")
        status = await client.get_run_status(run["run_id"])
        result = await client.get_run_result(run["run_id"])
        assert status.status == "completed"
        return render_result(result)

    import asyncio

    rendered = asyncio.run(scenario())
    assert "Do Now" in rendered
    assert "Agent Trace" in rendered
    assert "pinned" in rendered
