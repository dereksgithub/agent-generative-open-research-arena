"""Phase 6 scenario parsing edge case tests.

Validates that the scenario schema and loader handle boundary conditions
correctly: minimal scenarios, duplicate IDs, missing references, etc.
"""

from pathlib import Path

import pytest

from agora.scenarios.loader import load_scenario
from agora.scenarios.schema import (
    KPIDefinition,
    Location,
    PersonaDefinition,
    PolicyIntervention,
    Route,
    ScenarioSpec,
    SimulationConfig,
)


# -- Minimal valid scenarios --------------------------------------------------

def test_minimal_scenario():
    """A scenario with one location and one agent is valid."""
    spec = ScenarioSpec.model_validate({
        "name": "minimal",
        "locations": [{"id": "home", "name": "Home"}],
        "agents": [{"id": "a1", "name": "Agent 1", "home_location": "home", "work_location": "home"}],
    })
    assert spec.id == "minimal-v1"
    assert len(spec.agents) == 1


def test_scenario_with_no_agents():
    """A scenario with no agents is valid (for template authoring)."""
    spec = ScenarioSpec.model_validate({
        "name": "empty_world",
        "locations": [{"id": "plaza", "name": "Plaza"}],
    })
    assert len(spec.agents) == 0


def test_scenario_with_no_routes():
    """A scenario with locations but no routes is valid."""
    spec = ScenarioSpec.model_validate({
        "name": "isolated",
        "locations": [
            {"id": "a", "name": "Place A"},
            {"id": "b", "name": "Place B"},
        ],
        "agents": [{"id": "a1", "name": "Agent 1", "home_location": "a", "work_location": "a"}],
    })
    assert len(spec.routes) == 0


# -- ID generation ------------------------------------------------------------

def test_auto_id_from_name():
    spec = ScenarioSpec.model_validate({
        "name": "My Cool Scenario",
        "locations": [{"id": "home", "name": "Home"}],
    })
    assert spec.id == "my-cool-scenario-v1"


def test_explicit_id_preserved():
    spec = ScenarioSpec.model_validate({
        "id": "custom_id_v3",
        "name": "Custom",
        "locations": [{"id": "home", "name": "Home"}],
    })
    assert spec.id == "custom_id_v3"


# -- Validation errors ---------------------------------------------------------

def test_duplicate_location_ids_rejected():
    with pytest.raises(ValueError, match="Duplicate location id"):
        ScenarioSpec.model_validate({
            "name": "dup_loc",
            "locations": [
                {"id": "home", "name": "Home 1"},
                {"id": "home", "name": "Home 2"},
            ],
        })


def test_duplicate_agent_ids_rejected():
    with pytest.raises(ValueError, match="Duplicate agent id"):
        ScenarioSpec.model_validate({
            "name": "dup_agent",
            "locations": [{"id": "home", "name": "Home"}],
            "agents": [
                {"id": "a1", "name": "Agent 1", "home_location": "home", "work_location": "home"},
                {"id": "a1", "name": "Agent 2", "home_location": "home", "work_location": "home"},
            ],
        })


def test_agent_unknown_home_location_rejected():
    with pytest.raises(ValueError, match="unknown home location"):
        ScenarioSpec.model_validate({
            "name": "bad_home",
            "locations": [{"id": "home", "name": "Home"}],
            "agents": [
                {"id": "a1", "name": "Agent 1", "home_location": "nowhere", "work_location": "home"},
            ],
        })


def test_agent_unknown_work_location_rejected():
    with pytest.raises(ValueError, match="unknown work location"):
        ScenarioSpec.model_validate({
            "name": "bad_work",
            "locations": [{"id": "home", "name": "Home"}],
            "agents": [
                {"id": "a1", "name": "Agent 1", "home_location": "home", "work_location": "nowhere"},
            ],
        })


def test_route_unknown_origin_rejected():
    with pytest.raises(ValueError, match="unknown origin location"):
        ScenarioSpec.model_validate({
            "name": "bad_route_origin",
            "locations": [{"id": "a", "name": "A"}],
            "routes": [{"from": "nowhere", "to": "a", "mode": "walk"}],
        })


def test_route_unknown_destination_rejected():
    with pytest.raises(ValueError, match="unknown destination location"):
        ScenarioSpec.model_validate({
            "name": "bad_route_dest",
            "locations": [{"id": "a", "name": "A"}],
            "routes": [{"from": "a", "to": "nowhere", "mode": "walk"}],
        })


def test_intervention_beyond_tick_range_rejected():
    with pytest.raises(ValueError, match="outside simulation range"):
        ScenarioSpec.model_validate({
            "name": "bad_intervention",
            "simulation": {"ticks": 10},
            "locations": [{"id": "a", "name": "A"}],
            "interventions": [
                {"tick": 15, "name": "late_policy", "description": "Too late"},
            ],
        })


def test_intervention_at_last_tick_rejected():
    with pytest.raises(ValueError, match="outside simulation range"):
        ScenarioSpec.model_validate({
            "name": "edge_intervention",
            "simulation": {"ticks": 10},
            "locations": [{"id": "a", "name": "A"}],
            "interventions": [
                {"tick": 10, "name": "edge_policy", "description": "At boundary"},
            ],
        })


def test_intervention_at_tick_zero_valid():
    spec = ScenarioSpec.model_validate({
        "name": "tick_zero_intervention",
        "simulation": {"ticks": 5},
        "locations": [{"id": "a", "name": "A"}],
        "interventions": [
            {"tick": 0, "name": "early_policy", "description": "Immediate"},
        ],
    })
    assert spec.interventions[0].tick == 0


# -- Field defaults and edge values -------------------------------------------

def test_location_default_type():
    loc = Location(id="x", name="X")
    assert loc.type == "generic"


def test_location_zero_capacity():
    loc = Location(id="x", name="X", capacity=0)
    assert loc.capacity == 0


def test_persona_age_boundaries():
    p = PersonaDefinition(id="p", name="P", home_location="h", work_location="h", age=0)
    assert p.age == 0
    p = PersonaDefinition(id="p", name="P", home_location="h", work_location="h", age=150)
    assert p.age == 150


def test_persona_invalid_age_rejected():
    with pytest.raises(ValueError):
        PersonaDefinition(id="p", name="P", home_location="h", work_location="h", age=-1)
    with pytest.raises(ValueError):
        PersonaDefinition(id="p", name="P", home_location="h", work_location="h", age=151)


def test_simulation_config_defaults():
    cfg = SimulationConfig()
    assert cfg.ticks == 24
    assert cfg.tick_unit == "hour"
    assert cfg.seed is None


def test_policy_duration_must_be_positive():
    with pytest.raises(ValueError):
        PolicyIntervention(tick=0, name="bad", description="bad", duration=0)


# -- YAML loader edge cases ---------------------------------------------------

def test_empty_yaml_rejected(tmp_path: Path):
    f = tmp_path / "empty.yaml"
    f.write_text("")
    with pytest.raises(ValueError, match="YAML mapping"):
        load_scenario(f)


def test_yaml_list_rejected(tmp_path: Path):
    f = tmp_path / "list.yaml"
    f.write_text("- item1\n- item2\n")
    with pytest.raises(ValueError, match="YAML mapping"):
        load_scenario(f)


def test_yaml_with_extra_fields_accepted(tmp_path: Path):
    """Extra fields in YAML should be silently ignored (forward compat)."""
    f = tmp_path / "extra.yaml"
    f.write_text(
        """
name: extra_fields
future_feature: true
locations:
  - id: home
    name: Home
agents:
  - id: a1
    name: Agent 1
    home_location: home
    work_location: home
""".strip()
    )
    spec = load_scenario(f)
    assert spec.name == "extra_fields"
