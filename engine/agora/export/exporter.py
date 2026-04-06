"""Dataset exporter — writes rich research-oriented outputs from a simulation run."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from agora.agents.agent import Agent, Decision
from agora.scenarios.schema import KPIDefinition, ScenarioSpec
from agora.simulation.event_log import EventLog, EventType


class DatasetExporter:
    """Produces structured datasets from a completed simulation run.

    Outputs:
      - agent_states.jsonl  — per-tick snapshot of each agent's state
      - narratives.jsonl    — agent decision reasoning as analyzable records
      - kpis.json           — evaluated KPI values per tick and overall
      - agent_summary.csv   — one row per agent with aggregate stats
    """

    def __init__(
        self,
        scenario: ScenarioSpec,
        agents: list[Agent],
        decisions: list[Decision],
        event_log: EventLog,
        run_id: str,
        world_snapshots: list[dict[str, Any]] | None = None,
    ) -> None:
        self.scenario = scenario
        self.agents = agents
        self.decisions = decisions
        self.event_log = event_log
        self.run_id = run_id
        self.world_snapshots = world_snapshots

    def export_all(self, output_dir: Path) -> dict[str, Path]:
        """Write all export files and return a mapping of name -> path.

        This is the batch-mode entry point — it writes agent_states, narratives,
        agent_summary, and kpis. When the runner uses streaming writes for
        agent_states and narratives, use :meth:`export_summary` instead.
        """
        paths: dict[str, Path] = {}
        paths["agent_states"] = self._write_agent_states(output_dir / "agent_states.jsonl")
        paths["narratives"] = self._write_narratives(output_dir / "narratives.jsonl")
        paths["world_state"] = self._write_world_state(output_dir / "world_state.jsonl")
        paths.update(self.export_summary(output_dir))
        return paths

    def export_summary(self, output_dir: Path) -> dict[str, Path]:
        """Write summary-only exports (agent_summary.csv, kpis.json).

        Use this when agent_states.jsonl and narratives.jsonl have already been
        written incrementally by the runner's per-tick callback.
        """
        paths: dict[str, Path] = {}
        paths["agent_summary"] = self._write_agent_summary(output_dir / "agent_summary.csv")
        if self.scenario.kpis:
            paths["kpis"] = self._write_kpis(output_dir / "kpis.json")
        return paths

    # -- agent states ----------------------------------------------------------

    def _write_agent_states(self, path: Path) -> Path:
        """Write per-tick agent state snapshots."""
        with path.open("w", encoding="utf-8") as f:
            for record in self._iter_agent_state_records():
                f.write(json.dumps(record) + "\n")
        return path

    def _iter_agent_state_records(self) -> list[dict[str, Any]]:
        """Build per-tick state snapshots from runtime events and decisions."""
        agent_index = {agent.id: agent for agent in self.agents}
        decisions_by_key: dict[tuple[int, str], Decision] = {
            (decision.tick, decision.agent_id): decision for decision in self.decisions
        }
        memory_by_agent: dict[str, list[dict[str, Any]]] = {
            agent.id: [] for agent in self.agents
        }
        records: list[dict[str, Any]] = []

        for event in self.event_log.events:
            if event.event_type != EventType.AGENT_ACT or not event.agent_id:
                continue
            agent = agent_index[event.agent_id]
            decision = decisions_by_key.get((event.tick, event.agent_id))
            memory_entry = {
                "tick": event.tick,
                "event": self._memory_event_text(
                    event.data.get("action", ""),
                    event.data.get("to_location", ""),
                ),
            }
            memory_by_agent[agent.id].append(memory_entry)
            records.append({
                "run_id": self.run_id,
                "tick": event.tick,
                "agent_id": agent.id,
                "agent_name": agent.name,
                "role": agent.role,
                "location": event.data.get("to_location", ""),
                "action": event.data.get("action", "unknown"),
                "mode": decision.metadata.get("mode", "") if decision else "",
                "traits": agent.traits,
                "memory_snapshot": list(memory_by_agent[agent.id][-5:]),
            })

        return records

    @staticmethod
    def _memory_event_text(action: str, location: str) -> str:
        if action == "travel":
            return f"Traveled to {location}"
        return f"Stayed at {location}"

    # -- narratives ------------------------------------------------------------

    def _write_narratives(self, path: Path) -> Path:
        """Write decision narratives as structured records for qualitative analysis."""
        with path.open("w", encoding="utf-8") as f:
            for d in self.decisions:
                if not d.reasoning:
                    continue
                record = {
                    "run_id": self.run_id,
                    "tick": d.tick,
                    "agent_id": d.agent_id,
                    "action": d.action,
                    "target": d.target,
                    "reasoning": d.reasoning,
                    "mode": d.metadata.get("mode", ""),
                    "metadata": d.metadata,
                }
                f.write(json.dumps(record) + "\n")
        return path

    # -- world state ----------------------------------------------------------

    def _write_world_state(self, path: Path) -> Path:
        """Write one serializable world snapshot per tick."""
        with path.open("w", encoding="utf-8") as f:
            for record in self._iter_world_state_records():
                f.write(json.dumps(record) + "\n")
        return path

    def _iter_world_state_records(self) -> list[dict[str, Any]]:
        """Yield per-tick world snapshots.

        Prefer exact engine-produced snapshots when available. Fall back to a
        deterministic reconstruction from the scenario and event log so the
        batch exporter can still produce `world_state.jsonl`.
        """
        if self.world_snapshots is not None:
            return list(self.world_snapshots)

        occupancy_by_tick: dict[int, dict[str, int]] = {}
        for event in self.event_log.events:
            if event.event_type != EventType.TICK_OCCUPANCY:
                continue
            tick_occupancy = occupancy_by_tick.setdefault(event.tick, {})
            tick_occupancy[event.data.get("location_id", "")] = int(
                event.data.get("occupant_count", 0)
            )

        records: list[dict[str, Any]] = []
        for tick in range(self.scenario.simulation.ticks):
            active_interventions = self._active_interventions_at(tick)
            route_multiplier_by_mode: dict[str, float] = {}
            for intervention in active_interventions:
                if intervention["target_roles"]:
                    continue
                for key, value in intervention["effects"].items():
                    if key.endswith("_cost_multiplier"):
                        mode = key.removesuffix("_cost_multiplier")
                        route_multiplier_by_mode[mode] = (
                            route_multiplier_by_mode.get(mode, 1.0) * float(value)
                        )

            records.append({
                "tick": tick,
                "tick_unit": self.scenario.simulation.tick_unit,
                "locations": [
                    {
                        "id": loc.id,
                        "name": loc.name,
                        "type": loc.type,
                        "occupant_count": occupancy_by_tick.get(tick, {}).get(loc.id, 0),
                        "capacity": loc.capacity,
                        "resources": dict(loc.resources),
                    }
                    for loc in self.scenario.locations
                ],
                "routes": [
                    {
                        "from": route.from_location,
                        "to": route.to_location,
                        "mode": route.mode,
                        "base_travel_time": route.travel_time_minutes,
                        "current_travel_time": (
                            route.travel_time_minutes
                            * route_multiplier_by_mode.get(route.mode, 1.0)
                        ),
                        "congestion": 0.0,
                    }
                    for route in self.scenario.routes
                ],
                "active_interventions": active_interventions,
            })
        return records

    def _active_interventions_at(self, tick: int) -> list[dict[str, Any]]:
        active: list[dict[str, Any]] = []
        for intervention in self.scenario.interventions:
            if intervention.tick > tick:
                continue
            expires_at_tick = (
                intervention.tick + intervention.duration
                if intervention.duration is not None
                else None
            )
            if expires_at_tick is not None and tick >= expires_at_tick:
                continue
            active.append({
                "name": intervention.name,
                "description": intervention.description,
                "activated_at_tick": intervention.tick,
                "expires_at_tick": expires_at_tick,
                "effects": dict(intervention.effects),
                "target_roles": list(intervention.target_roles),
            })
        return active

    # -- agent summary ---------------------------------------------------------

    def _write_agent_summary(self, path: Path) -> Path:
        """Write one row per agent with aggregate statistics."""
        agent_stats: dict[str, dict[str, Any]] = {}
        for agent in self.agents:
            agent_stats[agent.id] = {
                "agent_id": agent.id,
                "agent_name": agent.name,
                "role": agent.role,
                "home_location": agent.home_location,
                "work_location": agent.work_location,
                "preferred_mode": agent.preferred_mode,
                "total_trips": 0,
                "total_stays": 0,
                "modes_used": set(),
                "locations_visited": set(),
            }

        for d in self.decisions:
            stats = agent_stats.get(d.agent_id)
            if stats is None:
                continue
            if d.action == "travel":
                stats["total_trips"] += 1
                mode = d.metadata.get("mode", "")
                if mode:
                    stats["modes_used"].add(mode)
                stats["locations_visited"].add(d.target)
            else:
                stats["total_stays"] += 1

        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "agent_id", "agent_name", "role", "home_location", "work_location",
                "preferred_mode", "total_trips", "total_stays",
                "unique_modes_used", "unique_locations_visited",
            ])
            for stats in agent_stats.values():
                writer.writerow([
                    stats["agent_id"],
                    stats["agent_name"],
                    stats["role"],
                    stats["home_location"],
                    stats["work_location"],
                    stats["preferred_mode"],
                    stats["total_trips"],
                    stats["total_stays"],
                    len(stats["modes_used"]),
                    len(stats["locations_visited"]),
                ])
        return path

    # -- KPI evaluation --------------------------------------------------------

    def _write_kpis(self, path: Path) -> Path:
        """Evaluate scenario-defined KPIs and write results."""
        results: dict[str, Any] = {
            "run_id": self.run_id,
            "scenario_id": self.scenario.id,
            "kpis": {},
        }

        for kpi in self.scenario.kpis:
            kpi_result = self._evaluate_kpi(kpi)
            results["kpis"][kpi.id] = kpi_result

        path.write_text(json.dumps(results, indent=2), encoding="utf-8")
        return path

    def _evaluate_kpi(self, kpi: KPIDefinition) -> dict[str, Any]:
        """Evaluate a single KPI definition against the run data."""
        if kpi.source == "decisions":
            return self._eval_decisions_kpi(kpi)
        if kpi.source == "agent_states":
            return self._eval_agent_states_kpi(kpi)
        return {"error": f"Unsupported KPI source: {kpi.source}"}

    def _eval_decisions_kpi(self, kpi: KPIDefinition) -> dict[str, Any]:
        """Evaluate a KPI over the decisions trace."""
        per_tick: dict[int, float] = {}
        for tick in range(self.scenario.simulation.ticks):
            tick_decisions = [d for d in self.decisions if d.tick == tick]
            matching = self._filter_decisions(tick_decisions, kpi.filter)
            per_tick[tick] = self._compute_metric(kpi.metric, matching, tick_decisions)

        overall = sum(per_tick.values())
        if kpi.metric in ("mean", "ratio") and per_tick:
            overall = overall / len(per_tick)

        return {
            "name": kpi.name,
            "description": kpi.description,
            "metric": kpi.metric,
            "unit": kpi.unit,
            "overall": round(overall, 4),
            "per_tick": {str(k): round(v, 4) for k, v in per_tick.items()},
        }

    def _eval_agent_states_kpi(self, kpi: KPIDefinition) -> dict[str, Any]:
        """Evaluate a KPI based on agent state snapshots."""
        agent_states = self._iter_agent_state_records()
        per_tick: dict[int, float] = {}

        for tick in range(self.scenario.simulation.ticks):
            tick_states = [state for state in agent_states if state["tick"] == tick]
            matching = self._filter_agent_states(tick_states, kpi.filter)
            per_tick[tick] = self._compute_metric(kpi.metric, matching, tick_states)

        overall = 0.0
        if per_tick:
            overall = sum(per_tick.values()) / len(per_tick)

        return {
            "name": kpi.name,
            "description": kpi.description,
            "metric": kpi.metric,
            "unit": kpi.unit,
            "overall": round(overall, 4),
            "per_tick": {str(k): round(v, 4) for k, v in per_tick.items()},
        }

    @staticmethod
    def _filter_decisions(
        decisions: list[Decision],
        filters: dict[str, str],
    ) -> list[Decision]:
        """Filter decisions by the KPI filter criteria."""
        result = decisions
        for key, value in filters.items():
            if key == "action":
                result = [d for d in result if d.action == value]
            elif key == "mode":
                result = [d for d in result if d.metadata.get("mode") == value]
            elif key == "target":
                result = [d for d in result if d.target == value]
        return result

    @staticmethod
    def _filter_agent_states(
        agent_states: list[dict[str, Any]],
        filters: dict[str, str],
    ) -> list[dict[str, Any]]:
        """Filter agent-state rows by supported keys."""
        result = agent_states
        for key, value in filters.items():
            if key == "role":
                result = [state for state in result if state["role"] == value]
            elif key == "action":
                result = [state for state in result if state["action"] == value]
            elif key == "location":
                result = [state for state in result if state["location"] == value]
            elif key == "mode":
                result = [state for state in result if state["mode"] == value]
        return result

    @staticmethod
    def _compute_metric(
        metric: str,
        matching: list[Any],
        all_decisions: list[Any],
    ) -> float:
        if metric == "count":
            return float(len(matching))
        if metric == "ratio":
            if not all_decisions:
                return 0.0
            return len(matching) / len(all_decisions)
        if metric == "sum":
            return float(len(matching))
        if metric == "mean":
            if not all_decisions:
                return 0.0
            return len(matching) / len(all_decisions)
        return 0.0
