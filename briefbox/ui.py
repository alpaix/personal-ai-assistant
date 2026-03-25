from __future__ import annotations

import os
from collections.abc import Sequence
from dataclasses import dataclass

import httpx

from briefbox.app.models import MessageAction, MessageResult, RunResultResponse, RunStatusResponse

DEFAULT_API_BASE_URL = os.environ.get("BRIEFBOX_API_URL", "http://127.0.0.1:8000")


@dataclass(slots=True)
class UIState:
    fixture_id: str = "monday-chaos-v1"
    run_id: str | None = None


class BriefBoxAPIError(RuntimeError):
    """Raised when the UI client cannot complete an API operation."""


class BriefBoxAPIClient:
    def __init__(
        self,
        *,
        base_url: str = DEFAULT_API_BASE_URL,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = client or httpx.AsyncClient(base_url=self.base_url, timeout=30.0)

    async def get_fixture_summary(self, fixture_id: str) -> dict:
        response = await self._client.get(f"/fixtures/{fixture_id}")
        return _parse_json_response(response)

    async def create_run(self, fixture_id: str) -> dict:
        response = await self._client.post(
            "/triage/run",
            json={"fixture_id": fixture_id, "use_cached_on_timeout": True},
        )
        return _parse_json_response(response)

    async def get_run_status(self, run_id: str) -> RunStatusResponse:
        response = await self._client.get(f"/triage/status/{run_id}")
        payload = _parse_json_response(response)
        return RunStatusResponse.model_validate(payload)

    async def get_run_result(self, run_id: str) -> RunResultResponse:
        response = await self._client.get(f"/triage/result/{run_id}")
        payload = _parse_json_response(response)
        return RunResultResponse.model_validate(payload)

    async def apply_action(self, run_id: str, message_id: str, action: MessageAction) -> dict:
        response = await self._client.post(
            "/actions/message",
            json={"run_id": run_id, "message_id": message_id, "action": action.value},
        )
        return _parse_json_response(response)

    async def unsubscribe(self, run_id: str, message_id: str) -> dict:
        response = await self._client.post(
            "/actions/unsubscribe",
            json={"run_id": run_id, "message_id": message_id},
        )
        return _parse_json_response(response)


def render_shell(state: UIState) -> str:
    return (
        "# BriefBox\n\n"
        f"- Fixture: `{state.fixture_id}`\n"
        f"- Active run: `{state.run_id or 'none'}`\n\n"
        "Commands:\n"
        "- `triage`\n"
        "- `fixture <fixture_id>`\n"
        "- `pin <message_id>`\n"
        "- `archive <message_id>`\n"
        "- `snooze <message_id>`\n"
        "- `unsubscribe <message_id>`\n"
        "- `refresh`\n"
    )


def render_progress(status: RunStatusResponse) -> str:
    lines = [
        "## Run Progress",
        f"- Run: `{status.run_id}`",
        f"- Status: `{status.status}`",
        f"- Processed: `{status.processed_messages}/{status.total_messages}`",
    ]
    if status.current_stage:
        lines.append(f"- Current stage: `{status.current_stage}`")
    if status.fallback_used:
        lines.append("- Fallback: `used`")
    if status.errors:
        lines.append("- Errors:")
        for error in status.errors:
            lines.append(f"  - {error}")
    return "\n".join(lines)


def render_result(result: RunResultResponse) -> str:
    lines = [
        f"## Result for `{result.run_id}`",
        f"- Status: `{result.status}`",
        f"- Messages: `{result.summary_stats.messages}`",
        (
            f"- Lanes: `do_now={result.summary_stats.lanes.get('do_now', 0)}`, "
            f"`track={result.summary_stats.lanes.get('track', 0)}`, "
            f"`ignore={result.summary_stats.lanes.get('ignore', 0)}`"
        ),
    ]
    if result.fallback_used:
        lines.append("- Fallback badge: `deterministic fallback used`")
    if result.errors:
        lines.append("- Errors:")
        for error in result.errors:
            lines.append(f"  - {error}")
    lines.extend(
        [
            "",
            "### Do Now",
            _render_lane(result.board.do_now),
            "",
            "### Track",
            _render_lane(result.board.track),
            "",
            "### Ignore",
            _render_lane(result.board.ignore),
            "",
            "### Agent Trace",
            _render_trace(result),
        ]
    )
    return "\n".join(lines)


def _render_lane(messages: Sequence[MessageResult]) -> str:
    if not messages:
        return "_No messages_"

    rendered: list[str] = []
    for message in messages:
        status_bits = []
        if message.pinned:
            status_bits.append("pinned")
        if message.archived:
            status_bits.append("archived")
        if message.snoozed:
            status_bits.append("snoozed")
        if message.unsubscribe_status:
            status_bits.append(f"unsubscribe={message.unsubscribe_status}")
        status_text = f" ({', '.join(status_bits)})" if status_bits else ""
        rendered.append(
            f"- `{message.message_id}` {message.subject}{status_text}\n"
            f"  - {message.summary}\n"
            f"  - confidence={message.confidence} priority={message.priority_score}\n"
            f"  - rationale: {message.score_rationale}"
        )
    return "\n".join(rendered)


def _render_trace(result: RunResultResponse) -> str:
    if not result.trace:
        return "_No trace available_"

    lines: list[str] = []
    for record in result.trace[:6]:
        lines.append(f"- `{record.message_id}` {record.subject} -> `{record.final_lane}`")
        for step in record.agent_steps:
            error_text = f" error={step.error}" if step.error else ""
            fallback_text = " fallback" if step.fallback_used else ""
            lines.append(f"  - `{step.agent_name}` latency={step.latency_ms}ms{fallback_text}{error_text}")
    if len(result.trace) > 6:
        lines.append(f"- ... {len(result.trace) - 6} more trace records")
    return "\n".join(lines)


def parse_command(text: str) -> tuple[str, str | None]:
    cleaned = text.strip()
    if not cleaned:
        return "", None
    parts = cleaned.split(maxsplit=1)
    command = parts[0].lower()
    argument = parts[1].strip() if len(parts) > 1 else None
    return command, argument


def _parse_json_response(response: httpx.Response) -> dict:
    try:
        payload = response.json()
    except ValueError as exc:
        raise BriefBoxAPIError("Backend returned non-JSON response") from exc
    if response.status_code >= 400:
        detail = payload.get("detail", "Unknown error")
        raise BriefBoxAPIError(str(detail))
    return payload
