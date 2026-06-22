import asyncio
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

# Fallback model: a different Gemini generation tried once after all primary retries fail.
# Only used for transient errors (503/timeout) — quota errors (429) skip this entirely
# because both models share the same API key and therefore the same quota pool.
_FALLBACK_MODEL = "gemini/gemini-2.0-flash"

# Wait times (seconds) between retry attempts for transient errors.
# Attempt 1→2 waits 2s, attempt 2→3 waits 4s.
_RETRY_DELAYS = (1, 2)


def _is_quota_error(exc: Exception) -> bool:
    """Return True for 429 / quota-exhausted errors where retrying will not help."""
    msg = str(exc).lower()
    return any(k in msg for k in ("429", "quota", "rate_limit", "resource_exhausted", "too_many_requests"))


class QuotaExhaustedError(RuntimeError):
    """Raised when the LLM API quota is exhausted so agents can fast-fail to manual fallback."""


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
        quota_hit = False

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

                if _is_quota_error(exc):
                    # 429 / quota exhausted — retrying won't help, and the fallback model
                    # shares the same API key so it would also fail. Stop immediately and
                    # let the agent fall back to its manual rule-based code.
                    log.warning(
                        "llm_quota_exhausted_fast_fail",
                        agent=agent_name,
                        attempt=attempt,
                        error=str(exc),
                    )
                    quota_hit = True
                    break

                log.warning("llm_call_failed", agent=agent_name, attempt=attempt, error=str(exc))
                # Exponential backoff so transient 503s have time to recover before next retry.
                if attempt < 3:
                    await asyncio.sleep(_RETRY_DELAYS[attempt - 1])

        if quota_hit:
            # Raise a typed exception so the caller knows quota is the reason,
            # not a transient failure that might succeed on a later request.
            raise QuotaExhaustedError(
                f"LLM quota exhausted for agent '{agent_name}': {last_error}"
            )

        # Primary model exhausted all retries with a transient error (503 / timeout).
        # Try the fallback model once — it is a different Gemini generation and may
        # be available even when the primary endpoint is overloaded.
        log.warning(
            "llm_primary_exhausted_trying_fallback",
            agent=agent_name,
            fallback_model=_FALLBACK_MODEL,
        )
        try:
            response = await litellm.acompletion(
                model=_FALLBACK_MODEL,
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
                "llm_fallback_success",
                agent=agent_name,
                fallback_model=_FALLBACK_MODEL,
                latency_ms=latency_ms,
                tokens_in=response.usage.prompt_tokens if response.usage else 0,
                tokens_out=response.usage.completion_tokens if response.usage else 0,
            )
            return result

        except Exception as fallback_exc:
            raise RuntimeError(
                f"LLM call failed after 3 attempts and fallback for agent '{agent_name}': "
                f"primary_error={last_error}, fallback_error={fallback_exc}"
            )
