"""Atomic local persistence for deterministic graph contributions."""

from __future__ import annotations

import os
import threading
import uuid
from pathlib import Path

from config import GRAPH_STORE_DIR
from schemas.graph import GraphContribution, StoredGraphState


class GraphStoreError(Exception):
    pass


class GraphStore:
    def __init__(self, storage_dir: Path = GRAPH_STORE_DIR) -> None:
        self.storage_dir = storage_dir
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.storage_dir / "graph.json"
        self._lock = threading.RLock()

    def _load(self) -> StoredGraphState:
        if not self.path.exists():
            return StoredGraphState()
        try:
            return StoredGraphState.model_validate_json(self.path.read_text("utf-8"))
        except Exception as exc:
            raise GraphStoreError("Stored knowledge graph is invalid.") from exc

    def _save(self, state: StoredGraphState) -> None:
        temporary = self.path.with_suffix(f".{uuid.uuid4().hex}.tmp")
        try:
            temporary.write_text(state.model_dump_json(indent=2), encoding="utf-8")
            os.replace(temporary, self.path)
        except OSError as exc:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            raise GraphStoreError("Failed to persist knowledge graph.") from exc

    @staticmethod
    def _remove_index(index: dict[str, list[str]], key: str, artifact_id: str) -> None:
        values = [value for value in index.get(key, []) if value != artifact_id]
        if values:
            index[key] = values
        else:
            index.pop(key, None)

    def upsert(self, contribution: GraphContribution) -> None:
        """Replace one source artifact atomically, making ingestion idempotent."""
        with self._lock:
            state = self._load()
            previous = state.contributions.get(contribution.artifact_id)
            if previous:
                for document_id in previous.document_ids:
                    self._remove_index(state.document_index, document_id, previous.artifact_id)
                if previous.version_group_id:
                    self._remove_index(
                        state.version_group_index,
                        previous.version_group_id,
                        previous.artifact_id,
                    )
            state.contributions[contribution.artifact_id] = contribution
            for document_id in contribution.document_ids:
                artifacts = state.document_index.setdefault(document_id, [])
                if contribution.artifact_id not in artifacts:
                    artifacts.append(contribution.artifact_id)
                    artifacts.sort()
            if contribution.version_group_id:
                artifacts = state.version_group_index.setdefault(
                    contribution.version_group_id, []
                )
                if contribution.artifact_id not in artifacts:
                    artifacts.append(contribution.artifact_id)
                    artifacts.sort()
            self._save(state)

    def for_document(self, document_id: str) -> list[GraphContribution]:
        with self._lock:
            state = self._load()
            return [
                state.contributions[artifact_id]
                for artifact_id in state.document_index.get(document_id, [])
                if artifact_id in state.contributions
            ]

    def for_version_group(self, version_group_id: str) -> list[GraphContribution]:
        with self._lock:
            state = self._load()
            return [
                state.contributions[artifact_id]
                for artifact_id in state.version_group_index.get(version_group_id, [])
                if artifact_id in state.contributions
            ]


graph_store = GraphStore()
