"""Structured event log with stable IDs for every simulation event."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class EventType(str, Enum):
    RUN_START = "run_start"
    RUN_END = "run_end"
    TICK_START = "tick_start"
    TICK_END = "tick_end"
    INTERVENTION_APPLIED = "intervention_applied"
    AGENT_PERCEIVE = "agent_perceive"
    AGENT_DELIBERATE = "agent_deliberate"
    AGENT_DECIDE = "agent_decide"
    AGENT_ACT = "agent_act"
    LLM_REQUEST = "llm_request"
    LLM_RESPONSE = "llm_response"
    LLM_ERROR = "llm_error"
    LLM_CACHE_HIT = "llm_cache_hit"
    LLM_DISABLED = "llm_disabled"


@dataclass
class Event:
    """A single structured event in the simulation log."""

    event_id: int
    run_id: str
    tick: int
    event_type: EventType
    agent_id: str | None = None
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["event_type"] = self.event_type.value
        return d


class EventLog:
    """Accumulates events during a simulation run.

    Provides append-only semantics and serialization to JSONL.
    """

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self._events: list[Event] = []
        self._next_id = 0

    def record(
        self,
        tick: int,
        event_type: EventType,
        agent_id: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> Event:
        event = Event(
            event_id=self._next_id,
            run_id=self.run_id,
            tick=tick,
            event_type=event_type,
            agent_id=agent_id,
            data=data or {},
        )
        self._events.append(event)
        self._next_id += 1
        return event

    @property
    def events(self) -> list[Event]:
        return list(self._events)

    def __len__(self) -> int:
        return len(self._events)

    def write_jsonl(self, path: Path) -> None:
        with path.open("w", encoding="utf-8") as f:
            for event in self._events:
                f.write(json.dumps(event.to_dict()) + "\n")
