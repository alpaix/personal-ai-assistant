from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Lane(StrEnum):
    DO_NOW = "do_now"
    TRACK = "track"
    IGNORE = "ignore"


class Category(StrEnum):
    ACTION_REQUIRED = "action_required"
    TRACKING = "tracking"
    PROMOTION = "promotion"
    NEWSLETTER = "newsletter"
    UPDATE = "update"
    NOISE = "noise"


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


class AgentStage(StrEnum):
    CLASSIFY = "classify"
    SUMMARIZE = "summarize"
    PRIORITIZE = "prioritize"
    EXTRACT_ACTIONS = "extract_actions"


class MessageAction(StrEnum):
    ARCHIVE = "archive"
    PIN = "pin"
    SNOOZE = "snooze"


class UnsubscribeMethod(StrEnum):
    MAILTO = "mailto"
    HTTP = "http"
    NONE = "none"


class UnsubscribeStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    UNSUPPORTED = "unsupported"


class FixtureMessage(BaseModel):
    message_id: str = Field(min_length=1)
    sender_name: str | None = None
    sender_email: str
    received_at: datetime
    subject: str
    body_text: str
    headers: dict[str, Any] = Field(default_factory=dict)


class FixtureDocument(BaseModel):
    fixture_id: str = Field(min_length=1)
    messages: list[FixtureMessage] = Field(min_length=1)


class ExtractedEntities(BaseModel):
    deadlines: list[str] = Field(default_factory=list)
    events: list[str] = Field(default_factory=list)
    shipments: list[str] = Field(default_factory=list)


class FallbackTriageResult(BaseModel):
    message_id: str
    category: Category
    lane: Lane
    confidence: float = Field(ge=0.0, le=1.0)
    summary: str = Field(min_length=1)
    entities: ExtractedEntities = Field(default_factory=ExtractedEntities)
    unsubscribe_candidate: bool = False
    needs_review: bool = False


class TriageStageOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: Category | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    summary: str | None = None
    entities: ExtractedEntities = Field(default_factory=ExtractedEntities)
    priority_score: int | None = Field(default=None, ge=0, le=100)
    score_rationale: str | None = None
    suggested_lane: Lane | None = None
    action: str | None = None
    action_deadline: str | None = None
    unsubscribe_candidate: bool | None = None


class TraceStep(BaseModel):
    agent_name: AgentStage
    output: TriageStageOutput
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    latency_ms: int = Field(ge=0)
    fallback_used: bool = False
    error: str | None = None


class MessageResult(BaseModel):
    message_id: str
    sender: str
    subject: str
    summary: str
    entities: ExtractedEntities = Field(default_factory=ExtractedEntities)
    category: Category
    final_lane: Lane
    confidence: float = Field(ge=0.0, le=1.0)
    priority_score: int = Field(ge=0, le=100)
    score_rationale: str
    action: str | None = None
    action_deadline: str | None = None
    unsubscribe_candidate: bool = False
    archived: bool = False
    pinned: bool = False
    snoozed: bool = False
    unsubscribe_status: UnsubscribeStatus | None = None
    unsubscribe_method: UnsubscribeMethod = UnsubscribeMethod.NONE
    unsubscribe_message: str | None = None
    needs_review: bool = False
    trace_steps: list[TraceStep] = Field(default_factory=list)


class TraceRecord(BaseModel):
    message_id: str
    sender: str
    subject: str
    agent_steps: list[TraceStep] = Field(default_factory=list)
    priority_score: int = Field(ge=0, le=100)
    score_rationale: str
    final_lane: Lane
    unsubscribe_recommended: bool = False


class RunBoard(BaseModel):
    do_now: list[MessageResult] = Field(default_factory=list)
    track: list[MessageResult] = Field(default_factory=list)
    ignore: list[MessageResult] = Field(default_factory=list)


class RunSummaryStats(BaseModel):
    messages: int = 0
    lanes: dict[str, int] = Field(default_factory=dict)


class RunRequest(BaseModel):
    fixture_id: str = Field(min_length=1)
    use_cached_on_timeout: bool = True


class RunCreatedResponse(BaseModel):
    run_id: str
    status: RunStatus


class MessageActionRequest(BaseModel):
    run_id: str = Field(min_length=1)
    message_id: str = Field(min_length=1)
    action: MessageAction


class MessageActionResponse(BaseModel):
    run_id: str
    message_id: str
    action: MessageAction
    updated: bool
    message: MessageResult


class RunStatusResponse(BaseModel):
    run_id: str
    status: RunStatus
    processed_messages: int = 0
    total_messages: int = 0
    current_stage: AgentStage | None = None
    fallback_used: bool = False
    errors: list[str] = Field(default_factory=list)


class RunResultResponse(BaseModel):
    run_id: str
    status: RunStatus
    fallback_used: bool = False
    board: RunBoard = Field(default_factory=RunBoard)
    trace: list[TraceRecord] = Field(default_factory=list)
    summary_stats: RunSummaryStats = Field(default_factory=RunSummaryStats)
    errors: list[str] = Field(default_factory=list)


class UnsubscribeRequest(BaseModel):
    run_id: str = Field(min_length=1)
    message_id: str = Field(min_length=1)


class UnsubscribeResponse(BaseModel):
    run_id: str
    message_id: str
    performed: bool
    method: UnsubscribeMethod
    status: UnsubscribeStatus
    user_message: str
    message: MessageResult


class RunRecord(BaseModel):
    run_id: str
    status: RunStatus
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    source_fixture_id: str
    total_messages: int = 0
    processed_messages: int = 0
    current_stage: AgentStage | None = None
    fallback_used: bool = False
    board: RunBoard = Field(default_factory=RunBoard)
    trace: list[TraceRecord] = Field(default_factory=list)
    summary_stats: RunSummaryStats = Field(default_factory=RunSummaryStats)
    errors: list[str] = Field(default_factory=list)


class HealthResponse(BaseModel):
    ok: bool = True
    service: str = "briefbox-api"


class FixtureSummary(BaseModel):
    fixture_id: str
    message_count: int
