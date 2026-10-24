"""Grounded conversational orchestration over RAG, graph, and bounded memory."""

from __future__ import annotations

import hashlib
import logging
import re
import uuid
from datetime import datetime, timezone

from pydantic import ValidationError as PydanticValidationError

import config
from ai.base import AIClient
from ai.conversation_prompts import SYSTEM_PROMPT, build_conversation_prompt
from ai.json_utils import JSONExtractionError, extract_json_object
from schemas.conversation import (
    Conversation,
    ConversationMessage,
    ConversationScope,
    ConversationSource,
    GeneratedConversationAnswer,
    MessageRole,
    RelatedFinding,
    SendMessageResponse,
)
from schemas.graph import GraphNode, GraphNodeType
from services.document_service import get_document_or_raise
from services.graph_service import get_graph
from services.retrieval_service import ensure_document_indexed, retrieve_relevant_chunks
from storage.conversation_store import ConversationStore, conversation_store
from storage.version_store import VersionStore, version_store

logger = logging.getLogger("blindspot.conversation")
_VERSION = re.compile(r"\bv\s*(\d+)\b", re.IGNORECASE)
_INSUFFICIENT = "I couldn't find enough evidence in this document to answer confidently."
_GRAPH_QUERY_TERMS = (
    "risk", "assumption", "recommend", "evidence", "source", "missing",
    "blind spot", "agent", "security", "financial", "optimist", "skeptic",
    "ethics", "legal", "version", "changed", "resolved", "persistent",
    "addressed", "bias", "perspective", "question",
)


class ConversationGenerationError(Exception):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class ConversationScopeError(Exception):
    def __init__(self, message: str = "Conversation does not belong to this document.") -> None:
        self.message = message
        super().__init__(message)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _source_id(document_id: str, source_type: str, location: int, version: int | None) -> str:
    raw = f"{document_id}\0{source_type}\0{location}\0{version or ''}"
    return f"src_{hashlib.sha256(raw.encode()).hexdigest()[:24]}"


def create_conversation(
    document_id: str,
    scope: ConversationScope,
    *,
    store: ConversationStore | None = None,
    versions: VersionStore | None = None,
) -> Conversation:
    get_document_or_raise(document_id)
    versions = versions or version_store
    group = versions.find_group_for_document(document_id)
    now = _now()
    conversation = Conversation(
        conversation_id=f"conv_{uuid.uuid4().hex}",
        document_id=document_id,
        scope=scope,
        version_group_id=group.version_group_id if scope == ConversationScope.SERIES and group else None,
        created_at=now,
        updated_at=now,
    )
    (store or conversation_store).save(conversation)
    logger.info("Created %s-scoped conversation %s", scope.value, conversation.conversation_id)
    return conversation


def get_scoped_conversation(
    document_id: str, conversation_id: str, *, store: ConversationStore | None = None
) -> Conversation:
    get_document_or_raise(document_id)
    conversation = (store or conversation_store).get(conversation_id)
    if conversation.document_id != document_id:
        raise ConversationScopeError()
    return conversation


def clear_conversation(
    document_id: str, conversation_id: str, *, store: ConversationStore | None = None
) -> Conversation:
    resolved_store = store or conversation_store
    conversation = get_scoped_conversation(document_id, conversation_id, store=resolved_store)
    conversation.messages = []
    conversation.updated_at = _now()
    resolved_store.save(conversation)
    return conversation


def _scoped_documents(conversation: Conversation, question: str, versions: VersionStore) -> list[tuple[str, int | None]]:
    if conversation.scope == ConversationScope.DOCUMENT:
        return [(conversation.document_id, None)]
    group = versions.find_group_for_document(conversation.document_id)
    if not group:
        return [(conversation.document_id, 1)]
    requested = {int(value) for value in _VERSION.findall(question)}
    entries = [item for item in group.versions if not requested or item.version_number in requested]
    if not requested:
        entries = entries[-config.CONVERSATION_SERIES_DOCUMENT_LIMIT:]
    return [(item.document_id, item.version_number) for item in entries]


def _history_text(conversation: Conversation) -> str:
    messages = conversation.messages[-config.CONVERSATION_HISTORY_MESSAGES:]
    rendered: list[str] = []
    used = 0
    for message in reversed(messages):
        line = f"{message.role.value.upper()}: {message.content.strip()}"
        remaining = config.CONVERSATION_HISTORY_CHARS - used
        if remaining <= 0:
            break
        rendered.append(line[:remaining])
        used += min(len(line), remaining)
    return "\n".join(reversed(rendered))


def _rag_context(
    scoped_documents: list[tuple[str, int | None]], question: str
) -> tuple[list[str], dict[str, ConversationSource]]:
    sections: list[str] = []
    sources: dict[str, ConversationSource] = {}
    for document_id, version in scoped_documents:
        try:
            document = get_document_or_raise(document_id)
            ensure_document_indexed(document)
            retrieved = retrieve_relevant_chunks(
                document_id, question, config.CONVERSATION_RAG_TOP_K
            )
        except Exception as exc:  # one context source must not break conversation
            logger.warning("Conversation RAG unavailable for %s: %s", document_id, type(exc).__name__)
            continue
        for item in retrieved:
            chunk = item.chunk
            source_id = _source_id(document_id, chunk.source_type, chunk.source_location, version)
            source = ConversationSource(
                source_id=source_id,
                document_id=document_id,
                source_type=chunk.source_type,
                source_location=chunk.source_location,
                version_number=version,
                visual_derived=chunk.source_type == "image",
                excerpt=chunk.text[:800],
            )
            sources[source_id] = source
            version_label = f"V{version} · " if version else ""
            sections.append(
                f"[SOURCE {source_id} | {version_label}{chunk.source_type.title()} {chunk.source_location}]\n{chunk.text}"
            )
    return sections, sources


def _graph_context(
    conversation: Conversation,
) -> tuple[list[str], dict[str, ConversationSource], dict[str, GraphNode], bool]:
    try:
        graph = get_graph(
            conversation.document_id,
            scope=conversation.scope.value,
            node_limit=config.CONVERSATION_GRAPH_NODE_LIMIT,
            edge_limit=min(config.GRAPH_MAX_EDGES, config.CONVERSATION_GRAPH_NODE_LIMIT * 3),
        )
    except Exception as exc:
        logger.warning("Conversation graph unavailable for %s: %s", conversation.document_id, type(exc).__name__)
        return [], {}, {}, False
    nodes = {node.id: node for node in graph.nodes}
    sections: list[str] = []
    artifacts = graph.metadata.get("artifacts")
    if isinstance(artifacts, list) and artifacts:
        sections.append("[STRUCTURED ANALYSIS / DEBATE / VERSION CONTEXT]\n" + "\n".join(str(item) for item in artifacts))
    if graph.diagnostics:
        sections.append(
            "[GRAPH DIAGNOSTICS]\n" + "\n".join(
                f"{item.type.value} | {item.title} | {item.description}" for item in graph.diagnostics
            )
        )
    if graph.edges:
        sections.append(
            "[GRAPH RELATIONSHIPS]\n" + "\n".join(
                f"{edge.source} --{edge.type.value}--> {edge.target}" for edge in graph.edges
            )
        )
    if graph.nodes:
        sections.append(
            "[GRAPH NODES]\n" + "\n".join(
                f"{node.id} | {node.type.value} | {node.label} | {node.description[:300]} | origin={','.join(value.value for value in node.origins)}"
                for node in graph.nodes
            )
        )
    sources: dict[str, ConversationSource] = {}
    for node in graph.nodes:
        if node.type != GraphNodeType.SOURCE:
            continue
        metadata = node.metadata
        location = metadata.get("source_location")
        document_id = metadata.get("document_id")
        if not isinstance(location, int) or location < 1 or not isinstance(document_id, str):
            continue
        source_type = str(metadata.get("source_type") or "source")
        version = metadata.get("version_number")
        version = version if isinstance(version, int) and version > 0 else None
        source_id = _source_id(document_id, source_type, location, version)
        sources[source_id] = ConversationSource(
            source_id=source_id, document_id=document_id, source_type=source_type,
            source_location=location, version_number=version,
            visual_derived=bool(metadata.get("visual_derived")), excerpt=node.description[:800],
        )
        sections.append(f"[GRAPH SOURCE {source_id}] {node.label}: {node.description}")
    return sections, sources, nodes, graph.truncated


def _bounded_context(sections: list[str]) -> str:
    output: list[str] = []
    remaining = config.CONVERSATION_CONTEXT_CHARS
    for section in sections:
        if remaining <= 0:
            break
        output.append(section[:remaining])
        remaining -= min(len(section), remaining)
    return "\n\n".join(output)


async def send_message(
    document_id: str,
    conversation_id: str,
    content: str,
    ai_client: AIClient,
    *,
    store: ConversationStore | None = None,
    versions: VersionStore | None = None,
) -> SendMessageResponse:
    resolved_store = store or conversation_store
    versions = versions or version_store
    conversation = get_scoped_conversation(document_id, conversation_id, store=resolved_store)
    scoped_documents = _scoped_documents(conversation, content, versions)
    rag_sections, rag_sources = _rag_context(scoped_documents, content)
    needs_graph = any(term in content.casefold() for term in _GRAPH_QUERY_TERMS)
    graph_sections, graph_sources, graph_nodes, graph_truncated = (
        _graph_context(conversation) if needs_graph else ([], {}, {}, False)
    )
    source_map = {**rag_sources, **graph_sources}
    context = _bounded_context([*rag_sections, *graph_sections])
    model_used: str | None = None
    if context.strip():
        raw = await ai_client.generate(
            SYSTEM_PROMPT,
            build_conversation_prompt(content, _history_text(conversation), context),
        )
        model_used = ai_client.model_name
        try:
            generated = GeneratedConversationAnswer.model_validate(extract_json_object(raw))
        except (JSONExtractionError, PydanticValidationError) as exc:
            raise ConversationGenerationError(
                "The AI service returned an invalid conversational response. Please try again."
            ) from exc
    else:
        generated = GeneratedConversationAnswer(answer=_INSUFFICIENT)

    sources = [source_map[value] for value in dict.fromkeys(generated.cited_source_ids) if value in source_map]
    related = [
        RelatedFinding(node_id=value, type=graph_nodes[value].type.value, label=graph_nodes[value].label)
        for value in dict.fromkeys(generated.related_node_ids)
        if value in graph_nodes
    ]
    answer = generated.answer.strip()
    if (source_map or graph_nodes) and not sources and not related and _INSUFFICIENT.casefold() not in answer.casefold():
        answer = _INSUFFICIENT
    now = _now()
    user_message = ConversationMessage(
        message_id=f"msg_{uuid.uuid4().hex}", role=MessageRole.USER,
        content=content, created_at=now,
    )
    assistant_message = ConversationMessage(
        message_id=f"msg_{uuid.uuid4().hex}", role=MessageRole.ASSISTANT,
        content=answer, created_at=_now(), sources=sources, related_findings=related,
        metadata={
            "model": model_used,
            "rag_available": bool(rag_sections),
            "graph_available": bool(graph_sections),
            "graph_truncated": graph_truncated,
            "scoped_document_count": len(scoped_documents),
        },
    )
    conversation.messages.extend([user_message, assistant_message])
    conversation.messages = conversation.messages[-config.CONVERSATION_MAX_STORED_MESSAGES:]
    conversation.updated_at = assistant_message.created_at
    resolved_store.save(conversation)
    return SendMessageResponse(
        conversation_id=conversation.conversation_id,
        message=assistant_message,
        conversation=conversation,
    )
