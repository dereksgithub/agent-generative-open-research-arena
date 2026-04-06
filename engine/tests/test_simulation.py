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


def test_streaming_output_matches_expected_line_counts(tmp_path: Path):
    """Verify that streamed output files have the correct number of records."""
    result = run_scenario(EXAMPLE_PATH, seed=42, output_dir=tmp_path / "out", use_llm=False)

    # 5 agents * 24 ticks = 120 decisions
    decisions = (result.output_dir / "decisions.jsonl").read_text().strip().split("\n")
    assert len(decisions) == 120

    # 5 agents * 24 ticks = 120 agent states
    agent_states = (result.output_dir / "agent_states.jsonl").read_text().strip().split("\n")
    assert len(agent_states) == 120

    # narratives — one per decision with reasoning (all heuristic decisions have reasoning)
    narratives = (result.output_dir / "narratives.jsonl").read_text().strip().split("\n")
    assert len(narratives) == 120

    # events.jsonl — verify it's valid JSONL and has correct structure
    events_text = (result.output_dir / "events.jsonl").read_text().strip()
    event_lines = events_text.split("\n")
    assert len(event_lines) > 0
    first_event = json.loads(event_lines[0])
    assert first_event["event_type"] == "run_start"
    last_event = json.loads(event_lines[-1])
    assert last_event["event_type"] == "run_end"

    # Verify agent_states records have the expected fields
    state_record = json.loads(agent_states[0])
    assert "run_id" in state_record
    assert "tick" in state_record
    assert "agent_id" in state_record
    assert "location" in state_record
    assert "action" in state_record


def test_occupancy_events_in_output(tmp_path: Path):
    """Verify TICK_OCCUPANCY events appear for every tick with correct structure."""
    result = run_scenario(EXAMPLE_PATH, seed=42, output_dir=tmp_path / "out", use_llm=False)

    events_text = (result.output_dir / "events.jsonl").read_text().strip()
    all_events = [json.loads(line) for line in events_text.split("\n")]
    occupancy_events = [e for e in all_events if e["event_type"] == "tick_occupancy"]

    # At least one occupancy event per tick (agents must be somewhere)
    ticks_with_occupancy = {e["tick"] for e in occupancy_events}
    assert ticks_with_occupancy == set(range(result.total_ticks))

    # Each occupancy event has the required fields and agent_id is null
    for e in occupancy_events:
        assert e["agent_id"] is None
        data = e["data"]
        assert "location_id" in data
        assert "location_name" in data
        assert "location_type" in data
        assert isinstance(data["occupant_ids"], list)
        assert data["occupant_count"] == len(data["occupant_ids"])
        assert data["occupant_count"] > 0  # empty locations should not emit


def test_provenance_chain_integrity(tmp_path: Path):
    """Verify the PERCEIVE → DELIBERATE → DECIDE → ACT chain via parent_event_id."""
    result = run_scenario(EXAMPLE_PATH, seed=42, output_dir=tmp_path / "out", use_llm=False)

    events_text = (result.output_dir / "events.jsonl").read_text().strip()
    all_events = [json.loads(line) for line in events_text.split("\n")]
    events_by_id = {e["event_id"]: e for e in all_events}

    # Group agent lifecycle events by (tick, agent_id)
    from collections import defaultdict
    agent_chains: dict[tuple[int, str], list[dict]] = defaultdict(list)
    lifecycle_types = {"agent_perceive", "agent_deliberate", "agent_decide", "agent_act"}
    for e in all_events:
        if e["event_type"] in lifecycle_types and e.get("agent_id"):
            agent_chains[(e["tick"], e["agent_id"])].append(e)

    assert len(agent_chains) > 0

    for (tick, agent_id), chain in agent_chains.items():
        # Sort by event_id to get chronological order
        chain.sort(key=lambda e: e["event_id"])
        types = [e["event_type"] for e in chain]
        assert types == ["agent_perceive", "agent_deliberate", "agent_decide", "agent_act"], (
            f"Unexpected chain for tick={tick}, agent={agent_id}: {types}"
        )

        perceive, deliberate, decide, act = chain

        # PERCEIVE has no parent
        assert "parent_event_id" not in perceive

        # DELIBERATE → PERCEIVE
        assert deliberate["parent_event_id"] == perceive["event_id"]

        # DECIDE → DELIBERATE (heuristic, no LLM events)
        assert decide["parent_event_id"] == deliberate["event_id"]

        # ACT → DECIDE
        assert act["parent_event_id"] == decide["event_id"]


def test_streaming_callback_fires_per_tick(tmp_path: Path):
    """Verify the engine's on_tick_complete callback fires for each tick."""
    from agora.agents.strategy import HeuristicStrategy
    from agora.scenarios.loader import load_scenario
    from agora.simulation.engine import SimulationEngine

    scenario = load_scenario(EXAMPLE_PATH)
    agents = []
    from agora.agents.agent import Agent
    for persona in scenario.agents:
        agents.append(Agent(
            id=persona.id, name=persona.name, role=persona.role,
            traits=list(persona.traits), home_location=persona.home_location,
            work_location=persona.work_location, preferred_mode=persona.preferred_mode,
            schedule=dict(persona.schedule), current_location=persona.home_location,
        ))

    engine = SimulationEngine(scenario, agents, seed=42, strategy=HeuristicStrategy())

    ticks_seen: list[int] = []
    decisions_per_tick: list[int] = []

    def callback(tick: int, tick_decisions: list) -> None:
        ticks_seen.append(tick)
        decisions_per_tick.append(len(tick_decisions))

    engine.run(on_tick_complete=callback)

    assert ticks_seen == list(range(24))
    assert all(count == 5 for count in decisions_per_tick)
