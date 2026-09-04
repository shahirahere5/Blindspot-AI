"""Grounded prompt for semantic version comparison."""

from __future__ import annotations

from schemas.comparison import StructuralDiff

SYSTEM_PROMPT = """You compare two explicitly related versions of a decision document.
Return one JSON object only. Perform a semantic assessment, not a raw textual diff.
Use only the supplied OLD VERSION and NEW VERSION evidence. Never merge their sources.
Every finding must use: title, description, old_evidence, new_evidence,
old_source_locations, new_source_locations. Cite only integer locations visible under
the matching version label. Empty evidence and source arrays are valid when one side
has no supporting content. Do not invent facts, versions, locations, or prior analyses.

Return summary, overall_change_assessment, and arrays named: new_risks,
resolved_risks, persistent_risks, new_assumptions, resolved_assumptions,
persistent_assumptions, new_biases, resolved_biases, persistent_biases,
new_missing_perspectives, resolved_missing_perspectives,
persistent_missing_perspectives, new_questions, resolved_questions,
persistent_questions, recommendation_progress, meaningful_additions,
meaningful_removals, regressions. recommendation_progress findings also require
progress_status: addressed, partially_addressed, not_addressed,
no_longer_applicable, or uncertain."""


def build_comparison_prompt(
    old_content: str,
    new_content: str,
    structural_diff: StructuralDiff,
) -> str:
    return f"""Compare these versions. The deterministic structural pass ran first:
{structural_diff.model_dump_json(indent=2)}

--- OLD VERSION ---
{old_content}

--- NEW VERSION ---
{new_content}

Explain what materially changed, what improved, and what regressed. Distinguish new,
resolved, and persistent blind spots. Treat normalized visual evidence exactly like
other labeled evidence. Return the required JSON object only."""
