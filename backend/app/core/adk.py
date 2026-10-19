"""
Google ADK (Agent Development Kit / Google GenAI SDK) Integration Layer.

Provides:
- GoogleADKClient: Native Pydantic Structured Outputs, pricing and token metrics.
- ContextCacheManager: Context caching for domain prompt packs and database schemas.
- create_data_tools: Autonomous ReAct tool execution with safe SQL and pgvector retrieval.
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Any, Callable, NamedTuple, Optional, Type, TypeVar

import structlog
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings

log = structlog.get_logger()
T = TypeVar("T", bound=BaseModel)

# Cost per 1 million tokens (USD). Input and output priced separately.
# Source: https://ai.google.dev/gemini-api/docs/pricing
_MODEL_PRICING_PER_1M: dict[str, dict[str, float]] = {
    "gemini-2.0-flash":     {"input": 0.10,  "output": 0.40},
    "gemini-2.0-flash-001": {"input": 0.10,  "output": 0.40},
    "gemini-1.5-flash":     {"input": 0.075, "output": 0.30},
    "gemini-1.5-pro":       {"input": 3.50,  "output": 10.50},
}
_DEFAULT_PRICING: dict[str, float] = {"input": 0.10, "output": 0.40}

# Exponential backoff retry delays (seconds)
_RETRY_DELAYS = (2, 4)
_CALL_TIMEOUT_SECONDS = 90


def _calculate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Return USD cost for one LLM call. Strips provider prefix before lookup."""
    short_model = model.split("/")[-1]
    pricing = _MODEL_PRICING_PER_1M.get(short_model, _DEFAULT_PRICING)
    return (prompt_tokens * pricing["input"] + completion_tokens * pricing["output"]) / 1_000_000


def _is_quota_error(exc: Exception) -> bool:
    """Return True for 429 / quota-exhausted errors."""
    msg = str(exc).lower()
    return any(k in msg for k in ("429", "quota", "rate_limit", "resource_exhausted", "too_many_requests"))


class GoogleADKClient:
    """
    Google GenAI SDK Client for native structured outputs (Pydantic schema enforcement),
    autonomous tool execution, and token/cost accumulation.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        from google import genai

        self._api_key = api_key or settings.llm_api_key
        raw_model = model or settings.llm_model
        # Strip provider prefix if present (e.g. "gemini/gemini-2.0-flash" -> "gemini-2.0-flash")
        self._model = raw_model.split("/")[-1]
        self.client = genai.Client(api_key=self._api_key)
        self.total_tokens: int = 0
        self.total_cost_usd: float = 0.0

    def _accumulate(self, model: str, prompt_tokens: int, completion_tokens: int) -> None:
        """Add token counts and cost from one call to running totals."""
        self.total_tokens += prompt_tokens + completion_tokens
        self.total_cost_usd += _calculate_cost(model, prompt_tokens, completion_tokens)

    async def structured_completion(
        self,
        prompt: str,
        schema: Type[T],
        agent_name: str,
        system_instruction: str | None = None,
        cached_content: str | None = None,
    ) -> T:
        """
        Executes a prompt against Gemini using native response_schema Pydantic enforcement.
        Catches transient errors with exponential back-off (2s, 4s).
        """
        from google.genai import types

        start = time.monotonic()
        last_error: Exception | None = None

        config_kwargs: dict[str, Any] = {
            "response_mime_type": "application/json",
            "response_schema": schema,
        }
        if system_instruction:
            config_kwargs["system_instruction"] = system_instruction
        if cached_content:
            config_kwargs["cached_content"] = cached_content

        config = types.GenerateContentConfig(**config_kwargs)

        for attempt in range(1, 4):
            try:
                response = await asyncio.wait_for(
                    self.client.aio.models.generate_content(
                        model=self._model,
                        contents=prompt,
                        config=config,
                    ),
                    timeout=_CALL_TIMEOUT_SECONDS,
                )

                raw_text = response.text or "{}"
                if raw_text.strip().startswith("```"):
                    raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text.strip())
                    raw_text = re.sub(r"\s*```$", "", raw_text.strip())

                result = schema.model_validate_json(raw_text)

                latency_ms = int((time.monotonic() - start) * 1000)
                usage = getattr(response, "usage_metadata", None)
                prompt_tokens = usage.prompt_token_count if usage else 0
                completion_tokens = usage.candidates_token_count if usage else 0
                self._accumulate(self._model, prompt_tokens, completion_tokens)

                log.info(
                    "adk_call_success",
                    agent=agent_name,
                    model=self._model,
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
                    log.warning(
                        "adk_quota_exhausted_fast_fail",
                        agent=agent_name,
                        attempt=attempt,
                        error=str(exc),
                    )
                    raise

                log.warning("adk_call_failed", agent=agent_name, attempt=attempt, error=str(exc))
                if attempt < 3:
                    await asyncio.sleep(_RETRY_DELAYS[attempt - 1])

        raise RuntimeError(
            f"Google ADK completion failed after 3 attempts for agent '{agent_name}': {last_error}"
        )


class ContextCacheManager:
    """
    Manages Gemini Context Caching for static domain prompts and database schemas.
    Caches reduce latency and provide token cost reduction on repeated dataset queries.
    """

    def __init__(self, client: Any | None = None, model: str | None = None) -> None:
        self._client = client
        raw_model = model or settings.llm_model
        self._model = raw_model.split("/")[-1]
        self._cache_map: dict[str, str] = {}

    def _get_client(self) -> Any:
        if self._client is None:
            from google import genai
            self._client = genai.Client(api_key=settings.llm_api_key)
        return self._client

    def get_or_create_schema_cache(
        self,
        domain_prompt: str,
        schema_description: str,
        ttl_minutes: int = 60,
    ) -> str | None:
        """
        Creates or retrieves a cached content token for domain context and table schema.
        Returns the cached content ID string to be reused across queries, or None on failure.
        """
        cache_key = f"{hash(domain_prompt)}_{hash(schema_description)}"
        if cache_key in self._cache_map:
            return self._cache_map[cache_key]

        try:
            from google.genai import types

            client = self._get_client()
            combined_content = (
                f"=== DOMAIN KNOWLEDGE & CONTEXT ===\n{domain_prompt}\n\n"
                f"=== DATABASE SCHEMA SPECIFICATION ===\n{schema_description}"
            )
            cache_config = types.CreateCachedContentConfig(
                contents=[combined_content],
                ttl=f"{ttl_minutes * 60}s",
                display_name=f"datamind_schema_{int(time.time())}",
            )
            cached_content = client.caches.create(
                model=self._model,
                config=cache_config,
            )
            cache_name = getattr(cached_content, "name", None)
            if cache_name:
                self._cache_map[cache_key] = cache_name
                log.info("adk_schema_cache_created", cache_name=cache_name, ttl_minutes=ttl_minutes)
                return cache_name
            return None
        except Exception as exc:
            log.warning("adk_schema_cache_create_failed", error=str(exc))
            return None


class DataTools(NamedTuple):
    execute_sql_query: Callable[..., Any]
    search_semantic_feedback: Callable[..., Any]


def create_data_tools(
    db_session: AsyncSession,
    table_name: str,
    dataset_id: str,
) -> DataTools:
    """
    Creates autonomous ReAct data tools for Gemini:
    - execute_sql_query: Safety-enforced read-only SELECT query executor on table_name.
    - search_semantic_feedback: pgvector semantic retrieval against dataset_embeddings.
    """

    async def execute_sql_query(sql: str) -> str:
        """
        Execute a read-only SELECT SQL query on PostgreSQL.
        All column names in the query must be double-quoted.

        Args:
            sql: A valid SQL SELECT query statement.

        Returns:
            JSON string containing query results or error message.
        """
        cleaned_sql = sql.strip().rstrip(";")
        # Remove any leading comments
        cleaned_sql = re.sub(r"^\s*--.*?\n", "", cleaned_sql, flags=re.MULTILINE).strip()

        # Strict SELECT enforcement
        if not re.match(r"^SELECT\b", cleaned_sql, re.IGNORECASE):
            log.error("adk_sql_tool_non_select_blocked", sql=cleaned_sql[:100])
            return json.dumps({"error": "Safety violation: Only read-only SELECT statements are permitted."})

        # Block destructive / DDL keywords
        forbidden_keywords = (
            r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|CREATE|REPLACE|GRANT|REVOKE)\b"
        )
        if re.search(forbidden_keywords, cleaned_sql, re.IGNORECASE):
            log.error("adk_sql_tool_forbidden_keyword_blocked", sql=cleaned_sql[:100])
            return json.dumps({"error": "Safety violation: DDL/DML statements are prohibited."})

        # Cap limit if not present or too large
        if not re.search(r"\bLIMIT\b", cleaned_sql, re.IGNORECASE):
            cleaned_sql = f"{cleaned_sql} LIMIT 100"

        try:
            async with await db_session.begin_nested():
                result = await db_session.execute(text(cleaned_sql))
                rows = [dict(zip(result.keys(), row)) for row in result.fetchall()]
            log.info("adk_sql_tool_executed", rows_count=len(rows), sql=cleaned_sql[:150])
            return json.dumps(rows, default=str)
        except Exception as exc:
            log.warning("adk_sql_tool_failed", error=str(exc), sql=cleaned_sql[:150])
            return json.dumps({"error": f"SQL execution error: {str(exc)}"})

    async def search_semantic_feedback(concept: str) -> str:
        """
        Search customer feedback, reviews, clinical notes, and unstructured text in pgvector
        using semantic embedding cosine similarity.

        Args:
            concept: The semantic concept or qualitative phrase to search for (e.g. 'battery issues').

        Returns:
            JSON string containing matching row IDs and count.
        """
        from app.agents.analysis import AnalysisAgent
        agent = AnalysisAgent()
        try:
            matched_ids = await agent.retrieve_semantic_row_ids(
                concept=concept,
                dataset_id=dataset_id,
                db=db_session,
                threshold=0.70,
                limit=500,
            )
            log.info("adk_semantic_tool_executed", concept=concept, matches=len(matched_ids))
            return json.dumps({"concept": concept, "matched_row_ids": matched_ids, "count": len(matched_ids)})
        except Exception as exc:
            log.warning("adk_semantic_tool_failed", error=str(exc), concept=concept)
            return json.dumps({"error": f"Semantic search failed: {str(exc)}", "matched_row_ids": []})

    return DataTools(
        execute_sql_query=execute_sql_query,
        search_semantic_feedback=search_semantic_feedback,
    )
