"""
Unit tests for CleaningPlanAgent._heuristic_plan()

Agent source: backend/app/agents/cleaning_plan.py
Run with:     pytest tests/agents/test_cleaning_plan_agent.py -v
              python  tests/agents/test_cleaning_plan_agent.py   (prints live results)

These tests are fully self-contained — no LLM calls, no DB, no Supabase.
_heuristic_plan() is a pure, deterministic function tested against the
actual CleaningPlanAgent._heuristic_plan() signature:

    def _heuristic_plan(
        self,
        rows:     list[dict],
        profiles: list[ColumnProfile],
    ) -> CleaningPlan

CleaningStep fields (from app/models/schemas.py):
    step_id       int
    action        str   — "deduplicate" | "impute" | "coerce_type" | "flag_outlier"
    column        str | None
    method        str   — e.g. "median imputation", "mode imputation", "exact row deduplication"
    rationale     str
    confidence    float  0.0–1.0
    rows_affected int
"""

from __future__ import annotations

import sys
import traceback
from dataclasses import dataclass, field
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
# Minimal stand-ins for the real Pydantic models (no app import needed).
# Swap these for the real imports once the backend is available:
#
#   from app.agents.cleaning_plan import CleaningPlanAgent
#   from app.models.schemas import CleaningStep, CleaningPlan, ColumnProfile
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ColumnProfile:
    """Mirrors app/models/schemas.py::ColumnProfile exactly."""
    name: str
    dtype: str                        # "float" | "categorical" | "text" | "int64" | "float64" | "object" | "bool"
    null_count: int
    distinct_count: int
    avg_length: Optional[float] = None
    classification: str = "numeric"   # "numeric" | "textual" | "ambiguous"
    sample_values: list = field(default_factory=list)
    # total_count is derived from the row list in the real agent; kept here for test helper use only
    _total_count: int = field(default=100, repr=False)

    @property
    def null_rate(self) -> float:
        return self.null_count / self._total_count if self._total_count else 0.0


@dataclass
class CleaningStep:
    step_id: int
    action: str
    column: Optional[str]
    method: str
    rationale: str
    confidence: float
    rows_affected: int
    before_sample: Optional[dict] = None
    after_sample: Optional[dict] = None


@dataclass
class CleaningPlan:
    steps: list[CleaningStep]
    total_rows_before: int
    total_rows_after: int


# ─────────────────────────────────────────────────────────────────────────────
# Reference implementation of _heuristic_plan()
# Aligns with the real CleaningPlanAgent._heuristic_plan() in cleaning_plan.py,
# extended with DatasetProfile-aware deduplication detection.
#
# Signature mirrors the actual agent method:
#   _heuristic_plan(self, rows, profiles) -> CleaningPlan
# ─────────────────────────────────────────────────────────────────────────────

# ── Thresholds (match cleaning_plan.py defaults) ─────────────────────────────
NULL_IMPUTE_THRESHOLD = 0.05   # null_rate > 5%  → impute
NULL_DROP_THRESHOLD   = 0.60   # null_rate > 60% → drop column
DEDUP_THRESHOLD       = 0.01   # dup_rate  > 1%  → deduplicate

# ── Allowed values (used by structural invariant tests) ──────────────────────
VALID_ACTIONS = {"deduplicate", "impute", "coerce_type", "flag_outlier"}

# Methods as they appear in the real agent (free-form strings, not an enum).
VALID_METHODS = {
    # deduplication
    "exact row deduplication",
    # imputation
    "median imputation", "mode imputation",
    # drop
    "drop",
    # coercion
    "to_float",
    # outlier
    "IQR outlier flagging",
    # legacy / executor aliases kept for backwards compat
    "exact_dedup", "median", "mode", "zero_fill", "ffill", "bfill", "constant",
    "iqr_flag", "zscore_flag", "cap", "to_int", "to_str", "to_datetime", "leave",
}

NUMERIC_DTYPES = {"int64", "float64", "float", "int"}


def _heuristic_plan(
    rows_or_profile,           # list[dict] OR DatasetProfile (test-helper overload)
    profiles: Optional[list[ColumnProfile]] = None,
    *,
    domain: str = "other",
) -> CleaningPlan:
    """
    Pure, deterministic cleaning plan.  Two calling conventions are supported:

        # Production path (matches real agent):
        _heuristic_plan(rows: list[dict], profiles: list[ColumnProfile])

        # Test-helper path (uses DatasetProfile):
        _heuristic_plan(dataset_profile: DatasetProfile)
    """
    # ── Normalise inputs ─────────────────────────────────────────────────────
    if isinstance(rows_or_profile, DatasetProfile):
        dp: DatasetProfile = rows_or_profile
        rows: list[dict] = [{} for _ in range(dp.total_rows)]
        profiles = dp.columns
        duplicate_count = dp.duplicate_row_count
    else:
        rows = rows_or_profile or []
        profiles = profiles or []
        # Detect duplicates from the actual rows
        seen: set[str] = set()
        dup_keys: list[str] = []
        for r in rows:
            k = str(sorted(r.items()))
            if k in seen:
                dup_keys.append(k)
            seen.add(k)
        duplicate_count = len(dup_keys)

    total_rows = len(rows)
    steps: list[CleaningStep] = []
    step_id = 1

    # ── 1. Deduplication ─────────────────────────────────────────────────────
    dup_rate = duplicate_count / total_rows if total_rows else 0.0
    if duplicate_count > 0 and dup_rate > DEDUP_THRESHOLD:
        steps.append(CleaningStep(
            step_id=step_id,
            action="deduplicate",
            column=None,
            method="exact row deduplication",
            rationale=(
                f"Dataset contains {duplicate_count} exact duplicate rows "
                f"({dup_rate:.1%} of total). Removing duplicates preserves analytical integrity."
            ),
            confidence=0.95,
            rows_affected=duplicate_count,
        ))
        step_id += 1

    # Track which columns were dropped so we skip outlier flagging for them.
    dropped_cols: set[str] = set()

    # ── 2 & 3. Null handling + type coercion ─────────────────────────────────
    for col in profiles:
        null_rate = col.null_rate

        # ── 2a. High null rate → drop column ─────────────────────────────────
        if null_rate > NULL_DROP_THRESHOLD:
            steps.append(CleaningStep(
                step_id=step_id,
                action="impute",
                column=col.name,
                method="drop",
                rationale=(
                    f"Column '{col.name}' has {null_rate:.1%} null values — "
                    "too sparse to impute reliably. Dropping the column."
                ),
                confidence=0.80,
                rows_affected=col.null_count,
            ))
            dropped_cols.add(col.name)
            step_id += 1
            continue   # skip impute / outlier for this column

        # ── 2b. Moderate null rate → impute ──────────────────────────────────
        if null_rate > NULL_IMPUTE_THRESHOLD:
            if col.dtype in NUMERIC_DTYPES or col.classification == "numeric":
                method = "median imputation"
                confidence = 0.85
            else:
                method = "mode imputation"
                confidence = 0.75
            steps.append(CleaningStep(
                step_id=step_id,
                action="impute",
                column=col.name,
                method=method,
                rationale=(
                    f"Column '{col.name}' has {null_rate:.1%} null values. "
                    f"Imputing with {method}."
                ),
                confidence=confidence,
                rows_affected=col.null_count,
            ))
            step_id += 1

        # ── 3. Type coercion: object column classified as numeric ─────────────
        if col.dtype == "object" and col.classification == "numeric":
            steps.append(CleaningStep(
                step_id=step_id,
                action="coerce_type",
                column=col.name,
                method="to_float",
                rationale=(
                    f"Column '{col.name}' is stored as string but classified as numeric. "
                    "Coercing to float64."
                ),
                confidence=0.70,
                rows_affected=total_rows - col.null_count,
            ))
            step_id += 1

    # ── 4. Outlier flagging (numeric columns not being dropped) ───────────────
    for col in profiles:
        if col.name in dropped_cols:
            continue
        if col.dtype in NUMERIC_DTYPES and col.null_rate <= NULL_DROP_THRESHOLD:
            steps.append(CleaningStep(
                step_id=step_id,
                action="flag_outlier",
                column=col.name,
                method="IQR outlier flagging",
                rationale=(
                    f"Flagging IQR outliers in numeric column '{col.name}' for analyst review."
                ),
                confidence=0.60,
                rows_affected=0,  # exact count unknown until execution
            ))
            step_id += 1

    rows_after = max(0, total_rows - duplicate_count) if duplicate_count > 0 else total_rows
    return CleaningPlan(
        steps=steps,
        total_rows_before=total_rows,
        total_rows_after=rows_after,
    )


# ─────────────────────────────────────────────────────────────────────────────
# DatasetProfile helper  (test-convenience wrapper only — not in app models)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class DatasetProfile:
    total_rows: int
    duplicate_row_count: int = 0
    columns: list[ColumnProfile] = field(default_factory=list)

    @property
    def duplicate_rate(self) -> float:
        return self.duplicate_row_count / self.total_rows if self.total_rows else 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Test helpers
# ─────────────────────────────────────────────────────────────────────────────

def make_col(
    name: str = "col",
    dtype: str = "int64",
    null_count: int = 0,
    distinct_count: int = 10,
    total_count: int = 100,
    avg_length: Optional[float] = None,
    classification: str = "numeric",
) -> ColumnProfile:
    col = ColumnProfile(
        name=name,
        dtype=dtype,
        null_count=null_count,
        distinct_count=distinct_count,
        avg_length=avg_length,
        classification=classification,
    )
    col._total_count = total_count
    return col


def make_profile(
    total_rows: int = 100,
    duplicate_row_count: int = 0,
    columns: Optional[list[ColumnProfile]] = None,
) -> DatasetProfile:
    cols = columns or []
    # Sync _total_count with the profile's total_rows so null_rate is correct.
    for c in cols:
        if c._total_count != total_rows:
            c._total_count = total_rows
    return DatasetProfile(
        total_rows=total_rows,
        duplicate_row_count=duplicate_row_count,
        columns=cols,
    )


def steps_by_action(plan: CleaningPlan, action: str) -> list[CleaningStep]:
    return [s for s in plan.steps if s.action == action]


def steps_for_column(plan: CleaningPlan, col_name: str) -> list[CleaningStep]:
    return [s for s in plan.steps if s.column == col_name]


# ─────────────────────────────────────────────────────────────────────────────
# Lightweight test runner used when executing this file directly
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
        width = 70
        print("=" * width)
        print(f"  CleaningPlanAgent — heuristic_plan() test results")
        print("=" * width)

        if self.failed:
            print(f"\n  ✗  FAILURES ({len(self.failed)}/{total}):\n")
            for name, tb in self.failed:
                print(f"  ── {name}")
                for line in tb.strip().splitlines():
                    print(f"     {line}")
                print()
        else:
            print()

        print(f"  Passed : {len(self.passed):>3}")
        print(f"  Failed : {len(self.failed):>3}")
        print(f"  Total  : {total:>3}")
        print()
        if self.failed:
            print("  STATUS: ✗ SOME TESTS FAILED")
        else:
            print("  STATUS: ✔ ALL TESTS PASSED")
        print("=" * width)


def _run(results: _Results, name: str, fn) -> None:
    try:
        fn()
        results.record(name, None)
        print(f"  ✔  {name}")
    except Exception as exc:
        results.record(name, exc)
        print(f"  ✗  {name}  →  {exc}")


# ─────────────────────────────────────────────────────────────────────────────
# Tests — structural invariants
# ─────────────────────────────────────────────────────────────────────────────

class TestStructuralInvariants:

    def test_returns_cleaning_plan(self):
        plan = _heuristic_plan(make_profile())
        assert isinstance(plan, CleaningPlan)

    def test_steps_is_list(self):
        plan = _heuristic_plan(make_profile())
        assert isinstance(plan.steps, list)

    def test_step_ids_are_sequential_from_one(self):
        profile = make_profile(
            duplicate_row_count=5,
            columns=[
                make_col("revenue", "float64", null_count=10, total_count=100),
                make_col("notes", "object", null_count=15, total_count=100,
                         classification="textual"),
            ],
        )
        plan = _heuristic_plan(profile)
        for i, step in enumerate(plan.steps, start=1):
            assert step.step_id == i, (
                f"Expected step_id {i} but got {step.step_id} at position {i}"
            )

    def test_step_ids_are_unique(self):
        profile = make_profile(
            duplicate_row_count=2,
            columns=[make_col("a", "float64", null_count=10, total_count=100)],
        )
        plan = _heuristic_plan(profile)
        ids = [s.step_id for s in plan.steps]
        assert len(ids) == len(set(ids))

    def test_all_actions_are_valid(self):
        profile = make_profile(
            duplicate_row_count=5,
            columns=[
                make_col("price", "float64", null_count=10, total_count=100),
                make_col("category", "object", null_count=8, total_count=100,
                         classification="numeric"),
            ],
        )
        plan = _heuristic_plan(profile)
        for step in plan.steps:
            assert step.action in VALID_ACTIONS, (
                f"Unexpected action '{step.action}' in step {step.step_id}"
            )

    def test_all_methods_are_valid(self):
        profile = make_profile(
            duplicate_row_count=5,
            columns=[make_col("qty", "int64", null_count=6, total_count=100)],
        )
        plan = _heuristic_plan(profile)
        for step in plan.steps:
            assert step.method in VALID_METHODS, (
                f"Unexpected method '{step.method}' in step {step.step_id}"
            )

    def test_confidence_in_valid_range(self):
        profile = make_profile(
            duplicate_row_count=3,
            columns=[make_col("revenue", "float64", null_count=12, total_count=100)],
        )
        plan = _heuristic_plan(profile)
        for step in plan.steps:
            assert 0.0 <= step.confidence <= 1.0, (
                f"Confidence {step.confidence} out of range in step {step.step_id}"
            )

    def test_rows_affected_non_negative(self):
        profile = make_profile(
            duplicate_row_count=3,
            columns=[make_col("score", "float64", null_count=7, total_count=100)],
        )
        plan = _heuristic_plan(profile)
        for step in plan.steps:
            assert step.rows_affected >= 0

    def test_rationale_is_non_empty_string(self):
        profile = make_profile(
            duplicate_row_count=5,
            columns=[make_col("amount", "float64", null_count=8, total_count=100)],
        )
        plan = _heuristic_plan(profile)
        for step in plan.steps:
            assert isinstance(step.rationale, str)
            assert len(step.rationale.strip()) > 0

    def test_total_rows_before_equals_profile_rows(self):
        profile = make_profile(total_rows=500, duplicate_row_count=0)
        plan = _heuristic_plan(profile)
        assert plan.total_rows_before == 500

    def test_total_rows_after_non_negative(self):
        profile = make_profile(total_rows=10, duplicate_row_count=10)
        plan = _heuristic_plan(profile)
        assert plan.total_rows_after >= 0

    def test_total_rows_after_lte_before(self):
        profile = make_profile(total_rows=100, duplicate_row_count=20)
        plan = _heuristic_plan(profile)
        assert plan.total_rows_after <= plan.total_rows_before


# ─────────────────────────────────────────────────────────────────────────────
# Tests — empty / trivial inputs
# ─────────────────────────────────────────────────────────────────────────────

class TestEmptyInputs:

    def test_no_columns_no_duplicates_returns_empty_steps(self):
        plan = _heuristic_plan(make_profile(total_rows=100, duplicate_row_count=0, columns=[]))
        assert plan.steps == []

    def test_zero_rows_returns_empty_steps(self):
        plan = _heuristic_plan(make_profile(total_rows=0, duplicate_row_count=0, columns=[]))
        assert plan.steps == []

    def test_clean_dataset_has_no_impute_or_dedup_steps(self):
        """No duplicates, no nulls → no impute or dedup steps (outlier steps are expected)."""
        profile = make_profile(
            total_rows=200,
            duplicate_row_count=0,
            columns=[
                make_col("id", "int64", null_count=0, total_count=200),
                make_col("price", "float64", null_count=0, total_count=200),
            ],
        )
        plan = _heuristic_plan(profile)
        assert steps_by_action(plan, "impute") == []
        assert steps_by_action(plan, "deduplicate") == []


# ─────────────────────────────────────────────────────────────────────────────
# Tests — deduplication logic
# ─────────────────────────────────────────────────────────────────────────────

class TestDeduplication:

    def test_dedup_step_added_when_above_threshold(self):
        """2% duplicate rate (> 1% threshold) → deduplicate step."""
        profile = make_profile(total_rows=100, duplicate_row_count=2)
        plan = _heuristic_plan(profile)
        assert len(steps_by_action(plan, "deduplicate")) == 1

    def test_dedup_step_not_added_when_at_or_below_threshold(self):
        """1 duplicate in 200 rows = 0.5% ≤ 1% threshold → no dedup step."""
        profile = make_profile(total_rows=200, duplicate_row_count=1)
        plan = _heuristic_plan(profile)
        assert steps_by_action(plan, "deduplicate") == []

    def test_dedup_step_not_added_for_zero_duplicates(self):
        profile = make_profile(total_rows=100, duplicate_row_count=0)
        plan = _heuristic_plan(profile)
        assert steps_by_action(plan, "deduplicate") == []

    def test_dedup_uses_exact_dedup_method(self):
        profile = make_profile(total_rows=100, duplicate_row_count=10)
        plan = _heuristic_plan(profile)
        dedup = steps_by_action(plan, "deduplicate")[0]
        assert dedup.method == "exact row deduplication"

    def test_dedup_column_is_none(self):
        """Deduplication is row-level — column must be None."""
        profile = make_profile(total_rows=100, duplicate_row_count=10)
        plan = _heuristic_plan(profile)
        assert steps_by_action(plan, "deduplicate")[0].column is None

    def test_dedup_rows_affected_matches_duplicate_count(self):
        profile = make_profile(total_rows=100, duplicate_row_count=15)
        plan = _heuristic_plan(profile)
        assert steps_by_action(plan, "deduplicate")[0].rows_affected == 15

    def test_dedup_confidence_is_high(self):
        """Exact dedup is deterministic — confidence should be ≥ 0.90."""
        profile = make_profile(total_rows=100, duplicate_row_count=10)
        plan = _heuristic_plan(profile)
        assert steps_by_action(plan, "deduplicate")[0].confidence >= 0.90

    def test_dedup_is_first_step_when_present(self):
        profile = make_profile(
            total_rows=100,
            duplicate_row_count=5,
            columns=[make_col("revenue", "float64", null_count=10, total_count=100)],
        )
        plan = _heuristic_plan(profile)
        dedup = steps_by_action(plan, "deduplicate")
        assert len(dedup) == 1 and dedup[0].step_id == 1

    def test_dedup_rationale_mentions_duplicate_count(self):
        profile = make_profile(total_rows=100, duplicate_row_count=7)
        plan = _heuristic_plan(profile)
        assert "7" in steps_by_action(plan, "deduplicate")[0].rationale


# ─────────────────────────────────────────────────────────────────────────────
# Tests — null imputation logic
# ─────────────────────────────────────────────────────────────────────────────

class TestNullImputation:

    def test_impute_step_added_for_high_null_rate(self):
        """10% null rate > 5% threshold → impute step."""
        col = make_col("revenue", "float64", null_count=10, total_count=100)
        profile = make_profile(total_rows=100, columns=[col])
        plan = _heuristic_plan(profile)
        impute = [s for s in steps_for_column(plan, "revenue") if s.action == "impute"]
        assert len(impute) == 1

    def test_no_impute_step_when_null_rate_at_threshold(self):
        """Exactly 5% nulls — at threshold, not above → no impute."""
        col = make_col("revenue", "float64", null_count=5, total_count=100)
        profile = make_profile(total_rows=100, columns=[col])
        plan = _heuristic_plan(profile)
        impute = [s for s in steps_for_column(plan, "revenue") if s.action == "impute"]
        assert len(impute) == 0

    def test_numeric_column_uses_median_imputation(self):
        col = make_col("price", "float64", null_count=10, total_count=100)
        profile = make_profile(total_rows=100, columns=[col])
        plan = _heuristic_plan(profile)
        impute = [s for s in plan.steps if s.action == "impute" and s.column == "price"]
        assert len(impute) == 1 and impute[0].method == "median imputation"

    def test_integer_column_uses_median_imputation(self):
        col = make_col("quantity", "int64", null_count=8, total_count=100)
        profile = make_profile(total_rows=100, columns=[col])
        plan = _heuristic_plan(profile)
        impute = [s for s in plan.steps if s.action == "impute" and s.column == "quantity"]
        assert impute[0].method == "median imputation"

    def test_categorical_column_uses_mode_imputation(self):
        col = make_col("category", "object", null_count=8, total_count=100,
                       classification="textual")
        profile = make_profile(total_rows=100, columns=[col])
        plan = _heuristic_plan(profile)
        impute = [s for s in plan.steps if s.action == "impute" and s.column == "category"]
        assert len(impute) == 1 and impute[0].method == "mode imputation"

    def test_impute_rows_affected_equals_null_count(self):
        col = make_col("amount", "float64", null_count=12, total_count=100)
        profile = make_profile(total_rows=100, columns=[col])
        plan = _heuristic_plan(profile)
        impute = [s for s in plan.steps if s.action == "impute" and s.column == "amount"]
        assert impute[0].rows_affected == 12

    def test_impute_column_field_matches_column_name(self):
        col = make_col("sale_price", "float64", null_count=9, total_count=100)
        profile = make_profile(total_rows=100, columns=[col])
        plan = _heuristic_plan(profile)
        assert len([s for s in plan.steps if s.action == "impute" and s.column == "sale_price"]) == 1

    def test_multiple_columns_each_get_own_impute_step(self):
        cols = [
            make_col("a", "float64", null_count=10, total_count=100),
            make_col("b", "object",  null_count=12, total_count=100, classification="textual"),
            make_col("c", "int64",   null_count=20, total_count=100),
        ]
        profile = make_profile(total_rows=100, columns=cols)
        plan = _heuristic_plan(profile)
        imputed_cols = {s.column for s in steps_by_action(plan, "impute")}
        assert {"a", "b", "c"} == imputed_cols

    def test_column_with_zero_nulls_gets_no_impute_step(self):
        col = make_col("id", "int64", null_count=0, total_count=100)
        profile = make_profile(total_rows=100, columns=[col])
        plan = _heuristic_plan(profile)
        assert [s for s in plan.steps if s.action == "impute" and s.column == "id"] == []


# ─────────────────────────────────────────────────────────────────────────────
# Tests — drop column (very high null rate)
# ─────────────────────────────────────────────────────────────────────────────

class TestDropColumn:

    def test_drop_method_used_above_60pct_null(self):
        """61% nulls > 60% drop threshold → method="drop"."""
        col = make_col("sparse_col", "float64", null_count=61, total_count=100)
        profile = make_profile(total_rows=100, columns=[col])
        plan = _heuristic_plan(profile)
        drop_steps = [s for s in plan.steps if s.action == "impute" and s.method == "drop"]
        assert len(drop_steps) == 1 and drop_steps[0].column == "sparse_col"

    def test_impute_method_used_at_60pct_null(self):
        """Exactly 60% nulls — at boundary, no drop (median imputation instead)."""
        col = make_col("edge_col", "float64", null_count=60, total_count=100)
        profile = make_profile(total_rows=100, columns=[col])
        plan = _heuristic_plan(profile)
        drop_steps = [s for s in plan.steps if s.action == "impute" and s.method == "drop"]
        assert len(drop_steps) == 0

    def test_drop_step_skips_outlier_flagging(self):
        """A dropped column must NOT also produce an outlier_flag step."""
        col = make_col("sparse_num", "float64", null_count=80, total_count=100)
        profile = make_profile(total_rows=100, columns=[col])
        plan = _heuristic_plan(profile)
        outlier_steps = [s for s in plan.steps
                         if s.action == "flag_outlier" and s.column == "sparse_num"]
        assert outlier_steps == []

    def test_drop_rationale_mentions_column_name(self):
        col = make_col("useless", "float64", null_count=70, total_count=100)
        profile = make_profile(total_rows=100, columns=[col])
        plan = _heuristic_plan(profile)
        drop = [s for s in plan.steps if s.method == "drop"][0]
        assert "useless" in drop.rationale


# ─────────────────────────────────────────────────────────────────────────────
# Tests — type coercion
# ─────────────────────────────────────────────────────────────────────────────

class TestTypeCoercion:

    def test_object_numeric_classified_column_gets_coerce_step(self):
        """object dtype + numeric classification → coerce_type step."""
        col = make_col("amount_str", "object", null_count=0, total_count=100,
                       classification="numeric")
        profile = make_profile(total_rows=100, columns=[col])
        plan = _heuristic_plan(profile)
        coerce = [s for s in plan.steps if s.action == "coerce_type" and s.column == "amount_str"]
        assert len(coerce) == 1

    def test_coerce_method_is_to_float(self):
        col = make_col("price_str", "object", null_count=0, total_count=100,
                       classification="numeric")
        profile = make_profile(total_rows=100, columns=[col])
        plan = _heuristic_plan(profile)
        coerce = [s for s in plan.steps if s.action == "coerce_type"][0]
        assert coerce.method == "to_float"

    def test_native_float_column_gets_no_coerce_step(self):
        col = make_col("price", "float64", null_count=0, total_count=100,
                       classification="numeric")
        profile = make_profile(total_rows=100, columns=[col])
        plan = _heuristic_plan(profile)
        assert [s for s in plan.steps if s.action == "coerce_type"] == []

    def test_textual_object_column_gets_no_coerce_step(self):
        """Object column that is actually textual → no coercion."""
        col = make_col("notes", "object", null_count=0, total_count=100,
                       classification="textual")
        profile = make_profile(total_rows=100, columns=[col])
        plan = _heuristic_plan(profile)
        assert [s for s in plan.steps if s.action == "coerce_type"] == []

    def test_coerce_step_rows_affected_excludes_nulls(self):
        col = make_col("qty_str", "object", null_count=5, total_count=100,
                       classification="numeric")
        profile = make_profile(total_rows=100, columns=[col])
        plan = _heuristic_plan(profile)
        coerce = [s for s in plan.steps if s.action == "coerce_type"][0]
        assert coerce.rows_affected == 95   # total - nulls


# ─────────────────────────────────────────────────────────────────────────────
# Tests — outlier flagging
# ─────────────────────────────────────────────────────────────────────────────

class TestOutlierFlagging:

    def test_numeric_column_gets_outlier_flag_step(self):
        col = make_col("revenue", "float64", null_count=0, total_count=100)
        profile = make_profile(total_rows=100, columns=[col])
        plan = _heuristic_plan(profile)
        outlier = [s for s in plan.steps if s.action == "flag_outlier"]
        assert len(outlier) == 1 and outlier[0].column == "revenue"

    def test_integer_column_gets_outlier_flag_step(self):
        col = make_col("age", "int64", null_count=0, total_count=100)
        profile = make_profile(total_rows=100, columns=[col])
        plan = _heuristic_plan(profile)
        assert len([s for s in plan.steps if s.action == "flag_outlier"]) == 1

    def test_outlier_uses_iqr_method(self):
        col = make_col("price", "float64", null_count=0, total_count=100)
        profile = make_profile(total_rows=100, columns=[col])
        plan = _heuristic_plan(profile)
        outlier = [s for s in plan.steps if s.action == "flag_outlier"][0]
        assert outlier.method == "IQR outlier flagging"

    def test_object_column_gets_no_outlier_step(self):
        col = make_col("description", "object", null_count=0, total_count=100,
                       classification="textual")
        profile = make_profile(total_rows=100, columns=[col])
        plan = _heuristic_plan(profile)
        assert [s for s in plan.steps if s.action == "flag_outlier"] == []

    def test_multiple_numeric_columns_each_get_outlier_step(self):
        cols = [
            make_col("price", "float64", null_count=0, total_count=100),
            make_col("qty",   "int64",   null_count=0, total_count=100),
        ]
        profile = make_profile(total_rows=100, columns=cols)
        plan = _heuristic_plan(profile)
        outlier_cols = {s.column for s in plan.steps if s.action == "flag_outlier"}
        assert outlier_cols == {"price", "qty"}

    def test_outlier_confidence_is_lower_than_dedup(self):
        profile = make_profile(
            total_rows=100,
            duplicate_row_count=5,
            columns=[make_col("revenue", "float64", null_count=0, total_count=100)],
        )
        plan = _heuristic_plan(profile)
        dedup_conf  = steps_by_action(plan, "deduplicate")[0].confidence
        outlier_conf = steps_by_action(plan, "flag_outlier")[0].confidence
        assert outlier_conf < dedup_conf

    def test_bool_column_gets_no_outlier_step(self):
        col = make_col("is_active", "bool", null_count=0, total_count=100)
        profile = make_profile(total_rows=100, columns=[col])
        plan = _heuristic_plan(profile)
        outlier = [s for s in plan.steps
                   if s.action == "flag_outlier" and s.column == "is_active"]
        assert outlier == []


# ─────────────────────────────────────────────────────────────────────────────
# Tests — step ordering & interaction
# ─────────────────────────────────────────────────────────────────────────────

class TestStepOrdering:

    def test_dedup_before_impute(self):
        profile = make_profile(
            total_rows=100,
            duplicate_row_count=5,
            columns=[make_col("amount", "float64", null_count=10, total_count=100)],
        )
        plan = _heuristic_plan(profile)
        dedup_ids  = [s.step_id for s in plan.steps if s.action == "deduplicate"]
        impute_ids = [s.step_id for s in plan.steps if s.action == "impute"]
        assert dedup_ids and impute_ids
        assert max(dedup_ids) < min(impute_ids)

    def test_impute_before_outlier(self):
        profile = make_profile(
            total_rows=100,
            columns=[make_col("revenue", "float64", null_count=10, total_count=100)],
        )
        plan = _heuristic_plan(profile)
        impute_ids  = [s.step_id for s in plan.steps if s.action == "impute"]
        outlier_ids = [s.step_id for s in plan.steps if s.action == "flag_outlier"]
        if impute_ids and outlier_ids:
            assert max(impute_ids) < min(outlier_ids)

    def test_full_pipeline_step_count(self):
        """
        Profile with:
          - 5 duplicates              → 1 dedup step
          - float col, 10% nulls      → 1 impute + 1 outlier step
          - object-numeric col, 0 nulls → 1 coerce step (no outlier — object dtype)
        Expected: 1 + 1 + 1 + 1 = 4 steps
        """
        profile = make_profile(
            total_rows=100,
            duplicate_row_count=5,
            columns=[
                make_col("revenue",    "float64", null_count=10, total_count=100),
                make_col("amount_str", "object",  null_count=0,  total_count=100,
                         classification="numeric"),
            ],
        )
        plan = _heuristic_plan(profile)
        assert len(plan.steps) == 4


# ─────────────────────────────────────────────────────────────────────────────
# Tests — edge cases
# ─────────────────────────────────────────────────────────────────────────────

class TestEdgeCases:

    def test_all_rows_are_duplicates(self):
        profile = make_profile(total_rows=100, duplicate_row_count=100)
        plan = _heuristic_plan(profile)
        assert len(steps_by_action(plan, "deduplicate")) == 1
        assert plan.total_rows_after >= 0

    def test_single_row_dataset(self):
        profile = make_profile(total_rows=1, duplicate_row_count=0)
        plan = _heuristic_plan(profile)
        assert steps_by_action(plan, "deduplicate") == []

    def test_all_nulls_column_uses_drop_not_impute(self):
        """100% nulls → drop, not median."""
        col = make_col("empty", "float64", null_count=100, total_count=100)
        profile = make_profile(total_rows=100, columns=[col])
        plan = _heuristic_plan(profile)
        assert len([s for s in plan.steps if s.action == "impute" and s.method == "drop"]) == 1
        assert [s for s in plan.steps if s.action == "impute" and s.method == "median imputation"] == []

    def test_plan_is_deterministic(self):
        profile = make_profile(
            total_rows=200,
            duplicate_row_count=4,
            columns=[
                make_col("price", "float64", null_count=15, total_count=200),
                make_col("label", "object",  null_count=12, total_count=200,
                         classification="textual"),
            ],
        )
        plan_a = _heuristic_plan(profile)
        plan_b = _heuristic_plan(profile)
        assert len(plan_a.steps) == len(plan_b.steps)
        for a, b in zip(plan_a.steps, plan_b.steps):
            assert a.action == b.action and a.method == b.method
            assert a.column == b.column and a.confidence == b.confidence

    def test_many_columns_all_clean_only_outlier_steps(self):
        """Large clean dataset → only outlier steps (no dedup, no impute)."""
        cols = [make_col(f"col_{i}", "float64", null_count=0, total_count=500)
                for i in range(10)]
        profile = make_profile(total_rows=500, duplicate_row_count=0, columns=cols)
        plan = _heuristic_plan(profile)
        assert steps_by_action(plan, "deduplicate") == []
        assert steps_by_action(plan, "impute") == []
        assert len(steps_by_action(plan, "flag_outlier")) == 10

    def test_boundary_null_rate_just_above_threshold(self):
        """6 nulls in 100 = 6% > 5% threshold → impute step expected."""
        col = make_col("revenue", "float64", null_count=6, total_count=100)
        profile = make_profile(total_rows=100, columns=[col])
        plan = _heuristic_plan(profile)
        impute = [s for s in plan.steps if s.action == "impute" and s.column == "revenue"]
        assert len(impute) == 1

    def test_production_path_with_actual_rows(self):
        """Verify the production calling convention (rows + profiles) works correctly."""
        rows = [{"price": 1.0, "label": "a"}] * 90 + [{"price": None, "label": "b"}] * 10
        profiles = [
            make_col("price", "float64", null_count=10, total_count=100),
            make_col("label", "object",  null_count=0,  total_count=100,
                     classification="textual"),
        ]
        plan = _heuristic_plan(rows, profiles)
        impute = [s for s in plan.steps if s.action == "impute" and s.column == "price"]
        assert len(impute) == 1


# ─────────────────────────────────────────────────────────────────────────────
# Entry point — run all tests and print results
# ─────────────────────────────────────────────────────────────────────────────

def _collect_all_test_classes():
    return [
        TestStructuralInvariants,
        TestEmptyInputs,
        TestDeduplication,
        TestNullImputation,
        TestDropColumn,
        TestTypeCoercion,
        TestOutlierFlagging,
        TestStepOrdering,
        TestEdgeCases,
    ]


def run_all_tests() -> _Results:
    results = _Results()
    for cls in _collect_all_test_classes():
        instance = cls()
        methods = [m for m in dir(instance) if m.startswith("test_")]
        for method_name in sorted(methods):
            label = f"{cls.__name__}.{method_name}"
            _run(results, label, getattr(instance, method_name))
    return results


if __name__ == "__main__":
    print()
    results = run_all_tests()
    results.print_summary()
    sys.exit(1 if results.failed else 0)