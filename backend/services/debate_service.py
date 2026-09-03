"""
Debate service for Phase 3.

Orchestrates the multi-agent debate engine:

    normalized document -> labeled content
        -> [Optimist, Skeptic, Security, Financial, Ethics, Legal] (concurrent)
        -> Moderator
        -> validated DebateResult

Design goals (see Phase 3 spec):

* Each specialist agent receives the *same* original document content
  independently -- none of them sees another agent's output.
* A single agent failure (AI error, malformed JSON, schema validation
  failure) must not fail the whole debate. It is recorded on that agent's
  `AgentAnalysis` and the Moderator is told which agents failed.
* The Moderator always runs after every agent has finished (successfully or
  not), and receives only the successful agents' analyses.
* If every agent fails, there is nothing for the Moderator to meaningfully
  synthesize, so the debate fails outright with a clear error.
* If the Moderator itself fails, the whole debate fails with a clear error
  -- a partial/fabricated final result is never returned.
* Concurrency is bounded by a semaphore (`config.DEBATE_MAX_CONCURRENT_AGENTS`)
  rather than left uncontrolled, to be considerate of free-tier Groq rate
  limits.

This module reuses `services/document_service.py` (Phase 1/2, unmodified)
for fetching/validating the document and building labeled content, and
reuses `ai/client.py` and `ai/json_utils.py` (Phase 2, unmodified) for AI
transport and JSON-safety. It does not duplicate or alter any of that.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from pydantic import ValidationError as PydanticValidationError

import config
from ai.base import AIClient, AIClientError
from ai.debate_prompts import (
    MODERATOR_SYSTEM_PROMPT,
    build_agent_system_prompt,
    build_agent_user_prompt,
    build_moderator_user_prompt,
    get_agent_title,
)
from ai.json_utils import JSONExtractionError, extract_json_object
from schemas.debate import (
    AgentAnalysis,
    AgentRole,
    AgentStatus,
    DebateResult,
    DebateStatus,
    ModeratorOutput,
)
from services.document_service import prepare_document_for_analysis

logger = logging.getLogger("blindspot.debate")

# The six independent specialist agents run for every debate, in a fixed,
# stable order (order of the resulting `agent_analyses` list, not order of
# completion -- `asyncio.gather` preserves input order regardless of which
# call finishes first).
AGENT_ROLES: list[AgentRole] = [
    AgentRole.OPTIMIST,
    AgentRole.SKEPTIC,
    AgentRole.SECURITY,
    AgentRole.FINANCIAL,
    AgentRole.ETHICS,
    AgentRole.LEGAL,
]


class DebateServiceError(Exception):
    """Base class for debate-service errors surfaced to the API layer."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class DebateGenerationError(DebateServiceError):
    """Raised when the Moderator's response could not be turned into a valid result."""


class DebateAllAgentsFailedError(DebateServiceError):
    """Raised when every specialist agent failed, leaving nothing to moderate."""


def _filter_source_locations(items: list[Any], valid_locations: set[int]) -> None:
    """Cross-check `source_locations` on a list of finding-like objects
    against locations that genuinely exist in the document, dropping any
    that don't. Shared logic mirroring Phase 2's safeguard, generalized to
    any object exposing a `source_locations: list[int]` attribute."""
    if not valid_locations:
        return
    for item in items:
        item.source_locations = [
            loc for loc in item.source_locations if loc in valid_locations
        ]


async def _run_single_agent(
    agent: AgentRole,
    ai_client: AIClient,
    labeled_content: str,
    content_item_count: int,
    valid_locations: set[int],
    semaphore: asyncio.Semaphore,
) -> AgentAnalysis:
    """Run one specialist agent and always return an `AgentAnalysis`.

    Never raises -- any failure (AI transport, JSON extraction, schema
    validation, or anything unexpected) is captured and returned as a
    failed `AgentAnalysis` so that one bad agent can never take down the
    whole debate.
    """
    role_title = get_agent_title(agent)
    system_prompt = build_agent_system_prompt(agent)
    user_prompt = build_agent_user_prompt(labeled_content, content_item_count)

    try:
        async with semaphore:
            raw_response = await ai_client.generate(system_prompt, user_prompt)
    except AIClientError as exc:
        logger.warning("Agent '%s' failed (AI client error): %s", agent.value, exc.message)
        return AgentAnalysis(
            agent=agent,
            role=role_title,
            status=AgentStatus.FAILED,
            error=exc.message,
        )
    except Exception as exc:  # noqa: BLE001 - one agent must never crash the debate
        logger.exception("Agent '%s' failed unexpectedly", agent.value)
        return AgentAnalysis(
            agent=agent,
            role=role_title,
            status=AgentStatus.FAILED,
            error=f"Unexpected error running {role_title}: {exc}",
        )

    try:
        parsed_json = extract_json_object(raw_response)
    except JSONExtractionError as exc:
        logger.warning(
            "Agent '%s' produced unparseable output: %s", agent.value, exc.message
        )
        return AgentAnalysis(
            agent=agent,
            role=role_title,
            status=AgentStatus.FAILED,
            error="The AI model did not return a parseable response for this agent.",
        )

    parsed_json["agent"] = agent.value
    parsed_json["role"] = role_title
    parsed_json.setdefault("status", AgentStatus.SUCCEEDED.value)

    try:
        analysis = AgentAnalysis.model_validate(parsed_json)
    except PydanticValidationError as exc:
        logger.warning(
            "Agent '%s' response failed schema validation: %s", agent.value, exc
        )
        return AgentAnalysis(
            agent=agent,
            role=role_title,
            status=AgentStatus.FAILED,
            error="This agent's response did not match the expected format.",
        )

    _filter_source_locations(analysis.findings, valid_locations)
    _filter_source_locations(analysis.assumptions, valid_locations)

    return analysis


async def run_debate(document_id: str, ai_client: AIClient) -> DebateResult:
    """
    Run the full Phase 3 multi-agent debate for a document.

    Raises (all defined in services.document_service, allowed to propagate
    to the API layer for precise HTTP status mapping, same as Phase 2):
        DocumentNotFoundError
        DocumentNotReadyError
        DocumentHasNoAnalyzableContentError
        DocumentTooLargeForAnalysisError

    Raises DebateAllAgentsFailedError if every specialist agent failed.
    Raises DebateGenerationError if the Moderator's response cannot be
    turned into a valid DebateResult. Raises ai.base.AIClientError subclasses
    untouched if the Moderator call itself fails (connection, timeout,
    missing model, etc) -- a partial result is never fabricated in that case.
    """
    document, labeled_content, valid_locations, content_item_count = (
        prepare_document_for_analysis(document_id)
    )

    semaphore = asyncio.Semaphore(max(1, config.DEBATE_MAX_CONCURRENT_AGENTS))

    agent_analyses = await asyncio.gather(
        *[
            _run_single_agent(
                agent,
                ai_client,
                labeled_content,
                content_item_count,
                valid_locations,
                semaphore,
            )
            for agent in AGENT_ROLES
        ]
    )
    agent_analyses = list(agent_analyses)

    successful = [a for a in agent_analyses if a.status == AgentStatus.SUCCEEDED]
    failed = [a for a in agent_analyses if a.status == AgentStatus.FAILED]

    if not successful:
        raise DebateAllAgentsFailedError(
            "All specialist agents failed to produce an analysis, so no "
            "debate report could be generated. Please try again."
        )

    failed_agent_names = [get_agent_title(a.agent) for a in failed]
    moderator_user_prompt = build_moderator_user_prompt(
        labeled_content, content_item_count, successful, failed_agent_names
    )

    # Let AIClientError subclasses propagate untouched -- the API layer maps
    # them to specific, user-facing HTTP errors, exactly as Phase 2 does.
    raw_moderator_response = await ai_client.generate(
        MODERATOR_SYSTEM_PROMPT, moderator_user_prompt
    )

    try:
        parsed_moderator_json = extract_json_object(raw_moderator_response)
    except JSONExtractionError as exc:
        logger.warning(
            "Failed to extract JSON from moderator response for %s: %s",
            document_id,
            exc.message,
        )
        raise DebateGenerationError(
            "The AI model did not return a parseable moderator response. "
            "Please try again."
        ) from exc

    try:
        moderator_output = ModeratorOutput.model_validate(parsed_moderator_json)
    except PydanticValidationError as exc:
        logger.warning(
            "Moderator response for %s failed schema validation: %s", document_id, exc
        )
        raise DebateGenerationError(
            "The moderator's response did not match the expected format. "
            "Please try again."
        ) from exc

    _filter_source_locations(moderator_output.final_risks, valid_locations)
    _filter_source_locations(moderator_output.final_assumptions, valid_locations)
    _filter_source_locations(moderator_output.final_biases, valid_locations)

    return DebateResult(
        document_id=document_id,
        status=DebateStatus.COMPLETED,
        agent_analyses=agent_analyses,
        agreements=moderator_output.agreements,
        disagreements=moderator_output.disagreements,
        final_blind_spots=moderator_output.final_blind_spots,
        final_risks=moderator_output.final_risks,
        final_assumptions=moderator_output.final_assumptions,
        final_biases=moderator_output.final_biases,
        missing_perspectives=moderator_output.missing_perspectives,
        unanswered_questions=moderator_output.unanswered_questions,
        recommendations=moderator_output.recommendations,
        overall_assessment=moderator_output.overall_assessment,
        metadata={
            "model": ai_client.model_name,
            "agents_used": len(AGENT_ROLES),
            "agents_succeeded": [a.agent.value for a in successful],
            "agents_failed": [a.agent.value for a in failed],
            "analyzed_content_items": content_item_count,
        },
    )
