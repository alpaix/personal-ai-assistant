from pathlib import Path

from briefbox.app.fixtures import load_fixture
from briefbox.app.rules import triage_fixture, triage_message


def test_triage_message_classifies_action_required_message() -> None:
    fixture = load_fixture("valid-fixture", base_dir=Path(__file__).resolve().parent.parent)
    result = triage_message(fixture.messages[0])

    assert result.lane == "do_now"
    assert result.category == "action_required"
    assert "today" in result.summary.lower()
    assert result.entities.deadlines == ["today"]


def test_triage_fixture_covers_all_three_lanes_for_monday_chaos_fixture() -> None:
    fixture = load_fixture("monday-chaos-v1", base_dir=Path(__file__).resolve().parent.parent)
    results = triage_fixture(fixture)
    lanes = {result.lane for result in results}

    assert len(results) >= 50
    assert lanes == {"do_now", "track", "ignore"}


def test_triage_fixture_marks_supported_unsubscribe_candidates() -> None:
    fixture = load_fixture("monday-chaos-v1", base_dir=Path(__file__).resolve().parent.parent)
    results = {result.message_id: result for result in triage_fixture(fixture)}

    assert results["msg-029"].lane == "ignore"
    assert results["msg-029"].unsubscribe_candidate is True


def test_triage_fixture_extracts_tracking_and_deadline_signals() -> None:
    fixture = load_fixture("monday-chaos-v1", base_dir=Path(__file__).resolve().parent.parent)
    results = {result.message_id: result for result in triage_fixture(fixture)}

    assert "2026-03-25" in results["msg-001"].entities.deadlines
    assert "tracking" in results["msg-013"].entities.shipments
    assert "travel" in results["msg-015"].entities.events


def test_triage_fixture_marks_ambiguous_noise_for_review() -> None:
    fixture = load_fixture("monday-chaos-v1", base_dir=Path(__file__).resolve().parent.parent)
    results = {result.message_id: result for result in triage_fixture(fixture)}

    assert results["msg-052"].needs_review is True
    assert results["msg-052"].lane == "ignore"
