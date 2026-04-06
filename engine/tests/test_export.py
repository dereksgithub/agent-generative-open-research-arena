"""Tests for the dataset export layer (Phase 3)."""

import csv
import json
from pathlib import Path

from agora.agents.strategy import HeuristicStrategy
from agora.export.exporter import DatasetExporter
from agora.scenarios.loader import load_scenario
from agora.simulation.engine import SimulationEngine
from agora.simulation.runner import run_scenario
from agora.simulation.runner import _build_agents

COMMUTE_PATH = Path(__file__).resolve().parents[2] / "scenarios" / "examples" / "morning_commute.yaml"
VACCINE_PATH = Path(__file__).resolve().parents[2] / "scenarios" / "examples" / "vaccine_uptake.yaml"


def test_export_produces_all_files(tmp_path: Path):
    result = run_scenario(COMMUTE_PATH, seed=42, output_dir=tmp_path / "out", use_llm=False)
    out = result.output_dir
    assert (out / "agent_states.jsonl").exists()
    assert (out / "narratives.jsonl").exists()
    assert (out / "agent_summary.csv").exists()
    assert (out / "kpis.json").exists()


def test_agent_states_has_correct_records(tmp_path: Path):
    result = run_scenario(COMMUTE_PATH, seed=42, output_dir=tmp_path / "out", use_llm=False)
    states = []
    with (result.output_dir / "agent_states.jsonl").open() as f:
        for line in f:
            states.append(json.loads(line))
    # 5 agents * 24 ticks = 120 records
    assert len(states) == 120
    assert all("run_id" in s for s in states)
    assert all("tick" in s for s in states)
    assert all("agent_id" in s for s in states)
    assert all("role" in s for s in states)


def test_agent_states_preserve_historical_locations(tmp_path: Path):
    result = run_scenario(COMMUTE_PATH, seed=42, output_dir=tmp_path / "out", use_llm=False)
    alice_states: dict[int, dict] = {}
    with (result.output_dir / "agent_states.jsonl").open() as f:
        for line in f:
            record = json.loads(line)
            if record["agent_id"] == "alice":
                alice_states[record["tick"]] = record

    assert alice_states[7]["location"] == "town_centre"
    assert alice_states[8]["location"] == "town_centre"
    assert alice_states[9]["location"] == "town_centre"
    assert alice_states[10]["location"] == "town_centre"


def test_narratives_have_reasoning(tmp_path: Path):
    result = run_scenario(COMMUTE_PATH, seed=42, output_dir=tmp_path / "out", use_llm=False)
    narratives = []
    with (result.output_dir / "narratives.jsonl").open() as f:
        for line in f:
            narratives.append(json.loads(line))
    assert len(narratives) > 0
    assert all("reasoning" in n for n in narratives)
    assert all(n["reasoning"] for n in narratives)  # no empty reasoning


def test_agent_summary_csv_structure(tmp_path: Path):
    result = run_scenario(COMMUTE_PATH, seed=42, output_dir=tmp_path / "out", use_llm=False)
    with (result.output_dir / "agent_summary.csv").open() as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    assert len(rows) == 5
    assert all("total_trips" in r for r in rows)
    assert all("total_stays" in r for r in rows)
    assert all("unique_modes_used" in r for r in rows)


def test_kpi_evaluation(tmp_path: Path):
    result = run_scenario(COMMUTE_PATH, seed=42, output_dir=tmp_path / "out", use_llm=False)
    kpi_data = json.loads((result.output_dir / "kpis.json").read_text())
    assert "kpis" in kpi_data
    assert "drive_trips" in kpi_data["kpis"]
    assert "transit_share" in kpi_data["kpis"]
    assert "total_commuters" in kpi_data["kpis"]

    drive = kpi_data["kpis"]["drive_trips"]
    assert drive["overall"] > 0
    assert "per_tick" in drive
    assert len(drive["per_tick"]) == 24

    commuters = kpi_data["kpis"]["total_commuters"]
    assert commuters["overall"] == 3
    assert commuters["per_tick"]["0"] == 3
    assert commuters["per_tick"]["23"] == 3


def test_kpi_transit_share_at_intervention_tick(tmp_path: Path):
    """At tick 7 (congestion charge), transit share should be high."""
    result = run_scenario(COMMUTE_PATH, seed=42, output_dir=tmp_path / "out", use_llm=False)
    kpi_data = json.loads((result.output_dir / "kpis.json").read_text())
    transit = kpi_data["kpis"]["transit_share"]
    # At tick 7, everyone switches to transit due to congestion charge
    assert transit["per_tick"]["7"] == 1.0


def test_vaccine_scenario_loads_and_runs(tmp_path: Path):
    result = run_scenario(VACCINE_PATH, seed=7, output_dir=tmp_path / "out", use_llm=False)
    assert result.total_ticks == 12
    assert result.total_decisions == 96  # 8 agents * 12 ticks
    assert result.scenario_id == "vaccine_uptake_v1"
    assert (result.output_dir / "kpis.json").exists()


def test_vaccine_kpis(tmp_path: Path):
    result = run_scenario(VACCINE_PATH, seed=7, output_dir=tmp_path / "out", use_llm=False)
    kpi_data = json.loads((result.output_dir / "kpis.json").read_text())
    assert "clinic_visits" in kpi_data["kpis"]
    assert "parent_count" in kpi_data["kpis"]
    assert kpi_data["kpis"]["parent_count"]["overall"] == 2
    assert kpi_data["kpis"]["parent_count"]["per_tick"]["0"] == 2


def test_enriched_persona_fields_in_config(tmp_path: Path):
    result = run_scenario(COMMUTE_PATH, seed=42, output_dir=tmp_path / "out", use_llm=False)
    config = json.loads((result.output_dir / "config.json").read_text())
    alice = config["scenario"]["agents"][0]
    assert alice["age"] == 34
    assert alice["income_bracket"] == "medium"
    assert alice["household_size"] == 3
    assert "backstory" in alice
    assert len(alice["values"]) > 0


def test_export_all_batch_mode_writes_world_state_and_historical_memory(tmp_path: Path):
    scenario = load_scenario(COMMUTE_PATH)
    agents = _build_agents(scenario)
    engine = SimulationEngine(
        scenario,
        agents,
        seed=42,
        strategy=HeuristicStrategy(),
    )
    decisions = engine.run()

    exporter = DatasetExporter(
        scenario,
        agents,
        decisions,
        engine.event_log,
        engine.state.run_id,
    )
    out = tmp_path / "batch_out"
    out.mkdir()
    paths = exporter.export_all(out)

    assert paths["world_state"].exists()
    world_state = [
        json.loads(line)
        for line in (out / "world_state.jsonl").read_text().splitlines()
    ]
    assert len(world_state) == scenario.simulation.ticks
    assert world_state[0]["tick"] == 0
    assert world_state[-1]["tick"] == scenario.simulation.ticks - 1

    alice_states = []
    for line in (out / "agent_states.jsonl").read_text().splitlines():
        record = json.loads(line)
        if record["agent_id"] == "alice":
            alice_states.append(record)
    alice_states.sort(key=lambda record: record["tick"])

    assert len(alice_states[0]["memory_snapshot"]) == 1
    assert alice_states[0]["memory_snapshot"][-1]["tick"] == 0
    assert len(alice_states[4]["memory_snapshot"]) == 5
    assert alice_states[4]["memory_snapshot"][-1]["tick"] == 4
    assert alice_states[10]["memory_snapshot"][-1]["tick"] == 10
