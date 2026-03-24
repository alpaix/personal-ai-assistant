from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from briefbox.app.models import FixtureDocument, FixtureSummary


class FixtureError(ValueError):
    """Raised when a fixture cannot be loaded safely."""


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def fixture_directory(base_dir: Path | None = None) -> Path:
    root = base_dir or project_root()
    return root / "data" / "fixtures"


def fixture_path(fixture_id: str, base_dir: Path | None = None) -> Path:
    return fixture_directory(base_dir=base_dir) / f"{fixture_id}.json"


def load_fixture(fixture_id: str, base_dir: Path | None = None) -> FixtureDocument:
    path = fixture_path(fixture_id, base_dir=base_dir)
    if not path.exists():
        raise FixtureError(f"Fixture '{fixture_id}' was not found at {path}")

    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise FixtureError(f"Fixture '{fixture_id}' contains invalid JSON") from exc

    try:
        document = FixtureDocument.model_validate(payload)
    except ValidationError as exc:
        raise FixtureError(f"Fixture '{fixture_id}' does not match the schema") from exc

    if document.fixture_id != fixture_id:
        raise FixtureError(f"Fixture id mismatch: expected '{fixture_id}', got '{document.fixture_id}'")

    duplicates = _duplicate_message_ids(document)
    if duplicates:
        duplicate_list = ", ".join(sorted(duplicates))
        raise FixtureError(f"Fixture '{fixture_id}' contains duplicate message ids: {duplicate_list}")

    return document


def summarize_fixture(fixture_id: str, base_dir: Path | None = None) -> FixtureSummary:
    document = load_fixture(fixture_id, base_dir=base_dir)
    return FixtureSummary(fixture_id=document.fixture_id, message_count=len(document.messages))


def _duplicate_message_ids(document: FixtureDocument) -> set[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for message in document.messages:
        if message.message_id in seen:
            duplicates.add(message.message_id)
        seen.add(message.message_id)
    return duplicates
