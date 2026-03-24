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


class HeaderMap(BaseModel):
    model_config = ConfigDict(extra="allow")


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


class HealthResponse(BaseModel):
    ok: bool = True
    service: str = "briefbox-api"


class FixtureSummary(BaseModel):
    fixture_id: str
    message_count: int
