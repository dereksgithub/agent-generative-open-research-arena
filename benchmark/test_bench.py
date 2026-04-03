"""Smoke tests for the benchmark framework.

These verify the benchmarking infrastructure works — they are NOT
performance assertions. Run bench_simulation.py for real benchmarks.
"""

from pathlib import Path

from benchmark.bench_simulation import (
    BenchmarkResult,
    _build_agents_from_scenario,
    _build_grid_scenario,
    run_benchmark,
    save_results,
)


def test_grid_scenario_builds_correctly():
    scenario = _build_grid_scenario(num_agents=10, num_ticks=12)
    assert len(scenario.agents) == 10
    assert scenario.simulation.ticks == 12
    assert len(scenario.locations) == 3
    assert len(scenario.routes) == 6


def test_agents_from_scenario():
    scenario = _build_grid_scenario(num_agents=5, num_ticks=6)
    agents = _build_agents_from_scenario(scenario)
    assert len(agents) == 5
    assert all(a.current_location == "home" for a in agents)


def test_run_benchmark_returns_result():
    result = run_benchmark(num_agents=3, num_ticks=4, warmup_runs=0, measured_runs=1)
    assert isinstance(result, BenchmarkResult)
    assert result.num_agents == 3
    assert result.num_ticks == 4
    assert result.num_decisions == 12  # 3 agents * 4 ticks
    assert result.wall_time_seconds > 0
    assert result.decisions_per_second > 0


def test_save_results(tmp_path: Path):
    result = run_benchmark(num_agents=2, num_ticks=2, warmup_runs=0, measured_runs=1)
    path = save_results([result], output_dir=tmp_path)
    assert path.exists()
    assert path.suffix == ".json"
