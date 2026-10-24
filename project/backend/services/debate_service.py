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
import random
import time
from typing import Any

from pydantic import ValidationError as PydanticValidationError

import config
from ai.base import AIClient, AIClientError, AIRateLimitError
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
from services import rag_service
from services.document_service import (
    ensure_document_is_analyzable,
    get_document_or_raise,
    prepare_document_for_analysis,
)

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


class DebateRequestController:
    """Bound concurrency, pace request starts, and retry transient 429s.

    One controller is shared by all six specialists and the moderator so a
    provider-requested cooldown applies to the whole debate, not just to the
    individual task that received the 429.
    """

    def __init__(
        self,
        ai_client: AIClient,
        *,
        max_concurrency: int,
        max_retries: int,
        base_delay_seconds: float,
        max_delay_seconds: float,
        jitter_seconds: float,
        request_interval_seconds: float,
        sleep=asyncio.sleep,
        clock=time.monotonic,
        random_uniform=random.uniform,
    ) -> None:
        self.ai_client = ai_client
        self.max_retries = max(0, max_retries)
        self.base_delay_seconds = max(0.0, base_delay_seconds)
        self.max_delay_seconds = max(self.base_delay_seconds, max_delay_seconds)
        self.jitter_seconds = max(0.0, jitter_seconds)
        self.request_interval_seconds = max(0.0, request_interval_seconds)
        self._semaphore = asyncio.Semaphore(max(1, max_concurrency))
        self._schedule_lock = asyncio.Lock()
        self._next_start_at = 0.0
        self._sleep = sleep
        self._clock = clock
        self._random_uniform = random_uniform

    async def _reserve_request_start(self) -> None:
        async with self._schedule_lock:
            wait_seconds = max(0.0, self._next_start_at - self._clock())
            if wait_seconds:
                await self._sleep(wait_seconds)
            now = self._clock()
            self._next_start_at = max(self._next_start_at, now) + self.request_interval_seconds

    async def _defer_requests(self, delay_seconds: float) -> None:
        async with self._schedule_lock:
            self._next_start_at = max(
                self._next_start_at, self._clock() + max(0.0, delay_seconds)
            )

    def _retry_delay(self, error: AIRateLimitError, retry_number: int) -> float:
        exponential = self.base_delay_seconds * (2 ** max(0, retry_number - 1))
        provider_delay = error.retry_after_seconds or 0.0
        jitter = self._random_uniform(0.0, self.jitter_seconds)
        return min(self.max_delay_seconds, max(exponential, provider_delay) + jitter)

    async def generate(self, system_prompt: str, user_prompt: str, *, caller: str) -> str:
        retries_used = 0
        while True:
            try:
                async with self._semaphore:
                    await self._reserve_request_start()
                    return await self.ai_client.generate(system_prompt, user_prompt)
            except AIRateLimitError as exc:
                if retries_used >= self.max_retries:
                    logger.warning(
                        "%s exhausted %d debate rate-limit retries (limit=%s)",
                        caller,
                        self.max_retries,
                        exc.limit_type or "unknown",
                    )
                    raise
                retries_used += 1
                delay = self._retry_delay(exc, retries_used)
                await self._defer_requests(delay)
                logger.warning(
                    "%s rate-limited; retry %d/%d in %.2fs (limit=%s)",
                    caller,
                    retries_used,
                    self.max_retries,
                    delay,
                    exc.limit_type or "unknown",
                )


def _filter_source_locations(items: list[Any], valid_locations: set[int]) -> None:
    """Cross-check `source_locations` on a list of finding-like objects
    against locations that genuinely exist in the document, dropping any
    that don't. Shared logic mirroring Phase 2's safeguard, generalized to
    any object exposing a `source_locations: list[int]` attribute."""
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
    request_control: asyncio.Semaphore | DebateRequestController,
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
        if isinstance(request_control, DebateRequestController):
            raw_response = await request_control.generate(
                system_prompt, user_prompt, caller=f"Agent '{agent.value}'"
            )
        else:
            # Retained for direct unit-level invocation of this internal helper.
            async with request_control:
                raw_response = await ai_client.generate(system_prompt, user_prompt)
    except AIClientError as exc:
        logger.warning("Agent '%s' failed (AI client error): %s", agent.value, exc.message)
        return AgentAnalysis(
            agent=agent,
            role=role_title,
            status=AgentStatus.FAILED,
            error="This agent could not complete its analysis.",
        )
    except Exception as exc:  # noqa: BLE001 - one agent must never crash the debate
        logger.exception("Agent '%s' failed unexpectedly", agent.value)
        return AgentAnalysis(
            agent=agent,
            role=role_title,
            status=AgentStatus.FAILED,
            error="This agent could not complete its analysis.",
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

    When debate RAG is enabled (independently or through global RAG), each
    specialist agent is grounded in chunks retrieved using its *own*
    perspective as the query (so, e.g., the Security agent sees chunks most
    relevant to security), and the Moderator is grounded in a broader
    retrieval. When disabled, this uses the legacy shared full-document path.
    """
    request_controller = DebateRequestController(
        ai_client,
        max_concurrency=config.DEBATE_MAX_CONCURRENT_AGENTS,
        max_retries=config.DEBATE_MAX_RATE_LIMIT_RETRIES,
        base_delay_seconds=config.DEBATE_RETRY_BASE_DELAY_SECONDS,
        max_delay_seconds=config.DEBATE_RETRY_MAX_DELAY_SECONDS,
        jitter_seconds=config.DEBATE_RETRY_JITTER_SECONDS,
        request_interval_seconds=config.DEBATE_REQUEST_INTERVAL_SECONDS,
    )

    debate_rag_enabled = config.RAG_ENABLED or config.DEBATE_RAG_ENABLED
    if debate_rag_enabled:
        document = get_document_or_raise(document_id)
        ensure_document_is_analyzable(document)
        rag_service.ensure_document_indexed(document)

        agent_rag_contexts: dict[AgentRole, rag_service.RagContext] = {
            agent: rag_service.build_context_from_query(
                document_id,
                rag_service.get_agent_retrieval_query(agent),
                config.DEBATE_RAG_TOP_K,
            )
            for agent in AGENT_ROLES
        }
        moderator_rag_context = rag_service.build_context_from_query(
            document_id,
            rag_service.MODERATOR_RETRIEVAL_QUERY,
            config.DEBATE_RAG_TOP_K,
        )

        agent_analyses = await asyncio.gather(
            *[
                _run_single_agent(
                    agent,
                    ai_client,
                    agent_rag_contexts[agent].content,
                    agent_rag_contexts[agent].item_count,
                    agent_rag_contexts[agent].valid_locations,
                    request_controller,
                )
                for agent in AGENT_ROLES
            ]
        )
        moderator_labeled_content = moderator_rag_context.content
        moderator_content_item_count = moderator_rag_context.item_count
        moderator_valid_locations = moderator_rag_context.valid_locations
    else:
        _, labeled_content, valid_locations, content_item_count = (
            prepare_document_for_analysis(document_id)
        )

        agent_analyses = await asyncio.gather(
            *[
                _run_single_agent(
                    agent,
                    ai_client,
                    labeled_content,
                    content_item_count,
                    valid_locations,
                    request_controller,
                )
                for agent in AGENT_ROLES
            ]
        )
        moderator_labeled_content = labeled_content
        moderator_content_item_count = content_item_count
        moderator_valid_locations = valid_locations

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
        moderator_labeled_content,
        moderator_content_item_count,
        successful,
        failed_agent_names,
    )

    # Let AIClientError subclasses propagate untouched -- the API layer maps
    # them to specific, user-facing HTTP errors, exactly as Phase 2 does.
    raw_moderator_response = await request_controller.generate(
        MODERATOR_SYSTEM_PROMPT, moderator_user_prompt, caller="Moderator"
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

    _filter_source_locations(moderator_output.final_risks, moderator_valid_locations)
    _filter_source_locations(
        moderator_output.final_assumptions, moderator_valid_locations
    )
    _filter_source_locations(moderator_output.final_biases, moderator_valid_locations)

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
            "analyzed_content_items": moderator_content_item_count,
            "rag_enabled": debate_rag_enabled,
        },
    )
