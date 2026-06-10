"""
Unit tests — Merge-Plan Decision with approved=True

Tests cover the full HITL #1 lifecycle:
    propose_merge_plan()       → IngestionAgent produces a MergePlan
    MergePlanDecision(approved=True/False) → user decision model
    apply_merge_decision()     → decision executor (the unit under closest test)

Architecture ref: architecture.md §HITL Checkpoints #1 — Schema & Merge Validation
    "User can: confirm, change merge key, change type-routing, exclude column/file."
    "Pipeline BLOCKS until user POSTs decision to /datasets/{id}/merge-plan/decision."

Run with:
    pytest  test_merge_plan_decision.py -v
    python  test_merge_plan_decision.py          # live results, no pytest needed

Fully independent — no LLM, no DB, no Supabase, no app imports.
"""

from __future__ import annotations

import sys
import traceback
from dataclasses import dataclass, field
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
# Stand-ins for app.models.schemas
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ColumnProfile:
    name: str
    dtype: str                      # "float" | "categorical" | "text" | "int64" …
    null_count: int = 0
    distinct_count: int = 10
    avg_length: Optional[float] = None
    classification: str = "numeric" # "numeric" | "textual" | "ambiguous"


@dataclass
class MergePlan:
    """
    Proposed by IngestionAgent.propose_merge_plan().

    strategy    : "single" | "union" | "join" | "separate"
    confidence  : 0.0–1.0
    column_profiles : columns that will be present after the merge
    join_key    : only set when strategy == "join"
    """
    strategy: str
    confidence: float
    column_profiles: list[ColumnProfile]
    join_key: Optional[str] = None


@dataclass
class MergePlanDecision:
    """
    User decision for HITL #1.

    approved            : True  → proceed with (possibly modified) plan
                          False → abort pipeline
    override_strategy   : override the agent's proposed strategy
    override_join_key   : override the agent's proposed join key
    excluded_columns    : column names the user wants dropped before routing
    column_routing_overrides : {col_name: "numeric" | "textual" | "ambiguous"}
                               user can reclassify individual columns
    """
    approved: bool
    override_strategy: Optional[str] = None
    override_join_key: Optional[str] = None
    excluded_columns: list[str] = field(default_factory=list)
    column_routing_overrides: dict[str, str] = field(default_factory=dict)


@dataclass
class MergeDecisionResult:
    """
    Output of apply_merge_decision() — the resolved, user-confirmed merge config
    that downstream agents (cleaning, routing) receive.
    """
    approved: bool
    effective_strategy: str
    effective_join_key: Optional[str]
    final_columns: list[ColumnProfile]   # excluded columns removed, routing applied
    column_profiles: list[ColumnProfile] # alias — same as final_columns


# ─────────────────────────────────────────────────────────────────────────────
# IngestionAgent.propose_merge_plan() — verbatim port from ingestion.py
# ─────────────────────────────────────────────────────────────────────────────

class IngestionAgent:

    def propose_merge_plan(
        self,
        file_profiles: list[tuple[str, list[ColumnProfile]]],
    ) -> MergePlan:
        if len(file_profiles) == 1:
            return MergePlan(
                strategy="single",
                confidence=0.99,
                column_profiles=file_profiles[0][1],
            )

        all_col_sets = [set(p.name for p in profiles) for _, profiles in file_profiles]
        if all(s == all_col_sets[0] for s in all_col_sets):
            return MergePlan(
                strategy="union",
                confidence=0.92,
                column_profiles=file_profiles[0][1],
            )

        common_cols = all_col_sets[0].intersection(*all_col_sets[1:])
        join_key = next(iter(common_cols), None)
        all_profiles = [p for _, profiles in file_profiles for p in profiles]
        return MergePlan(
            strategy="join" if join_key else "separate",
            join_key=join_key,
            confidence=0.75 if join_key else 0.55,
            column_profiles=all_profiles,
        )


# ─────────────────────────────────────────────────────────────────────────────
# apply_merge_decision() — the HITL executor under closest test
#
# This function is the bridge between the agent's *proposal* and the user's
# *decision*. It is the component that:
#   1. Honours approved=True / False
#   2. Applies strategy overrides
#   3. Applies join_key overrides
#   4. Removes excluded columns
#   5. Applies per-column routing overrides
# ─────────────────────────────────────────────────────────────────────────────

VALID_STRATEGIES = {"single", "union", "join", "separate"}
VALID_ROUTINGS   = {"numeric", "textual", "ambiguous"}


def apply_merge_decision(
    plan: MergePlan,
    decision: MergePlanDecision,
) -> MergeDecisionResult:
    """
    Resolves a MergePlan + MergePlanDecision into an executable MergeDecisionResult.

    Rules (from architecture.md §HITL #1):
    - If not approved → return immediately with approved=False; no further work.
    - effective_strategy = override_strategy if provided, else plan.strategy
    - effective_join_key = override_join_key if provided, else plan.join_key
    - final_columns = plan.column_profiles minus excluded_columns,
                      with classification overridden per column_routing_overrides
    """
    if not decision.approved:
        return MergeDecisionResult(
            approved=False,
            effective_strategy=plan.strategy,
            effective_join_key=plan.join_key,
            final_columns=[],
            column_profiles=[],
        )

    effective_strategy = (
        decision.override_strategy
        if decision.override_strategy is not None
        else plan.strategy
    )

    effective_join_key = (
        decision.override_join_key
        if decision.override_join_key is not None
        else plan.join_key
    )

    excluded = set(decision.excluded_columns)
    final_columns: list[ColumnProfile] = []
    for col in plan.column_profiles:
        if col.name in excluded:
            continue
        if col.name in decision.column_routing_overrides:
            new_routing = decision.column_routing_overrides[col.name]
            # shallow copy with classification override
            col = ColumnProfile(
                name=col.name,
                dtype=col.dtype,
                null_count=col.null_count,
                distinct_count=col.distinct_count,
                avg_length=col.avg_length,
                classification=new_routing,
            )
        final_columns.append(col)

    return MergeDecisionResult(
        approved=True,
        effective_strategy=effective_strategy,
        effective_join_key=effective_join_key,
        final_columns=final_columns,
        column_profiles=final_columns,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def make_col(
    name: str,
    dtype: str = "float",
    classification: str = "numeric",
    null_count: int = 0,
) -> ColumnProfile:
    return ColumnProfile(name=name, dtype=dtype, classification=classification,
                         null_count=null_count)


def make_plan(
    strategy: str = "single",
    confidence: float = 0.99,
    columns: Optional[list[ColumnProfile]] = None,
    join_key: Optional[str] = None,
) -> MergePlan:
    return MergePlan(
        strategy=strategy,
        confidence=confidence,
        column_profiles=columns or [make_col("revenue"), make_col("region", "categorical")],
        join_key=join_key,
    )


def approve(
    override_strategy: Optional[str] = None,
    override_join_key: Optional[str] = None,
    excluded_columns: Optional[list[str]] = None,
    column_routing_overrides: Optional[dict[str, str]] = None,
) -> MergePlanDecision:
    return MergePlanDecision(
        approved=True,
        override_strategy=override_strategy,
        override_join_key=override_join_key,
        excluded_columns=excluded_columns or [],
        column_routing_overrides=column_routing_overrides or {},
    )


def reject() -> MergePlanDecision:
    return MergePlanDecision(approved=False)


agent = IngestionAgent()


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
        print("  Merge-Plan Decision — test results")
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
# propose_merge_plan — single file
# ─────────────────────────────────────────────────────────────────────────────

class TestProposeSingleFile:

    def test_single_file_strategy_is_single(self):
        cols = [make_col("revenue"), make_col("region", "categorical")]
        plan = agent.propose_merge_plan([("f1.csv", cols)])
        assert plan.strategy == "single"

    def test_single_file_confidence_is_099(self):
        cols = [make_col("revenue")]
        plan = agent.propose_merge_plan([("f1.csv", cols)])
        assert plan.confidence == 0.99

    def test_single_file_column_profiles_match(self):
        cols = [make_col("revenue"), make_col("region", "categorical")]
        plan = agent.propose_merge_plan([("f1.csv", cols)])
        assert [p.name for p in plan.column_profiles] == ["revenue", "region"]

    def test_single_file_join_key_is_none(self):
        cols = [make_col("revenue")]
        plan = agent.propose_merge_plan([("f1.csv", cols)])
        assert plan.join_key is None

    def test_single_file_returns_merge_plan_instance(self):
        cols = [make_col("revenue")]
        plan = agent.propose_merge_plan([("f1.csv", cols)])
        assert isinstance(plan, MergePlan)


# ─────────────────────────────────────────────────────────────────────────────
# propose_merge_plan — multi-file UNION
# ─────────────────────────────────────────────────────────────────────────────

class TestProposeUnion:

    def _same_schema_files(self) -> list[tuple[str, list[ColumnProfile]]]:
        cols = [make_col("revenue"), make_col("region", "categorical")]
        return [("q1.csv", cols), ("q2.csv", cols)]

    def test_identical_schemas_strategy_is_union(self):
        plan = agent.propose_merge_plan(self._same_schema_files())
        assert plan.strategy == "union"

    def test_union_confidence_is_092(self):
        plan = agent.propose_merge_plan(self._same_schema_files())
        assert plan.confidence == 0.92

    def test_union_join_key_is_none(self):
        plan = agent.propose_merge_plan(self._same_schema_files())
        assert plan.join_key is None

    def test_union_profiles_taken_from_first_file(self):
        cols_a = [make_col("revenue"), make_col("region", "categorical")]
        cols_b = [make_col("revenue"), make_col("region", "categorical")]
        plan = agent.propose_merge_plan([("a.csv", cols_a), ("b.csv", cols_b)])
        assert [p.name for p in plan.column_profiles] == ["revenue", "region"]

    def test_three_files_same_schema_union(self):
        cols = [make_col("amount"), make_col("date", "categorical")]
        files = [("a.csv", cols), ("b.csv", cols), ("c.csv", cols)]
        plan = agent.propose_merge_plan(files)
        assert plan.strategy == "union"


# ─────────────────────────────────────────────────────────────────────────────
# propose_merge_plan — multi-file JOIN
# ─────────────────────────────────────────────────────────────────────────────

class TestProposeJoin:

    def _join_files(self) -> list[tuple[str, list[ColumnProfile]]]:
        cols_a = [make_col("customer_id", "categorical"), make_col("revenue")]
        cols_b = [make_col("customer_id", "categorical"), make_col("email", "text")]
        return [("sales.csv", cols_a), ("customers.csv", cols_b)]

    def test_different_schemas_with_common_key_strategy_is_join(self):
        plan = agent.propose_merge_plan(self._join_files())
        assert plan.strategy == "join"

    def test_join_confidence_is_075(self):
        plan = agent.propose_merge_plan(self._join_files())
        assert plan.confidence == 0.75

    def test_join_key_is_common_column(self):
        plan = agent.propose_merge_plan(self._join_files())
        assert plan.join_key == "customer_id"

    def test_join_profiles_contain_all_columns_from_both_files(self):
        plan = agent.propose_merge_plan(self._join_files())
        names = {p.name for p in plan.column_profiles}
        assert "customer_id" in names
        assert "revenue" in names
        assert "email" in names

    def test_join_profile_count_is_sum_of_both_files(self):
        cols_a = [make_col("id", "categorical"), make_col("revenue")]
        cols_b = [make_col("id", "categorical"), make_col("name", "text")]
        plan = agent.propose_merge_plan([("a.csv", cols_a), ("b.csv", cols_b)])
        # 2 + 2 = 4 (id appears twice — once per file)
        assert len(plan.column_profiles) == 4


# ─────────────────────────────────────────────────────────────────────────────
# propose_merge_plan — SEPARATE (no common key)
# ─────────────────────────────────────────────────────────────────────────────

class TestProposeSeparate:

    def _disjoint_files(self) -> list[tuple[str, list[ColumnProfile]]]:
        cols_a = [make_col("revenue"), make_col("region", "categorical")]
        cols_b = [make_col("patient_id", "categorical"), make_col("los")]
        return [("finance.csv", cols_a), ("health.csv", cols_b)]

    def test_no_common_key_strategy_is_separate(self):
        plan = agent.propose_merge_plan(self._disjoint_files())
        assert plan.strategy == "separate"

    def test_separate_confidence_is_055(self):
        plan = agent.propose_merge_plan(self._disjoint_files())
        assert plan.confidence == 0.55

    def test_separate_join_key_is_none(self):
        plan = agent.propose_merge_plan(self._disjoint_files())
        assert plan.join_key is None


# ─────────────────────────────────────────────────────────────────────────────
# MergePlanDecision model — approved=True baseline
# ─────────────────────────────────────────────────────────────────────────────

class TestDecisionApprovedTrue:

    def test_approved_true_flag_is_set(self):
        decision = approve()
        assert decision.approved is True

    def test_approved_true_result_approved_is_true(self):
        plan = make_plan()
        result = apply_merge_decision(plan, approve())
        assert result.approved is True

    def test_approved_true_returns_merge_decision_result(self):
        plan = make_plan()
        result = apply_merge_decision(plan, approve())
        assert isinstance(result, MergeDecisionResult)

    def test_approved_true_final_columns_not_empty(self):
        plan = make_plan(columns=[make_col("revenue"), make_col("region", "categorical")])
        result = apply_merge_decision(plan, approve())
        assert len(result.final_columns) > 0

    def test_approved_true_all_plan_columns_present_by_default(self):
        cols = [make_col("revenue"), make_col("region", "categorical"), make_col("date", "text")]
        plan = make_plan(columns=cols)
        result = apply_merge_decision(plan, approve())
        result_names = {c.name for c in result.final_columns}
        assert result_names == {"revenue", "region", "date"}

    def test_approved_true_column_profiles_alias_matches_final_columns(self):
        plan = make_plan()
        result = apply_merge_decision(plan, approve())
        assert result.column_profiles is result.final_columns


# ─────────────────────────────────────────────────────────────────────────────
# MergePlanDecision model — approved=False
# ─────────────────────────────────────────────────────────────────────────────

class TestDecisionApprovedFalse:

    def test_rejected_approved_flag_is_false(self):
        decision = reject()
        assert decision.approved is False

    def test_rejected_result_approved_is_false(self):
        plan = make_plan()
        result = apply_merge_decision(plan, reject())
        assert result.approved is False

    def test_rejected_final_columns_is_empty(self):
        plan = make_plan(columns=[make_col("revenue"), make_col("region", "categorical")])
        result = apply_merge_decision(plan, reject())
        assert result.final_columns == []

    def test_rejected_column_profiles_is_empty(self):
        plan = make_plan()
        result = apply_merge_decision(plan, reject())
        assert result.column_profiles == []

    def test_rejected_effective_strategy_echoes_plan_strategy(self):
        plan = make_plan(strategy="union")
        result = apply_merge_decision(plan, reject())
        assert result.effective_strategy == "union"

    def test_rejected_does_not_raise(self):
        plan = make_plan()
        try:
            apply_merge_decision(plan, reject())
        except Exception as exc:
            raise AssertionError(f"reject() raised unexpectedly: {exc}") from exc

    def test_rejected_with_overrides_overrides_ignored(self):
        """Even if the user supplied overrides, rejection means nothing proceeds."""
        plan = make_plan(strategy="union")
        decision = MergePlanDecision(
            approved=False,
            override_strategy="join",
            override_join_key="id",
            excluded_columns=["revenue"],
        )
        result = apply_merge_decision(plan, decision)
        assert result.approved is False
        assert result.final_columns == []


# ─────────────────────────────────────────────────────────────────────────────
# Effective strategy resolution
# ─────────────────────────────────────────────────────────────────────────────

class TestEffectiveStrategy:

    def test_no_override_uses_plan_strategy_single(self):
        plan = make_plan(strategy="single")
        result = apply_merge_decision(plan, approve())
        assert result.effective_strategy == "single"

    def test_no_override_uses_plan_strategy_union(self):
        plan = make_plan(strategy="union")
        result = apply_merge_decision(plan, approve())
        assert result.effective_strategy == "union"

    def test_no_override_uses_plan_strategy_join(self):
        plan = make_plan(strategy="join", join_key="id")
        result = apply_merge_decision(plan, approve())
        assert result.effective_strategy == "join"

    def test_no_override_uses_plan_strategy_separate(self):
        plan = make_plan(strategy="separate")
        result = apply_merge_decision(plan, approve())
        assert result.effective_strategy == "separate"

    def test_override_strategy_union_replaces_single(self):
        plan = make_plan(strategy="single")
        result = apply_merge_decision(plan, approve(override_strategy="union"))
        assert result.effective_strategy == "union"

    def test_override_strategy_join_replaces_union(self):
        plan = make_plan(strategy="union")
        result = apply_merge_decision(plan, approve(override_strategy="join"))
        assert result.effective_strategy == "join"

    def test_override_strategy_separate_replaces_join(self):
        plan = make_plan(strategy="join", join_key="id")
        result = apply_merge_decision(plan, approve(override_strategy="separate"))
        assert result.effective_strategy == "separate"

    def test_override_strategy_single_replaces_separate(self):
        plan = make_plan(strategy="separate")
        result = apply_merge_decision(plan, approve(override_strategy="single"))
        assert result.effective_strategy == "single"

    def test_all_valid_strategy_overrides_accepted(self):
        for strategy in VALID_STRATEGIES:
            plan = make_plan(strategy="single")
            result = apply_merge_decision(plan, approve(override_strategy=strategy))
            assert result.effective_strategy == strategy


# ─────────────────────────────────────────────────────────────────────────────
# Effective join key resolution
# ─────────────────────────────────────────────────────────────────────────────

class TestEffectiveJoinKey:

    def test_no_join_key_in_plan_none_in_result(self):
        plan = make_plan(strategy="single", join_key=None)
        result = apply_merge_decision(plan, approve())
        assert result.effective_join_key is None

    def test_plan_join_key_propagates_when_no_override(self):
        plan = make_plan(strategy="join", join_key="customer_id")
        result = apply_merge_decision(plan, approve())
        assert result.effective_join_key == "customer_id"

    def test_override_join_key_replaces_plan_key(self):
        plan = make_plan(strategy="join", join_key="old_key")
        result = apply_merge_decision(plan, approve(override_join_key="new_key"))
        assert result.effective_join_key == "new_key"

    def test_override_join_key_when_plan_has_none(self):
        plan = make_plan(strategy="union", join_key=None)
        result = apply_merge_decision(plan, approve(override_join_key="id"))
        assert result.effective_join_key == "id"

    def test_override_join_key_to_none_not_possible_via_default(self):
        """override_join_key=None means 'no override' — plan key is kept."""
        plan = make_plan(strategy="join", join_key="original_key")
        result = apply_merge_decision(plan, approve(override_join_key=None))
        assert result.effective_join_key == "original_key"


# ─────────────────────────────────────────────────────────────────────────────
# Column exclusion
# ─────────────────────────────────────────────────────────────────────────────

class TestColumnExclusion:

    def test_no_excluded_columns_all_present(self):
        cols = [make_col("a"), make_col("b"), make_col("c")]
        plan = make_plan(columns=cols)
        result = apply_merge_decision(plan, approve())
        assert {c.name for c in result.final_columns} == {"a", "b", "c"}

    def test_single_excluded_column_removed(self):
        cols = [make_col("revenue"), make_col("pii_email", "text"), make_col("region", "categorical")]
        plan = make_plan(columns=cols)
        result = apply_merge_decision(plan, approve(excluded_columns=["pii_email"]))
        names = {c.name for c in result.final_columns}
        assert "pii_email" not in names
        assert "revenue" in names
        assert "region" in names

    def test_multiple_excluded_columns_all_removed(self):
        cols = [make_col("id", "categorical"), make_col("ssn", "text"),
                make_col("dob", "text"), make_col("revenue")]
        plan = make_plan(columns=cols)
        result = apply_merge_decision(plan, approve(excluded_columns=["ssn", "dob"]))
        names = {c.name for c in result.final_columns}
        assert "ssn" not in names
        assert "dob" not in names
        assert "id" in names
        assert "revenue" in names

    def test_exclude_all_columns_returns_empty_final_columns(self):
        cols = [make_col("a"), make_col("b")]
        plan = make_plan(columns=cols)
        result = apply_merge_decision(plan, approve(excluded_columns=["a", "b"]))
        assert result.final_columns == []

    def test_exclude_nonexistent_column_is_silently_ignored(self):
        cols = [make_col("revenue")]
        plan = make_plan(columns=cols)
        result = apply_merge_decision(plan, approve(excluded_columns=["ghost_column"]))
        assert len(result.final_columns) == 1
        assert result.final_columns[0].name == "revenue"

    def test_excluded_column_count_is_correct(self):
        cols = [make_col(f"col_{i}") for i in range(10)]
        plan = make_plan(columns=cols)
        excluded = [f"col_{i}" for i in range(3)]
        result = apply_merge_decision(plan, approve(excluded_columns=excluded))
        assert len(result.final_columns) == 7

    def test_column_order_preserved_after_exclusion(self):
        cols = [make_col("a"), make_col("b"), make_col("c"), make_col("d")]
        plan = make_plan(columns=cols)
        result = apply_merge_decision(plan, approve(excluded_columns=["b"]))
        assert [c.name for c in result.final_columns] == ["a", "c", "d"]


# ─────────────────────────────────────────────────────────────────────────────
# Column routing overrides
# ─────────────────────────────────────────────────────────────────────────────

class TestColumnRoutingOverrides:

    def test_no_overrides_classification_unchanged(self):
        cols = [make_col("notes", "text", "ambiguous")]
        plan = make_plan(columns=cols)
        result = apply_merge_decision(plan, approve())
        assert result.final_columns[0].classification == "ambiguous"

    def test_ambiguous_reclassified_as_textual(self):
        cols = [make_col("notes", "text", "ambiguous")]
        plan = make_plan(columns=cols)
        result = apply_merge_decision(
            plan, approve(column_routing_overrides={"notes": "textual"})
        )
        assert result.final_columns[0].classification == "textual"

    def test_ambiguous_reclassified_as_numeric(self):
        cols = [make_col("code", "text", "ambiguous")]
        plan = make_plan(columns=cols)
        result = apply_merge_decision(
            plan, approve(column_routing_overrides={"code": "numeric"})
        )
        assert result.final_columns[0].classification == "numeric"

    def test_numeric_reclassified_as_textual(self):
        cols = [make_col("product_id", "categorical", "numeric")]
        plan = make_plan(columns=cols)
        result = apply_merge_decision(
            plan, approve(column_routing_overrides={"product_id": "textual"})
        )
        assert result.final_columns[0].classification == "textual"

    def test_textual_reclassified_as_numeric(self):
        cols = [make_col("description", "text", "textual")]
        plan = make_plan(columns=cols)
        result = apply_merge_decision(
            plan, approve(column_routing_overrides={"description": "numeric"})
        )
        assert result.final_columns[0].classification == "numeric"

    def test_multiple_routing_overrides_all_applied(self):
        cols = [
            make_col("notes",   "text",        "ambiguous"),
            make_col("code",    "categorical", "numeric"),
            make_col("revenue", "float",       "numeric"),
        ]
        plan = make_plan(columns=cols)
        overrides = {"notes": "textual", "code": "textual"}
        result = apply_merge_decision(plan, approve(column_routing_overrides=overrides))
        by_name = {c.name: c for c in result.final_columns}
        assert by_name["notes"].classification == "textual"
        assert by_name["code"].classification == "textual"
        assert by_name["revenue"].classification == "numeric"  # unchanged

    def test_routing_override_does_not_change_dtype(self):
        """Routing overrides only change classification, not dtype."""
        cols = [make_col("notes", "text", "ambiguous")]
        plan = make_plan(columns=cols)
        result = apply_merge_decision(
            plan, approve(column_routing_overrides={"notes": "numeric"})
        )
        assert result.final_columns[0].dtype == "text"

    def test_routing_override_does_not_change_null_count(self):
        cols = [ColumnProfile(name="x", dtype="float", null_count=7, classification="ambiguous")]
        plan = make_plan(columns=cols)
        result = apply_merge_decision(
            plan, approve(column_routing_overrides={"x": "numeric"})
        )
        assert result.final_columns[0].null_count == 7

    def test_routing_override_for_nonexistent_column_ignored(self):
        cols = [make_col("revenue")]
        plan = make_plan(columns=cols)
        result = apply_merge_decision(
            plan, approve(column_routing_overrides={"ghost": "textual"})
        )
        assert len(result.final_columns) == 1
        assert result.final_columns[0].name == "revenue"

    def test_excluded_column_not_in_final_even_if_also_overridden(self):
        """Exclusion takes precedence over routing override for the same column."""
        cols = [make_col("pii", "text", "textual"), make_col("revenue")]
        plan = make_plan(columns=cols)
        result = apply_merge_decision(
            plan,
            approve(
                excluded_columns=["pii"],
                column_routing_overrides={"pii": "numeric"},
            ),
        )
        names = {c.name for c in result.final_columns}
        assert "pii" not in names


# ─────────────────────────────────────────────────────────────────────────────
# Combined overrides
# ─────────────────────────────────────────────────────────────────────────────

class TestCombinedOverrides:

    def test_strategy_and_join_key_override_together(self):
        plan = make_plan(strategy="union", join_key=None)
        result = apply_merge_decision(
            plan,
            approve(override_strategy="join", override_join_key="customer_id"),
        )
        assert result.effective_strategy == "join"
        assert result.effective_join_key == "customer_id"

    def test_strategy_override_and_column_exclusion_together(self):
        cols = [make_col("id", "categorical"), make_col("revenue"), make_col("notes", "text")]
        plan = make_plan(strategy="union", columns=cols)
        result = apply_merge_decision(
            plan,
            approve(override_strategy="join", excluded_columns=["notes"]),
        )
        assert result.effective_strategy == "join"
        assert "notes" not in {c.name for c in result.final_columns}

    def test_exclusion_and_routing_override_together(self):
        cols = [make_col("pii", "text", "textual"),
                make_col("code", "text", "ambiguous"),
                make_col("revenue")]
        plan = make_plan(columns=cols)
        result = apply_merge_decision(
            plan,
            approve(
                excluded_columns=["pii"],
                column_routing_overrides={"code": "numeric"},
            ),
        )
        names = {c.name for c in result.final_columns}
        assert "pii" not in names
        by_name = {c.name: c for c in result.final_columns}
        assert by_name["code"].classification == "numeric"
        assert by_name["revenue"].classification == "numeric"

    def test_all_overrides_together(self):
        cols = [
            make_col("id",      "categorical", "numeric"),
            make_col("pii",     "text",        "textual"),
            make_col("notes",   "text",        "ambiguous"),
            make_col("revenue", "float",       "numeric"),
        ]
        plan = make_plan(strategy="union", columns=cols, join_key=None)
        result = apply_merge_decision(
            plan,
            approve(
                override_strategy="join",
                override_join_key="id",
                excluded_columns=["pii"],
                column_routing_overrides={"notes": "textual"},
            ),
        )
        assert result.approved is True
        assert result.effective_strategy == "join"
        assert result.effective_join_key == "id"
        names = {c.name for c in result.final_columns}
        assert "pii" not in names
        by_name = {c.name: c for c in result.final_columns}
        assert by_name["notes"].classification == "textual"
        assert by_name["revenue"].classification == "numeric"


# ─────────────────────────────────────────────────────────────────────────────
# Propose → approve round-trip (full HITL #1 lifecycle)
# ─────────────────────────────────────────────────────────────────────────────

class TestProposeApproveRoundTrip:

    def test_single_file_approve_no_overrides(self):
        cols = [make_col("revenue"), make_col("region", "categorical")]
        plan = agent.propose_merge_plan([("sales.csv", cols)])
        result = apply_merge_decision(plan, approve())
        assert result.approved is True
        assert result.effective_strategy == "single"
        assert len(result.final_columns) == 2

    def test_union_approve_no_overrides(self):
        cols = [make_col("amount"), make_col("date", "categorical")]
        plan = agent.propose_merge_plan([("q1.csv", cols), ("q2.csv", cols)])
        result = apply_merge_decision(plan, approve())
        assert result.effective_strategy == "union"
        assert result.effective_join_key is None

    def test_union_approve_override_to_join(self):
        cols = [make_col("customer_id", "categorical"), make_col("revenue")]
        plan = agent.propose_merge_plan([("q1.csv", cols), ("q2.csv", cols)])
        assert plan.strategy == "union"
        result = apply_merge_decision(
            plan, approve(override_strategy="join", override_join_key="customer_id")
        )
        assert result.effective_strategy == "join"
        assert result.effective_join_key == "customer_id"

    def test_join_approve_no_overrides(self):
        cols_a = [make_col("cust_id", "categorical"), make_col("revenue")]
        cols_b = [make_col("cust_id", "categorical"), make_col("email", "text")]
        plan = agent.propose_merge_plan([("sales.csv", cols_a), ("crm.csv", cols_b)])
        result = apply_merge_decision(plan, approve())
        assert result.effective_strategy == "join"
        assert result.effective_join_key == "cust_id"

    def test_join_approve_override_key(self):
        cols_a = [make_col("cust_id", "categorical"), make_col("revenue")]
        cols_b = [make_col("cust_id", "categorical"), make_col("spend")]
        plan = agent.propose_merge_plan([("a.csv", cols_a), ("b.csv", cols_b)])
        result = apply_merge_decision(
            plan, approve(override_join_key="revenue")
        )
        assert result.effective_join_key == "revenue"

    def test_separate_approve_override_to_union(self):
        cols_a = [make_col("revenue"), make_col("region", "categorical")]
        cols_b = [make_col("patient_id", "categorical"), make_col("los")]
        plan = agent.propose_merge_plan([("finance.csv", cols_a), ("health.csv", cols_b)])
        assert plan.strategy == "separate"
        result = apply_merge_decision(plan, approve(override_strategy="union"))
        assert result.effective_strategy == "union"

    def test_single_file_reject_pipeline_aborted(self):
        cols = [make_col("revenue")]
        plan = agent.propose_merge_plan([("sales.csv", cols)])
        result = apply_merge_decision(plan, reject())
        assert result.approved is False
        assert result.final_columns == []

    def test_union_with_pii_exclusion(self):
        cols = [make_col("email", "text", "textual"),
                make_col("revenue"),
                make_col("region", "categorical")]
        plan = agent.propose_merge_plan([("a.csv", cols), ("b.csv", cols)])
        result = apply_merge_decision(plan, approve(excluded_columns=["email"]))
        names = {c.name for c in result.final_columns}
        assert "email" not in names
        assert "revenue" in names

    def test_join_with_ambiguous_column_reclassified(self):
        cols_a = [make_col("id", "categorical"), make_col("revenue")]
        cols_b = [make_col("id", "categorical"), make_col("category", "text", "ambiguous")]
        plan = agent.propose_merge_plan([("a.csv", cols_a), ("b.csv", cols_b)])
        result = apply_merge_decision(
            plan,
            approve(column_routing_overrides={"category": "textual"}),
        )
        by_name = {c.name: c for c in result.final_columns}
        assert by_name["category"].classification == "textual"

    def test_full_override_single_file(self):
        """Single-file upload; user reroutes one ambiguous column and excludes another."""
        cols = [
            make_col("order_id",    "categorical", "numeric"),
            make_col("notes",       "text",        "ambiguous"),
            make_col("internal_ip", "text",        "textual"),
            make_col("revenue",     "float",       "numeric"),
        ]
        plan = agent.propose_merge_plan([("orders.csv", cols)])
        result = apply_merge_decision(
            plan,
            approve(
                excluded_columns=["internal_ip"],
                column_routing_overrides={"notes": "textual"},
            ),
        )
        assert result.approved is True
        assert result.effective_strategy == "single"
        names = {c.name for c in result.final_columns}
        assert "internal_ip" not in names
        by_name = {c.name: c for c in result.final_columns}
        assert by_name["notes"].classification == "textual"
        assert by_name["revenue"].classification == "numeric"


# ─────────────────────────────────────────────────────────────────────────────
# Edge cases & robustness
# ─────────────────────────────────────────────────────────────────────────────

class TestEdgeCases:

    def test_empty_columns_approve_returns_empty_final_columns(self):
        plan = MergePlan(strategy="single", confidence=0.99, column_profiles=[])
        result = apply_merge_decision(plan, approve())
        assert result.final_columns == []

    def test_empty_columns_reject_also_empty(self):
        plan = MergePlan(strategy="single", confidence=0.99, column_profiles=[])
        result = apply_merge_decision(plan, reject())
        assert result.final_columns == []

    def test_single_column_approved(self):
        plan = make_plan(columns=[make_col("revenue")])
        result = apply_merge_decision(plan, approve())
        assert len(result.final_columns) == 1
        assert result.final_columns[0].name == "revenue"

    def test_many_columns_all_preserved(self):
        cols = [make_col(f"col_{i}") for i in range(50)]
        plan = make_plan(columns=cols)
        result = apply_merge_decision(plan, approve())
        assert len(result.final_columns) == 50

    def test_plan_column_profiles_not_mutated_by_decision(self):
        """apply_merge_decision must not modify the original MergePlan."""
        cols = [make_col("notes", "text", "ambiguous")]
        plan = make_plan(columns=cols)
        apply_merge_decision(
            plan, approve(column_routing_overrides={"notes": "textual"})
        )
        # Original plan column classification must be unchanged
        assert plan.column_profiles[0].classification == "ambiguous"

    def test_confidence_value_preserved_in_plan(self):
        """MergeDecisionResult doesn't expose confidence (it's on MergePlan), but
        the plan object itself must still be intact after the decision call."""
        plan = make_plan(strategy="union", confidence=0.92)
        apply_merge_decision(plan, approve())
        assert plan.confidence == 0.92

    def test_duplicate_excluded_column_names_handled(self):
        cols = [make_col("revenue"), make_col("pii", "text", "textual")]
        plan = make_plan(columns=cols)
        # Same column listed twice in excluded_columns
        result = apply_merge_decision(plan, approve(excluded_columns=["pii", "pii"]))
        assert "pii" not in {c.name for c in result.final_columns}
        assert len(result.final_columns) == 1

    def test_all_strategies_round_trip_approved(self):
        for strategy in VALID_STRATEGIES:
            plan = make_plan(strategy=strategy)
            result = apply_merge_decision(plan, approve())
            assert result.approved is True
            assert result.effective_strategy == strategy

    def test_all_routing_values_accepted_in_overrides(self):
        for routing in VALID_ROUTINGS:
            cols = [make_col("target", "text", "ambiguous")]
            plan = make_plan(columns=cols)
            result = apply_merge_decision(
                plan, approve(column_routing_overrides={"target": routing})
            )
            assert result.final_columns[0].classification == routing


# ═════════════════════════════════════════════════════════════════════════════
# Runner
# ═════════════════════════════════════════════════════════════════════════════

def _collect_all_test_classes():
    return [
        TestProposeSingleFile,
        TestProposeUnion,
        TestProposeJoin,
        TestProposeSeparate,
        TestDecisionApprovedTrue,
        TestDecisionApprovedFalse,
        TestEffectiveStrategy,
        TestEffectiveJoinKey,
        TestColumnExclusion,
        TestColumnRoutingOverrides,
        TestCombinedOverrides,
        TestProposeApproveRoundTrip,
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