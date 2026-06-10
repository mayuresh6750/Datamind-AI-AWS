"""
Unit tests for  GET /datasets/{id}/cleaning-plan

Task reference : S3-14 (Sprint 3)
    "GET /datasets/{id}/cleaning-plan —
     return numbered steps with rationale + confidence"

Architecture refs:
    • HITL #2 screen consumes this endpoint (U5)
    • Confidence colour thresholds: red < 0.50, orange < 0.70, yellow < 0.90
    • CleaningStep fields: step_id, action, column, method, rationale,
                           confidence (0.0–1.0), rows_affected
    • CleaningPlan fields: steps (list), total_rows_before, total_rows_after

Run with:
    pytest  test_get_cleaning_plan.py -v
    python  test_get_cleaning_plan.py       # live results, no pytest needed

Fully independent — no real HTTP server, no DB, no LLM, no Supabase.
A minimal WSGI-style test client (TestClient) is implemented in-process
so every test is a plain function call with no network I/O.
"""

from __future__ import annotations

import json
import sys
import traceback
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional


# ─────────────────────────────────────────────────────────────────────────────
# Schema stand-ins  (mirrors app/models/schemas.py)
# ─────────────────────────────────────────────────────────────────────────────

VALID_ACTIONS  = {"deduplicate", "impute", "coerce_type", "flag_outlier"}
VALID_METHODS  = {
    "exact row deduplication",
    "median imputation", "mode imputation", "drop",
    "to_float",
    "IQR outlier flagging",
}
CONFIDENCE_RED    = 0.50   # < 0.50  → red badge
CONFIDENCE_ORANGE = 0.70   # < 0.70  → orange badge
CONFIDENCE_YELLOW = 0.90   # < 0.90  → yellow badge


@dataclass
class CleaningStep:
    step_id: int
    action: str
    column: Optional[str]
    method: str
    rationale: str
    confidence: float       # 0.0 – 1.0
    rows_affected: int


@dataclass
class CleaningPlan:
    steps: list[CleaningStep]
    total_rows_before: int
    total_rows_after: int


# ─────────────────────────────────────────────────────────────────────────────
# In-process HTTP response / request primitives
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Response:
    status_code: int
    body: Any           # already parsed from JSON
    headers: dict[str, str] = field(default_factory=dict)

    # ── helpers ──────────────────────────────────────────────────────────────
    def json(self) -> Any:
        return self.body

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300


# ─────────────────────────────────────────────────────────────────────────────
# Fake data store & repository
# ─────────────────────────────────────────────────────────────────────────────

class DatasetStore:
    """
    In-memory store that the fake API handler reads from.

    Pre-populate with dataset_id → CleaningPlan entries.
    Leave an id absent to trigger 404.
    Use _error to force a 500 on a specific dataset_id.
    """

    def __init__(self) -> None:
        self._plans: dict[str, CleaningPlan] = {}
        self._errors: set[str] = set()
        self._unauthorized: set[str] = set()  # 401
        self._forbidden: set[str] = set()     # 403
        self._pipeline_pending: set[str] = set()  # 202 – plan not ready yet

    def set_plan(self, dataset_id: str, plan: CleaningPlan) -> None:
        self._plans[dataset_id] = plan

    def set_error(self, dataset_id: str) -> None:
        self._errors.add(dataset_id)

    def set_unauthorized(self, dataset_id: str) -> None:
        self._unauthorized.add(dataset_id)

    def set_forbidden(self, dataset_id: str) -> None:
        self._forbidden.add(dataset_id)

    def set_pipeline_pending(self, dataset_id: str) -> None:
        self._pipeline_pending.add(dataset_id)

    def get_plan(self, dataset_id: str) -> Optional[CleaningPlan]:
        return self._plans.get(dataset_id)

    def is_error(self, dataset_id: str) -> bool:
        return dataset_id in self._errors

    def is_unauthorized(self, dataset_id: str) -> bool:
        return dataset_id in self._unauthorized

    def is_forbidden(self, dataset_id: str) -> bool:
        return dataset_id in self._forbidden

    def is_pending(self, dataset_id: str) -> bool:
        return dataset_id in self._pipeline_pending


# ─────────────────────────────────────────────────────────────────────────────
# Fake FastAPI-style handler for GET /datasets/{id}/cleaning-plan
# ─────────────────────────────────────────────────────────────────────────────

def _serialize_step(step: CleaningStep) -> dict:
    return {
        "step_id":      step.step_id,
        "action":       step.action,
        "column":       step.column,
        "method":       step.method,
        "rationale":    step.rationale,
        "confidence":   step.confidence,
        "rows_affected": step.rows_affected,
        # Derived display field consumed by HITL #2 UI
        "confidence_badge": _confidence_badge(step.confidence),
    }


def _confidence_badge(confidence: float) -> str:
    if confidence < CONFIDENCE_RED:
        return "red"
    if confidence < CONFIDENCE_ORANGE:
        return "orange"
    if confidence < CONFIDENCE_YELLOW:
        return "yellow"
    return "green"


def _serialize_plan(plan: CleaningPlan) -> dict:
    return {
        "steps":             [_serialize_step(s) for s in plan.steps],
        "total_rows_before": plan.total_rows_before,
        "total_rows_after":  plan.total_rows_after,
        "step_count":        len(plan.steps),
    }


def handle_get_cleaning_plan(
    dataset_id: str,
    store: DatasetStore,
    *,
    auth_token: Optional[str] = "Bearer valid-token",
) -> Response:
    """
    Simulates:  GET /datasets/{dataset_id}/cleaning-plan

    Auth layer:
        - Missing / empty token → 401
        - dataset_id in store._unauthorized → 401
        - dataset_id in store._forbidden    → 403
    Business layer:
        - dataset_id not in store           → 404
        - dataset_id in store._errors       → 500
        - dataset_id in store._pipeline_pending → 202 (still generating)
        - happy path                        → 200 + CleaningPlan JSON
    """
    # ── 401: missing auth ─────────────────────────────────────────────────────
    if not auth_token or not auth_token.strip():
        return Response(
            status_code=401,
            body={"detail": "Authentication required"},
            headers={"WWW-Authenticate": "Bearer"},
        )

    # ── 401: token-level rejection ────────────────────────────────────────────
    if store.is_unauthorized(dataset_id):
        return Response(
            status_code=401,
            body={"detail": "Invalid or expired token"},
            headers={"WWW-Authenticate": "Bearer"},
        )

    # ── 403: insufficient permissions ─────────────────────────────────────────
    if store.is_forbidden(dataset_id):
        return Response(
            status_code=403,
            body={"detail": "You do not have permission to access this dataset"},
        )

    # ── 500: upstream error ───────────────────────────────────────────────────
    if store.is_error(dataset_id):
        return Response(
            status_code=500,
            body={"detail": "Internal server error while retrieving cleaning plan"},
        )

    # ── 404: dataset not found ────────────────────────────────────────────────
    plan = store.get_plan(dataset_id)
    if plan is None:
        return Response(
            status_code=404,
            body={"detail": f"Dataset '{dataset_id}' not found"},
        )

    # ── 202: cleaning plan not yet generated ─────────────────────────────────
    if store.is_pending(dataset_id):
        return Response(
            status_code=202,
            body={
                "detail": "Cleaning plan is still being generated",
                "status": "pending",
            },
        )

    # ── 200: happy path ───────────────────────────────────────────────────────
    return Response(
        status_code=200,
        body=_serialize_plan(plan),
        headers={"Content-Type": "application/json"},
    )


# ─────────────────────────────────────────────────────────────────────────────
# Test helpers & fixtures
# ─────────────────────────────────────────────────────────────────────────────

def new_id() -> str:
    return str(uuid.uuid4())


def make_step(
    step_id: int = 1,
    action: str = "deduplicate",
    column: Optional[str] = None,
    method: str = "exact row deduplication",
    rationale: str = "Remove exact duplicates.",
    confidence: float = 0.95,
    rows_affected: int = 5,
) -> CleaningStep:
    return CleaningStep(
        step_id=step_id, action=action, column=column,
        method=method, rationale=rationale,
        confidence=confidence, rows_affected=rows_affected,
    )


def make_plan(
    steps: Optional[list[CleaningStep]] = None,
    total_rows_before: int = 1000,
    total_rows_after: int = 995,
) -> CleaningPlan:
    return CleaningPlan(
        steps=steps if steps is not None else [make_step()],
        total_rows_before=total_rows_before,
        total_rows_after=total_rows_after,
    )


def get(
    dataset_id: str,
    store: DatasetStore,
    token: Optional[str] = "Bearer valid-token",
) -> Response:
    return handle_get_cleaning_plan(dataset_id, store, auth_token=token)


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
        print("  GET /datasets/{id}/cleaning-plan — test results")
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
# 200 — happy path: status code and content-type
# ─────────────────────────────────────────────────────────────────────────────

class TestHappyPathStatusAndHeaders:

    def test_returns_200_for_existing_dataset(self):
        store = DatasetStore()
        did = new_id()
        store.set_plan(did, make_plan())
        assert get(did, store).status_code == 200

    def test_response_ok_property_true_on_200(self):
        store = DatasetStore()
        did = new_id()
        store.set_plan(did, make_plan())
        assert get(did, store).ok is True

    def test_content_type_is_json(self):
        store = DatasetStore()
        did = new_id()
        store.set_plan(did, make_plan())
        resp = get(did, store)
        assert resp.headers.get("Content-Type") == "application/json"

    def test_body_is_dict(self):
        store = DatasetStore()
        did = new_id()
        store.set_plan(did, make_plan())
        body = get(did, store).json()
        assert isinstance(body, dict)


# ─────────────────────────────────────────────────────────────────────────────
# 200 — response shape: top-level fields
# ─────────────────────────────────────────────────────────────────────────────

class TestResponseShape:

    REQUIRED_KEYS = {"steps", "total_rows_before", "total_rows_after", "step_count"}

    def _body(self) -> dict:
        store = DatasetStore()
        did = new_id()
        store.set_plan(did, make_plan())
        return get(did, store).json()

    def test_response_has_steps_key(self):
        assert "steps" in self._body()

    def test_response_has_total_rows_before(self):
        assert "total_rows_before" in self._body()

    def test_response_has_total_rows_after(self):
        assert "total_rows_after" in self._body()

    def test_response_has_step_count(self):
        assert "step_count" in self._body()

    def test_steps_is_list(self):
        assert isinstance(self._body()["steps"], list)

    def test_total_rows_before_is_int(self):
        assert isinstance(self._body()["total_rows_before"], int)

    def test_total_rows_after_is_int(self):
        assert isinstance(self._body()["total_rows_after"], int)

    def test_step_count_is_int(self):
        assert isinstance(self._body()["step_count"], int)

    def test_step_count_matches_steps_length(self):
        body = self._body()
        assert body["step_count"] == len(body["steps"])

    def test_all_required_keys_present(self):
        body = self._body()
        assert self.REQUIRED_KEYS.issubset(body.keys())


# ─────────────────────────────────────────────────────────────────────────────
# 200 — CleaningStep fields in each step object
# ─────────────────────────────────────────────────────────────────────────────

class TestStepShape:

    REQUIRED_STEP_KEYS = {
        "step_id", "action", "column", "method",
        "rationale", "confidence", "rows_affected", "confidence_badge",
    }

    def _steps(self, n: int = 1) -> list[dict]:
        store = DatasetStore()
        did = new_id()
        steps = [
            make_step(i + 1, "impute", f"col_{i}", "median imputation",
                      f"rationale {i}", 0.8, i * 10)
            for i in range(n)
        ]
        store.set_plan(did, make_plan(steps=steps))
        return get(did, store).json()["steps"]

    def test_step_has_all_required_keys(self):
        step = self._steps(1)[0]
        assert self.REQUIRED_STEP_KEYS.issubset(step.keys())

    def test_step_id_is_int(self):
        assert isinstance(self._steps(1)[0]["step_id"], int)

    def test_step_action_is_str(self):
        assert isinstance(self._steps(1)[0]["action"], str)

    def test_step_method_is_str(self):
        assert isinstance(self._steps(1)[0]["method"], str)

    def test_step_rationale_is_str(self):
        assert isinstance(self._steps(1)[0]["rationale"], str)

    def test_step_rationale_is_non_empty(self):
        assert len(self._steps(1)[0]["rationale"].strip()) > 0

    def test_step_confidence_is_float(self):
        assert isinstance(self._steps(1)[0]["confidence"], float)

    def test_step_rows_affected_is_int(self):
        assert isinstance(self._steps(1)[0]["rows_affected"], int)

    def test_step_confidence_badge_is_str(self):
        assert isinstance(self._steps(1)[0]["confidence_badge"], str)

    def test_step_column_can_be_none(self):
        store = DatasetStore()
        did = new_id()
        store.set_plan(did, make_plan(steps=[make_step(1, "deduplicate", None)]))
        step = get(did, store).json()["steps"][0]
        assert step["column"] is None

    def test_step_column_can_be_string(self):
        store = DatasetStore()
        did = new_id()
        store.set_plan(did, make_plan(steps=[make_step(1, "impute", "revenue")]))
        step = get(did, store).json()["steps"][0]
        assert step["column"] == "revenue"


# ─────────────────────────────────────────────────────────────────────────────
# 200 — CleaningStep field VALUES
# ─────────────────────────────────────────────────────────────────────────────

class TestStepValues:

    def test_step_id_matches_source(self):
        store = DatasetStore()
        did = new_id()
        store.set_plan(did, make_plan(steps=[make_step(step_id=7)]))
        assert get(did, store).json()["steps"][0]["step_id"] == 7

    def test_action_deduplicate_preserved(self):
        store = DatasetStore()
        did = new_id()
        store.set_plan(did, make_plan(steps=[make_step(action="deduplicate")]))
        assert get(did, store).json()["steps"][0]["action"] == "deduplicate"

    def test_action_impute_preserved(self):
        store = DatasetStore()
        did = new_id()
        store.set_plan(did, make_plan(steps=[make_step(action="impute", column="revenue")]))
        assert get(did, store).json()["steps"][0]["action"] == "impute"

    def test_action_coerce_type_preserved(self):
        store = DatasetStore()
        did = new_id()
        store.set_plan(did, make_plan(steps=[make_step(action="coerce_type", column="price")]))
        assert get(did, store).json()["steps"][0]["action"] == "coerce_type"

    def test_action_flag_outlier_preserved(self):
        store = DatasetStore()
        did = new_id()
        store.set_plan(did, make_plan(steps=[make_step(action="flag_outlier", column="score")]))
        assert get(did, store).json()["steps"][0]["action"] == "flag_outlier"

    def test_all_valid_actions_accepted(self):
        for action in VALID_ACTIONS:
            store = DatasetStore()
            did = new_id()
            col = "x" if action != "deduplicate" else None
            store.set_plan(did, make_plan(steps=[make_step(action=action, column=col)]))
            step = get(did, store).json()["steps"][0]
            assert step["action"] == action

    def test_confidence_value_exact(self):
        store = DatasetStore()
        did = new_id()
        store.set_plan(did, make_plan(steps=[make_step(confidence=0.732)]))
        assert abs(get(did, store).json()["steps"][0]["confidence"] - 0.732) < 1e-9

    def test_rows_affected_value_exact(self):
        store = DatasetStore()
        did = new_id()
        store.set_plan(did, make_plan(steps=[make_step(rows_affected=142)]))
        assert get(did, store).json()["steps"][0]["rows_affected"] == 142

    def test_rationale_preserved_verbatim(self):
        rationale = "Column has 8% nulls; median imputation preserves distribution."
        store = DatasetStore()
        did = new_id()
        store.set_plan(did, make_plan(steps=[make_step(rationale=rationale)]))
        assert get(did, store).json()["steps"][0]["rationale"] == rationale

    def test_method_preserved_verbatim(self):
        store = DatasetStore()
        did = new_id()
        store.set_plan(did, make_plan(steps=[make_step(method="median imputation")]))
        assert get(did, store).json()["steps"][0]["method"] == "median imputation"

    def test_total_rows_before_exact(self):
        store = DatasetStore()
        did = new_id()
        store.set_plan(did, make_plan(total_rows_before=5000))
        assert get(did, store).json()["total_rows_before"] == 5000

    def test_total_rows_after_exact(self):
        store = DatasetStore()
        did = new_id()
        store.set_plan(did, make_plan(total_rows_after=4900))
        assert get(did, store).json()["total_rows_after"] == 4900


# ─────────────────────────────────────────────────────────────────────────────
# 200 — Confidence badge thresholds (HITL #2 UI colour coding)
# ─────────────────────────────────────────────────────────────────────────────

class TestConfidenceBadges:
    """
    From architecture.md:
        red    < 0.50
        orange < 0.70
        yellow < 0.90
        green  ≥ 0.90
    Low-confidence steps (< 0.50) are unchecked by default in the UI.
    """

    def _badge(self, confidence: float) -> str:
        store = DatasetStore()
        did = new_id()
        store.set_plan(did, make_plan(steps=[make_step(confidence=confidence)]))
        return get(did, store).json()["steps"][0]["confidence_badge"]

    # ── red ───────────────────────────────────────────────────────────────────
    def test_confidence_0_is_red(self):
        assert self._badge(0.0) == "red"

    def test_confidence_010_is_red(self):
        assert self._badge(0.10) == "red"

    def test_confidence_049_is_red(self):
        assert self._badge(0.49) == "red"

    def test_confidence_just_below_050_is_red(self):
        assert self._badge(0.4999) == "red"

    # ── orange ────────────────────────────────────────────────────────────────
    def test_confidence_050_is_orange(self):
        assert self._badge(0.50) == "orange"

    def test_confidence_060_is_orange(self):
        assert self._badge(0.60) == "orange"

    def test_confidence_just_below_070_is_orange(self):
        assert self._badge(0.6999) == "orange"

    def test_confidence_069_is_orange(self):
        assert self._badge(0.69) == "orange"

    # ── yellow ────────────────────────────────────────────────────────────────
    def test_confidence_070_is_yellow(self):
        assert self._badge(0.70) == "yellow"

    def test_confidence_080_is_yellow(self):
        assert self._badge(0.80) == "yellow"

    def test_confidence_just_below_090_is_yellow(self):
        assert self._badge(0.8999) == "yellow"

    def test_confidence_089_is_yellow(self):
        assert self._badge(0.89) == "yellow"

    # ── green ─────────────────────────────────────────────────────────────────
    def test_confidence_090_is_green(self):
        assert self._badge(0.90) == "green"

    def test_confidence_095_is_green(self):
        assert self._badge(0.95) == "green"

    def test_confidence_100_is_green(self):
        assert self._badge(1.0) == "green"

    # ── badge is always one of four valid values ──────────────────────────────
    def test_badge_is_valid_colour(self):
        valid = {"red", "orange", "yellow", "green"}
        for conf in [0.0, 0.25, 0.49, 0.50, 0.65, 0.70, 0.85, 0.90, 1.0]:
            assert self._badge(conf) in valid, f"Bad badge for confidence={conf}"


# ─────────────────────────────────────────────────────────────────────────────
# 200 — step ordering and numbering
# ─────────────────────────────────────────────────────────────────────────────

class TestStepOrdering:

    def test_steps_returned_in_source_order(self):
        store = DatasetStore()
        did = new_id()
        steps = [make_step(i + 1) for i in range(5)]
        store.set_plan(did, make_plan(steps=steps))
        ids = [s["step_id"] for s in get(did, store).json()["steps"]]
        assert ids == [1, 2, 3, 4, 5]

    def test_step_ids_are_sequential_from_one(self):
        store = DatasetStore()
        did = new_id()
        steps = [make_step(i + 1) for i in range(4)]
        store.set_plan(did, make_plan(steps=steps))
        ids = [s["step_id"] for s in get(did, store).json()["steps"]]
        assert ids == list(range(1, 5))

    def test_step_count_matches_actual_steps(self):
        store = DatasetStore()
        did = new_id()
        n = 7
        steps = [make_step(i + 1) for i in range(n)]
        store.set_plan(did, make_plan(steps=steps))
        body = get(did, store).json()
        assert body["step_count"] == n
        assert len(body["steps"]) == n

    def test_single_step_plan(self):
        store = DatasetStore()
        did = new_id()
        store.set_plan(did, make_plan(steps=[make_step(1)]))
        body = get(did, store).json()
        assert body["step_count"] == 1
        assert len(body["steps"]) == 1

    def test_zero_step_plan(self):
        store = DatasetStore()
        did = new_id()
        store.set_plan(did, make_plan(steps=[]))
        body = get(did, store).json()
        assert body["step_count"] == 0
        assert body["steps"] == []


# ─────────────────────────────────────────────────────────────────────────────
# 200 — multi-step plans with mixed actions and confidence values
# ─────────────────────────────────────────────────────────────────────────────

class TestMultiStepPlans:

    def test_full_pipeline_plan_four_steps(self):
        """Dedup + impute + coerce + flag — canonical four-step plan."""
        store = DatasetStore()
        did = new_id()
        steps = [
            make_step(1, "deduplicate",  None,        "exact row deduplication", "Duplicates found.", 0.95, 12),
            make_step(2, "impute",       "revenue",   "median imputation",       "8% nulls.",         0.85, 80),
            make_step(3, "coerce_type",  "price_str", "to_float",                "String numbers.",   0.70, 920),
            make_step(4, "flag_outlier", "revenue",   "IQR outlier flagging",    "Outlier check.",    0.60, 0),
        ]
        store.set_plan(did, make_plan(steps=steps, total_rows_before=1000, total_rows_after=988))
        body = get(did, store).json()
        assert body["step_count"] == 4
        assert body["steps"][0]["action"] == "deduplicate"
        assert body["steps"][1]["column"] == "revenue"
        assert body["steps"][2]["method"] == "to_float"
        assert body["steps"][3]["confidence_badge"] == "orange"

    def test_steps_with_mixed_confidence_badges(self):
        store = DatasetStore()
        did = new_id()
        steps = [
            make_step(1, confidence=0.30),   # red
            make_step(2, confidence=0.60),   # orange
            make_step(3, confidence=0.75),   # yellow
            make_step(4, confidence=0.95),   # green
        ]
        store.set_plan(did, make_plan(steps=steps))
        badges = [s["confidence_badge"] for s in get(did, store).json()["steps"]]
        assert badges == ["red", "orange", "yellow", "green"]

    def test_all_steps_have_rationale(self):
        store = DatasetStore()
        did = new_id()
        steps = [make_step(i + 1, rationale=f"reason {i}") for i in range(6)]
        store.set_plan(did, make_plan(steps=steps))
        rationales = [s["rationale"] for s in get(did, store).json()["steps"]]
        assert all(r.startswith("reason") for r in rationales)

    def test_step_ids_unique_across_multi_step_plan(self):
        store = DatasetStore()
        did = new_id()
        steps = [make_step(i + 1) for i in range(10)]
        store.set_plan(did, make_plan(steps=steps))
        ids = [s["step_id"] for s in get(did, store).json()["steps"]]
        assert len(ids) == len(set(ids))

    def test_different_columns_per_step(self):
        store = DatasetStore()
        did = new_id()
        steps = [
            make_step(1, "impute",       "revenue",  "median imputation"),
            make_step(2, "impute",       "quantity", "mode imputation"),
            make_step(3, "flag_outlier", "price",    "IQR outlier flagging"),
        ]
        store.set_plan(did, make_plan(steps=steps))
        cols = [s["column"] for s in get(did, store).json()["steps"]]
        assert cols == ["revenue", "quantity", "price"]


# ─────────────────────────────────────────────────────────────────────────────
# 404 — dataset not found
# ─────────────────────────────────────────────────────────────────────────────

class TestNotFound:

    def test_unknown_id_returns_404(self):
        store = DatasetStore()
        assert get(new_id(), store).status_code == 404

    def test_404_body_has_detail_key(self):
        store = DatasetStore()
        body = get(new_id(), store).json()
        assert "detail" in body

    def test_404_detail_mentions_dataset_id(self):
        store = DatasetStore()
        did = new_id()
        body = get(did, store).json()
        assert did in body["detail"]

    def test_404_ok_property_is_false(self):
        store = DatasetStore()
        assert get(new_id(), store).ok is False

    def test_different_unknown_ids_all_return_404(self):
        store = DatasetStore()
        for _ in range(5):
            assert get(new_id(), store).status_code == 404

    def test_known_id_does_not_return_404(self):
        store = DatasetStore()
        did = new_id()
        store.set_plan(did, make_plan())
        assert get(did, store).status_code != 404

    def test_wrong_id_for_existing_dataset_returns_404(self):
        store = DatasetStore()
        real_id = new_id()
        store.set_plan(real_id, make_plan())
        assert get(new_id(), store).status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# 401 — authentication
# ─────────────────────────────────────────────────────────────────────────────

class TestAuthentication:

    def test_no_token_returns_401(self):
        store = DatasetStore()
        did = new_id()
        store.set_plan(did, make_plan())
        assert get(did, store, token=None).status_code == 401

    def test_empty_token_returns_401(self):
        store = DatasetStore()
        did = new_id()
        store.set_plan(did, make_plan())
        assert get(did, store, token="").status_code == 401

    def test_whitespace_token_returns_401(self):
        store = DatasetStore()
        did = new_id()
        store.set_plan(did, make_plan())
        assert get(did, store, token="   ").status_code == 401

    def test_401_has_www_authenticate_header(self):
        store = DatasetStore()
        did = new_id()
        store.set_plan(did, make_plan())
        resp = get(did, store, token=None)
        assert "WWW-Authenticate" in resp.headers

    def test_401_www_authenticate_is_bearer(self):
        store = DatasetStore()
        did = new_id()
        store.set_plan(did, make_plan())
        resp = get(did, store, token=None)
        assert resp.headers["WWW-Authenticate"] == "Bearer"

    def test_401_body_has_detail(self):
        store = DatasetStore()
        did = new_id()
        store.set_plan(did, make_plan())
        assert "detail" in get(did, store, token=None).json()

    def test_invalid_token_for_dataset_returns_401(self):
        store = DatasetStore()
        did = new_id()
        store.set_plan(did, make_plan())
        store.set_unauthorized(did)
        assert get(did, store).status_code == 401

    def test_valid_token_passes_auth(self):
        store = DatasetStore()
        did = new_id()
        store.set_plan(did, make_plan())
        assert get(did, store, token="Bearer valid").status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# 403 — authorisation (wrong user / tenant isolation)
# ─────────────────────────────────────────────────────────────────────────────

class TestAuthorisation:

    def test_forbidden_dataset_returns_403(self):
        store = DatasetStore()
        did = new_id()
        store.set_plan(did, make_plan())
        store.set_forbidden(did)
        assert get(did, store).status_code == 403

    def test_403_body_has_detail(self):
        store = DatasetStore()
        did = new_id()
        store.set_plan(did, make_plan())
        store.set_forbidden(did)
        assert "detail" in get(did, store).json()

    def test_403_ok_is_false(self):
        store = DatasetStore()
        did = new_id()
        store.set_plan(did, make_plan())
        store.set_forbidden(did)
        assert get(did, store).ok is False

    def test_403_not_returned_for_own_dataset(self):
        store = DatasetStore()
        did = new_id()
        store.set_plan(did, make_plan())
        assert get(did, store).status_code == 200

    def test_different_dataset_id_not_forbidden(self):
        """Forbidden flag on one id must not affect another."""
        store = DatasetStore()
        bad = new_id()
        good = new_id()
        store.set_plan(bad, make_plan())
        store.set_plan(good, make_plan())
        store.set_forbidden(bad)
        assert get(good, store).status_code == 200
        assert get(bad, store).status_code == 403


# ─────────────────────────────────────────────────────────────────────────────
# 202 — cleaning plan still being generated (pipeline pending)
# ─────────────────────────────────────────────────────────────────────────────

class TestPlanPending:

    def test_pending_dataset_returns_202(self):
        store = DatasetStore()
        did = new_id()
        store.set_plan(did, make_plan())
        store.set_pipeline_pending(did)
        assert get(did, store).status_code == 202

    def test_202_body_has_detail(self):
        store = DatasetStore()
        did = new_id()
        store.set_plan(did, make_plan())
        store.set_pipeline_pending(did)
        assert "detail" in get(did, store).json()

    def test_202_body_has_status_pending(self):
        store = DatasetStore()
        did = new_id()
        store.set_plan(did, make_plan())
        store.set_pipeline_pending(did)
        assert get(did, store).json().get("status") == "pending"

    def test_non_pending_dataset_returns_200_not_202(self):
        store = DatasetStore()
        did = new_id()
        store.set_plan(did, make_plan())
        assert get(did, store).status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# 500 — internal server error
# ─────────────────────────────────────────────────────────────────────────────

class TestServerError:

    def test_error_dataset_returns_500(self):
        store = DatasetStore()
        did = new_id()
        store.set_error(did)
        assert get(did, store).status_code == 500

    def test_500_body_has_detail(self):
        store = DatasetStore()
        did = new_id()
        store.set_error(did)
        assert "detail" in get(did, store).json()

    def test_500_ok_is_false(self):
        store = DatasetStore()
        did = new_id()
        store.set_error(did)
        assert get(did, store).ok is False

    def test_error_on_one_id_does_not_affect_another(self):
        store = DatasetStore()
        bad = new_id()
        good = new_id()
        store.set_error(bad)
        store.set_plan(good, make_plan())
        assert get(bad, store).status_code == 500
        assert get(good, store).status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# Domain-specific cleaning plans
# ─────────────────────────────────────────────────────────────────────────────

class TestDomainSpecificPlans:

    def test_finance_plan_revenue_imputation(self):
        store = DatasetStore()
        did = new_id()
        steps = [
            make_step(1, "deduplicate",  None,      "exact row deduplication", "Exact duplicates in export.", 0.95, 8),
            make_step(2, "impute",       "revenue", "median imputation",       "Revenue has 6% nulls.",       0.85, 60),
            make_step(3, "flag_outlier", "arr",     "IQR outlier flagging",    "Flag ARR outliers.",          0.70, 0),
        ]
        store.set_plan(did, make_plan(steps=steps, total_rows_before=1000, total_rows_after=992))
        body = get(did, store).json()
        assert body["step_count"] == 3
        assert body["steps"][1]["column"] == "revenue"
        assert body["steps"][1]["method"] == "median imputation"

    def test_healthcare_plan_readmission_flag(self):
        store = DatasetStore()
        did = new_id()
        steps = [
            make_step(1, "deduplicate",  None,             "exact row deduplication", "Dups in EHR export.",  0.95, 3),
            make_step(2, "impute",       "length_of_stay", "median imputation",       "LOS has 4% nulls.",    0.80, 40),
            make_step(3, "flag_outlier", "length_of_stay", "IQR outlier flagging",    "Flag extreme LOS.",    0.65, 0),
        ]
        store.set_plan(did, make_plan(steps=steps))
        body = get(did, store).json()
        impute = next(s for s in body["steps"] if s["action"] == "impute")
        assert impute["column"] == "length_of_stay"

    def test_retail_plan_sku_margin_coercion(self):
        store = DatasetStore()
        did = new_id()
        steps = [
            make_step(1, "coerce_type",  "price_str", "to_float", "Prices stored as strings.", 0.70, 500),
            make_step(2, "flag_outlier", "margin",    "IQR outlier flagging", "Outlier margins.", 0.60, 0),
        ]
        store.set_plan(did, make_plan(steps=steps))
        body = get(did, store).json()
        assert body["steps"][0]["action"] == "coerce_type"
        assert body["steps"][0]["confidence_badge"] == "yellow"

    def test_low_confidence_steps_have_red_badge(self):
        """Red-badge steps are unchecked by default in the HITL #2 UI."""
        store = DatasetStore()
        did = new_id()
        steps = [make_step(1, confidence=0.30), make_step(2, confidence=0.45)]
        store.set_plan(did, make_plan(steps=steps))
        badges = [s["confidence_badge"] for s in get(did, store).json()["steps"]]
        assert all(b == "red" for b in badges)

    def test_marketing_plan_ctr_imputation(self):
        store = DatasetStore()
        did = new_id()
        steps = [
            make_step(1, "impute", "ctr",  "median imputation", "CTR missing for 3% rows.", 0.82, 30),
            make_step(2, "impute", "cpa",  "median imputation", "CPA missing for 2% rows.", 0.78, 20),
        ]
        store.set_plan(did, make_plan(steps=steps))
        body = get(did, store).json()
        assert body["step_count"] == 2
        assert all(s["action"] == "impute" for s in body["steps"])


# ─────────────────────────────────────────────────────────────────────────────
# Edge cases & robustness
# ─────────────────────────────────────────────────────────────────────────────

class TestEdgeCases:

    def test_empty_plan_returns_empty_steps_list(self):
        store = DatasetStore()
        did = new_id()
        store.set_plan(did, make_plan(steps=[]))
        body = get(did, store).json()
        assert body["steps"] == [] and body["step_count"] == 0

    def test_plan_with_20_steps_all_returned(self):
        store = DatasetStore()
        did = new_id()
        steps = [make_step(i + 1) for i in range(20)]
        store.set_plan(did, make_plan(steps=steps))
        assert len(get(did, store).json()["steps"]) == 20

    def test_dataset_id_with_hyphens(self):
        """Standard UUID format must be handled correctly."""
        store = DatasetStore()
        did = str(uuid.uuid4())   # e.g. "550e8400-e29b-41d4-a716-446655440000"
        store.set_plan(did, make_plan())
        assert get(did, store).status_code == 200

    def test_multiple_datasets_independent(self):
        store = DatasetStore()
        id_a, id_b = new_id(), new_id()
        plan_a = make_plan(steps=[make_step(1, confidence=0.9)], total_rows_before=100)
        plan_b = make_plan(steps=[make_step(1, confidence=0.5)], total_rows_before=200)
        store.set_plan(id_a, plan_a)
        store.set_plan(id_b, plan_b)
        body_a = get(id_a, store).json()
        body_b = get(id_b, store).json()
        assert body_a["total_rows_before"] == 100
        assert body_b["total_rows_before"] == 200
        assert body_a["steps"][0]["confidence_badge"] == "green"
        assert body_b["steps"][0]["confidence_badge"] == "orange"

    def test_total_rows_after_can_equal_before(self):
        """If no dedup step removes rows, before == after is valid."""
        store = DatasetStore()
        did = new_id()
        store.set_plan(did, make_plan(total_rows_before=500, total_rows_after=500))
        body = get(did, store).json()
        assert body["total_rows_before"] == body["total_rows_after"]

    def test_single_character_rationale_still_returned(self):
        store = DatasetStore()
        did = new_id()
        store.set_plan(did, make_plan(steps=[make_step(rationale="x")]))
        assert get(did, store).json()["steps"][0]["rationale"] == "x"

    def test_rows_affected_zero_is_valid(self):
        store = DatasetStore()
        did = new_id()
        store.set_plan(did, make_plan(steps=[make_step(rows_affected=0)]))
        assert get(did, store).json()["steps"][0]["rows_affected"] == 0

    def test_same_dataset_id_same_plan_on_repeated_calls(self):
        store = DatasetStore()
        did = new_id()
        store.set_plan(did, make_plan())
        r1 = get(did, store).json()
        r2 = get(did, store).json()
        assert r1 == r2


# ═════════════════════════════════════════════════════════════════════════════
# Runner
# ═════════════════════════════════════════════════════════════════════════════

def _collect_all_test_classes():
    return [
        TestHappyPathStatusAndHeaders,
        TestResponseShape,
        TestStepShape,
        TestStepValues,
        TestConfidenceBadges,
        TestStepOrdering,
        TestMultiStepPlans,
        TestNotFound,
        TestAuthentication,
        TestAuthorisation,
        TestPlanPending,
        TestServerError,
        TestDomainSpecificPlans,
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