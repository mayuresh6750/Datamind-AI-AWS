import json
import logging
from functools import lru_cache

import boto3
from botocore.exceptions import ClientError

from app.core.config import settings

logger = logging.getLogger(__name__)


class AmazonTitanEmbeddingModel:
    """
    Amazon Titan Embeddings v2 (amazon.titan-embed-text-v2:0) via AWS Bedrock Runtime.
    - 1024 dimensions (Matryoshka learning compatible with pgvector)
    - Pre-normalized unit vectors (cosine similarity == dot product)
    - IAM authenticated with zero external API keys
    """

    def __init__(self) -> None:
        self.model_id = getattr(settings, "aws_titan_embedding_model", "amazon.titan-embed-text-v2:0")
        self.region = getattr(settings, "aws_bedrock_region", "us-east-1")
        self._client = boto3.client(
            "bedrock-runtime",
            region_name=self.region,
            aws_access_key_id=settings.aws_access_key_id or None,
            aws_secret_access_key=settings.aws_secret_access_key or None,
        )
        self._dimensions = 1024

    def embed(self, text: str) -> list[float]:
        try:
            payload = {
                "inputText": text,
                "dimensions": self._dimensions,
                "normalize": True,
            }
            response = self._client.invoke_model(
                modelId=self.model_id,
                contentType="application/json",
                accept="application/json",
                body=json.dumps(payload),
            )
            body = json.loads(response["body"].read())
            return body["embedding"]
        except Exception as e:
            logger.warning("Bedrock Titan Embeddings call failed (%s); falling back to local model.", e)
            return _get_local_fallback().embed(text)

    def embed_batch(self, texts: list[str], batch_size: int = 32) -> list[list[float]]:
        # Bedrock Runtime processes one embedding per invoke_model request
        embeddings: list[list[float]] = []
        for text in texts:
            embeddings.append(self.embed(text))
        return embeddings

    @property
    def dimensions(self) -> int:
        return self._dimensions


class LocalSentenceTransformerModel:
    """
    Fallback local embedding model (Qwen3-Embedding-0.6B via sentence-transformers).
    """

    def __init__(self) -> None:
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(
            settings.embedding_model,
            device=settings.embedding_device,
        )

    def embed(self, text: str) -> list[float]:
        return self._model.encode(text, normalize_embeddings=True).tolist()

    def embed_batch(self, texts: list[str], batch_size: int = 32) -> list[list[float]]:
        return self._model.encode(
            texts,
            batch_size=batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
        ).tolist()

    @property
    def dimensions(self) -> int:
        return self._model.get_embedding_dimension() or 1024


@lru_cache(maxsize=1)
def _get_local_fallback() -> LocalSentenceTransformerModel:
    return LocalSentenceTransformerModel()


@lru_cache(maxsize=1)
def get_embedding_model():
    """
    Singleton factory for embedding models.
    Returns Amazon Titan Embeddings v2 if provider is 'aws_bedrock'.
    """
    provider = getattr(settings, "embedding_provider", "aws_bedrock")
    if provider == "aws_bedrock":
        return AmazonTitanEmbeddingModel()
    return _get_local_fallback()
