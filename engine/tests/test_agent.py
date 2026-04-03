"""Tests for the agent model."""

from agora.agents.agent import Agent, Decision


def _make_agent(**overrides) -> Agent:
    defaults = dict(
        id="test",
        name="Test Agent",
        role="commuter",
        traits=["punctual"],
        home_location="home",
        work_location="office",
        preferred_mode="drive",
        schedule={},
        current_location="home",
    )
    defaults.update(overrides)
    return Agent(**defaults)


def test_agent_stay_when_no_goal():
    agent = _make_agent()
    world = {"tick": 12, "routes_from": {}, "active_interventions": []}
    perception = agent.perceive(world)
    goal = agent.deliberate(perception)
    decision = agent.decide(goal, perception)
    assert decision.action == "stay"
    assert decision.target == "home"


def test_agent_travels_to_work_in_morning():
    agent = _make_agent()
    routes = [{"from": "home", "to": "office", "mode": "drive", "travel_time_minutes": 15}]
    world = {"tick": 8, "routes_from": {"home": routes}, "active_interventions": []}
    perception = agent.perceive(world)
    goal = agent.deliberate(perception)
    decision = agent.decide(goal, perception)
    assert decision.action == "travel"
    assert decision.target == "office"
    assert decision.metadata["mode"] == "drive"


def test_intervention_changes_mode():
    agent = _make_agent(preferred_mode="drive")
    routes = [
        {"from": "home", "to": "office", "mode": "drive", "travel_time_minutes": 15},
        {"from": "home", "to": "office", "mode": "transit", "travel_time_minutes": 25},
    ]
    interventions = [{"effects": {"drive_cost_multiplier": 3.0}}]
    world = {"tick": 8, "routes_from": {"home": routes}, "active_interventions": interventions}
    perception = agent.perceive(world)
    goal = agent.deliberate(perception)
    decision = agent.decide(goal, perception)
    # drive 15 * 3.0 = 45 > transit 25 * 1.0 = 25, so transit wins
    assert decision.metadata["mode"] == "transit"


def test_act_updates_location():
    agent = _make_agent(current_location="home")
    d = Decision(tick=8, agent_id="test", action="travel", target="office", reasoning="test")
    agent.act(d)
    assert agent.current_location == "office"
    assert len(agent.memory) == 1


def test_schedule_overrides_default():
    agent = _make_agent(schedule={"5": "travel_to:park"})
    world = {"tick": 5, "routes_from": {}, "active_interventions": []}
    perception = agent.perceive(world)
    goal = agent.deliberate(perception)
    assert goal == "travel_to:park"
