"""Unit tests for ai.json_utils.extract_json_object."""

from __future__ import annotations

import pytest

from ai.json_utils import JSONExtractionError, extract_json_object


def test_extract_plain_json():
    result = extract_json_object('{"a": 1, "b": "two"}')
    assert result == {"a": 1, "b": "two"}


def test_extract_json_from_fenced_code_block():
    text = 'Here is the analysis:\n```json\n{"a": 1}\n```\nHope this helps!'
    result = extract_json_object(text)
    assert result == {"a": 1}


def test_extract_json_from_unlabeled_fence():
    text = '```\n{"a": 1}\n```'
    result = extract_json_object(text)
    assert result == {"a": 1}


def test_extract_json_with_surrounding_prose():
    text = 'Sure, here is my analysis: {"a": 1, "nested": {"b": 2}} Let me know if you need more.'
    result = extract_json_object(text)
    assert result == {"a": 1, "nested": {"b": 2}}


def test_extract_json_raises_on_no_json():
    with pytest.raises(JSONExtractionError):
        extract_json_object("There is no JSON here at all.")


def test_extract_json_raises_on_empty_string():
    with pytest.raises(JSONExtractionError):
        extract_json_object("")


def test_extract_json_raises_on_non_object_json():
    with pytest.raises(JSONExtractionError):
        extract_json_object("[1, 2, 3]")
