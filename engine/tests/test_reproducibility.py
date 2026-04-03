"""Phase 6 reproducibility tests — verify deterministic behavior across runs.

These tests go beyond the basic golden-run fixture test to check that
reproducibility holds under various configurations and edge cases.
"""

import json
from pathlib import Path

from agora.simulation.runner import run_scenario

COMMUTE_PATH = Path(__file__).resolve().parents[2] / "scenarios" / "examples" / "morning_commute.yaml"
VACCINE_PATH = Path(__file__).resolve().parents[2] / "scenarios" / "examples" / "vaccine_uptake.yaml"


def _run_and_read(scenario_path: Path, seed: int, tmp_path: Path, label: str) -> dict:
    """Run a scenario and return all output file contents as strings."""
    result = run_scenario(scenario_path, seed=seed, output_dir=tmp_path / label, use_llm=False)
    return {
        name: (result.output_dir / name).read_text()
        for name in [
            "decisions.jsonl",
            "aggregate.csv",
            "events.jsonl",
            "agent_states.jsonl",
            "narratives.jsonl",
            "agent_summary.csv",
        ]
        if (result.output_dir / name).exists()
    }


def test_commute_same_seed_identical_outputs(tmp_path: Path):
    """Same scenario + same seed must produce byte-identical outputs."""
    run_a = _run_and_read(COMMUTE_PATH, seed=42, tmp_path=tmp_path, label="a")
    run_b = _run_and_read(COMMUTE_PATH, seed=42, tmp_path=tmp_path, label="b")
    for filename in run_a:
        assert run_a[filename] == run_b[filename], f"Output {filename} diverged between identical runs"


def test_vaccine_same_seed_identical_outputs(tmp_path: Path):
    """Vaccine scenario reproducibility check."""
    run_a = _run_and_read(VACCINE_PATH, seed=7, tmp_path=tmp_path, label="a")
    run_b = _run_and_read(VACCINE_PATH, seed=7, tmp_path=tmp_path, label="b")
    for filename in run_a:
        assert run_a[filename] == run_b[filename], f"Output {filename} diverged between identical runs"


def test_different_seeds_produce_different_run_ids(tmp_path: Path):
    """Different seeds must produce different run IDs."""
    r1 = run_scenario(COMMUTE_PATH, seed=1, output_dir=tmp_path / "s1", use_llm=False)
    r2 = run_scenario(COMMUTE_PATH, seed=2, output_dir=tmp_path / "s2", use_llm=False)
    assert r1.run_id != r2.run_id


def test_run_id_deterministic(tmp_path: Path):
    """Same inputs must produce the same run_id."""
    r1 = run_scenario(COMMUTE_PATH, seed=42, output_dir=tmp_path / "d1", use_llm=False)
    r2 = run_scenario(COMMUTE_PATH, seed=42, output_dir=tmp_path / "d2", use_llm=False)
    assert r1.run_id == r2.run_id


def test_event_log_deterministic(tmp_path: Path):
    """Event logs must be identical for same-seed runs."""
    r1 = run_scenario(COMMUTE_PATH, seed=42, output_dir=tmp_path / "e1", use_llm=False)
    r2 = run_scenario(COMMUTE_PATH, seed=42, output_dir=tmp_path / "e2", use_llm=False)
    events_1 = (r1.output_dir / "events.jsonl").read_text()
    events_2 = (r2.output_dir / "events.jsonl").read_text()
    assert events_1 == events_2


def test_kpis_deterministic(tmp_path: Path):
    """KPI values must be identical for same-seed runs."""
    r1 = run_scenario(COMMUTE_PATH, seed=42, output_dir=tmp_path / "k1", use_llm=False)
    r2 = run_scenario(COMMUTE_PATH, seed=42, output_dir=tmp_path / "k2", use_llm=False)
    kpi_1 = json.loads((r1.output_dir / "kpis.json").read_text())
    kpi_2 = json.loads((r2.output_dir / "kpis.json").read_text())
    assert kpi_1 == kpi_2


def test_metadata_seed_recorded(tmp_path: Path):
    """The metadata file must record the seed used."""
    result = run_scenario(COMMUTE_PATH, seed=99, output_dir=tmp_path / "out", use_llm=False)
    meta = json.loads((result.output_dir / "metadata.json").read_text())
    assert meta["seed"] == 99
