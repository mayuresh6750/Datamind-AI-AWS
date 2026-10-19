"""
Unit tests for IntentAgent.parse()

Source agent : backend/app/agents/intent.py

Run with:
    pytest  test_intent_agent.py -v
    python  test_intent_agent.py          # live results, no pytest needed

Fully independent — no real LLM, no DB, no Supabase, no app imports.
External dependencies are replaced by in-process stubs:

    MockLLM        — controls exactly what AnalysisSpec structured_completion returns.
                     Records every prompt it receives and can be set to raise.
    ColumnProfile  — minimal dataclass matching app/models/schemas.py
    AnalysisSpec   — minimal dataclass matching app/models/schemas.py

Contract under test  (IntentAgent.parse):
    ┌─────────────────────────────────────────────────────────────────────┐
    │ 1. Format column profiles into "name | classification | dtype" lines │
    │ 2. Build _INTENT_PROMPT with domain, question, columns, schema       │
    │ 3. Call llm.structured_completion(prompt, AnalysisSpec, …)           │
    │ 4. Return the AnalysisSpec as-is (no mutation)                       │
    └─────────────────────────────────────────────────────────────────────┘

AnalysisSpec fields (from PRD §4 / schemas.py):
    dimensions          list[str]   — grouping columns
    measures            list[str]   — numeric columns to aggregate
    filters             list | None
    time_range          dict | None
    suggested_chart_types list[str] — subset of [line, bar, table, scatter, pie]
    restatement         str         — domain-rephrased question
    confidence          float       — 0.0–1.0
"""

from __future__ import annotations

import asyncio
import sys
import traceback
from dataclasses import dataclass, field
from typing import Any, Optional


# ─────────────────────────────────────────────────────────────────────────────
# Stand-ins for app.models.schemas
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ColumnProfile:
    name: str
    dtype: str                      # "float" | "int64" | "object" | "text" | "categorical" | …
    null_count: int = 0
    distinct_count: int = 10
    avg_length: Optional[float] = None
    classification: str = "numeric" # "numeric" | "textual" | "ambiguous"


@dataclass
class AnalysisSpec:
    dimensions: list[str]
    measures: list[str]
    suggested_chart_types: list[str] = field(default_factory=list)
    restatement: str = ""
    confidence: float = 1.0
    filters: Optional[list] = None
    time_range: Optional[dict] = None

    # Stub for Pydantic's model_json_schema() — returns a plain dict so the
    # prompt-formatting code has something to embed.
    @classmethod
    def model_json_schema(cls) -> dict:
        return {
            "type": "object",
            "properties": {
                "dimensions":            {"type": "array",  "items": {"type": "string"}},
                "measures":              {"type": "array",  "items": {"type": "string"}},
                "suggested_chart_types": {"type": "array",  "items": {"type": "string"}},
                "restatement":           {"type": "string"},
                "confidence":            {"type": "number", "minimum": 0.0, "maximum": 1.0},
                "filters":               {"type": "array"},
                "time_range":            {"type": "object"},
            },
            "required": ["dimensions", "measures", "suggested_chart_types",
                         "restatement", "confidence"],
        }


# ─────────────────────────────────────────────────────────────────────────────
# _INTENT_PROMPT — verbatim copy from intent.py
# ─────────────────────────────────────────────────────────────────────────────

_INTENT_PROMPT = """
You are an intent parser for a {domain} analytics platform.

The user's question is:
"{question}"

Available columns (name | classification | dtype):
{columns}

Parse the intent into a structured analysis spec. Return ONLY valid JSON matching this schema:
{schema}

Rules:
- dimensions: grouping columns (categorical, date/time, or textual classification columns)
- measures: numeric columns to aggregate
- suggested_chart_types: 1-3 chart types from [line, bar, table, scatter, pie]
- restatement: rephrase the question in domain-specific terms to confirm understanding
- confidence: float 0.0–1.0 reflecting how clearly the question maps to available columns
""".strip()


# ─────────────────────────────────────────────────────────────────────────────
# Mock LLM
# ─────────────────────────────────────────────────────────────────────────────

class MockLLM:
    """
    Controls exactly what structured_completion returns.

    Attributes:
        spec_to_return      The AnalysisSpec instance the mock returns.
        last_prompt         The full prompt string passed in on the last call.
        last_model_class    The model class argument passed in.
        last_agent_name     The agent_name kwarg.
        call_count          How many times structured_completion was called.
        raise_on_call       If set, structured_completion raises this exception.
    """

    def __init__(self, spec: Optional[AnalysisSpec] = None) -> None:
        self.spec_to_return: AnalysisSpec = spec or _default_spec()
        self.last_prompt: str = ""
        self.last_model_class: Any = None
        self.last_agent_name: str = ""
        self.call_count: int = 0
        self.raise_on_call: Optional[Exception] = None

    async def structured_completion(
        self,
        prompt: str,
        model_class,
        *,
        agent_name: str = "",
    ) -> Any:
        self.last_prompt = prompt
        self.last_model_class = model_class
        self.last_agent_name = agent_name
        self.call_count += 1
        if self.raise_on_call:
            raise self.raise_on_call
        return self.spec_to_return


# ─────────────────────────────────────────────────────────────────────────────
# Agent under test — verbatim port of intent.py (app imports replaced)
# ─────────────────────────────────────────────────────────────────────────────

import logging
_log = logging.getLogger("intent_agent_test")


class IntentAgent:
    """Verbatim port of the real agent — only app-level imports are replaced."""

    def __init__(self, llm=None) -> None:
        self.llm = llm

    async def parse(
        self,
        question: str,
        profiles: list[ColumnProfile],
        domain: str,
    ) -> AnalysisSpec:
        col_lines = "\n".join(
            f"{p.name} | {p.classification} | {p.dtype}" for p in profiles
        )

        prompt = _INTENT_PROMPT.format(
            domain=domain,
            question=question,
            columns=col_lines,
            schema=AnalysisSpec.model_json_schema(),
        )

        spec = await self.llm.structured_completion(prompt, AnalysisSpec, agent_name="intent")
        _log.info(
            "intent_parsed domain=%s confidence=%s restatement=%s",
            domain, spec.confidence, spec.restatement,
        )
        return spec


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def run(coro):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


def _default_spec(**overrides) -> AnalysisSpec:
    base = dict(
        dimensions=["region"],
        measures=["revenue"],
        suggested_chart_types=["bar"],
        restatement="Show total revenue by region",
        confidence=0.9,
        filters=None,
        time_range=None,
    )
    base.update(overrides)
    return AnalysisSpec(**base)


def make_agent(spec: Optional[AnalysisSpec] = None) -> tuple[IntentAgent, MockLLM]:
    llm = MockLLM(spec or _default_spec())
    return IntentAgent(llm=llm), llm


def make_col(
    name: str,
    classification: str = "numeric",
    dtype: str = "float64",
) -> ColumnProfile:
    return ColumnProfile(name=name, dtype=dtype, classification=classification)


def make_numeric_col(name: str) -> ColumnProfile:
    return make_col(name, "numeric", "float64")


def make_textual_col(name: str) -> ColumnProfile:
    return make_col(name, "textual", "text")


def make_categorical_col(name: str) -> ColumnProfile:
    return make_col(name, "numeric", "categorical")


# ─────────────────────────────────────────────────────────────────────────────
# Lightweight runner
# ─────────────────────────────────────────────────────────────────────────────

class _Results:
    def __init__(self) -> None:
        self.passed: list[str] = []
        self.failed: list[tuple[str, str]] = []

    def record(self, name: str, exc: Optional[Exception]) -> None:
        if exc is None:
            self.passed.append(name)
        else:
            self.failed.append((name, traceback.format_exc()))

    def print_summary(self) -> None:
        total = len(self.passed) + len(self.failed)
        w = 72
        print("=" * w)
        print("  IntentAgent.parse() — test results")
        print("=" * w)
        if self.failed:
            print(f"\n  ✗  FAILURES ({len(self.failed)}/{total}):\n")
            for name, tb in self.failed:
                print(f"  ── {name}")
                for line in tb.strip().splitlines():
                    print(f"     {line}")
                print()
        print(f"\n  Passed : {len(self.passed):>3}")
        print(f"  Failed : {len(self.failed):>3}")
        print(f"  Total  : {total:>3}")
        status = "✔ ALL TESTS PASSED" if not self.failed else "✗ SOME TESTS FAILED"
        print(f"\n  STATUS: {status}")
        print("=" * w)


def _run(results: _Results, name: str, fn) -> None:
    try:
        fn()
        results.record(name, None)
        print(f"  ✔  {name}")
    except Exception as exc:
        results.record(name, exc)
        print(f"  ✗  {name}  →  {exc}")


# ═════════════════════════════════════════════════════════════════════════════
# TEST CLASSES
# ═════════════════════════════════════════════════════════════════════════════


# ─────────────────────────────────────────────────────────────────────────────
# Return-type & identity
# ─────────────────────────────────────────────────────────────────────────────

class TestReturnType:

    def test_returns_analysis_spec(self):
        agent, _ = make_agent()
        result = run(agent.parse("show revenue by region", [], "finance"))
        assert isinstance(result, AnalysisSpec)

    def test_returns_exact_spec_from_llm(self):
        """parse() must return the AnalysisSpec from the LLM without modification."""
        spec = _default_spec(dimensions=["ward"], measures=["los"], confidence=0.77)
        agent, _ = make_agent(spec)
        result = run(agent.parse("avg length of stay by ward", [], "healthcare"))
        assert result is spec

    def test_dimensions_field_is_list(self):
        agent, _ = make_agent()
        result = run(agent.parse("q", [], "finance"))
        assert isinstance(result.dimensions, list)

    def test_measures_field_is_list(self):
        agent, _ = make_agent()
        result = run(agent.parse("q", [], "finance"))
        assert isinstance(result.measures, list)

    def test_suggested_chart_types_is_list(self):
        agent, _ = make_agent()
        result = run(agent.parse("q", [], "finance"))
        assert isinstance(result.suggested_chart_types, list)

    def test_restatement_is_str(self):
        agent, _ = make_agent()
        result = run(agent.parse("q", [], "finance"))
        assert isinstance(result.restatement, str)

    def test_confidence_is_float(self):
        agent, _ = make_agent()
        result = run(agent.parse("q", [], "finance"))
        assert isinstance(result.confidence, float)

    def test_spec_not_mutated_after_return(self):
        """The spec the LLM produced must be identical after parse() returns."""
        spec = _default_spec(dimensions=["channel"], measures=["cpa"])
        agent, _ = make_agent(spec)
        result = run(agent.parse("q", [], "marketing"))
        assert result.dimensions == ["channel"]
        assert result.measures == ["cpa"]


# ─────────────────────────────────────────────────────────────────────────────
# AnalysisSpec field values — dimensions
# ─────────────────────────────────────────────────────────────────────────────

class TestSpecDimensions:

    def test_single_dimension_preserved(self):
        spec = _default_spec(dimensions=["region"])
        agent, _ = make_agent(spec)
        result = run(agent.parse("revenue by region", [], "finance"))
        assert result.dimensions == ["region"]

    def test_multiple_dimensions_preserved(self):
        spec = _default_spec(dimensions=["region", "channel", "product"])
        agent, _ = make_agent(spec)
        result = run(agent.parse("q", [], "retail"))
        assert result.dimensions == ["region", "channel", "product"]

    def test_empty_dimensions_preserved(self):
        spec = _default_spec(dimensions=[])
        agent, _ = make_agent(spec)
        result = run(agent.parse("what is total revenue?", [], "finance"))
        assert result.dimensions == []

    def test_dimension_column_name_is_exact_string(self):
        spec = _default_spec(dimensions=["admission_date"])
        agent, _ = make_agent(spec)
        result = run(agent.parse("q", [], "healthcare"))
        assert "admission_date" in result.dimensions

    def test_dimensions_order_preserved(self):
        ordered = ["year", "quarter", "month", "week"]
        spec = _default_spec(dimensions=ordered)
        agent, _ = make_agent(spec)
        result = run(agent.parse("q", [], "finance"))
        assert result.dimensions == ordered


# ─────────────────────────────────────────────────────────────────────────────
# AnalysisSpec field values — measures
# ─────────────────────────────────────────────────────────────────────────────

class TestSpecMeasures:

    def test_single_measure_preserved(self):
        spec = _default_spec(measures=["revenue"])
        agent, _ = make_agent(spec)
        result = run(agent.parse("q", [], "finance"))
        assert result.measures == ["revenue"]

    def test_multiple_measures_preserved(self):
        spec = _default_spec(measures=["revenue", "units_sold", "gross_margin"])
        agent, _ = make_agent(spec)
        result = run(agent.parse("q", [], "retail"))
        assert result.measures == ["revenue", "units_sold", "gross_margin"]

    def test_empty_measures_preserved(self):
        spec = _default_spec(measures=[])
        agent, _ = make_agent(spec)
        result = run(agent.parse("list all regions", [], "finance"))
        assert result.measures == []

    def test_measures_order_preserved(self):
        ordered = ["mrr", "arr", "churn_rate", "cac"]
        spec = _default_spec(measures=ordered)
        agent, _ = make_agent(spec)
        result = run(agent.parse("q", [], "finance"))
        assert result.measures == ordered


# ─────────────────────────────────────────────────────────────────────────────
# AnalysisSpec field values — suggested_chart_types
# ─────────────────────────────────────────────────────────────────────────────

class TestSpecChartTypes:

    VALID_CHART_TYPES = {"line", "bar", "table", "scatter", "pie"}

    def test_single_chart_type_bar(self):
        spec = _default_spec(suggested_chart_types=["bar"])
        agent, _ = make_agent(spec)
        result = run(agent.parse("q", [], "finance"))
        assert result.suggested_chart_types == ["bar"]

    def test_single_chart_type_line(self):
        spec = _default_spec(suggested_chart_types=["line"])
        agent, _ = make_agent(spec)
        result = run(agent.parse("q", [], "finance"))
        assert result.suggested_chart_types == ["line"]

    def test_multiple_chart_types_preserved(self):
        spec = _default_spec(suggested_chart_types=["line", "bar", "table"])
        agent, _ = make_agent(spec)
        result = run(agent.parse("q", [], "finance"))
        assert result.suggested_chart_types == ["line", "bar", "table"]

    def test_all_valid_chart_types_accepted(self):
        for ct in self.VALID_CHART_TYPES:
            spec = _default_spec(suggested_chart_types=[ct])
            agent, _ = make_agent(spec)
            result = run(agent.parse("q", [], "finance"))
            assert ct in result.suggested_chart_types

    def test_chart_types_list_at_most_three(self):
        """PRD constrains suggested_chart_types to 1–3 items."""
        spec = _default_spec(suggested_chart_types=["bar", "line", "table"])
        agent, _ = make_agent(spec)
        result = run(agent.parse("q", [], "finance"))
        assert len(result.suggested_chart_types) <= 3

    def test_empty_chart_types_preserved(self):
        spec = _default_spec(suggested_chart_types=[])
        agent, _ = make_agent(spec)
        result = run(agent.parse("q", [], "finance"))
        assert result.suggested_chart_types == []


# ─────────────────────────────────────────────────────────────────────────────
# AnalysisSpec field values — confidence
# ─────────────────────────────────────────────────────────────────────────────

class TestSpecConfidence:

    def test_confidence_high_preserved(self):
        spec = _default_spec(confidence=0.95)
        agent, _ = make_agent(spec)
        result = run(agent.parse("q", [], "finance"))
        assert result.confidence == 0.95

    def test_confidence_low_preserved(self):
        spec = _default_spec(confidence=0.2)
        agent, _ = make_agent(spec)
        result = run(agent.parse("q", [], "finance"))
        assert result.confidence == 0.2

    def test_confidence_zero_preserved(self):
        spec = _default_spec(confidence=0.0)
        agent, _ = make_agent(spec)
        result = run(agent.parse("q", [], "finance"))
        assert result.confidence == 0.0

    def test_confidence_one_preserved(self):
        spec = _default_spec(confidence=1.0)
        agent, _ = make_agent(spec)
        result = run(agent.parse("q", [], "finance"))
        assert result.confidence == 1.0

    def test_confidence_value_is_exact(self):
        spec = _default_spec(confidence=0.732)
        agent, _ = make_agent(spec)
        result = run(agent.parse("q", [], "finance"))
        assert abs(result.confidence - 0.732) < 1e-9


# ─────────────────────────────────────────────────────────────────────────────
# AnalysisSpec field values — restatement
# ─────────────────────────────────────────────────────────────────────────────

class TestSpecRestatement:

    def test_restatement_preserved_verbatim(self):
        restatement = "Show total monthly recurring revenue grouped by customer segment"
        spec = _default_spec(restatement=restatement)
        agent, _ = make_agent(spec)
        result = run(agent.parse("q", [], "finance"))
        assert result.restatement == restatement

    def test_empty_restatement_preserved(self):
        spec = _default_spec(restatement="")
        agent, _ = make_agent(spec)
        result = run(agent.parse("q", [], "finance"))
        assert result.restatement == ""

    def test_restatement_with_domain_vocabulary(self):
        restatement = "Show MRR churn rate across cohorts for the last 6 months"
        spec = _default_spec(restatement=restatement)
        agent, _ = make_agent(spec)
        result = run(agent.parse("what is our churn?", [], "finance"))
        assert result.restatement == restatement

    def test_restatement_is_not_the_original_question(self):
        """By design the restatement should be the LLM's rephrasing, not the raw input."""
        question = "whats our numbers"
        restatement = "Show total revenue and gross margin aggregated by region"
        spec = _default_spec(restatement=restatement)
        agent, _ = make_agent(spec)
        result = run(agent.parse(question, [], "finance"))
        assert result.restatement != question


# ─────────────────────────────────────────────────────────────────────────────
# AnalysisSpec field values — filters & time_range
# ─────────────────────────────────────────────────────────────────────────────

class TestSpecOptionalFields:

    def test_none_filters_preserved(self):
        spec = _default_spec(filters=None)
        agent, _ = make_agent(spec)
        result = run(agent.parse("q", [], "finance"))
        assert result.filters is None

    def test_filters_list_preserved(self):
        filters = [{"col": "region", "op": "=", "val": "APAC"}]
        spec = _default_spec(filters=filters)
        agent, _ = make_agent(spec)
        result = run(agent.parse("q", [], "finance"))
        assert result.filters == filters

    def test_multiple_filters_preserved(self):
        filters = [
            {"col": "region", "op": "=",  "val": "APAC"},
            {"col": "year",   "op": ">",  "val": 2022},
            {"col": "status", "op": "in", "val": ["active", "trial"]},
        ]
        spec = _default_spec(filters=filters)
        agent, _ = make_agent(spec)
        result = run(agent.parse("q", [], "finance"))
        assert result.filters == filters

    def test_none_time_range_preserved(self):
        spec = _default_spec(time_range=None)
        agent, _ = make_agent(spec)
        result = run(agent.parse("q", [], "finance"))
        assert result.time_range is None

    def test_time_range_dict_preserved(self):
        tr = {"start": "2024-01-01", "end": "2024-12-31"}
        spec = _default_spec(time_range=tr)
        agent, _ = make_agent(spec)
        result = run(agent.parse("q", [], "finance"))
        assert result.time_range == tr


# ─────────────────────────────────────────────────────────────────────────────
# LLM interaction — call mechanics
# ─────────────────────────────────────────────────────────────────────────────

class TestLLMCallMechanics:

    def test_llm_called_exactly_once(self):
        agent, llm = make_agent()
        run(agent.parse("show revenue by region", [], "finance"))
        assert llm.call_count == 1

    def test_llm_called_with_analysis_spec_class(self):
        agent, llm = make_agent()
        run(agent.parse("q", [], "finance"))
        assert llm.last_model_class is AnalysisSpec

    def test_llm_called_with_agent_name_intent(self):
        agent, llm = make_agent()
        run(agent.parse("q", [], "finance"))
        assert llm.last_agent_name == "intent"

    def test_llm_receives_a_non_empty_prompt(self):
        agent, llm = make_agent()
        run(agent.parse("show revenue by region", [], "finance"))
        assert len(llm.last_prompt.strip()) > 0

    def test_second_call_updates_prompt(self):
        """Each parse() call must build a fresh prompt, not reuse the previous one."""
        agent, llm = make_agent()
        run(agent.parse("question one", [], "finance"))
        first_prompt = llm.last_prompt
        run(agent.parse("question two", [], "finance"))
        assert llm.last_prompt != first_prompt

    def test_llm_exception_propagates(self):
        """parse() does not swallow LLM errors — the supervisor handles retries."""
        agent, llm = make_agent()
        llm.raise_on_call = RuntimeError("LLM rate limit exceeded")
        try:
            run(agent.parse("q", [], "finance"))
            raise AssertionError("Expected RuntimeError to propagate")
        except RuntimeError as exc:
            assert "rate limit" in str(exc)

    def test_llm_timeout_propagates(self):
        agent, llm = make_agent()
        llm.raise_on_call = TimeoutError("LLM response timed out")
        try:
            run(agent.parse("q", [], "finance"))
            raise AssertionError("Expected TimeoutError to propagate")
        except TimeoutError:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# Prompt construction — question
# ─────────────────────────────────────────────────────────────────────────────

class TestPromptQuestion:

    def test_question_appears_in_prompt(self):
        agent, llm = make_agent()
        run(agent.parse("show me revenue by region", [], "finance"))
        assert "show me revenue by region" in llm.last_prompt

    def test_question_with_special_characters(self):
        question = "what's the MoM Δ in ARR (%)?"
        agent, llm = make_agent()
        run(agent.parse(question, [], "finance"))
        assert question in llm.last_prompt

    def test_empty_question_appears_as_empty_in_prompt(self):
        agent, llm = make_agent()
        run(agent.parse("", [], "finance"))
        # The prompt template wraps the question in quotes; empty string is valid
        assert '""' in llm.last_prompt

    def test_multiline_question_appears_in_prompt(self):
        question = "compare revenue\nby region\nand channel"
        agent, llm = make_agent()
        run(agent.parse(question, [], "finance"))
        assert question in llm.last_prompt

    def test_long_question_fully_included(self):
        question = "what is the quarter-over-quarter growth rate of gross margin " \
                   "segmented by customer tier and acquisition channel for 2023 vs 2024?"
        agent, llm = make_agent()
        run(agent.parse(question, [], "finance"))
        assert question in llm.last_prompt

    def test_different_questions_produce_different_prompts(self):
        agent_a, llm_a = make_agent()
        agent_b, llm_b = make_agent()
        run(agent_a.parse("revenue by region", [], "finance"))
        run(agent_b.parse("churn rate by cohort", [], "finance"))
        assert llm_a.last_prompt != llm_b.last_prompt


# ─────────────────────────────────────────────────────────────────────────────
# Prompt construction — domain
# ─────────────────────────────────────────────────────────────────────────────

class TestPromptDomain:

    DOMAINS = ["finance", "healthcare", "retail", "marketing", "operations", "other"]

    def test_domain_appears_in_prompt(self):
        for domain in self.DOMAINS:
            agent, llm = make_agent()
            run(agent.parse("q", [], domain))
            assert domain in llm.last_prompt, f"Domain '{domain}' missing from prompt"

    def test_different_domains_produce_different_prompts(self):
        agent_a, llm_a = make_agent()
        agent_b, llm_b = make_agent()
        run(agent_a.parse("q", [], "finance"))
        run(agent_b.parse("q", [], "healthcare"))
        assert llm_a.last_prompt != llm_b.last_prompt

    def test_finance_domain_in_prompt(self):
        agent, llm = make_agent()
        run(agent.parse("q", [], "finance"))
        assert "finance" in llm.last_prompt

    def test_healthcare_domain_in_prompt(self):
        agent, llm = make_agent()
        run(agent.parse("q", [], "healthcare"))
        assert "healthcare" in llm.last_prompt

    def test_retail_domain_in_prompt(self):
        agent, llm = make_agent()
        run(agent.parse("q", [], "retail"))
        assert "retail" in llm.last_prompt


# ─────────────────────────────────────────────────────────────────────────────
# Prompt construction — column profiles
# ─────────────────────────────────────────────────────────────────────────────

class TestPromptColumnProfiles:

    def test_column_name_appears_in_prompt(self):
        cols = [make_numeric_col("revenue")]
        agent, llm = make_agent()
        run(agent.parse("q", cols, "finance"))
        assert "revenue" in llm.last_prompt

    def test_column_classification_appears_in_prompt(self):
        cols = [make_textual_col("description")]
        agent, llm = make_agent()
        run(agent.parse("q", cols, "finance"))
        assert "textual" in llm.last_prompt

    def test_column_dtype_appears_in_prompt(self):
        cols = [make_col("price", "numeric", "float64")]
        agent, llm = make_agent()
        run(agent.parse("q", cols, "finance"))
        assert "float64" in llm.last_prompt

    def test_column_formatted_as_pipe_delimited_line(self):
        """Format must be: name | classification | dtype"""
        cols = [make_col("revenue", "numeric", "float64")]
        agent, llm = make_agent()
        run(agent.parse("q", cols, "finance"))
        assert "revenue | numeric | float64" in llm.last_prompt

    def test_multiple_columns_all_appear_in_prompt(self):
        cols = [
            make_col("region",  "numeric",  "categorical"),
            make_col("revenue", "numeric",  "float64"),
            make_col("notes",   "textual",  "text"),
        ]
        agent, llm = make_agent()
        run(agent.parse("q", cols, "finance"))
        assert "region"  in llm.last_prompt
        assert "revenue" in llm.last_prompt
        assert "notes"   in llm.last_prompt

    def test_multiple_columns_each_on_own_line(self):
        cols = [make_col("a", "numeric", "float64"), make_col("b", "textual", "text")]
        agent, llm = make_agent()
        run(agent.parse("q", cols, "finance"))
        # Both pipe-delimited lines must appear in the prompt
        assert "a | numeric | float64" in llm.last_prompt
        assert "b | textual | text"    in llm.last_prompt

    def test_no_columns_produces_empty_column_section(self):
        agent, llm = make_agent()
        run(agent.parse("q", [], "finance"))
        # Empty columns block = the columns format string is empty string
        # Verify the prompt still contains the surrounding template text
        assert "Available columns (name | classification | dtype):" in llm.last_prompt

    def test_column_order_preserved_in_prompt(self):
        cols = [
            make_col("z_col", "numeric", "float64"),
            make_col("a_col", "textual", "text"),
            make_col("m_col", "numeric", "categorical"),
        ]
        agent, llm = make_agent()
        run(agent.parse("q", cols, "finance"))
        z_pos = llm.last_prompt.index("z_col")
        a_pos = llm.last_prompt.index("a_col")
        m_pos = llm.last_prompt.index("m_col")
        assert z_pos < a_pos < m_pos

    def test_large_column_set_all_present(self):
        cols = [make_col(f"col_{i}", "numeric", "float64") for i in range(30)]
        agent, llm = make_agent()
        run(agent.parse("q", cols, "finance"))
        for i in range(30):
            assert f"col_{i}" in llm.last_prompt

    def test_numeric_classification_in_prompt(self):
        cols = [make_col("amount", "numeric", "float64")]
        agent, llm = make_agent()
        run(agent.parse("q", cols, "finance"))
        assert "numeric" in llm.last_prompt

    def test_ambiguous_classification_in_prompt(self):
        cols = [make_col("code", "ambiguous", "text")]
        agent, llm = make_agent()
        run(agent.parse("q", cols, "finance"))
        assert "ambiguous" in llm.last_prompt

    def test_schema_embedded_in_prompt(self):
        """AnalysisSpec.model_json_schema() output must appear in the prompt."""
        agent, llm = make_agent()
        run(agent.parse("q", [], "finance"))
        # The schema is a dict; some of its keys should appear in the prompt
        assert "dimensions" in llm.last_prompt
        assert "measures"   in llm.last_prompt


# ─────────────────────────────────────────────────────────────────────────────
# Domain-specific column and spec combinations
# ─────────────────────────────────────────────────────────────────────────────

class TestDomainSpecificCombinations:

    def test_finance_revenue_by_region(self):
        cols = [
            make_categorical_col("region"),
            make_numeric_col("revenue"),
            make_numeric_col("gross_margin"),
        ]
        spec = _default_spec(
            dimensions=["region"],
            measures=["revenue"],
            suggested_chart_types=["bar"],
            restatement="Show total revenue grouped by region",
            confidence=0.95,
        )
        agent, _ = make_agent(spec)
        result = run(agent.parse("show me revenue by region", cols, "finance"))
        assert result.dimensions == ["region"]
        assert result.measures == ["revenue"]
        assert "bar" in result.suggested_chart_types

    def test_healthcare_los_by_ward(self):
        cols = [
            make_categorical_col("ward"),
            make_numeric_col("length_of_stay"),
            make_numeric_col("readmission_rate"),
        ]
        spec = _default_spec(
            dimensions=["ward"],
            measures=["length_of_stay"],
            suggested_chart_types=["bar", "table"],
            restatement="Show average length of stay by ward",
            confidence=0.88,
        )
        agent, _ = make_agent(spec)
        result = run(agent.parse("avg length of stay by ward", cols, "healthcare"))
        assert result.dimensions == ["ward"]
        assert result.measures == ["length_of_stay"]

    def test_retail_sales_by_sku_and_channel(self):
        cols = [
            make_categorical_col("sku"),
            make_categorical_col("channel"),
            make_numeric_col("units_sold"),
            make_numeric_col("margin"),
        ]
        spec = _default_spec(
            dimensions=["sku", "channel"],
            measures=["units_sold", "margin"],
            suggested_chart_types=["table"],
            confidence=0.80,
        )
        agent, _ = make_agent(spec)
        result = run(agent.parse("top SKUs by channel", cols, "retail"))
        assert "sku" in result.dimensions
        assert "channel" in result.dimensions
        assert "units_sold" in result.measures

    def test_marketing_ctr_by_campaign(self):
        cols = [
            make_categorical_col("campaign"),
            make_numeric_col("ctr"),
            make_numeric_col("cpa"),
        ]
        spec = _default_spec(
            dimensions=["campaign"],
            measures=["ctr", "cpa"],
            suggested_chart_types=["bar"],
            confidence=0.91,
        )
        agent, _ = make_agent(spec)
        result = run(agent.parse("which campaigns have best CTR?", cols, "marketing"))
        assert "campaign" in result.dimensions
        assert "ctr" in result.measures

    def test_operations_throughput_by_line(self):
        cols = [
            make_categorical_col("production_line"),
            make_numeric_col("throughput"),
            make_numeric_col("defect_rate"),
        ]
        spec = _default_spec(
            dimensions=["production_line"],
            measures=["throughput"],
            suggested_chart_types=["line", "bar"],
            confidence=0.85,
        )
        agent, _ = make_agent(spec)
        result = run(agent.parse("throughput per production line", cols, "operations"))
        assert "production_line" in result.dimensions
        assert "throughput" in result.measures

    def test_low_confidence_ambiguous_question(self):
        """Vague questions should yield low confidence from the LLM."""
        spec = _default_spec(
            dimensions=[],
            measures=[],
            suggested_chart_types=["table"],
            restatement="Question is too ambiguous to map to available columns",
            confidence=0.15,
        )
        agent, _ = make_agent(spec)
        result = run(agent.parse("what about the thing?", [], "other"))
        assert result.confidence < 0.5
        assert result.dimensions == []

    def test_time_series_question_suggests_line_chart(self):
        cols = [
            make_col("date", "numeric", "date"),
            make_numeric_col("revenue"),
        ]
        spec = _default_spec(
            dimensions=["date"],
            measures=["revenue"],
            suggested_chart_types=["line"],
            confidence=0.93,
        )
        agent, _ = make_agent(spec)
        result = run(agent.parse("revenue over time", cols, "finance"))
        assert "line" in result.suggested_chart_types


# ─────────────────────────────────────────────────────────────────────────────
# Edge cases & robustness
# ─────────────────────────────────────────────────────────────────────────────

class TestEdgeCases:

    def test_empty_question_does_not_raise(self):
        agent, _ = make_agent()
        try:
            run(agent.parse("", [], "finance"))
        except Exception as exc:
            raise AssertionError(f"parse() raised on empty question: {exc}") from exc

    def test_very_long_question_does_not_raise(self):
        question = "show me " + "revenue " * 500
        agent, _ = make_agent()
        try:
            run(agent.parse(question, [], "finance"))
        except Exception as exc:
            raise AssertionError(f"parse() raised on long question: {exc}") from exc

    def test_zero_profiles_does_not_raise(self):
        agent, _ = make_agent()
        result = run(agent.parse("total revenue", [], "finance"))
        assert isinstance(result, AnalysisSpec)

    def test_single_profile_does_not_raise(self):
        agent, _ = make_agent()
        result = run(agent.parse("q", [make_numeric_col("revenue")], "finance"))
        assert isinstance(result, AnalysisSpec)

    def test_50_profiles_all_in_prompt(self):
        cols = [make_col(f"col_{i}", "numeric", "float64") for i in range(50)]
        agent, llm = make_agent()
        run(agent.parse("q", cols, "finance"))
        for i in range(50):
            assert f"col_{i}" in llm.last_prompt

    def test_column_with_spaces_in_name(self):
        cols = [make_col("total revenue", "numeric", "float64")]
        agent, llm = make_agent()
        run(agent.parse("q", cols, "finance"))
        assert "total revenue" in llm.last_prompt

    def test_column_with_unicode_name(self):
        cols = [make_col("収益", "numeric", "float64")]
        agent, llm = make_agent()
        run(agent.parse("q", cols, "finance"))
        assert "収益" in llm.last_prompt

    def test_spec_with_all_chart_types_returned_intact(self):
        all_types = ["line", "bar", "table"]
        spec = _default_spec(suggested_chart_types=all_types)
        agent, _ = make_agent(spec)
        result = run(agent.parse("q", [], "finance"))
        assert result.suggested_chart_types == all_types

    def test_concurrent_independent_calls_do_not_share_state(self):
        """Two agents with separate LLMs must not interfere."""
        spec_a = _default_spec(dimensions=["region"], measures=["revenue"])
        spec_b = _default_spec(dimensions=["ward"],   measures=["los"])
        agent_a, llm_a = make_agent(spec_a)
        agent_b, llm_b = make_agent(spec_b)
        r_a = run(agent_a.parse("revenue by region", [], "finance"))
        r_b = run(agent_b.parse("los by ward",       [], "healthcare"))
        assert r_a.dimensions == ["region"]
        assert r_b.dimensions == ["ward"]
        assert llm_a.last_prompt != llm_b.last_prompt

    def test_parse_called_twice_on_same_agent_updates_result(self):
        """Calling parse() twice on the same agent must return the current LLM output."""
        llm = MockLLM(_default_spec(dimensions=["region"]))
        agent = IntentAgent(llm=llm)
        run(agent.parse("first question", [], "finance"))
        llm.spec_to_return = _default_spec(dimensions=["ward"])
        result = run(agent.parse("second question", [], "healthcare"))
        assert result.dimensions == ["ward"]


# ═════════════════════════════════════════════════════════════════════════════
# Runner
# ═════════════════════════════════════════════════════════════════════════════

def _collect_all_test_classes():
    return [
        TestReturnType,
        TestSpecDimensions,
        TestSpecMeasures,
        TestSpecChartTypes,
        TestSpecConfidence,
        TestSpecRestatement,
        TestSpecOptionalFields,
        TestLLMCallMechanics,
        TestPromptQuestion,
        TestPromptDomain,
        TestPromptColumnProfiles,
        TestDomainSpecificCombinations,
        TestEdgeCases,
    ]


def run_all_tests() -> _Results:
    results = _Results()
    for cls in _collect_all_test_classes():
        instance = cls()
        for method_name in sorted(m for m in dir(instance) if m.startswith("test_")):
            label = f"{cls.__name__}.{method_name}"
            _run(results, label, getattr(instance, method_name))
    return results


if __name__ == "__main__":
    print()
    results = run_all_tests()
    results.print_summary()
    sys.exit(1 if results.failed else 0)