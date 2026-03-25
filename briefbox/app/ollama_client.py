from __future__ import annotations

import json
import time
from dataclasses import dataclass

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
        model: str = "qwen3:latest",
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
            raise ModelResponseError(f"Ollama stage '{stage}' request failed") from exc

        latency_ms = int((time.perf_counter() - started) * 1000)
        try:
            body = response.json()
        except ValueError as exc:
            raise ModelResponseError("Ollama returned non-JSON transport payload") from exc

        raw_response = body.get("response")
        if not isinstance(raw_response, str) or not raw_response.strip():
            raise ModelResponseError("Ollama response did not include a JSON string")

        try:
            parsed = json.loads(raw_response)
        except json.JSONDecodeError as exc:
            raise ModelResponseError("Ollama returned invalid JSON stage output") from exc

        try:
            output = TriageStageOutput.model_validate(parsed)
        except Exception as exc:
            raise ModelResponseError("Ollama stage output did not match the schema") from exc

        return StageResult(output=output, latency_ms=latency_ms)

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
