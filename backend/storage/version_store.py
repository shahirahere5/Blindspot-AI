"""Concurrency-safe, local JSON persistence for explicit version groups."""

from __future__ import annotations

import os
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from config import VERSION_GROUPS_DIR
from schemas.document import NormalizedDocument
from schemas.versioning import StoredVersionGroup, VersionEntry, VersionHistory

_GROUP_ID = re.compile(r"^vg_[0-9a-f]{32}$")


class VersionStoreError(Exception):
    pass


class VersionConflictError(VersionStoreError):
    pass


class VersionRelationshipError(VersionStoreError):
    pass


class VersionStore:
    def __init__(self, groups_dir: Path = VERSION_GROUPS_DIR) -> None:
        self.groups_dir = groups_dir
        self.groups_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _path(self, group_id: str) -> Path:
        if not _GROUP_ID.fullmatch(group_id):
            raise VersionStoreError("Invalid version group ID.")
        return self.groups_dir / f"{group_id}.json"

    def _read(self, path: Path) -> StoredVersionGroup:
        try:
            return StoredVersionGroup.model_validate_json(path.read_text("utf-8"))
        except Exception as exc:
            raise VersionStoreError("Stored version history is invalid.") from exc

    def _write(self, group: StoredVersionGroup) -> None:
        destination = self._path(group.version_group_id)
        temporary = destination.with_suffix(f".{uuid.uuid4().hex}.tmp")
        try:
            temporary.write_text(group.model_dump_json(indent=2), encoding="utf-8")
            os.replace(temporary, destination)
        except OSError as exc:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            raise VersionStoreError("Failed to persist version history.") from exc

    def _all_groups(self) -> list[StoredVersionGroup]:
        groups: list[StoredVersionGroup] = []
        try:
            paths = list(self.groups_dir.glob("vg_*.json"))
        except OSError as exc:
            raise VersionStoreError("Failed to read version history.") from exc
        for path in paths:
            groups.append(self._read(path))
        return groups

    def find_group_for_document(self, document_id: str) -> StoredVersionGroup | None:
        with self._lock:
            matches = [
                group for group in self._all_groups()
                if any(item.document_id == document_id for item in group.versions)
            ]
            if len(matches) > 1:
                raise VersionStoreError("Document belongs to multiple version groups.")
            return matches[0] if matches else None

    def history_for(self, document: NormalizedDocument) -> VersionHistory:
        group = self.find_group_for_document(document.document_id)
        if group:
            return VersionHistory(
                version_group_id=group.version_group_id,
                versions=sorted(group.versions, key=lambda item: item.version_number),
            )
        created_at = _document_timestamp(document)
        return VersionHistory(
            version_group_id=None,
            versions=[_entry(document, 1, created_at)],
        )

    def assert_can_append(self, parent_document_id: str) -> None:
        group = self.find_group_for_document(parent_document_id)
        if group and group.versions[-1].document_id != parent_document_id:
            raise VersionConflictError(
                "New versions can only be uploaded from the latest version."
            )

    def append(
        self,
        parent: NormalizedDocument,
        child: NormalizedDocument,
        *,
        label: str | None,
        notes: str | None,
    ) -> tuple[StoredVersionGroup, VersionEntry]:
        with self._lock:
            group = self.find_group_for_document(parent.document_id)
            now = datetime.now(timezone.utc)
            if group is None:
                parent_entry = _entry(parent, 1, _document_timestamp(parent))
                group = StoredVersionGroup(
                    version_group_id=f"vg_{uuid.uuid4().hex}",
                    created_at=now,
                    updated_at=now,
                    versions=[parent_entry],
                )
            elif group.versions[-1].document_id != parent.document_id:
                raise VersionConflictError(
                    "A newer version was already added. Refresh the version history."
                )

            child_entry = _entry(
                child,
                len(group.versions) + 1,
                now,
                previous_document_id=parent.document_id,
                label=label,
                notes=notes,
            )
            group.versions.append(child_entry)
            group.updated_at = now
            self._write(group)
            return group, child_entry

    def require_comparable(
        self, old_document_id: str, new_document_id: str
    ) -> tuple[StoredVersionGroup, VersionEntry, VersionEntry]:
        if old_document_id == new_document_id:
            raise VersionRelationshipError("Select two different versions to compare.")
        with self._lock:
            old_group = self.find_group_for_document(old_document_id)
            new_group = self.find_group_for_document(new_document_id)
            if not old_group or not new_group or old_group.version_group_id != new_group.version_group_id:
                raise VersionRelationshipError(
                    "Documents must belong to the same explicit version group."
                )
            old = next(item for item in old_group.versions if item.document_id == old_document_id)
            new = next(item for item in old_group.versions if item.document_id == new_document_id)
            if old.version_number >= new.version_number:
                raise VersionRelationshipError(
                    "The old version must precede the new version."
                )
            return old_group, old, new


def _document_timestamp(document: NormalizedDocument) -> datetime:
    value = document.metadata.get("uploaded_at")
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def _entry(
    document: NormalizedDocument,
    version_number: int,
    created_at: datetime,
    previous_document_id: str | None = None,
    label: str | None = None,
    notes: str | None = None,
) -> VersionEntry:
    return VersionEntry(
        document_id=document.document_id,
        version_number=version_number,
        filename=document.filename,
        file_type=document.file_type,
        status=document.status,
        created_at=created_at,
        previous_document_id=previous_document_id,
        label=label,
        notes=notes,
    )


version_store = VersionStore()
