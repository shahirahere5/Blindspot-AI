"""End-to-end service integration of visual evidence with existing pipelines."""

from __future__ import annotations

import config
import api.analysis as analysis_api
import api.debate as debate_api
import services.multimodal_service as multimodal_service
from schemas.vision import VisualAnalysis
from tests.fakes import (
    ALL_VALID_AGENT_RESPONSES,
    VALID_MODERATOR_JSON,
    DebateFakeAIClient,
    FakeAIClient,
)

from tests.test_multimodal_service import FakeVisionClient


def _upload_visual_image(client, monkeypatch, sample_png_bytes, fake=None) -> str:
    monkeypatch.setattr(config, "MULTIMODAL_ENABLED", True)
    fake = fake or FakeVisionClient()
    monkeypatch.setattr(multimodal_service, "get_vision_client", lambda: fake)
    response = client.post(
        "/api/documents/upload",
        files={"file": ("chart.png", sample_png_bytes, "image/png")},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "processed"
    return response.json()["document_id"]


def test_visual_image_indexes_retrieves_and_grounded_analysis_filters_sources(
    client, monkeypatch, sample_png_bytes
):
    document_id = _upload_visual_image(client, monkeypatch, sample_png_bytes)

    index_response = client.post(f"/api/documents/{document_id}/index")
    retrieve_response = client.post(
        f"/api/documents/{document_id}/retrieve",
        json={"query": "decision relevant chart trend", "top_k": 3},
    )
    assert index_response.status_code == 200
    assert retrieve_response.status_code == 200
    assert retrieve_response.json()["results"][0]["metadata"] == {
        "chunk_index": 0,
        "source_type": "image",
        "source_location": 1,
    }

    analysis_json = """{
      "summary":"Visual evidence analyzed.",
      "overall_assessment":"Review the chart.",
      "risks":[{"title":"Trend risk","description":"A chart risk.","severity":"high","evidence":"A decision-relevant chart trend","source_locations":[1,99],"recommendation":"Validate it."}],
      "assumptions":[],"biases":[],"missing_perspectives":[],
      "unanswered_questions":[],"recommendations":[]
    }"""
    text_client = FakeAIClient(response_text=analysis_json)
    monkeypatch.setattr(analysis_api, "get_ai_client", lambda: text_client)
    response = client.post(f"/api/documents/{document_id}/analyze")

    assert response.status_code == 200
    assert response.json()["risks"][0]["source_locations"] == [1]
    assert "Visual summary for the supplied evidence" in text_client.calls[0][1]


def test_debate_agents_and_moderator_receive_persisted_visual_evidence(
    client, monkeypatch, sample_png_bytes
):
    document_id = _upload_visual_image(client, monkeypatch, sample_png_bytes)
    debate_client = DebateFakeAIClient(
        responses={**ALL_VALID_AGENT_RESPONSES, "moderator": VALID_MODERATOR_JSON}
    )
    monkeypatch.setattr(debate_api, "get_ai_client", lambda: debate_client)

    response = client.post(f"/api/documents/{document_id}/debate")

    assert response.status_code == 200
    assert len(debate_client.calls) == 7
    assert all("Visual summary for the supplied evidence" in user for _, user in debate_client.calls)
    assert len(response.json()["agent_analyses"]) == 6


def test_visual_retrieval_remains_document_scoped(
    client, monkeypatch, sample_png_bytes
):
    class SequencedVision(FakeVisionClient):
        def __init__(self):
            super().__init__()
            self.upload_number = 0

        async def analyze_image(self, *args):
            self.upload_number += 1
            topic = "cybersecurity controls" if self.upload_number == 1 else "financial forecast"
            return VisualAnalysis(summary=topic)

    fake = SequencedVision()
    first = _upload_visual_image(client, monkeypatch, sample_png_bytes, fake)
    second = _upload_visual_image(client, monkeypatch, sample_png_bytes, fake)

    first_response = client.post(
        f"/api/documents/{first}/retrieve",
        json={"query": "cybersecurity", "top_k": 3},
    )
    second_response = client.post(
        f"/api/documents/{second}/retrieve",
        json={"query": "cybersecurity", "top_k": 3},
    )

    first_text = " ".join(item["text"] for item in first_response.json()["results"])
    second_text = " ".join(item["text"] for item in second_response.json()["results"])
    assert "cybersecurity controls" in first_text
    assert "cybersecurity controls" not in second_text
    assert "financial forecast" in second_text
