"""
Pydantic models for the Phase 2 "single AI analyzer" output.

These models are the strict contract the raw AI response is validated
against before it is ever returned to a client. Nothing from the model is
trusted until it has passed through this schema.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Priority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Confidence(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class AnalysisStatus(str, Enum):
    COMPLETED = "completed"
    FAILED = "failed"


def _clean_source_locations(value: Any) -> list[int]:
    """Coerce a raw 'source_locations' value into a clean list[int].

    Local models are inconsistent about this field (missing, a single int,
    strings, floats, null entries...). Rather than fail validation outright,
    we normalize best-effort and drop anything that isn't a genuine location,
    since an empty list is an explicitly allowed "no confident source" value.
    """
    if value is None:
        return []
    if isinstance(value, (int, float, str)):
        value = [value]
    if not isinstance(value, list):
        return []

    cleaned: list[int] = []
    for item in value:
        try:
            cleaned.append(int(item))
        except (TypeError, ValueError):
            continue
    return cleaned


class Risk(BaseModel):
    title: str
    description: str
    severity: Severity = Severity.MEDIUM
    evidence: str = ""
    source_locations: list[int] = Field(default_factory=list)
    recommendation: str = ""

    @field_validator("source_locations", mode="before")
    @classmethod
    def _normalize_source_locations(cls, value: Any) -> list[int]:
        return _clean_source_locations(value)


class Assumption(BaseModel):
    title: str
    description: str
    confidence: Confidence = Confidence.MEDIUM
    evidence: str = ""
    source_locations: list[int] = Field(default_factory=list)
    why_it_matters: str = ""

    @field_validator("source_locations", mode="before")
    @classmethod
    def _normalize_source_locations(cls, value: Any) -> list[int]:
        return _clean_source_locations(value)


class Bias(BaseModel):
    title: str
    description: str
    evidence: str = ""
    source_locations: list[int] = Field(default_factory=list)
    recommendation: str = ""

    @field_validator("source_locations", mode="before")
    @classmethod
    def _normalize_source_locations(cls, value: Any) -> list[int]:
        return _clean_source_locations(value)


class MissingPerspective(BaseModel):
    perspective: str
    description: str
    why_it_matters: str = ""
    questions_to_consider: list[str] = Field(default_factory=list)


class UnansweredQuestion(BaseModel):
    question: str
    importance: Priority = Priority.MEDIUM
    reason: str = ""


class Recommendation(BaseModel):
    priority: Priority = Priority.MEDIUM
    title: str
    description: str


class AnalysisReport(BaseModel):
    """The full, validated Blind Spot analysis for a single document."""

    document_id: str
    status: AnalysisStatus = AnalysisStatus.COMPLETED
    summary: str = ""
    overall_assessment: str = ""
    risks: list[Risk] = Field(default_factory=list)
    assumptions: list[Assumption] = Field(default_factory=list)
    biases: list[Bias] = Field(default_factory=list)
    missing_perspectives: list[MissingPerspective] = Field(default_factory=list)
    unanswered_questions: list[UnansweredQuestion] = Field(default_factory=list)
    recommendations: list[Recommendation] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AnalysisErrorResponse(BaseModel):
    """Uniform error payload for analysis-specific failures."""

    success: bool = False
    error: str
    detail: str | None = None
