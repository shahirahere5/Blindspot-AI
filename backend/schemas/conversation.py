"""Strongly typed contracts for grounded, document-scoped conversation."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator

import config


class ConversationScope(str, Enum):
    DOCUMENT = "document"
    SERIES = "series"


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"


class ConversationSource(BaseModel):
    source_id: str
    document_id: str
    source_type: str
    source_location: int = Field(ge=1)
    version_number: int | None = Field(default=None, ge=1)
    visual_derived: bool = False
    excerpt: str = Field(default="", max_length=800)


class RelatedFinding(BaseModel):
    node_id: str
    type: str
    label: str


class ConversationMessage(BaseModel):
    message_id: str
    role: MessageRole
    content: str
    created_at: datetime
    sources: list[ConversationSource] = Field(default_factory=list)
    related_findings: list[RelatedFinding] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Conversation(BaseModel):
    conversation_id: str
    document_id: str
    scope: ConversationScope
    version_group_id: str | None = None
    created_at: datetime
    updated_at: datetime
    messages: list[ConversationMessage] = Field(default_factory=list)


class CreateConversationRequest(BaseModel):
    scope: ConversationScope = ConversationScope.DOCUMENT


class SendMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=config.CONVERSATION_MAX_MESSAGE_CHARS)

    @field_validator("content")
    @classmethod
    def content_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Message cannot be empty.")
        return value


class SendMessageResponse(BaseModel):
    conversation_id: str
    message: ConversationMessage
    conversation: Conversation


class GeneratedConversationAnswer(BaseModel):
    answer: str = Field(min_length=1, max_length=12_000)
    cited_source_ids: list[str] = Field(default_factory=list)
    related_node_ids: list[str] = Field(default_factory=list)
