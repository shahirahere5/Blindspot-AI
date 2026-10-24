"""Focused tests for bounded, provider-aware debate rate-limit handling."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
import pytest

import config
from ai.base import AIAuthenticationError, AIClient, AIRateLimitError
from schemas.debate import AgentStatus, DebateStatus
from services.debate_service import (
    DebateAllAgentsFailedError,
    DebateRequestController,
    run_debate,
)
from tests.fakes import (
    ALL_VALID_AGENT_RESPONSES,
    VALID_MODERATOR_JSON,
    _debate_role_key,
)


class SequencedDebateClient(AIClient):
    def __init__(self, outcomes: dict[str, Sequence[str | Exception]]) -> None:
        self.outcomes = {role: list(values) for role, values in outcomes.items()}
        self.calls: list[str] = []

    @property
    def model_name(self) -> str:
        return "fake-model"

    async def generate(self, system_prompt: str, user_prompt: str) -> str:
        role = _debate_role_key(system_prompt)
        self.calls.append(role)
        values = self.outcomes.get(role)
        if not values:
            raise AssertionError(f"No outcome remains for {role}")
        outcome = values.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def time(self) -> float:
        return self.now

    async def sleep(self, delay: float) -> None:
        self.sleeps.append(delay)
        self.now += delay


def _successful_outcomes() -> dict[str, list[str | Exception]]:
    return {
        **{role: [response] for role, response in ALL_VALID_AGENT_RESPONSES.items()},
        "moderator": [VALID_MODERATOR_JSON],
    }


def _enable_fast_retries(monkeypatch, retries: int) -> None:
    monkeypatch.setattr(config, "DEBATE_MAX_CONCURRENT_AGENTS", 2)
    monkeypatch.setattr(config, "DEBATE_MAX_RATE_LIMIT_RETRIES", retries)
    monkeypatch.setattr(config, "DEBATE_RETRY_BASE_DELAY_SECONDS", 0.0)
    monkeypatch.setattr(config, "DEBATE_RETRY_MAX_DELAY_SECONDS", 0.0)
    monkeypatch.setattr(config, "DEBATE_RETRY_JITTER_SECONDS", 0.0)
    monkeypatch.setattr(config, "DEBATE_REQUEST_INTERVAL_SECONDS", 0.0)
    monkeypatch.setattr(config, "DEBATE_RAG_ENABLED", False)


@pytest.mark.asyncio
async def test_one_agent_rate_limit_then_success_is_retried_once(
    client, monkeypatch, uploaded_txt_document_id
):
    _enable_fast_retries(monkeypatch, 2)
    outcomes = _successful_outcomes()
    outcomes["security"] = [
        AIRateLimitError("safe", retry_after_seconds=0),
        ALL_VALID_AGENT_RESPONSES["security"],
    ]
    ai_client = SequencedDebateClient(outcomes)

    result = await run_debate(uploaded_txt_document_id, ai_client)

    assert result.status == DebateStatus.COMPLETED
    assert next(a for a in result.agent_analyses if a.agent.value == "security").status == AgentStatus.SUCCEEDED
    assert ai_client.calls.count("security") == 2
    assert len(ai_client.calls) == 8


@pytest.mark.asyncio
async def test_agent_exhausting_retries_remains_a_partial_failure(
    client, monkeypatch, uploaded_txt_document_id
):
    _enable_fast_retries(monkeypatch, 2)
    outcomes = _successful_outcomes()
    outcomes["security"] = [AIRateLimitError("safe")] * 3
    ai_client = SequencedDebateClient(outcomes)

    result = await run_debate(uploaded_txt_document_id, ai_client)

    security = next(a for a in result.agent_analyses if a.agent.value == "security")
    assert security.status == AgentStatus.FAILED
    assert result.metadata["agents_failed"] == ["security"]
    assert ai_client.calls.count("security") == 3
    assert ai_client.calls.count("moderator") == 1


@pytest.mark.asyncio
async def test_all_agents_exhausting_rate_limit_never_calls_moderator(
    client, monkeypatch, uploaded_txt_document_id
):
    _enable_fast_retries(monkeypatch, 1)
    outcomes = {
        role: [AIRateLimitError("safe"), AIRateLimitError("safe")]
        for role in ALL_VALID_AGENT_RESPONSES
    }
    ai_client = SequencedDebateClient(outcomes)

    with pytest.raises(DebateAllAgentsFailedError):
        await run_debate(uploaded_txt_document_id, ai_client)

    assert len(ai_client.calls) == 12
    assert "moderator" not in ai_client.calls


@pytest.mark.asyncio
async def test_moderator_rate_limit_then_success_is_retried(
    client, monkeypatch, uploaded_txt_document_id
):
    _enable_fast_retries(monkeypatch, 2)
    outcomes = _successful_outcomes()
    outcomes["moderator"] = [AIRateLimitError("safe"), VALID_MODERATOR_JSON]
    ai_client = SequencedDebateClient(outcomes)

    result = await run_debate(uploaded_txt_document_id, ai_client)

    assert result.status == DebateStatus.COMPLETED
    assert ai_client.calls.count("moderator") == 2


@pytest.mark.asyncio
async def test_moderator_rate_limit_retries_are_bounded(
    client, monkeypatch, uploaded_txt_document_id
):
    _enable_fast_retries(monkeypatch, 2)
    outcomes = _successful_outcomes()
    outcomes["moderator"] = [AIRateLimitError("safe")] * 3
    ai_client = SequencedDebateClient(outcomes)

    with pytest.raises(AIRateLimitError):
        await run_debate(uploaded_txt_document_id, ai_client)

    assert ai_client.calls.count("moderator") == 3


@pytest.mark.asyncio
async def test_retry_after_and_exponential_backoff_are_respected():
    clock = FakeClock()
    outcomes: list[str | Exception] = [
        AIRateLimitError("safe", retry_after_seconds=2.5),
        "ok",
    ]

    class Client(AIClient):
        model_name = "fake-model"

        async def generate(self, system_prompt: str, user_prompt: str) -> str:
            outcome = outcomes.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

    controller = DebateRequestController(
        Client(), max_concurrency=1, max_retries=2,
        base_delay_seconds=1.0, max_delay_seconds=10.0,
        jitter_seconds=0.0, request_interval_seconds=0.0,
        sleep=clock.sleep, clock=clock.time,
    )

    assert await controller.generate("system", "user", caller="test") == "ok"
    assert clock.sleeps == [2.5]


@pytest.mark.asyncio
async def test_retry_count_is_bounded_and_authentication_is_not_retried():
    rate_clock = FakeClock()

    class AlwaysLimited(AIClient):
        model_name = "fake-model"

        def __init__(self) -> None:
            self.calls = 0

        async def generate(self, system_prompt: str, user_prompt: str) -> str:
            self.calls += 1
            raise AIRateLimitError("safe")

    limited = AlwaysLimited()
    controller = DebateRequestController(
        limited, max_concurrency=1, max_retries=2,
        base_delay_seconds=1.0, max_delay_seconds=10.0,
        jitter_seconds=0.0, request_interval_seconds=0.0,
        sleep=rate_clock.sleep, clock=rate_clock.time,
    )
    with pytest.raises(AIRateLimitError):
        await controller.generate("system", "user", caller="test")
    assert limited.calls == 3
    assert rate_clock.sleeps == [1.0, 2.0]

    class AuthenticationFailure(AIClient):
        model_name = "fake-model"

        def __init__(self) -> None:
            self.calls = 0

        async def generate(self, system_prompt: str, user_prompt: str) -> str:
            self.calls += 1
            raise AIAuthenticationError("safe")

    authentication = AuthenticationFailure()
    auth_controller = DebateRequestController(
        authentication, max_concurrency=1, max_retries=5,
        base_delay_seconds=1.0, max_delay_seconds=10.0,
        jitter_seconds=0.0, request_interval_seconds=0.0,
    )
    with pytest.raises(AIAuthenticationError):
        await auth_controller.generate("system", "user", caller="test")
    assert authentication.calls == 1


@pytest.mark.asyncio
async def test_controller_respects_concurrency_limit():
    class TrackingClient(AIClient):
        model_name = "fake-model"

        def __init__(self) -> None:
            self.active = 0
            self.maximum_active = 0

        async def generate(self, system_prompt: str, user_prompt: str) -> str:
            self.active += 1
            self.maximum_active = max(self.maximum_active, self.active)
            await asyncio.sleep(0.01)
            self.active -= 1
            return "ok"

    tracking = TrackingClient()
    controller = DebateRequestController(
        tracking, max_concurrency=2, max_retries=0,
        base_delay_seconds=0.0, max_delay_seconds=0.0,
        jitter_seconds=0.0, request_interval_seconds=0.0,
    )

    await asyncio.gather(*[
        controller.generate("system", f"user-{index}", caller=f"test-{index}")
        for index in range(6)
    ])

    assert tracking.maximum_active == 2


@pytest.mark.asyncio
async def test_controller_paces_request_starts():
    clock = FakeClock()

    class InstantClient(AIClient):
        model_name = "fake-model"

        async def generate(self, system_prompt: str, user_prompt: str) -> str:
            return "ok"

    controller = DebateRequestController(
        InstantClient(), max_concurrency=2, max_retries=0,
        base_delay_seconds=0.0, max_delay_seconds=0.0,
        jitter_seconds=0.0, request_interval_seconds=2.0,
        sleep=clock.sleep, clock=clock.time,
    )

    await asyncio.gather(*[
        controller.generate("system", f"user-{index}", caller=f"test-{index}")
        for index in range(3)
    ])

    assert clock.sleeps == [2.0, 2.0]
