"""Core agent model — perceive, deliberate, decide, act."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Decision:
    """A single agent decision at one tick."""

    tick: int
    agent_id: str
    action: str  # e.g. "travel", "stay", "switch_mode"
    target: str  # e.g. location id or mode name
    reasoning: str  # natural-language explanation
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class MemoryEntry:
    """One item in an agent's short-term memory."""

    tick: int
    event: str


@dataclass
class Agent:
    """A cognitive agent in the simulation.

    Lifecycle per tick: perceive() -> deliberate() -> decide() -> act()
    """

    id: str
    name: str
    role: str
    traits: list[str]
    home_location: str
    work_location: str
    preferred_mode: str
    schedule: dict[str, str]

    # Mutable state
    current_location: str = ""
    memory: list[MemoryEntry] = field(default_factory=list)
    _rng: random.Random = field(default_factory=random.Random, repr=False)

    # Enriched persona fields (carried from scenario for LLM prompts)
    _persona_values: list[str] = field(default_factory=list, repr=False)
    _persona_backstory: str = field(default="", repr=False)
    _persona_income_bracket: str = field(default="", repr=False)
    _persona_age: int | None = field(default=None, repr=False)
    _persona_household_size: int | None = field(default=None, repr=False)

    def seed(self, seed_value: int) -> None:
        self._rng = random.Random(seed_value)

    # -- lifecycle methods ----------------------------------------------------

    def perceive(self, world_state: dict[str, Any]) -> dict[str, Any]:
        """Build a perception of the world relevant to this agent."""
        active_interventions = world_state.get("active_interventions", [])
        return {
            "tick": world_state["tick"],
            "tick_unit": world_state.get("tick_unit", "hour"),
            "current_location": self.current_location,
            "available_routes": world_state.get("routes_from", {}).get(
                self.current_location, []
            ),
            "active_interventions": active_interventions,
            "recent_memory": self.memory[-5:],
        }

    def deliberate(self, perception: dict[str, Any]) -> str:
        """Determine the agent's goal for this tick based on schedule and perception."""
        tick = perception["tick"]
        tick_key = str(tick)
        if tick_key in self.schedule:
            return self.schedule[tick_key]
        # Default: go to work in morning ticks, go home in evening
        if 7 <= tick <= 9:
            return f"travel_to:{self.work_location}"
        if 17 <= tick <= 19:
            return f"travel_to:{self.home_location}"
        return "stay"

    def decide(
        self,
        goal: str,
        perception: dict[str, Any],
    ) -> Decision:
        """Choose a concrete action to pursue the goal (heuristic mode)."""
        tick = perception["tick"]

        if goal.startswith("travel_to:"):
            target_loc = goal.split(":", 1)[1]
            routes = perception.get("available_routes", [])
            # Check if any intervention modifies travel costs
            cost_multipliers = self._intervention_costs(
                perception.get("active_interventions", [])
            )

            # Pick best available route to target
            best_mode = self.preferred_mode
            if routes:
                candidates = [r for r in routes if r.get("to") == target_loc]
                if candidates:
                    # Pick cheapest (by travel time * cost multiplier)
                    def effective_cost(r: dict) -> float:
                        base = r.get("travel_time_minutes", 10.0)
                        mult = cost_multipliers.get(r.get("mode", "walk"), 1.0)
                        return base * mult

                    best_cost = min(effective_cost(candidate) for candidate in candidates)
                    best_candidates = [
                        candidate
                        for candidate in candidates
                        if effective_cost(candidate) == best_cost
                    ]
                    best = (
                        best_candidates[0]
                        if len(best_candidates) == 1
                        else self._rng.choice(best_candidates)
                    )
                    best_mode = best.get("mode", self.preferred_mode)

            reasoning = (
                f"I want to reach {target_loc}. "
                f"Choosing {best_mode} based on my preferences and current conditions."
            )
            if cost_multipliers:
                reasoning += f" Active policies affect costs: {cost_multipliers}."

            return Decision(
                tick=tick,
                agent_id=self.id,
                action="travel",
                target=target_loc,
                reasoning=reasoning,
                metadata={"mode": best_mode},
            )

        # Default: stay put
        return Decision(
            tick=tick,
            agent_id=self.id,
            action="stay",
            target=self.current_location,
            reasoning="No pressing goal this tick — staying put.",
        )

    def act(self, decision: Decision) -> None:
        """Apply a decision to mutate agent state."""
        if decision.action == "travel":
            self.current_location = decision.target
            self.memory.append(
                MemoryEntry(tick=decision.tick, event=f"Traveled to {decision.target}")
            )
        else:
            self.memory.append(
                MemoryEntry(tick=decision.tick, event=f"Stayed at {self.current_location}")
            )

    # -- helpers --------------------------------------------------------------

    @staticmethod
    def _intervention_costs(interventions: list[dict[str, Any]]) -> dict[str, float]:
        """Merge cost-affecting interventions into mode -> multiplier map."""
        costs: dict[str, float] = {}
        for iv in interventions:
            for key, val in iv.get("effects", {}).items():
                if key.endswith("_cost_multiplier"):
                    mode = key.replace("_cost_multiplier", "")
                    costs[mode] = costs.get(mode, 1.0) * val
        return costs
