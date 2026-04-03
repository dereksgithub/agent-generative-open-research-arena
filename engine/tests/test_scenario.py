"""Tests for scenario loading and validation."""

from pathlib import Path

import pytest

from agora.scenarios.loader import load_scenario
from agora.scenarios.schema import ScenarioSpec


EXAMPLE_PATH = Path(__file__).resolve().parents[2] / "scenarios" / "examples" / "morning_commute.yaml"


def test_load_example_scenario():
    spec = load_scenario(EXAMPLE_PATH)
    assert isinstance(spec, ScenarioSpec)
    assert spec.id == "morning_commute_v1"
    assert spec.name == "morning_commute"
    assert spec.domain == "transport"
    assert len(spec.agents) == 5
    assert len(spec.locations) == 4
    assert len(spec.routes) > 0
    assert len(spec.interventions) == 1
    assert spec.simulation.ticks == 24
    assert spec.locations[0].resources["parking_spaces"] == 120


def test_scenario_agents_have_locations():
    spec = load_scenario(EXAMPLE_PATH)
    location_ids = {loc.id for loc in spec.locations}
    for agent in spec.agents:
        assert agent.home_location in location_ids
        assert agent.work_location in location_ids


def test_invalid_yaml_raises(tmp_path: Path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("not_a_mapping")
    with pytest.raises(ValueError, match="YAML mapping"):
        load_scenario(bad)


def test_missing_name_raises(tmp_path: Path):
    bad = tmp_path / "no_name.yaml"
    bad.write_text("description: missing name field\n")
    with pytest.raises(ValueError, match="Invalid scenario"):
        load_scenario(bad)


def test_unknown_route_location_raises(tmp_path: Path):
    bad = tmp_path / "bad_route.yaml"
    bad.write_text(
        """
name: bad_route
locations:
  - id: home
    name: Home
routes:
  - from: home
    to: office
    mode: walk
agents:
  - id: a1
    name: Agent 1
    home_location: home
    work_location: home
""".strip()
    )
    with pytest.raises(ValueError, match="unknown destination location 'office'"):
        load_scenario(bad)


def test_unknown_schedule_location_raises(tmp_path: Path):
    bad = tmp_path / "bad_schedule.yaml"
    bad.write_text(
        """
name: bad_schedule
locations:
  - id: home
    name: Home
agents:
  - id: a1
    name: Agent 1
    home_location: home
    work_location: home
    schedule:
      "2": "travel_to:office"
""".strip()
    )
    with pytest.raises(ValueError, match="references unknown location 'office'"):
        load_scenario(bad)


def test_invalid_kpi_metric_raises(tmp_path: Path):
    bad = tmp_path / "bad_kpi_metric.yaml"
    bad.write_text(
        """
name: bad_kpi_metric
locations:
  - id: home
    name: Home
agents:
  - id: a1
    name: Agent 1
    home_location: home
    work_location: home
kpis:
  - id: weird
    name: Weird KPI
    metric: median
    source: decisions
""".strip()
    )
    with pytest.raises(ValueError, match="metric"):
        load_scenario(bad)


def test_invalid_kpi_source_raises(tmp_path: Path):
    bad = tmp_path / "bad_kpi_source.yaml"
    bad.write_text(
        """
name: bad_kpi_source
locations:
  - id: home
    name: Home
agents:
  - id: a1
    name: Agent 1
    home_location: home
    work_location: home
kpis:
  - id: weird
    name: Weird KPI
    metric: count
    source: locations
""".strip()
    )
    with pytest.raises(ValueError, match="source"):
        load_scenario(bad)
