"""Tests for the structured event log."""

import json
from pathlib import Path

from agora.simulation.event_log import EventLog, EventType


def test_event_ids_are_sequential():
    log = EventLog(run_id="test123")
    e1 = log.record(tick=0, event_type=EventType.TICK_START)
    e2 = log.record(tick=0, event_type=EventType.AGENT_PERCEIVE, agent_id="alice")
    e3 = log.record(tick=0, event_type=EventType.TICK_END)
    assert e1.event_id == 0
    assert e2.event_id == 1
    assert e3.event_id == 2


def test_all_events_have_run_id():
    log = EventLog(run_id="abc")
    log.record(tick=0, event_type=EventType.RUN_START)
    log.record(tick=1, event_type=EventType.TICK_START)
    for event in log.events:
        assert event.run_id == "abc"


def test_event_data_preserved():
    log = EventLog(run_id="test")
    log.record(
        tick=3,
        event_type=EventType.AGENT_DECIDE,
        agent_id="bob",
        data={"action": "travel", "target": "office"},
    )
    event = log.events[0]
    assert event.agent_id == "bob"
    assert event.data["action"] == "travel"
    assert event.data["target"] == "office"


def test_write_jsonl(tmp_path: Path):
    log = EventLog(run_id="test")
    log.record(tick=0, event_type=EventType.RUN_START, data={"seed": 42})
    log.record(tick=0, event_type=EventType.TICK_START)
    log.record(tick=0, event_type=EventType.TICK_END)

    path = tmp_path / "events.jsonl"
    log.write_jsonl(path)

    lines = path.read_text().strip().split("\n")
    assert len(lines) == 3

    first = json.loads(lines[0])
    assert first["event_type"] == "run_start"
    assert first["run_id"] == "test"
    assert first["data"]["seed"] == 42


def test_len():
    log = EventLog(run_id="test")
    assert len(log) == 0
    log.record(tick=0, event_type=EventType.TICK_START)
    assert len(log) == 1


def test_to_dict_serializes_enum():
    log = EventLog(run_id="test")
    e = log.record(tick=0, event_type=EventType.INTERVENTION_APPLIED)
    d = e.to_dict()
    assert d["event_type"] == "intervention_applied"
    assert isinstance(d["event_type"], str)


def test_parent_event_id_included_when_set():
    log = EventLog(run_id="test")
    e = log.record(tick=0, event_type=EventType.AGENT_PERCEIVE, agent_id="alice")
    e2 = log.record(
        tick=0, event_type=EventType.AGENT_DELIBERATE, agent_id="alice",
        parent_event_id=e.event_id,
    )
    d = e2.to_dict()
    assert d["parent_event_id"] == e.event_id


def test_parent_event_id_omitted_when_none():
    log = EventLog(run_id="test")
    e = log.record(tick=0, event_type=EventType.TICK_START)
    d = e.to_dict()
    assert "parent_event_id" not in d


def test_tick_occupancy_serializes_correctly():
    log = EventLog(run_id="test")
    e = log.record(
        tick=5,
        event_type=EventType.TICK_OCCUPANCY,
        data={
            "location_id": "downtown",
            "location_name": "Downtown Core",
            "location_type": "commercial",
            "occupant_ids": ["alice", "bob"],
            "occupant_count": 2,
        },
    )
    d = e.to_dict()
    assert d["event_type"] == "tick_occupancy"
    assert isinstance(d["event_type"], str)
    assert d["agent_id"] is None
    assert d["data"]["location_id"] == "downtown"
    assert d["data"]["occupant_ids"] == ["alice", "bob"]
    assert d["data"]["occupant_count"] == 2


# -- streaming mode tests -----------------------------------------------------


def test_streaming_flush_writes_incrementally(tmp_path: Path):
    path = tmp_path / "events.jsonl"
    log = EventLog(run_id="stream", output_path=path)

    log.record(tick=0, event_type=EventType.TICK_START)
    log.record(tick=0, event_type=EventType.TICK_END)
    log.flush()

    # After first flush, file should contain 2 lines
    lines = path.read_text().strip().split("\n")
    assert len(lines) == 2

    log.record(tick=1, event_type=EventType.TICK_START)
    log.record(tick=1, event_type=EventType.TICK_END)
    log.flush()

    # After second flush, file should contain 4 lines
    lines = path.read_text().strip().split("\n")
    assert len(lines) == 4

    log.close()


def test_streaming_close_flushes_remaining(tmp_path: Path):
    path = tmp_path / "events.jsonl"
    log = EventLog(run_id="stream", output_path=path)

    log.record(tick=0, event_type=EventType.RUN_START)
    log.record(tick=0, event_type=EventType.TICK_START)
    # No explicit flush — close should flush everything
    log.close()

    lines = path.read_text().strip().split("\n")
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["event_type"] == "run_start"


def test_streaming_close_is_idempotent(tmp_path: Path):
    path = tmp_path / "events.jsonl"
    log = EventLog(run_id="stream", output_path=path)
    log.record(tick=0, event_type=EventType.TICK_START)
    log.close()
    log.close()  # should not raise

    lines = path.read_text().strip().split("\n")
    assert len(lines) == 1


def test_streaming_write_jsonl_is_noop(tmp_path: Path):
    """write_jsonl should be a no-op when streaming mode is active."""
    stream_path = tmp_path / "events.jsonl"
    batch_path = tmp_path / "batch.jsonl"
    log = EventLog(run_id="stream", output_path=stream_path)
    log.record(tick=0, event_type=EventType.TICK_START)
    log.flush()
    log.close()

    # write_jsonl should not create batch_path since streaming was used
    log.write_jsonl(batch_path)
    assert not batch_path.exists()


def test_streaming_event_order_preserved(tmp_path: Path):
    path = tmp_path / "events.jsonl"
    log = EventLog(run_id="stream", output_path=path)

    for tick in range(5):
        log.record(tick=tick, event_type=EventType.TICK_START)
        log.record(tick=tick, event_type=EventType.AGENT_PERCEIVE, agent_id="alice")
        log.record(tick=tick, event_type=EventType.TICK_END)
        log.flush()

    log.close()

    lines = path.read_text().strip().split("\n")
    assert len(lines) == 15  # 3 events * 5 ticks
    for i, line in enumerate(lines):
        event = json.loads(line)
        assert event["event_id"] == i


def test_streaming_flush_since_returns_updated_marker(tmp_path: Path):
    path = tmp_path / "events.jsonl"
    log = EventLog(run_id="stream", output_path=path)

    log.record(tick=0, event_type=EventType.TICK_START)
    marker = log.flush_since(0)
    assert marker == 1

    log.record(tick=0, event_type=EventType.TICK_END)
    marker = log.flush_since(marker)
    assert marker == 2
    log.close()

    lines = path.read_text().strip().split("\n")
    assert len(lines) == 2
    assert json.loads(lines[-1])["event_type"] == "tick_end"


def test_batch_mode_flush_is_noop():
    """flush() should be safe to call on a batch-mode EventLog."""
    log = EventLog(run_id="batch")
    log.record(tick=0, event_type=EventType.TICK_START)
    log.flush()  # should not raise
    log.close()  # should not raise


def test_streaming_partial_run_has_complete_ticks(tmp_path: Path):
    """Simulate a crash after tick 1 — file should have ticks 0 and 1 complete."""
    path = tmp_path / "events.jsonl"
    log = EventLog(run_id="partial", output_path=path)

    # Tick 0
    log.record(tick=0, event_type=EventType.TICK_START)
    log.record(tick=0, event_type=EventType.TICK_END)
    log.flush()

    # Tick 1
    log.record(tick=1, event_type=EventType.TICK_START)
    log.record(tick=1, event_type=EventType.TICK_END)
    log.flush()

    # Tick 2 starts but "crashes" — no flush/close
    log.record(tick=2, event_type=EventType.TICK_START)
    # Simulate crash: don't flush or close

    # Read what was flushed — ticks 0 and 1 should be complete
    lines = path.read_text().strip().split("\n")
    assert len(lines) == 4  # 2 events * 2 ticks
    last = json.loads(lines[-1])
    assert last["tick"] == 1
    assert last["event_type"] == "tick_end"
