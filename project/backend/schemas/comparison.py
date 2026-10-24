"""Structured contracts for semantic comparison between two versions."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ComparisonStatus(str, Enum):
    COMPLETED = "completed"


class ProgressStatus(str, Enum):
    ADDRESSED = "addressed"
    PARTIALLY_ADDRESSED = "partially_addressed"
    NOT_ADDRESSED = "not_addressed"
    NO_LONGER_APPLICABLE = "no_longer_applicable"
    UNCERTAIN = "uncertain"


class ComparisonFinding(BaseModel):
    title: str
    description: str
    old_evidence: str = ""
    new_evidence: str = ""
    old_source_locations: list[int] = Field(default_factory=list)
    new_source_locations: list[int] = Field(default_factory=list)


class RecommendationProgress(ComparisonFinding):
    progress_status: ProgressStatus


class StructuralDiff(BaseModel):
    old_content_blocks: int
    new_content_blocks: int
    unchanged_blocks: int
    added_blocks: int
    removed_blocks: int
    added_snippets: list[str] = Field(default_factory=list)
    removed_snippets: list[str] = Field(default_factory=list)


class ComparisonRequest(BaseModel):
    old_document_id: str
    new_document_id: str


class ComparisonReport(BaseModel):
    old_document_id: str
    new_document_id: str
    version_group_id: str
    old_version_number: int
    new_version_number: int
    status: ComparisonStatus = ComparisonStatus.COMPLETED
    summary: str
    overall_change_assessment: str
    new_risks: list[ComparisonFinding] = Field(default_factory=list)
    resolved_risks: list[ComparisonFinding] = Field(default_factory=list)
    persistent_risks: list[ComparisonFinding] = Field(default_factory=list)
    new_assumptions: list[ComparisonFinding] = Field(default_factory=list)
    resolved_assumptions: list[ComparisonFinding] = Field(default_factory=list)
    persistent_assumptions: list[ComparisonFinding] = Field(default_factory=list)
    new_biases: list[ComparisonFinding] = Field(default_factory=list)
    resolved_biases: list[ComparisonFinding] = Field(default_factory=list)
    persistent_biases: list[ComparisonFinding] = Field(default_factory=list)
    new_missing_perspectives: list[ComparisonFinding] = Field(default_factory=list)
    resolved_missing_perspectives: list[ComparisonFinding] = Field(default_factory=list)
    persistent_missing_perspectives: list[ComparisonFinding] = Field(default_factory=list)
    new_questions: list[ComparisonFinding] = Field(default_factory=list)
    resolved_questions: list[ComparisonFinding] = Field(default_factory=list)
    persistent_questions: list[ComparisonFinding] = Field(default_factory=list)
    recommendation_progress: list[RecommendationProgress] = Field(default_factory=list)
    meaningful_additions: list[ComparisonFinding] = Field(default_factory=list)
    meaningful_removals: list[ComparisonFinding] = Field(default_factory=list)
    regressions: list[ComparisonFinding] = Field(default_factory=list)
    structural_diff: StructuralDiff
    metadata: dict[str, Any] = Field(default_factory=dict)
