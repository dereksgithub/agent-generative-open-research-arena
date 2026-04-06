"""Tests for output file contracts — verify the structure and schema of every
output file produced by a simulation run.

Phase 6: these tests ensure downstream analysis scripts can rely on stable
field names, types, and file formats across AGORA versions.
"""

import csv
import json
from pathlib import Path

import pytest

from agora.simulation.runner import run_scenario

COMMUTE_PATH = Path(__file__).resolve().parents[2] / "scenarios" / "examples" / "morning_commute.yaml"
VACCINE_PATH = Path(__file__).resolve().parents[2] / "scenarios" / "examples" / "vaccine_uptake.yaml"


@pytest.fixture(scope="module")
def commute_run(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("commute")
    result = run_scenario(COMMUTE_PATH, seed=42, output_dir=out, use_llm=False)
    return result.output_dir


@pytest.fixture(scope="module")
def vaccine_run(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("vaccine")
    result = run_scenario(VACCINE_PATH, seed=7, output_dir=out, use_llm=False)
    return result.output_dir


# -- decisions.jsonl contract -------------------------------------------------

class TestDecisionsContract:
    REQUIRED_FIELDS = {"tick", "agent_id", "action", "target", "reasoning", "metadata"}

    def test_every_line_is_valid_json(self, commute_run: Path):
        for line in (commute_run / "decisions.jsonl").read_text().splitlines():
            json.loads(line)

    def test_required_fields_present(self, commute_run: Path):
        for line in (commute_run / "decisions.jsonl").read_text().splitlines():
            record = json.loads(line)
            assert self.REQUIRED_FIELDS.issubset(record.keys()), (
                f"Missing fields: {self.REQUIRED_FIELDS - record.keys()}"
            )

    def test_tick_is_non_negative_int(self, commute_run: Path):
        for line in (commute_run / "decisions.jsonl").read_text().splitlines():
            record = json.loads(line)
            assert isinstance(record["tick"], int)
            assert record["tick"] >= 0

    def test_action_is_known_value(self, commute_run: Path):
        for line in (commute_run / "decisions.jsonl").read_text().splitlines():
            record = json.loads(line)
            assert record["action"] in {"travel", "stay"}

    def test_metadata_is_dict(self, commute_run: Path):
        for line in (commute_run / "decisions.jsonl").read_text().splitlines():
            record = json.loads(line)
            assert isinstance(record["metadata"], dict)


# -- metadata.json contract ---------------------------------------------------

class TestMetadataContract:
    REQUIRED_FIELDS = {
        "agora_version", "run_id", "scenario_id", "scenario_name",
        "domain", "decision_mode", "total_ticks", "total_agents",
        "total_decisions", "seed",
    }

    def test_required_fields_present(self, commute_run: Path):
        meta = json.loads((commute_run / "metadata.json").read_text())
        assert self.REQUIRED_FIELDS.issubset(meta.keys())

    def test_types_are_correct(self, commute_run: Path):
        meta = json.loads((commute_run / "metadata.json").read_text())
        assert isinstance(meta["agora_version"], str)
        assert isinstance(meta["run_id"], str)
        assert isinstance(meta["total_ticks"], int)
        assert isinstance(meta["total_agents"], int)
        assert isinstance(meta["total_decisions"], int)
        assert isinstance(meta["seed"], int)

    def test_counts_are_consistent(self, commute_run: Path):
        meta = json.loads((commute_run / "metadata.json").read_text())
        decisions = (commute_run / "decisions.jsonl").read_text().strip().splitlines()
        assert meta["total_decisions"] == len(decisions)
        assert meta["total_ticks"] == 24
        assert meta["total_agents"] == 5


# -- config.json contract -----------------------------------------------------

class TestConfigContract:
    def test_has_scenario_and_seed(self, commute_run: Path):
        config = json.loads((commute_run / "config.json").read_text())
        assert "scenario" in config
        assert "effective_seed" in config
        assert "agora_version" in config

    def test_scenario_is_full_dump(self, commute_run: Path):
        config = json.loads((commute_run / "config.json").read_text())
        scenario = config["scenario"]
        assert "name" in scenario
        assert "locations" in scenario
        assert "agents" in scenario
        assert "routes" in scenario
        assert "simulation" in scenario


# -- aggregate.csv contract ---------------------------------------------------

class TestAggregateContract:
    REQUIRED_COLUMNS = {"tick", "travel_count", "stay_count", "total_agents"}

    def test_has_required_columns(self, commute_run: Path):
        with (commute_run / "aggregate.csv").open() as f:
            reader = csv.DictReader(f)
            assert self.REQUIRED_COLUMNS.issubset(set(reader.fieldnames or []))

    def test_has_one_row_per_tick(self, commute_run: Path):
        with (commute_run / "aggregate.csv").open() as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 24

    def test_tick_values_are_sequential(self, commute_run: Path):
        with (commute_run / "aggregate.csv").open() as f:
            rows = list(csv.DictReader(f))
        ticks = [int(r["tick"]) for r in rows]
        assert ticks == list(range(24))


# -- events.jsonl contract ----------------------------------------------------

class TestEventsContract:
    REQUIRED_FIELDS = {"event_id", "run_id", "tick", "event_type"}

    def test_every_line_is_valid_json(self, commute_run: Path):
        for line in (commute_run / "events.jsonl").read_text().splitlines():
            json.loads(line)

    def test_required_fields_present(self, commute_run: Path):
        for line in (commute_run / "events.jsonl").read_text().splitlines():
            record = json.loads(line)
            assert self.REQUIRED_FIELDS.issubset(record.keys())

    def test_event_ids_are_sequential(self, commute_run: Path):
        events = [
            json.loads(line)
            for line in (commute_run / "events.jsonl").read_text().splitlines()
        ]
        ids = [e["event_id"] for e in events]
        assert ids == list(range(len(ids)))

    def test_starts_with_run_start_ends_with_run_end(self, commute_run: Path):
        events = [
            json.loads(line)
            for line in (commute_run / "events.jsonl").read_text().splitlines()
        ]
        assert events[0]["event_type"] == "run_start"
        assert events[-1]["event_type"] == "run_end"

    def test_all_events_share_run_id(self, commute_run: Path):
        events = [
            json.loads(line)
            for line in (commute_run / "events.jsonl").read_text().splitlines()
        ]
        run_ids = {e["run_id"] for e in events}
        assert len(run_ids) == 1


# -- agent_states.jsonl contract -----------------------------------------------

class TestAgentStatesContract:
    REQUIRED_FIELDS = {"run_id", "tick", "agent_id", "agent_name", "role", "location", "action"}

    def test_required_fields_present(self, commute_run: Path):
        for line in (commute_run / "agent_states.jsonl").read_text().splitlines():
            record = json.loads(line)
            assert self.REQUIRED_FIELDS.issubset(record.keys())

    def test_record_count_matches_agents_times_ticks(self, commute_run: Path):
        lines = (commute_run / "agent_states.jsonl").read_text().strip().splitlines()
        assert len(lines) == 5 * 24  # 5 agents, 24 ticks

    def test_memory_snapshot_present_and_valid(self, commute_run: Path):
        for line in (commute_run / "agent_states.jsonl").read_text().splitlines():
            record = json.loads(line)
            assert "memory_snapshot" in record
            snapshot = record["memory_snapshot"]
            assert isinstance(snapshot, list)
            for entry in snapshot:
                assert "tick" in entry and isinstance(entry["tick"], int)
                assert "event" in entry and isinstance(entry["event"], str)

    def test_memory_window_grows_then_caps_at_five(self, commute_run: Path):
        records = [
            json.loads(line)
            for line in (commute_run / "agent_states.jsonl").read_text().splitlines()
        ]
        # Pick one agent and check window size by tick
        agent_id = records[0]["agent_id"]
        agent_records = sorted(
            [r for r in records if r["agent_id"] == agent_id],
            key=lambda r: r["tick"],
        )
        for r in agent_records:
            expected_len = min(r["tick"] + 1, 5)
            assert len(r["memory_snapshot"]) == expected_len, (
                f"tick={r['tick']}: expected {expected_len} memory entries, got {len(r['memory_snapshot'])}"
            )


# -- narratives.jsonl contract -------------------------------------------------

class TestNarrativesContract:
    REQUIRED_FIELDS = {"run_id", "tick", "agent_id", "action", "target", "reasoning"}

    def test_required_fields_present(self, commute_run: Path):
        for line in (commute_run / "narratives.jsonl").read_text().splitlines():
            record = json.loads(line)
            assert self.REQUIRED_FIELDS.issubset(record.keys())

    def test_no_empty_reasoning(self, commute_run: Path):
        for line in (commute_run / "narratives.jsonl").read_text().splitlines():
            record = json.loads(line)
            assert record["reasoning"]


# -- agent_summary.csv contract ------------------------------------------------

class TestAgentSummaryContract:
    REQUIRED_COLUMNS = {
        "agent_id", "agent_name", "role", "home_location", "work_location",
        "preferred_mode", "total_trips", "total_stays",
    }

    def test_has_required_columns(self, commute_run: Path):
        with (commute_run / "agent_summary.csv").open() as f:
            reader = csv.DictReader(f)
            assert self.REQUIRED_COLUMNS.issubset(set(reader.fieldnames or []))

    def test_one_row_per_agent(self, commute_run: Path):
        with (commute_run / "agent_summary.csv").open() as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 5


# -- kpis.json contract --------------------------------------------------------

class TestKPIsContract:
    def test_has_run_id_and_kpis(self, commute_run: Path):
        data = json.loads((commute_run / "kpis.json").read_text())
        assert "run_id" in data
        assert "kpis" in data
        assert isinstance(data["kpis"], dict)

    def test_each_kpi_has_overall_and_per_tick(self, commute_run: Path):
        data = json.loads((commute_run / "kpis.json").read_text())
        for kpi_id, kpi in data["kpis"].items():
            assert "overall" in kpi, f"KPI '{kpi_id}' missing 'overall'"
            assert "per_tick" in kpi, f"KPI '{kpi_id}' missing 'per_tick'"
            assert "name" in kpi
            assert "metric" in kpi

    def test_vaccine_scenario_kpis(self, vaccine_run: Path):
        data = json.loads((vaccine_run / "kpis.json").read_text())
        assert "clinic_visits" in data["kpis"]
        assert "parent_count" in data["kpis"]


# -- world_state.jsonl contract ------------------------------------------------

class TestWorldStateContract:
    REQUIRED_FIELDS = {"tick", "tick_unit", "locations", "routes", "active_interventions"}

    def test_file_exists(self, commute_run: Path):
        assert (commute_run / "world_state.jsonl").exists()

    def test_every_line_is_valid_json(self, commute_run: Path):
        for line in (commute_run / "world_state.jsonl").read_text().splitlines():
            json.loads(line)

    def test_required_fields_present(self, commute_run: Path):
        for line in (commute_run / "world_state.jsonl").read_text().splitlines():
            record = json.loads(line)
            assert self.REQUIRED_FIELDS.issubset(record.keys()), (
                f"Missing fields: {self.REQUIRED_FIELDS - record.keys()}"
            )

    def test_one_record_per_tick(self, commute_run: Path):
        lines = (commute_run / "world_state.jsonl").read_text().strip().splitlines()
        assert len(lines) == 24
        ticks = [json.loads(line)["tick"] for line in lines]
        assert ticks == list(range(24))

    def test_location_records_have_required_fields(self, commute_run: Path):
        first = json.loads(
            (commute_run / "world_state.jsonl").read_text().splitlines()[0]
        )
        for loc in first["locations"]:
            assert "id" in loc
            assert "name" in loc
            assert "type" in loc
            assert "occupant_count" in loc
            assert isinstance(loc["occupant_count"], int)
            assert "capacity" in loc

    def test_route_records_have_required_fields(self, commute_run: Path):
        first = json.loads(
            (commute_run / "world_state.jsonl").read_text().splitlines()[0]
        )
        for route in first["routes"]:
            assert "from" in route
            assert "to" in route
            assert "mode" in route
            assert "base_travel_time" in route
            assert "current_travel_time" in route

    def test_occupant_counts_sum_to_total_agents(self, commute_run: Path):
        for line in (commute_run / "world_state.jsonl").read_text().splitlines():
            record = json.loads(line)
            total = sum(loc["occupant_count"] for loc in record["locations"])
            assert total == 5, f"Tick {record['tick']}: occupant sum {total} != 5"

    def test_intervention_effects_visible(self, commute_run: Path):
        """Verify congestion pricing intervention changes travel times."""
        lines = (commute_run / "world_state.jsonl").read_text().splitlines()
        pre = json.loads(lines[5])   # tick 5: before intervention
        post = json.loads(lines[7])  # tick 7: after intervention

        # Find drive routes and compare
        pre_drive = {(r["from"], r["to"]): r for r in pre["routes"] if r["mode"] == "drive"}
        post_drive = {(r["from"], r["to"]): r for r in post["routes"] if r["mode"] == "drive"}

        # At least one drive route should have increased travel time
        any_increased = any(
            post_drive[key]["current_travel_time"] > pre_drive[key]["base_travel_time"]
            for key in pre_drive
            if key in post_drive
        )
        assert any_increased, "Expected intervention to increase at least one drive route travel time"


# -- cross-file consistency ---------------------------------------------------

class TestCrossFileConsistency:
    def test_run_id_consistent_across_files(self, commute_run: Path):
        meta = json.loads((commute_run / "metadata.json").read_text())
        run_id = meta["run_id"]

        # Check events
        first_event = json.loads(
            (commute_run / "events.jsonl").read_text().splitlines()[0]
        )
        assert first_event["run_id"] == run_id

        # Check agent_states
        first_state = json.loads(
            (commute_run / "agent_states.jsonl").read_text().splitlines()[0]
        )
        assert first_state["run_id"] == run_id

        # Check narratives
        first_narrative = json.loads(
            (commute_run / "narratives.jsonl").read_text().splitlines()[0]
        )
        assert first_narrative["run_id"] == run_id

        # Check kpis
        kpi_data = json.loads((commute_run / "kpis.json").read_text())
        assert kpi_data["run_id"] == run_id

    def test_scenario_yaml_copied(self, commute_run: Path):
        assert (commute_run / "scenario.yaml").exists()
        content = (commute_run / "scenario.yaml").read_text()
        assert "morning_commute" in content
