"""Run orchestrator — loads scenario, runs engine, writes structured outputs."""

from __future__ import annotations

import csv
import json
import logging
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agora import __version__
from agora.agents.agent import Agent, Decision
from agora.agents.strategy import DecisionStrategy, HeuristicStrategy, LLMStrategy
from agora.export.exporter import DatasetExporter
from agora.scenarios.loader import load_scenario
from agora.scenarios.schema import ScenarioSpec

from .engine import SimulationEngine

logger = logging.getLogger(__name__)

# Default output root relative to cwd
_DEFAULT_RUNS_DIR = Path("runs")


@dataclass
class RunResult:
    """Summary returned after a successful simulation run."""

    output_dir: Path
    scenario_name: str
    total_ticks: int
    total_decisions: int
    seed: int | None
    run_id: str
    scenario_id: str
    llm_accounting: dict[str, Any] = field(default_factory=dict)
    llm_settings: dict[str, Any] = field(default_factory=dict)
    llm_status: dict[str, Any] = field(default_factory=dict)


def run_scenario(
    scenario_path: Path,
    *,
    seed: int | None = None,
    output_dir: Path | None = None,
    use_llm: bool = False,
    llm_provider: str = "openai",
    llm_model: str | None = None,
    llm_api_key: str | None = None,
    llm_base_url: str | None = None,
    llm_temperature: float = 0.4,
    llm_max_tokens: int = 512,
    llm_timeout: float = 60.0,
    llm_max_retries: int = 2,
    llm_cache_dir: Path | None = None,
    llm_max_consecutive_failures: int = 3,
) -> RunResult:
    """Load, execute, and persist a full scenario run."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # 1. Load and validate scenario
    logger.info("Loading scenario: %s", scenario_path)
    scenario = load_scenario(scenario_path)

    # Override seed if provided via CLI
    effective_seed = seed if seed is not None else scenario.simulation.seed

    # 2. Build agents from persona definitions
    agents = _build_agents(scenario)

    # 3. Prepare output directory
    out = _prepare_output_dir(scenario, output_dir)
    logger.info("Output directory: %s", out)

    # 4. Snapshot config
    _write_config_snapshot(out, scenario, scenario_path, effective_seed)

    # 5. Build strategy
    strategy: DecisionStrategy
    if use_llm:
        # Default cache dir inside the output directory
        cache = llm_cache_dir or out / ".prompt_cache"
        strategy = LLMStrategy(
            provider=llm_provider,
            model=llm_model,
            api_key=llm_api_key,
            base_url=llm_base_url,
            temperature=llm_temperature,
            max_tokens=llm_max_tokens,
            timeout=llm_timeout,
            max_retries=llm_max_retries,
            cache_dir=cache,
            max_consecutive_failures=llm_max_consecutive_failures,
        )
        logger.info("Using LLM strategy: provider=%s model=%s", llm_provider, llm_model or "(default)")
    else:
        strategy = HeuristicStrategy()
        logger.info("Using heuristic strategy (no LLM calls)")

    # 6. Run simulation
    engine = SimulationEngine(scenario, agents, seed=effective_seed, strategy=strategy)

    # Attach event log to LLM strategy for audit logging
    if isinstance(strategy, LLMStrategy):
        strategy.set_event_log(engine.event_log)

    logger.info(
        "Running '%s': %d agents, %d ticks (run_id=%s)",
        scenario.name,
        len(agents),
        scenario.simulation.ticks,
        engine.state.run_id,
    )
    decisions = engine.run()

    # 7. Write outputs
    _write_decisions_jsonl(out / "decisions.jsonl", decisions)
    _write_aggregate_csv(out / "aggregate.csv", decisions, scenario)

    # Collect LLM accounting if applicable
    llm_accounting: dict[str, Any] = {}
    llm_settings: dict[str, Any] = {}
    llm_status: dict[str, Any] = {}
    if isinstance(strategy, LLMStrategy):
        llm_accounting = strategy.get_accounting()
        llm_settings = strategy.get_settings()
        llm_status = strategy.get_status()

    _write_metadata(
        out / "metadata.json",
        scenario,
        effective_seed,
        decisions,
        engine.state.run_id,
        engine.strategy_name,
        llm_accounting=llm_accounting,
        llm_settings=llm_settings,
        llm_status=llm_status,
    )
    engine.event_log.write_jsonl(out / "events.jsonl")

    # 8. Dataset exports
    exporter = DatasetExporter(scenario, agents, decisions, engine.event_log, engine.state.run_id)
    exporter.export_all(out)

    # 9. Close LLM client
    if isinstance(strategy, LLMStrategy):
        import asyncio
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            loop.create_task(strategy.close())
        else:
            asyncio.run(strategy.close())

    logger.info("Run complete: %d decisions written", len(decisions))
    return RunResult(
        output_dir=out,
        scenario_name=scenario.name,
        total_ticks=scenario.simulation.ticks,
        total_decisions=len(decisions),
        seed=effective_seed,
        run_id=engine.state.run_id,
        scenario_id=scenario.id or "",
        llm_accounting=llm_accounting,
        llm_settings=llm_settings,
        llm_status=llm_status,
    )


# -- agent construction -------------------------------------------------------

def _build_agents(scenario: ScenarioSpec) -> list[Agent]:
    agents: list[Agent] = []
    for persona in scenario.agents:
        agent = Agent(
            id=persona.id,
            name=persona.name,
            role=persona.role,
            traits=list(persona.traits),
            home_location=persona.home_location,
            work_location=persona.work_location,
            preferred_mode=persona.preferred_mode,
            schedule=dict(persona.schedule),
            current_location=persona.home_location,
        )
        # Carry enriched persona fields for LLM prompts
        agent._persona_values = list(persona.values)
        agent._persona_backstory = persona.backstory
        agent._persona_income_bracket = persona.income_bracket
        agent._persona_age = persona.age
        agent._persona_household_size = persona.household_size
        agents.append(agent)
    return agents


# -- output helpers ------------------------------------------------------------

def _prepare_output_dir(scenario: ScenarioSpec, output_dir: Path | None) -> Path:
    if output_dir:
        out = output_dir.resolve()
    else:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        out = _DEFAULT_RUNS_DIR / scenario.name / timestamp
    out.mkdir(parents=True, exist_ok=True)
    return out


def _write_config_snapshot(
    out: Path,
    scenario: ScenarioSpec,
    source_path: Path,
    seed: int | None,
) -> None:
    # Copy original YAML
    shutil.copy2(source_path, out / "scenario.yaml")
    # Write resolved config as JSON
    config = {
        "scenario": scenario.model_dump(mode="json"),
        "effective_seed": seed,
        "agora_version": __version__,
    }
    (out / "config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")


def _write_decisions_jsonl(path: Path, decisions: list[Decision]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for d in decisions:
            record = {
                "tick": d.tick,
                "agent_id": d.agent_id,
                "action": d.action,
                "target": d.target,
                "reasoning": d.reasoning,
                "metadata": d.metadata,
            }
            f.write(json.dumps(record) + "\n")


def _write_aggregate_csv(
    path: Path,
    decisions: list[Decision],
    scenario: ScenarioSpec,
) -> None:
    """Write per-tick aggregate stats."""
    tick_stats: dict[int, dict[str, int]] = {}
    for d in decisions:
        stats = tick_stats.setdefault(d.tick, {"travel": 0, "stay": 0})
        stats[d.action] = stats.get(d.action, 0) + 1

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["tick", "travel_count", "stay_count", "total_agents"])
        for tick in range(scenario.simulation.ticks):
            stats = tick_stats.get(tick, {})
            writer.writerow([
                tick,
                stats.get("travel", 0),
                stats.get("stay", 0),
                len(scenario.agents),
            ])


def _write_metadata(
    path: Path,
    scenario: ScenarioSpec,
    seed: int | None,
    decisions: list[Decision],
    run_id: str = "",
    strategy_name: str = "",
    llm_accounting: dict[str, Any] | None = None,
    llm_settings: dict[str, Any] | None = None,
    llm_status: dict[str, Any] | None = None,
) -> None:
    meta: dict[str, Any] = {
        "agora_version": __version__,
        "run_id": run_id,
        "scenario_id": scenario.id,
        "scenario_name": scenario.name,
        "domain": scenario.domain,
        "decision_mode": strategy_name,
        "total_ticks": scenario.simulation.ticks,
        "total_agents": len(scenario.agents),
        "total_decisions": len(decisions),
        "seed": seed,
    }
    if llm_accounting:
        meta["llm_accounting"] = llm_accounting
    if llm_settings:
        meta["llm_settings"] = llm_settings
    if llm_status:
        meta["llm_status"] = llm_status
    path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
