"""Tests for simulation engine step semantics and Phase 2 behavior."""

from pathlib import Path

from agora.agents.agent import Agent
from agora.agents.strategy import HeuristicStrategy
from agora.scenarios.loader import load_scenario
from agora.scenarios.schema import ScenarioSpec
from agora.simulation.engine import SimulationEngine
from agora.simulation.event_log import EventType
from agora.simulation.runner import run_scenario

EXAMPLE_PATH = Path(__file__).resolve().parents[2] / "scenarios" / "examples" / "morning_commute.yaml"


def _build_engine():
    scenario = load_scenario(EXAMPLE_PATH)
    agents = []
    for p in scenario.agents:
        agents.append(Agent(
            id=p.id, name=p.name, role=p.role, traits=list(p.traits),
            home_location=p.home_location, work_location=p.work_location,
            preferred_mode=p.preferred_mode, schedule=dict(p.schedule),
            current_location=p.home_location,
        ))
    return SimulationEngine(scenario, agents, seed=42)


def _build_role_targeted_engine() -> SimulationEngine:
    scenario = ScenarioSpec.model_validate(
        {
            "id": "role_targeted_v1",
            "name": "role_targeted",
            "simulation": {"ticks": 2, "tick_unit": "hour", "seed": 42},
            "locations": [
                {"id": "home", "name": "Home"},
                {"id": "office", "name": "Office"},
            ],
            "routes": [
                {"from": "home", "to": "office", "mode": "drive", "travel_time_minutes": 10},
                {"from": "home", "to": "office", "mode": "transit", "travel_time_minutes": 12},
            ],
            "agents": [
                {
                    "id": "commuter",
                    "name": "Commuter",
                    "role": "commuter",
                    "home_location": "home",
                    "work_location": "office",
                    "preferred_mode": "drive",
                    "schedule": {"0": "travel_to:office"},
                },
                {
                    "id": "student",
                    "name": "Student",
                    "role": "student",
                    "home_location": "home",
                    "work_location": "office",
                    "preferred_mode": "drive",
                    "schedule": {"0": "travel_to:office"},
                },
            ],
            "interventions": [
                {
                    "tick": 0,
                    "name": "commuter_drive_penalty",
                    "description": "Penalize driving for commuters only",
                    "effects": {"drive_cost_multiplier": 2.0},
                    "target_roles": ["commuter"],
                    "duration": 1,
                }
            ],
        }
    )
    agents = [
        Agent(
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
        for persona in scenario.agents
    ]
    return SimulationEngine(scenario, agents, seed=42)


def test_event_log_records_full_lifecycle():
    engine = _build_engine()
    engine.run()
    types = [e.event_type for e in engine.event_log.events]
    assert types[0] == EventType.RUN_START
    assert types[-1] == EventType.RUN_END
    assert EventType.TICK_START in types
    assert EventType.TICK_END in types
    assert EventType.AGENT_PERCEIVE in types
    assert EventType.AGENT_DELIBERATE in types
    assert EventType.AGENT_DECIDE in types
    assert EventType.AGENT_ACT in types
    assert EventType.INTERVENTION_APPLIED in types


def test_event_log_has_stable_run_id():
    engine = _build_engine()
    engine.run()
    run_id = engine.state.run_id
    assert all(e.run_id == run_id for e in engine.event_log.events)


def test_run_id_is_deterministic_for_same_inputs():
    engine_a = _build_engine()
    engine_b = _build_engine()
    assert engine_a.state.run_id == engine_b.state.run_id


def test_event_ids_are_sequential():
    engine = _build_engine()
    engine.run()
    ids = [e.event_id for e in engine.event_log.events]
    assert ids == list(range(len(ids)))


def test_intervention_modifies_route_costs():
    engine = _build_engine()
    # Before intervention
    drive_routes = [r for r in engine.state.routes if r.mode == "drive"]
    assert all(r.current_travel_time == r.base_travel_time for r in drive_routes)

    # Run through tick 7 (intervention tick)
    for tick in range(8):
        engine._step_tick(tick)

    # After intervention: drive cost should be multiplied
    drive_routes = [r for r in engine.state.routes if r.mode == "drive"]
    assert all(r.current_travel_time > r.base_travel_time for r in drive_routes)
    # Transit routes should be unaffected
    transit_routes = [r for r in engine.state.routes if r.mode == "transit"]
    assert all(r.current_travel_time == r.base_travel_time for r in transit_routes)


def test_targeted_intervention_applies_only_to_matching_roles():
    engine = _build_role_targeted_engine()
    engine._apply_interventions(0)

    commuter_snapshot = engine.state.snapshot_for_agent("home", "commuter")
    student_snapshot = engine.state.snapshot_for_agent("home", "student")

    commuter_drive = next(
        route["travel_time_minutes"]
        for route in commuter_snapshot["routes_from"]["home"]
        if route["mode"] == "drive"
    )
    student_drive = next(
        route["travel_time_minutes"]
        for route in student_snapshot["routes_from"]["home"]
        if route["mode"] == "drive"
    )
    assert commuter_drive == 20.0
    assert student_drive == 10.0


def test_duration_expires_targeted_intervention():
    engine = _build_role_targeted_engine()
    engine._apply_interventions(0)
    engine._apply_interventions(1)

    commuter_snapshot = engine.state.snapshot_for_agent("home", "commuter")
    commuter_drive = next(
        route["travel_time_minutes"]
        for route in commuter_snapshot["routes_from"]["home"]
        if route["mode"] == "drive"
    )
    assert commuter_drive == 10.0


def test_occupancy_tracking():
    engine = _build_engine()
    north = engine.state.locations["suburbs_north"]
    south = engine.state.locations["suburbs_south"]
    assert set(north.occupant_ids) == {"alice", "bob", "eve"}
    assert set(south.occupant_ids) == {"carol", "dave"}

    engine.run()
    all_occupants = set()
    for loc in engine.state.locations.values():
        all_occupants.update(loc.occupant_ids)
    assert all_occupants == {"alice", "bob", "carol", "dave", "eve"}


def test_strategy_is_used():
    """Verify the engine delegates to the strategy, not directly to agent.decide()."""
    engine = _build_engine()
    assert isinstance(engine.strategy, HeuristicStrategy)
    decisions = engine.run()
    assert len(decisions) == 120  # 5 agents * 24 ticks


def test_events_jsonl_written(tmp_path: Path):
    result = run_scenario(EXAMPLE_PATH, seed=42, output_dir=tmp_path / "out", use_llm=False)
    events_file = result.output_dir / "events.jsonl"
    assert events_file.exists()
    lines = events_file.read_text().strip().split("\n")
    assert len(lines) > 100  # should have many events for 24 ticks * 5 agents


def test_metadata_includes_run_id(tmp_path: Path):
    import json

    result = run_scenario(EXAMPLE_PATH, seed=42, output_dir=tmp_path / "out", use_llm=False)
    meta = json.loads((result.output_dir / "metadata.json").read_text())
    assert "run_id" in meta
    assert len(meta["run_id"]) == 12
    assert meta["scenario_id"] == "morning_commute_v1"
    assert meta["decision_mode"] == "heuristic"
