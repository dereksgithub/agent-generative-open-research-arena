"""Prompt contract for LLM-backed agent reasoning.

Builds structured prompts from agent persona + world perception + goal,
and parses structured JSON responses back into Decision objects.
"""

from __future__ import annotations

import json
from typing import Any

SYSTEM_PROMPT = """\
You are an agent in a social simulation.  You must respond with ONLY a valid
JSON object — no markdown fences, no commentary, no extra text.

JSON schema:
{
  "action": "travel" | "stay",
  "target": "<location_id or current location>",
  "mode": "<transport mode if travelling, else empty string>",
  "reasoning": "<one or two sentences explaining your choice>"
}

Rules:
- Pick exactly ONE action per tick.
- "travel" means move to a different location; "stay" means remain.
- Your reasoning should reflect your persona, values, and current conditions.
- If there are active policy interventions, factor their costs into your decision.
"""


def build_user_prompt(
    agent_context: dict[str, Any],
    goal: str,
    perception: dict[str, Any],
) -> str:
    """Build the user-turn prompt sent to the LLM for one agent decision."""
    parts: list[str] = []

    # Persona block
    parts.append("## Who you are")
    parts.append(f"Name: {agent_context['name']}")
    parts.append(f"Role: {agent_context['role']}")
    if agent_context.get("traits"):
        parts.append(f"Traits: {', '.join(agent_context['traits'])}")
    if agent_context.get("values"):
        parts.append(f"Values: {', '.join(agent_context['values'])}")
    if agent_context.get("backstory"):
        parts.append(f"Background: {agent_context['backstory']}")
    if agent_context.get("income_bracket"):
        parts.append(f"Income bracket: {agent_context['income_bracket']}")
    if agent_context.get("preferred_mode"):
        parts.append(f"Preferred transport mode: {agent_context['preferred_mode']}")

    # Situation block
    parts.append("")
    parts.append("## Current situation")
    parts.append(f"Tick: {perception['tick']} ({perception.get('tick_unit', 'hour')})")
    parts.append(f"Your current location: {perception['current_location']}")
    parts.append(f"Your goal this tick: {goal}")

    # Available routes
    routes = perception.get("available_routes", [])
    if routes:
        parts.append("")
        parts.append("## Available routes from your location")
        for r in routes:
            line = f"- to {r['to']} via {r.get('mode', '?')}: {r.get('travel_time_minutes', '?')} min"
            parts.append(line)

    # Active interventions
    interventions = perception.get("active_interventions", [])
    if interventions:
        parts.append("")
        parts.append("## Active policy interventions")
        for iv in interventions:
            desc = iv.get("description", iv.get("name", "unknown"))
            effects = iv.get("effects", {})
            parts.append(f"- {desc} (effects: {effects})")

    # Recent memory
    recent = perception.get("recent_memory", [])
    if recent:
        parts.append("")
        parts.append("## Your recent memory")
        for mem in recent[-3:]:
            event = mem.event if hasattr(mem, "event") else mem.get("event", str(mem))
            parts.append(f"- {event}")

    parts.append("")
    parts.append("Respond with the JSON object only.")
    return "\n".join(parts)


def build_agent_context(agent: Any) -> dict[str, Any]:
    """Extract prompt-relevant fields from an Agent dataclass."""
    ctx: dict[str, Any] = {
        "id": agent.id,
        "name": agent.name,
        "role": agent.role,
        "traits": list(agent.traits),
        "preferred_mode": agent.preferred_mode,
        "home_location": agent.home_location,
        "work_location": agent.work_location,
    }
    # Enriched fields stored as _persona_* on Agent
    for field_name in ("values", "backstory", "income_bracket", "age", "household_size"):
        val = getattr(agent, f"_persona_{field_name}", None)
        if val:
            ctx[field_name] = val
    return ctx


def parse_llm_decision(raw_text: str) -> dict[str, Any]:
    """Parse the LLM response text into a decision dict.

    Handles common LLM quirks: markdown fences, trailing text, etc.
    Returns a dict with keys: action, target, mode, reasoning.
    Raises ValueError if the response cannot be parsed.
    """
    text = raw_text.strip()

    # Strip markdown code fences if present
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first and last fence lines
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()

    # Try to find JSON object in the text
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError(f"No JSON object found in LLM response: {raw_text[:200]}")

    json_str = text[start : end + 1]
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in LLM response: {exc}") from exc

    # Validate required fields
    action = data.get("action", "").strip().lower()
    if action not in ("travel", "stay"):
        raise ValueError(f"Invalid action '{action}' — must be 'travel' or 'stay'")

    return {
        "action": action,
        "target": str(data.get("target", "")),
        "mode": str(data.get("mode", "")),
        "reasoning": str(data.get("reasoning", "")),
    }
