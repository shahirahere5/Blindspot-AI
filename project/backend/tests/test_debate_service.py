"""Tests for services.debate_service.run_debate (Phase 3 orchestration)."""

from __future__ import annotations

import pytest

from ai.base import AIConnectionError, AITimeoutError
from schemas.debate import AgentStatus, DebateStatus
from services.debate_service import (
    DebateAllAgentsFailedError,
    DebateGenerationError,
    run_debate,
)
from services.document_service import DocumentNotFoundError
from tests.fakes import (
    ALL_VALID_AGENT_RESPONSES,
    INVALID_AGENT_JSON_RESPONSE,
    VALID_MODERATOR_JSON,
    VALID_MODERATOR_JSON_WITH_FAKE_LOCATION,
    DebateFakeAIClient,
)


def _all_success_responses(moderator: str = VALID_MODERATOR_JSON) -> dict[str, str]:
    return {**ALL_VALID_AGENT_RESPONSES, "moderator": moderator}


# ---------------------------------------------------------------------------
# 1. All six agents execute + moderator receives results + full success
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_full_debate_runs_all_agents_and_moderator(
    client, uploaded_txt_document_id
):
    fake_client = DebateFakeAIClient(responses=_all_success_responses())

    result = await run_debate(uploaded_txt_document_id, fake_client)

    assert result.status == DebateStatus.COMPLETED
    assert len(result.agent_analyses) == 6
    assert all(a.status == AgentStatus.SUCCEEDED for a in result.agent_analyses)
    assert result.metadata["agents_used"] == 6
    assert sorted(result.metadata["agents_succeeded"]) == sorted(
        [
            "optimist",
            "skeptic",
            "security",
            "financial",
            "ethics",
            "legal",
        ]
    )
    assert result.metadata["agents_failed"] == []
    assert result.overall_assessment
    assert len(result.final_risks) == 1
    # 7 total calls: 6 agents + 1 moderator.
    assert len(fake_client.calls) == 7


# ---------------------------------------------------------------------------
# 2. One failed agent does not fail the entire debate
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_one_agent_failure_does_not_fail_the_debate(
    client, uploaded_txt_document_id
):
    responses = _all_success_responses()
    del responses["financial"]
    fake_client = DebateFakeAIClient(
        responses=responses,
        errors={"financial": AIConnectionError("Could not connect to Groq.")},
    )

    result = await run_debate(uploaded_txt_document_id, fake_client)

    assert result.status == DebateStatus.COMPLETED
    assert len(result.agent_analyses) == 6
    failed = [a for a in result.agent_analyses if a.status == AgentStatus.FAILED]
    assert len(failed) == 1
    assert failed[0].agent.value == "financial"
    assert result.metadata["agents_failed"] == ["financial"]
    assert "financial" not in result.metadata["agents_succeeded"]

    # The moderator prompt should have been told financial analysis failed.
    moderator_calls = [
        (sp, up) for sp, up in fake_client.calls if "Moderator Agent" in sp
    ]
    assert len(moderator_calls) == 1
    assert "Financial Agent" in moderator_calls[0][1]


# ---------------------------------------------------------------------------
# 3. All agents failing leaves nothing to moderate
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_all_agents_failing_raises_clear_error(client, uploaded_txt_document_id):
    error = AITimeoutError("Groq did not respond in time.")
    fake_client = DebateFakeAIClient(
        errors={
            "optimist": error,
            "skeptic": error,
            "security": error,
            "financial": error,
            "ethics": error,
            "legal": error,
        }
    )

    with pytest.raises(DebateAllAgentsFailedError):
        await run_debate(uploaded_txt_document_id, fake_client)

    # The moderator must never be called if there is nothing to moderate.
    assert all("Moderator Agent" not in sp for sp, _ in fake_client.calls)


# ---------------------------------------------------------------------------
# 4. Moderator failure is handled -- no fabricated final result
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_moderator_ai_failure_propagates(client, uploaded_txt_document_id):
    fake_client = DebateFakeAIClient(
        responses=ALL_VALID_AGENT_RESPONSES,
        errors={"moderator": AIConnectionError("Could not connect to Groq.")},
    )

    with pytest.raises(AIConnectionError):
        await run_debate(uploaded_txt_document_id, fake_client)


@pytest.mark.asyncio
async def test_moderator_unparseable_response_raises_generation_error(
    client, uploaded_txt_document_id
):
    fake_client = DebateFakeAIClient(
        responses={
            **ALL_VALID_AGENT_RESPONSES,
            "moderator": INVALID_AGENT_JSON_RESPONSE,
        }
    )

    with pytest.raises(DebateGenerationError):
        await run_debate(uploaded_txt_document_id, fake_client)


@pytest.mark.asyncio
async def test_moderator_schema_validation_failure_raises_generation_error(
    client, uploaded_txt_document_id
):
    bad_moderator_json = '{"overall_assessment": "ok", "final_risks": "not a list"}'
    fake_client = DebateFakeAIClient(
        responses={**ALL_VALID_AGENT_RESPONSES, "moderator": bad_moderator_json}
    )

    with pytest.raises(DebateGenerationError):
        await run_debate(uploaded_txt_document_id, fake_client)


# ---------------------------------------------------------------------------
# 5. Fabricated source locations from the moderator are filtered
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_moderator_fabricated_source_location_is_filtered(
    client, uploaded_txt_document_id
):
    fake_client = DebateFakeAIClient(
        responses=_all_success_responses(VALID_MODERATOR_JSON_WITH_FAKE_LOCATION)
    )

    result = await run_debate(uploaded_txt_document_id, fake_client)

    assert result.final_risks[0].source_locations == [1]


# ---------------------------------------------------------------------------
# 6. Missing document
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_debate_missing_document_raises_not_found(client):
    fake_client = DebateFakeAIClient(responses=_all_success_responses())

    with pytest.raises(DocumentNotFoundError):
        await run_debate("doc_does_not_exist", fake_client)

    assert fake_client.calls == []
