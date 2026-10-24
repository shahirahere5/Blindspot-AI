"""
RAG orchestration for Phase 4.

This is the one module `services/analysis_service.py` and
`services/debate_service.py` talk to when `config.RAG_ENABLED` is true --
it composes `services/retrieval_service.py` (indexing/retrieval) and
`rag/context_builder.py` (rendering) into a single ready-to-use
`RagContext`, and defines the retrieval queries used for the single
analyzer and for each of the six specialist debate agents.

Nothing here changes what happens when `RAG_ENABLED` is false -- Phase 2/3
never import this module in that case.
"""

from __future__ import annotations

from dataclasses import dataclass

import config
from rag.context_builder import build_rag_context
from schemas.debate import AgentRole
from services.document_service import DocumentTooLargeForAnalysisError
from services.retrieval_service import retrieve_relevant_chunks

# Re-exported for convenience so callers only need to import this module.
from services.retrieval_service import (  # noqa: F401
    DocumentNotIndexedError,
    ensure_document_indexed,
)


@dataclass
class RagContext:
    """Grounded, source-labeled context ready to drop into a prompt, plus
    the location-validation set it implies (see rag/context_builder.py)."""

    content: str
    valid_locations: set[int]
    item_count: int  # number of chunks actually retrieved and used


# The single Phase 2 analyzer has no specific "angle", so it retrieves
# broadly across every category it reports on.
ANALYSIS_RETRIEVAL_QUERY = (
    "risks, hidden assumptions, biases, missing perspectives, unanswered "
    "questions, and recommendations in this document"
)

# The Moderator needs a broad, whole-document view to synthesize across all
# six agents, so it also retrieves broadly rather than from one angle.
MODERATOR_RETRIEVAL_QUERY = (
    "overall risks, assumptions, blind spots, disagreements, and "
    "recommendations across the whole document"
)

# Each specialist debate agent retrieves using its own perspective as the
# query, so it's grounded in the chunks most relevant to *its* angle rather
# than the whole document -- smaller, more targeted prompts per agent
# instead of one large shared prompt.
_AGENT_RETRIEVAL_QUERIES: dict[AgentRole, str] = {
    AgentRole.OPTIMIST: (
        "strengths, opportunities, positive assumptions, advantages, and "
        "reasons this could succeed"
    ),
    AgentRole.SKEPTIC: (
        "unsupported assumptions, unsupported claims, contradictions, "
        "missing evidence, failure scenarios, feasibility concerns, "
        "overconfidence, hidden dependencies"
    ),
    AgentRole.SECURITY: (
        "data security, privacy, authentication, authorization, data "
        "leakage, prompt injection, malicious input, system abuse, "
        "infrastructure"
    ),
    AgentRole.FINANCIAL: (
        "cost assumptions, revenue model, pricing, ROI, market viability, "
        "operational costs, scalability costs, monetization"
    ),
    AgentRole.ETHICS: (
        "ethical risks, fairness, bias, discrimination, human impact, "
        "misuse, transparency, accountability, overreliance on AI"
    ),
    AgentRole.LEGAL: (
        "legal risk, regulatory considerations, privacy requirements, "
        "intellectual property, liability, compliance, consent"
    ),
}


def get_agent_retrieval_query(agent: AgentRole) -> str:
    """The retrieval query used to ground one specialist debate agent."""
    return _AGENT_RETRIEVAL_QUERIES[agent]


def build_context_from_query(
    document_id: str, query: str, top_k: int | None = None
) -> RagContext:
    """
    Retrieve the most relevant chunks for `query` and render them into a
    ready-to-use `RagContext`.

    The document must already be indexed -- call `ensure_document_indexed`
    first (re-exported from services.retrieval_service). Raises
    DocumentNotIndexedError, or an ai.embeddings.base.EmbeddingError /
    storage.vector_store.VectorStoreError subclass, untouched.
    """
    retrieved = retrieve_relevant_chunks(document_id, query, top_k)
    content, valid_locations = build_rag_context(retrieved)

    if len(content) > config.MAX_ANALYSIS_CONTENT_CHARS:
        # Extremely unlikely with a small top_k, but keep the same safety
        # net Phase 2/3 already rely on rather than ever sending an
        # unbounded prompt.
        raise DocumentTooLargeForAnalysisError(
            "The retrieved RAG context "
            f"({len(content):,} characters) exceeds the maximum supported "
            f"for a single analysis pass ({config.MAX_ANALYSIS_CONTENT_CHARS:,} "
            "characters). Try a smaller RAG_TOP_K or RAG_CHUNK_SIZE."
        )

    return RagContext(
        content=content, valid_locations=valid_locations, item_count=len(retrieved)
    )
