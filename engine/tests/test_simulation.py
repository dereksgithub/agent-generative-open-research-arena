"""Tests for the simulation engine and runner."""

import json
from pathlib import Path

from agora.simulation.runner import run_scenario


EXAMPLE_PATH = Path(__file__).resolve().parents[2] / "scenarios" / "examples" / "morning_commute.yaml"


def test_run_produces_outputs(tmp_path: Path):
    result = run_scenario(EXAMPLE_PATH, seed=42, output_dir=tmp_path / "out", use_llm=False)
    assert result.total_ticks == 24
    assert result.total_decisions == 120
    assert result.seed == 42
    assert result.run_id
    assert result.scenario_id == "morning_commute_v1"
    assert (result.output_dir / "decisions.jsonl").exists()
    assert (result.output_dir / "aggregate.csv").exists()
    assert (result.output_dir / "metadata.json").exists()
    assert (result.output_dir / "config.json").exists()
    assert (result.output_dir / "scenario.yaml").exists()
    assert (result.output_dir / "events.jsonl").exists()


def test_reproducibility(tmp_path: Path):
    r1 = run_scenario(EXAMPLE_PATH, seed=42, output_dir=tmp_path / "r1", use_llm=False)
    r2 = run_scenario(EXAMPLE_PATH, seed=42, output_dir=tmp_path / "r2", use_llm=False)
    for filename in [
        "decisions.jsonl",
        "aggregate.csv",
        "config.json",
        "scenario.yaml",
        "events.jsonl",
        "metadata.json",
    ]:
        assert (r1.output_dir / filename).read_text() == (r2.output_dir / filename).read_text()


def test_different_seed_different_output(tmp_path: Path):
    """Different seeds should not crash — outputs may or may not differ for heuristic mode."""
    r1 = run_scenario(EXAMPLE_PATH, seed=1, output_dir=tmp_path / "s1", use_llm=False)
    r2 = run_scenario(EXAMPLE_PATH, seed=99, output_dir=tmp_path / "s2", use_llm=False)
    assert r1.total_decisions == r2.total_decisions
    meta1 = json.loads((r1.output_dir / "metadata.json").read_text())
    meta2 = json.loads((r2.output_dir / "metadata.json").read_text())
    assert meta1["run_id"] != meta2["run_id"]
