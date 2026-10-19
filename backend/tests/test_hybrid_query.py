import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.schemas import AnalysisSpec, ColumnProfile, DashboardSpec, KPICard, ChartSpec
from app.agents.intent import IntentAgent
from app.agents.analysis import AnalysisAgent
from app.agents.insights import InsightsAgent


def make_mock_db():
    mock_db = MagicMock()
    mock_nested = MagicMock()
    mock_nested.__aenter__ = AsyncMock(return_value=mock_nested)
    mock_nested.__aexit__ = AsyncMock(return_value=None)
    mock_db.begin_nested = AsyncMock(return_value=mock_nested)
    mock_db.execute = AsyncMock()
    return mock_db


def test_analysis_spec_semantic_filter_field():
    """Verify semantic_filter_concept field exists and defaults to None."""
    spec = AnalysisSpec(
        reasoning="Test",
        dimensions=["category"],
        measures=["sales"],
        aggregation="sum",
        suggested_chart_types=["bar"],
        restatement="Sales by category",
        confidence=0.9,
    )
    assert spec.semantic_filter_concept is None

    spec_hybrid = AnalysisSpec(
        reasoning="Hybrid",
        dimensions=[],
        measures=["revenue"],
        aggregation="sum",
        suggested_chart_types=["bar"],
        restatement="Revenue lost to battery issues",
        confidence=0.85,
        semantic_filter_concept="battery issues",
    )
    assert spec_hybrid.semantic_filter_concept == "battery issues"


@pytest.mark.asyncio
async def test_intent_agent_extracts_semantic_concept():
    """Verify IntentAgent extracts semantic concepts from natural language questions."""
    agent = IntentAgent()
    profiles = [
        ColumnProfile(name="Product", dtype="text", null_count=0, distinct_count=10, classification="structured"),
        ColumnProfile(name="Revenue", dtype="float", null_count=0, distinct_count=100, classification="numeric"),
        ColumnProfile(name="Review", dtype="text", null_count=0, distinct_count=500, classification="textual"),
    ]

    # Test heuristic concept extraction
    concept1 = agent._extract_semantic_concept("What was the total revenue lost to battery issues?", profiles)
    assert concept1 == "battery issues"

    concept2 = agent._extract_semantic_concept("Average order value for customers complaining about delivery delays", profiles)
    assert concept2 == "delivery delays"

    concept3 = agent._extract_semantic_concept("How many patients readmitted due to post-surgery infections?", profiles)
    assert concept3 == "post-surgery infections"

    # Standard query without semantic filter
    concept_std = agent._extract_semantic_concept("Total revenue by product", profiles)
    assert concept_std is None


@pytest.mark.asyncio
async def test_intent_agent_parse_hybrid_fallback():
    """Verify parse() populates semantic_filter_concept even under heuristic fallback."""
    agent = IntentAgent(llm=MagicMock())
    agent.llm.structured_completion = AsyncMock(side_effect=Exception("LLM offline"))

    profiles = [
        ColumnProfile(name="Order_ID", dtype="text", null_count=0, distinct_count=50, classification="structured"),
        ColumnProfile(name="Revenue", dtype="float", null_count=0, distinct_count=50, classification="numeric"),
        ColumnProfile(name="Feedback", dtype="text", null_count=0, distinct_count=50, classification="textual"),
    ]

    spec = await agent.parse("What was the total revenue lost to battery issues?", profiles, domain="retail")
    assert spec.semantic_filter_concept == "battery issues"
    assert "Revenue" in spec.measures
    assert spec.aggregation == "sum"


@pytest.mark.asyncio
async def test_analysis_agent_retrieve_semantic_row_ids():
    """Verify retrieve_semantic_row_ids queries pgvector, filters by threshold, and extracts row IDs."""
    agent = AnalysisAgent()
    mock_db = make_mock_db()

    row1 = MagicMock()
    row1.similarity = 0.88
    row1.metadata = {"_row_id": "row_1", "order_id": "ORD-101"}

    row2 = MagicMock()
    row2.similarity = 0.72
    row2.metadata = {"_row_id": "row_2", "order_id": "ORD-102"}

    row_low = MagicMock()
    row_low.similarity = 0.55  # Below 0.70 threshold
    row_low.metadata = {"_row_id": "row_3", "order_id": "ORD-103"}

    mock_result = MagicMock()
    mock_result.__iter__.return_value = [row1, row2, row_low]
    mock_db.execute.return_value = mock_result

    with patch("app.agents.analysis.get_embedding_model") as mock_get_emb:
        mock_emb_model = MagicMock()
        mock_emb_model.embed.return_value = [0.1] * 1024
        mock_get_emb.return_value = mock_emb_model

        ids = await agent.retrieve_semantic_row_ids(
            concept="battery issues",
            dataset_id="test-ds-id",
            db=mock_db,
            threshold=0.70,
            limit=500,
            id_column="order_id",
        )

        assert ids == ["ORD-101", "ORD-102"]
        assert "ORD-103" not in ids


@pytest.mark.asyncio
async def test_analysis_agent_run_numeric_with_id_filters():
    """Verify run_numeric safely applies dynamic IN filter in WHERE clause."""
    agent = AnalysisAgent()
    mock_db = make_mock_db()

    # Mock information_schema.columns discovery
    mock_col_res = MagicMock()
    mock_col_res.fetchall.return_value = [("Order_ID",), ("Revenue",), ("_row_id",)]

    # Mock sample query
    mock_samp_res = MagicMock()
    mock_samp_res.fetchall.return_value = [(100.5,), (200.0,)]

    # Mock aggregation query
    mock_exec_res = MagicMock()
    mock_exec_res.keys.return_value = ["Revenue"]
    mock_exec_res.fetchall.return_value = [(300.5,)]

    mock_db.execute.side_effect = [mock_col_res, mock_samp_res, mock_exec_res]

    spec = AnalysisSpec(
        reasoning="Test hybrid",
        dimensions=[],
        measures=["Revenue"],
        aggregation="sum",
        suggested_chart_types=["bar"],
        restatement="Total revenue",
        confidence=0.9,
        filters=[{"col": "Order_ID", "op": "IN", "val": ["ORD-101", "ORD-102"]}],
    )

    rows = await agent.run_numeric(spec, "ds_test", mock_db, "retail")
    assert rows == [{"Revenue": 300.5}]

    # Inspect the generated SQL call
    executed_sql = str(mock_db.execute.call_args_list[2][0][0])
    assert '"Order_ID" IN (\'ORD-101\', \'ORD-102\')' in executed_sql
    assert 'SUM(NULLIF(REGEXP_REPLACE("Revenue"' in executed_sql


@pytest.mark.asyncio
async def test_analysis_agent_run_numeric_zero_semantic_matches():
    """Verify run_numeric handles 0 matching IDs gracefully without crashing."""
    agent = AnalysisAgent()
    mock_db = make_mock_db()
    mock_col_res = MagicMock()
    mock_col_res.fetchall.return_value = [("Order_ID",), ("Revenue",)]
    mock_db.execute.return_value = mock_col_res

    spec = AnalysisSpec(
        reasoning="Zero match test",
        dimensions=[],
        measures=["Revenue"],
        aggregation="sum",
        suggested_chart_types=["bar"],
        restatement="Revenue lost",
        confidence=0.9,
        semantic_filter_concept="nuclear radiation leak",
        filters=[{"col": "Order_ID", "op": "IN", "val": []}],  # 0 IDs matched
    )

    rows = await agent.run_numeric(spec, "ds_test", mock_db, "retail")
    assert rows == []


@pytest.mark.asyncio
async def test_insights_agent_grounds_narrative_with_semantic_concept():
    """Verify InsightsAgent explicitly grounds executive narrative and recommendation in semantic concept."""
    agent = InsightsAgent()
    dashboard = DashboardSpec(
        kpi_cards=[
            KPICard(label="Total Lost Revenue", value="$48,200"),
            KPICard(label="Affected Orders", value="142"),
        ],
        charts=[
            ChartSpec(chart_type="bar", title="Lost Revenue", data=[{"x": "Battery", "y": 48200}], x_field="x", y_field="y"),
        ],
        narrative="",
        recommended_action="",
    )

    # Test heuristic enrichment
    enriched = agent._heuristic_insights(dashboard, domain="retail", semantic_concept="battery issues")
    assert "battery issues" in enriched.narrative.lower()
    assert "$48,200" in enriched.narrative
    assert "battery issues" in enriched.recommended_action.lower()
