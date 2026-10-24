"""Contracts for explicit document version groups."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from schemas.document import DocumentStatus, FileType, UploadResponse


class VersionEntry(BaseModel):
    document_id: str
    version_number: int = Field(ge=1)
    filename: str
    file_type: FileType
    status: DocumentStatus
    created_at: datetime
    previous_document_id: str | None = None
    label: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=2000)


class VersionHistory(BaseModel):
    version_group_id: str | None
    versions: list[VersionEntry]


class VersionedUploadResponse(UploadResponse):
    version_group_id: str
    version_number: int
    previous_document_id: str
    label: str | None = None
    notes: str | None = None
    created_at: datetime


class StoredVersionGroup(BaseModel):
    version_group_id: str
    created_at: datetime
    updated_at: datetime
    versions: list[VersionEntry]
