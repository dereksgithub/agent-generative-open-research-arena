"""Tests for the cognition prompt contract (Phase 4)."""


from agora.agents.agent import Agent
from agora.cognition.prompt import (
    SYSTEM_PROMPT,
    build_agent_context,
    build_user_prompt,
    parse_llm_decision,
)

import pytest


def _make_agent(**overrides) -> Agent:
    defaults = dict(
        id="alice",
        name="Alice",
        role="commuter",
        traits=["punctual", "cost-sensitive"],
        home_location="suburbs_north",
        work_location="town_centre",
        preferred_mode="drive",
        schedule={},
        current_location="suburbs_north",
    )
    defaults.update(overrides)
    agent = Agent(**defaults)
    agent._persona_values = ["convenience", "reliability"]
    agent._persona_backstory = "Alice is a project manager."
    agent._persona_income_bracket = "medium"
    agent._persona_age = 34
    return agent


def test_system_prompt_is_nonempty():
    assert len(SYSTEM_PROMPT) > 50
    assert "JSON" in SYSTEM_PROMPT


def test_build_agent_context_extracts_fields():
    agent = _make_agent()
    ctx = build_agent_context(agent)
    assert ctx["id"] == "alice"
    assert ctx["name"] == "Alice"
    assert ctx["role"] == "commuter"
    assert ctx["traits"] == ["punctual", "cost-sensitive"]
    assert ctx["values"] == ["convenience", "reliability"]
    assert ctx["backstory"] == "Alice is a project manager."
    assert ctx["income_bracket"] == "medium"
    assert ctx["age"] == 34


def test_build_user_prompt_contains_persona_and_perception():
    agent = _make_agent()
    ctx = build_agent_context(agent)
    perception = {
        "tick": 8,
        "tick_unit": "hour",
        "current_location": "suburbs_north",
        "available_routes": [
            {"to": "town_centre", "mode": "drive", "travel_time_minutes": 15},
            {"to": "town_centre", "mode": "transit", "travel_time_minutes": 25},
        ],
        "active_interventions": [
            {"name": "congestion_charge", "effects": {"drive_cost_multiplier": 2.5}},
        ],
        "recent_memory": [],
    }
    prompt = build_user_prompt(ctx, "travel_to:town_centre", perception)
    assert "Alice" in prompt
    assert "commuter" in prompt
    assert "town_centre" in prompt
    assert "drive" in prompt
    assert "transit" in prompt
    assert "congestion" in prompt or "drive_cost_multiplier" in prompt
    assert "Tick: 8" in prompt


def test_parse_llm_decision_valid_json():
    raw = '{"action": "travel", "target": "town_centre", "mode": "transit", "reasoning": "Cheaper."}'
    result = parse_llm_decision(raw)
    assert result["action"] == "travel"
    assert result["target"] == "town_centre"
    assert result["mode"] == "transit"
    assert result["reasoning"] == "Cheaper."


def test_parse_llm_decision_strips_markdown_fences():
    raw = '```json\n{"action": "stay", "target": "home", "mode": "", "reasoning": "No goal."}\n```'
    result = parse_llm_decision(raw)
    assert result["action"] == "stay"
    assert result["target"] == "home"


def test_parse_llm_decision_extracts_from_surrounding_text():
    raw = 'Here is my decision:\n{"action": "travel", "target": "office", "mode": "walk", "reasoning": "Exercise."}\nDone.'
    result = parse_llm_decision(raw)
    assert result["action"] == "travel"


def test_parse_llm_decision_rejects_invalid_action():
    raw = '{"action": "fly", "target": "mars", "mode": "rocket", "reasoning": "Adventure."}'
    with pytest.raises(ValueError, match="Invalid action"):
        parse_llm_decision(raw)


def test_parse_llm_decision_rejects_no_json():
    with pytest.raises(ValueError, match="No JSON"):
        parse_llm_decision("I think you should walk.")


def test_parse_llm_decision_rejects_malformed_json():
    with pytest.raises(ValueError, match="Invalid JSON"):
        parse_llm_decision('{"action": "travel", "target":}')
