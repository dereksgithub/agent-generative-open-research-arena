"""Pydantic models for AGORA scenario definitions."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, model_validator


def _slugify(value: str) -> str:
    """Convert a label into a stable identifier fragment."""
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


class Location(BaseModel):
    """A named location in the simulation world."""

    id: str
    name: str
    type: str = "generic"  # e.g. "residential", "commercial", "transit_stop"
    capacity: int | None = Field(default=None, ge=0)
    x: float = 0.0
    y: float = 0.0
    resources: dict[str, float] = Field(default_factory=dict)


class Route(BaseModel):
    """A connection between two locations."""

    from_location: str = Field(alias="from")
    to_location: str = Field(alias="to")
    mode: str = "walk"  # walk, drive, transit
    travel_time_minutes: float = Field(default=10.0, gt=0)

    model_config = {"populate_by_name": True}


class PersonaDefinition(BaseModel):
    """Template for agent personas."""

    id: str
    name: str
    role: str = ""  # e.g. "commuter", "student", "retiree"
    traits: list[str] = Field(default_factory=list)
    home_location: str = ""
    work_location: str = ""
    preferred_mode: str = "walk"
    schedule: dict[str, str] = Field(default_factory=dict)  # tick -> goal

    # Extended persona fields for richer agent modeling
    age: int | None = Field(default=None, ge=0, le=150)
    income_bracket: str = ""  # e.g. "low", "medium", "high"
    household_size: int | None = Field(default=None, ge=1)
    values: list[str] = Field(default_factory=list)  # e.g. ["sustainability", "convenience"]
    backstory: str = ""  # free-text persona background for LLM-backed reasoning
    attributes: dict[str, float] = Field(default_factory=dict)  # domain-specific numeric attrs


class PolicyIntervention(BaseModel):
    """A policy change injected at a specific tick."""

    tick: int = Field(ge=0)
    name: str
    description: str
    effects: dict[str, float] = Field(default_factory=dict)
    target_roles: list[str] = Field(default_factory=list)  # empty = all agents
    duration: int | None = Field(default=None, ge=1)  # ticks; None = permanent


class KPIDefinition(BaseModel):
    """A key performance indicator tracked across the simulation run."""

    id: str
    name: str
    description: str = ""
    metric: Literal["count", "ratio", "mean", "sum"]
    source: Literal["decisions", "agent_states"]
    filter: dict[str, str] = Field(default_factory=dict)  # e.g. {"action": "travel", "mode": "drive"}
    unit: str = ""  # e.g. "trips", "agents", "%"


class SimulationConfig(BaseModel):
    """Top-level simulation parameters."""

    ticks: int = 24
    tick_unit: str = "hour"
    seed: int | None = None


class ScenarioSpec(BaseModel):
    """Complete scenario specification loaded from YAML."""

    id: str | None = None
    name: str
    description: str = ""
    domain: str = "transport"
    version: str = "1"

    simulation: SimulationConfig = Field(default_factory=SimulationConfig)
    locations: list[Location] = Field(default_factory=list)
    routes: list[Route] = Field(default_factory=list)
    agents: list[PersonaDefinition] = Field(default_factory=list)
    interventions: list[PolicyIntervention] = Field(default_factory=list)
    kpis: list[KPIDefinition] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_references(self) -> "ScenarioSpec":
        """Fill stable IDs and reject semantically inconsistent scenarios."""
        if not self.id:
            version = _slugify(self.version) or "1"
            self.id = f"{_slugify(self.name)}-v{version}"

        location_ids: set[str] = set()
        for location in self.locations:
            if location.id in location_ids:
                raise ValueError(f"Duplicate location id: {location.id}")
            location_ids.add(location.id)

        agent_ids: set[str] = set()
        for agent in self.agents:
            if agent.id in agent_ids:
                raise ValueError(f"Duplicate agent id: {agent.id}")
            agent_ids.add(agent.id)
            if agent.home_location not in location_ids:
                raise ValueError(
                    f"Agent '{agent.id}' references unknown home location '{agent.home_location}'"
                )
            if agent.work_location not in location_ids:
                raise ValueError(
                    f"Agent '{agent.id}' references unknown work location '{agent.work_location}'"
                )
            for tick_key, goal in agent.schedule.items():
                if goal.startswith("travel_to:"):
                    target = goal.split(":", 1)[1]
                    if target not in location_ids:
                        raise ValueError(
                            f"Agent '{agent.id}' schedule at tick '{tick_key}' "
                            f"references unknown location '{target}'"
                        )

        for route in self.routes:
            if route.from_location not in location_ids:
                raise ValueError(
                    f"Route references unknown origin location '{route.from_location}'"
                )
            if route.to_location not in location_ids:
                raise ValueError(
                    f"Route references unknown destination location '{route.to_location}'"
                )

        for intervention in self.interventions:
            if intervention.tick >= self.simulation.ticks:
                raise ValueError(
                    f"Intervention '{intervention.name}' has tick {intervention.tick} "
                    f"outside simulation range 0..{self.simulation.ticks - 1}"
                )

        return self
