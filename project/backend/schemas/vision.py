"""Validated structured observations returned by a vision provider."""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints, model_validator


Observation = Annotated[str, StringConstraints(max_length=2_000)]


class VisualAnalysis(BaseModel):
    visible_text: str = Field(default="", max_length=12_000)
    summary: str = Field(default="", max_length=4_000)
    key_evidence: list[Observation] = Field(default_factory=list, max_length=30)
    relationships: list[Observation] = Field(default_factory=list, max_length=30)
    concerns: list[Observation] = Field(default_factory=list, max_length=30)

    @model_validator(mode="after")
    def require_useful_content(self) -> "VisualAnalysis":
        values = [
            self.visible_text,
            self.summary,
            *self.key_evidence,
            *self.relationships,
            *self.concerns,
        ]
        if not any(value.strip() for value in values):
            raise ValueError("Vision response contained no useful observations.")
        return self

    def as_evidence_text(self, existing_text: str = "") -> str:
        """Render observations as grounded text for existing RAG/AI pipelines."""
        sections: list[str] = []
        visible_text = self.visible_text.strip()
        if visible_text and visible_text.casefold() not in existing_text.casefold():
            sections.append(f"Visible text:\n{visible_text}")
        if self.summary.strip():
            sections.append(f"Visual summary:\n{self.summary.strip()}")
        for heading, values in (
            ("Key visual evidence", self.key_evidence),
            ("Visual relationships", self.relationships),
            ("Potential visual concerns", self.concerns),
        ):
            cleaned = [value.strip() for value in values if value.strip()]
            if cleaned:
                sections.append(f"{heading}:\n" + "\n".join(f"- {v}" for v in cleaned))
        return "\n\n".join(sections)
