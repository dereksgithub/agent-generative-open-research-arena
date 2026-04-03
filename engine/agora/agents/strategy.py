"""Decision strategy abstraction — separates HOW agents decide from the simulation loop.

The simulation engine calls strategy.decide() during the decide phase.
Different strategies (heuristic, LLM-backed, hybrid) implement this interface.

Model routing:
  - HeuristicStrategy: deterministic, no LLM calls — cheapest, fastest, reproducible.
  - LLMStrategy: sends agent persona + perception to an LLM and parses structured output.
                  Falls back to heuristic on parse failure or after retry exhaustion.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, Any

from agora.cognition.prompt import (
    SYSTEM_PROMPT,
    build_agent_context,
    build_user_prompt,
    parse_llm_decision,
)
from agora.llm.client import LLMClient, LLMError, LLMResponse

if TYPE_CHECKING:
    from agora.simulation.event_log import EventLog

    from .agent import Agent, Decision

logger = logging.getLogger(__name__)


class DecisionStrategy(ABC):
    """Abstract base for agent decision-making strategies."""

    @abstractmethod
    def decide(
        self,
        agent: "Agent",
        goal: str,
        perception: dict[str, Any],
    ) -> "Decision":
        """Given an agent, its goal, and its perception, produce a decision."""

    @property
    def name(self) -> str:
        return self.__class__.__name__.removesuffix("Strategy").lower()


class HeuristicStrategy(DecisionStrategy):
    """Rule-based decisions — deterministic, no LLM calls.

    This is the default strategy used when --no-llm is passed.
    It delegates to Agent.decide() which contains the heuristic logic.
    """

    def decide(
        self,
        agent: "Agent",
        goal: str,
        perception: dict[str, Any],
    ) -> "Decision":
        return agent.decide(goal, perception)


class LLMStrategy(DecisionStrategy):
    """LLM-backed agent decisions with structured prompt contract.

    Sends the agent's persona, perception, and goal to an LLM, parses the
    structured JSON response into a Decision, and falls back to heuristic
    on any failure.

    Supports:
      - Any provider registered in the LLM client (OpenAI, Anthropic, local, etc.)
      - Optional prompt caching for reproducibility and cost control
      - Audit logging of every LLM interaction via the simulation event log
      - Graceful fallback to heuristic on parse errors or API failures
    """

    def __init__(
        self,
        *,
        provider: str = "openai",
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        temperature: float = 0.4,
        max_tokens: int = 512,
        timeout: float = 60.0,
        max_retries: int = 2,
        cache_dir: Path | None = None,
        event_log: "EventLog | None" = None,
        max_consecutive_failures: int = 3,
    ) -> None:
        self._client = LLMClient(
            provider=provider,
            model=model,
            api_key=api_key,
            base_url=base_url,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
            max_retries=max_retries,
            cache_dir=cache_dir,
        )
        self._event_log = event_log
        self._fallback = HeuristicStrategy()
        self._consecutive_failures = 0
        self._max_consecutive_failures = max(1, max_consecutive_failures)
        self._llm_disabled_reason: str | None = None

    def set_event_log(self, event_log: "EventLog") -> None:
        """Attach the simulation event log for LLM audit logging."""
        self._event_log = event_log

    def decide(
        self,
        agent: "Agent",
        goal: str,
        perception: dict[str, Any],
    ) -> "Decision":
        """Synchronous wrapper — runs the async LLM call in an event loop."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # We're inside an existing event loop (e.g. Jupyter).
            # Create a new thread to run the coroutine.
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, self._decide_async(agent, goal, perception))
                return future.result()
        else:
            return asyncio.run(self._decide_async(agent, goal, perception))

    async def _decide_async(
        self,
        agent: "Agent",
        goal: str,
        perception: dict[str, Any],
    ) -> "Decision":
        """The real LLM decision flow."""
        from .agent import Decision

        tick = perception.get("tick", 0)
        if self._llm_disabled_reason is not None:
            return self._fallback_decide(
                agent,
                goal,
                perception,
                reason=self._llm_disabled_reason,
                source="llm_disabled",
            )

        agent_ctx = build_agent_context(agent)
        user_prompt = build_user_prompt(agent_ctx, goal, perception)
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]
        request_settings = self._client.get_request_settings()
        prompt_hash = hashlib.sha256(
            json.dumps(messages, sort_keys=True).encode("utf-8")
        ).hexdigest()

        # Audit: log the request
        self._log_event(
            "LLM_REQUEST",
            tick,
            agent.id,
            {
                "provider": self._client.provider_name,
                "model": self._client.model,
                "prompt_length": len(user_prompt),
                "prompt_sha256": prompt_hash,
                "settings": request_settings,
                "messages": messages,
            },
        )

        try:
            resp: LLMResponse = await self._client.chat(messages)
        except LLMError as exc:
            logger.warning("LLM call failed for agent %s at tick %d: %s — falling back to heuristic",
                           agent.id, tick, exc)
            self._register_failure(tick, agent.id, str(exc))
            self._log_event(
                "LLM_ERROR", tick, agent.id,
                {"error": str(exc), "retryable": exc.retryable},
            )
            return self._fallback_decide(
                agent,
                goal,
                perception,
                reason=str(exc),
                source="llm_error",
            )

        # Audit: log the response
        log_data: dict[str, Any] = {
            "provider": resp.provider,
            "model": resp.model,
            "prompt_tokens": resp.prompt_tokens,
            "completion_tokens": resp.completion_tokens,
            "total_tokens": resp.total_tokens,
            "latency_ms": resp.latency_ms,
            "cached": resp.cached,
            "content": resp.content,
            "prompt_sha256": prompt_hash,
        }

        # Parse the structured response
        try:
            parsed = parse_llm_decision(resp.content)
            normalized = self._normalize_llm_decision(parsed, perception)
        except ValueError as exc:
            logger.warning("Failed to parse LLM response for agent %s at tick %d: %s — falling back",
                           agent.id, tick, exc)
            self._register_failure(tick, agent.id, f"Parse failure: {exc}")
            self._log_event(
                "LLM_ERROR", tick, agent.id,
                {"error": f"Parse failure: {exc}", "raw_content": resp.content[:500]},
            )
            return self._fallback_decide(
                agent,
                goal,
                perception,
                reason=f"Parse failure: {exc}",
                source="llm_parse_error",
            )

        log_data["parsed_decision"] = normalized
        if resp.cached:
            self._log_event("LLM_CACHE_HIT", tick, agent.id, log_data)
        else:
            self._log_event("LLM_RESPONSE", tick, agent.id, log_data)
        self._consecutive_failures = 0

        return Decision(
            tick=tick,
            agent_id=agent.id,
            action=normalized["action"],
            target=normalized["target"],
            reasoning=normalized["reasoning"],
            metadata={
                "mode": normalized.get("mode", ""),
                "decision_source": "llm",
                "llm_provider": resp.provider,
                "llm_model": resp.model,
                "llm_tokens": resp.total_tokens,
                "llm_latency_ms": resp.latency_ms,
                "llm_cached": resp.cached,
            },
        )

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.close()

    def get_accounting(self) -> dict[str, Any]:
        """Return cumulative token/latency accounting."""
        return self._client.get_accounting()

    def get_settings(self) -> dict[str, Any]:
        """Return normalized request settings for run metadata."""
        settings = self._client.get_request_settings()
        settings["max_consecutive_failures"] = self._max_consecutive_failures
        return settings

    def get_status(self) -> dict[str, Any]:
        """Return runtime LLM status for run metadata."""
        return {
            "disabled": self._llm_disabled_reason is not None,
            "disabled_reason": self._llm_disabled_reason,
            "consecutive_failures": self._consecutive_failures,
        }

    def _log_event(
        self, event_type_name: str, tick: int, agent_id: str, data: dict[str, Any]
    ) -> None:
        """Write to the simulation event log if available."""
        if self._event_log is None:
            return
        from agora.simulation.event_log import EventType
        et = EventType(event_type_name.lower())
        self._event_log.record(tick=tick, event_type=et, agent_id=agent_id, data=data)

    def _normalize_llm_decision(
        self,
        parsed: dict[str, Any],
        perception: dict[str, Any],
    ) -> dict[str, str]:
        action = parsed["action"]
        current_location = str(perception.get("current_location", ""))
        routes = perception.get("available_routes", [])

        if action == "stay":
            return {
                "action": "stay",
                "target": current_location,
                "mode": "",
                "reasoning": parsed.get("reasoning", ""),
            }

        valid_routes = [route for route in routes if route.get("to")]
        valid_targets = {str(route["to"]) for route in valid_routes}
        target = str(parsed.get("target", "")).strip()
        if target not in valid_targets or target == current_location:
            raise ValueError(f"Invalid travel target '{target}' for current perception")

        candidate_routes = [route for route in valid_routes if str(route.get("to")) == target]
        valid_modes = {str(route.get("mode", "")).strip() for route in candidate_routes if route.get("mode")}
        mode = str(parsed.get("mode", "")).strip()
        if not mode:
            raise ValueError(f"Missing travel mode for target '{target}'")
        if mode not in valid_modes:
            raise ValueError(f"Invalid travel mode '{mode}' for target '{target}'")

        return {
            "action": "travel",
            "target": target,
            "mode": mode,
            "reasoning": parsed.get("reasoning", ""),
        }

    def _fallback_decide(
        self,
        agent: "Agent",
        goal: str,
        perception: dict[str, Any],
        *,
        reason: str,
        source: str,
    ) -> "Decision":
        decision = self._fallback.decide(agent, goal, perception)
        decision.metadata = {
            **decision.metadata,
            "decision_source": source,
            "fallback_reason": reason,
            "llm_provider_attempted": self._client.provider_name,
            "llm_model_attempted": self._client.model,
            "llm_disabled": self._llm_disabled_reason is not None,
        }
        return decision

    def _register_failure(self, tick: int, agent_id: str, reason: str) -> None:
        self._consecutive_failures += 1
        if (
            self._llm_disabled_reason is None
            and self._consecutive_failures >= self._max_consecutive_failures
        ):
            self._llm_disabled_reason = (
                f"LLM disabled after {self._consecutive_failures} consecutive failures: {reason}"
            )
            self._log_event(
                "LLM_DISABLED",
                tick,
                agent_id,
                {
                    "provider": self._client.provider_name,
                    "model": self._client.model,
                    "reason": self._llm_disabled_reason,
                    "consecutive_failures": self._consecutive_failures,
                },
            )
