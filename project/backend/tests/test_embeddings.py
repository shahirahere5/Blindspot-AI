"""Unit tests for the Phase 4 embedding layer (ai/embeddings/*)."""

from __future__ import annotations

import pytest

import config
from ai.embeddings.base import EmbeddingConfigurationError, EmbeddingGenerationError
from ai.embeddings.factory import get_embedding_provider
from ai.embeddings.hashing import HashingEmbeddingProvider


def test_hashing_provider_is_deterministic():
    provider = HashingEmbeddingProvider(dimension=64)

    v1 = provider.embed_texts(["hello world"])[0]
    v2 = provider.embed_texts(["hello world"])[0]

    assert v1 == v2


def test_hashing_provider_returns_correct_dimension():
    provider = HashingEmbeddingProvider(dimension=32)

    vectors = provider.embed_texts(["some text", "some other text"])

    assert len(vectors) == 2
    assert all(len(v) == 32 for v in vectors)
    assert provider.dimension == 32


def test_hashing_provider_different_texts_produce_different_vectors():
    provider = HashingEmbeddingProvider(dimension=64)

    v1, v2 = provider.embed_texts(["financial risk and revenue model", "cats and dogs"])

    assert v1 != v2


def test_hashing_provider_shared_vocabulary_is_more_similar_than_unrelated_text():
    provider = HashingEmbeddingProvider(dimension=128)

    base = "financial risk revenue model pricing market"
    similar = "financial risk revenue pricing plan"
    unrelated = "cats dogs birthday party balloons"

    v_base, v_similar, v_unrelated = provider.embed_texts([base, similar, unrelated])

    def cosine(a, b):
        dot = sum(x * y for x, y in zip(a, b))
        return dot  # vectors are already L2-normalized by the provider

    assert cosine(v_base, v_similar) > cosine(v_base, v_unrelated)


def test_hashing_provider_empty_text_returns_zero_vector():
    provider = HashingEmbeddingProvider(dimension=16)

    vectors = provider.embed_texts([""])

    assert vectors == [[0.0] * 16]


def test_embed_texts_empty_list_returns_empty_list():
    provider = HashingEmbeddingProvider(dimension=16)

    assert provider.embed_texts([]) == []


def test_hashing_provider_rejects_non_positive_dimension():
    with pytest.raises(EmbeddingConfigurationError):
        HashingEmbeddingProvider(dimension=0)


def test_hashing_provider_wraps_unexpected_failures():
    provider = HashingEmbeddingProvider(dimension=16)
    provider._embed_one = lambda text: (_ for _ in ()).throw(RuntimeError("boom"))

    with pytest.raises(EmbeddingGenerationError):
        provider.embed_texts(["anything"])


def test_factory_returns_hashing_provider_by_default(monkeypatch):
    monkeypatch.setattr(config, "RAG_EMBEDDING_PROVIDER", "hashing")

    provider = get_embedding_provider()

    assert provider.provider_name == "hashing"


def test_factory_raises_configuration_error_for_unknown_provider(monkeypatch):
    monkeypatch.setattr(config, "RAG_EMBEDDING_PROVIDER", "some-unsupported-provider")

    with pytest.raises(EmbeddingConfigurationError):
        get_embedding_provider()
