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
