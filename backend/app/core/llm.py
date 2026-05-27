import time
from typing import TypeVar, Type

import structlog
from pydantic import BaseModel

from app.core.config import settings

log = structlog.get_logger()
T = TypeVar("T", bound=BaseModel)

_PROVIDER_ROUTES: dict[str, str] = {
    "google_gemini": "gemini",
}


class LLMClient:
    """
    LiteLLM-compatible abstraction layer.
    All agents call this; no agent hardcodes a provider.
    Per-tenant provider config is resolved at call time.
    """

    def __init__(self, tenant_id: str | None = None) -> None:
        self.tenant_id = tenant_id
        self._provider = settings.llm_provider
        self._model = settings.llm_model
        self._api_key = settings.llm_api_key

    async def structured_completion(
        self,
        prompt: str,
        schema: Type[T],
        agent_name: str,
        provider_override: str | None = None,
        model_override: str | None = None,
    ) -> T:
        import litellm

        provider = provider_override or self._provider
        model = model_override or self._model
        litellm_model = f"{_PROVIDER_ROUTES.get(provider, provider)}/{model}"

        start = time.monotonic()
        last_error: Exception | None = None

        for attempt in range(1, 4):
            try:
                response = await litellm.acompletion(
                    model=litellm_model,
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "You are a data intelligence agent. "
                                "Respond ONLY with valid JSON matching the requested schema."
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                    api_key=self._api_key,
                    response_format={"type": "json_object"},
                )
                raw = response.choices[0].message.content or "{}"
                result = schema.model_validate_json(raw)

                latency_ms = int((time.monotonic() - start) * 1000)
                log.info(
                    "llm_call_success",
                    agent=agent_name,
                    provider=provider,
                    model=model,
                    attempt=attempt,
                    latency_ms=latency_ms,
                    tokens_in=response.usage.prompt_tokens if response.usage else 0,
                    tokens_out=response.usage.completion_tokens if response.usage else 0,
                )
                return result

            except Exception as exc:
                last_error = exc
                log.warning("llm_call_failed", agent=agent_name, attempt=attempt, error=str(exc))

        raise RuntimeError(
            f"LLM call failed after 3 attempts for agent '{agent_name}': {last_error}"
        )
