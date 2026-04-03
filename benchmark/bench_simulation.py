"""Performance benchmarks for AGORA simulation runs.

Measures wall-clock time, memory usage, and throughput for simulation
execution under different configurations. Results are written to
benchmark/results/ as JSON for tracking over time.

Usage:
    python -m benchmark.bench_simulation
    python -m benchmark.bench_simulation --agents 50 --ticks 100
"""

from __future__ import annotations

import argparse
import json
import os
import resource
import statistics
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Ensure engine is importable
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "engine"))

from agora import __version__
from agora.agents.agent import Agent
from agora.agents.strategy import HeuristicStrategy
from agora.scenarios.schema import ScenarioSpec
from agora.simulation.engine import SimulationEngine


# ---------------------------------------------------------------------------
# Benchmark result model
# ---------------------------------------------------------------------------

@dataclass
class BenchmarkResult:
    """Captured metrics from a single benchmark run."""

    name: str
    num_agents: int
    num_ticks: int
    num_decisions: int
    wall_time_seconds: float
    peak_memory_mb: float
    decisions_per_second: float
    ticks_per_second: float
    event_count: int
    seed: int
    agora_version: str
    timestamp: str
    extra: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Scenario factories for benchmarking
# ---------------------------------------------------------------------------

def _build_grid_scenario(num_agents: int, num_ticks: int) -> ScenarioSpec:
    """Build a synthetic scenario with N agents on a simple grid.

    Creates a home location, a work location, and routes between them.
    All agents commute in morning ticks and return in evening ticks.
    """
    locations = [
        {"id": "home", "name": "Home District", "type": "residential", "x": 0, "y": 0},
        {"id": "work", "name": "Work District", "type": "commercial", "x": 5, "y": 0},
        {"id": "park", "name": "City Park", "type": "generic", "x": 2.5, "y": 2},
    ]
    routes = [
        {"from": "home", "to": "work", "mode": "drive", "travel_time_minutes": 15},
        {"from": "home", "to": "work", "mode": "transit", "travel_time_minutes": 25},
        {"from": "work", "to": "home", "mode": "drive", "travel_time_minutes": 15},
        {"from": "work", "to": "home", "mode": "transit", "travel_time_minutes": 25},
        {"from": "home", "to": "park", "mode": "walk", "travel_time_minutes": 30},
        {"from": "park", "to": "home", "mode": "walk", "travel_time_minutes": 30},
    ]
    agents = []
    for i in range(num_agents):
        mode = ["drive", "transit", "walk"][i % 3]
        agents.append({
            "id": f"agent_{i:04d}",
            "name": f"Agent {i}",
            "role": "commuter",
            "home_location": "home",
            "work_location": "work",
            "preferred_mode": mode,
        })

    return ScenarioSpec.model_validate({
        "id": f"bench_grid_{num_agents}a_{num_ticks}t",
        "name": f"bench_grid_{num_agents}",
        "simulation": {"ticks": num_ticks, "tick_unit": "hour", "seed": 42},
        "locations": locations,
        "routes": routes,
        "agents": agents,
    })


def _build_agents_from_scenario(scenario: ScenarioSpec) -> list[Agent]:
    """Build agent objects from a scenario spec."""
    agents = []
    for persona in scenario.agents:
        agents.append(Agent(
            id=persona.id,
            name=persona.name,
            role=persona.role,
            traits=list(persona.traits),
            home_location=persona.home_location,
            work_location=persona.work_location,
            preferred_mode=persona.preferred_mode,
            schedule=dict(persona.schedule),
            current_location=persona.home_location,
        ))
    return agents


# ---------------------------------------------------------------------------
# Benchmark runner
# ---------------------------------------------------------------------------

def run_benchmark(
    num_agents: int = 10,
    num_ticks: int = 24,
    seed: int = 42,
    warmup_runs: int = 1,
    measured_runs: int = 3,
) -> BenchmarkResult:
    """Run the simulation benchmark and return collected metrics."""
    scenario = _build_grid_scenario(num_agents, num_ticks)

    # Warmup
    for _ in range(warmup_runs):
        agents = _build_agents_from_scenario(scenario)
        engine = SimulationEngine(scenario, agents, seed=seed, strategy=HeuristicStrategy())
        engine.run()

    # Measured runs
    times: list[float] = []
    last_decisions = 0
    last_event_count = 0
    peak_mem = 0.0

    for _ in range(measured_runs):
        agents = _build_agents_from_scenario(scenario)
        engine = SimulationEngine(scenario, agents, seed=seed, strategy=HeuristicStrategy())

        t0 = time.perf_counter()
        decisions = engine.run()
        elapsed = time.perf_counter() - t0

        times.append(elapsed)
        last_decisions = len(decisions)
        last_event_count = len(engine.event_log)

        # Peak RSS (macOS/Linux)
        usage = resource.getrusage(resource.RUSAGE_SELF)
        # ru_maxrss is in bytes on Linux, kilobytes on macOS
        if sys.platform == "darwin":
            peak_mem = max(peak_mem, usage.ru_maxrss / (1024 * 1024))
        else:
            peak_mem = max(peak_mem, usage.ru_maxrss / 1024)

    median_time = statistics.median(times)

    return BenchmarkResult(
        name=f"grid_{num_agents}agents_{num_ticks}ticks",
        num_agents=num_agents,
        num_ticks=num_ticks,
        num_decisions=last_decisions,
        wall_time_seconds=round(median_time, 4),
        peak_memory_mb=round(peak_mem, 2),
        decisions_per_second=round(last_decisions / median_time, 1) if median_time > 0 else 0,
        ticks_per_second=round(num_ticks / median_time, 1) if median_time > 0 else 0,
        event_count=last_event_count,
        seed=seed,
        agora_version=__version__,
        timestamp=datetime.now(timezone.utc).isoformat(),
        extra={
            "warmup_runs": warmup_runs,
            "measured_runs": measured_runs,
            "all_times_seconds": [round(t, 4) for t in times],
        },
    )


# ---------------------------------------------------------------------------
# Standard benchmark suite
# ---------------------------------------------------------------------------

STANDARD_CONFIGS = [
    {"num_agents": 5, "num_ticks": 24},     # tiny (matches example scenario)
    {"num_agents": 20, "num_ticks": 48},     # small
    {"num_agents": 50, "num_ticks": 100},    # medium
    {"num_agents": 100, "num_ticks": 100},   # large
    {"num_agents": 200, "num_ticks": 200},   # stress
]


def run_suite(configs: list[dict] | None = None) -> list[BenchmarkResult]:
    """Run the full benchmark suite and return all results."""
    configs = configs or STANDARD_CONFIGS
    results: list[BenchmarkResult] = []
    for cfg in configs:
        print(f"  Benchmarking: {cfg['num_agents']} agents x {cfg['num_ticks']} ticks ...", end=" ", flush=True)
        result = run_benchmark(**cfg)
        print(f"{result.wall_time_seconds}s ({result.decisions_per_second} decisions/s)")
        results.append(result)
    return results


def save_results(results: list[BenchmarkResult], output_dir: Path | None = None) -> Path:
    """Save benchmark results to a timestamped JSON file."""
    out_dir = output_dir or Path(__file__).parent / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = out_dir / f"bench_{timestamp}.json"
    data = {
        "agora_version": __version__,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "results": [asdict(r) for r in results],
    }
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="AGORA simulation benchmarks")
    parser.add_argument("--agents", type=int, default=None, help="Number of agents (runs single config)")
    parser.add_argument("--ticks", type=int, default=None, help="Number of ticks (runs single config)")
    parser.add_argument("--suite", action="store_true", help="Run the full standard suite")
    parser.add_argument("--output-dir", type=Path, default=None, help="Output directory for results")
    args = parser.parse_args()

    print(f"AGORA Benchmark Suite v{__version__}")
    print("=" * 50)

    if args.agents or args.ticks:
        num_agents = args.agents or 10
        num_ticks = args.ticks or 24
        result = run_benchmark(num_agents=num_agents, num_ticks=num_ticks)
        results = [result]
        print(f"  {result.name}: {result.wall_time_seconds}s "
              f"({result.decisions_per_second} decisions/s, "
              f"{result.peak_memory_mb} MB peak)")
    elif args.suite:
        results = run_suite()
    else:
        # Default: run the small configs only
        results = run_suite(STANDARD_CONFIGS[:3])

    path = save_results(results, args.output_dir)
    print(f"\nResults saved to: {path}")


if __name__ == "__main__":
    main()
