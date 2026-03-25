from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx

from briefbox.app.fixtures import project_root
from briefbox.app.models import MessageResult, UnsubscribeMethod, UnsubscribeStatus


class ActionError(RuntimeError):
    """Raised when a message action cannot be applied."""


@dataclass(slots=True)
class UnsubscribeExecutionResult:
    performed: bool
    method: UnsubscribeMethod
    status: UnsubscribeStatus
    user_message: str


class UnsubscribeExecutor:
    def __init__(
        self,
        *,
        http_client: httpx.Client | None = None,
        outbox_dir: Path | None = None,
    ) -> None:
        self.http_client = http_client or httpx.Client(timeout=10.0)
        self.outbox_dir = outbox_dir or project_root() / "data" / "unsubscribe-outbox"

    def execute(
        self,
        *,
        run_id: str,
        message: MessageResult,
        raw_headers: dict[str, str],
    ) -> UnsubscribeExecutionResult:
        header_value = str(raw_headers.get("List-Unsubscribe", "")).strip()
        if not header_value:
            return UnsubscribeExecutionResult(
                performed=False,
                method=UnsubscribeMethod.NONE,
                status=UnsubscribeStatus.UNSUPPORTED,
                user_message="Manual unsubscribe required: no List-Unsubscribe header.",
            )

        targets = _parse_targets(header_value)
        if not targets:
            return UnsubscribeExecutionResult(
                performed=False,
                method=UnsubscribeMethod.NONE,
                status=UnsubscribeStatus.UNSUPPORTED,
                user_message="Manual unsubscribe required: unsupported List-Unsubscribe header.",
            )

        for target in targets:
            if target.startswith("mailto:"):
                return self._handle_mailto(run_id=run_id, message=message, target=target)
            if target.startswith(("http://", "https://")):
                return self._handle_http(target)

        return UnsubscribeExecutionResult(
            performed=False,
            method=UnsubscribeMethod.NONE,
            status=UnsubscribeStatus.UNSUPPORTED,
            user_message="Manual unsubscribe required: unsupported unsubscribe target.",
        )

    def _handle_mailto(
        self,
        *,
        run_id: str,
        message: MessageResult,
        target: str,
    ) -> UnsubscribeExecutionResult:
        parsed = urlparse(target)
        params = parse_qs(parsed.query)
        payload = {
            "run_id": run_id,
            "message_id": message.message_id,
            "to": parsed.path,
            "subject": params.get("subject", ["unsubscribe"])[0],
            "body": params.get("body", [f"Please unsubscribe {message.sender}."])[0],
        }
        self.outbox_dir.mkdir(parents=True, exist_ok=True)
        outbox_file = self.outbox_dir / f"{run_id}-{message.message_id}.json"
        outbox_file.write_text(json.dumps(payload, indent=2))
        return UnsubscribeExecutionResult(
            performed=True,
            method=UnsubscribeMethod.MAILTO,
            status=UnsubscribeStatus.SUCCEEDED,
            user_message=f"Queued mailto unsubscribe request for {message.sender}.",
        )

    def _handle_http(self, target: str) -> UnsubscribeExecutionResult:
        try:
            response = self.http_client.get(target)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            return UnsubscribeExecutionResult(
                performed=False,
                method=UnsubscribeMethod.HTTP,
                status=UnsubscribeStatus.FAILED,
                user_message=f"HTTP unsubscribe failed: {exc}",
            )

        return UnsubscribeExecutionResult(
            performed=True,
            method=UnsubscribeMethod.HTTP,
            status=UnsubscribeStatus.SUCCEEDED,
            user_message="HTTP unsubscribe request completed successfully.",
        )


def apply_message_action(message: MessageResult, action: str) -> tuple[MessageResult, bool]:
    updated = False
    if action == "archive":
        if not message.archived:
            message.archived = True
            updated = True
    elif action == "pin":
        if not message.pinned:
            message.pinned = True
            updated = True
    elif action == "snooze":
        if not message.snoozed:
            message.snoozed = True
            updated = True
    else:  # pragma: no cover
        raise ActionError(f"Unsupported action '{action}'")
    return message, updated


def _parse_targets(header_value: str) -> list[str]:
    cleaned = header_value.replace("<", "").replace(">", "")
    return [part.strip() for part in cleaned.split(",") if part.strip()]
