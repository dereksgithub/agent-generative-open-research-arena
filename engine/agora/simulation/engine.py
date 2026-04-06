"""Simulation engine — typed state model, deterministic tick loop, structured event log."""

from __future__ import annotations

import hashlib
import logging
import random
from collections.abc import Callable
from typing import Any

from agora.agents.agent import Agent, Decision
from agora.agents.strategy import DecisionStrategy, HeuristicStrategy
from agora.scenarios.schema import PolicyIntervention, ScenarioSpec

from .event_log import EventLog, EventType
from .state import (
    InterventionState,
    LocationState,
    RouteState,
    SimulationState,
    TickPhase,
)

TickCallback = Callable[[int, list[Decision]], None]

logger = logging.getLogger(__name__)


class SimulationEngine:
    """Drives the tick loop with explicit state transitions and event logging.

    Step semantics per tick:
      1. INTERVENTIONS — activate any scheduled policy changes
      2. PERCEIVE      — each agent observes the world
      3. DELIBERATE    — each agent determines its goal
      4. DECIDE        — each agent chooses an action (via DecisionStrategy)
      5. ACT           — each agent's decision mutates state
      6. RECORD        — tick summary is logged

    The engine is fully deterministic for non-LLM paths when a seed is provided.
    The RNG chain is: master_seed -> per-agent seed (master + agent_index).
    """

    def __init__(
        self,
        scenario: ScenarioSpec,
        agents: list[Agent],
        seed: int | None = None,
        strategy: DecisionStrategy | None = None,
    ) -> None:
        self.scenario = scenario
        self.agents = agents
        self.seed = seed
        self.strategy = strategy or HeuristicStrategy()
        self.strategy_name = self.strategy.__class__.__name__.removesuffix("Strategy").lower()

        # Build typed state
        run_id = self._build_run_id(scenario.id or scenario.name, seed, self.strategy_name)
        self.state = self._init_state(scenario, seed, run_id)
        self._seed_initial_occupancy()
        self.event_log = EventLog(run_id=self.state.run_id)
        self.world_snapshots: list[dict[str, Any]] = []

        # Index interventions by tick
        self._interventions_by_tick: dict[int, list[PolicyIntervention]] = {}
        for iv in scenario.interventions:
            self._interventions_by_tick.setdefault(iv.tick, []).append(iv)

        # Master RNG for deterministic agent seeding
        self._master_rng = random.Random(seed)
        if seed is not None:
            for i, agent in enumerate(agents):
                agent.seed(seed + i)

    def run(
        self,
        on_tick_complete: TickCallback | None = None,
    ) -> list[Decision]:
        """Execute all ticks and return the full decision trace.

        Parameters
        ----------
        on_tick_complete:
            Optional callback invoked after each tick with ``(tick, decisions)``.
            Use this to stream per-tick outputs (decisions, agent states, etc.)
            to disk incrementally instead of waiting for the full run to finish.
        """
        all_decisions: list[Decision] = []

        self.event_log.record(
            tick=0,
            event_type=EventType.RUN_START,
            data={
                "run_id": self.state.run_id,
                "scenario": self.scenario.name,
                "scenario_id": self.scenario.id,
                "strategy": self.strategy_name,
                "total_ticks": self.state.total_ticks,
                "num_agents": len(self.agents),
                "seed": self.seed,
            },
        )

        for tick in range(self.state.total_ticks):
            tick_decisions = self._step_tick(tick)
            all_decisions.extend(tick_decisions)
            # Flush events for this tick to disk (no-op in batch mode)
            self.event_log.flush()
            if on_tick_complete is not None:
                on_tick_complete(tick, tick_decisions)

        self.event_log.record(
            tick=self.state.tick,
            event_type=EventType.RUN_END,
            data={
                "scenario_id": self.scenario.id,
                "strategy": self.strategy_name,
                "total_decisions": len(all_decisions),
            },
        )
        # Final flush to capture RUN_END
        self.event_log.flush()

        return all_decisions

    # -- tick execution -------------------------------------------------------

    def _step_tick(self, tick: int) -> list[Decision]:
        """Execute one complete tick through all phases."""
        self.state.tick = tick
        decisions: list[Decision] = []

        self.event_log.record(tick=tick, event_type=EventType.TICK_START)

        # Phase 1: INTERVENTIONS
        self.state.phase = TickPhase.INTERVENTIONS
        self._apply_interventions(tick)

        # Phase 2-5: Agent lifecycle
        for agent in self.agents:
            # PERCEIVE
            self.state.phase = TickPhase.PERCEIVE
            world_snapshot = self.state.snapshot_for_agent(agent.current_location, agent.role)
            perception = agent.perceive(world_snapshot)
            perceive_event = self.event_log.record(
                tick=tick,
                event_type=EventType.AGENT_PERCEIVE,
                agent_id=agent.id,
                data={"location": agent.current_location},
            )

            # DELIBERATE
            self.state.phase = TickPhase.DELIBERATE
            goal = agent.deliberate(perception)
            deliberate_event = self.event_log.record(
                tick=tick,
                event_type=EventType.AGENT_DELIBERATE,
                agent_id=agent.id,
                data={"goal": goal},
                parent_event_id=perceive_event.event_id,
            )

            # DECIDE
            self.state.phase = TickPhase.DECIDE
            decision, strategy_event_id = self.strategy.decide_with_provenance(
                agent, goal, perception,
                parent_event_id=deliberate_event.event_id,
            )
            decide_parent = strategy_event_id if strategy_event_id is not None else deliberate_event.event_id
            decide_event = self.event_log.record(
                tick=tick,
                event_type=EventType.AGENT_DECIDE,
                agent_id=agent.id,
                data={
                    "action": decision.action,
                    "target": decision.target,
                    "reasoning": decision.reasoning,
                    "metadata": decision.metadata,
                },
                parent_event_id=decide_parent,
            )

            # ACT
            self.state.phase = TickPhase.ACT
            old_location = agent.current_location
            agent.act(decision)
            self._update_occupancy(agent.id, old_location, agent.current_location)
            self.event_log.record(
                tick=tick,
                event_type=EventType.AGENT_ACT,
                agent_id=agent.id,
                data={
                    "action": decision.action,
                    "from_location": old_location,
                    "to_location": agent.current_location,
                },
                parent_event_id=decide_event.event_id,
            )

            decisions.append(decision)

        # Occupancy snapshot — one event per occupied location
        for loc_id, loc in self.state.locations.items():
            if len(loc.occupant_ids) > 0:
                self.event_log.record(
                    tick=tick,
                    event_type=EventType.TICK_OCCUPANCY,
                    data={
                        "location_id": loc_id,
                        "location_name": loc.name,
                        "location_type": loc.type,
                        "occupant_ids": list(loc.occupant_ids),
                        "occupant_count": len(loc.occupant_ids),
                    },
                )

        # Keep per-tick world snapshots available for batch exporters and tests.
        self.world_snapshots.append(self.state.to_snapshot())

        # Phase 6: RECORD
        self.state.phase = TickPhase.RECORD
        self.event_log.record(
            tick=tick,
            event_type=EventType.TICK_END,
            data={"num_decisions": len(decisions)},
        )

        logger.debug("Tick %d: %d decisions", tick, len(decisions))
        return decisions

    # -- initialization -------------------------------------------------------

    @staticmethod
    def _init_state(
        scenario: ScenarioSpec,
        seed: int | None,
        run_id: str,
    ) -> SimulationState:
        """Build the initial typed simulation state from the scenario spec."""
        locations: dict[str, LocationState] = {}
        for loc in scenario.locations:
            locations[loc.id] = LocationState(
                id=loc.id,
                name=loc.name,
                type=loc.type,
                capacity=loc.capacity,
                x=loc.x,
                y=loc.y,
                resources=dict(loc.resources),
            )

        routes: list[RouteState] = []
        for route in scenario.routes:
            routes.append(RouteState(
                from_location=route.from_location,
                to_location=route.to_location,
                mode=route.mode,
                base_travel_time=route.travel_time_minutes,
                current_travel_time=route.travel_time_minutes,
            ))

        return SimulationState(
            run_id=run_id,
            scenario_id=scenario.id or "",
            tick=0,
            tick_unit=scenario.simulation.tick_unit,
            total_ticks=scenario.simulation.ticks,
            seed=seed,
            locations=locations,
            routes=routes,
        )

    @staticmethod
    def _build_run_id(
        scenario_id: str,
        seed: int | None,
        strategy_name: str,
    ) -> str:
        """Build a stable run ID from deterministic run inputs."""
        material = f"{scenario_id}|{seed}|{strategy_name}"
        return hashlib.sha256(material.encode("utf-8")).hexdigest()[:12]

    # -- interventions --------------------------------------------------------

    def _apply_interventions(self, tick: int) -> None:
        """Activate any interventions scheduled for this tick and apply route effects."""
        self.state.active_interventions = [
            intervention
            for intervention in self.state.active_interventions
            if intervention.is_active_at(tick)
        ]

        new = self._interventions_by_tick.get(tick, [])
        for iv in new:
            logger.info("Tick %d: Applying intervention '%s'", tick, iv.name)
            intervention = InterventionState(
                name=iv.name,
                description=iv.description,
                activated_at_tick=tick,
                effects=dict(iv.effects),
                target_roles=list(iv.target_roles),
                expires_at_tick=tick + iv.duration if iv.duration is not None else None,
            )
            self.state.active_interventions.append(intervention)
            self.event_log.record(
                tick=tick,
                event_type=EventType.INTERVENTION_APPLIED,
                data={
                    "name": iv.name,
                    "effects": iv.effects,
                    "target_roles": iv.target_roles,
                    "duration": iv.duration,
                },
            )

        # Recompute route travel times based on all active interventions
        self._recompute_route_costs()

    def _recompute_route_costs(self) -> None:
        """Apply all active intervention effects to route travel times."""
        for route in self.state.routes:
            multiplier = 1.0
            for iv in self.state.active_interventions:
                if iv.target_roles:
                    continue
                key = f"{route.mode}_cost_multiplier"
                if key in iv.effects:
                    multiplier *= iv.effects[key]
            route.current_travel_time = route.base_travel_time * multiplier

    # -- occupancy tracking ---------------------------------------------------

    def _seed_initial_occupancy(self) -> None:
        """Populate starting location occupancy before the first tick."""
        for agent in self.agents:
            location = self.state.get_location(agent.current_location)
            if location is None:
                raise ValueError(
                    f"Agent '{agent.id}' starts at unknown location '{agent.current_location}'"
                )
            self._add_occupant(location, agent.id)

    def _update_occupancy(
        self, agent_id: str, old_loc: str, new_loc: str
    ) -> None:
        """Update location occupant lists when an agent moves."""
        if old_loc == new_loc:
            return
        old = self.state.get_location(old_loc)
        if old:
            self._remove_occupant(old, agent_id)
        new = self.state.get_location(new_loc)
        if new is None:
            raise ValueError(f"Agent '{agent_id}' moved to unknown location '{new_loc}'")
        self._add_occupant(new, agent_id)

    @staticmethod
    def _remove_occupant(location: LocationState, agent_id: str) -> None:
        if agent_id in location.occupant_ids:
            location.occupant_ids.remove(agent_id)

    @staticmethod
    def _add_occupant(location: LocationState, agent_id: str) -> None:
        if agent_id in location.occupant_ids:
            return
        if location.capacity is not None and len(location.occupant_ids) >= location.capacity:
            raise ValueError(
                f"Location '{location.id}' exceeded capacity {location.capacity}"
            )
        location.occupant_ids.append(agent_id)
