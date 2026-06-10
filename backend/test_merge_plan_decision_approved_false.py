"""
Unit tests — Merge-Plan Decision with approved=False

Tests cover every aspect of the rejection path through HITL #1:
    MergePlanDecision(approved=False)  — model construction
    apply_merge_decision(plan, reject) — executor behaviour on rejection
    Pipeline abort contract            — downstream must see a clean stop signal

Architecture ref : architecture.md §HITL Checkpoints #1
    "Pipeline BLOCKS until user POSTs decision to
     /datasets/{id}/merge-plan/decision."
    approved=False  →  pipeline aborts; no cleaning, no routing, no DB writes.

PRD ref : §4 — "never run data cleaning silently: every cleaning step is
    proposed to the user as a plan, the user approves … only then does
    the agent execute."  The same principle applies at merge time.

Run with:
    pytest  test_merge_plan_decision_rejected.py -v
    python  test_merge_plan_decision_rejected.py    # live results, no pytest needed

Fully independent — no LLM, no DB, no Supabase, no app imports.
All shared infrastructure (dataclasses, apply_merge_decision, helpers)
is reproduced verbatim so this file runs entirely on its own.
"""

from __future__ import annotations

import sys
import traceback
from dataclasses import dataclass, field
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
# Shared schema stand-ins  (mirrors app/models/schemas.py)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ColumnProfile:
    name: str
    dtype: str                       # "float" | "categorical" | "text" | "int64" …
    null_count: int = 0
    distinct_count: int = 10
    avg_length: Optional[float] = None
    classification: str = "numeric"  # "numeric" | "textual" | "ambiguous"


@dataclass
class MergePlan:
    strategy: str                    # "single" | "union" | "join" | "separate"
    confidence: float
    column_profiles: list[ColumnProfile]
    join_key: Optional[str] = None


@dataclass
class MergePlanDecision:
    approved: bool
    override_strategy: Optional[str] = None
    override_join_key: Optional[str] = None
    excluded_columns: list[str] = field(default_factory=list)
    column_routing_overrides: dict[str, str] = field(default_factory=dict)


@dataclass
class MergeDecisionResult:
    approved: bool
    effective_strategy: str
    effective_join_key: Optional[str]
    final_columns: list[ColumnProfile]
    column_profiles: list[ColumnProfile]


# ─────────────────────────────────────────────────────────────────────────────
# IngestionAgent.propose_merge_plan()  (verbatim port from ingestion.py)
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
# apply_merge_decision()  (verbatim port — the unit under closest test)
# ─────────────────────────────────────────────────────────────────────────────

VALID_STRATEGIES = {"single", "union", "join", "separate"}
VALID_ROUTINGS   = {"numeric", "textual", "ambiguous"}


def apply_merge_decision(
    plan: MergePlan,
    decision: MergePlanDecision,
) -> MergeDecisionResult:
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
# Pipeline abort tracker
# Used to verify that downstream stages are never entered after a rejection.
# ─────────────────────────────────────────────────────────────────────────────

class PipelineStageTracker:
    """Records which pipeline stages were called after apply_merge_decision()."""

    def __init__(self) -> None:
        self.stages_entered: list[str] = []

    def maybe_enter_stage(self, stage_name: str, result: MergeDecisionResult) -> bool:
        """
        Simulates a pipeline gate check.
        Returns True and records the stage only if result.approved is True.
        Downstream stages (cleaning, routing, DB writes) call this before proceeding.
        """
        if not result.approved:
            return False
        self.stages_entered.append(stage_name)
        return True

    def entered(self, stage_name: str) -> bool:
        return stage_name in self.stages_entered


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def make_col(
    name: str,
    dtype: str = "float",
    classification: str = "numeric",
    null_count: int = 0,
) -> ColumnProfile:
    return ColumnProfile(
        name=name, dtype=dtype,
        classification=classification, null_count=null_count,
    )


def make_plan(
    strategy: str = "single",
    confidence: float = 0.99,
    columns: Optional[list[ColumnProfile]] = None,
    join_key: Optional[str] = None,
) -> MergePlan:
    cols = columns if columns is not None else [
        make_col("revenue"), make_col("region", "categorical"),
    ]
    return MergePlan(
        strategy=strategy,
        confidence=confidence,
        column_profiles=cols,
        join_key=join_key,
    )


def reject(
    override_strategy: Optional[str] = None,
    override_join_key: Optional[str] = None,
    excluded_columns: Optional[list[str]] = None,
    column_routing_overrides: Optional[dict[str, str]] = None,
) -> MergePlanDecision:
    """
    Builds a MergePlanDecision with approved=False.
    Optional fields let tests verify overrides are still ignored on rejection.
    """
    return MergePlanDecision(
        approved=False,
        override_strategy=override_strategy,
        override_join_key=override_join_key,
        excluded_columns=excluded_columns or [],
        column_routing_overrides=column_routing_overrides or {},
    )


def approve() -> MergePlanDecision:
    return MergePlanDecision(approved=True)


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
        print("  Merge-Plan Decision (approved=False) — test results")
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
# MergePlanDecision model — approved=False construction
# ─────────────────────────────────────────────────────────────────────────────

class TestRejectionModelConstruction:
    """Verify the MergePlanDecision object is correctly built with approved=False."""

    def test_approved_flag_is_false(self):
        decision = reject()
        assert decision.approved is False

    def test_approved_is_bool_not_falsy_value(self):
        decision = reject()
        assert type(decision.approved) is bool

    def test_approved_false_is_not_none(self):
        decision = reject()
        assert decision.approved is not None

    def test_approved_false_is_bool_not_int_zero(self):
        """bool is a subclass of int in Python so False == 0 is True by design.
        The correct guarantee: approved is typed bool, not bare int."""
        decision = reject()
        assert type(decision.approved) is bool
        assert decision.approved is False

    def test_default_override_strategy_is_none(self):
        decision = reject()
        assert decision.override_strategy is None

    def test_default_override_join_key_is_none(self):
        decision = reject()
        assert decision.override_join_key is None

    def test_default_excluded_columns_is_empty_list(self):
        decision = reject()
        assert decision.excluded_columns == []

    def test_default_column_routing_overrides_is_empty_dict(self):
        decision = reject()
        assert decision.column_routing_overrides == {}

    def test_rejected_with_override_strategy_still_has_approved_false(self):
        decision = reject(override_strategy="union")
        assert decision.approved is False

    def test_rejected_with_override_join_key_still_has_approved_false(self):
        decision = reject(override_join_key="customer_id")
        assert decision.approved is False

    def test_rejected_with_excluded_columns_still_has_approved_false(self):
        decision = reject(excluded_columns=["pii_email"])
        assert decision.approved is False

    def test_rejected_with_routing_overrides_still_has_approved_false(self):
        decision = reject(column_routing_overrides={"notes": "textual"})
        assert decision.approved is False

    def test_rejected_with_all_fields_populated_approved_is_false(self):
        decision = MergePlanDecision(
            approved=False,
            override_strategy="join",
            override_join_key="id",
            excluded_columns=["col_a", "col_b"],
            column_routing_overrides={"notes": "textual"},
        )
        assert decision.approved is False


# ─────────────────────────────────────────────────────────────────────────────
# apply_merge_decision — core rejection contract
# ─────────────────────────────────────────────────────────────────────────────

class TestRejectionCoreContract:
    """The six hard guarantees every rejection must satisfy."""

    def test_result_approved_is_false(self):
        result = apply_merge_decision(make_plan(), reject())
        assert result.approved is False

    def test_result_is_merge_decision_result_instance(self):
        result = apply_merge_decision(make_plan(), reject())
        assert isinstance(result, MergeDecisionResult)

    def test_final_columns_is_empty_list(self):
        plan = make_plan(columns=[make_col("revenue"), make_col("region", "categorical")])
        result = apply_merge_decision(plan, reject())
        assert result.final_columns == []

    def test_column_profiles_is_empty_list(self):
        plan = make_plan(columns=[make_col("revenue"), make_col("region", "categorical")])
        result = apply_merge_decision(plan, reject())
        assert result.column_profiles == []

    def test_final_columns_and_column_profiles_both_empty(self):
        result = apply_merge_decision(make_plan(), reject())
        assert result.final_columns == [] and result.column_profiles == []

    def test_does_not_raise_any_exception(self):
        try:
            apply_merge_decision(make_plan(), reject())
        except Exception as exc:
            raise AssertionError(f"apply_merge_decision raised on rejection: {exc}") from exc

    def test_returns_immediately_without_processing_columns(self):
        """Rejection must short-circuit before any column iteration."""
        # Use a large column list — if processing happened, the behaviour would
        # differ depending on excluded_columns; with rejection it must always be [].
        cols = [make_col(f"col_{i}") for i in range(100)]
        plan = make_plan(columns=cols)
        result = apply_merge_decision(plan, reject())
        assert result.final_columns == []


# ─────────────────────────────────────────────────────────────────────────────
# effective_strategy on rejection — echoes plan strategy for audit
# ─────────────────────────────────────────────────────────────────────────────

class TestRejectionEffectiveStrategyAudit:
    """
    On rejection the result still records the *original* proposed strategy.
    This is required for the hitl_decisions audit log — the operator must be
    able to see what was proposed and that it was rejected.
    """

    def test_single_strategy_echoed(self):
        plan = make_plan(strategy="single")
        result = apply_merge_decision(plan, reject())
        assert result.effective_strategy == "single"

    def test_union_strategy_echoed(self):
        plan = make_plan(strategy="union")
        result = apply_merge_decision(plan, reject())
        assert result.effective_strategy == "union"

    def test_join_strategy_echoed(self):
        plan = make_plan(strategy="join", join_key="customer_id")
        result = apply_merge_decision(plan, reject())
        assert result.effective_strategy == "join"

    def test_separate_strategy_echoed(self):
        plan = make_plan(strategy="separate")
        result = apply_merge_decision(plan, reject())
        assert result.effective_strategy == "separate"

    def test_effective_strategy_echoes_plan_not_override(self):
        """Even if the rejection carried an override_strategy, the echo must
        reflect the original proposal — rejection means the pipeline stops,
        not that the override is applied."""
        plan = make_plan(strategy="single")
        result = apply_merge_decision(plan, reject(override_strategy="union"))
        assert result.effective_strategy == "single"

    def test_all_strategies_echoed_correctly(self):
        for strategy in VALID_STRATEGIES:
            plan = make_plan(strategy=strategy)
            result = apply_merge_decision(plan, reject())
            assert result.effective_strategy == strategy, (
                f"Expected '{strategy}' echoed, got '{result.effective_strategy}'"
            )


# ─────────────────────────────────────────────────────────────────────────────
# effective_join_key on rejection — echoes plan join_key for audit
# ─────────────────────────────────────────────────────────────────────────────

class TestRejectionEffectiveJoinKeyAudit:

    def test_none_join_key_echoed_as_none(self):
        plan = make_plan(strategy="single", join_key=None)
        result = apply_merge_decision(plan, reject())
        assert result.effective_join_key is None

    def test_join_key_echoed_verbatim(self):
        plan = make_plan(strategy="join", join_key="customer_id")
        result = apply_merge_decision(plan, reject())
        assert result.effective_join_key == "customer_id"

    def test_join_key_echoed_not_overridden(self):
        """override_join_key in the rejection must not replace the echoed key."""
        plan = make_plan(strategy="join", join_key="original_key")
        result = apply_merge_decision(plan, reject(override_join_key="new_key"))
        assert result.effective_join_key == "original_key"

    def test_union_plan_join_key_none_echoed(self):
        cols = [make_col("revenue"), make_col("region", "categorical")]
        plan = agent.propose_merge_plan([("a.csv", cols), ("b.csv", cols)])
        assert plan.join_key is None
        result = apply_merge_decision(plan, reject())
        assert result.effective_join_key is None

    def test_join_plan_join_key_echoed(self):
        cols_a = [make_col("cust_id", "categorical"), make_col("revenue")]
        cols_b = [make_col("cust_id", "categorical"), make_col("email", "text")]
        plan = agent.propose_merge_plan([("a.csv", cols_a), ("b.csv", cols_b)])
        assert plan.join_key == "cust_id"
        result = apply_merge_decision(plan, reject())
        assert result.effective_join_key == "cust_id"


# ─────────────────────────────────────────────────────────────────────────────
# Overrides are ignored on rejection
# ─────────────────────────────────────────────────────────────────────────────

class TestOverridesIgnoredOnRejection:
    """
    Any override field supplied alongside approved=False must have zero effect.
    The pipeline aborts; there is nothing to override.
    """

    def test_override_strategy_ignored(self):
        plan = make_plan(strategy="single")
        result = apply_merge_decision(plan, reject(override_strategy="union"))
        assert result.approved is False
        assert result.final_columns == []

    def test_override_join_key_ignored(self):
        plan = make_plan(strategy="join", join_key="old_key")
        result = apply_merge_decision(plan, reject(override_join_key="new_key"))
        assert result.approved is False
        assert result.final_columns == []

    def test_excluded_columns_ignored(self):
        cols = [make_col("revenue"), make_col("pii", "text", "textual")]
        plan = make_plan(columns=cols)
        result = apply_merge_decision(plan, reject(excluded_columns=["pii"]))
        # columns are empty regardless — exclusion was not applied
        assert result.final_columns == []

    def test_routing_overrides_ignored(self):
        cols = [make_col("notes", "text", "ambiguous")]
        plan = make_plan(columns=cols)
        result = apply_merge_decision(
            plan, reject(column_routing_overrides={"notes": "textual"})
        )
        assert result.final_columns == []

    def test_all_overrides_together_still_rejected(self):
        cols = [make_col("id", "categorical"), make_col("revenue"), make_col("pii", "text")]
        plan = make_plan(strategy="union", columns=cols)
        result = apply_merge_decision(
            plan,
            reject(
                override_strategy="join",
                override_join_key="id",
                excluded_columns=["pii"],
                column_routing_overrides={"revenue": "textual"},
            ),
        )
        assert result.approved is False
        assert result.final_columns == []
        assert result.column_profiles == []

    def test_override_strategy_does_not_appear_in_effective_strategy(self):
        plan = make_plan(strategy="single")
        result = apply_merge_decision(plan, reject(override_strategy="join"))
        # effective_strategy reflects the original proposal, not the override
        assert result.effective_strategy == "single"

    def test_rejected_result_carries_no_column_data_at_all(self):
        """Both column fields must be empty — no partial data can leak through."""
        cols = [make_col(f"c{i}") for i in range(20)]
        plan = make_plan(columns=cols)
        result = apply_merge_decision(plan, reject())
        assert len(result.final_columns) == 0
        assert len(result.column_profiles) == 0


# ─────────────────────────────────────────────────────────────────────────────
# Plan is not mutated by rejection
# ─────────────────────────────────────────────────────────────────────────────

class TestPlanNotMutatedByRejection:
    """
    apply_merge_decision() must never modify the MergePlan it receives.
    The plan must be reusable (e.g. for audit logging or re-proposal).
    """

    def test_plan_strategy_unchanged_after_rejection(self):
        plan = make_plan(strategy="union")
        apply_merge_decision(plan, reject())
        assert plan.strategy == "union"

    def test_plan_confidence_unchanged_after_rejection(self):
        plan = make_plan(confidence=0.92)
        apply_merge_decision(plan, reject())
        assert plan.confidence == 0.92

    def test_plan_join_key_unchanged_after_rejection(self):
        plan = make_plan(strategy="join", join_key="customer_id")
        apply_merge_decision(plan, reject())
        assert plan.join_key == "customer_id"

    def test_plan_column_profiles_list_unchanged_after_rejection(self):
        cols = [make_col("revenue"), make_col("region", "categorical")]
        plan = make_plan(columns=cols)
        apply_merge_decision(plan, reject())
        assert len(plan.column_profiles) == 2

    def test_plan_column_profile_names_unchanged_after_rejection(self):
        cols = [make_col("revenue"), make_col("region", "categorical")]
        plan = make_plan(columns=cols)
        apply_merge_decision(plan, reject())
        assert [p.name for p in plan.column_profiles] == ["revenue", "region"]

    def test_plan_column_classification_unchanged_after_rejection(self):
        cols = [make_col("notes", "text", "ambiguous")]
        plan = make_plan(columns=cols)
        apply_merge_decision(plan, reject(column_routing_overrides={"notes": "textual"}))
        assert plan.column_profiles[0].classification == "ambiguous"

    def test_plan_reusable_for_approval_after_rejection(self):
        """The same plan object can be passed to a subsequent approve() call."""
        cols = [make_col("revenue"), make_col("region", "categorical")]
        plan = make_plan(strategy="union", columns=cols)
        apply_merge_decision(plan, reject())          # first call — rejected
        result = apply_merge_decision(plan, approve())  # second call — approved
        assert result.approved is True
        assert len(result.final_columns) == 2


# ─────────────────────────────────────────────────────────────────────────────
# Rejection across all propose_merge_plan strategies
# ─────────────────────────────────────────────────────────────────────────────

class TestRejectionAcrossAllStrategies:
    """
    Every strategy the agent can propose must reject cleanly.
    None of the strategy-specific logic must run on rejection.
    """

    def test_single_file_proposal_rejected(self):
        cols = [make_col("revenue"), make_col("region", "categorical")]
        plan = agent.propose_merge_plan([("sales.csv", cols)])
        assert plan.strategy == "single"
        result = apply_merge_decision(plan, reject())
        assert result.approved is False
        assert result.final_columns == []

    def test_union_proposal_rejected(self):
        cols = [make_col("amount"), make_col("date", "categorical")]
        plan = agent.propose_merge_plan([("q1.csv", cols), ("q2.csv", cols)])
        assert plan.strategy == "union"
        result = apply_merge_decision(plan, reject())
        assert result.approved is False
        assert result.final_columns == []

    def test_join_proposal_rejected(self):
        cols_a = [make_col("cust_id", "categorical"), make_col("revenue")]
        cols_b = [make_col("cust_id", "categorical"), make_col("email", "text")]
        plan = agent.propose_merge_plan([("sales.csv", cols_a), ("crm.csv", cols_b)])
        assert plan.strategy == "join"
        result = apply_merge_decision(plan, reject())
        assert result.approved is False
        assert result.final_columns == []

    def test_separate_proposal_rejected(self):
        cols_a = [make_col("revenue"), make_col("region", "categorical")]
        cols_b = [make_col("patient_id", "categorical"), make_col("los")]
        plan = agent.propose_merge_plan([("finance.csv", cols_a), ("health.csv", cols_b)])
        assert plan.strategy == "separate"
        result = apply_merge_decision(plan, reject())
        assert result.approved is False
        assert result.final_columns == []

    def test_low_confidence_join_rejected(self):
        """A 0.75-confidence join proposal that the user doesn't trust."""
        cols_a = [make_col("order_id", "categorical"), make_col("revenue")]
        cols_b = [make_col("order_id", "categorical"), make_col("shipping_cost")]
        plan = agent.propose_merge_plan([("orders.csv", cols_a), ("logistics.csv", cols_b)])
        assert plan.confidence == 0.75
        result = apply_merge_decision(plan, reject())
        assert result.approved is False

    def test_low_confidence_separate_rejected(self):
        """A 0.55-confidence separate proposal — user rejects to investigate schemas."""
        cols_a = [make_col("revenue")]
        cols_b = [make_col("patient_count")]
        plan = agent.propose_merge_plan([("a.csv", cols_a), ("b.csv", cols_b)])
        assert plan.confidence == 0.55
        result = apply_merge_decision(plan, reject())
        assert result.approved is False


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline abort — downstream stages must not execute after rejection
# ─────────────────────────────────────────────────────────────────────────────

class TestPipelineAbortAfterRejection:
    """
    Simulates the pipeline gate pattern: each downstream stage checks
    result.approved before proceeding.  All must be blocked on rejection.
    """

    DOWNSTREAM_STAGES = [
        "type_routing",
        "layer3_write",
        "layer4_embedding",
        "cleaning_plan",
        "cleaning_execution",
        "intent_parse",
        "analysis",
        "dashboard_generate",
    ]

    def _run_pipeline(self, result: MergeDecisionResult) -> PipelineStageTracker:
        tracker = PipelineStageTracker()
        for stage in self.DOWNSTREAM_STAGES:
            tracker.maybe_enter_stage(stage, result)
        return tracker

    def test_no_downstream_stage_entered_on_rejection(self):
        result = apply_merge_decision(make_plan(), reject())
        tracker = self._run_pipeline(result)
        assert tracker.stages_entered == []

    def test_type_routing_not_entered(self):
        result = apply_merge_decision(make_plan(), reject())
        tracker = self._run_pipeline(result)
        assert not tracker.entered("type_routing")

    def test_layer3_write_not_entered(self):
        result = apply_merge_decision(make_plan(), reject())
        tracker = self._run_pipeline(result)
        assert not tracker.entered("layer3_write")

    def test_layer4_embedding_not_entered(self):
        result = apply_merge_decision(make_plan(), reject())
        tracker = self._run_pipeline(result)
        assert not tracker.entered("layer4_embedding")

    def test_cleaning_plan_not_entered(self):
        result = apply_merge_decision(make_plan(), reject())
        tracker = self._run_pipeline(result)
        assert not tracker.entered("cleaning_plan")

    def test_cleaning_execution_not_entered(self):
        result = apply_merge_decision(make_plan(), reject())
        tracker = self._run_pipeline(result)
        assert not tracker.entered("cleaning_execution")

    def test_intent_parse_not_entered(self):
        result = apply_merge_decision(make_plan(), reject())
        tracker = self._run_pipeline(result)
        assert not tracker.entered("intent_parse")

    def test_analysis_not_entered(self):
        result = apply_merge_decision(make_plan(), reject())
        tracker = self._run_pipeline(result)
        assert not tracker.entered("analysis")

    def test_dashboard_generate_not_entered(self):
        result = apply_merge_decision(make_plan(), reject())
        tracker = self._run_pipeline(result)
        assert not tracker.entered("dashboard_generate")

    def test_approved_true_does_enter_downstream_stages(self):
        """Sanity check: approval does proceed into downstream stages."""
        result = apply_merge_decision(make_plan(), approve())
        tracker = self._run_pipeline(result)
        assert tracker.stages_entered == self.DOWNSTREAM_STAGES

    def test_gate_check_idempotent_on_rejection(self):
        """Calling maybe_enter_stage twice on the same rejected result is safe."""
        result = apply_merge_decision(make_plan(), reject())
        tracker = PipelineStageTracker()
        tracker.maybe_enter_stage("cleaning_plan", result)
        tracker.maybe_enter_stage("cleaning_plan", result)
        assert tracker.stages_entered == []


# ─────────────────────────────────────────────────────────────────────────────
# Re-proposal after rejection (retry semantics)
# ─────────────────────────────────────────────────────────────────────────────

class TestReProposalAfterRejection:
    """
    After a user rejects, the agent may propose a revised plan
    (e.g. different strategy or schema) and the user approves the second attempt.
    The system must handle this gracefully.
    """

    def test_second_proposal_approved_after_first_rejected(self):
        cols = [make_col("revenue"), make_col("region", "categorical")]
        plan = agent.propose_merge_plan([("sales.csv", cols)])

        first = apply_merge_decision(plan, reject())
        assert first.approved is False

        second = apply_merge_decision(plan, approve())
        assert second.approved is True
        assert len(second.final_columns) == 2

    def test_rejection_then_different_plan_approved(self):
        cols_a = [make_col("cust_id", "categorical"), make_col("revenue")]
        cols_b = [make_col("cust_id", "categorical"), make_col("email", "text")]
        plan_join = agent.propose_merge_plan([("a.csv", cols_a), ("b.csv", cols_b)])
        assert plan_join.strategy == "join"

        first = apply_merge_decision(plan_join, reject())
        assert first.approved is False

        # User uploads a third file with matching schema → union proposed instead
        cols_c = cols_a
        plan_union = agent.propose_merge_plan([("a.csv", cols_a), ("c.csv", cols_c)])
        assert plan_union.strategy == "union"
        second = apply_merge_decision(plan_union, approve())
        assert second.approved is True
        assert second.effective_strategy == "union"

    def test_multiple_rejections_then_approval(self):
        plan = make_plan(strategy="separate")
        for _ in range(3):
            r = apply_merge_decision(plan, reject())
            assert r.approved is False
        final = apply_merge_decision(plan, approve())
        assert final.approved is True

    def test_rejection_does_not_poison_subsequent_approval_result(self):
        """Columns returned by a later approval must be complete, not empty."""
        cols = [make_col("revenue"), make_col("region", "categorical"), make_col("notes", "text")]
        plan = make_plan(columns=cols)
        apply_merge_decision(plan, reject())
        result = apply_merge_decision(plan, approve())
        assert len(result.final_columns) == 3

    def test_plan_confidence_unchanged_across_reject_then_approve(self):
        plan = make_plan(confidence=0.92)
        apply_merge_decision(plan, reject())
        apply_merge_decision(plan, approve())
        assert plan.confidence == 0.92


# ─────────────────────────────────────────────────────────────────────────────
# Rejection with various plan shapes
# ─────────────────────────────────────────────────────────────────────────────

class TestRejectionWithVariousPlanShapes:

    def test_empty_column_plan_rejected(self):
        plan = MergePlan(strategy="single", confidence=0.99, column_profiles=[])
        result = apply_merge_decision(plan, reject())
        assert result.approved is False
        assert result.final_columns == []

    def test_single_column_plan_rejected(self):
        plan = MergePlan(
            strategy="single", confidence=0.99,
            column_profiles=[make_col("revenue")],
        )
        result = apply_merge_decision(plan, reject())
        assert result.approved is False
        assert result.final_columns == []

    def test_large_column_plan_rejected(self):
        cols = [make_col(f"col_{i}") for i in range(100)]
        plan = make_plan(columns=cols)
        result = apply_merge_decision(plan, reject())
        assert result.final_columns == []

    def test_plan_with_all_textual_columns_rejected(self):
        cols = [make_col(f"text_{i}", "text", "textual") for i in range(5)]
        plan = make_plan(columns=cols)
        result = apply_merge_decision(plan, reject())
        assert result.final_columns == []

    def test_plan_with_all_ambiguous_columns_rejected(self):
        cols = [make_col(f"amb_{i}", "text", "ambiguous") for i in range(5)]
        plan = make_plan(columns=cols)
        result = apply_merge_decision(plan, reject())
        assert result.final_columns == []

    def test_plan_with_mixed_classifications_rejected(self):
        cols = [
            make_col("revenue",     "float",       "numeric"),
            make_col("notes",       "text",        "textual"),
            make_col("code",        "categorical", "ambiguous"),
        ]
        plan = make_plan(columns=cols)
        result = apply_merge_decision(plan, reject())
        assert result.final_columns == []

    def test_plan_with_null_heavy_columns_rejected(self):
        cols = [make_col("sparse", "float", "numeric", null_count=90)]
        plan = make_plan(columns=cols)
        result = apply_merge_decision(plan, reject())
        assert result.final_columns == []

    def test_zero_confidence_plan_rejected(self):
        plan = MergePlan(strategy="separate", confidence=0.0, column_profiles=[make_col("x")])
        result = apply_merge_decision(plan, reject())
        assert result.approved is False

    def test_full_confidence_plan_rejected(self):
        plan = MergePlan(strategy="single", confidence=1.0, column_profiles=[make_col("x")])
        result = apply_merge_decision(plan, reject())
        assert result.approved is False

    def test_join_plan_with_join_key_rejected(self):
        cols_a = [make_col("id", "categorical"), make_col("revenue")]
        cols_b = [make_col("id", "categorical"), make_col("cost")]
        plan = agent.propose_merge_plan([("a.csv", cols_a), ("b.csv", cols_b)])
        result = apply_merge_decision(plan, reject())
        assert result.approved is False
        assert result.final_columns == []


# ─────────────────────────────────────────────────────────────────────────────
# Rejection for real-world HITL #1 scenarios
# ─────────────────────────────────────────────────────────────────────────────

class TestRealWorldRejectionScenarios:
    """
    Business-realistic rejection reasons mapped to concrete test cases.
    Each documents *why* a user would reject, not just that they can.
    """

    def test_schema_mismatch_user_rejects_separate_strategy(self):
        """User expected a union but got 'separate' — rejects to fix the files."""
        cols_a = [make_col("revenue"), make_col("region", "categorical")]
        cols_b = [make_col("sales"),   make_col("territory", "categorical")]
        plan = agent.propose_merge_plan([("q1.csv", cols_a), ("q2.csv", cols_b)])
        assert plan.strategy == "separate"
        result = apply_merge_decision(plan, reject())
        assert result.approved is False

    def test_wrong_join_key_user_rejects_join_strategy(self):
        """Agent picked the wrong common column as join key — user rejects."""
        cols_a = [make_col("status", "categorical"), make_col("revenue")]
        cols_b = [make_col("status", "categorical"), make_col("cost")]
        plan = agent.propose_merge_plan([("a.csv", cols_a), ("b.csv", cols_b)])
        # 'status' is common but is a poor join key — user rejects
        assert plan.strategy == "join"
        assert plan.join_key == "status"
        result = apply_merge_decision(plan, reject())
        assert result.approved is False

    def test_pii_concern_user_rejects_before_routing(self):
        """User notices PII columns would be routed to Layer 3 — rejects to review."""
        cols = [
            make_col("patient_ssn",  "text", "textual"),
            make_col("patient_name", "text", "textual"),
            make_col("los", "float", "numeric"),
        ]
        plan = agent.propose_merge_plan([("ehr.csv", cols)])
        result = apply_merge_decision(plan, reject())
        assert result.approved is False
        # Critical: PII columns must NOT be in final_columns
        assert result.final_columns == []

    def test_low_confidence_proposal_user_rejects(self):
        """0.55 confidence on 'separate' — user rejects to investigate."""
        cols_a = [make_col("mrr"), make_col("arr")]
        cols_b = [make_col("ctr"), make_col("cpa")]
        plan = agent.propose_merge_plan([("finance.csv", cols_a), ("marketing.csv", cols_b)])
        assert plan.confidence == 0.55
        result = apply_merge_decision(plan, reject())
        assert result.approved is False

    def test_wrong_file_uploaded_user_rejects(self):
        """User uploaded the wrong file — rejects the entire merge plan."""
        cols = [make_col("personal_notes", "text", "textual")]
        plan = agent.propose_merge_plan([("wrong_file.csv", cols)])
        result = apply_merge_decision(plan, reject())
        assert result.approved is False
        assert result.final_columns == []

    def test_multi_file_union_rejected_because_schemas_diverged(self):
        """Agent says UNION but user knows Q3 had a schema change — rejects."""
        cols_q1 = [make_col("revenue"), make_col("region", "categorical")]
        cols_q2 = [make_col("revenue"), make_col("region", "categorical")]
        plan = agent.propose_merge_plan([("q1.csv", cols_q1), ("q2.csv", cols_q2)])
        assert plan.strategy == "union"
        result = apply_merge_decision(plan, reject())
        assert result.approved is False

    def test_finance_dataset_rejected_over_currency_concern(self):
        """Finance user notices no currency column — rejects to fix source data."""
        cols = [
            make_col("amount",  "float",       "numeric"),
            make_col("account", "categorical", "numeric"),
        ]
        plan = agent.propose_merge_plan([("ledger.csv", cols)])
        result = apply_merge_decision(plan, reject())
        assert result.approved is False

    def test_healthcare_dataset_rejected_over_phi_concern(self):
        """Healthcare user spots unmasked patient identifiers — rejects."""
        cols = [
            make_col("patient_id",   "categorical", "numeric"),
            make_col("dob",          "text",        "textual"),
            make_col("diagnosis_code","categorical", "numeric"),
        ]
        plan = agent.propose_merge_plan([("ehr.csv", cols)])
        result = apply_merge_decision(plan, reject())
        assert result.approved is False
        assert result.final_columns == []


# ─────────────────────────────────────────────────────────────────────────────
# Edge cases — boundary conditions on the rejection path
# ─────────────────────────────────────────────────────────────────────────────

class TestRejectionEdgeCases:

    def test_rejection_called_multiple_times_on_same_plan(self):
        plan = make_plan()
        for _ in range(10):
            result = apply_merge_decision(plan, reject())
            assert result.approved is False

    def test_rejection_called_multiple_times_on_same_decision(self):
        plan_a = make_plan(strategy="single")
        plan_b = make_plan(strategy="union")
        decision = reject()
        r_a = apply_merge_decision(plan_a, decision)
        r_b = apply_merge_decision(plan_b, decision)
        assert r_a.approved is False
        assert r_b.approved is False

    def test_result_final_columns_is_list_not_none(self):
        result = apply_merge_decision(make_plan(), reject())
        assert result.final_columns is not None
        assert isinstance(result.final_columns, list)

    def test_result_column_profiles_is_list_not_none(self):
        result = apply_merge_decision(make_plan(), reject())
        assert result.column_profiles is not None
        assert isinstance(result.column_profiles, list)

    def test_result_effective_strategy_is_string(self):
        result = apply_merge_decision(make_plan(), reject())
        assert isinstance(result.effective_strategy, str)

    def test_result_effective_strategy_is_non_empty(self):
        result = apply_merge_decision(make_plan(), reject())
        assert len(result.effective_strategy) > 0

    def test_approved_false_is_strict_bool(self):
        result = apply_merge_decision(make_plan(), reject())
        assert result.approved is False
        assert not result.approved  # falsy check
        assert type(result.approved) is bool

    def test_rejection_with_empty_excluded_list_same_result(self):
        plan = make_plan()
        r1 = apply_merge_decision(plan, reject())
        r2 = apply_merge_decision(plan, reject(excluded_columns=[]))
        assert r1.approved == r2.approved
        assert r1.final_columns == r2.final_columns

    def test_rejection_with_empty_routing_overrides_same_result(self):
        plan = make_plan()
        r1 = apply_merge_decision(plan, reject())
        r2 = apply_merge_decision(plan, reject(column_routing_overrides={}))
        assert r1.approved == r2.approved
        assert r1.final_columns == r2.final_columns


# ═════════════════════════════════════════════════════════════════════════════
# Runner
# ═════════════════════════════════════════════════════════════════════════════

def _collect_all_test_classes():
    return [
        TestRejectionModelConstruction,
        TestRejectionCoreContract,
        TestRejectionEffectiveStrategyAudit,
        TestRejectionEffectiveJoinKeyAudit,
        TestOverridesIgnoredOnRejection,
        TestPlanNotMutatedByRejection,
        TestRejectionAcrossAllStrategies,
        TestPipelineAbortAfterRejection,
        TestReProposalAfterRejection,
        TestRejectionWithVariousPlanShapes,
        TestRealWorldRejectionScenarios,
        TestRejectionEdgeCases,
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