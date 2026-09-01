"""Fake AIClient implementations used to test Phase 2 without a real Groq API call."""

from __future__ import annotations

from ai.base import AIClient, AIClientError


class FakeAIClient(AIClient):
    """Returns a fixed canned response, or raises a fixed canned error."""

    def __init__(
        self,
        response_text: str | None = None,
        error: AIClientError | None = None,
        model_name: str = "fake-model",
    ):
        self.response_text = response_text
        self.error = error
        self._model_name = model_name
        self.calls: list[tuple[str, str]] = []

    @property
    def model_name(self) -> str:
        return self._model_name

    async def generate(self, system_prompt: str, user_prompt: str) -> str:
        self.calls.append((system_prompt, user_prompt))
        if self.error is not None:
            raise self.error
        assert self.response_text is not None
        return self.response_text


VALID_ANALYSIS_JSON = """{
  "summary": "The pitch proposes a subscription-based scheduling tool for small clinics.",
  "overall_assessment": "The idea is plausible but several important questions remain unanswered.",
  "risks": [
    {
      "title": "Scalability risk",
      "description": "The document does not explain how the system will handle rapid growth.",
      "severity": "high",
      "evidence": "The startup expects to acquire one million users within six months.",
      "source_locations": [1],
      "recommendation": "Add a scaling strategy and capacity assumptions."
    }
  ],
  "assumptions": [
    {
      "title": "Customer demand assumption",
      "description": "The proposal assumes sufficient demand without validating it.",
      "confidence": "medium",
      "evidence": "Hello Blind Spot AI.",
      "source_locations": [1],
      "why_it_matters": "Demand assumptions affect the viability of the proposal."
    }
  ],
  "biases": [
    {
      "title": "Confirmation bias",
      "description": "The document emphasizes positive evidence while overlooking contrary evidence.",
      "evidence": "This is a plain text test file.",
      "source_locations": [1],
      "recommendation": "Include contrary evidence and alternative explanations."
    }
  ],
  "missing_perspectives": [
    {
      "perspective": "Security",
      "description": "The document does not address security implications.",
      "why_it_matters": "Security weaknesses could create significant risks.",
      "questions_to_consider": ["What are the main attack vectors?"]
    }
  ],
  "unanswered_questions": [
    {
      "question": "What is the long-term revenue model?",
      "importance": "high",
      "reason": "The proposal discusses growth but does not explain sustainable revenue."
    }
  ],
  "recommendations": [
    {
      "priority": "high",
      "title": "Validate market demand",
      "description": "Conduct customer interviews or market research before committing resources."
    }
  ]
}"""


VALID_ANALYSIS_JSON_WITH_FAKE_LOCATION = VALID_ANALYSIS_JSON.replace(
    '"source_locations": [1]', '"source_locations": [1, 999]'
)

INVALID_JSON_RESPONSE = "Sure! Here's my analysis: it looks fine, no JSON for you."

MALFORMED_SCHEMA_JSON = """{
  "summary": "ok",
  "risks": "this should be a list, not a string"
}"""
