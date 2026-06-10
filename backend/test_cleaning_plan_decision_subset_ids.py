"""
Unit tests — Cleaning-Plan Decision with a subset of step IDs approved

Tests cover every permutation of partial approval through HITL #2:

    CleaningPlanDecision(approved_step_ids=[...])
        → CleaningExecutorAgent.execute() runs ONLY those steps
        → Skipped steps have zero effect on rows
        → Audit contains only executed step IDs
        → step_modifications apply only to approved steps

Architecture ref: architecture.md §HITL #2 — Cleaning Plan Approval
    "User can: approve all / approve some / modify a step / reject."
    "Low-confidence steps (< 0.50) unchecked by default."
    "Executes ONLY approved steps against Layer 2 Parquet."

PRD invariant: raw data (Layer 1) is NEVER modified.
    Only the approved subset may alter the working copy.

Run with:
    pytest  test_cleaning_plan_decision_subset.py -v
    python  test_cleaning_plan_decision_subset.py    # live results

Fully independent — no LLM, no DB, no Supabase, no app imports.
CleaningExecutorAgent is reproduced verbatim from cleaning_executor.py.
"""

from __future__ import annotations

import statistics
import sys
import traceback
from collections import Counter
from dataclasses import dataclass, field
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
# Stand-ins for app.models.schemas
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
    """
    HITL #2 user decision.

    approved_step_ids   : step IDs the user approved (subset of the full plan)
    step_modifications  : {step_id: {"method": "<override>"}} — user can change
                          the method for any approved step
    """
    approved_step_ids: list[int]
    step_modifications: dict[int, dict] = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────────
# CleaningExecutorAgent — verbatim copy of cleaning_executor.py
# ─────────────────────────────────────────────────────────────────────────────

class CleaningExecutorAgent:

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
                "rows_changed": (
                    before_count - after_count
                    if step.action == "deduplicate"
                    else step.rows_affected
                ),
            })

        return working, audit

    def _apply_step(self, rows, step, method):
        if step.action == "deduplicate":
            return self._deduplicate(rows)
        if step.action == "impute" and step.column:
            return self._impute(rows, step.column, method)
        if step.action == "coerce_type" and step.column:
            return self._coerce_type(rows, step.column)
        if step.action == "flag_outlier" and step.column:
            return self._flag_outlier(rows, step.column)
        return rows

    def _deduplicate(self, rows):
        seen = set()
        result = []
        for row in rows:
            key = str(sorted(row.items()))
            if key not in seen:
                seen.add(key)
                result.append(row)
        return result

    def _impute(self, rows, column, method):
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

    def _coerce_type(self, rows, column):
        result = []
        for row in rows:
            val = row.get(column)
            try:
                coerced = float(str(val).replace(",", "")) if val not in (None, "") else None
            except ValueError:
                coerced = val
            result.append({**row, column: coerced})
        return result

    def _flag_outlier(self, rows, column):
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
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def make_agent() -> CleaningExecutorAgent:
    return CleaningExecutorAgent()


def step(
    step_id: int,
    action: str = "impute",
    column: Optional[str] = "value",
    method: str = "median imputation",
    rows_affected: int = 0,
    confidence: float = 0.9,
) -> CleaningStep:
    return CleaningStep(
        step_id=step_id, action=action, column=column,
        method=method, rows_affected=rows_affected, confidence=confidence,
    )


def decide(
    approved: list[int],
    modifications: Optional[dict[int, dict]] = None,
) -> CleaningPlanDecision:
    return CleaningPlanDecision(
        approved_step_ids=approved,
        step_modifications=modifications or {},
    )


def executed_ids(audit: list[dict]) -> list[int]:
    return [e["step_id"] for e in audit]


def skipped_ids(all_steps: list[CleaningStep], audit: list[dict]) -> list[int]:
    ran = set(executed_ids(audit))
    return [s.step_id for s in all_steps if s.step_id not in ran]


# ─────────────────────────────────────────────────────────────────────────────
# Lightweight runner
# ─────────────────────────────────────────────────────────────────────────────

class _Results:
    def __init__(self) -> None:
        self.passed: list[str] = []
        self.failed: list[tuple[str, str]] = []

    def record(self, name: str, exc) -> None:
        if exc is None:
            self.passed.append(name)
        else:
            self.failed.append((name, traceback.format_exc()))

    def print_summary(self) -> None:
        total = len(self.passed) + len(self.failed)
        w = 72
        print("=" * w)
        print("  Cleaning-Plan Decision (subset) — test results")
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
# CleaningPlanDecision model — subset construction
# ─────────────────────────────────────────────────────────────────────────────

class TestDecisionModelSubset:
    """Verify the decision model correctly captures a partial approval list."""

    def test_approved_step_ids_stored_verbatim(self):
        d = decide([1, 3])
        assert d.approved_step_ids == [1, 3]

    def test_approved_step_ids_is_list(self):
        d = decide([2, 4])
        assert isinstance(d.approved_step_ids, list)

    def test_single_id_subset(self):
        d = decide([2])
        assert d.approved_step_ids == [2]

    def test_empty_approved_ids(self):
        d = decide([])
        assert d.approved_step_ids == []

    def test_all_ids_in_subset(self):
        d = decide([1, 2, 3, 4, 5])
        assert len(d.approved_step_ids) == 5

    def test_modifications_default_empty(self):
        d = decide([1])
        assert d.step_modifications == {}

    def test_modifications_stored_verbatim(self):
        mods = {2: {"method": "mode imputation"}}
        d = decide([1, 2], modifications=mods)
        assert d.step_modifications == mods

    def test_subset_does_not_include_unapproved_ids(self):
        d = decide([1, 3])
        assert 2 not in d.approved_step_ids
        assert 4 not in d.approved_step_ids

    def test_approved_ids_preserve_order(self):
        ids = [5, 2, 8, 1]
        d = decide(ids)
        assert d.approved_step_ids == ids


# ─────────────────────────────────────────────────────────────────────────────
# Audit — only approved step IDs appear
# ─────────────────────────────────────────────────────────────────────────────

class TestAuditContainsOnlyApprovedIds:

    def test_only_approved_id_in_audit(self):
        steps = [step(1), step(2), step(3)]
        rows = [{"value": 1}]
        _, audit = make_agent().execute(rows, steps, decide([2]))
        assert executed_ids(audit) == [2]

    def test_two_approved_ids_both_in_audit(self):
        steps = [step(1), step(2), step(3), step(4)]
        rows = [{"value": 1}]
        _, audit = make_agent().execute(rows, steps, decide([1, 3]))
        assert set(executed_ids(audit)) == {1, 3}

    def test_unapproved_ids_absent_from_audit(self):
        steps = [step(i) for i in range(1, 6)]
        rows = [{"value": 1}]
        _, audit = make_agent().execute(rows, steps, decide([2, 4]))
        assert 1 not in executed_ids(audit)
        assert 3 not in executed_ids(audit)
        assert 5 not in executed_ids(audit)

    def test_audit_length_equals_approved_count(self):
        steps = [step(i) for i in range(1, 7)]
        rows = [{"value": 1}]
        _, audit = make_agent().execute(rows, steps, decide([1, 3, 5]))
        assert len(audit) == 3

    def test_empty_approved_ids_produces_empty_audit(self):
        steps = [step(1), step(2), step(3)]
        rows = [{"value": None}, {"value": 5}]
        _, audit = make_agent().execute(rows, steps, decide([]))
        assert audit == []

    def test_all_approved_all_appear_in_audit(self):
        steps = [step(i) for i in range(1, 5)]
        rows = [{"value": 1}]
        _, audit = make_agent().execute(rows, steps, decide([1, 2, 3, 4]))
        assert set(executed_ids(audit)) == {1, 2, 3, 4}

    def test_audit_order_follows_step_list_not_approval_list(self):
        """Steps run in declaration order; audit must reflect that order."""
        steps = [step(3), step(1), step(2)]
        rows = [{"value": 1}]
        _, audit = make_agent().execute(rows, steps, decide([1, 2, 3]))
        assert executed_ids(audit) == [3, 1, 2]

    def test_one_approved_out_of_ten(self):
        steps = [step(i) for i in range(1, 11)]
        rows = [{"value": 1}]
        _, audit = make_agent().execute(rows, steps, decide([7]))
        assert executed_ids(audit) == [7]

    def test_nonexistent_approved_id_produces_no_audit_entry(self):
        """Approving an ID that has no matching step is silently ignored."""
        steps = [step(1), step(2)]
        rows = [{"value": 1}]
        _, audit = make_agent().execute(rows, steps, decide([99]))
        assert audit == []


# ─────────────────────────────────────────────────────────────────────────────
# Row effects — skipped steps have zero effect
# ─────────────────────────────────────────────────────────────────────────────

class TestSkippedStepsHaveNoEffect:

    def test_skipped_impute_leaves_nulls_unfilled(self):
        """Step 2 (impute revenue) is skipped — nulls must remain."""
        steps = [
            step(1, "impute", "qty",     "median imputation"),
            step(2, "impute", "revenue", "median imputation"),
        ]
        rows = [{"qty": None, "revenue": None}, {"qty": 10, "revenue": 20}]
        cleaned, _ = make_agent().execute(rows, steps, decide([1]))
        # step 1 ran → qty nulls filled; step 2 skipped → revenue still None
        assert cleaned[0]["qty"] is not None
        assert cleaned[0]["revenue"] is None

    def test_skipped_dedup_leaves_duplicates_in_place(self):
        steps = [
            step(1, "deduplicate", None, "exact row deduplication"),
            step(2, "impute",      "v",  "median imputation"),
        ]
        rows = [{"v": 5}, {"v": 5}, {"v": 10}]
        cleaned, _ = make_agent().execute(rows, steps, decide([2]))
        assert len(cleaned) == 3  # duplicates not removed

    def test_skipped_coerce_leaves_strings_unchanged(self):
        steps = [
            step(1, "coerce_type", "price", "to_float"),
            step(2, "impute",      "qty",   "median imputation"),
        ]
        rows = [{"price": "100", "qty": None}, {"price": "200", "qty": 50}]
        cleaned, _ = make_agent().execute(rows, steps, decide([2]))
        assert cleaned[0]["price"] == "100"  # still a string

    def test_skipped_flag_outlier_adds_no_flag_column(self):
        steps = [
            step(1, "impute",       "v", "median imputation"),
            step(2, "flag_outlier", "v", "IQR outlier flagging"),
        ]
        rows = [{"v": None}] + [{"v": float(i)} for i in range(1, 11)]
        cleaned, _ = make_agent().execute(rows, steps, decide([1]))
        assert "_outlier_v" not in cleaned[0]

    def test_skipped_middle_step_effect_absent(self):
        """Approve steps 1 and 3, skip step 2 — step 2's column untouched."""
        steps = [
            step(1, "impute", "a", "median imputation"),
            step(2, "impute", "b", "median imputation"),   # skipped
            step(3, "impute", "c", "median imputation"),
        ]
        rows = [{"a": None, "b": None, "c": None},
                {"a": 10, "b": 20, "c": 30}]
        cleaned, _ = make_agent().execute(rows, steps, decide([1, 3]))
        assert cleaned[0]["a"] is not None   # step 1 ran
        assert cleaned[0]["b"] is None       # step 2 skipped
        assert cleaned[0]["c"] is not None   # step 3 ran

    def test_no_approved_steps_rows_identical_to_input(self):
        steps = [step(1, "deduplicate", None, "exact row deduplication"),
                 step(2, "impute", "v", "median imputation")]
        rows = [{"v": 1}, {"v": 1}, {"v": 2}]
        cleaned, _ = make_agent().execute(rows, steps, decide([]))
        assert cleaned == [{"v": 1}, {"v": 1}, {"v": 2}]

    def test_skipped_dedup_does_not_change_row_count(self):
        steps = [step(1, "deduplicate", None, "exact row deduplication"),
                 step(2, "impute", "v", "median imputation")]
        rows = [{"v": 5}] * 10
        cleaned, _ = make_agent().execute(rows, steps, decide([2]))
        assert len(cleaned) == 10

    def test_approved_steps_still_run_when_others_skipped(self):
        steps = [step(1, "impute", "x", "median imputation"),
                 step(2, "impute", "y", "median imputation"),
                 step(3, "impute", "z", "median imputation")]
        rows = [{"x": None, "y": None, "z": None},
                {"x": 10, "y": 20, "z": 30}]
        cleaned, _ = make_agent().execute(rows, steps, decide([1, 3]))
        assert cleaned[0]["x"] is not None
        assert cleaned[0]["z"] is not None


# ─────────────────────────────────────────────────────────────────────────────
# Specific subset patterns
# ─────────────────────────────────────────────────────────────────────────────

class TestSubsetPatterns:

    def _five_step_plan(self) -> list[CleaningStep]:
        return [
            step(1, "deduplicate",  None,      "exact row deduplication", rows_affected=0),
            step(2, "impute",       "revenue", "median imputation",       rows_affected=50),
            step(3, "coerce_type",  "price",   "to_float",                rows_affected=100),
            step(4, "impute",       "qty",     "mode imputation",         rows_affected=20),
            step(5, "flag_outlier", "revenue", "IQR outlier flagging",    rows_affected=0),
        ]

    def _rows(self) -> list[dict]:
        base = [{"revenue": float(i), "price": str(i * 10), "qty": i % 3 or None}
                for i in range(1, 11)]
        base.append({"revenue": None, "price": "5", "qty": 2})
        return base

    # ── approve only first step ───────────────────────────────────────────────

    def test_approve_first_only_dedup_runs(self):
        rows = [{"v": 1}] * 3 + [{"v": 2}]
        steps = [step(1, "deduplicate", None, "exact row deduplication"),
                 step(2, "impute", "v", "median imputation")]
        cleaned, audit = make_agent().execute(rows, steps, decide([1]))
        assert len(cleaned) == 2
        assert executed_ids(audit) == [1]

    def test_approve_first_only_impute_column_untouched(self):
        rows = [{"v": None}, {"v": 10}]
        steps = [step(1, "deduplicate", None, "exact row deduplication"),
                 step(2, "impute", "v", "median imputation")]
        cleaned, _ = make_agent().execute(rows, steps, decide([1]))
        assert cleaned[0]["v"] is None

    # ── approve only last step ────────────────────────────────────────────────

    def test_approve_last_only_earlier_steps_skipped(self):
        steps = self._five_step_plan()
        rows = self._rows()
        _, audit = make_agent().execute(rows, steps, decide([5]))
        assert executed_ids(audit) == [5]

    def test_approve_last_only_dedup_not_run(self):
        steps = self._five_step_plan()
        rows = [{"revenue": 1.0, "price": "10", "qty": 1}] * 3
        cleaned, _ = make_agent().execute(rows, steps, decide([5]))
        assert len(cleaned) == 3   # duplicates remain

    # ── approve only middle step ──────────────────────────────────────────────

    def test_approve_middle_step_only(self):
        steps = self._five_step_plan()
        rows = self._rows()
        _, audit = make_agent().execute(rows, steps, decide([3]))
        assert executed_ids(audit) == [3]

    def test_approve_middle_coerce_converts_price(self):
        steps = self._five_step_plan()
        rows = [{"revenue": 1.0, "price": "100", "qty": 1}]
        cleaned, _ = make_agent().execute(rows, steps, decide([3]))
        assert cleaned[0]["price"] == 100.0

    # ── approve first and last, skip middle ───────────────────────────────────

    def test_approve_first_and_last_skips_middle_three(self):
        steps = self._five_step_plan()
        rows = self._rows()
        _, audit = make_agent().execute(rows, steps, decide([1, 5]))
        assert set(executed_ids(audit)) == {1, 5}

    def test_first_and_last_approved_middle_impute_columns_unchanged(self):
        steps = self._five_step_plan()
        rows = [{"revenue": None, "price": "10", "qty": None},
                {"revenue": 5.0,  "price": "20", "qty": 2}]
        cleaned, _ = make_agent().execute(rows, steps, decide([1, 5]))
        assert cleaned[0]["revenue"] is None  # impute(revenue) skipped
        assert cleaned[0]["qty"] is None      # impute(qty) skipped

    # ── approve alternate steps ───────────────────────────────────────────────

    def test_approve_odd_steps_1_3_5(self):
        steps = self._five_step_plan()
        rows = self._rows()
        _, audit = make_agent().execute(rows, steps, decide([1, 3, 5]))
        assert set(executed_ids(audit)) == {1, 3, 5}

    def test_approve_even_steps_2_4(self):
        steps = self._five_step_plan()
        rows = self._rows()
        _, audit = make_agent().execute(rows, steps, decide([2, 4]))
        assert set(executed_ids(audit)) == {2, 4}

    def test_odd_approved_even_skipped_row_effects_correct(self):
        """Steps 2 and 4 skipped — revenue and qty nulls must remain."""
        steps = self._five_step_plan()
        rows = [{"revenue": None, "price": "5", "qty": None},
                {"revenue": 10.0, "price": "10", "qty": 3}]
        cleaned, _ = make_agent().execute(rows, steps, decide([1, 3, 5]))
        assert cleaned[0]["revenue"] is None
        assert cleaned[0]["qty"] is None

    # ── approve consecutive subset ────────────────────────────────────────────

    def test_approve_steps_2_3_4_consecutive(self):
        steps = self._five_step_plan()
        rows = self._rows()
        _, audit = make_agent().execute(rows, steps, decide([2, 3, 4]))
        assert set(executed_ids(audit)) == {2, 3, 4}

    def test_consecutive_subset_dedup_not_run(self):
        steps = self._five_step_plan()
        rows = [{"revenue": 1.0, "price": "10", "qty": 1}] * 4
        cleaned, _ = make_agent().execute(rows, steps, decide([2, 3, 4]))
        assert len(cleaned) == 4


# ─────────────────────────────────────────────────────────────────────────────
# Low-confidence steps defaulting to unapproved
# ─────────────────────────────────────────────────────────────────────────────

class TestLowConfidenceDefaultBehaviour:
    """
    From architecture.md: "Low-confidence steps (< 0.50) unchecked by default."
    The agent itself doesn't check confidence — that's the UI's job.
    These tests verify that when the UI omits low-confidence step IDs from
    approved_step_ids, they are correctly skipped by the executor.
    """

    def test_low_confidence_step_skipped_when_not_in_approved(self):
        steps = [
            step(1, "impute", "v", "median imputation", confidence=0.30),  # red — UI unchecks
            step(2, "impute", "w", "median imputation", confidence=0.90),  # green — checked
        ]
        rows = [{"v": None, "w": None}, {"v": 10, "w": 20}]
        cleaned, audit = make_agent().execute(rows, steps, decide([2]))
        assert cleaned[0]["v"] is None    # low-confidence step skipped
        assert cleaned[0]["w"] is not None  # high-confidence step ran
        assert executed_ids(audit) == [2]

    def test_low_confidence_step_still_runs_if_user_explicitly_approves(self):
        """User can override the default and approve a low-confidence step."""
        steps = [step(1, "impute", "v", "median imputation", confidence=0.30)]
        rows = [{"v": None}, {"v": 10}]
        cleaned, audit = make_agent().execute(rows, steps, decide([1]))
        assert cleaned[0]["v"] is not None
        assert executed_ids(audit) == [1]

    def test_mixed_confidence_plan_user_approves_only_high_confidence(self):
        """Simulate the default UI state: only high-confidence steps checked."""
        steps = [
            step(1, "deduplicate",  None, "exact row deduplication", confidence=0.95),
            step(2, "impute",       "v",  "median imputation",       confidence=0.40),  # red
            step(3, "impute",       "w",  "median imputation",       confidence=0.85),
            step(4, "flag_outlier", "v",  "IQR outlier flagging",    confidence=0.45),  # red
            step(5, "coerce_type",  "x",  "to_float",                confidence=0.72),
        ]
        rows = [{"v": None, "w": None, "x": "10"}, {"v": 5.0, "w": 8.0, "x": "20"}]
        # UI auto-approves steps >= 0.50: 1, 3, 5
        cleaned, audit = make_agent().execute(rows, steps, decide([1, 3, 5]))
        assert set(executed_ids(audit)) == {1, 3, 5}
        assert cleaned[0]["v"] is None      # step 2 skipped
        assert cleaned[0]["w"] is not None  # step 3 ran
        assert cleaned[0]["x"] == 10.0     # step 5 ran

    def test_all_low_confidence_produces_empty_audit(self):
        """All steps are red — UI leaves them unchecked — no execution."""
        steps = [
            step(1, "impute", "a", "median imputation", confidence=0.20),
            step(2, "impute", "b", "median imputation", confidence=0.35),
        ]
        rows = [{"a": None, "b": None}, {"a": 10, "b": 20}]
        cleaned, audit = make_agent().execute(rows, steps, decide([]))
        assert audit == []
        assert cleaned[0]["a"] is None
        assert cleaned[0]["b"] is None


# ─────────────────────────────────────────────────────────────────────────────
# step_modifications apply only to approved steps
# ─────────────────────────────────────────────────────────────────────────────

class TestModificationsOnSubset:

    def test_modification_on_approved_step_takes_effect(self):
        """User approves step 2 and overrides its method."""
        steps = [
            step(1, "impute", "a", "median imputation"),
            step(2, "impute", "b", "median imputation"),
        ]
        rows = [{"a": None, "b": None}, {"a": "x", "b": "x"}, {"a": "y", "b": "y"}]
        _, audit = make_agent().execute(
            rows, steps,
            decide([2], modifications={2: {"method": "mode imputation"}}),
        )
        assert audit[0]["method"] == "mode imputation"

    def test_modification_on_skipped_step_has_no_effect(self):
        """Step 1 is skipped — its modification must not be applied."""
        steps = [
            step(1, "impute", "a", "median imputation"),
            step(2, "impute", "b", "median imputation"),
        ]
        rows = [{"a": None, "b": None}, {"a": 10, "b": 20}]
        cleaned, audit = make_agent().execute(
            rows, steps,
            decide([2], modifications={1: {"method": "mode imputation"}}),
        )
        assert executed_ids(audit) == [2]
        assert cleaned[0]["a"] is None   # step 1 still skipped

    def test_modification_only_applies_to_its_own_step(self):
        """Override on step 2 must not bleed into step 3."""
        steps = [
            step(1, "impute", "a", "median imputation"),
            step(2, "impute", "b", "median imputation"),
            step(3, "impute", "c", "median imputation"),
        ]
        rows = [{"a": None, "b": None, "c": None},
                {"a": 10, "b": 20, "c": 30}]
        _, audit = make_agent().execute(
            rows, steps,
            decide([1, 2, 3], modifications={2: {"method": "mode imputation"}}),
        )
        by_id = {e["step_id"]: e for e in audit}
        assert by_id[1]["method"] == "median imputation"
        assert by_id[2]["method"] == "mode imputation"
        assert by_id[3]["method"] == "median imputation"

    def test_multiple_modifications_on_multiple_approved_steps(self):
        steps = [
            step(1, "impute", "a", "median imputation"),
            step(2, "impute", "b", "median imputation"),
            step(3, "impute", "c", "median imputation"),
        ]
        rows = [{"a": None, "b": None, "c": None},
                {"a": "x", "b": "x", "c": "x"},
                {"a": "y", "b": "y", "c": "y"}]
        mods = {1: {"method": "mode imputation"}, 3: {"method": "mode imputation"}}
        _, audit = make_agent().execute(rows, steps, decide([1, 2, 3], modifications=mods))
        by_id = {e["step_id"]: e for e in audit}
        assert by_id[1]["method"] == "mode imputation"
        assert by_id[2]["method"] == "median imputation"
        assert by_id[3]["method"] == "mode imputation"

    def test_modification_changes_actual_fill_value(self):
        """median vs mode give different results on [1, 2, 3, 10, 10]."""
        steps = [step(1, "impute", "v", "median imputation")]
        rows = [{"v": None}, {"v": 1}, {"v": 2}, {"v": 3}, {"v": 10}, {"v": 10}]
        cleaned_median, _ = make_agent().execute(rows, steps, decide([1]))
        cleaned_mode, _ = make_agent().execute(
            rows, steps, decide([1], modifications={1: {"method": "mode imputation"}})
        )
        assert cleaned_median[0]["v"] != cleaned_mode[0]["v"]

    def test_modification_on_unapproved_step_never_runs(self):
        """Modification for step 3, but step 3 is not approved → no effect."""
        steps = [
            step(1, "impute", "a", "median imputation"),
            step(2, "impute", "b", "median imputation"),
            step(3, "impute", "c", "median imputation"),
        ]
        rows = [{"a": None, "b": None, "c": None},
                {"a": 10, "b": 20, "c": 30}]
        cleaned, audit = make_agent().execute(
            rows, steps,
            decide([1, 2], modifications={3: {"method": "mode imputation"}}),
        )
        assert 3 not in executed_ids(audit)
        assert cleaned[0]["c"] is None   # step 3 never ran


# ─────────────────────────────────────────────────────────────────────────────
# Audit entry correctness for subsets
# ─────────────────────────────────────────────────────────────────────────────

class TestAuditCorrectnessForSubsets:

    def test_audit_rows_before_reflects_state_after_prior_approved_steps(self):
        """
        Step 1 (dedup) removes rows → step 3's rows_before must reflect the
        post-dedup count, not the original count.
        """
        steps = [
            step(1, "deduplicate", None, "exact row deduplication"),
            step(2, "impute",      "v",  "median imputation"),   # skipped
            step(3, "impute",      "w",  "median imputation"),
        ]
        rows = [{"v": None, "w": None}] * 5 + [{"v": 10, "w": 20}]
        _, audit = make_agent().execute(rows, steps, decide([1, 3]))
        by_id = {e["step_id"]: e for e in audit}
        # dedup sees 6 rows, produces 2 (one null-v row + one distinct row)
        assert by_id[1]["rows_before"] == 6
        assert by_id[3]["rows_before"] == by_id[1]["rows_after"]

    def test_skipped_step_rows_before_not_in_audit(self):
        """Skipped steps have no audit entry at all — cannot check rows_before."""
        steps = [step(1), step(2), step(3)]
        rows = [{"value": 1}]
        _, audit = make_agent().execute(rows, steps, decide([1, 3]))
        ids_in_audit = {e["step_id"] for e in audit}
        assert 2 not in ids_in_audit

    def test_audit_entry_has_all_required_keys_for_subset(self):
        required = {"step_id", "action", "column", "method", "rationale",
                    "confidence", "rows_before", "rows_after", "rows_changed"}
        steps = [step(1), step(2)]
        rows = [{"value": 1}]
        _, audit = make_agent().execute(rows, steps, decide([1]))
        assert required.issubset(audit[0].keys())

    def test_rows_changed_is_correct_for_impute_subset(self):
        """rows_changed for non-dedup steps echoes step.rows_affected."""
        steps = [
            step(1, "impute", "v", "median imputation", rows_affected=7),
            step(2, "impute", "w", "median imputation", rows_affected=3),
        ]
        rows = [{"v": None, "w": None}, {"v": 10, "w": 20}]
        _, audit = make_agent().execute(rows, steps, decide([1]))
        assert audit[0]["rows_changed"] == 7

    def test_rows_changed_is_correct_for_dedup_subset(self):
        steps = [
            step(1, "deduplicate", None, "exact row deduplication"),
            step(2, "impute", "v", "median imputation"),
        ]
        rows = [{"v": 1}] * 4 + [{"v": 2}]
        _, audit = make_agent().execute(rows, steps, decide([1]))
        assert audit[0]["rows_changed"] == 3   # 5 → 2, change = 3


# ─────────────────────────────────────────────────────────────────────────────
# Row immutability — input rows never mutated
# ─────────────────────────────────────────────────────────────────────────────

class TestInputImmutability:
    """
    PRD invariant: raw data is never modified.
    The executor must deep-copy rows before any step runs.
    Approving a subset must not mutate input rows.
    """

    def test_input_rows_unchanged_after_subset_execution(self):
        steps = [step(1, "impute", "v", "median imputation")]
        original = [{"v": None}, {"v": 10}]
        make_agent().execute(original, steps, decide([1]))
        assert original[0]["v"] is None

    def test_input_rows_unchanged_with_empty_approval(self):
        steps = [step(1, "impute", "v", "median imputation")]
        original = [{"v": None}, {"v": 10}]
        make_agent().execute(original, steps, decide([]))
        assert original[0]["v"] is None

    def test_cleaned_rows_are_independent_of_input(self):
        steps = [step(1, "impute", "v", "median imputation")]
        original = [{"v": None}, {"v": 10}]
        cleaned, _ = make_agent().execute(original, steps, decide([1]))
        cleaned[0]["v"] = 999
        assert original[0]["v"] is None

    def test_skipped_steps_do_not_mutate_input_either(self):
        steps = [step(1, "impute", "v", "median imputation"),
                 step(2, "impute", "v", "mode imputation")]
        original = [{"v": None}, {"v": 5}]
        make_agent().execute(original, steps, decide([2]))
        assert original[0]["v"] is None


# ─────────────────────────────────────────────────────────────────────────────
# Real-world HITL #2 scenarios
# ─────────────────────────────────────────────────────────────────────────────

class TestRealWorldHITLScenarios:

    def test_finance_user_approves_dedup_and_revenue_impute_skips_outlier(self):
        """
        Finance dataset: user approves dedup (certain) and revenue imputation
        (confident), but skips outlier flagging (wants to review first).
        """
        steps = [
            step(1, "deduplicate",  None,      "exact row deduplication", confidence=0.95),
            step(2, "impute",       "revenue", "median imputation",       confidence=0.88),
            step(3, "flag_outlier", "revenue", "IQR outlier flagging",    confidence=0.62),
        ]
        rows = (
            [{"revenue": None}] +
            [{"revenue": float(i)} for i in range(1, 10)] +
            [{"revenue": 5.0}]   # duplicate of i=5
        )
        original_count = len(rows)   # 11
        cleaned, audit = make_agent().execute(rows, steps, decide([1, 2]))
        assert set(executed_ids(audit)) == {1, 2}
        # dedup ran → 1 duplicate removed
        assert len(cleaned) == original_count - 1
        # impute ran → no None remaining
        assert all(r["revenue"] is not None for r in cleaned)
        # outlier flag did NOT run → no _outlier_revenue key on any row
        assert all("_outlier_revenue" not in r for r in cleaned)

    def test_healthcare_user_skips_low_confidence_imputation(self):
        """
        Healthcare dataset: user skips the low-confidence LOS imputation
        but approves dedup and coerce of the date string.
        """
        steps = [
            step(1, "deduplicate",  None,   "exact row deduplication", confidence=0.95),
            step(2, "impute",       "los",  "median imputation",       confidence=0.38),  # red
            step(3, "coerce_type",  "date", "to_float",                confidence=0.72),
        ]
        rows = [{"los": None, "date": "20240101"},
                {"los": 3.5,  "date": "20240102"},
                {"los": 4.0,  "date": "20240103"}]
        cleaned, audit = make_agent().execute(rows, steps, decide([1, 3]))
        assert set(executed_ids(audit)) == {1, 3}
        assert cleaned[0]["los"] is None       # step 2 skipped
        assert cleaned[0]["date"] == 20240101.0  # step 3 ran

    def test_retail_user_approves_only_coerce_and_flag(self):
        """
        Retail: user trusts the coerce and outlier flag but rejects imputation
        for SKU quantity (prefers to fill manually).
        """
        steps = [
            step(1, "impute",       "qty",   "median imputation",    confidence=0.75),
            step(2, "coerce_type",  "price", "to_float",             confidence=0.85),
            step(3, "flag_outlier", "price", "IQR outlier flagging", confidence=0.70),
        ]
        rows = [{"qty": None, "price": str(i * 10)} for i in range(1, 12)]
        cleaned, audit = make_agent().execute(rows, steps, decide([2, 3]))
        assert set(executed_ids(audit)) == {2, 3}
        assert cleaned[0]["qty"] is None        # step 1 skipped
        assert isinstance(cleaned[0]["price"], float)  # step 2 ran
        assert "_outlier_price" in cleaned[0]   # step 3 ran

    def test_user_approves_single_step_out_of_six(self):
        """User only confident about dedup — approves nothing else."""
        steps = [step(i + 1) for i in range(6)]
        steps[0] = step(1, "deduplicate", None, "exact row deduplication")
        rows = [{"value": 1}] * 5 + [{"value": 2}]
        cleaned, audit = make_agent().execute(rows, steps, decide([1]))
        assert len(audit) == 1
        assert audit[0]["step_id"] == 1
        assert len(cleaned) == 2

    def test_user_modifies_and_approves_subset(self):
        """
        User approves steps 1 and 3, and changes step 1's method from median to mode.
        """
        steps = [
            step(1, "impute", "category", "median imputation"),
            step(2, "impute", "revenue",  "median imputation"),
            step(3, "impute", "notes",    "median imputation"),
        ]
        rows = [{"category": None, "revenue": None, "notes": None},
                {"category": "A", "revenue": 10, "notes": "A"},
                {"category": "A", "revenue": 20, "notes": "B"}]
        _, audit = make_agent().execute(
            rows, steps,
            decide([1, 3], modifications={1: {"method": "mode imputation"}}),
        )
        by_id = {e["step_id"]: e for e in audit}
        assert set(by_id.keys()) == {1, 3}
        assert by_id[1]["method"] == "mode imputation"
        assert by_id[3]["method"] == "median imputation"
        assert 2 not in by_id


# ─────────────────────────────────────────────────────────────────────────────
# Edge cases
# ─────────────────────────────────────────────────────────────────────────────

class TestEdgeCases:

    def test_approve_subset_from_single_step_plan(self):
        steps = [step(1, "impute", "v", "median imputation")]
        rows = [{"v": None}, {"v": 5}]
        cleaned, audit = make_agent().execute(rows, steps, decide([1]))
        assert len(audit) == 1
        assert cleaned[0]["v"] is not None

    def test_approve_subset_from_single_step_plan_skipped(self):
        steps = [step(1, "impute", "v", "median imputation")]
        rows = [{"v": None}, {"v": 5}]
        cleaned, audit = make_agent().execute(rows, steps, decide([]))
        assert audit == []
        assert cleaned[0]["v"] is None

    def test_duplicate_approved_id_does_not_double_run(self):
        """If approved_step_ids contains the same id twice, step runs once."""
        steps = [step(1, "deduplicate", None, "exact row deduplication")]
        rows = [{"v": 1}] * 4 + [{"v": 2}]
        cleaned, audit = make_agent().execute(rows, steps, decide([1, 1]))
        assert len(audit) == 1
        assert len(cleaned) == 2   # dedup ran once, not twice

    def test_approved_id_larger_than_all_step_ids_silently_ignored(self):
        steps = [step(1), step(2)]
        rows = [{"value": 1}]
        _, audit = make_agent().execute(rows, steps, decide([99]))
        assert audit == []

    def test_approved_id_zero_not_in_plan_silently_ignored(self):
        steps = [step(1), step(2)]
        rows = [{"value": 1}]
        _, audit = make_agent().execute(rows, steps, decide([0]))
        assert audit == []

    def test_subset_on_empty_row_list_returns_empty_rows(self):
        steps = [step(1, "impute", "v", "median imputation")]
        cleaned, audit = make_agent().execute([], steps, decide([1]))
        assert cleaned == []
        assert len(audit) == 1  # step executed (on 0 rows)

    def test_large_plan_tiny_subset(self):
        steps = [step(i + 1) for i in range(20)]
        rows = [{"value": float(i)} for i in range(5)]
        _, audit = make_agent().execute(rows, steps, decide([10]))
        assert executed_ids(audit) == [10]
        assert len(audit) == 1

    def test_subset_is_full_set_all_steps_run(self):
        steps = [
            step(1, "deduplicate", None, "exact row deduplication"),
            step(2, "impute", "v", "median imputation"),
        ]
        rows = [{"v": None}] * 2 + [{"v": 10}]
        cleaned, audit = make_agent().execute(rows, steps, decide([1, 2]))
        assert set(executed_ids(audit)) == {1, 2}
        assert all(r["v"] is not None for r in cleaned)


# ═════════════════════════════════════════════════════════════════════════════
# Runner
# ═════════════════════════════════════════════════════════════════════════════

def _collect_all_test_classes():
    return [
        TestDecisionModelSubset,
        TestAuditContainsOnlyApprovedIds,
        TestSkippedStepsHaveNoEffect,
        TestSubsetPatterns,
        TestLowConfidenceDefaultBehaviour,
        TestModificationsOnSubset,
        TestAuditCorrectnessForSubsets,
        TestInputImmutability,
        TestRealWorldHITLScenarios,
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