"""Explicit, typed simulation state model with step semantics."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TickPhase(str, Enum):
    """Discrete phases within a single tick."""

    INTERVENTIONS = "interventions"
    PERCEIVE = "perceive"
    DELIBERATE = "deliberate"
    DECIDE = "decide"
    ACT = "act"
    RECORD = "record"


@dataclass
class LocationState:
    """Runtime state of a single location."""

    id: str
    name: str
    type: str
    capacity: int | None
    x: float
    y: float
    occupant_ids: list[str] = field(default_factory=list)
    resources: dict[str, float] = field(default_factory=dict)


@dataclass
class RouteState:
    """Runtime state of a route between two locations."""

    from_location: str
    to_location: str
    mode: str
    base_travel_time: float
    current_travel_time: float  # may be modified by interventions
    congestion: float = 0.0  # 0.0 = free-flow, 1.0 = gridlock


@dataclass
class InterventionState:
    """An active policy intervention with its effects on the world."""

    name: str
    description: str
    activated_at_tick: int
    effects: dict[str, float] = field(default_factory=dict)
    target_roles: list[str] = field(default_factory=list)
    expires_at_tick: int | None = None

    def applies_to_role(self, role: str) -> bool:
        """Return True when this intervention should affect the given role."""
        return not self.target_roles or role in self.target_roles

    def is_active_at(self, tick: int) -> bool:
        """Return True when this intervention is active at the given tick."""
        return self.expires_at_tick is None or tick < self.expires_at_tick


@dataclass
class SimulationState:
    """Complete, explicit simulation state at any point in time.

    This is the single source of truth for the simulation. Every mutation
    goes through the engine's step methods so the state is always consistent.
    """

    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    scenario_id: str = ""
    tick: int = 0
    tick_unit: str = "hour"
    total_ticks: int = 24
    phase: TickPhase = TickPhase.INTERVENTIONS
    seed: int | None = None

    # World
    locations: dict[str, LocationState] = field(default_factory=dict)
    routes: list[RouteState] = field(default_factory=list)
    active_interventions: list[InterventionState] = field(default_factory=list)

    # Counters for stable IDs
    _next_event_id: int = field(default=0, repr=False)

    def next_event_id(self) -> int:
        eid = self._next_event_id
        self._next_event_id += 1
        return eid

    def routes_from(self, location_id: str) -> list[RouteState]:
        """Get all routes departing from a location."""
        return [r for r in self.routes if r.from_location == location_id]

    def get_location(self, location_id: str) -> LocationState | None:
        return self.locations.get(location_id)

    def to_snapshot(self) -> dict[str, Any]:
        """Return a serializable snapshot of the full world state at this tick."""
        return {
            "tick": self.tick,
            "tick_unit": self.tick_unit,
            "locations": [
                {
                    "id": loc.id,
                    "name": loc.name,
                    "type": loc.type,
                    "occupant_count": len(loc.occupant_ids),
                    "capacity": loc.capacity,
                    "resources": dict(loc.resources),
                }
                for loc in self.locations.values()
            ],
            "routes": [
                {
                    "from": r.from_location,
                    "to": r.to_location,
                    "mode": r.mode,
                    "base_travel_time": r.base_travel_time,
                    "current_travel_time": r.current_travel_time,
                    "congestion": r.congestion,
                }
                for r in self.routes
            ],
            "active_interventions": [
                {
                    "name": iv.name,
                    "description": iv.description,
                    "activated_at_tick": iv.activated_at_tick,
                    "expires_at_tick": iv.expires_at_tick,
                    "effects": iv.effects,
                    "target_roles": iv.target_roles,
                }
                for iv in self.active_interventions
            ],
        }

    def snapshot_for_agent(self, agent_location: str, agent_role: str = "") -> dict[str, Any]:
        """Build the world-view dict that agents receive during perceive().

        This keeps backward compatibility with the existing agent interface
        while providing richer typed data internally.
        """
        routes_list = []
        for r in self.routes_from(agent_location):
            targeted_multiplier = 1.0
            for intervention in self.active_interventions:
                if not intervention.target_roles or not intervention.applies_to_role(agent_role):
                    continue
                key = f"{r.mode}_cost_multiplier"
                if key in intervention.effects:
                    targeted_multiplier *= intervention.effects[key]
            routes_list.append({
                "from": r.from_location,
                "to": r.to_location,
                "mode": r.mode,
                "travel_time_minutes": r.current_travel_time * targeted_multiplier,
            })

        interventions_list = []
        for iv in self.active_interventions:
            if not iv.applies_to_role(agent_role):
                continue
            interventions_list.append({
                "name": iv.name,
                "description": iv.description,
                "effects": iv.effects,
            })

        return {
            "tick": self.tick,
            "tick_unit": self.tick_unit,
            "scenario_id": self.scenario_id,
            "current_location_resources": dict(
                self.locations.get(agent_location).resources
            ) if agent_location in self.locations else {},
            "routes_from": {agent_location: routes_list} if routes_list else {},
            "active_interventions": interventions_list,
        }
