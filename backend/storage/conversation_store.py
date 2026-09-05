"""Atomic local persistence for bounded conversation histories."""

from __future__ import annotations

import os
import re
import threading
import uuid
from pathlib import Path

import config
from schemas.conversation import Conversation

_CONVERSATION_ID = re.compile(r"^conv_[0-9a-f]{32}$")


class ConversationStoreError(Exception):
    pass


class ConversationNotFoundError(ConversationStoreError):
    def __init__(self, message: str = "Conversation was not found.") -> None:
        self.message = message
        super().__init__(message)


class InvalidConversationIdError(ConversationStoreError):
    def __init__(self, message: str = "Invalid conversation ID.") -> None:
        self.message = message
        super().__init__(message)


class ConversationStore:
    def __init__(self, storage_dir: Path = config.CONVERSATION_STORE_DIR) -> None:
        self.storage_dir = storage_dir
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _path(self, conversation_id: str) -> Path:
        if not _CONVERSATION_ID.fullmatch(conversation_id):
            raise InvalidConversationIdError()
        return self.storage_dir / f"{conversation_id}.json"

    def save(self, conversation: Conversation) -> None:
        destination = self._path(conversation.conversation_id)
        temporary = destination.with_suffix(f".{uuid.uuid4().hex}.tmp")
        with self._lock:
            try:
                temporary.write_text(conversation.model_dump_json(indent=2), encoding="utf-8")
                os.replace(temporary, destination)
            except OSError as exc:
                temporary.unlink(missing_ok=True)
                raise ConversationStoreError("Failed to persist conversation.") from exc

    def get(self, conversation_id: str) -> Conversation:
        path = self._path(conversation_id)
        with self._lock:
            if not path.exists():
                raise ConversationNotFoundError()
            try:
                return Conversation.model_validate_json(path.read_text("utf-8"))
            except ConversationNotFoundError:
                raise
            except Exception as exc:
                raise ConversationStoreError("Stored conversation is invalid.") from exc


conversation_store = ConversationStore()
