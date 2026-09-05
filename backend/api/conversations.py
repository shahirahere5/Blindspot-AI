"""Document-scoped APIs for persistent grounded conversation."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from ai.base import (
    AIAuthenticationError, AIClientError, AIConfigurationError,
    AIConnectionError, AIModelUnavailableError, AIRateLimitError,
    AIResponseError, AITimeoutError,
)
from ai.client import get_ai_client
from ai.safe_errors import safe_ai_error_detail
from schemas.conversation import (
    Conversation, CreateConversationRequest, SendMessageRequest, SendMessageResponse,
)
from services.conversation_service import (
    ConversationGenerationError, ConversationScopeError, clear_conversation,
    create_conversation, get_scoped_conversation, send_message,
)
from services.document_service import DocumentNotFoundError, DocumentNotReadyError
from storage.conversation_store import (
    ConversationNotFoundError, ConversationStoreError, InvalidConversationIdError,
)
from storage.path_safety import validate_document_id

logger = logging.getLogger("blindspot.conversation_api")
router = APIRouter(prefix="/api/documents", tags=["conversations"])


def _raise_ai(exc: AIClientError) -> None:
    status = 502
    if isinstance(exc, AIConfigurationError): status = 500
    elif isinstance(exc, AIRateLimitError): status = 429
    elif isinstance(exc, AITimeoutError): status = 504
    elif isinstance(exc, (AIAuthenticationError, AIConnectionError, AIModelUnavailableError, AIResponseError)): status = 502
    logger.warning("Conversational AI failure: %s", type(exc).__name__)
    raise HTTPException(status_code=status, detail=safe_ai_error_detail(exc, "conversation")) from exc


def _raise_storage(exc: Exception) -> None:
    if isinstance(exc, InvalidConversationIdError):
        raise HTTPException(status_code=400, detail=exc.message) from exc
    if isinstance(exc, (ConversationNotFoundError, ConversationScopeError)):
        raise HTTPException(status_code=404, detail=exc.message) from exc
    logger.error("Conversation storage failure: %s", type(exc).__name__)
    raise HTTPException(status_code=500, detail="Conversation history is temporarily unavailable.") from exc


@router.post("/{document_id}/conversations", response_model=Conversation, status_code=201)
async def create_document_conversation(document_id: str, request: CreateConversationRequest) -> Conversation:
    validate_document_id(document_id)
    try:
        return create_conversation(document_id, request.scope)
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc
    except DocumentNotReadyError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc
    except ConversationStoreError as exc:
        _raise_storage(exc)


@router.get("/{document_id}/conversations/{conversation_id}", response_model=Conversation)
async def get_document_conversation(document_id: str, conversation_id: str) -> Conversation:
    validate_document_id(document_id)
    try:
        return get_scoped_conversation(document_id, conversation_id)
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc
    except (ConversationStoreError, ConversationScopeError) as exc:
        _raise_storage(exc)


@router.post("/{document_id}/conversations/{conversation_id}/messages", response_model=SendMessageResponse)
async def send_conversation_message(
    document_id: str, conversation_id: str, request: SendMessageRequest,
) -> SendMessageResponse:
    validate_document_id(document_id)
    try:
        return await send_message(document_id, conversation_id, request.content, get_ai_client())
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc
    except (ConversationStoreError, ConversationScopeError) as exc:
        _raise_storage(exc)
    except AIClientError as exc:
        _raise_ai(exc)
    except ConversationGenerationError as exc:
        raise HTTPException(status_code=422, detail=exc.message) from exc


@router.delete("/{document_id}/conversations/{conversation_id}/messages", response_model=Conversation)
async def clear_document_conversation(document_id: str, conversation_id: str) -> Conversation:
    validate_document_id(document_id)
    try:
        return clear_conversation(document_id, conversation_id)
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc
    except (ConversationStoreError, ConversationScopeError) as exc:
        _raise_storage(exc)
