"""
Utilities for safely extracting and parsing JSON out of raw LLM text output.

Local models frequently wrap JSON in markdown fences, add a sentence of
preamble/postamble, or produce minor formatting issues. This module centralizes
"best-effort but still safe" handling of that, without ever using `eval`.
"""

from __future__ import annotations

import json
import re


class JSONExtractionError(Exception):
    """Raised when no valid JSON object could be extracted from model output."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


_CODE_FENCE_PATTERN = re.compile(
    r"```(?:json)?\s*(?P<body>{.*?})\s*```", re.DOTALL | re.IGNORECASE
)


def extract_json_object(raw_text: str) -> dict:
    """
    Extract and parse a single JSON object from raw model output.

    Strategy, in order:
    1. Try to parse the entire response as JSON.
    2. Look for a ```json ... ``` or ``` ... ``` fenced code block containing
       an object, and parse that.
    3. Fall back to locating the first '{' and the matching last '}' in the
       text and parsing the substring between them.

    Raises JSONExtractionError if no valid JSON object can be parsed.
    """
    if not raw_text or not raw_text.strip():
        raise JSONExtractionError("Model returned an empty response.")

    text = raw_text.strip()

    # Strategy 1: the whole thing is JSON already.
    parsed = _try_parse(text)
    if parsed is not None:
        return parsed

    # Strategy 2: a fenced code block.
    fence_match = _CODE_FENCE_PATTERN.search(text)
    if fence_match:
        parsed = _try_parse(fence_match.group("body"))
        if parsed is not None:
            return parsed

    # Strategy 3: first '{' to last '}' in the text.
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        candidate = text[first_brace : last_brace + 1]
        parsed = _try_parse(candidate)
        if parsed is not None:
            return parsed

    raise JSONExtractionError(
        "Could not extract a valid JSON object from the model's response."
    )


def _try_parse(candidate: str) -> dict | None:
    try:
        result = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    if not isinstance(result, dict):
        return None
    return result
