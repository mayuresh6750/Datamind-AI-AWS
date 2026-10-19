"""
Unit tests for Google ADK (Google GenAI SDK) Integration in DataMind AI:
1. GoogleADKClient.structured_completion returning valid Pydantic models (AnalysisSpec, DashboardSpec).
2. Token accumulation & cost metrics.
3. Context cache creation and non-blocking error tolerance.
4. Tool execution safety (read-only SELECT enforcement, blocking DDL/DML, savepoints).
5. Autonomous ReAct analysis (run_adk_analysis) with deterministic fallback.
6. Integration with LLMClient.
"""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.adk import ContextCacheManager, GoogleADKClient, create_data_tools
from app.core.llm import LLMClient
from app.models.schemas import (
    AnalysisResult,
    AnalysisSpec,
    ChartSpec,
    DashboardSpec,
    KPICard,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures & Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_mock_response(text_content: str, prompt_tokens: int = 150, completion_tokens: int = 50) -> MagicMock:
    resp = MagicMock()
    resp.text = text_content
    usage = MagicMock()
    usage.prompt_token_count = prompt_tokens
    usage.candidates_token_count = completion_tokens
    resp.usage_metadata = usage
    return resp


class MockAsyncDbSession:
    """Mock AsyncSession with begin_nested() savepoint support."""
    def __init__(self, execute_result: list[dict] | None = None, raise_on_execute: Exception | None = None):
        self.execute_result = execute_result or []
        self.raise_on_execute = raise_on_execute
        self.executed_queries: list[str] = []

    async def begin_nested(self):
        class SavepointContext:
            async def __aenter__(self):
                return self
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                return False
        return SavepointContext()

    async def execute(self, statement, params=None):
        if self.raise_on_execute:
            raise self.raise_on_execute
        self.executed_queries.append(str(statement))

        class MockResult:
            def __init__(self, data: list[dict]):
                self.data = data
            def keys(self):
                return list(self.data[0].keys()) if self.data else []
            def fetchall(self):
                return [tuple(d.values()) for d in self.data]
            def __iter__(self):
                return iter(self.data)

        return MockResult(self.execute_result)


# ─────────────────────────────────────────────────────────────────────────────
# 1. GoogleADKClient Structured Completion Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_adk_structured_completion_analysis_spec():
    client = GoogleADKClient(api_key="test-key", model="gemini-2.0-flash")
    spec_data = {
        "reasoning": "User wants revenue aggregated by region",
        "original_question": "Total sales by region",
        "dimensions": ["region"],
        "measures": ["revenue"],
        "aggregation": "sum",
        "suggested_chart_types": ["bar"],
        "restatement": "Show total sales by region",
        "confidence": 0.95,
        "semantic_filter_concept": None,
    }
    mock_resp = _make_mock_response(json.dumps(spec_data), prompt_tokens=200, completion_tokens=80)

    with patch.object(client.client.aio.models, "generate_content", new=AsyncMock(return_value=mock_resp)):
        result = await client.structured_completion(
            prompt="Analyze sales by region",
            schema=AnalysisSpec,
            agent_name="intent_adk",
        )

    assert isinstance(result, AnalysisSpec)
    assert result.dimensions == ["region"]
    assert result.measures == ["revenue"]
    assert result.aggregation == "sum"
    assert result.confidence == 0.95
    assert client.total_tokens == 280
    assert client.total_cost_usd > 0.0


@pytest.mark.asyncio
async def test_adk_structured_completion_dashboard_spec():
    client = GoogleADKClient(api_key="test-key", model="gemini-2.0-flash")
    dashboard_data = {
        "kpi_cards": [{"label": "Total Revenue", "value": "$1,250,000", "change": "+14%", "change_pct": 14.0}],
        "charts": [{
            "chart_type": "bar",
            "title": "Revenue by Region",
            "data": [{"region": "North", "revenue": 500000}],
            "x_field": "region",
            "y_field": "revenue",
        }],
        "narrative": "North region continues to lead growth.",
        "recommended_action": "Expand inventory in North region.",
    }
    mock_resp = _make_mock_response(json.dumps(dashboard_data))

    with patch.object(client.client.aio.models, "generate_content", new=AsyncMock(return_value=mock_resp)):
        result = await client.structured_completion(
            prompt="Generate dashboard",
            schema=DashboardSpec,
            agent_name="dashboard_adk",
        )

    assert isinstance(result, DashboardSpec)
    assert len(result.kpi_cards) == 1
    assert result.kpi_cards[0].value == "$1,250,000"
    assert len(result.charts) == 1
    assert result.charts[0].chart_type == "bar"


@pytest.mark.asyncio
async def test_adk_retry_on_transient_failure():
    client = GoogleADKClient(api_key="test-key", model="gemini-2.0-flash")
    spec_data = {
        "reasoning": "Recovered spec",
        "dimensions": ["category"],
        "measures": ["profit"],
        "aggregation": "sum",
        "suggested_chart_types": ["bar"],
        "restatement": "Profit by category",
        "confidence": 0.9,
    }
    mock_resp = _make_mock_response(json.dumps(spec_data))

    call_mock = AsyncMock(side_effect=[
        RuntimeError("Transient 503 service unavailable"),
        mock_resp,
    ])

    with patch.object(client.client.aio.models, "generate_content", new=call_mock):
        with patch("asyncio.sleep", new=AsyncMock()):  # avoid actual sleep delay in test
            result = await client.structured_completion(
                prompt="Profit by category",
                schema=AnalysisSpec,
                agent_name="intent_adk",
            )

    assert result.dimensions == ["category"]
    assert call_mock.call_count == 2


@pytest.mark.asyncio
async def test_adk_quota_exhausted_fast_fails():
    client = GoogleADKClient(api_key="test-key", model="gemini-2.0-flash")
    call_mock = AsyncMock(side_effect=RuntimeError("ResourceExhausted: 429 quota exceeded"))

    with patch.object(client.client.aio.models, "generate_content", new=call_mock):
        with pytest.raises(RuntimeError) as exc_info:
            await client.structured_completion(
                prompt="test prompt",
                schema=AnalysisSpec,
                agent_name="intent_adk",
            )
        assert "429" in str(exc_info.value) or "quota" in str(exc_info.value).lower()
        # Should not retry 3 times on quota exhaustion
        assert call_mock.call_count == 1


# ─────────────────────────────────────────────────────────────────────────────
# 2. Context Cache Manager Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_context_cache_creation_and_reuse():
    mock_client = MagicMock()
    mock_cached_obj = MagicMock()
    mock_cached_obj.name = "cachedContents/test_cache_abc123"
    mock_client.caches.create.return_value = mock_cached_obj

    cache_mgr = ContextCacheManager(client=mock_client, model="gemini-2.0-flash")
    cache_id = cache_mgr.get_or_create_schema_cache(
        domain_prompt="Retail eCommerce with orders, returns, and customers",
        schema_description="Table: orders (order_id, customer_id, total_amount)",
        ttl_minutes=30,
    )

    assert cache_id == "cachedContents/test_cache_abc123"
    assert mock_client.caches.create.call_count == 1

    # Second call with same inputs returns cached token without calling API again
    cache_id_second = cache_mgr.get_or_create_schema_cache(
        domain_prompt="Retail eCommerce with orders, returns, and customers",
        schema_description="Table: orders (order_id, customer_id, total_amount)",
        ttl_minutes=30,
    )
    assert cache_id_second == "cachedContents/test_cache_abc123"
    assert mock_client.caches.create.call_count == 1


def test_context_cache_error_tolerance():
    mock_client = MagicMock()
    mock_client.caches.create.side_effect = RuntimeError("Context caching not supported for tier")

    cache_mgr = ContextCacheManager(client=mock_client, model="gemini-2.0-flash")
    # Gracefully returns None without crashing
    cache_id = cache_mgr.get_or_create_schema_cache(
        domain_prompt="Healthcare dataset",
        schema_description="Table: patients (patient_id, diag)",
    )
    assert cache_id is None


# ─────────────────────────────────────────────────────────────────────────────
# 3. Autonomous Tool Execution & Safety Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tool_execute_sql_query_allows_safe_select():
    db = MockAsyncDbSession(execute_result=[{"region": "EMEA", "sales": 45000}])
    tools = create_data_tools(db, table_name="ds_orders", dataset_id="ds_1")

    res = await tools.execute_sql_query('SELECT "region", SUM("sales") FROM "ds_orders" GROUP BY "region"')
    data = json.loads(res)
    assert isinstance(data, list)
    assert data[0]["region"] == "EMEA"
    assert data[0]["sales"] == 45000


@pytest.mark.asyncio
async def test_tool_execute_sql_query_blocks_ddl_and_dml():
    db = MockAsyncDbSession()
    tools = create_data_tools(db, table_name="ds_orders", dataset_id="ds_1")

    # DROP TABLE
    res1 = await tools.execute_sql_query("DROP TABLE ds_orders")
    assert "error" in json.loads(res1)
    assert "Safety violation" in json.loads(res1)["error"]

    # DELETE FROM
    res2 = await tools.execute_sql_query("DELETE FROM ds_orders WHERE id = 1")
    assert "error" in json.loads(res2)

    # Injection comment bypass
    res3 = await tools.execute_sql_query("-- comment\nDROP TABLE ds_orders")
    assert "error" in json.loads(res3)

    # Non-select statement
    res4 = await tools.execute_sql_query("UPDATE ds_orders SET status = 'cancelled'")
    assert "error" in json.loads(res4)

    assert len(db.executed_queries) == 0


@pytest.mark.asyncio
async def test_tool_search_semantic_feedback():
    db = MockAsyncDbSession()
    tools = create_data_tools(db, table_name="ds_orders", dataset_id="ds_1")

    with patch("app.agents.analysis.AnalysisAgent.retrieve_semantic_row_ids", new=AsyncMock(return_value=["id_1", "id_2"])):
        res = await tools.search_semantic_feedback("delivery delays")
        data = json.loads(res)
        assert data["concept"] == "delivery delays"
        assert data["matched_row_ids"] == ["id_1", "id_2"]
        assert data["count"] == 2


# ─────────────────────────────────────────────────────────────────────────────
# 4. AnalysisAgent Autonomous ReAct & Fallback
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_analysis_agent_run_adk_analysis_success():
    from app.agents.analysis import AnalysisAgent

    agent = AnalysisAgent()
    spec = AnalysisSpec(
        reasoning="Count orders with battery issues",
        dimensions=["region"],
        measures=["revenue"],
        aggregation="sum",
        suggested_chart_types=["bar"],
        restatement="Revenue by region for battery issues",
        confidence=0.9,
        semantic_filter_concept="battery issues",
    )

    db = MockAsyncDbSession(execute_result=[{"region": "APAC", "revenue": 12000}])

    mock_resp = MagicMock()
    mock_resp.text = "Identified 1 region impacted by battery issues."

    with patch("google.genai.Client") as mock_genai_cls:
        mock_client_inst = MagicMock()
        mock_client_inst.aio.models.generate_content = AsyncMock(return_value=mock_resp)
        mock_genai_cls.return_value = mock_client_inst

        result = await agent.run_adk_analysis(
            spec=spec,
            table_name="ds_reviews",
            dataset_id="ds_rev_1",
            db=db,
            domain="retail",
            available_cols=["region", "revenue", "_row_id"],
        )

    assert isinstance(result, AnalysisResult)
    assert result.confidence >= 0.85
    assert len(result.rows) > 0 or result.summary != ""


@pytest.mark.asyncio
async def test_analysis_agent_run_adk_analysis_fallback_on_error():
    from app.agents.analysis import AnalysisAgent

    agent = AnalysisAgent()
    spec = AnalysisSpec(
        reasoning="Test fallback",
        dimensions=["category"],
        measures=["sales"],
        aggregation="sum",
        suggested_chart_types=["bar"],
        restatement="Sales by category",
        confidence=0.88,
    )

    db = MockAsyncDbSession(execute_result=[{"category": "Tech", "sales": 80000}])

    # ADK raises error -> falls back to deterministic SQL
    with patch("google.genai.Client", side_effect=RuntimeError("ADK service offline")):
        with patch.object(agent, "run_numeric", new=AsyncMock(return_value=[{"category": "Tech", "sales": 80000}])):
            result = await agent.run_adk_analysis(
                spec=spec,
                table_name="ds_sales",
                dataset_id="ds_1",
                db=db,
                domain="retail",
            )

    assert isinstance(result, AnalysisResult)
    assert len(result.rows) == 1
    assert result.rows[0]["category"] == "Tech"
    assert "deterministic SQL" in result.summary


# ─────────────────────────────────────────────────────────────────────────────
# 5. LLMClient Integration with GoogleADKClient
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_llm_client_delegates_to_adk_for_google_gemini():
    client = LLMClient()
    client._provider = "google_gemini"

    mock_adk = MagicMock()
    spec = AnalysisSpec(
        reasoning="Test reasoning",
        dimensions=["status"],
        measures=["count"],
        aggregation="count",
        suggested_chart_types=["bar"],
        restatement="Count by status",
        confidence=0.9,
    )
    mock_adk.structured_completion = AsyncMock(return_value=spec)
    mock_adk.total_tokens = 120
    mock_adk.total_cost_usd = 0.0005
    client._adk_client = mock_adk
    client._force_adk = True

    result = await client.structured_completion(
        prompt="Status count",
        schema=AnalysisSpec,
        agent_name="test_integration",
    )

    assert result.dimensions == ["status"]
    assert client.total_tokens == 120
    assert client.total_cost_usd == 0.0005
    assert mock_adk.structured_completion.call_count == 1
