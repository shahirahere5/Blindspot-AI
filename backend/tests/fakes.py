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


# ---------------------------------------------------------------------------
# Phase 3: multi-agent debate fakes
# ---------------------------------------------------------------------------

# Maps a distinctive substring of each role's system prompt (see
# ai/debate_prompts.py) to a short role key, so a single fake client can
# route responses/errors per-role even though the six agents run
# concurrently and call order is not guaranteed.
_DEBATE_ROLE_MARKERS: dict[str, str] = {
    "Optimist Agent": "optimist",
    "Skeptic Agent": "skeptic",
    "Security Agent": "security",
    "Financial Agent": "financial",
    "Ethics Agent": "ethics",
    "Legal Agent": "legal",
    "Moderator Agent": "moderator",
}


def _debate_role_key(system_prompt: str) -> str:
    for marker, key in _DEBATE_ROLE_MARKERS.items():
        if marker in system_prompt:
            return key
    return "unknown"


class DebateFakeAIClient(AIClient):
    """Fake AI client for Phase 3 tests.

    Routes each `generate()` call to a per-role canned response or error,
    identified by inspecting the system prompt (since the six specialist
    agents are invoked concurrently, call *order* cannot be relied on).
    Any role not present in either mapping raises AssertionError so a test
    is never silently missing a fixture it thinks it configured.
    """

    def __init__(
        self,
        responses: dict[str, str] | None = None,
        errors: dict[str, AIClientError] | None = None,
        model_name: str = "fake-model",
    ) -> None:
        self.responses = responses or {}
        self.errors = errors or {}
        self._model_name = model_name
        self.calls: list[tuple[str, str]] = []

    @property
    def model_name(self) -> str:
        return self._model_name

    async def generate(self, system_prompt: str, user_prompt: str) -> str:
        self.calls.append((system_prompt, user_prompt))
        role = _debate_role_key(system_prompt)

        if role in self.errors:
            raise self.errors[role]
        if role in self.responses:
            return self.responses[role]

        raise AssertionError(
            f"DebateFakeAIClient has no response or error configured for role '{role}'."
        )


def valid_agent_json(summary: str = "A perspective-specific summary.") -> str:
    """A minimal, schema-valid response for a single specialist agent."""
    return f"""{{
  "summary": "{summary}",
  "findings": [
    {{
      "title": "Example finding",
      "description": "An example finding from this agent's perspective.",
      "severity": "medium",
      "evidence": "Hello Blind Spot AI.",
      "source_locations": [1],
      "recommendation": "Consider addressing this before proceeding."
    }}
  ],
  "assumptions": [
    {{
      "title": "Example assumption",
      "description": "An assumption this agent noticed.",
      "confidence": "medium",
      "evidence": "This is a plain text test file.",
      "source_locations": [1],
      "why_it_matters": "It affects the proposal's viability."
    }}
  ],
  "questions": [
    {{
      "question": "An open question from this agent's perspective?",
      "importance": "medium",
      "reason": "It is not addressed in the document."
    }}
  ],
  "confidence": "medium"
}}"""


VALID_OPTIMIST_JSON = valid_agent_json("The proposal has real strengths.")
VALID_SKEPTIC_JSON = valid_agent_json("Several claims are unsupported.")
VALID_SECURITY_JSON = valid_agent_json("No significant security concerns found.")
VALID_FINANCIAL_JSON = valid_agent_json("Financial details are largely missing.")
VALID_ETHICS_JSON = valid_agent_json("No significant ethical concerns found.")
VALID_LEGAL_JSON = valid_agent_json("A qualified professional should review compliance.")

ALL_VALID_AGENT_RESPONSES: dict[str, str] = {
    "optimist": VALID_OPTIMIST_JSON,
    "skeptic": VALID_SKEPTIC_JSON,
    "security": VALID_SECURITY_JSON,
    "financial": VALID_FINANCIAL_JSON,
    "ethics": VALID_ETHICS_JSON,
    "legal": VALID_LEGAL_JSON,
}

VALID_MODERATOR_JSON = """{
  "overall_assessment": "The proposal is promising but leaves several important questions unanswered.",
  "agreements": ["Multiple agents noted the proposal lacks supporting detail."],
  "disagreements": ["The Optimist sees the growth plan as a strength while the Skeptic sees it as unsupported."],
  "final_blind_spots": ["No agent found evidence of a validated customer base."],
  "final_risks": [
    {
      "title": "Unvalidated demand",
      "description": "The proposal assumes demand without evidence of validation.",
      "severity": "high",
      "evidence": "Hello Blind Spot AI.",
      "source_locations": [1],
      "recommendation": "Validate demand with real customers before scaling."
    }
  ],
  "final_assumptions": [
    {
      "title": "Customer demand assumption",
      "description": "The proposal assumes sufficient demand without validating it.",
      "confidence": "medium",
      "evidence": "This is a plain text test file.",
      "source_locations": [1],
      "why_it_matters": "Demand assumptions affect the viability of the proposal."
    }
  ],
  "final_biases": [
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
      "perspective": "End User",
      "description": "The document does not describe the end user's experience.",
      "why_it_matters": "User experience gaps could undermine adoption.",
      "questions_to_consider": ["How will users actually interact with this?"]
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

VALID_MODERATOR_JSON_WITH_FAKE_LOCATION = VALID_MODERATOR_JSON.replace(
    '"source_locations": [1]', '"source_locations": [1, 999]', 1
)

INVALID_AGENT_JSON_RESPONSE = "Sure! Here's my take: looks fine, no JSON here."

MALFORMED_AGENT_SCHEMA_JSON = """{
  "summary": "ok",
  "findings": "this should be a list, not a string"
}"""


# ---------------------------------------------------------------------------
# Phase 4: RAG embedding fakes
# ---------------------------------------------------------------------------
from ai.embeddings.base import EmbeddingGenerationError, EmbeddingProvider


class FakeEmbeddingProvider(EmbeddingProvider):
    """A controllable embedding provider for unit tests: returns exact,
    pre-assigned vectors for known texts (so similarity ranking in a test
    is fully predictable), or raises EmbeddingGenerationError on demand."""

    def __init__(
        self,
        dimension: int = 4,
        vectors: dict[str, list[float]] | None = None,
        default_vector: list[float] | None = None,
        fail: bool = False,
    ) -> None:
        self._dimension = dimension
        self._vectors = vectors or {}
        self._default_vector = default_vector or [0.0] * dimension
        self._fail = fail
        self.calls: list[list[str]] = []

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def provider_name(self) -> str:
        return "fake"

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        if self._fail:
            raise EmbeddingGenerationError("Simulated embedding failure.")
        if not texts:
            return []
        return [self._vectors.get(text, self._default_vector) for text in texts]