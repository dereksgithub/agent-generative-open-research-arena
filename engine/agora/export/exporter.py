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
    ) -> None:
        self.scenario = scenario
        self.agents = agents
        self.decisions = decisions
        self.event_log = event_log
        self.run_id = run_id

    def export_all(self, output_dir: Path) -> dict[str, Path]:
        """Write all export files and return a mapping of name -> path."""
        paths: dict[str, Path] = {}
        paths["agent_states"] = self._write_agent_states(output_dir / "agent_states.jsonl")
        paths["narratives"] = self._write_narratives(output_dir / "narratives.jsonl")
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
        records: list[dict[str, Any]] = []

        for event in self.event_log.events:
            if event.event_type != EventType.AGENT_ACT or not event.agent_id:
                continue
            agent = agent_index[event.agent_id]
            decision = decisions_by_key.get((event.tick, event.agent_id))
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
            })

        return records

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
