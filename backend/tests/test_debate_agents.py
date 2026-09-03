"""Unit tests for individual specialist agents in the Phase 3 debate engine."""

from __future__ import annotations

import asyncio

import pytest

from ai.base import AIConnectionError, AIRateLimitError, AITimeoutError
from ai.debate_prompts import build_agent_system_prompt, get_agent_title
from schemas.debate import AgentRole, AgentStatus
from services.debate_service import _run_single_agent
from tests.fakes import (
    INVALID_AGENT_JSON_RESPONSE,
    MALFORMED_AGENT_SCHEMA_JSON,
    DebateFakeAIClient,
    valid_agent_json,
)


ALL_ROLES = [
    AgentRole.OPTIMIST,
    AgentRole.SKEPTIC,
    AgentRole.SECURITY,
    AgentRole.FINANCIAL,
    AgentRole.ETHICS,
    AgentRole.LEGAL,
]


# ---------------------------------------------------------------------------
# 1. Each agent can be constructed / has the correct role
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("agent", ALL_ROLES)
def test_each_agent_has_a_distinct_title(agent):
    title = get_agent_title(agent)
    assert title
    assert "Agent" in title


@pytest.mark.parametrize("agent", ALL_ROLES)
def test_each_agent_system_prompt_declares_its_role(agent):
    prompt = build_agent_system_prompt(agent)
    assert get_agent_title(agent) in prompt


def test_agent_titles_are_all_unique():
    titles = {get_agent_title(agent) for agent in ALL_ROLES}
    assert len(titles) == len(ALL_ROLES)


# ---------------------------------------------------------------------------
# 2. Agent output parses correctly
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize("agent", ALL_ROLES)
async def test_agent_parses_valid_response(agent):
    role_key = agent.value
    fake_client = DebateFakeAIClient(responses={role_key: valid_agent_json()})
    semaphore = asyncio.Semaphore(6)

    result = await _run_single_agent(
        agent, fake_client, "[TEXT 1]\nHello.", 1, {1}, semaphore
    )

    assert result.status == AgentStatus.SUCCEEDED
    assert result.agent == agent
    assert result.role == get_agent_title(agent)
    assert len(result.findings) == 1
    assert len(result.assumptions) == 1
    assert len(result.questions) == 1
    assert result.confidence.value == "medium"
    assert len(fake_client.calls) == 1


# ---------------------------------------------------------------------------
# 3. Malformed JSON is handled
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_agent_handles_unparseable_response():
    fake_client = DebateFakeAIClient(
        responses={"skeptic": INVALID_AGENT_JSON_RESPONSE}
    )
    semaphore = asyncio.Semaphore(6)

    result = await _run_single_agent(
        AgentRole.SKEPTIC, fake_client, "[TEXT 1]\nHello.", 1, {1}, semaphore
    )

    assert result.status == AgentStatus.FAILED
    assert result.error is not None
    assert result.findings == []


@pytest.mark.asyncio
async def test_agent_handles_schema_validation_failure():
    fake_client = DebateFakeAIClient(
        responses={"financial": MALFORMED_AGENT_SCHEMA_JSON}
    )
    semaphore = asyncio.Semaphore(6)

    result = await _run_single_agent(
        AgentRole.FINANCIAL, fake_client, "[TEXT 1]\nHello.", 1, {1}, semaphore
    )

    assert result.status == AgentStatus.FAILED
    assert result.error is not None


# ---------------------------------------------------------------------------
# 4. Agent failures (AI client errors) are handled
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        AIConnectionError("Could not connect to Groq."),
        AITimeoutError("Groq did not respond in time."),
        AIRateLimitError("Rate limit reached."),
    ],
)
async def test_agent_handles_ai_client_errors(error):
    fake_client = DebateFakeAIClient(errors={"ethics": error})
    semaphore = asyncio.Semaphore(6)

    result = await _run_single_agent(
        AgentRole.ETHICS, fake_client, "[TEXT 1]\nHello.", 1, {1}, semaphore
    )

    assert result.status == AgentStatus.FAILED
    assert result.error == error.message
    assert result.agent == AgentRole.ETHICS


# ---------------------------------------------------------------------------
# 5. Fabricated source locations are filtered, same safeguard as Phase 2
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_agent_filters_fabricated_source_locations():
    response = valid_agent_json().replace(
        '"source_locations": [1]', '"source_locations": [1, 999]'
    )
    fake_client = DebateFakeAIClient(responses={"legal": response})
    semaphore = asyncio.Semaphore(6)

    result = await _run_single_agent(
        AgentRole.LEGAL, fake_client, "[TEXT 1]\nHello.", 1, {1}, semaphore
    )

    assert result.status == AgentStatus.SUCCEEDED
    assert result.findings[0].source_locations == [1]
