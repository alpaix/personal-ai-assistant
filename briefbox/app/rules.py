from __future__ import annotations

import re
from collections.abc import Iterable

from briefbox.app.models import (
    Category,
    ExtractedEntities,
    FallbackTriageResult,
    FixtureDocument,
    FixtureMessage,
    Lane,
)

ACTION_KEYWORDS = (
    "approve",
    "approval",
    "action required",
    "reply needed",
    "urgent",
    "deadline",
    "sign",
    "signature",
    "review",
    "confirm by",
    "complete by",
    "availability",
    "respond by",
    "permission slip",
    "verify",
)
TRACKING_KEYWORDS = (
    "tracking",
    "shipment",
    "delivered",
    "delivery",
    "out for delivery",
    "itinerary",
    "flight",
    "hotel",
    "reservation",
    "appointment",
    "webinar",
    "conference",
    "meetup",
    "ticket",
    "check-in",
    "scheduled",
    "delay",
    "delayed",
    "trip",
    "travel",
)
IGNORE_KEYWORDS = (
    "sale",
    "deal",
    "discount",
    "coupon",
    "newsletter",
    "digest",
    "unsubscribe",
    "promo",
    "promotion",
    "limited time",
    "shop now",
    "black friday",
    "sponsor",
    "marketing",
)
UPDATE_KEYWORDS = (
    "receipt",
    "renewal",
    "processed",
    "statement",
    "invoice",
)

DEADLINE_PATTERN = re.compile(
    r"\b("
    r"today|tomorrow|monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
    r"\d{4}-\d{2}-\d{2}"
    r")\b",
    re.IGNORECASE,
)


def triage_message(message: FixtureMessage) -> FallbackTriageResult:
    subject = message.subject.strip()
    searchable = " ".join(
        [
            message.sender_email,
            message.subject,
            message.body_text,
            _header_value(message, "List-Unsubscribe"),
        ]
    ).lower()
    entities = ExtractedEntities(
        deadlines=_extract_deadlines(searchable),
        events=_extract_events(searchable),
        shipments=_extract_shipments(searchable),
    )

    action_hits = _keyword_hits(searchable, ACTION_KEYWORDS)
    track_hits = _keyword_hits(searchable, TRACKING_KEYWORDS)
    ignore_hits = _keyword_hits(searchable, IGNORE_KEYWORDS)
    update_hits = _keyword_hits(searchable, UPDATE_KEYWORDS)
    has_list_unsubscribe = bool(_header_value(message, "List-Unsubscribe"))

    needs_review = not any((action_hits, track_hits, ignore_hits, update_hits))

    if action_hits:
        category = Category.ACTION_REQUIRED
        lane = Lane.DO_NOW
        confidence = _confidence(0.93, action_hits, bool(entities.deadlines))
        summary = f"Action required: {subject}"
    elif track_hits or entities.events or entities.shipments:
        category = Category.TRACKING
        lane = Lane.TRACK
        confidence = _confidence(0.88, track_hits, bool(entities.events or entities.shipments))
        summary = f"Tracking update: {subject}"
    elif ignore_hits or has_list_unsubscribe:
        category = Category.NEWSLETTER if "newsletter" in searchable or "digest" in searchable else Category.PROMOTION
        lane = Lane.IGNORE
        confidence = _confidence(0.91, ignore_hits, has_list_unsubscribe)
        summary = f"Low-priority inbox noise: {subject}"
    elif entities.deadlines:
        category = Category.ACTION_REQUIRED
        lane = Lane.DO_NOW
        confidence = _confidence(0.74, len(entities.deadlines), True)
        summary = f"Deadline to review: {subject}"
    elif update_hits:
        category = Category.UPDATE
        lane = Lane.TRACK
        confidence = _confidence(0.73, update_hits, False)
        summary = f"Keep an eye on this update: {subject}"
    else:
        category = Category.NOISE
        lane = Lane.IGNORE
        confidence = 0.35
        summary = f"Needs manual review: {subject}"

    return FallbackTriageResult(
        message_id=message.message_id,
        category=category,
        lane=lane,
        confidence=round(min(confidence, 0.99), 2),
        summary=summary,
        entities=entities,
        unsubscribe_candidate=has_list_unsubscribe or category in {Category.PROMOTION, Category.NEWSLETTER},
        needs_review=needs_review,
    )


def triage_fixture(document: FixtureDocument) -> list[FallbackTriageResult]:
    return [triage_message(message) for message in document.messages]


def _header_value(message: FixtureMessage, header_name: str) -> str:
    return str(message.headers.get(header_name, "")).strip()


def _keyword_hits(searchable: str, keywords: Iterable[str]) -> int:
    hits = 0
    for keyword in keywords:
        pattern = re.compile(rf"\b{re.escape(keyword)}\b", re.IGNORECASE)
        if pattern.search(searchable):
            hits += 1
    return hits


def _extract_deadlines(searchable: str) -> list[str]:
    return _dedupe(match.group(0).lower() for match in DEADLINE_PATTERN.finditer(searchable))


def _extract_events(searchable: str) -> list[str]:
    events: list[str] = []
    if "meeting" in searchable or "offsite" in searchable:
        events.append("meeting")
    if "webinar" in searchable:
        events.append("webinar")
    if "conference" in searchable or "summit" in searchable:
        events.append("conference")
    if "appointment" in searchable:
        events.append("appointment")
    if "meetup" in searchable:
        events.append("meetup")
    if "flight" in searchable or "hotel" in searchable:
        events.append("travel")
    return _dedupe(events)


def _extract_shipments(searchable: str) -> list[str]:
    shipments: list[str] = []
    if "tracking" in searchable:
        shipments.append("tracking")
    if "shipment" in searchable or "shipped" in searchable:
        shipments.append("shipment")
    if "delivery" in searchable or "delivered" in searchable:
        shipments.append("delivery")
    return _dedupe(shipments)


def _confidence(base: float, hit_count: int, extra_signal: bool) -> float:
    confidence = base + min(hit_count, 3) * 0.02
    if extra_signal:
        confidence += 0.02
    return confidence


def _dedupe(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value and value not in seen:
            deduped.append(value)
            seen.add(value)
    return deduped
