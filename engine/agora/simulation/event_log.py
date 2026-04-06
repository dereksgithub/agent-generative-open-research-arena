"""Structured event log with stable IDs for every simulation event.

Supports two modes:

- **Batch mode** (default): events accumulate in memory and are written at the
  end of the run via ``write_jsonl()``.  This is the original behaviour and is
  used by tests and small runs.

- **Streaming mode**: pass ``output_path`` to the constructor.  Events are
  still kept in the in-memory list (so downstream code like ``DatasetExporter``
  can reference them), but they are also flushed to disk incrementally via
  ``flush()``.  Call ``flush()`` after each tick to bound I/O buffering and
  guarantee crash-safe output up to the last completed tick.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import IO, Any


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
    TICK_OCCUPANCY = "tick_occupancy"


@dataclass
class Event:
    """A single structured event in the simulation log."""

    event_id: int
    run_id: str
    tick: int
    event_type: EventType
    agent_id: str | None = None
    data: dict[str, Any] = field(default_factory=dict)
    parent_event_id: int | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["event_type"] = self.event_type.value
        if self.parent_event_id is None:
            del d["parent_event_id"]
        return d


class EventLog:
    """Accumulates events during a simulation run.

    Provides append-only semantics and serialization to JSONL.
    Supports optional streaming writes via ``output_path``.
    """

    def __init__(self, run_id: str, *, output_path: Path | None = None) -> None:
        self.run_id = run_id
        self._events: list[Event] = []
        self._next_id = 0
        self._flush_marker = 0
        self._streaming = output_path is not None
        self._fh: IO[str] | None = None
        if output_path is not None:
            self._fh = output_path.open("w", encoding="utf-8")

    def record(
        self,
        tick: int,
        event_type: EventType,
        agent_id: str | None = None,
        data: dict[str, Any] | None = None,
        parent_event_id: int | None = None,
    ) -> Event:
        event = Event(
            event_id=self._next_id,
            run_id=self.run_id,
            tick=tick,
            event_type=event_type,
            agent_id=agent_id,
            data=data or {},
            parent_event_id=parent_event_id,
        )
        self._events.append(event)
        self._next_id += 1
        return event

    @property
    def events(self) -> list[Event]:
        return list(self._events)

    def __len__(self) -> int:
        return len(self._events)

    # -- streaming I/O --------------------------------------------------------

    def flush(self) -> None:
        """Write all events recorded since the last flush to the output file.

        No-op when running in batch mode (no ``output_path`` given).
        """
        self._flush_marker = self.flush_since(self._flush_marker)

    def flush_since(self, marker: int) -> int:
        """Flush events recorded after *marker* and return the next marker.

        This is the lower-level streaming primitive used by :meth:`flush`.
        It lets callers flush a specific event range without re-serializing
        previously written records.
        """
        if self._fh is None:
            return len(self._events)

        for event in self._events[marker:]:
            self._fh.write(json.dumps(event.to_dict()) + "\n")
        self._fh.flush()
        next_marker = len(self._events)
        self._flush_marker = max(self._flush_marker, next_marker)
        return next_marker

    def close(self) -> None:
        """Flush remaining events and close the output file handle.

        Safe to call multiple times or when running in batch mode.
        """
        if self._fh is None:
            return
        self.flush()
        self._fh.close()
        self._fh = None

    # -- batch I/O (backward compat) ------------------------------------------

    def write_jsonl(self, path: Path) -> None:
        """Write **all** events to *path* in one shot (batch mode).

        When streaming mode is active, this is a no-op because the file has
        already been written incrementally.
        """
        if self._streaming:
            # Streaming mode — file already written via flush/close.
            return
        with path.open("w", encoding="utf-8") as f:
            for event in self._events:
                f.write(json.dumps(event.to_dict()) + "\n")
