from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any

import httpx

from briefbox.app.models import AgentStage, FixtureMessage, TriageStageOutput


class ModelTimeoutError(RuntimeError):
    """Raised when the model call exceeds the configured timeout."""


class ModelResponseError(RuntimeError):
    """Raised when the model call or response shape is invalid."""


@dataclass(slots=True)
class StageResult:
    output: TriageStageOutput
    latency_ms: int


class OllamaClient:
    """Minimal Ollama wrapper that enforces JSON-only stage outputs."""

    def __init__(
        self,
        *,
        base_url: str = "http://127.0.0.1:11434",
        model: str = os.environ.get("BRIEFBOX_OLLAMA_MODEL", "llama3.2:3b"),
        timeout_s: float = 10.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_s = timeout_s
        self._client = client or httpx.Client(base_url=self.base_url, timeout=self.timeout_s)

    def run_stage(self, message: FixtureMessage, stage: AgentStage) -> StageResult:
        payload = {
            "model": self.model,
            "format": "json",
            "stream": False,
            "prompt": self._build_prompt(message, stage),
        }
        started = time.perf_counter()
        try:
            response = self._client.post("/api/generate", json=payload)
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise ModelTimeoutError(f"Ollama stage '{stage}' timed out") from exc
        except httpx.HTTPError as exc:
            detail = self._response_error_detail(getattr(exc, "response", None))
            suffix = f": {detail}" if detail else ""
            raise ModelResponseError(f"Ollama stage '{stage}' request failed{suffix}") from exc

        latency_ms = int((time.perf_counter() - started) * 1000)
        try:
            body = response.json()
        except ValueError as exc:
            raise ModelResponseError("Ollama returned non-JSON transport payload") from exc

        raw_response = body.get("response")
        if not isinstance(raw_response, str) or not raw_response.strip():
            raw_response = body.get("thinking")
        if not isinstance(raw_response, str) or not raw_response.strip():
            raise ModelResponseError("Ollama response did not include a JSON string")

        try:
            parsed = json.loads(raw_response)
        except json.JSONDecodeError as exc:
            parsed = self._extract_json_object(raw_response)
            if parsed is None:
                raise ModelResponseError("Ollama returned invalid JSON stage output") from exc

        try:
            output = TriageStageOutput.model_validate(self._normalize_stage_output(parsed))
        except Exception as exc:
            raise ModelResponseError("Ollama stage output did not match the schema") from exc

        return StageResult(output=output, latency_ms=latency_ms)

    def check_model_availability(self) -> str | None:
        try:
            response = self._client.get("/api/tags", timeout=min(self.timeout_s, 1.0))
            response.raise_for_status()
        except httpx.TimeoutException:
            return f"Ollama at {self.base_url} timed out while listing local models"
        except httpx.HTTPError:
            return f"Ollama at {self.base_url} is unavailable"

        try:
            payload = response.json()
        except ValueError:
            return "Ollama returned invalid JSON while listing local models"

        models = payload.get("models")
        if not isinstance(models, list):
            return "Ollama did not return a valid local model list"

        available_models = {
            name
            for item in models
            if isinstance(item, dict)
            for name in (item.get("name"), item.get("model"))
            if isinstance(name, str) and name
        }
        if self.model not in available_models:
            return f"Ollama model '{self.model}' is not available locally"

        return None

    def _response_error_detail(self, response: httpx.Response | None) -> str | None:
        if response is None:
            return None
        try:
            payload = response.json()
        except ValueError:
            return None
        detail = payload.get("error")
        return detail if isinstance(detail, str) and detail else None

    def _extract_json_object(self, raw_response: str) -> dict[str, Any] | None:
        start = raw_response.find("{")
        end = raw_response.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        try:
            parsed = json.loads(raw_response[start : end + 1])
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None

    def _normalize_stage_output(self, parsed: Any) -> dict[str, Any]:
        if not isinstance(parsed, dict):
            return parsed

        normalized = dict(parsed)

        category = normalized.get("category")
        if isinstance(category, str):
            normalized["category"] = {
                "approval": "action_required",
                "approval_needed": "action_required",
                "action": "action_required",
                "request": "action_required",
                "shipment": "tracking",
                "shipping": "tracking",
                "delivery": "tracking",
                "shipment_update": "tracking",
                "promo": "promotion",
                "marketing": "promotion",
                "offer": "promotion",
                "info": "update",
                "informational": "update",
                "spam": "noise",
            }.get(category, category)

        suggested_lane = normalized.get("suggested_lane")
        if isinstance(suggested_lane, str):
            normalized["suggested_lane"] = {
                "urgent": "do_now",
                "action_required": "do_now",
                "approval_needed": "do_now",
                "business_support": "do_now",
                "follow_up": "track",
                "monitor": "track",
                "tracking": "track",
                "newsletter": "ignore",
                "promotion": "ignore",
                "noise": "ignore",
                "archive": "ignore",
                "low_priority": "ignore",
            }.get(suggested_lane, suggested_lane)

        priority_score = normalized.get("priority_score")
        if isinstance(priority_score, float):
            normalized["priority_score"] = int(round(priority_score * 100)) if 0.0 <= priority_score <= 1.0 else int(
                round(priority_score)
            )

        entities = normalized.get("entities")
        if isinstance(entities, dict):
            normalized["entities"] = {
                "deadlines": self._coerce_string_list(entities.get("deadlines")),
                "events": self._coerce_string_list(entities.get("events")),
                "shipments": self._coerce_string_list(entities.get("shipments")),
            }
        else:
            normalized["entities"] = {"deadlines": [], "events": [], "shipments": []}

        return normalized

    def _coerce_string_list(self, value: Any) -> list[str]:
        if isinstance(value, str):
            return [value]
        if isinstance(value, list):
            return [item for item in value if isinstance(item, str)]
        return []

    def _build_prompt(self, message: FixtureMessage, stage: AgentStage) -> str:
        stage_instruction = {
            AgentStage.CLASSIFY: "Classify the email into a category and confidence.",
            AgentStage.SUMMARIZE: "Write a concise summary and extract entities.",
            AgentStage.PRIORITIZE: "Assign a lane, priority score, and rationale.",
            AgentStage.EXTRACT_ACTIONS: "Extract the next action, optional deadline, and unsubscribe candidate flag.",
        }[stage]
        return (
            "You are part of the BriefBox email triage pipeline.\n"
            "Return strict JSON only. Do not wrap the JSON in markdown.\n"
            f"Stage: {stage.value}\n"
            f"Instruction: {stage_instruction}\n"
            "JSON schema keys you may use: "
            "category, confidence, summary, entities, priority_score, score_rationale, "
            "suggested_lane, action, action_deadline, unsubscribe_candidate.\n"
            f"Sender: {message.sender_email}\n"
            f"Subject: {message.subject}\n"
            f"Body: {message.body_text}\n"
            f"Headers: {json.dumps(message.headers, sort_keys=True)}"
        )
