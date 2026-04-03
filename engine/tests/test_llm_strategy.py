"""Tests for LLMStrategy — decision routing with mocked LLM calls (Phase 4)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, Mock, patch

import pytest

from agora.agents.agent import Agent, Decision
from agora.agents.strategy import HeuristicStrategy, LLMStrategy
from agora.llm.client import LLMError, LLMPermanentError, LLMResponse, LLMTransientError
from agora.simulation.event_log import EventLog, EventType


def _make_agent(**overrides) -> Agent:
    defaults = dict(
        id="alice",
        name="Alice",
        role="commuter",
        traits=["punctual"],
        home_location="home",
        work_location="office",
        preferred_mode="drive",
        schedule={},
        current_location="home",
    )
    defaults.update(overrides)
    agent = Agent(**defaults)
    agent._persona_values = ["convenience"]
    agent._persona_backstory = "Test agent."
    agent._persona_income_bracket = "medium"
    return agent


def _make_perception(tick: int = 8) -> dict:
    return {
        "tick": tick,
        "tick_unit": "hour",
        "current_location": "home",
        "available_routes": [
            {"to": "office", "mode": "drive", "travel_time_minutes": 15},
            {"to": "office", "mode": "transit", "travel_time_minutes": 25},
        ],
        "active_interventions": [],
        "recent_memory": [],
    }


def _mock_llm_response(action="travel", target="office", mode="drive", reasoning="Good choice."):
    content = json.dumps({"action": action, "target": target, "mode": mode, "reasoning": reasoning})
    return LLMResponse(
        content=content,
        model="gpt-4o",
        provider="openai",
        usage={"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        latency_ms=250.0,
    )


class TestLLMStrategyDecision:
    """Test LLM strategy produces decisions from mocked LLM responses."""

    @patch("agora.agents.strategy.LLMClient")
    def test_llm_decision_success(self, MockClient):
        mock_client = Mock()
        mock_client.chat = AsyncMock(return_value=_mock_llm_response())
        mock_client.provider_name = "openai"
        mock_client.model = "gpt-4o"
        mock_client.get_accounting = Mock(return_value={"total_tokens": 150})
        mock_client.get_request_settings = Mock(return_value={"provider": "openai"})

        strategy = LLMStrategy(provider="openai")
        strategy._client = mock_client

        agent = _make_agent()
        perception = _make_perception()
        decision = strategy.decide(agent, "travel_to:office", perception)

        assert decision.action == "travel"
        assert decision.target == "office"
        assert decision.metadata["mode"] == "drive"
        assert decision.metadata["llm_provider"] == "openai"
        assert decision.metadata["llm_tokens"] == 150
        assert decision.metadata["llm_latency_ms"] == 250.0

    @patch("agora.agents.strategy.LLMClient")
    def test_llm_fallback_on_api_error(self, MockClient):
        mock_client = Mock()
        mock_client.chat = AsyncMock(side_effect=LLMTransientError("timeout"))
        mock_client.provider_name = "openai"
        mock_client.model = "gpt-4o"
        mock_client.get_request_settings = Mock(return_value={"provider": "openai"})

        strategy = LLMStrategy(provider="openai")
        strategy._client = mock_client

        agent = _make_agent()
        agent.seed(42)
        perception = _make_perception()
        decision = strategy.decide(agent, "travel_to:office", perception)

        # Should fall back to heuristic
        assert decision.action == "travel"
        assert decision.target == "office"
        assert decision.metadata["decision_source"] == "llm_error"
        assert decision.metadata["llm_provider_attempted"] == "openai"
        assert decision.metadata["llm_model_attempted"] == "gpt-4o"

    @patch("agora.agents.strategy.LLMClient")
    def test_llm_fallback_on_parse_error(self, MockClient):
        mock_client = Mock()
        bad_response = LLMResponse(
            content="I think you should walk!",  # not valid JSON
            model="gpt-4o",
            provider="openai",
            usage={},
            latency_ms=100.0,
        )
        mock_client.chat = AsyncMock(return_value=bad_response)
        mock_client.provider_name = "openai"
        mock_client.model = "gpt-4o"
        mock_client.get_request_settings = Mock(return_value={"provider": "openai"})

        strategy = LLMStrategy(provider="openai")
        strategy._client = mock_client

        agent = _make_agent()
        agent.seed(42)
        perception = _make_perception()
        decision = strategy.decide(agent, "travel_to:office", perception)

        # Falls back to heuristic
        assert decision.action == "travel"
        assert decision.metadata["decision_source"] == "llm_parse_error"

    @patch("agora.agents.strategy.LLMClient")
    def test_llm_fallback_on_invalid_world_target(self, MockClient):
        mock_client = Mock()
        mock_client.chat = AsyncMock(
            return_value=_mock_llm_response(target="mars", mode="rocket")
        )
        mock_client.provider_name = "openai"
        mock_client.model = "gpt-4o"
        mock_client.get_request_settings = Mock(return_value={"provider": "openai"})

        strategy = LLMStrategy(provider="openai")
        strategy._client = mock_client

        agent = _make_agent()
        agent.seed(42)
        perception = _make_perception()
        decision = strategy.decide(agent, "travel_to:office", perception)

        assert decision.action == "travel"
        assert decision.metadata["decision_source"] == "llm_parse_error"


class TestLLMStrategyAuditLogging:
    """Test that LLM strategy logs events to the simulation event log."""

    @patch("agora.agents.strategy.LLMClient")
    def test_successful_call_logs_request_and_response(self, MockClient):
        mock_client = Mock()
        mock_client.chat = AsyncMock(return_value=_mock_llm_response())
        mock_client.provider_name = "openai"
        mock_client.model = "gpt-4o"
        mock_client.get_request_settings = Mock(return_value={"provider": "openai"})

        event_log = EventLog(run_id="test123")
        strategy = LLMStrategy(provider="openai", event_log=event_log)
        strategy._client = mock_client

        agent = _make_agent()
        strategy.decide(agent, "travel_to:office", _make_perception())

        event_types = [e.event_type for e in event_log.events]
        assert EventType.LLM_REQUEST in event_types
        assert EventType.LLM_RESPONSE in event_types
        request_event = next(e for e in event_log.events if e.event_type == EventType.LLM_REQUEST)
        response_event = next(e for e in event_log.events if e.event_type == EventType.LLM_RESPONSE)
        assert "messages" in request_event.data
        assert "settings" in request_event.data
        assert response_event.data["content"].startswith("{")
        assert response_event.data["parsed_decision"]["target"] == "office"

    @patch("agora.agents.strategy.LLMClient")
    def test_error_logs_llm_error_event(self, MockClient):
        mock_client = Mock()
        mock_client.chat = AsyncMock(side_effect=LLMTransientError("rate limited"))
        mock_client.provider_name = "openai"
        mock_client.model = "gpt-4o"
        mock_client.get_request_settings = Mock(return_value={"provider": "openai"})

        event_log = EventLog(run_id="test123")
        strategy = LLMStrategy(provider="openai", event_log=event_log)
        strategy._client = mock_client

        agent = _make_agent()
        agent.seed(42)
        strategy.decide(agent, "travel_to:office", _make_perception())

        event_types = [e.event_type for e in event_log.events]
        assert EventType.LLM_ERROR in event_types

    @patch("agora.agents.strategy.LLMClient")
    def test_repeated_failures_disable_llm(self, MockClient):
        mock_client = Mock()
        mock_client.chat = AsyncMock(side_effect=LLMTransientError("provider down"))
        mock_client.provider_name = "openai"
        mock_client.model = "gpt-4o"
        mock_client.get_request_settings = Mock(return_value={"provider": "openai"})

        event_log = EventLog(run_id="test123")
        strategy = LLMStrategy(
            provider="openai",
            event_log=event_log,
            max_consecutive_failures=2,
        )
        strategy._client = mock_client

        agent = _make_agent()
        agent.seed(42)

        strategy.decide(agent, "travel_to:office", _make_perception(tick=0))
        strategy.decide(agent, "travel_to:office", _make_perception(tick=1))
        decision = strategy.decide(agent, "travel_to:office", _make_perception(tick=2))

        assert mock_client.chat.await_count == 2
        assert decision.metadata["decision_source"] == "llm_disabled"
        assert EventType.LLM_DISABLED in [e.event_type for e in event_log.events]


class TestHeuristicStrategy:
    """Verify heuristic strategy is unchanged."""

    def test_heuristic_name(self):
        s = HeuristicStrategy()
        assert s.name == "heuristic"

    def test_heuristic_delegates_to_agent(self):
        agent = _make_agent()
        agent.seed(42)
        s = HeuristicStrategy()
        perception = _make_perception()
        decision = s.decide(agent, "travel_to:office", perception)
        assert decision.action == "travel"
        assert decision.agent_id == "alice"
