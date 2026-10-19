import pytest
from pydantic import BaseModel
from unittest.mock import patch, MagicMock

from app.core.config import settings
from app.core.embeddings import AmazonTitanEmbeddingModel, get_embedding_model
from app.core.llm import LLMClient, _PROVIDER_ROUTES, _MODEL_PRICING_PER_1M


class SampleSchema(BaseModel):
    summary: str
    status: str


def test_provider_routes_includes_bedrock():
    """Verify Bedrock is registered as an official LLM provider."""
    assert "aws_bedrock" in _PROVIDER_ROUTES
    assert _PROVIDER_ROUTES["aws_bedrock"] == "bedrock"


def test_pricing_includes_claude_sonnet():
    """Verify Claude 3.5 Sonnet token pricing table entries exist."""
    assert "anthropic.claude-3-5-sonnet-20241022-v2:0" in _MODEL_PRICING_PER_1M
    assert _MODEL_PRICING_PER_1M["anthropic.claude-3-5-sonnet-20241022-v2:0"]["input"] == 3.00


def test_titan_embedding_model_initialization():
    """Verify Titan Embeddings v2 model initializes with 1024 dimensions."""
    model = AmazonTitanEmbeddingModel()
    assert model.dimensions == 1024
    assert model.model_id == "amazon.titan-embed-text-v2:0"


def test_titan_embedding_model_embed_fallback():
    """Verify Titan Embeddings v2 gracefully falls back to local model if API unavailable."""
    model = AmazonTitanEmbeddingModel()
    with patch.object(model._client, "invoke_model", side_effect=RuntimeError("Access Denied")):
        with patch("app.core.embeddings._get_local_fallback") as mock_fallback:
            mock_fallback.return_value.embed.return_value = [0.1] * 1024
            embedding = model.embed("DataMind AI test")
            assert isinstance(embedding, list)
            assert len(embedding) == 1024
