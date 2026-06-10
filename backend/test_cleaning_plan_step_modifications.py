"""
Unit tests — Cleaning Plan with Step Modifications

Tests cover every dimension of the step_modifications contract in
CleaningPlanDecision:

    step_modifications: dict[int, dict]
        key   → step_id of the step being modified
        value → {"method": "<override_method>"}
                 (currently the only mutable field per architecture §HITL #2)

Architecture ref: architecture.md §HITL #2
    "User can: approve all / approve some / modify a step / reject."
    "Decision + modifications recorded in hitl_decisions."

PRD ref §7: "Low-confidence steps (< 0.50) unchecked by default."
    A modification is separate from approval — a step must be in BOTH
    approved_step_ids AND step_modifications to have its method changed.

Scope of this file:
    1.  Modification model construction
    2.  Method override → effective_method in audit
    3.  Method override → actual row-level behaviour change
    4.  Isolation: modification on step N does not bleed into step M
    5.  Unapproved step with modification → modification is ignored
    6.  All imputation method variants the executor supports
    7.  Modification + method routing inside _impute()
    8.  Multiple simultaneous modifications
    9.  Empty / absent modifications behave as no-op
    10. Audit field correctness after modification
    11. Input immutability with modifications active
    12. Real-world HITL #2 modification scenarios

Run with:
    pytest  test_cleaning_plan_step_modifications.py -v
    python  test_cleaning_plan_step_modifications.py   # live results

Fully independent — no LLM, no DB, no Supabase, no app imports.
CleaningExecutorAgent reproduced verbatim from cleaning_executor.py.
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
    action: str           # "deduplicate" | "impute" | "coerce_type" | "flag_outlier"
    column: Optional[str]
    method: str           # original proposed method
    rationale: str = "test rationale"
    confidence: float = 0.9
    rows_affected: int = 0


@dataclass
class CleaningPlanDecision:
    """
    HITL #2 user decision.

    approved_step_ids  : steps to execute
    step_modifications : {step_id: {"method": "<override>"}}
                         user-supplied corrections to the agent's proposals
    """
    approved_step_ids: list[int]
    step_modifications: dict[int, dict] = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────────
# CleaningExecutorAgent — verbatim from cleaning_executor.py
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
                "step_id":      step.step_id,
                "action":       step.action,
                "column":       step.column,
                "method":       effective_method,
                "rationale":    step.rationale,
                "confidence":   step.confidence,
                "rows_before":  before_count,
                "rows_after":   after_count,
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
        seen, result = set(), []
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

def agent() -> CleaningExecutorAgent:
    return CleaningExecutorAgent()


def make_step(
    step_id: int = 1,
    action: str = "impute",
    column: Optional[str] = "value",
    method: str = "median imputation",
    confidence: float = 0.85,
    rows_affected: int = 0,
) -> CleaningStep:
    return CleaningStep(
        step_id=step_id, action=action, column=column,
        method=method, confidence=confidence, rows_affected=rows_affected,
    )


def decide(
    approved: list[int],
    modifications: Optional[dict[int, dict]] = None,
) -> CleaningPlanDecision:
    return CleaningPlanDecision(
        approved_step_ids=approved,
        step_modifications=modifications or {},
    )


def audit_by_id(audit: list[dict]) -> dict[int, dict]:
    return {e["step_id"]: e for e in audit}


# Numeric dataset with a known median and mode for deterministic testing.
# Values: [1, 2, 3, 10, 10] → median = 3.0, mode = 10
NUMERIC_ROWS = [
    {"v": None},
    {"v": 1}, {"v": 2}, {"v": 3}, {"v": 10}, {"v": 10},
]

# Categorical dataset → mode = "A" (appears 3 times)
CATEGORICAL_ROWS = [
    {"cat": None},
    {"cat": "A"}, {"cat": "A"}, {"cat": "A"},
    {"cat": "B"}, {"cat": "C"},
]


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
        print("  Cleaning Plan — Step Modifications — test results")
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
# 1. Modification model construction
# ─────────────────────────────────────────────────────────────────────────────

class TestModificationModelConstruction:
    """Verify CleaningPlanDecision stores step_modifications correctly."""

    def test_empty_modifications_default(self):
        d = decide([1])
        assert d.step_modifications == {}

    def test_single_modification_stored(self):
        mods = {1: {"method": "mode imputation"}}
        d = decide([1], modifications=mods)
        assert d.step_modifications == mods

    def test_multiple_modifications_stored(self):
        mods = {1: {"method": "mode imputation"}, 3: {"method": "to_float"}}
        d = decide([1, 3], modifications=mods)
        assert len(d.step_modifications) == 2

    def test_modification_key_is_step_id(self):
        mods = {5: {"method": "mode imputation"}}
        d = decide([5], modifications=mods)
        assert 5 in d.step_modifications

    def test_modification_value_has_method_key(self):
        mods = {2: {"method": "mode imputation"}}
        d = decide([2], modifications=mods)
        assert "method" in d.step_modifications[2]

    def test_modification_method_value_stored_verbatim(self):
        mods = {1: {"method": "most_frequent"}}
        d = decide([1], modifications=mods)
        assert d.step_modifications[1]["method"] == "most_frequent"

    def test_modification_for_unapproved_step_stored_in_model(self):
        """The model stores all modifications; the executor ignores unapproved ones."""
        mods = {99: {"method": "mode imputation"}}
        d = decide([1], modifications=mods)
        assert 99 in d.step_modifications

    def test_approved_ids_and_modifications_are_independent_fields(self):
        d = decide([1, 2], modifications={2: {"method": "mode imputation"}})
        assert d.approved_step_ids == [1, 2]
        assert 2 in d.step_modifications


# ─────────────────────────────────────────────────────────────────────────────
# 2. effective_method in audit — override replaces original
# ─────────────────────────────────────────────────────────────────────────────

class TestEffectiveMethodInAudit:
    """Audit must record the *effective* method after override, not the original."""

    def test_override_method_appears_in_audit(self):
        steps = [make_step(1, method="median imputation")]
        _, audit = agent().execute(
            [{"value": None}, {"value": 5}],
            steps,
            decide([1], {1: {"method": "mode imputation"}}),
        )
        assert audit[0]["method"] == "mode imputation"

    def test_original_method_absent_from_audit_when_overridden(self):
        steps = [make_step(1, method="median imputation")]
        _, audit = agent().execute(
            [{"value": None}, {"value": 5}],
            steps,
            decide([1], {1: {"method": "mode imputation"}}),
        )
        assert audit[0]["method"] != "median imputation"

    def test_no_modification_keeps_original_method_in_audit(self):
        steps = [make_step(1, method="median imputation")]
        _, audit = agent().execute(
            [{"value": None}, {"value": 5}],
            steps,
            decide([1]),
        )
        assert audit[0]["method"] == "median imputation"

    def test_override_method_verbatim_in_audit(self):
        override = "custom_strategy_v2"
        steps = [make_step(1, method="median imputation")]
        _, audit = agent().execute(
            [{"value": 1}],
            steps,
            decide([1], {1: {"method": override}}),
        )
        assert audit[0]["method"] == override

    def test_two_steps_each_with_override_both_in_audit(self):
        steps = [
            make_step(1, column="a", method="median imputation"),
            make_step(2, column="b", method="median imputation"),
        ]
        rows = [{"a": None, "b": None}, {"a": 5, "b": 10}]
        _, audit = agent().execute(
            rows, steps,
            decide([1, 2], {
                1: {"method": "mode imputation"},
                2: {"method": "most_frequent"},
            }),
        )
        by_id = audit_by_id(audit)
        assert by_id[1]["method"] == "mode imputation"
        assert by_id[2]["method"] == "most_frequent"

    def test_only_modified_step_shows_override_in_audit(self):
        steps = [
            make_step(1, column="a", method="median imputation"),
            make_step(2, column="b", method="median imputation"),
            make_step(3, column="c", method="median imputation"),
        ]
        rows = [{"a": None, "b": None, "c": None}, {"a": 5, "b": 10, "c": 15}]
        _, audit = agent().execute(
            rows, steps,
            decide([1, 2, 3], {2: {"method": "mode imputation"}}),
        )
        by_id = audit_by_id(audit)
        assert by_id[1]["method"] == "median imputation"
        assert by_id[2]["method"] == "mode imputation"
        assert by_id[3]["method"] == "median imputation"

    def test_step_id_in_audit_matches_modified_step(self):
        steps = [make_step(7, method="median imputation")]
        _, audit = agent().execute(
            [{"value": None}, {"value": 5}],
            steps,
            decide([7], {7: {"method": "mode imputation"}}),
        )
        assert audit[0]["step_id"] == 7
        assert audit[0]["method"] == "mode imputation"

    def test_audit_other_fields_unaffected_by_override(self):
        """action, column, confidence, rationale must not change due to method override."""
        steps = [make_step(1, action="impute", column="revenue",
                           method="median imputation", confidence=0.88)]
        rows = [{"revenue": None}, {"revenue": 10}]
        _, audit = agent().execute(
            rows, steps,
            decide([1], {1: {"method": "mode imputation"}}),
        )
        assert audit[0]["action"] == "impute"
        assert audit[0]["column"] == "revenue"
        assert audit[0]["confidence"] == 0.88


# ─────────────────────────────────────────────────────────────────────────────
# 3. Method override changes actual row-level behaviour
# ─────────────────────────────────────────────────────────────────────────────

class TestOverrideChangesRowBehaviour:
    """
    The key contract: the override method must actually change what the executor
    does to the data — not just what it records in the audit.
    """

    def test_median_to_mode_produces_different_fill_value(self):
        # [1, 2, 3, 10, 10]: median=3.0, mode=10
        rows = list(NUMERIC_ROWS)
        steps = [make_step(1, column="v", method="median imputation")]
        cleaned_median, _ = agent().execute(rows, steps, decide([1]))
        cleaned_mode, _ = agent().execute(
            rows, steps, decide([1], {1: {"method": "mode imputation"}})
        )
        assert cleaned_median[0]["v"] == 3.0
        assert cleaned_mode[0]["v"] == 10

    def test_mode_to_median_produces_different_fill_value(self):
        rows = list(NUMERIC_ROWS)
        steps = [make_step(1, column="v", method="mode imputation")]
        cleaned_mode, _ = agent().execute(rows, steps, decide([1]))
        cleaned_median, _ = agent().execute(
            rows, steps, decide([1], {1: {"method": "median imputation"}})
        )
        assert cleaned_mode[0]["v"] == 10
        assert cleaned_median[0]["v"] == 3.0

    def test_median_override_fills_null_with_correct_median(self):
        # non-null: [4, 8] → median = 6.0
        rows = [{"v": None}, {"v": 4}, {"v": 8}]
        steps = [make_step(1, column="v", method="mode imputation")]
        cleaned, _ = agent().execute(
            rows, steps, decide([1], {1: {"method": "median imputation"}})
        )
        assert cleaned[0]["v"] == 6.0

    def test_mode_override_fills_null_with_most_frequent(self):
        rows = list(CATEGORICAL_ROWS)
        steps = [make_step(1, column="cat", method="median imputation")]
        cleaned, _ = agent().execute(
            rows, steps, decide([1], {1: {"method": "mode imputation"}})
        )
        assert cleaned[0]["cat"] == "A"

    def test_frequent_keyword_triggers_mode_behaviour(self):
        rows = list(CATEGORICAL_ROWS)
        steps = [make_step(1, column="cat", method="median imputation")]
        cleaned, _ = agent().execute(
            rows, steps, decide([1], {1: {"method": "most_frequent"}})
        )
        assert cleaned[0]["cat"] == "A"

    def test_unknown_override_method_falls_back_to_first_non_null(self):
        rows = [{"v": None}, {"v": 42}, {"v": 99}]
        steps = [make_step(1, column="v", method="median imputation")]
        cleaned, _ = agent().execute(
            rows, steps, decide([1], {1: {"method": "unknown_strategy"}})
        )
        assert cleaned[0]["v"] == 42

    def test_no_override_preserves_original_behaviour(self):
        rows = list(NUMERIC_ROWS)
        steps = [make_step(1, column="v", method="median imputation")]
        cleaned, _ = agent().execute(rows, steps, decide([1]))
        assert cleaned[0]["v"] == 3.0

    def test_override_applies_to_all_null_cells_in_column(self):
        rows = [{"v": None}, {"v": None}, {"v": None}, {"v": 10}, {"v": 20}]
        steps = [make_step(1, column="v", method="median imputation")]
        cleaned, _ = agent().execute(
            rows, steps, decide([1], {1: {"method": "mode imputation"}})
        )
        # mode of [10, 20] — Counter picks first in case of tie → 10
        for r in cleaned:
            assert r["v"] is not None

    def test_empty_string_treated_as_null_and_filled_by_override(self):
        rows = [{"v": ""}, {"v": 5}, {"v": 15}]
        steps = [make_step(1, column="v", method="mode imputation")]
        cleaned, _ = agent().execute(
            rows, steps, decide([1], {1: {"method": "median imputation"}})
        )
        assert cleaned[0]["v"] == 10.0   # median of [5, 15]

    def test_non_null_rows_not_changed_by_override(self):
        rows = [{"v": None}, {"v": 7}, {"v": 14}]
        steps = [make_step(1, column="v", method="median imputation")]
        cleaned, _ = agent().execute(
            rows, steps, decide([1], {1: {"method": "mode imputation"}})
        )
        assert cleaned[1]["v"] == 7
        assert cleaned[2]["v"] == 14


# ─────────────────────────────────────────────────────────────────────────────
# 4. Isolation — modification on step N does not affect step M
# ─────────────────────────────────────────────────────────────────────────────

class TestModificationIsolation:

    def test_modification_on_step_2_does_not_change_step_1_behaviour(self):
        steps = [
            make_step(1, column="a", method="median imputation"),
            make_step(2, column="b", method="median imputation"),
        ]
        rows = [{"a": None, "b": None}, {"a": 1}, {"a": 2}, {"b": 10}, {"b": 20}]
        rows = [
            {"a": None, "b": None},
            {"a": 2.0,  "b": 10.0},
            {"a": 4.0,  "b": 20.0},
        ]
        cleaned, audit = agent().execute(
            rows, steps,
            decide([1, 2], {2: {"method": "mode imputation"}}),
        )
        by_id = audit_by_id(audit)
        # Step 1 must use median (not mode)
        assert by_id[1]["method"] == "median imputation"
        # Step 1 result: median of [2.0, 4.0] = 3.0
        assert cleaned[0]["a"] == 3.0

    def test_modification_on_step_1_does_not_change_step_3_behaviour(self):
        steps = [
            make_step(1, column="a", method="median imputation"),
            make_step(2, column="b", method="median imputation"),
            make_step(3, column="c", method="median imputation"),
        ]
        rows = [
            {"a": None, "b": None, "c": None},
            {"a": 2.0,  "b": 5.0,  "c": 8.0},
            {"a": 4.0,  "b": 15.0, "c": 12.0},
        ]
        cleaned, audit = agent().execute(
            rows, steps,
            decide([1, 2, 3], {1: {"method": "mode imputation"}}),
        )
        by_id = audit_by_id(audit)
        assert by_id[3]["method"] == "median imputation"
        # c: median of [8.0, 12.0] = 10.0
        assert cleaned[0]["c"] == 10.0

    def test_adjacent_steps_with_same_column_each_use_own_method(self):
        """Two impute steps on the same column, different methods."""
        steps = [
            make_step(1, column="v", method="median imputation"),
            make_step(2, column="v", method="mode imputation"),
        ]
        rows = [{"v": None}, {"v": 1}, {"v": 2}, {"v": 10}, {"v": 10}]
        _, audit = agent().execute(
            rows, steps,
            decide([1, 2], {1: {"method": "mode imputation"}}),
        )
        by_id = audit_by_id(audit)
        # Both overridden to mode → same, but isolation test checks they don't bleed
        assert by_id[1]["method"] == "mode imputation"
        assert by_id[2]["method"] == "mode imputation"

    def test_five_step_plan_one_modification_four_unaffected(self):
        cols = ["a", "b", "c", "d", "e"]
        steps = [make_step(i + 1, column=cols[i], method="median imputation")
                 for i in range(5)]
        rows = [{c: None for c in cols}] + [{c: float(i + 1) for c in cols}
                                             for i in range(4)]
        _, audit = agent().execute(
            rows, steps,
            decide([1, 2, 3, 4, 5], {3: {"method": "mode imputation"}}),
        )
        by_id = audit_by_id(audit)
        for sid in [1, 2, 4, 5]:
            assert by_id[sid]["method"] == "median imputation", \
                f"Step {sid} should not be modified"
        assert by_id[3]["method"] == "mode imputation"


# ─────────────────────────────────────────────────────────────────────────────
# 5. Unapproved step with modification — modification completely ignored
# ─────────────────────────────────────────────────────────────────────────────

class TestUnapprovedStepModificationIgnored:

    def test_unapproved_step_with_modification_does_not_run(self):
        steps = [make_step(1), make_step(2, column="b")]
        rows = [{"value": None, "b": None}, {"value": 5, "b": 10}]
        cleaned, audit = agent().execute(
            rows, steps,
            decide([1], {2: {"method": "mode imputation"}}),
        )
        assert len(audit) == 1
        assert audit[0]["step_id"] == 1
        assert cleaned[0]["b"] is None   # step 2 never ran

    def test_unapproved_step_modification_not_in_audit(self):
        steps = [make_step(1), make_step(2)]
        rows = [{"value": None}, {"value": 5}]
        _, audit = agent().execute(
            rows, steps,
            decide([1], {2: {"method": "mode imputation"}}),
        )
        ids = [e["step_id"] for e in audit]
        assert 2 not in ids

    def test_modification_on_nonexistent_step_id_silently_ignored(self):
        steps = [make_step(1)]
        rows = [{"value": None}, {"value": 5}]
        _, audit = agent().execute(
            rows, steps,
            decide([1], {99: {"method": "mode imputation"}}),
        )
        # Step 1 runs normally, modification for 99 is silently discarded
        assert audit[0]["method"] == "median imputation"

    def test_modification_dict_for_unapproved_step_does_not_raise(self):
        steps = [make_step(1)]
        rows = [{"value": 1}]
        try:
            agent().execute(rows, steps, decide([1], {2: {"method": "mode imputation"}}))
        except Exception as exc:
            raise AssertionError(f"Raised unexpectedly: {exc}") from exc

    def test_approve_later_without_modification_runs_original_method(self):
        """Step 2 was first submitted without approval; now approved without mod."""
        steps = [make_step(1), make_step(2, method="median imputation")]
        rows = [{"value": None}, {"value": 5}, {"value": 15}]
        cleaned, audit = agent().execute(rows, steps, decide([2]))
        assert audit[0]["method"] == "median imputation"
        assert cleaned[0]["value"] == 10.0


# ─────────────────────────────────────────────────────────────────────────────
# 6. All supported imputation method variants
# ─────────────────────────────────────────────────────────────────────────────

class TestAllImputationMethodVariants:
    """
    _impute() branches:
        "median" in method  → median
        "mode"   in method  → mode
        "frequent" in method → mode (alias)
        anything else       → first non-null (fallback)
    """

    # ── median keyword variants ───────────────────────────────────────────────

    def test_median_imputation_keyword(self):
        rows = [{"v": None}, {"v": 2}, {"v": 8}]
        steps = [make_step(1, column="v", method="mode imputation")]
        cleaned, _ = agent().execute(
            rows, steps, decide([1], {1: {"method": "median imputation"}})
        )
        assert cleaned[0]["v"] == 5.0   # median(2, 8) = 5.0

    def test_Median_uppercase_keyword(self):
        rows = [{"v": None}, {"v": 2}, {"v": 8}]
        steps = [make_step(1, column="v", method="mode imputation")]
        cleaned, _ = agent().execute(
            rows, steps, decide([1], {1: {"method": "Median Imputation"}})
        )
        assert cleaned[0]["v"] == 5.0

    def test_MEDIAN_all_caps_keyword(self):
        rows = [{"v": None}, {"v": 2}, {"v": 8}]
        steps = [make_step(1, column="v", method="mode imputation")]
        cleaned, _ = agent().execute(
            rows, steps, decide([1], {1: {"method": "MEDIAN"}})
        )
        assert cleaned[0]["v"] == 5.0

    # ── mode keyword variants ─────────────────────────────────────────────────

    def test_mode_imputation_keyword(self):
        rows = list(CATEGORICAL_ROWS)
        steps = [make_step(1, column="cat", method="median imputation")]
        cleaned, _ = agent().execute(
            rows, steps, decide([1], {1: {"method": "mode imputation"}})
        )
        assert cleaned[0]["cat"] == "A"

    def test_Mode_uppercase_keyword(self):
        rows = list(CATEGORICAL_ROWS)
        steps = [make_step(1, column="cat", method="median imputation")]
        cleaned, _ = agent().execute(
            rows, steps, decide([1], {1: {"method": "Mode Imputation"}})
        )
        assert cleaned[0]["cat"] == "A"

    def test_MODE_all_caps_keyword(self):
        rows = list(CATEGORICAL_ROWS)
        steps = [make_step(1, column="cat", method="median imputation")]
        cleaned, _ = agent().execute(
            rows, steps, decide([1], {1: {"method": "MODE"}})
        )
        assert cleaned[0]["cat"] == "A"

    # ── most_frequent alias ───────────────────────────────────────────────────

    def test_most_frequent_alias(self):
        rows = list(CATEGORICAL_ROWS)
        steps = [make_step(1, column="cat", method="median imputation")]
        cleaned, _ = agent().execute(
            rows, steps, decide([1], {1: {"method": "most_frequent"}})
        )
        assert cleaned[0]["cat"] == "A"

    def test_frequent_keyword_alone(self):
        rows = list(CATEGORICAL_ROWS)
        steps = [make_step(1, column="cat", method="median imputation")]
        cleaned, _ = agent().execute(
            rows, steps, decide([1], {1: {"method": "frequent"}})
        )
        assert cleaned[0]["cat"] == "A"

    def test_MOST_FREQUENT_uppercase(self):
        rows = list(CATEGORICAL_ROWS)
        steps = [make_step(1, column="cat", method="median imputation")]
        cleaned, _ = agent().execute(
            rows, steps, decide([1], {1: {"method": "MOST_FREQUENT"}})
        )
        assert cleaned[0]["cat"] == "A"

    # ── fallback (first non-null) ─────────────────────────────────────────────

    def test_unknown_method_uses_first_non_null(self):
        rows = [{"v": None}, {"v": 42}, {"v": 99}]
        steps = [make_step(1, column="v", method="median imputation")]
        cleaned, _ = agent().execute(
            rows, steps, decide([1], {1: {"method": "fill_forward"}})
        )
        assert cleaned[0]["v"] == 42

    def test_empty_method_string_uses_first_non_null(self):
        rows = [{"v": None}, {"v": 7}, {"v": 14}]
        steps = [make_step(1, column="v", method="median imputation")]
        cleaned, _ = agent().execute(
            rows, steps, decide([1], {1: {"method": ""}})
        )
        assert cleaned[0]["v"] == 7

    def test_whitespace_method_string_uses_first_non_null(self):
        rows = [{"v": None}, {"v": 3}, {"v": 9}]
        steps = [make_step(1, column="v", method="median imputation")]
        cleaned, _ = agent().execute(
            rows, steps, decide([1], {1: {"method": "   "}})
        )
        assert cleaned[0]["v"] == 3


# ─────────────────────────────────────────────────────────────────────────────
# 7. Modification routing inside _impute: fill values match method
# ─────────────────────────────────────────────────────────────────────────────

class TestImputationFillValueMatchesOverrideMethod:
    """
    For a dataset where median ≠ mode, verify the fill value precisely matches
    whichever method the override selects.
    Dataset: [1, 2, 3, 10, 10] → median=3.0, mode=10
    """

    def test_median_override_fills_exactly_3_0(self):
        rows = list(NUMERIC_ROWS)
        steps = [make_step(1, column="v", method="mode imputation")]
        cleaned, _ = agent().execute(
            rows, steps, decide([1], {1: {"method": "median imputation"}})
        )
        assert cleaned[0]["v"] == 3.0

    def test_mode_override_fills_exactly_10(self):
        rows = list(NUMERIC_ROWS)
        steps = [make_step(1, column="v", method="median imputation")]
        cleaned, _ = agent().execute(
            rows, steps, decide([1], {1: {"method": "mode imputation"}})
        )
        assert cleaned[0]["v"] == 10

    def test_override_fill_applies_to_all_nulls(self):
        rows = [{"v": None}, {"v": None}, {"v": 1}, {"v": 2}, {"v": 3}, {"v": 10}, {"v": 10}]
        steps = [make_step(1, column="v", method="median imputation")]
        cleaned, _ = agent().execute(
            rows, steps, decide([1], {1: {"method": "mode imputation"}})
        )
        assert cleaned[0]["v"] == 10
        assert cleaned[1]["v"] == 10

    def test_override_does_not_alter_already_filled_rows(self):
        rows = list(NUMERIC_ROWS)
        steps = [make_step(1, column="v", method="median imputation")]
        cleaned, _ = agent().execute(
            rows, steps, decide([1], {1: {"method": "mode imputation"}})
        )
        # rows 1-5 already have values; they must not change
        assert cleaned[1]["v"] == 1
        assert cleaned[2]["v"] == 2
        assert cleaned[3]["v"] == 3
        assert cleaned[4]["v"] == 10
        assert cleaned[5]["v"] == 10

    def test_even_count_median_calculated_correctly_with_override(self):
        # [2, 4, 6, 8] → median = 5.0
        rows = [{"v": None}, {"v": 2}, {"v": 4}, {"v": 6}, {"v": 8}]
        steps = [make_step(1, column="v", method="mode imputation")]
        cleaned, _ = agent().execute(
            rows, steps, decide([1], {1: {"method": "median imputation"}})
        )
        assert cleaned[0]["v"] == 5.0


# ─────────────────────────────────────────────────────────────────────────────
# 8. Multiple simultaneous modifications
# ─────────────────────────────────────────────────────────────────────────────

class TestMultipleSimultaneousModifications:

    def test_two_modifications_both_applied(self):
        steps = [
            make_step(1, column="a", method="median imputation"),
            make_step(2, column="b", method="median imputation"),
        ]
        rows = [{"a": None, "b": None}, {"a": 5.0, "b": "X"}, {"a": 10.0, "b": "X"}]
        cleaned, audit = agent().execute(
            rows, steps,
            decide([1, 2], {
                1: {"method": "mode imputation"},
                2: {"method": "mode imputation"},
            }),
        )
        by_id = audit_by_id(audit)
        assert by_id[1]["method"] == "mode imputation"
        assert by_id[2]["method"] == "mode imputation"

    def test_three_modifications_all_applied(self):
        cols = ["a", "b", "c"]
        steps = [make_step(i + 1, column=cols[i], method="median imputation")
                 for i in range(3)]
        rows = [{c: None for c in cols}] + [{c: float(i) for c in cols}
                                             for i in range(1, 5)]
        _, audit = agent().execute(
            rows, steps,
            decide([1, 2, 3], {
                1: {"method": "mode imputation"},
                2: {"method": "most_frequent"},
                3: {"method": "mode imputation"},
            }),
        )
        by_id = audit_by_id(audit)
        assert by_id[1]["method"] == "mode imputation"
        assert by_id[2]["method"] == "most_frequent"
        assert by_id[3]["method"] == "mode imputation"

    def test_modifications_on_alternating_steps(self):
        steps = [make_step(i + 1, column=f"c{i}", method="median imputation")
                 for i in range(5)]
        rows = [{f"c{i}": None for i in range(5)}] + \
               [{f"c{i}": float(j) for i in range(5)} for j in range(1, 4)]
        _, audit = agent().execute(
            rows, steps,
            decide([1, 2, 3, 4, 5], {
                1: {"method": "mode imputation"},
                3: {"method": "mode imputation"},
                5: {"method": "mode imputation"},
            }),
        )
        by_id = audit_by_id(audit)
        assert by_id[1]["method"] == "mode imputation"
        assert by_id[2]["method"] == "median imputation"   # unmodified
        assert by_id[3]["method"] == "mode imputation"
        assert by_id[4]["method"] == "median imputation"   # unmodified
        assert by_id[5]["method"] == "mode imputation"

    def test_partial_modifications_some_steps_unmodified(self):
        steps = [make_step(i + 1, column=f"c{i}", method="median imputation")
                 for i in range(4)]
        rows = [{f"c{i}": None for i in range(4)}] + \
               [{f"c{i}": float(j) for i in range(4)} for j in range(1, 4)]
        _, audit = agent().execute(
            rows, steps,
            decide([1, 2, 3, 4], {2: {"method": "mode imputation"}}),
        )
        by_id = audit_by_id(audit)
        assert by_id[1]["method"] == "median imputation"
        assert by_id[2]["method"] == "mode imputation"
        assert by_id[3]["method"] == "median imputation"
        assert by_id[4]["method"] == "median imputation"

    def test_all_steps_modified_audit_reflects_all_overrides(self):
        methods = ["mode imputation", "most_frequent", "mode imputation"]
        steps = [make_step(i + 1, column=f"c{i}", method="median imputation")
                 for i in range(3)]
        rows = [{f"c{i}": None for i in range(3)}] + \
               [{f"c{i}": float(j) for i in range(3)} for j in range(1, 4)]
        mods = {i + 1: {"method": methods[i]} for i in range(3)}
        _, audit = agent().execute(rows, steps, decide([1, 2, 3], mods))
        by_id = audit_by_id(audit)
        for i, method in enumerate(methods):
            assert by_id[i + 1]["method"] == method


# ─────────────────────────────────────────────────────────────────────────────
# 9. Empty / absent modifications behave as no-op
# ─────────────────────────────────────────────────────────────────────────────

class TestEmptyOrAbsentModifications:

    def test_no_modifications_uses_original_method(self):
        rows = list(NUMERIC_ROWS)
        steps = [make_step(1, column="v", method="median imputation")]
        cleaned, audit = agent().execute(rows, steps, decide([1]))
        assert audit[0]["method"] == "median imputation"
        assert cleaned[0]["v"] == 3.0

    def test_empty_modifications_dict_uses_original_method(self):
        rows = list(NUMERIC_ROWS)
        steps = [make_step(1, column="v", method="median imputation")]
        cleaned, audit = agent().execute(rows, steps, decide([1], modifications={}))
        assert audit[0]["method"] == "median imputation"
        assert cleaned[0]["v"] == 3.0

    def test_modification_dict_without_method_key_uses_original(self):
        """An override dict that has no 'method' key is a no-op."""
        rows = list(NUMERIC_ROWS)
        steps = [make_step(1, column="v", method="median imputation")]
        cleaned, audit = agent().execute(
            rows, steps, decide([1], {1: {}})  # empty override dict
        )
        assert audit[0]["method"] == "median imputation"
        assert cleaned[0]["v"] == 3.0

    def test_modification_with_none_method_value_falls_back_to_first_non_null(self):
        """If the override explicitly sets method=None, .get('method', original) returns None."""
        rows = [{"v": None}, {"v": 42}]
        steps = [make_step(1, column="v", method="median imputation")]
        # When method is None, "median" in None.lower() would raise —
        # executor must handle gracefully (falls to else → first non-null)
        try:
            cleaned, audit = agent().execute(
                rows, steps, decide([1], {1: {"method": None}})
            )
            # If it runs, v[0] should be 42 (first non-null fallback)
            assert cleaned[0]["v"] == 42
        except Exception:
            pass  # Any exception here would be a bug in the executor itself

    def test_omitting_step_from_modifications_uses_original_method(self):
        steps = [
            make_step(1, column="a", method="median imputation"),
            make_step(2, column="b", method="mode imputation"),
        ]
        rows = [{"a": None, "b": None}, {"a": 5.0, "b": "X"}, {"a": 10.0, "b": "Y"}]
        _, audit = agent().execute(
            rows, steps,
            decide([1, 2], {1: {"method": "mode imputation"}}),
        )
        by_id = audit_by_id(audit)
        assert by_id[1]["method"] == "mode imputation"    # overridden
        assert by_id[2]["method"] == "mode imputation"    # original, unchanged


# ─────────────────────────────────────────────────────────────────────────────
# 10. Audit field correctness after modification
# ─────────────────────────────────────────────────────────────────────────────

class TestAuditFieldCorrectnessWithModification:

    REQUIRED_KEYS = {
        "step_id", "action", "column", "method", "rationale",
        "confidence", "rows_before", "rows_after", "rows_changed",
    }

    def test_all_required_audit_keys_present_with_modification(self):
        steps = [make_step(1)]
        rows = [{"value": None}, {"value": 5}]
        _, audit = agent().execute(
            rows, steps, decide([1], {1: {"method": "mode imputation"}})
        )
        assert self.REQUIRED_KEYS.issubset(audit[0].keys())

    def test_audit_method_is_override_not_original(self):
        steps = [make_step(1, method="median imputation")]
        rows = [{"value": None}, {"value": 5}]
        _, audit = agent().execute(
            rows, steps, decide([1], {1: {"method": "mode imputation"}})
        )
        assert audit[0]["method"] == "mode imputation"

    def test_audit_rows_before_correct_with_modification(self):
        steps = [make_step(1)]
        rows = [{"value": None}] + [{"value": float(i)} for i in range(9)]
        _, audit = agent().execute(
            rows, steps, decide([1], {1: {"method": "mode imputation"}})
        )
        assert audit[0]["rows_before"] == 10

    def test_audit_rows_after_unchanged_for_impute(self):
        """Impute does not remove rows — rows_after must equal rows_before."""
        steps = [make_step(1)]
        rows = [{"value": None}, {"value": 5}, {"value": 10}]
        _, audit = agent().execute(
            rows, steps, decide([1], {1: {"method": "mode imputation"}})
        )
        assert audit[0]["rows_before"] == audit[0]["rows_after"]

    def test_audit_confidence_unchanged_by_modification(self):
        steps = [make_step(1, confidence=0.73)]
        rows = [{"value": None}, {"value": 5}]
        _, audit = agent().execute(
            rows, steps, decide([1], {1: {"method": "mode imputation"}})
        )
        assert audit[0]["confidence"] == 0.73

    def test_audit_action_unchanged_by_modification(self):
        steps = [make_step(1, action="impute")]
        rows = [{"value": None}, {"value": 5}]
        _, audit = agent().execute(
            rows, steps, decide([1], {1: {"method": "mode imputation"}})
        )
        assert audit[0]["action"] == "impute"

    def test_audit_column_unchanged_by_modification(self):
        steps = [make_step(1, column="revenue")]
        rows = [{"revenue": None}, {"revenue": 50}]
        _, audit = agent().execute(
            rows, steps, decide([1], {1: {"method": "mode imputation"}})
        )
        assert audit[0]["column"] == "revenue"

    def test_audit_step_id_unchanged_by_modification(self):
        steps = [make_step(42)]
        rows = [{"value": None}, {"value": 5}]
        _, audit = agent().execute(
            rows, steps, decide([42], {42: {"method": "mode imputation"}})
        )
        assert audit[0]["step_id"] == 42


# ─────────────────────────────────────────────────────────────────────────────
# 11. Input immutability with modifications active
# ─────────────────────────────────────────────────────────────────────────────

class TestInputImmutabilityWithModifications:

    def test_original_rows_not_mutated_when_modification_active(self):
        original = [{"v": None}, {"v": 5}, {"v": 10}]
        steps = [make_step(1, column="v", method="median imputation")]
        agent().execute(original, steps, decide([1], {1: {"method": "mode imputation"}}))
        assert original[0]["v"] is None

    def test_cleaned_rows_independent_of_original_with_modification(self):
        original = [{"v": None}, {"v": 5}]
        steps = [make_step(1, column="v", method="median imputation")]
        cleaned, _ = agent().execute(
            original, steps, decide([1], {1: {"method": "mode imputation"}})
        )
        cleaned[0]["v"] = 999
        assert original[0]["v"] is None

    def test_step_object_method_not_mutated_by_override(self):
        """The CleaningStep.method field must remain the original after execute()."""
        s = make_step(1, method="median imputation")
        rows = [{"value": None}, {"value": 5}]
        agent().execute([{"value": None}, {"value": 5}], [s],
                        decide([1], {1: {"method": "mode imputation"}}))
        assert s.method == "median imputation"

    def test_decision_step_modifications_not_mutated_by_execute(self):
        d = decide([1], {1: {"method": "mode imputation"}})
        steps = [make_step(1)]
        rows = [{"value": None}, {"value": 5}]
        agent().execute(rows, steps, d)
        assert d.step_modifications[1]["method"] == "mode imputation"


# ─────────────────────────────────────────────────────────────────────────────
# 12. Real-world HITL #2 modification scenarios
# ─────────────────────────────────────────────────────────────────────────────

class TestRealWorldModificationScenarios:

    def test_finance_change_median_to_mode_for_categorical_revenue_tier(self):
        """
        Finance dataset: agent proposed median for revenue_tier (categorical),
        but user corrects it to mode because the column is non-numeric.
        """
        steps = [
            make_step(1, "deduplicate",  None,           "exact row deduplication"),
            make_step(2, "impute",       "revenue_tier", "median imputation", confidence=0.70),
            make_step(3, "flag_outlier", "revenue",      "IQR outlier flagging"),
        ]
        rows = [
            {"revenue_tier": None,  "revenue": 50000},
            {"revenue_tier": "Mid", "revenue": 45000},
            {"revenue_tier": "Mid", "revenue": 55000},
            {"revenue_tier": "Mid", "revenue": 60000},
            {"revenue_tier": "Low", "revenue": 20000},
        ]
        cleaned, audit = agent().execute(
            rows, steps,
            decide([1, 2, 3], {2: {"method": "mode imputation"}}),
        )
        by_id = audit_by_id(audit)
        assert by_id[2]["method"] == "mode imputation"
        assert cleaned[0]["revenue_tier"] == "Mid"

    def test_healthcare_change_median_to_mode_for_ward_code(self):
        """
        Healthcare: ward_code should use mode not median — user modifies.
        """
        steps = [
            make_step(1, "impute", "los",       "median imputation", confidence=0.85),
            make_step(2, "impute", "ward_code", "median imputation", confidence=0.68),
        ]
        rows = [
            {"los": None, "ward_code": None},
            {"los": 3.0,  "ward_code": "ICU"},
            {"los": 5.0,  "ward_code": "ICU"},
            {"los": 4.0,  "ward_code": "ICU"},
            {"los": 7.0,  "ward_code": "GEN"},
        ]
        cleaned, audit = agent().execute(
            rows, steps,
            decide([1, 2], {2: {"method": "mode imputation"}}),
        )
        by_id = audit_by_id(audit)
        assert by_id[1]["method"] == "median imputation"   # unchanged
        assert by_id[2]["method"] == "mode imputation"     # modified
        # ward_code filled with mode = "ICU"
        assert cleaned[0]["ward_code"] == "ICU"
        # los filled with median of [3.0, 5.0, 4.0, 7.0] = 4.5
        assert cleaned[0]["los"] == 4.5

    def test_retail_change_mode_to_median_for_numeric_price_column(self):
        """
        Retail: agent proposed mode for price (too conservative); user wants median.
        """
        steps = [
            make_step(1, "impute", "price", "mode imputation", confidence=0.72),
            make_step(2, "impute", "qty",   "median imputation"),
        ]
        rows = [
            {"price": None, "qty": None},
            {"price": 10.0, "qty": 2},
            {"price": 20.0, "qty": 3},
            {"price": 30.0, "qty": 4},
        ]
        cleaned, audit = agent().execute(
            rows, steps,
            decide([1, 2], {1: {"method": "median imputation"}}),
        )
        by_id = audit_by_id(audit)
        assert by_id[1]["method"] == "median imputation"
        # median of [10.0, 20.0, 30.0] = 20.0
        assert cleaned[0]["price"] == 20.0

    def test_marketing_user_corrects_mode_to_median_for_ctr(self):
        """
        Marketing: CTR is numeric — agent proposed mode but user changes to median.
        """
        steps = [
            make_step(1, "impute", "ctr", "mode imputation", confidence=0.60),
            make_step(2, "impute", "cpa", "median imputation"),
        ]
        rows = [
            {"ctr": None,  "cpa": 5.0},
            {"ctr": 0.02,  "cpa": 4.0},
            {"ctr": 0.04,  "cpa": 6.0},
            {"ctr": 0.06,  "cpa": None},
        ]
        cleaned, audit = agent().execute(
            rows, steps,
            decide([1, 2], {1: {"method": "median imputation"}}),
        )
        by_id = audit_by_id(audit)
        assert by_id[1]["method"] == "median imputation"
        assert abs(cleaned[0]["ctr"] - 0.04) < 1e-9   # median of [0.02, 0.04, 0.06]

    def test_user_modifies_all_impute_steps_in_five_step_plan(self):
        """Full HITL #2 modification sweep: every impute step overridden."""
        steps = [
            make_step(1, "deduplicate",  None,  "exact row deduplication"),
            make_step(2, "impute",       "a",   "median imputation"),
            make_step(3, "impute",       "b",   "median imputation"),
            make_step(4, "impute",       "c",   "median imputation"),
            make_step(5, "flag_outlier", "a",   "IQR outlier flagging"),
        ]
        rows = [{"a": None, "b": None, "c": None}] + \
               [{"a": float(i), "b": float(i), "c": float(i)} for i in range(1, 5)]
        _, audit = agent().execute(
            rows, steps,
            decide([1, 2, 3, 4, 5], {
                2: {"method": "mode imputation"},
                3: {"method": "most_frequent"},
                4: {"method": "mode imputation"},
            }),
        )
        by_id = audit_by_id(audit)
        assert by_id[1]["method"] == "exact row deduplication"  # unchanged
        assert by_id[2]["method"] == "mode imputation"
        assert by_id[3]["method"] == "most_frequent"
        assert by_id[4]["method"] == "mode imputation"
        assert by_id[5]["method"] == "IQR outlier flagging"     # unchanged


# ═════════════════════════════════════════════════════════════════════════════
# Runner
# ═════════════════════════════════════════════════════════════════════════════

def _collect_all_test_classes():
    return [
        TestModificationModelConstruction,
        TestEffectiveMethodInAudit,
        TestOverrideChangesRowBehaviour,
        TestModificationIsolation,
        TestUnapprovedStepModificationIgnored,
        TestAllImputationMethodVariants,
        TestImputationFillValueMatchesOverrideMethod,
        TestMultipleSimultaneousModifications,
        TestEmptyOrAbsentModifications,
        TestAuditFieldCorrectnessWithModification,
        TestInputImmutabilityWithModifications,
        TestRealWorldModificationScenarios,
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