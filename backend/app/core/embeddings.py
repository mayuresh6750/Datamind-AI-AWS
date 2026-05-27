from functools import lru_cache

from app.core.config import settings


class EmbeddingModel:
    """
    Qwen3-Embedding-0.6B via sentence-transformers.
    Self-hosted in the FastAPI container — no Ollama required.
    8K token context, 1024 dimensions, provider-neutral.
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
        return self._model.get_sentence_embedding_dimension() or 1024


@lru_cache(maxsize=1)
def get_embedding_model() -> EmbeddingModel:
    """Singleton — model loads once at container startup."""
    return EmbeddingModel()
