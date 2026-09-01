"""Unit tests for schemas.analysis models: validation and normalization."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from schemas.analysis import AnalysisReport, Risk, Severity


def test_risk_defaults_and_enum_validation():
    risk = Risk(title="X", description="Y")
    assert risk.severity == Severity.MEDIUM
    assert risk.source_locations == []


def test_risk_rejects_invalid_severity():
    with pytest.raises(ValidationError):
        Risk(title="X", description="Y", severity="catastrophic")


def test_source_locations_normalizes_mixed_types():
    risk = Risk(
        title="X",
        description="Y",
        source_locations=["1", 2, 3.0, None, "not-a-number"],
    )
    assert risk.source_locations == [1, 2, 3]


def test_source_locations_accepts_single_int():
    risk = Risk(title="X", description="Y", source_locations=2)
    assert risk.source_locations == [2]


def test_analysis_report_minimal_valid():
    report = AnalysisReport(document_id="doc_1")
    assert report.status.value == "completed"
    assert report.risks == []
    assert report.metadata == {}


def test_analysis_report_requires_document_id():
    with pytest.raises(ValidationError):
        AnalysisReport()
