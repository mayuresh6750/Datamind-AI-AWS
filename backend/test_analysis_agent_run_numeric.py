"""
Unit tests for AnalysisAgent.run_numeric()

Source agent : backend/app/agents/analysis.py

Run with:
    pytest  test_analysis_agent.py -v
    python  test_analysis_agent.py          # live results, no pytest needed

Fully independent — no real DB, no LLM, no Supabase, no app imports.
Every external dependency is replaced by an in-process stub:

    MockLLM       — controls exactly what SQL the "LLM" emits
    MockDB        — AsyncSession stand-in; captures every SQL string sent to it,
                    returns configurable rows, and can be set to raise on execute()
    MockResult    — mimics SQLAlchemy AsyncResult (keys() + fetchall())

Contract under test  (AnalysisAgent.run_numeric):
    ┌─────────────────────────────────────────────────────────────────┐
    │ 1. Build a prompt from spec, table_name, domain                 │
    │ 2. Call llm.structured_completion → SQLOutput(sql=…)            │
    │ 3. Strip trailing semicolon                                     │
    │ 4. BLOCK anything that does not start with SELECT (case-insens) │
    │ 5. Execute the SQL against the AsyncSession                     │
    │ 6. Return list[dict] — one dict per row, keyed by column name   │
    │ 7. On DB exception → log and return []                          │
    └─────────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import asyncio
import json
import statistics
import sys
import traceback
from dataclasses import dataclass, field
from typing import Any, Optional
from unittest.mock import AsyncMock, MagicMock, patch


# ─────────────────────────────────────────────────────────────────────────────
# Stand-ins for app.models.schemas
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class AnalysisSpec:
    dimensions: list[str]
    measures: list[str]
    filters: Optional[list] = None
    time_range: Optional[dict] = None
    suggested_chart_types: list[str] = field(default_factory=list)
    restatement: str = ""
    confidence: float = 1.0


# ─────────────────────────────────────────────────────────────────────────────
# Stand-in for pydantic.BaseModel  (SQLOutput only needs .sql)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class SQLOutput:
    sql: str


# ─────────────────────────────────────────────────────────────────────────────
# Mock LLM
# ─────────────────────────────────────────────────────────────────────────────

class MockLLM:
    """
    Controls exactly what SQL structured_completion returns.

    Usage:
        llm = MockLLM("SELECT id, SUM(revenue) FROM sales GROUP BY id")
        # llm.last_prompt  — the full prompt string passed in
        # llm.call_count   — how many times structured_completion was called
    """

    def __init__(self, sql_to_return: str = "SELECT 1") -> None:
        self.sql_to_return = sql_to_return
        self.last_prompt: str = ""
        self.call_count: int = 0
        self.raise_on_call: Optional[Exception] = None

    async def structured_completion(self, prompt: str, model_class, *, agent_name: str = "") -> Any:
        self.last_prompt = prompt
        self.call_count += 1
        if self.raise_on_call:
            raise self.raise_on_call
        return SQLOutput(sql=self.sql_to_return)


# ─────────────────────────────────────────────────────────────────────────────
# Mock DB (AsyncSession)
# ─────────────────────────────────────────────────────────────────────────────

class MockResult:
    """
    Mimics the object returned by AsyncSession.execute().
    keys()     → list of column names
    fetchall() → list of row tuples
    """

    def __init__(self, columns: list[str], data: list[tuple]) -> None:
        self._columns = columns
        self._data = data

    def keys(self) -> list[str]:
        return self._columns

    def fetchall(self) -> list[tuple]:
        return self._data


class MockDB:
    """
    Minimal AsyncSession stand-in.

    Attributes:
        executed_sqls  — list of raw SQL strings passed to execute()
        raise_on_execute — if set, execute() raises this exception
        result_columns — column names the mock result exposes
        result_rows    — row tuples the mock result returns
    """

    def __init__(
        self,
        columns: Optional[list[str]] = None,
        rows: Optional[list[tuple]] = None,
    ) -> None:
        self.result_columns: list[str] = columns or []
        self.result_rows: list[tuple] = rows or []
        self.executed_sqls: list[str] = []
        self.raise_on_execute: Optional[Exception] = None

    async def execute(self, stmt, *args, **kwargs) -> MockResult:
        # SQLAlchemy wraps raw SQL in text(); extract the string for inspection
        raw = str(stmt) if not hasattr(stmt, "text") else stmt.text
        self.executed_sqls.append(raw)
        if self.raise_on_execute:
            raise self.raise_on_execute
        return MockResult(self.result_columns, self.result_rows)


# ─────────────────────────────────────────────────────────────────────────────
# Agent under test — verbatim copy of analysis.py run_numeric()
# with minimal shims replacing the app-specific imports
# ─────────────────────────────────────────────────────────────────────────────

import logging

_log = logging.getLogger("analysis_agent_test")

_SQL_GEN_PROMPT = """
You are a SQL generator for a {domain} dataset.

Table name: "{table_name}"
Columns available: {columns}

Analysis spec:
- dimensions: {dimensions}
- measures: {measures}
- filters: {filters}
- time_range: {time_range}

Generate a single read-only SELECT statement that:
1. Groups by the dimension columns
2. Aggregates the measure columns (use SUM or AVG as appropriate)
3. Applies any filters from the spec
4. Returns at most 1000 rows

Return ONLY the raw SQL — no explanation, no markdown, no semicolon at the end.
""".strip()


class _TextClause:
    """Minimal stand-in for sqlalchemy.text()."""
    def __init__(self, sql: str) -> None:
        self.text = sql

    def __str__(self) -> str:
        return self.text


def _text(sql: str) -> _TextClause:
    return _TextClause(sql)


class AnalysisAgent:
    """Verbatim port of the real agent — only imports are replaced."""

    def __init__(self, llm=None) -> None:
        self.llm = llm

    async def run_numeric(
        self,
        spec: AnalysisSpec,
        table_name: str,
        db,
        domain: str,
    ) -> list[dict]:
        all_cols = spec.dimensions + spec.measures
        prompt = _SQL_GEN_PROMPT.format(
            domain=domain,
            table_name=table_name,
            columns=", ".join(all_cols),
            dimensions=spec.dimensions,
            measures=spec.measures,
            filters=json.dumps(spec.filters or []),
            time_range=json.dumps(spec.time_range or {}),
        )

        sql_result = await self.llm.structured_completion(
            f"Return JSON: {{\"sql\": \"<your SELECT here>\"}} for: {prompt}",
            SQLOutput,
            agent_name="analysis_sql_gen",
        )
        sql = sql_result.sql.strip().rstrip(";")

        # Safety: only allow SELECT statements
        if not sql.strip().upper().startswith("SELECT"):
            _log.error("analysis_non_select_sql_blocked sql=%s", sql[:100])
            return []

        try:
            result = await db.execute(_text(sql))
            rows = [dict(zip(result.keys(), row)) for row in result.fetchall()]
            _log.info("analysis_sql_executed rows=%d table=%s", len(rows), table_name)
            return rows
        except Exception as exc:
            _log.error("analysis_sql_failed error=%s sql=%s", str(exc), sql[:200])
            return []


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def run(coro):
    """Run a coroutine synchronously (Python 3.7+)."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


def make_spec(
    dimensions: Optional[list[str]] = None,
    measures: Optional[list[str]] = None,
    filters: Optional[list] = None,
    time_range: Optional[dict] = None,
) -> AnalysisSpec:
    return AnalysisSpec(
        dimensions=dimensions or ["region"],
        measures=measures or ["revenue"],
        filters=filters,
        time_range=time_range,
    )


def make_agent(sql: str = "SELECT 1") -> tuple[AnalysisAgent, MockLLM]:
    llm = MockLLM(sql)
    return AnalysisAgent(llm=llm), llm


def make_db(
    columns: Optional[list[str]] = None,
    rows: Optional[list[tuple]] = None,
) -> MockDB:
    return MockDB(columns=columns or [], rows=rows or [])


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
        print("  AnalysisAgent.run_numeric() — test results")
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
# Return-type invariants
# ─────────────────────────────────────────────────────────────────────────────

class TestReturnType:

    def test_returns_list(self):
        agent, _ = make_agent("SELECT region, SUM(revenue) FROM t GROUP BY region")
        db = make_db(["region", "revenue"], [("APAC", 100)])
        result = run(agent.run_numeric(make_spec(), "t", db, "finance"))
        assert isinstance(result, list)

    def test_each_element_is_dict(self):
        agent, _ = make_agent("SELECT region, SUM(revenue) FROM t GROUP BY region")
        db = make_db(["region", "revenue"], [("APAC", 100), ("EMEA", 200)])
        result = run(agent.run_numeric(make_spec(), "t", db, "finance"))
        assert all(isinstance(r, dict) for r in result)

    def test_empty_db_result_returns_empty_list(self):
        agent, _ = make_agent("SELECT region FROM t GROUP BY region")
        db = make_db(["region"], [])
        result = run(agent.run_numeric(make_spec(), "t", db, "finance"))
        assert result == []

    def test_row_keys_match_column_names(self):
        agent, _ = make_agent("SELECT region, SUM(revenue) FROM t GROUP BY region")
        db = make_db(["region", "total_revenue"], [("APAC", 500)])
        result = run(agent.run_numeric(make_spec(), "t", db, "finance"))
        assert set(result[0].keys()) == {"region", "total_revenue"}

    def test_row_values_match_db_data(self):
        agent, _ = make_agent("SELECT region, SUM(revenue) FROM t GROUP BY region")
        db = make_db(["region", "revenue"], [("APAC", 999)])
        result = run(agent.run_numeric(make_spec(), "t", db, "finance"))
        assert result[0] == {"region": "APAC", "revenue": 999}

    def test_multiple_rows_all_returned(self):
        data = [(f"R{i}", i * 100) for i in range(25)]
        agent, _ = make_agent("SELECT region, revenue FROM t")
        db = make_db(["region", "revenue"], data)
        result = run(agent.run_numeric(make_spec(), "t", db, "finance"))
        assert len(result) == 25

    def test_row_order_preserved(self):
        data = [("Z", 1), ("A", 2), ("M", 3)]
        agent, _ = make_agent("SELECT region, revenue FROM t")
        db = make_db(["region", "revenue"], data)
        result = run(agent.run_numeric(make_spec(), "t", db, "finance"))
        assert [r["region"] for r in result] == ["Z", "A", "M"]


# ─────────────────────────────────────────────────────────────────────────────
# SELECT-only safety gate
# ─────────────────────────────────────────────────────────────────────────────

class TestSelectOnlySafetyGate:

    def _blocked(self, sql: str) -> bool:
        agent, _ = make_agent(sql)
        db = make_db(["x"], [(1,)])
        result = run(agent.run_numeric(make_spec(), "t", db, "finance"))
        return result == []

    def _allowed(self, sql: str) -> bool:
        agent, _ = make_agent(sql)
        db = make_db(["x"], [(42,)])
        return run(agent.run_numeric(make_spec(), "t", db, "finance")) != []

    # ── blocked ───────────────────────────────────────────────────────────────

    def test_drop_table_blocked(self):
        assert self._blocked("DROP TABLE sales")

    def test_delete_blocked(self):
        assert self._blocked("DELETE FROM sales WHERE 1=1")

    def test_insert_blocked(self):
        assert self._blocked("INSERT INTO sales VALUES (1, 2)")

    def test_update_blocked(self):
        assert self._blocked("UPDATE sales SET revenue = 0")

    def test_truncate_blocked(self):
        assert self._blocked("TRUNCATE TABLE sales")

    def test_create_table_blocked(self):
        assert self._blocked("CREATE TABLE evil (id INT)")

    def test_alter_table_blocked(self):
        assert self._blocked("ALTER TABLE sales ADD COLUMN x INT")

    def test_empty_sql_blocked(self):
        assert self._blocked("")

    def test_whitespace_only_sql_blocked(self):
        assert self._blocked("   \n\t  ")

    def test_sql_injection_comment_bypass_blocked(self):
        # Starts with comment — still not SELECT
        assert self._blocked("-- comment\nDROP TABLE sales")

    def test_select_embedded_in_delete_blocked(self):
        # The string starts with DELETE, not SELECT
        assert self._blocked("DELETE FROM t WHERE id IN (SELECT id FROM t)")

    # ── allowed ───────────────────────────────────────────────────────────────

    def test_select_uppercase_allowed(self):
        assert self._allowed("SELECT region, SUM(revenue) FROM t GROUP BY region")

    def test_select_lowercase_allowed(self):
        assert self._allowed("select region from t")

    def test_select_mixed_case_allowed(self):
        assert self._allowed("Select region FROM t")

    def test_select_with_leading_whitespace_allowed(self):
        assert self._allowed("   SELECT region FROM t")

    def test_select_with_leading_newline_allowed(self):
        assert self._allowed("\nSELECT region FROM t")

    def test_select_with_cte_allowed(self):
        # WITH … AS (SELECT …) SELECT … — starts with WITH, not SELECT
        # The agent blocks it; this test documents that known limitation
        result = self._blocked("WITH cte AS (SELECT 1) SELECT * FROM cte")
        assert result is True  # blocked — starts with WITH, not SELECT

    def test_select_star_allowed(self):
        assert self._allowed("SELECT * FROM t LIMIT 10")

    def test_select_subquery_in_from_allowed(self):
        assert self._allowed("SELECT a FROM (SELECT a FROM t) sub")

    # ── DB is never called when blocked ──────────────────────────────────────

    def test_blocked_sql_never_reaches_db(self):
        agent, _ = make_agent("DROP TABLE sales")
        db = make_db()
        run(agent.run_numeric(make_spec(), "t", db, "finance"))
        assert db.executed_sqls == []

    def test_allowed_sql_reaches_db_exactly_once(self):
        agent, _ = make_agent("SELECT 1")
        db = make_db(["x"], [(1,)])
        run(agent.run_numeric(make_spec(), "t", db, "finance"))
        assert len(db.executed_sqls) == 1


# ─────────────────────────────────────────────────────────────────────────────
# Semicolon stripping
# ─────────────────────────────────────────────────────────────────────────────

class TestSemicolonStripping:

    def _sql_sent_to_db(self, sql_from_llm: str) -> str:
        agent, _ = make_agent(sql_from_llm)
        db = make_db(["x"], [(1,)])
        run(agent.run_numeric(make_spec(), "t", db, "finance"))
        assert db.executed_sqls, "No SQL was sent to DB"
        return db.executed_sqls[0]

    def test_trailing_semicolon_stripped(self):
        sent = self._sql_sent_to_db("SELECT 1;")
        assert not sent.rstrip().endswith(";")

    def test_trailing_semicolon_with_whitespace_stripped(self):
        sent = self._sql_sent_to_db("SELECT 1;   ")
        assert ";" not in sent

    def test_no_semicolon_unchanged(self):
        sent = self._sql_sent_to_db("SELECT region FROM t")
        assert sent == "SELECT region FROM t"

    def test_semicolon_inside_string_literal_preserved(self):
        # Semicolon inside a quoted constant must not be stripped
        sent = self._sql_sent_to_db("SELECT 'a;b' AS val FROM t")
        assert ";" in sent   # inner semicolon survives

    def test_leading_and_trailing_whitespace_stripped(self):
        sent = self._sql_sent_to_db("  SELECT 1  ")
        assert sent == sent.strip()


# ─────────────────────────────────────────────────────────────────────────────
# LLM interaction
# ─────────────────────────────────────────────────────────────────────────────

class TestLLMInteraction:

    def test_llm_called_exactly_once(self):
        agent, llm = make_agent("SELECT 1")
        db = make_db(["x"], [(1,)])
        run(agent.run_numeric(make_spec(), "t", db, "finance"))
        assert llm.call_count == 1

    def test_prompt_contains_table_name(self):
        agent, llm = make_agent("SELECT 1")
        db = make_db()
        run(agent.run_numeric(make_spec(), "sales_2024", db, "finance"))
        assert "sales_2024" in llm.last_prompt

    def test_prompt_contains_domain(self):
        agent, llm = make_agent("SELECT 1")
        db = make_db()
        run(agent.run_numeric(make_spec(), "t", db, "healthcare"))
        assert "healthcare" in llm.last_prompt

    def test_prompt_contains_dimensions(self):
        agent, llm = make_agent("SELECT 1")
        spec = make_spec(dimensions=["patient_id", "ward"])
        db = make_db()
        run(agent.run_numeric(spec, "t", db, "healthcare"))
        assert "patient_id" in llm.last_prompt
        assert "ward" in llm.last_prompt

    def test_prompt_contains_measures(self):
        agent, llm = make_agent("SELECT 1")
        spec = make_spec(measures=["los", "readmission_rate"])
        db = make_db()
        run(agent.run_numeric(spec, "t", db, "healthcare"))
        assert "los" in llm.last_prompt
        assert "readmission_rate" in llm.last_prompt

    def test_prompt_contains_all_columns(self):
        """all_cols = dimensions + measures must all appear in the prompt."""
        agent, llm = make_agent("SELECT 1")
        spec = make_spec(dimensions=["dim_a"], measures=["meas_b"])
        db = make_db()
        run(agent.run_numeric(spec, "t", db, "finance"))
        assert "dim_a" in llm.last_prompt
        assert "meas_b" in llm.last_prompt

    def test_prompt_contains_filters_as_json(self):
        agent, llm = make_agent("SELECT 1")
        spec = make_spec(filters=[{"col": "region", "op": "=", "val": "APAC"}])
        db = make_db()
        run(agent.run_numeric(spec, "t", db, "retail"))
        assert "APAC" in llm.last_prompt

    def test_prompt_contains_time_range_as_json(self):
        agent, llm = make_agent("SELECT 1")
        spec = make_spec(time_range={"start": "2024-01-01", "end": "2024-12-31"})
        db = make_db()
        run(agent.run_numeric(spec, "t", db, "finance"))
        assert "2024-01-01" in llm.last_prompt

    def test_none_filters_rendered_as_empty_json_array(self):
        agent, llm = make_agent("SELECT 1")
        spec = make_spec(filters=None)
        db = make_db()
        run(agent.run_numeric(spec, "t", db, "finance"))
        assert "[]" in llm.last_prompt

    def test_none_time_range_rendered_as_empty_json_object(self):
        agent, llm = make_agent("SELECT 1")
        spec = make_spec(time_range=None)
        db = make_db()
        run(agent.run_numeric(spec, "t", db, "finance"))
        assert "{}" in llm.last_prompt


# ─────────────────────────────────────────────────────────────────────────────
# SQL sent to DB
# ─────────────────────────────────────────────────────────────────────────────

class TestSQLSentToDB:

    def test_exact_sql_from_llm_sent_to_db(self):
        expected_sql = "SELECT region, SUM(revenue) FROM sales GROUP BY region"
        agent, _ = make_agent(expected_sql)
        db = make_db(["region", "revenue"], [])
        run(agent.run_numeric(make_spec(), "sales", db, "finance"))
        assert db.executed_sqls[0] == expected_sql

    def test_sql_wrapped_in_text_clause_before_db_call(self):
        """The agent must wrap raw SQL in text() before calling db.execute()."""
        agent, _ = make_agent("SELECT 1")
        db = make_db(["x"], [(1,)])
        run(agent.run_numeric(make_spec(), "t", db, "finance"))
        # MockDB stores the .text attribute string; verify it came through
        assert "SELECT 1" in db.executed_sqls[0]

    def test_db_execute_called_exactly_once_on_success(self):
        agent, _ = make_agent("SELECT 1")
        db = make_db(["x"], [(1,)])
        run(agent.run_numeric(make_spec(), "t", db, "finance"))
        assert len(db.executed_sqls) == 1

    def test_db_execute_not_called_on_non_select(self):
        agent, _ = make_agent("DELETE FROM t")
        db = make_db()
        run(agent.run_numeric(make_spec(), "t", db, "finance"))
        assert db.executed_sqls == []

    def test_semicolon_free_sql_reaches_db(self):
        agent, _ = make_agent("SELECT id FROM t;")
        db = make_db(["id"], [(1,)])
        run(agent.run_numeric(make_spec(), "t", db, "finance"))
        assert db.executed_sqls[0] == "SELECT id FROM t"


# ─────────────────────────────────────────────────────────────────────────────
# DB exception handling
# ─────────────────────────────────────────────────────────────────────────────

class TestDBExceptionHandling:

    def test_db_exception_returns_empty_list(self):
        agent, _ = make_agent("SELECT 1")
        db = make_db()
        db.raise_on_execute = RuntimeError("connection refused")
        result = run(agent.run_numeric(make_spec(), "t", db, "finance"))
        assert result == []

    def test_db_operational_error_returns_empty_list(self):
        agent, _ = make_agent("SELECT 1")
        db = make_db()
        db.raise_on_execute = Exception("column 'xyz' does not exist")
        result = run(agent.run_numeric(make_spec(), "t", db, "finance"))
        assert result == []

    def test_db_exception_does_not_propagate(self):
        """run_numeric must swallow DB errors — never raise to the caller."""
        agent, _ = make_agent("SELECT 1")
        db = make_db()
        db.raise_on_execute = ValueError("syntax error near 'FROM'")
        try:
            result = run(agent.run_numeric(make_spec(), "t", db, "finance"))
        except Exception as exc:
            raise AssertionError(f"run_numeric raised unexpectedly: {exc}") from exc

    def test_db_exception_returns_list_not_none(self):
        agent, _ = make_agent("SELECT 1")
        db = make_db()
        db.raise_on_execute = RuntimeError("timeout")
        result = run(agent.run_numeric(make_spec(), "t", db, "finance"))
        assert result is not None and isinstance(result, list)

    def test_db_exception_after_llm_success(self):
        """LLM returned valid SELECT; DB blows up — must still return []."""
        agent, llm = make_agent("SELECT region, SUM(revenue) FROM t GROUP BY region")
        db = make_db()
        db.raise_on_execute = Exception("disk full")
        result = run(agent.run_numeric(make_spec(), "t", db, "finance"))
        assert result == []
        assert llm.call_count == 1  # LLM was still called


# ─────────────────────────────────────────────────────────────────────────────
# LLM failure handling
# ─────────────────────────────────────────────────────────────────────────────

class TestLLMFailureHandling:

    def test_llm_exception_propagates(self):
        """
        The agent does NOT catch LLM errors (by design — the supervisor handles them).
        Verify the exception surfaces rather than being silently swallowed.
        """
        agent, llm = make_agent("SELECT 1")
        llm.raise_on_call = RuntimeError("LLM rate limit")
        db = make_db()
        try:
            run(agent.run_numeric(make_spec(), "t", db, "finance"))
            raise AssertionError("Expected RuntimeError to propagate")
        except RuntimeError as exc:
            assert "LLM rate limit" in str(exc)

    def test_db_not_called_when_llm_raises(self):
        agent, llm = make_agent("SELECT 1")
        llm.raise_on_call = RuntimeError("LLM unavailable")
        db = make_db()
        try:
            run(agent.run_numeric(make_spec(), "t", db, "finance"))
        except RuntimeError:
            pass
        assert db.executed_sqls == []


# ─────────────────────────────────────────────────────────────────────────────
# Row → dict mapping
# ─────────────────────────────────────────────────────────────────────────────

class TestRowMapping:

    def test_single_column_mapped_correctly(self):
        agent, _ = make_agent("SELECT region FROM t")
        db = make_db(["region"], [("APAC",), ("EMEA",)])
        result = run(agent.run_numeric(make_spec(), "t", db, "finance"))
        assert result == [{"region": "APAC"}, {"region": "EMEA"}]

    def test_multi_column_mapped_correctly(self):
        agent, _ = make_agent("SELECT region, SUM(rev) FROM t GROUP BY region")
        db = make_db(["region", "total_rev"], [("APAC", 500), ("EMEA", 300)])
        result = run(agent.run_numeric(make_spec(), "t", db, "finance"))
        assert result[0] == {"region": "APAC", "total_rev": 500}
        assert result[1] == {"region": "EMEA", "total_rev": 300}

    def test_none_values_in_row_preserved(self):
        agent, _ = make_agent("SELECT region, revenue FROM t")
        db = make_db(["region", "revenue"], [("APAC", None)])
        result = run(agent.run_numeric(make_spec(), "t", db, "finance"))
        assert result[0]["revenue"] is None

    def test_numeric_values_preserved_as_is(self):
        agent, _ = make_agent("SELECT id, score FROM t")
        db = make_db(["id", "score"], [(1, 3.14)])
        result = run(agent.run_numeric(make_spec(), "t", db, "finance"))
        assert result[0]["id"] == 1
        assert abs(result[0]["score"] - 3.14) < 1e-9

    def test_column_count_matches_row_tuple_length(self):
        agent, _ = make_agent("SELECT a, b, c FROM t")
        db = make_db(["a", "b", "c"], [(1, 2, 3), (4, 5, 6)])
        result = run(agent.run_numeric(make_spec(), "t", db, "finance"))
        assert all(len(r) == 3 for r in result)

    def test_rows_are_independent_dicts(self):
        """Mutating one returned row must not affect another."""
        agent, _ = make_agent("SELECT region FROM t")
        db = make_db(["region"], [("APAC",), ("EMEA",)])
        result = run(agent.run_numeric(make_spec(), "t", db, "finance"))
        result[0]["region"] = "MUTATED"
        assert result[1]["region"] == "EMEA"


# ─────────────────────────────────────────────────────────────────────────────
# Domain variations
# ─────────────────────────────────────────────────────────────────────────────

class TestDomainVariations:
    """Verify the agent works correctly across all supported domains."""

    DOMAINS = ["finance", "healthcare", "retail", "marketing", "operations", "other"]

    def _run_for_domain(self, domain: str) -> list[dict]:
        agent, _ = make_agent("SELECT col FROM t")
        db = make_db(["col"], [("val",)])
        return run(agent.run_numeric(make_spec(), "t", db, domain))

    def test_finance_domain(self):
        assert self._run_for_domain("finance") == [{"col": "val"}]

    def test_healthcare_domain(self):
        assert self._run_for_domain("healthcare") == [{"col": "val"}]

    def test_retail_domain(self):
        assert self._run_for_domain("retail") == [{"col": "val"}]

    def test_marketing_domain(self):
        assert self._run_for_domain("marketing") == [{"col": "val"}]

    def test_operations_domain(self):
        assert self._run_for_domain("operations") == [{"col": "val"}]

    def test_other_domain(self):
        assert self._run_for_domain("other") == [{"col": "val"}]

    def test_domain_appears_in_llm_prompt(self):
        for domain in self.DOMAINS:
            _, llm = make_agent("SELECT 1")
            db = make_db()
            run(AnalysisAgent(llm=llm).run_numeric(make_spec(), "t", db, domain))
            assert domain in llm.last_prompt, f"Domain '{domain}' missing from prompt"


# ─────────────────────────────────────────────────────────────────────────────
# AnalysisSpec variations
# ─────────────────────────────────────────────────────────────────────────────

class TestSpecVariations:

    def test_multiple_dimensions(self):
        spec = make_spec(dimensions=["region", "channel", "product"])
        agent, llm = make_agent("SELECT region FROM t")
        db = make_db(["region"], [])
        run(agent.run_numeric(spec, "t", db, "retail"))
        assert all(d in llm.last_prompt for d in ["region", "channel", "product"])

    def test_multiple_measures(self):
        spec = make_spec(measures=["revenue", "units", "margin"])
        agent, llm = make_agent("SELECT 1")
        db = make_db()
        run(agent.run_numeric(spec, "t", db, "retail"))
        assert all(m in llm.last_prompt for m in ["revenue", "units", "margin"])

    def test_single_dimension_single_measure(self):
        spec = make_spec(dimensions=["ward"], measures=["los"])
        agent, _ = make_agent("SELECT ward, AVG(los) FROM t GROUP BY ward")
        db = make_db(["ward", "avg_los"], [("ICU", 4.2)])
        result = run(agent.run_numeric(spec, "t", db, "healthcare"))
        assert result[0]["ward"] == "ICU"

    def test_filters_list_serialised_to_json_in_prompt(self):
        filters = [{"col": "region", "op": "=", "val": "APAC"},
                   {"col": "year",   "op": ">", "val": 2022}]
        spec = make_spec(filters=filters)
        _, llm = make_agent("SELECT 1")
        db = make_db()
        run(AnalysisAgent(llm=llm).run_numeric(spec, "t", db, "finance"))
        prompt_data = llm.last_prompt
        assert "APAC" in prompt_data
        assert "2022" in prompt_data

    def test_empty_filters_list_rendered_as_empty_array(self):
        spec = make_spec(filters=[])
        _, llm = make_agent("SELECT 1")
        db = make_db()
        run(AnalysisAgent(llm=llm).run_numeric(spec, "t", db, "finance"))
        assert "[]" in llm.last_prompt

    def test_time_range_dict_serialised_in_prompt(self):
        spec = make_spec(time_range={"start": "2023-Q1", "end": "2023-Q4"})
        _, llm = make_agent("SELECT 1")
        db = make_db()
        run(AnalysisAgent(llm=llm).run_numeric(spec, "t", db, "finance"))
        assert "2023-Q1" in llm.last_prompt
        assert "2023-Q4" in llm.last_prompt


# ─────────────────────────────────────────────────────────────────────────────
# Table name handling
# ─────────────────────────────────────────────────────────────────────────────

class TestTableNameHandling:

    def test_table_name_appears_in_prompt(self):
        _, llm = make_agent("SELECT 1")
        db = make_db()
        run(AnalysisAgent(llm=llm).run_numeric(make_spec(), "orders_q3_2024", db, "retail"))
        assert "orders_q3_2024" in llm.last_prompt

    def test_table_name_with_schema_prefix(self):
        _, llm = make_agent("SELECT 1")
        db = make_db()
        run(AnalysisAgent(llm=llm).run_numeric(make_spec(), "public.sales", db, "finance"))
        assert "public.sales" in llm.last_prompt

    def test_table_name_with_underscores(self):
        _, llm = make_agent("SELECT 1")
        db = make_db()
        run(AnalysisAgent(llm=llm).run_numeric(make_spec(), "my_fact_table", db, "finance"))
        assert "my_fact_table" in llm.last_prompt

    def test_different_table_names_produce_different_prompts(self):
        _, llm_a = make_agent("SELECT 1")
        _, llm_b = make_agent("SELECT 1")
        db = make_db()
        run(AnalysisAgent(llm=llm_a).run_numeric(make_spec(), "table_a", db, "finance"))
        run(AnalysisAgent(llm=llm_b).run_numeric(make_spec(), "table_b", db, "finance"))
        assert llm_a.last_prompt != llm_b.last_prompt


# ─────────────────────────────────────────────────────────────────────────────
# Edge cases & robustness
# ─────────────────────────────────────────────────────────────────────────────

class TestEdgeCases:

    def test_sql_with_only_whitespace_before_select_allowed(self):
        agent, _ = make_agent("\n\n  SELECT 1")
        db = make_db(["x"], [(1,)])
        result = run(agent.run_numeric(make_spec(), "t", db, "finance"))
        assert result == [{"x": 1}]

    def test_large_result_set_all_rows_returned(self):
        data = [(i, float(i)) for i in range(500)]
        agent, _ = make_agent("SELECT id, val FROM t LIMIT 1000")
        db = make_db(["id", "val"], data)
        result = run(agent.run_numeric(make_spec(), "t", db, "finance"))
        assert len(result) == 500

    def test_wide_row_many_columns(self):
        n_cols = 30
        cols = [f"col_{i}" for i in range(n_cols)]
        row = tuple(range(n_cols))
        agent, _ = make_agent(f"SELECT {', '.join(cols)} FROM t")
        db = make_db(cols, [row])
        result = run(agent.run_numeric(make_spec(), "t", db, "finance"))
        assert len(result[0]) == n_cols

    def test_select_returning_boolean_values(self):
        agent, _ = make_agent("SELECT is_active FROM t")
        db = make_db(["is_active"], [(True,), (False,)])
        result = run(agent.run_numeric(make_spec(), "t", db, "operations"))
        assert result[0]["is_active"] is True
        assert result[1]["is_active"] is False

    def test_select_returning_mixed_types(self):
        agent, _ = make_agent("SELECT id, name, score FROM t")
        db = make_db(["id", "name", "score"], [(1, "Alice", 99.5)])
        result = run(agent.run_numeric(make_spec(), "t", db, "finance"))
        assert result[0] == {"id": 1, "name": "Alice", "score": 99.5}

    def test_llm_returns_sql_with_extra_whitespace(self):
        agent, _ = make_agent("   SELECT   id   FROM   t   ")
        db = make_db(["id"], [(42,)])
        result = run(agent.run_numeric(make_spec(), "t", db, "finance"))
        assert result == [{"id": 42}]

    def test_concurrent_calls_do_not_share_state(self):
        """Two independent agents with separate LLMs and DBs must not interfere."""
        agent_a, _ = make_agent("SELECT a FROM t")
        agent_b, _ = make_agent("SELECT b FROM t")
        db_a = make_db(["a"], [(1,)])
        db_b = make_db(["b"], [(2,)])
        r_a = run(agent_a.run_numeric(make_spec(), "t", db_a, "finance"))
        r_b = run(agent_b.run_numeric(make_spec(), "t", db_b, "finance"))
        assert r_a == [{"a": 1}]
        assert r_b == [{"b": 2}]


# ═════════════════════════════════════════════════════════════════════════════
# Runner
# ═════════════════════════════════════════════════════════════════════════════

def _collect_all_test_classes():
    return [
        TestReturnType,
        TestSelectOnlySafetyGate,
        TestSemicolonStripping,
        TestLLMInteraction,
        TestSQLSentToDB,
        TestDBExceptionHandling,
        TestLLMFailureHandling,
        TestRowMapping,
        TestDomainVariations,
        TestSpecVariations,
        TestTableNameHandling,
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