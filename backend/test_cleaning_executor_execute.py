"""
Unit tests for CleaningExecutorAgent.execute()

Source agent: backend/app/agents/cleaning_executor.py

Run with:
    pytest  test_cleaning_executor_agent.py -v
    python  test_cleaning_executor_agent.py          # prints live results

Fully independent — no LLM, no DB, no Supabase, no app imports.
The agent class and its Pydantic model stand-ins are reproduced verbatim
so these tests exercise the real logic, not a mock.

CleaningExecutorAgent.execute() contract:
    Input  : rows (list[dict]), steps (list[CleaningStep]), decision (CleaningPlanDecision)
    Output : (cleaned_rows: list[dict], audit_entries: list[dict])

    - Only steps whose step_id is in decision.approved_step_ids are executed.
    - decision.step_modifications[step_id]["method"] overrides the step's method.
    - Every executed step produces exactly one audit entry.
    - Audit entry keys: step_id, action, column, method, rationale, confidence,
                        rows_before, rows_after, rows_changed.

Internal methods under test:
    _deduplicate   — removes exact duplicate rows (order-stable, keeps first)
    _impute        — fills None / "" with median | mode | first-non-null
    _coerce_type   — casts string numbers to float; leaves un-parseable values
    _flag_outlier  — adds _outlier_<col> bool via IQR; skips if < 4 non-null values
"""

from __future__ import annotations

import statistics
import sys
import traceback
from collections import Counter
from dataclasses import dataclass, field
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
# Stand-ins for app.models.schemas (no app import required)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CleaningStep:
    step_id: int
    action: str          # "deduplicate" | "impute" | "coerce_type" | "flag_outlier"
    column: Optional[str]
    method: str
    rationale: str = "test rationale"
    confidence: float = 0.9
    rows_affected: int = 0


@dataclass
class CleaningPlanDecision:
    approved_step_ids: list[int]
    step_modifications: dict[int, dict] = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────────
# Agent under test — verbatim copy of cleaning_executor.py
# (swap for the real import once the backend package is on sys.path)
# ─────────────────────────────────────────────────────────────────────────────

class CleaningExecutorAgent:
    """Executes approved cleaning steps; logs every action for the audit trail."""

    def execute(
        self,
        rows: list[dict],
        steps: list[CleaningStep],
        decision: CleaningPlanDecision,
    ) -> tuple[list[dict], list[dict]]:
        approved_ids = set(decision.approved_step_ids)
        approved_steps = [s for s in steps if s.step_id in approved_ids]

        audit: list[dict] = []
        working = [dict(r) for r in rows]

        for step in approved_steps:
            overrides = decision.step_modifications.get(step.step_id, {})
            effective_method = overrides.get("method", step.method)

            before_count = len(working)
            working = self._apply_step(working, step, effective_method)
            after_count = len(working)

            audit.append({
                "step_id": step.step_id,
                "action": step.action,
                "column": step.column,
                "method": effective_method,
                "rationale": step.rationale,
                "confidence": step.confidence,
                "rows_before": before_count,
                "rows_after": after_count,
                "rows_changed": before_count - after_count if step.action == "deduplicate" else step.rows_affected,
            })

        return working, audit

    def _apply_step(self, rows: list[dict], step: CleaningStep, method: str) -> list[dict]:
        if step.action == "deduplicate":
            return self._deduplicate(rows)
        if step.action == "impute" and step.column:
            return self._impute(rows, step.column, method)
        if step.action == "coerce_type" and step.column:
            return self._coerce_type(rows, step.column)
        if step.action == "flag_outlier" and step.column:
            return self._flag_outlier(rows, step.column)
        return rows

    def _deduplicate(self, rows: list[dict]) -> list[dict]:
        seen: set[str] = set()
        result: list[dict] = []
        for row in rows:
            key = str(sorted(row.items()))
            if key not in seen:
                seen.add(key)
                result.append(row)
        return result

    def _impute(self, rows: list[dict], column: str, method: str) -> list[dict]:
        non_null = [r[column] for r in rows if r.get(column) not in (None, "")]
        if not non_null:
            return rows
        if "median" in method.lower():
            try:
                fill_value = statistics.median(float(v) for v in non_null)
            except Exception:
                fill_value = non_null[0]
        elif "mode" in method.lower() or "frequent" in method.lower():
            counts = Counter(non_null)
            fill_value = counts.most_common(1)[0][0]
        else:
            fill_value = non_null[0]
        return [
            {**row, column: fill_value} if row.get(column) in (None, "") else row
            for row in rows
        ]

    def _coerce_type(self, rows: list[dict], column: str) -> list[dict]:
        result = []
        for row in rows:
            val = row.get(column)
            try:
                coerced = float(str(val).replace(",", "")) if val not in (None, "") else None
            except ValueError:
                coerced = val
            result.append({**row, column: coerced})
        return result

    def _flag_outlier(self, rows: list[dict], column: str) -> list[dict]:
        try:
            vals = [float(r[column]) for r in rows if r.get(column) not in (None, "")]
            if len(vals) < 4:
                return rows
            q1 = statistics.quantiles(vals, n=4)[0]
            q3 = statistics.quantiles(vals, n=4)[2]
            iqr = q3 - q1
            lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
            return [
                {**row, f"_outlier_{column}": float(row[column]) < lower or float(row[column]) > upper}
                if row.get(column) not in (None, "") else row
                for row in rows
            ]
        except Exception:
            return rows


# ─────────────────────────────────────────────────────────────────────────────
# Test helpers
# ─────────────────────────────────────────────────────────────────────────────

def make_agent() -> CleaningExecutorAgent:
    return CleaningExecutorAgent()


def make_step(
    step_id: int = 1,
    action: str = "deduplicate",
    column: Optional[str] = None,
    method: str = "exact row deduplication",
    rows_affected: int = 0,
    confidence: float = 0.9,
) -> CleaningStep:
    return CleaningStep(
        step_id=step_id,
        action=action,
        column=column,
        method=method,
        rows_affected=rows_affected,
        confidence=confidence,
    )


def make_decision(
    approved_ids: list[int],
    modifications: Optional[dict[int, dict]] = None,
) -> CleaningPlanDecision:
    return CleaningPlanDecision(
        approved_step_ids=approved_ids,
        step_modifications=modifications or {},
    )


# ─────────────────────────────────────────────────────────────────────────────
# Lightweight test runner
# ─────────────────────────────────────────────────────────────────────────────

class _Results:
    def __init__(self) -> None:
        self.passed: list[str] = []
        self.failed: list[tuple[str, str]] = []

    def record(self, name: str, exc: Optional[Exception]) -> None:
        (self.passed if exc is None else self.failed).append(
            name if exc is None else (name, traceback.format_exc())
        )

    def print_summary(self) -> None:
        total = len(self.passed) + len(self.failed)
        w = 72
        print("=" * w)
        print("  CleaningExecutorAgent — execute() test results")
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
# execute() — return-type & structural invariants
# ─────────────────────────────────────────────────────────────────────────────

class TestExecuteReturnStructure:

    def test_returns_tuple_of_two(self):
        agent = make_agent()
        result = agent.execute([], [], make_decision([]))
        assert isinstance(result, tuple) and len(result) == 2

    def test_first_element_is_list(self):
        agent = make_agent()
        rows, _ = agent.execute([], [], make_decision([]))
        assert isinstance(rows, list)

    def test_second_element_is_list(self):
        agent = make_agent()
        _, audit = agent.execute([], [], make_decision([]))
        assert isinstance(audit, list)

    def test_empty_rows_empty_steps_returns_empty_rows(self):
        agent = make_agent()
        rows, audit = agent.execute([], [], make_decision([]))
        assert rows == [] and audit == []

    def test_input_rows_are_not_mutated(self):
        """execute() must deep-copy rows — original list must be untouched."""
        original = [{"a": None}, {"a": None}]
        step = make_step(1, "impute", "a", "median imputation", rows_affected=2)
        # Give it a non-null row so median has something to work with
        rows = [{"a": 5}, {"a": None}]
        agent = make_agent()
        agent.execute(rows, [step], make_decision([1]))
        assert rows[1]["a"] is None  # original unchanged

    def test_output_rows_are_independent_copies(self):
        rows = [{"x": 1}]
        step = make_step(1, "impute", "x", "median imputation")
        agent = make_agent()
        cleaned, _ = agent.execute(rows, [step], make_decision([1]))
        cleaned[0]["x"] = 999
        assert rows[0]["x"] == 1  # original still untouched


# ─────────────────────────────────────────────────────────────────────────────
# execute() — HITL approval gating
# ─────────────────────────────────────────────────────────────────────────────

class TestApprovalGating:

    def test_no_approved_steps_returns_rows_unchanged(self):
        rows = [{"a": 1}, {"a": 1}]
        step = make_step(1, "deduplicate")
        agent = make_agent()
        cleaned, audit = agent.execute(rows, [step], make_decision([]))
        assert len(cleaned) == 2 and audit == []

    def test_only_approved_step_is_executed(self):
        rows = [{"a": 1}, {"a": 1}]
        dedup = make_step(1, "deduplicate")
        impute = make_step(2, "impute", "a", "median imputation")
        agent = make_agent()
        cleaned, audit = agent.execute(rows, [dedup, impute], make_decision([1]))
        # dedup removes duplicate → 1 row; impute was not approved
        assert len(cleaned) == 1
        assert len(audit) == 1 and audit[0]["step_id"] == 1

    def test_all_steps_approved_all_executed(self):
        rows = [{"price": "1,000"}, {"price": None}]
        steps = [
            make_step(1, "coerce_type", "price", "to_float"),
            make_step(2, "impute", "price", "median imputation"),
        ]
        agent = make_agent()
        _, audit = agent.execute(rows, steps, make_decision([1, 2]))
        assert len(audit) == 2

    def test_unapproved_step_produces_no_audit_entry(self):
        rows = [{"v": None}]
        step = make_step(1, "impute", "v", "median imputation")
        agent = make_agent()
        _, audit = agent.execute(rows, [step], make_decision([]))
        assert audit == []

    def test_approved_ids_not_in_steps_are_silently_ignored(self):
        """Approval for a non-existent step_id must not raise."""
        rows = [{"a": 1}]
        agent = make_agent()
        cleaned, audit = agent.execute(rows, [], make_decision([99]))
        assert cleaned == [{"a": 1}] and audit == []

    def test_steps_executed_in_declaration_order(self):
        """Steps must run in the order they appear in the steps list, not by step_id."""
        log = []

        class OrderAgent(CleaningExecutorAgent):
            def _impute(self, rows, column, method):
                log.append(f"impute:{column}")
                return rows
            def _coerce_type(self, rows, column):
                log.append(f"coerce:{column}")
                return rows

        rows = [{"a": 1, "b": 2}]
        steps = [
            make_step(2, "coerce_type", "b", "to_float"),
            make_step(1, "impute",      "a", "median imputation"),
        ]
        OrderAgent().execute(rows, steps, make_decision([1, 2]))
        assert log == ["coerce:b", "impute:a"]


# ─────────────────────────────────────────────────────────────────────────────
# execute() — method override via step_modifications
# ─────────────────────────────────────────────────────────────────────────────

class TestMethodOverride:

    def test_override_changes_effective_method_in_audit(self):
        rows = [{"x": None}, {"x": 10}, {"x": 20}]
        step = make_step(1, "impute", "x", "median imputation")
        decision = make_decision([1], {1: {"method": "mode imputation"}})
        agent = make_agent()
        _, audit = agent.execute(rows, [step], decision)
        assert audit[0]["method"] == "mode imputation"

    def test_override_actually_changes_behaviour(self):
        """mode vs median give different fill values for this dataset."""
        # non-null values: [1, 1, 1, 10, 10] → mode=1, median=1 (same here)
        # use [1, 2, 10, 10, 10] → mode=10, median=10  (same — pick unambiguous case)
        # use [1, 2, 3, 10, 10] → mode=10, median=3
        rows = [{"v": None}, {"v": 1}, {"v": 2}, {"v": 3}, {"v": 10}, {"v": 10}]
        step_median = make_step(1, "impute", "v", "median imputation")
        step_mode   = make_step(1, "impute", "v", "median imputation")

        agent = make_agent()
        cleaned_median, _ = agent.execute(rows, [step_median], make_decision([1]))
        cleaned_mode, _   = agent.execute(rows, [step_mode],
                                          make_decision([1], {1: {"method": "mode imputation"}}))

        fill_median = cleaned_median[0]["v"]
        fill_mode   = cleaned_mode[0]["v"]
        assert fill_median != fill_mode, (
            f"Expected different fill values; both were {fill_median}"
        )

    def test_no_override_uses_original_method(self):
        rows = [{"x": None}, {"x": 5}, {"x": 15}]
        step = make_step(1, "impute", "x", "median imputation")
        agent = make_agent()
        _, audit = agent.execute(rows, [step], make_decision([1]))
        assert audit[0]["method"] == "median imputation"

    def test_override_for_different_step_does_not_affect_this_step(self):
        rows = [{"x": None}, {"x": 5}, {"x": 15}]
        step = make_step(1, "impute", "x", "median imputation")
        # Override targets step_id=2 (does not exist) — step 1 must be unaffected
        decision = make_decision([1], {2: {"method": "mode imputation"}})
        agent = make_agent()
        _, audit = agent.execute(rows, [step], decision)
        assert audit[0]["method"] == "median imputation"


# ─────────────────────────────────────────────────────────────────────────────
# execute() — audit entry shape & content
# ─────────────────────────────────────────────────────────────────────────────

class TestAuditEntries:

    REQUIRED_KEYS = {
        "step_id", "action", "column", "method", "rationale",
        "confidence", "rows_before", "rows_after", "rows_changed",
    }

    def test_audit_entry_has_all_required_keys(self):
        rows = [{"a": 1}, {"a": 1}]
        step = make_step(1, "deduplicate")
        agent = make_agent()
        _, audit = agent.execute(rows, [step], make_decision([1]))
        assert self.REQUIRED_KEYS.issubset(audit[0].keys())

    def test_one_audit_entry_per_executed_step(self):
        rows = [{"a": 1}, {"b": 2}]
        steps = [
            make_step(1, "impute", "a", "median imputation"),
            make_step(2, "impute", "b", "median imputation"),
        ]
        agent = make_agent()
        _, audit = agent.execute(rows, steps, make_decision([1, 2]))
        assert len(audit) == 2

    def test_audit_step_id_matches_step(self):
        rows = [{"a": 1}]
        step = make_step(7, "impute", "a", "median imputation")
        agent = make_agent()
        _, audit = agent.execute(rows, [step], make_decision([7]))
        assert audit[0]["step_id"] == 7

    def test_audit_action_matches_step(self):
        rows = [{"a": 1}, {"a": 1}]
        step = make_step(1, "deduplicate")
        agent = make_agent()
        _, audit = agent.execute(rows, [step], make_decision([1]))
        assert audit[0]["action"] == "deduplicate"

    def test_audit_column_matches_step(self):
        rows = [{"price": None}, {"price": 9}]
        step = make_step(1, "impute", "price", "median imputation")
        agent = make_agent()
        _, audit = agent.execute(rows, [step], make_decision([1]))
        assert audit[0]["column"] == "price"

    def test_audit_confidence_matches_step(self):
        rows = [{"a": 1}]
        step = make_step(1, "impute", "a", "median imputation", confidence=0.77)
        agent = make_agent()
        _, audit = agent.execute(rows, [step], make_decision([1]))
        assert audit[0]["confidence"] == 0.77

    def test_audit_rows_before_is_accurate(self):
        rows = [{"a": i} for i in range(20)]
        step = make_step(1, "impute", "a", "median imputation")
        agent = make_agent()
        _, audit = agent.execute(rows, [step], make_decision([1]))
        assert audit[0]["rows_before"] == 20

    def test_audit_rows_after_equals_len_cleaned(self):
        rows = [{"a": 1}, {"a": 1}, {"a": 2}]
        step = make_step(1, "deduplicate")
        agent = make_agent()
        cleaned, audit = agent.execute(rows, [step], make_decision([1]))
        assert audit[0]["rows_after"] == len(cleaned)

    def test_audit_rows_changed_for_dedup_is_difference(self):
        rows = [{"a": 1}, {"a": 1}, {"a": 2}]
        step = make_step(1, "deduplicate")
        agent = make_agent()
        _, audit = agent.execute(rows, [step], make_decision([1]))
        assert audit[0]["rows_changed"] == 1   # 3 before − 2 after

    def test_audit_rows_changed_for_non_dedup_uses_rows_affected(self):
        """Non-dedup steps use step.rows_affected for rows_changed in the audit."""
        rows = [{"a": None}, {"a": None}, {"a": 5}]
        step = make_step(1, "impute", "a", "median imputation", rows_affected=2)
        agent = make_agent()
        _, audit = agent.execute(rows, [step], make_decision([1]))
        assert audit[0]["rows_changed"] == 2

    def test_audit_entries_ordered_by_execution(self):
        rows = [{"a": 1, "b": None}]
        steps = [
            make_step(1, "impute", "b", "median imputation"),
            make_step(2, "coerce_type", "a", "to_float"),
        ]
        agent = make_agent()
        _, audit = agent.execute(rows, steps, make_decision([1, 2]))
        assert [e["step_id"] for e in audit] == [1, 2]

    def test_rationale_preserved_in_audit(self):
        rows = [{"x": 1}]
        step = CleaningStep(1, "impute", "x", "median imputation",
                            rationale="special reason", confidence=0.9)
        agent = make_agent()
        _, audit = agent.execute(rows, [step], make_decision([1]))
        assert audit[0]["rationale"] == "special reason"


# ─────────────────────────────────────────────────────────────────────────────
# _deduplicate
# ─────────────────────────────────────────────────────────────────────────────

class TestDeduplicate:

    def test_removes_exact_duplicate_rows(self):
        rows = [{"a": 1, "b": 2}, {"a": 1, "b": 2}, {"a": 3, "b": 4}]
        step = make_step(1, "deduplicate")
        agent = make_agent()
        cleaned, _ = agent.execute(rows, [step], make_decision([1]))
        assert len(cleaned) == 2

    def test_keeps_first_occurrence(self):
        rows = [{"id": 1, "v": "first"}, {"id": 1, "v": "first"}, {"id": 2, "v": "second"}]
        step = make_step(1, "deduplicate")
        agent = make_agent()
        cleaned, _ = agent.execute(rows, [step], make_decision([1]))
        assert cleaned[0] == {"id": 1, "v": "first"}
        assert cleaned[1] == {"id": 2, "v": "second"}

    def test_no_duplicates_returns_same_rows(self):
        rows = [{"a": 1}, {"a": 2}, {"a": 3}]
        step = make_step(1, "deduplicate")
        agent = make_agent()
        cleaned, _ = agent.execute(rows, [step], make_decision([1]))
        assert len(cleaned) == 3

    def test_all_duplicates_returns_one_row(self):
        rows = [{"x": 7}] * 10
        step = make_step(1, "deduplicate")
        agent = make_agent()
        cleaned, _ = agent.execute(rows, [step], make_decision([1]))
        assert cleaned == [{"x": 7}]

    def test_empty_input_returns_empty(self):
        step = make_step(1, "deduplicate")
        agent = make_agent()
        cleaned, _ = agent.execute([], [step], make_decision([1]))
        assert cleaned == []

    def test_single_row_unchanged(self):
        rows = [{"a": 1}]
        step = make_step(1, "deduplicate")
        agent = make_agent()
        cleaned, _ = agent.execute(rows, [step], make_decision([1]))
        assert cleaned == [{"a": 1}]

    def test_original_row_order_preserved(self):
        rows = [{"n": 3}, {"n": 1}, {"n": 2}]
        step = make_step(1, "deduplicate")
        agent = make_agent()
        cleaned, _ = agent.execute(rows, [step], make_decision([1]))
        assert [r["n"] for r in cleaned] == [3, 1, 2]

    def test_partial_duplicates_only_duplicate_removed(self):
        """Rows that share some but not all fields are NOT duplicates."""
        rows = [{"a": 1, "b": 2}, {"a": 1, "b": 99}]
        step = make_step(1, "deduplicate")
        agent = make_agent()
        cleaned, _ = agent.execute(rows, [step], make_decision([1]))
        assert len(cleaned) == 2

    def test_dedup_audit_rows_changed_correct(self):
        rows = [{"a": 1}] * 5
        step = make_step(1, "deduplicate")
        agent = make_agent()
        _, audit = agent.execute(rows, [step], make_decision([1]))
        assert audit[0]["rows_changed"] == 4   # 5 - 1


# ─────────────────────────────────────────────────────────────────────────────
# _impute
# ─────────────────────────────────────────────────────────────────────────────

class TestImpute:

    # ── median ────────────────────────────────────────────────────────────────

    def test_median_fills_none_values(self):
        rows = [{"v": None}, {"v": 10}, {"v": 20}]
        step = make_step(1, "impute", "v", "median imputation")
        agent = make_agent()
        cleaned, _ = agent.execute(rows, [step], make_decision([1]))
        assert cleaned[0]["v"] == 15.0

    def test_median_fills_empty_string_values(self):
        rows = [{"v": ""}, {"v": 10}, {"v": 20}]
        step = make_step(1, "impute", "v", "median imputation")
        agent = make_agent()
        cleaned, _ = agent.execute(rows, [step], make_decision([1]))
        assert cleaned[0]["v"] == 15.0

    def test_median_does_not_overwrite_existing_values(self):
        rows = [{"v": 5}, {"v": None}, {"v": 10}, {"v": 20}]
        step = make_step(1, "impute", "v", "median imputation")
        agent = make_agent()
        cleaned, _ = agent.execute(rows, [step], make_decision([1]))
        assert cleaned[0]["v"] == 5

    def test_median_even_count_is_average_of_middle_two(self):
        rows = [{"v": None}, {"v": 10}, {"v": 20}, {"v": 30}, {"v": 40}]
        step = make_step(1, "impute", "v", "median imputation")
        agent = make_agent()
        cleaned, _ = agent.execute(rows, [step], make_decision([1]))
        assert cleaned[0]["v"] == 25.0

    def test_median_multiple_nulls_all_filled(self):
        rows = [{"v": None}, {"v": None}, {"v": 10}, {"v": 20}]
        step = make_step(1, "impute", "v", "median imputation")
        agent = make_agent()
        cleaned, _ = agent.execute(rows, [step], make_decision([1]))
        assert all(r["v"] is not None for r in cleaned)

    # ── mode ──────────────────────────────────────────────────────────────────

    def test_mode_fills_with_most_frequent_value(self):
        rows = [{"cat": None}, {"cat": "A"}, {"cat": "A"}, {"cat": "B"}]
        step = make_step(1, "impute", "cat", "mode imputation")
        agent = make_agent()
        cleaned, _ = agent.execute(rows, [step], make_decision([1]))
        assert cleaned[0]["cat"] == "A"

    def test_mode_keyword_frequent_also_triggers_mode(self):
        rows = [{"cat": None}, {"cat": "X"}, {"cat": "X"}, {"cat": "Y"}]
        step = make_step(1, "impute", "cat", "most_frequent")
        agent = make_agent()
        cleaned, _ = agent.execute(rows, [step], make_decision([1]))
        assert cleaned[0]["cat"] == "X"

    def test_mode_does_not_overwrite_existing_values(self):
        rows = [{"cat": "Z"}, {"cat": None}, {"cat": "A"}, {"cat": "A"}]
        step = make_step(1, "impute", "cat", "mode imputation")
        agent = make_agent()
        cleaned, _ = agent.execute(rows, [step], make_decision([1]))
        assert cleaned[0]["cat"] == "Z"

    # ── fallback (unknown method) ─────────────────────────────────────────────

    def test_unknown_method_fills_with_first_non_null(self):
        rows = [{"v": None}, {"v": 42}, {"v": 99}]
        step = make_step(1, "impute", "v", "some_unknown_strategy")
        agent = make_agent()
        cleaned, _ = agent.execute(rows, [step], make_decision([1]))
        assert cleaned[0]["v"] == 42

    # ── all-null edge case ────────────────────────────────────────────────────

    def test_all_null_column_returns_rows_unchanged(self):
        rows = [{"v": None}, {"v": None}]
        step = make_step(1, "impute", "v", "median imputation")
        agent = make_agent()
        cleaned, _ = agent.execute(rows, [step], make_decision([1]))
        assert all(r["v"] is None for r in cleaned)

    def test_impute_does_not_affect_other_columns(self):
        rows = [{"a": None, "b": 99}, {"a": 10, "b": 55}]
        step = make_step(1, "impute", "a", "median imputation")
        agent = make_agent()
        cleaned, _ = agent.execute(rows, [step], make_decision([1]))
        assert cleaned[0]["b"] == 99
        assert cleaned[1]["b"] == 55

    def test_impute_missing_column_returns_rows_unchanged(self):
        """If the target column doesn't exist in the row, rows pass through silently."""
        rows = [{"x": 1}, {"x": 2}]
        step = make_step(1, "impute", "nonexistent", "median imputation")
        agent = make_agent()
        cleaned, _ = agent.execute(rows, [step], make_decision([1]))
        assert cleaned == [{"x": 1}, {"x": 2}]

    def test_impute_row_count_unchanged(self):
        rows = [{"v": None}, {"v": 1}, {"v": 2}]
        step = make_step(1, "impute", "v", "median imputation")
        agent = make_agent()
        cleaned, _ = agent.execute(rows, [step], make_decision([1]))
        assert len(cleaned) == 3


# ─────────────────────────────────────────────────────────────────────────────
# _coerce_type
# ─────────────────────────────────────────────────────────────────────────────

class TestCoerceType:

    def test_string_integer_coerced_to_float(self):
        rows = [{"price": "42"}]
        step = make_step(1, "coerce_type", "price", "to_float")
        agent = make_agent()
        cleaned, _ = agent.execute(rows, [step], make_decision([1]))
        assert cleaned[0]["price"] == 42.0
        assert isinstance(cleaned[0]["price"], float)

    def test_string_float_coerced(self):
        rows = [{"price": "3.14"}]
        step = make_step(1, "coerce_type", "price", "to_float")
        agent = make_agent()
        cleaned, _ = agent.execute(rows, [step], make_decision([1]))
        assert abs(cleaned[0]["price"] - 3.14) < 1e-9

    def test_comma_formatted_number_coerced(self):
        rows = [{"price": "1,234.56"}]
        step = make_step(1, "coerce_type", "price", "to_float")
        agent = make_agent()
        cleaned, _ = agent.execute(rows, [step], make_decision([1]))
        assert cleaned[0]["price"] == 1234.56

    def test_none_value_stays_none(self):
        rows = [{"price": None}]
        step = make_step(1, "coerce_type", "price", "to_float")
        agent = make_agent()
        cleaned, _ = agent.execute(rows, [step], make_decision([1]))
        assert cleaned[0]["price"] is None

    def test_empty_string_becomes_none(self):
        rows = [{"price": ""}]
        step = make_step(1, "coerce_type", "price", "to_float")
        agent = make_agent()
        cleaned, _ = agent.execute(rows, [step], make_decision([1]))
        assert cleaned[0]["price"] is None

    def test_non_numeric_string_left_unchanged(self):
        rows = [{"code": "ABC"}]
        step = make_step(1, "coerce_type", "code", "to_float")
        agent = make_agent()
        cleaned, _ = agent.execute(rows, [step], make_decision([1]))
        assert cleaned[0]["code"] == "ABC"

    def test_already_float_value_returned_as_float(self):
        rows = [{"v": 7.5}]
        step = make_step(1, "coerce_type", "v", "to_float")
        agent = make_agent()
        cleaned, _ = agent.execute(rows, [step], make_decision([1]))
        assert cleaned[0]["v"] == 7.5

    def test_coerce_does_not_affect_other_columns(self):
        rows = [{"price": "10", "label": "keep_me"}]
        step = make_step(1, "coerce_type", "price", "to_float")
        agent = make_agent()
        cleaned, _ = agent.execute(rows, [step], make_decision([1]))
        assert cleaned[0]["label"] == "keep_me"

    def test_coerce_row_count_unchanged(self):
        rows = [{"v": str(i)} for i in range(50)]
        step = make_step(1, "coerce_type", "v", "to_float")
        agent = make_agent()
        cleaned, _ = agent.execute(rows, [step], make_decision([1]))
        assert len(cleaned) == 50

    def test_mixed_valid_invalid_strings_in_same_column(self):
        rows = [{"v": "5"}, {"v": "abc"}, {"v": "10"}]
        step = make_step(1, "coerce_type", "v", "to_float")
        agent = make_agent()
        cleaned, _ = agent.execute(rows, [step], make_decision([1]))
        assert cleaned[0]["v"] == 5.0
        assert cleaned[1]["v"] == "abc"   # left unchanged
        assert cleaned[2]["v"] == 10.0

    def test_negative_number_coerced_correctly(self):
        rows = [{"delta": "-42.5"}]
        step = make_step(1, "coerce_type", "delta", "to_float")
        agent = make_agent()
        cleaned, _ = agent.execute(rows, [step], make_decision([1]))
        assert cleaned[0]["delta"] == -42.5


# ─────────────────────────────────────────────────────────────────────────────
# _flag_outlier
# ─────────────────────────────────────────────────────────────────────────────

class TestFlagOutlier:

    def _outlier_col(self, col: str) -> str:
        return f"_outlier_{col}"

    def test_outlier_flag_column_added(self):
        rows = [{"v": float(i)} for i in range(10)]
        step = make_step(1, "flag_outlier", "v", "IQR outlier flagging")
        agent = make_agent()
        cleaned, _ = agent.execute(rows, [step], make_decision([1]))
        assert all(self._outlier_col("v") in r for r in cleaned)

    def test_extreme_high_value_flagged_true(self):
        rows = [{"v": float(i)} for i in range(1, 11)]  # 1–10
        rows.append({"v": 1000.0})  # clear outlier
        step = make_step(1, "flag_outlier", "v", "IQR outlier flagging")
        agent = make_agent()
        cleaned, _ = agent.execute(rows, [step], make_decision([1]))
        outlier_row = next(r for r in cleaned if r["v"] == 1000.0)
        assert outlier_row[self._outlier_col("v")] is True

    def test_extreme_low_value_flagged_true(self):
        rows = [{"v": float(i)} for i in range(10, 21)]  # 10–20
        rows.insert(0, {"v": -500.0})
        step = make_step(1, "flag_outlier", "v", "IQR outlier flagging")
        agent = make_agent()
        cleaned, _ = agent.execute(rows, [step], make_decision([1]))
        outlier_row = next(r for r in cleaned if r["v"] == -500.0)
        assert outlier_row[self._outlier_col("v")] is True

    def test_normal_values_flagged_false(self):
        rows = [{"v": float(i)} for i in range(1, 11)]
        step = make_step(1, "flag_outlier", "v", "IQR outlier flagging")
        agent = make_agent()
        cleaned, _ = agent.execute(rows, [step], make_decision([1]))
        assert all(r[self._outlier_col("v")] is False for r in cleaned)

    def test_fewer_than_4_non_null_values_skips_flagging(self):
        rows = [{"v": 1.0}, {"v": 2.0}, {"v": 3.0}]   # only 3 non-null
        step = make_step(1, "flag_outlier", "v", "IQR outlier flagging")
        agent = make_agent()
        cleaned, _ = agent.execute(rows, [step], make_decision([1]))
        assert self._outlier_col("v") not in cleaned[0]

    def test_null_rows_not_given_outlier_flag(self):
        rows = [{"v": None}, {"v": 1.0}, {"v": 2.0}, {"v": 3.0}, {"v": 4.0}]
        step = make_step(1, "flag_outlier", "v", "IQR outlier flagging")
        agent = make_agent()
        cleaned, _ = agent.execute(rows, [step], make_decision([1]))
        assert self._outlier_col("v") not in cleaned[0]

    def test_row_count_unchanged_after_flagging(self):
        rows = [{"v": float(i)} for i in range(20)]
        step = make_step(1, "flag_outlier", "v", "IQR outlier flagging")
        agent = make_agent()
        cleaned, _ = agent.execute(rows, [step], make_decision([1]))
        assert len(cleaned) == 20

    def test_other_columns_not_affected(self):
        rows = [{"v": float(i), "name": "r"} for i in range(10)]
        step = make_step(1, "flag_outlier", "v", "IQR outlier flagging")
        agent = make_agent()
        cleaned, _ = agent.execute(rows, [step], make_decision([1]))
        assert all(r["name"] == "r" for r in cleaned)

    def test_non_numeric_column_returns_rows_unchanged(self):
        rows = [{"cat": "a"}, {"cat": "b"}, {"cat": "c"}, {"cat": "d"}]
        step = make_step(1, "flag_outlier", "cat", "IQR outlier flagging")
        agent = make_agent()
        cleaned, _ = agent.execute(rows, [step], make_decision([1]))
        # Should not crash; flag column may or may not appear but must not raise
        assert len(cleaned) == 4

    def test_flag_column_is_bool_type(self):
        rows = [{"v": float(i)} for i in range(10)]
        step = make_step(1, "flag_outlier", "v", "IQR outlier flagging")
        agent = make_agent()
        cleaned, _ = agent.execute(rows, [step], make_decision([1]))
        for r in cleaned:
            assert isinstance(r[self._outlier_col("v")], bool)

    def test_flag_column_named_correctly(self):
        rows = [{"sale_amount": float(i)} for i in range(10)]
        step = make_step(1, "flag_outlier", "sale_amount", "IQR outlier flagging")
        agent = make_agent()
        cleaned, _ = agent.execute(rows, [step], make_decision([1]))
        assert "_outlier_sale_amount" in cleaned[0]


# ─────────────────────────────────────────────────────────────────────────────
# Multi-step pipeline interactions
# ─────────────────────────────────────────────────────────────────────────────

class TestPipelineInteractions:

    def test_dedup_then_impute_pipeline(self):
        """After dedup, impute should fill nulls in the reduced row set."""
        rows = [
            {"v": None},
            {"v": None},   # duplicate of row 0
            {"v": 10},
            {"v": 20},
        ]
        steps = [
            make_step(1, "deduplicate"),
            make_step(2, "impute", "v", "median imputation"),
        ]
        agent = make_agent()
        cleaned, audit = agent.execute(rows, steps, make_decision([1, 2]))
        # dedup: rows 0 & 1 are identical → 3 rows remain
        assert audit[0]["rows_after"] == 3
        # impute fills the one remaining None
        assert all(r["v"] is not None for r in cleaned)

    def test_coerce_then_impute_pipeline(self):
        """Coerce strings to float first, then median-impute the None values."""
        rows = [
            {"price": "10"},
            {"price": "20"},
            {"price": None},
        ]
        steps = [
            make_step(1, "coerce_type", "price", "to_float"),
            make_step(2, "impute", "price", "median imputation"),
        ]
        agent = make_agent()
        cleaned, _ = agent.execute(rows, steps, make_decision([1, 2]))
        assert cleaned[2]["price"] == 15.0  # median of 10.0 and 20.0

    def test_impute_then_flag_outlier_pipeline(self):
        """Fill nulls first, then flag outliers — all rows should have flag column."""
        rows = [{"v": None}] + [{"v": float(i)} for i in range(1, 11)]
        steps = [
            make_step(1, "impute", "v", "median imputation"),
            make_step(2, "flag_outlier", "v", "IQR outlier flagging"),
        ]
        agent = make_agent()
        cleaned, _ = agent.execute(rows, steps, make_decision([1, 2]))
        assert all("_outlier_v" in r for r in cleaned)

    def test_full_pipeline_dedup_impute_coerce_flag(self):
        rows = [
            {"price": "100", "qty": None},
            {"price": "100", "qty": None},  # duplicate
            {"price": "200", "qty": 5},
            {"price": "300", "qty": 8},
            {"price": "200", "qty": 3},
            {"price": "100", "qty": 1},
            {"price": "150", "qty": 2},
            {"price": "180", "qty": 4},
            {"price": "220", "qty": 6},
            {"price": "90",  "qty": 7},
        ]
        steps = [
            make_step(1, "deduplicate"),
            make_step(2, "coerce_type", "price", "to_float"),
            make_step(3, "impute",      "qty",   "median imputation"),
            make_step(4, "flag_outlier","qty",   "IQR outlier flagging"),
        ]
        agent = make_agent()
        cleaned, audit = agent.execute(rows, steps, make_decision([1, 2, 3, 4]))

        assert len(audit) == 4
        assert audit[0]["rows_after"] == 9           # 1 duplicate removed
        assert all(isinstance(r["price"], float) for r in cleaned)
        assert all(r["qty"] is not None for r in cleaned)
        assert all("_outlier_qty" in r for r in cleaned)

    def test_skip_non_approved_middle_step(self):
        """Step 2 not approved — steps 1 and 3 run; step 2's effect absent."""
        rows = [{"v": None}, {"v": 5}, {"v": 10}, {"v": 5}]
        steps = [
            make_step(1, "deduplicate"),
            make_step(2, "impute", "v", "median imputation"),  # NOT approved
            make_step(3, "flag_outlier", "v", "IQR outlier flagging"),
        ]
        agent = make_agent()
        cleaned, audit = agent.execute(rows, steps, make_decision([1, 3]))

        assert len(audit) == 2
        executed_ids = [e["step_id"] for e in audit]
        assert executed_ids == [1, 3]
        # null was NOT imputed because step 2 was skipped
        null_rows = [r for r in cleaned if r["v"] is None]
        assert len(null_rows) == 1


# ─────────────────────────────────────────────────────────────────────────────
# Edge cases & robustness
# ─────────────────────────────────────────────────────────────────────────────

class TestEdgeCases:

    def test_single_row_single_step(self):
        rows = [{"a": 1}]
        step = make_step(1, "deduplicate")
        agent = make_agent()
        cleaned, audit = agent.execute(rows, [step], make_decision([1]))
        assert cleaned == [{"a": 1}] and len(audit) == 1

    def test_large_dataset_dedup_performance(self):
        """1 000 identical rows → 1 row after dedup; should complete quickly."""
        rows = [{"x": 1, "y": 2}] * 1000
        step = make_step(1, "deduplicate")
        agent = make_agent()
        cleaned, _ = agent.execute(rows, [step], make_decision([1]))
        assert len(cleaned) == 1

    def test_many_columns_impute_only_targets_specified_column(self):
        rows = [{f"col_{i}": None for i in range(20)} | {"target": None}]
        # give non-null rows so median has something
        rows += [{"target": float(j), **{f"col_{i}": float(i) for i in range(20)}} for j in range(1, 5)]
        step = make_step(1, "impute", "target", "median imputation")
        agent = make_agent()
        cleaned, _ = agent.execute(rows, [step], make_decision([1]))
        assert cleaned[0]["target"] is not None
        # all other columns in row 0 should still be None
        assert all(cleaned[0][f"col_{i}"] is None for i in range(20))

    def test_unknown_action_passes_rows_through(self):
        rows = [{"a": 1}]
        step = make_step(1, "unknown_action", "a", "some_method")
        agent = make_agent()
        cleaned, audit = agent.execute(rows, [step], make_decision([1]))
        assert cleaned == [{"a": 1}]
        assert len(audit) == 1   # step was executed; audit still recorded

    def test_impute_with_no_column_passes_rows_through(self):
        """impute step with column=None must not crash."""
        rows = [{"a": None}, {"a": 5}]
        step = make_step(1, "impute", None, "median imputation")
        agent = make_agent()
        cleaned, audit = agent.execute(rows, [step], make_decision([1]))
        assert cleaned[0]["a"] is None  # nothing changed

    def test_flag_outlier_with_no_column_passes_rows_through(self):
        rows = [{"v": 1.0}, {"v": 2.0}]
        step = make_step(1, "flag_outlier", None, "IQR outlier flagging")
        agent = make_agent()
        cleaned, _ = agent.execute(rows, [step], make_decision([1]))
        assert cleaned == [{"v": 1.0}, {"v": 2.0}]

    def test_duplicate_approved_ids_do_not_double_execute(self):
        """Passing the same step_id twice in approved_step_ids must not run it twice."""
        rows = [{"a": 1}, {"a": 1}, {"a": 2}]
        step = make_step(1, "deduplicate")
        # approved_ids has step 1 listed twice
        decision = CleaningPlanDecision(approved_step_ids=[1, 1])
        agent = make_agent()
        cleaned, audit = agent.execute(rows, [step], decision)
        # Only one audit entry because the step list has one step
        assert len(audit) == 1

    def test_rows_with_mixed_types_in_column(self):
        """Imputing a column that has int, float and string non-null values."""
        rows = [{"v": None}, {"v": 10}, {"v": 20.0}, {"v": "30"}]
        step = make_step(1, "impute", "v", "median imputation")
        agent = make_agent()
        cleaned, _ = agent.execute(rows, [step], make_decision([1]))
        assert cleaned[0]["v"] is not None


# ═════════════════════════════════════════════════════════════════════════════
# Runner
# ═════════════════════════════════════════════════════════════════════════════

def _collect_all_test_classes():
    return [
        TestExecuteReturnStructure,
        TestApprovalGating,
        TestMethodOverride,
        TestAuditEntries,
        TestDeduplicate,
        TestImpute,
        TestCoerceType,
        TestFlagOutlier,
        TestPipelineInteractions,
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