"""Golden-run fixture tests — ensure example scenario outputs stay stable.

Phase 6: each example scenario has a golden fixture file. If the simulation
engine changes in a way that alters outputs, these tests will fail.
Regenerate fixtures intentionally by rerunning the scenario with the fixture
seed and copying the resulting `decisions.jsonl` into `engine/tests/fixtures/`,
then rerun this test file to verify the updated fixture.
"""

from pathlib import Path

import pytest

from agora.simulation.runner import run_scenario

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
SCENARIOS_DIR = Path(__file__).resolve().parents[2] / "scenarios" / "examples"

GOLDEN_CASES = [
    ("morning_commute.yaml", 42, "morning_commute_seed42.jsonl"),
    ("vaccine_uptake.yaml", 7, "vaccine_uptake_seed7.jsonl"),
]


@pytest.mark.parametrize("scenario_file,seed,fixture_file", GOLDEN_CASES)
def test_golden_output_matches_fixture(scenario_file, seed, fixture_file, tmp_path: Path):
    result = run_scenario(
        SCENARIOS_DIR / scenario_file,
        seed=seed,
        output_dir=tmp_path / "golden",
        use_llm=False,
    )
    actual = (result.output_dir / "decisions.jsonl").read_text()
    expected = (FIXTURES_DIR / fixture_file).read_text()
    assert actual == expected, (
        f"Golden output for {scenario_file} (seed={seed}) diverged from fixture "
        f"{fixture_file} — if intentional, regenerate the fixture."
    )
