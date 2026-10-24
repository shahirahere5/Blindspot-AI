"""
Pydantic models for the Phase 3 "multi-agent debate" output.

Reuses the Phase 2 building blocks (`Risk`, `Assumption`, `Bias`,
`MissingPerspective`, `UnansweredQuestion`, `Recommendation`, `Severity`,
`Confidence`) so the final synthesized report has exactly the same shape as
the Phase 2 `AnalysisReport` wherever possible -- this keeps things simple
for a future frontend that already knows how to render those types, and
avoids duplicating validation/normalization logic (e.g. `source_locations`
coercion) that already exists and is already tested.

Everything here is a strict contract: nothing coming back from an agent or
the moderator is trusted until it has passed through these models.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator

from schemas.analysis import (
    Assumption,
    Bias,
    Confidence,
    MissingPerspective,
    Recommendation,
    Risk,
    Severity,
    UnansweredQuestion,
    _clean_source_locations,
)


class AgentRole(str, Enum):
    """The six independent specialist perspectives run in Phase 3."""

    OPTIMIST = "optimist"
    SKEPTIC = "skeptic"
    SECURITY = "security"
    FINANCIAL = "financial"
    ETHICS = "ethics"
    LEGAL = "legal"


class AgentStatus(str, Enum):
    """Whether an individual agent's analysis succeeded or failed.

    A single agent failure must never fail the whole debate -- the debate
    service records the failure here and continues with whatever agents
    did succeed, and the Moderator is told which agents are missing.
    """

    SUCCEEDED = "succeeded"
    FAILED = "failed"


class DebateStatus(str, Enum):
    COMPLETED = "completed"
    FAILED = "failed"


class AgentFinding(BaseModel):
    """A single finding produced by one specialist agent.

    The same shape is reused across all agents regardless of perspective --
    an Optimist's "finding" is a strength/opportunity, a Skeptic's is a
    weakness, a Security agent's is a security risk, etc. `severity` is used
    generically as an importance scale in every case.
    """

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


class AgentAnalysis(BaseModel):
    """The full, validated output of a single specialist agent."""

    agent: AgentRole
    role: str = ""
    status: AgentStatus = AgentStatus.SUCCEEDED
    error: str | None = None
    summary: str = ""
    findings: list[AgentFinding] = Field(default_factory=list)
    assumptions: list[Assumption] = Field(default_factory=list)
    questions: list[UnansweredQuestion] = Field(default_factory=list)
    confidence: Confidence = Confidence.MEDIUM
    metadata: dict[str, Any] = Field(default_factory=dict)


class DebateResult(BaseModel):
    """The full, validated Blind Spot debate report for a single document."""

    document_id: str
    status: DebateStatus = DebateStatus.COMPLETED
    agent_analyses: list[AgentAnalysis] = Field(default_factory=list)
    agreements: list[str] = Field(default_factory=list)
    disagreements: list[str] = Field(default_factory=list)
    final_blind_spots: list[str] = Field(default_factory=list)
    final_risks: list[Risk] = Field(default_factory=list)
    final_assumptions: list[Assumption] = Field(default_factory=list)
    final_biases: list[Bias] = Field(default_factory=list)
    missing_perspectives: list[MissingPerspective] = Field(default_factory=list)
    unanswered_questions: list[UnansweredQuestion] = Field(default_factory=list)
    recommendations: list[Recommendation] = Field(default_factory=list)
    overall_assessment: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class ModeratorOutput(BaseModel):
    """Intermediate model used to validate the Moderator's raw JSON output
    before it is merged with the (already-validated) agent analyses into a
    final `DebateResult`. Not returned to clients directly."""

    overall_assessment: str = ""
    agreements: list[str] = Field(default_factory=list)
    disagreements: list[str] = Field(default_factory=list)
    final_blind_spots: list[str] = Field(default_factory=list)
    final_risks: list[Risk] = Field(default_factory=list)
    final_assumptions: list[Assumption] = Field(default_factory=list)
    final_biases: list[Bias] = Field(default_factory=list)
    missing_perspectives: list[MissingPerspective] = Field(default_factory=list)
    unanswered_questions: list[UnansweredQuestion] = Field(default_factory=list)
    recommendations: list[Recommendation] = Field(default_factory=list)


class DebateErrorResponse(BaseModel):
    """Uniform error payload for debate-specific failures."""

    success: bool = False
    error: str
    detail: str | None = None
