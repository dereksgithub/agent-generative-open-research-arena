"""Runner-level Phase 4 tests for LLM orchestration and graceful fallback."""

from __future__ import annotations

import json
import re
from pathlib import Path
from unittest.mock import AsyncMock, patch

from agora.cli import main
from agora.llm.client import LLMResponse, LLMTransientError
from agora.simulation.event_log import EventType
from agora.simulation.runner import run_scenario

EXAMPLE_PATH = Path(__file__).resolve().parents[2] / "scenarios" / "examples" / "morning_commute.yaml"


def _fake_llm_response(prompt: str) -> LLMResponse:
    current_location = re.search(r"Your current location: (.+)", prompt)
    goal = re.search(r"Your goal this tick: (.+)", prompt)
    current = current_location.group(1).strip() if current_location else "unknown"
    goal_text = goal.group(1).strip() if goal else "stay"

    if goal_text == "stay":
        payload = {
            "action": "stay",
            "target": current,
            "mode": "",
            "reasoning": "No travel goal this tick.",
        }
    else:
        target = goal_text.split(":", 1)[1]
        route_match = re.search(rf"- to {re.escape(target)} via ([^:]+):", prompt)
        if target == current or route_match is None:
            payload = {
                "action": "stay",
                "target": current,
                "mode": "",
                "reasoning": "Already at the goal location.",
            }
        else:
            mode = route_match.group(1).strip()
            payload = {
                "action": "travel",
                "target": target,
                "mode": mode,
                "reasoning": "Following the scheduled travel goal.",
            }

    return LLMResponse(
        content=json.dumps(payload),
        model="gpt-4o-mini",
        provider="openai",
        usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        latency_ms=12.5,
    )


def test_llm_run_records_audit_metadata(tmp_path: Path):
    async def fake_chat(_self, messages, **_kwargs):
        return _fake_llm_response(messages[1]["content"])

    with patch("agora.agents.strategy.LLMClient.chat", new=fake_chat), patch(
        "agora.agents.strategy.LLMClient.get_accounting",
        return_value={
            "total_requests": 120,
            "total_cached": 0,
            "total_prompt_tokens": 1200,
            "total_completion_tokens": 600,
            "total_tokens": 1800,
            "total_latency_ms": 1500.0,
            "provider": "openai",
            "model": "gpt-4o-mini",
        },
    ):
        result = run_scenario(
            EXAMPLE_PATH,
            seed=42,
            output_dir=tmp_path / "out",
            use_llm=True,
            llm_provider="openai",
            llm_temperature=0.2,
            llm_max_tokens=128,
            llm_timeout=12.0,
            llm_max_retries=1,
        )

    metadata = json.loads((result.output_dir / "metadata.json").read_text())
    assert metadata["decision_mode"] == "llm"
    assert metadata["llm_settings"]["temperature"] == 0.2
    assert metadata["llm_settings"]["max_tokens"] == 128
    assert metadata["llm_settings"]["timeout_seconds"] == 12.0
    assert metadata["llm_status"]["disabled"] is False
    assert metadata["llm_accounting"]["total_tokens"] == 1800

    events = [
        json.loads(line)
        for line in (result.output_dir / "events.jsonl").read_text().splitlines()
        if line.strip()
    ]
    request_event = next(event for event in events if event["event_type"] == EventType.LLM_REQUEST.value)
    response_event = next(event for event in events if event["event_type"] == EventType.LLM_RESPONSE.value)
    assert "messages" in request_event["data"]
    assert "settings" in request_event["data"]
    assert "parsed_decision" in response_event["data"]
    assert response_event["data"]["parsed_decision"]["action"] in {"travel", "stay"}


def test_llm_run_falls_back_and_disables_after_consecutive_failures(tmp_path: Path):
    with patch(
        "agora.agents.strategy.LLMClient.chat",
        new=AsyncMock(side_effect=LLMTransientError("provider down")),
    ), patch(
        "agora.agents.strategy.LLMClient.get_accounting",
        return_value={
            "total_requests": 0,
            "total_cached": 0,
            "total_prompt_tokens": 0,
            "total_completion_tokens": 0,
            "total_tokens": 0,
            "total_latency_ms": 0.0,
            "provider": "openai",
            "model": "gpt-4o",
        },
    ):
        result = run_scenario(
            EXAMPLE_PATH,
            seed=42,
            output_dir=tmp_path / "out",
            use_llm=True,
            llm_provider="openai",
            llm_max_consecutive_failures=1,
        )

    metadata = json.loads((result.output_dir / "metadata.json").read_text())
    assert metadata["llm_status"]["disabled"] is True
    assert "consecutive failures" in metadata["llm_status"]["disabled_reason"]

    decisions = [
        json.loads(line)
        for line in (result.output_dir / "decisions.jsonl").read_text().splitlines()
        if line.strip()
    ]
    assert decisions[0]["metadata"]["decision_source"] == "llm_error"
    assert decisions[1]["metadata"]["decision_source"] == "llm_disabled"

    events = [
        json.loads(line)
        for line in (result.output_dir / "events.jsonl").read_text().splitlines()
        if line.strip()
    ]
    assert EventType.LLM_DISABLED.value in {event["event_type"] for event in events}


def test_llm_run_threads_provenance_chain_through_request_and_response(tmp_path: Path):
    async def fake_chat(_self, messages, **_kwargs):
        return _fake_llm_response(messages[1]["content"])

    with patch("agora.agents.strategy.LLMClient.chat", new=fake_chat):
        result = run_scenario(
            EXAMPLE_PATH,
            seed=42,
            output_dir=tmp_path / "out",
            use_llm=True,
            llm_provider="openai",
        )

    events = [
        json.loads(line)
        for line in (result.output_dir / "events.jsonl").read_text().splitlines()
        if line.strip()
    ]
    events_by_id = {event["event_id"]: event for event in events}

    first_request = next(event for event in events if event["event_type"] == EventType.LLM_REQUEST.value)
    agent_id = first_request["agent_id"]
    tick = first_request["tick"]

    deliberate = next(
        event for event in events
        if event["tick"] == tick
        and event["agent_id"] == agent_id
        and event["event_type"] == EventType.AGENT_DELIBERATE.value
    )
    response = next(
        event for event in events
        if event["tick"] == tick
        and event["agent_id"] == agent_id
        and event["event_type"] == EventType.LLM_RESPONSE.value
    )
    decide = next(
        event for event in events
        if event["tick"] == tick
        and event["agent_id"] == agent_id
        and event["event_type"] == EventType.AGENT_DECIDE.value
    )
    act = next(
        event for event in events
        if event["tick"] == tick
        and event["agent_id"] == agent_id
        and event["event_type"] == EventType.AGENT_ACT.value
    )

    assert first_request["parent_event_id"] == deliberate["event_id"]
    assert response["parent_event_id"] == first_request["event_id"]
    assert decide["parent_event_id"] == response["event_id"]
    assert act["parent_event_id"] == decide["event_id"]
    assert events_by_id[decide["parent_event_id"]]["event_type"] == EventType.LLM_RESPONSE.value


def test_cli_invalid_provider_returns_clean_error(tmp_path: Path, capsys):
    exit_code = main(
        [
            "run",
            str(EXAMPLE_PATH),
            "--llm",
            "--llm-provider",
            "nosuch",
            "--output-dir",
            str(tmp_path / "out"),
        ]
    )
    captured = capsys.readouterr()
    assert exit_code == 2
    assert "Unknown provider 'nosuch'" in captured.err
    assert "Traceback" not in captured.err
