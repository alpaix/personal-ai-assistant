import json
from pathlib import Path

import pytest

from briefbox.app.fixtures import FixtureError, load_fixture


def test_load_fixture_returns_document() -> None:
    base_dir = Path(__file__).resolve().parent.parent

    document = load_fixture("valid-fixture", base_dir=base_dir)

    assert document.fixture_id == "valid-fixture"
    assert len(document.messages) == 2


def test_load_fixture_raises_for_missing_fixture(tmp_path: Path) -> None:
    with pytest.raises(FixtureError, match="was not found"):
        load_fixture("missing-fixture", base_dir=tmp_path)


def test_load_fixture_raises_for_duplicate_message_ids(tmp_path: Path) -> None:
    fixtures_dir = tmp_path / "data" / "fixtures"
    fixtures_dir.mkdir(parents=True)
    payload = {
        "fixture_id": "duplicate-fixture",
        "messages": [
            {
                "message_id": "dup-001",
                "sender_email": "one@example.com",
                "received_at": "2026-03-24T09:00:00Z",
                "subject": "One",
                "body_text": "First message",
                "headers": {},
            },
            {
                "message_id": "dup-001",
                "sender_email": "two@example.com",
                "received_at": "2026-03-24T10:00:00Z",
                "subject": "Two",
                "body_text": "Second message",
                "headers": {},
            },
        ],
    }
    (fixtures_dir / "duplicate-fixture.json").write_text(json.dumps(payload))

    with pytest.raises(FixtureError, match="duplicate message ids"):
        load_fixture("duplicate-fixture", base_dir=tmp_path)


def test_load_fixture_raises_for_schema_mismatch(tmp_path: Path) -> None:
    fixtures_dir = tmp_path / "data" / "fixtures"
    fixtures_dir.mkdir(parents=True)
    payload = {
        "fixture_id": "bad-fixture",
        "messages": [{"message_id": "msg-001"}],
    }
    (fixtures_dir / "bad-fixture.json").write_text(json.dumps(payload))

    with pytest.raises(FixtureError, match="does not match the schema"):
        load_fixture("bad-fixture", base_dir=tmp_path)
