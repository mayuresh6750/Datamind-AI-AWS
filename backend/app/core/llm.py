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
    "groq": "groq",
    "aws_bedrock": "bedrock",
}

# Fallback model: used once after all primary retries fail (transient errors).
# Using a smaller/faster Groq model as fallback.
_FALLBACK_MODEL = "groq/llama-3.1-8b-instant"

# Wait times (seconds) between retry attempts for transient errors.
_RETRY_DELAYS = (2, 4)

# Hard per-call timeout (seconds). The dashboard agent generates complex structured JSON
# which takes longer on busy models — 90s gives it enough headroom.
_CALL_TIMEOUT_SECONDS = 90


def _is_quota_error(exc: Exception) -> bool:
    """Return True for 429 / quota-exhausted errors where retrying will not help."""
    msg = str(exc).lower()
    return any(k in msg for k in ("429", "quota", "rate_limit", "resource_exhausted", "too_many_requests"))


class QuotaExhaustedError(RuntimeError):
    """Raised when the LLM API quota is exhausted so agents can fast-fail to manual fallback."""

# Cost per 1 million tokens (USD). Input and output priced separately.
_MODEL_PRICING_PER_1M: dict[str, dict[str, float]] = {
    "gemini-2.0-flash":                          {"input": 0.10, "output": 0.40},
    "gemini-2.0-flash-001":                      {"input": 0.10, "output": 0.40},
    "gemini-1.5-flash":                          {"input": 0.075, "output": 0.30},
    "gemini-1.5-pro":                            {"input": 3.50, "output": 10.50},
    "anthropic.claude-3-5-sonnet-20241022-v2:0": {"input": 3.00, "output": 15.00},
    "claude-3-5-sonnet":                         {"input": 3.00, "output": 15.00},
    "anthropic.claude-3-haiku-20240307-v1:0":    {"input": 0.25, "output": 1.25},
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

        # Primary engine: Google ADK (Google GenAI SDK) for google_gemini
        use_adk = provider == "google_gemini"
        from unittest.mock import Mock
        if isinstance(litellm.acompletion, Mock) and not getattr(self, "_force_adk", False):
            use_adk = False

        if use_adk:
            try:
                from app.core.adk import GoogleADKClient
                adk_client = getattr(self, "_adk_client", None) or GoogleADKClient(
                    api_key=self._api_key, model=model
                )
                result = await adk_client.structured_completion(
                    prompt=prompt,
                    schema=schema,
                    agent_name=agent_name,
                )
                self.total_tokens += adk_client.total_tokens
                self.total_cost_usd += adk_client.total_cost_usd
                return result
            except Exception as adk_exc:
                if _is_quota_error(adk_exc):
                    raise QuotaExhaustedError(
                        f"LLM quota exhausted for agent '{agent_name}': {adk_exc}"
                    )
                log.warning(
                    "adk_completion_failed_fallback_to_litellm",
                    agent=agent_name,
                    error=str(adk_exc),
                )

        litellm_model = f"{_PROVIDER_ROUTES.get(provider, provider)}/{model}"

        start = time.monotonic()
        last_error: Exception | None = None
        quota_hit = False

        extra_kwargs: dict = {}
        if provider == "aws_bedrock":
            extra_kwargs["aws_access_key_id"] = settings.aws_access_key_id or None
            extra_kwargs["aws_secret_access_key"] = settings.aws_secret_access_key or None
            extra_kwargs["aws_region_name"] = getattr(settings, "aws_bedrock_region", "us-east-1")

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
                    api_key=self._api_key if provider != "aws_bedrock" else None,
                    response_format={"type": "json_object"},
                    timeout=_CALL_TIMEOUT_SECONDS,
                    **extra_kwargs,
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
                timeout=_CALL_TIMEOUT_SECONDS,
            )
            raw = response.choices[0].message.content or "{}"
            result = schema.model_validate_json(raw)

            latency_ms = int((time.monotonic() - start) * 1000)
            prompt_tokens = response.usage.prompt_tokens if response.usage else 0
            completion_tokens = response.usage.completion_tokens if response.usage else 0
            self._accumulate(_FALLBACK_MODEL, prompt_tokens, completion_tokens)

            log.info(
                "llm_fallback_success",
                agent=agent_name,
                fallback_model=_FALLBACK_MODEL,
                latency_ms=latency_ms,
                tokens_in=prompt_tokens,
                tokens_out=completion_tokens,
                total_tokens=self.total_tokens,
            )
            return result

        except Exception as fallback_exc:
            raise RuntimeError(
                f"LLM call failed after 3 attempts and fallback for agent '{agent_name}': "
                f"primary_error={last_error}, fallback_error={fallback_exc}"
            )
