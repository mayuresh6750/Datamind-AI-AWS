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

# Fallback: pinned stable model tried once if the primary model exhausts all 3 retries.
# gemini-2.0-flash-001 is used because it is a known-good, version-locked alternative
# that remains available even when the primary model is rate-limited or unavailable.
_FALLBACK_MODEL = "gemini/gemini-2.0-flash-001"

# Cost per 1 million tokens (USD). Input and output priced separately.
# Source: https://ai.google.dev/gemini-api/docs/pricing
_MODEL_PRICING_PER_1M: dict[str, dict[str, float]] = {
    "gemini-2.0-flash":     {"input": 0.10,  "output": 0.40},
    "gemini-2.0-flash-001": {"input": 0.10,  "output": 0.40},
    "gemini-1.5-flash":     {"input": 0.075, "output": 0.30},
    "gemini-1.5-pro":       {"input": 3.50,  "output": 10.50},
}
_DEFAULT_PRICING: dict[str, float] = {"input": 0.10, "output": 0.40}


def _calculate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Return USD cost for one LLM call. Strips provider prefix before lookup."""
    short_model = model.split("/")[-1]
    pricing = _MODEL_PRICING_PER_1M.get(short_model, _DEFAULT_PRICING)
    return (prompt_tokens * pricing["input"] + completion_tokens * pricing["output"]) / 1_000_000


class LLMClient:
    """
    LiteLLM-compatible abstraction layer.
    All agents call this; no agent hardcodes a provider.
    Per-tenant provider config is resolved at call time.

    Token tracking:
        total_tokens   — cumulative (prompt + completion) tokens across all calls on this instance
        total_cost_usd — cumulative USD cost across all calls on this instance
    Pass one shared LLMClient to all agents in a pipeline run so the worker
    can read totals at the end and persist them to PipelineRun.
    """

    def __init__(self, tenant_id: str | None = None) -> None:
        self.tenant_id = tenant_id
        self._provider = settings.llm_provider
        self._model = settings.llm_model
        self._api_key = settings.llm_api_key
        # Cumulative counters — accumulated across every call made on this instance
        self.total_tokens: int = 0
        self.total_cost_usd: float = 0.0

    def _accumulate(self, model: str, prompt_tokens: int, completion_tokens: int) -> None:
        """Add token counts and cost from one call to the running totals."""
        self.total_tokens += prompt_tokens + completion_tokens
        self.total_cost_usd += _calculate_cost(model, prompt_tokens, completion_tokens)

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
                prompt_tokens = response.usage.prompt_tokens if response.usage else 0
                completion_tokens = response.usage.completion_tokens if response.usage else 0
                self._accumulate(model, prompt_tokens, completion_tokens)

                log.info(
                    "llm_call_success",
                    agent=agent_name,
                    provider=provider,
                    model=model,
                    attempt=attempt,
                    latency_ms=latency_ms,
                    tokens_in=prompt_tokens,
                    tokens_out=completion_tokens,
                    total_tokens=self.total_tokens,
                )
                return result

            except Exception as exc:
                last_error = exc
                log.warning("llm_call_failed", agent=agent_name, attempt=attempt, error=str(exc))

        # Primary model exhausted all 3 attempts — try the fallback model once.
        # This runs only when every retry above has failed.
        log.warning(
            "llm_primary_exhausted_trying_fallback",
            agent=agent_name,
            fallback_model=_FALLBACK_MODEL,  # log which fallback model is being used
        )
        try:
            # Single attempt with the fallback model — no further retries to keep latency bounded
            response = await litellm.acompletion(
                model=_FALLBACK_MODEL,  # use the pinned fallback model instead of the primary
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
            result = schema.model_validate_json(raw)  # parse fallback response into the schema

            latency_ms = int((time.monotonic() - start) * 1000)
            prompt_tokens = response.usage.prompt_tokens if response.usage else 0
            completion_tokens = response.usage.completion_tokens if response.usage else 0
            self._accumulate(_FALLBACK_MODEL, prompt_tokens, completion_tokens)

            log.info(
                "llm_fallback_success",  # distinct log event so it's easy to monitor fallback usage
                agent=agent_name,
                fallback_model=_FALLBACK_MODEL,
                latency_ms=latency_ms,
                tokens_in=prompt_tokens,
                tokens_out=completion_tokens,
                total_tokens=self.total_tokens,
            )
            return result  # return the fallback result — caller is unaware a fallback was used

        except Exception as fallback_exc:
            # Fallback also failed — nothing left to try, raise with full context
            raise RuntimeError(
                f"LLM call failed after 3 attempts and fallback for agent '{agent_name}': "
                f"primary_error={last_error}, fallback_error={fallback_exc}"
            )
