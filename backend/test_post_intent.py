"""
Unit tests for  POST /datasets/{id}/intent

Task reference : S4-09 (Sprint 4)
    "POST /datasets/{id}/intent —
     submit intent text, return restated interpretation for HITL #3"

Architecture refs:
    • HITL #3 — Intent Capture (U6 screen)
    • Intent Agent parses free-text goal into a structured AnalysisSpec
    • Returns restatement for user confirmation / refinement
    • AnalysisSpec fields: dimensions, measures, suggested_chart_types,
                           restatement, confidence (0.0–1.0), filters, time_range
    • Domains: finance | healthcare | retail | marketing | operations | other

Request body:
    {
        "question":  str,          # user's free-text intent
        "domain":    str,          # active domain for the dataset
        "confirmed": bool          # True = user confirmed the restatement (HITL #3)
    }

Response (200):
    {
        "dataset_id":    str,
        "restatement":   str,      # agent's rephrased version of the question
        "analysis_spec": {         # structured AnalysisSpec
            "dimensions":            list[str],
            "measures":              list[str],
            "suggested_chart_types": list[str],
            "restatement":           str,
            "confidence":            float,
            "filters":               list | null,
            "time_range":            dict | null,
        },
        "confidence":    float,
        "hitl_status":   str,      # "pending_confirmation" | "confirmed"
    }

Run with:
    pytest  test_post_intent.py -v
    python  test_post_intent.py       # live results, no pytest needed

Fully independent — no real HTTP server, no LLM, no DB, no Supabase.
All external dependencies replaced by in-process stubs.
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

VALID_CHART_TYPES = {"line", "bar", "table", "scatter", "pie"}
VALID_DOMAINS     = {"finance", "healthcare", "retail", "marketing", "operations", "other"}
VALID_HITL_STATUS = {"pending_confirmation", "confirmed"}


@dataclass
class AnalysisSpec:
    dimensions: list[str]
    measures: list[str]
    suggested_chart_types: list[str]
    restatement: str
    confidence: float
    filters: Optional[list] = None
    time_range: Optional[dict] = None


@dataclass
class IntentRequest:
    """Request body for POST /datasets/{id}/intent."""
    question: str
    domain: str
    confirmed: bool = False          # True = user confirmed the restatement


# ─────────────────────────────────────────────────────────────────────────────
# In-process HTTP response
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Response:
    status_code: int
    body: Any
    headers: dict[str, str] = field(default_factory=dict)

    def json(self) -> Any:
        return self.body

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300


# ─────────────────────────────────────────────────────────────────────────────
# Dataset store and mock Intent Agent
# ─────────────────────────────────────────────────────────────────────────────

class MockIntentAgent:
    """
    Controls exactly what AnalysisSpec the handler returns.
    Records every (question, domain) pair it was called with.
    Can be set to raise to simulate agent failure.
    """

    def __init__(self, spec: Optional[AnalysisSpec] = None) -> None:
        self.spec_to_return = spec or _default_spec()
        self.calls: list[dict] = []          # [{question, domain}, ...]
        self.raise_on_call: Optional[Exception] = None

    def parse(self, question: str, domain: str) -> AnalysisSpec:
        self.calls.append({"question": question, "domain": domain})
        if self.raise_on_call:
            raise self.raise_on_call
        return self.spec_to_return

    @property
    def call_count(self) -> int:
        return len(self.calls)


class DatasetStore:
    """
    In-memory dataset registry.
    Controls 404 / 401 / 403 / 500 / 409 (pipeline not ready) responses.
    """

    def __init__(self) -> None:
        self._datasets: set[str] = set()
        self._unauthorized: set[str] = set()
        self._forbidden: set[str] = set()
        self._errors: set[str] = set()
        self._pipeline_not_ready: set[str] = set()   # 409 — cleaning not done yet

    def register(self, dataset_id: str) -> None:
        self._datasets.add(dataset_id)

    def exists(self, did: str) -> bool:
        return did in self._datasets

    def set_unauthorized(self, did: str) -> None:
        self._unauthorized.add(did)

    def set_forbidden(self, did: str) -> None:
        self._forbidden.add(did)

    def set_error(self, did: str) -> None:
        self._errors.add(did)

    def set_pipeline_not_ready(self, did: str) -> None:
        self._pipeline_not_ready.add(did)

    def is_unauthorized(self, did: str) -> bool:
        return did in self._unauthorized

    def is_forbidden(self, did: str) -> bool:
        return did in self._forbidden

    def is_error(self, did: str) -> bool:
        return did in self._errors

    def is_pipeline_not_ready(self, did: str) -> bool:
        return did in self._pipeline_not_ready


# ─────────────────────────────────────────────────────────────────────────────
# Fake FastAPI handler for POST /datasets/{id}/intent
# ─────────────────────────────────────────────────────────────────────────────

def _spec_to_dict(spec: AnalysisSpec) -> dict:
    return {
        "dimensions":            spec.dimensions,
        "measures":              spec.measures,
        "suggested_chart_types": spec.suggested_chart_types,
        "restatement":           spec.restatement,
        "confidence":            spec.confidence,
        "filters":               spec.filters,
        "time_range":            spec.time_range,
    }


def handle_post_intent(
    dataset_id: str,
    request: IntentRequest,
    store: DatasetStore,
    intent_agent: MockIntentAgent,
    *,
    auth_token: Optional[str] = "Bearer valid-token",
) -> Response:
    """
    Simulates:  POST /datasets/{dataset_id}/intent

    Auth layer:
        missing / empty token         → 401
        store.is_unauthorized         → 401
        store.is_forbidden            → 403

    Validation layer:
        empty question string         → 422 (unprocessable entity)
        unknown domain                → 422
        dataset not in store          → 404
        pipeline not ready (cleaning
          not yet complete)           → 409 Conflict

    Business layer:
        store.is_error                → 500
        happy path                    → 200
    """

    # ── 401: missing token ────────────────────────────────────────────────────
    if not auth_token or not auth_token.strip():
        return Response(
            status_code=401,
            body={"detail": "Authentication required"},
            headers={"WWW-Authenticate": "Bearer"},
        )

    # ── 401: invalid token for dataset ────────────────────────────────────────
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

    # ── 422: empty question ───────────────────────────────────────────────────
    if not request.question or not request.question.strip():
        return Response(
            status_code=422,
            body={"detail": "question must not be empty"},
        )

    # ── 422: invalid domain ───────────────────────────────────────────────────
    if request.domain not in VALID_DOMAINS:
        return Response(
            status_code=422,
            body={"detail": f"domain '{request.domain}' is not valid. "
                            f"Must be one of: {sorted(VALID_DOMAINS)}"},
        )

    # ── 404: dataset not found ────────────────────────────────────────────────
    if not store.exists(dataset_id):
        return Response(
            status_code=404,
            body={"detail": f"Dataset '{dataset_id}' not found"},
        )

    # ── 409: pipeline not ready (cleaning incomplete) ─────────────────────────
    if store.is_pipeline_not_ready(dataset_id):
        return Response(
            status_code=409,
            body={
                "detail": "Cleaning pipeline has not completed for this dataset",
                "status": "pipeline_not_ready",
            },
        )

    # ── 500: upstream error ───────────────────────────────────────────────────
    if store.is_error(dataset_id):
        return Response(
            status_code=500,
            body={"detail": "Internal server error while parsing intent"},
        )

    # ── 200: happy path ───────────────────────────────────────────────────────
    try:
        spec = intent_agent.parse(request.question, request.domain)
    except Exception as exc:
        return Response(
            status_code=500,
            body={"detail": f"Intent agent failed: {exc}"},
        )

    hitl_status = "confirmed" if request.confirmed else "pending_confirmation"

    return Response(
        status_code=200,
        body={
            "dataset_id":    dataset_id,
            "restatement":   spec.restatement,
            "analysis_spec": _spec_to_dict(spec),
            "confidence":    spec.confidence,
            "hitl_status":   hitl_status,
        },
        headers={"Content-Type": "application/json"},
    )


# ─────────────────────────────────────────────────────────────────────────────
# Helpers & fixtures
# ─────────────────────────────────────────────────────────────────────────────

def new_id() -> str:
    return str(uuid.uuid4())


def _default_spec(**overrides) -> AnalysisSpec:
    base = dict(
        dimensions=["region"],
        measures=["revenue"],
        suggested_chart_types=["bar"],
        restatement="Show total revenue grouped by region",
        confidence=0.92,
        filters=None,
        time_range=None,
    )
    base.update(overrides)
    return AnalysisSpec(**base)


def make_env(
    spec: Optional[AnalysisSpec] = None,
    register: bool = True,
) -> tuple[str, DatasetStore, MockIntentAgent]:
    """Returns (dataset_id, store, agent) ready for a happy-path test."""
    did = new_id()
    store = DatasetStore()
    if register:
        store.register(did)
    agent = MockIntentAgent(spec or _default_spec())
    return did, store, agent


def post(
    dataset_id: str,
    store: DatasetStore,
    intent_agent: MockIntentAgent,
    question: str = "show revenue by region",
    domain: str = "finance",
    confirmed: bool = False,
    token: Optional[str] = "Bearer valid-token",
) -> Response:
    req = IntentRequest(question=question, domain=domain, confirmed=confirmed)
    return handle_post_intent(dataset_id, req, store, intent_agent, auth_token=token)


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
        print("  POST /datasets/{id}/intent — test results")
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
# 200 — status, headers, top-level body shape
# ─────────────────────────────────────────────────────────────────────────────

class TestHappyPathStatus:

    def test_returns_200(self):
        did, store, agent = make_env()
        assert post(did, store, agent).status_code == 200

    def test_ok_property_true(self):
        did, store, agent = make_env()
        assert post(did, store, agent).ok is True

    def test_content_type_json(self):
        did, store, agent = make_env()
        resp = post(did, store, agent)
        assert resp.headers.get("Content-Type") == "application/json"

    def test_body_is_dict(self):
        did, store, agent = make_env()
        assert isinstance(post(did, store, agent).json(), dict)


class TestResponseShape:

    REQUIRED_KEYS = {"dataset_id", "restatement", "analysis_spec",
                     "confidence", "hitl_status"}

    def test_all_required_top_level_keys_present(self):
        did, store, agent = make_env()
        assert self.REQUIRED_KEYS.issubset(post(did, store, agent).json().keys())

    def test_dataset_id_in_response(self):
        did, store, agent = make_env()
        assert "dataset_id" in post(did, store, agent).json()

    def test_restatement_in_response(self):
        did, store, agent = make_env()
        assert "restatement" in post(did, store, agent).json()

    def test_analysis_spec_in_response(self):
        did, store, agent = make_env()
        assert "analysis_spec" in post(did, store, agent).json()

    def test_confidence_in_response(self):
        did, store, agent = make_env()
        assert "confidence" in post(did, store, agent).json()

    def test_hitl_status_in_response(self):
        did, store, agent = make_env()
        assert "hitl_status" in post(did, store, agent).json()

    def test_analysis_spec_is_dict(self):
        did, store, agent = make_env()
        assert isinstance(post(did, store, agent).json()["analysis_spec"], dict)

    def test_restatement_is_str(self):
        did, store, agent = make_env()
        assert isinstance(post(did, store, agent).json()["restatement"], str)

    def test_confidence_is_float(self):
        did, store, agent = make_env()
        assert isinstance(post(did, store, agent).json()["confidence"], float)

    def test_hitl_status_is_str(self):
        did, store, agent = make_env()
        assert isinstance(post(did, store, agent).json()["hitl_status"], str)


# ─────────────────────────────────────────────────────────────────────────────
# 200 — dataset_id echoed correctly
# ─────────────────────────────────────────────────────────────────────────────

class TestDatasetIdEchoed:

    def test_dataset_id_matches_path_param(self):
        did, store, agent = make_env()
        assert post(did, store, agent).json()["dataset_id"] == did

    def test_different_dataset_id_echoed_correctly(self):
        did = new_id()
        store = DatasetStore()
        store.register(did)
        agent = MockIntentAgent()
        assert post(did, store, agent).json()["dataset_id"] == did

    def test_dataset_id_is_string(self):
        did, store, agent = make_env()
        assert isinstance(post(did, store, agent).json()["dataset_id"], str)

    def test_dataset_id_is_not_empty(self):
        did, store, agent = make_env()
        assert post(did, store, agent).json()["dataset_id"] != ""

    def test_two_different_datasets_return_correct_ids(self):
        did_a, store_a, agent_a = make_env()
        did_b, store_b, agent_b = make_env()
        assert post(did_a, store_a, agent_a).json()["dataset_id"] == did_a
        assert post(did_b, store_b, agent_b).json()["dataset_id"] == did_b


# ─────────────────────────────────────────────────────────────────────────────
# 200 — restatement field
# ─────────────────────────────────────────────────────────────────────────────

class TestRestatement:

    def test_restatement_matches_spec(self):
        spec = _default_spec(restatement="Show MRR by customer segment")
        did, store, agent = make_env(spec)
        assert post(did, store, agent).json()["restatement"] == "Show MRR by customer segment"

    def test_restatement_also_in_analysis_spec(self):
        spec = _default_spec(restatement="Total revenue grouped by region")
        did, store, agent = make_env(spec)
        body = post(did, store, agent).json()
        assert body["restatement"] == body["analysis_spec"]["restatement"]

    def test_restatement_non_empty_for_valid_question(self):
        did, store, agent = make_env()
        assert len(post(did, store, agent).json()["restatement"].strip()) > 0

    def test_restatement_is_not_the_raw_question(self):
        """Agent rephrases in domain terms — restatement ≠ raw input."""
        spec = _default_spec(restatement="Show total monthly recurring revenue by plan tier")
        did, store, agent = make_env(spec)
        body = post(did, store, agent,
                    question="whats our numbers",
                    domain="finance").json()
        assert body["restatement"] != "whats our numbers"

    def test_restatement_verbatim_from_agent(self):
        text = "Compare average length of stay across wards for Q1 2024"
        spec = _default_spec(restatement=text)
        did, store, agent = make_env(spec)
        assert post(did, store, agent).json()["restatement"] == text


# ─────────────────────────────────────────────────────────────────────────────
# 200 — analysis_spec fields
# ─────────────────────────────────────────────────────────────────────────────

class TestAnalysisSpecShape:

    REQUIRED_SPEC_KEYS = {
        "dimensions", "measures", "suggested_chart_types",
        "restatement", "confidence", "filters", "time_range",
    }

    def _spec_body(self, **kwargs) -> dict:
        spec = _default_spec(**kwargs)
        did, store, agent = make_env(spec)
        return post(did, store, agent).json()["analysis_spec"]

    def test_all_required_spec_keys_present(self):
        assert self.REQUIRED_SPEC_KEYS.issubset(self._spec_body().keys())

    def test_dimensions_is_list(self):
        assert isinstance(self._spec_body()["dimensions"], list)

    def test_measures_is_list(self):
        assert isinstance(self._spec_body()["measures"], list)

    def test_suggested_chart_types_is_list(self):
        assert isinstance(self._spec_body()["suggested_chart_types"], list)

    def test_restatement_is_str(self):
        assert isinstance(self._spec_body()["restatement"], str)

    def test_confidence_is_float(self):
        assert isinstance(self._spec_body()["confidence"], float)

    def test_dimensions_preserved(self):
        assert self._spec_body(dimensions=["ward", "payer"])["dimensions"] == ["ward", "payer"]

    def test_measures_preserved(self):
        assert self._spec_body(measures=["los", "readmission_rate"])["measures"] == ["los", "readmission_rate"]

    def test_chart_types_preserved(self):
        assert self._spec_body(suggested_chart_types=["bar", "line"])["suggested_chart_types"] == ["bar", "line"]

    def test_confidence_value_exact(self):
        spec = self._spec_body(confidence=0.87)
        assert abs(spec["confidence"] - 0.87) < 1e-9

    def test_filters_none_when_absent(self):
        assert self._spec_body(filters=None)["filters"] is None

    def test_filters_list_preserved(self):
        f = [{"col": "region", "op": "=", "val": "APAC"}]
        assert self._spec_body(filters=f)["filters"] == f

    def test_time_range_none_when_absent(self):
        assert self._spec_body(time_range=None)["time_range"] is None

    def test_time_range_dict_preserved(self):
        tr = {"start": "2024-01-01", "end": "2024-12-31"}
        assert self._spec_body(time_range=tr)["time_range"] == tr


# ─────────────────────────────────────────────────────────────────────────────
# 200 — confidence top-level field
# ─────────────────────────────────────────────────────────────────────────────

class TestConfidenceField:

    def test_confidence_matches_spec_value(self):
        spec = _default_spec(confidence=0.94)
        did, store, agent = make_env(spec)
        assert post(did, store, agent).json()["confidence"] == 0.94

    def test_confidence_matches_analysis_spec_confidence(self):
        spec = _default_spec(confidence=0.78)
        did, store, agent = make_env(spec)
        body = post(did, store, agent).json()
        assert body["confidence"] == body["analysis_spec"]["confidence"]

    def test_low_confidence_preserved(self):
        spec = _default_spec(confidence=0.12)
        did, store, agent = make_env(spec)
        assert abs(post(did, store, agent).json()["confidence"] - 0.12) < 1e-9

    def test_confidence_zero_preserved(self):
        spec = _default_spec(confidence=0.0)
        did, store, agent = make_env(spec)
        assert post(did, store, agent).json()["confidence"] == 0.0

    def test_confidence_one_preserved(self):
        spec = _default_spec(confidence=1.0)
        did, store, agent = make_env(spec)
        assert post(did, store, agent).json()["confidence"] == 1.0


# ─────────────────────────────────────────────────────────────────────────────
# 200 — hitl_status (HITL #3 confirmation flag)
# ─────────────────────────────────────────────────────────────────────────────

class TestHITLStatus:

    def test_unconfirmed_request_returns_pending_confirmation(self):
        did, store, agent = make_env()
        body = post(did, store, agent, confirmed=False).json()
        assert body["hitl_status"] == "pending_confirmation"

    def test_confirmed_request_returns_confirmed(self):
        did, store, agent = make_env()
        body = post(did, store, agent, confirmed=True).json()
        assert body["hitl_status"] == "confirmed"

    def test_default_confirmed_is_false_gives_pending(self):
        did, store, agent = make_env()
        req = IntentRequest(question="show revenue", domain="finance")
        resp = handle_post_intent(did, req, store, agent)
        assert resp.json()["hitl_status"] == "pending_confirmation"

    def test_hitl_status_is_valid_value(self):
        for confirmed in [True, False]:
            did, store, agent = make_env()
            status = post(did, store, agent, confirmed=confirmed).json()["hitl_status"]
            assert status in VALID_HITL_STATUS

    def test_confirmed_true_does_not_change_analysis_spec(self):
        """Confirming intent must not alter the analysis spec content."""
        spec = _default_spec(dimensions=["channel"], measures=["cpa"])
        did, store, agent = make_env(spec)
        body_unconfirmed = post(did, store, agent, confirmed=False).json()
        did2, store2, agent2 = make_env(spec)
        body_confirmed   = post(did2, store2, agent2, confirmed=True).json()
        assert body_unconfirmed["analysis_spec"] == body_confirmed["analysis_spec"]


# ─────────────────────────────────────────────────────────────────────────────
# 200 — Intent Agent called with correct arguments
# ─────────────────────────────────────────────────────────────────────────────

class TestIntentAgentInteraction:

    def test_agent_called_exactly_once(self):
        did, store, agent = make_env()
        post(did, store, agent)
        assert agent.call_count == 1

    def test_agent_receives_question(self):
        did, store, agent = make_env()
        post(did, store, agent, question="what is our churn rate?")
        assert agent.calls[0]["question"] == "what is our churn rate?"

    def test_agent_receives_domain(self):
        did, store, agent = make_env()
        post(did, store, agent, domain="healthcare")
        assert agent.calls[0]["domain"] == "healthcare"

    def test_agent_called_with_exact_question_verbatim(self):
        q = "compare Q3 vs Q4 revenue by channel and SKU margin"
        did, store, agent = make_env()
        post(did, store, agent, question=q)
        assert agent.calls[0]["question"] == q

    def test_agent_not_called_on_validation_error(self):
        did, store, agent = make_env()
        post(did, store, agent, question="")   # empty → 422
        assert agent.call_count == 0

    def test_agent_not_called_on_404(self):
        store = DatasetStore()    # dataset NOT registered
        agent = MockIntentAgent()
        post(new_id(), store, agent)
        assert agent.call_count == 0

    def test_agent_not_called_on_401(self):
        did, store, agent = make_env()
        post(did, store, agent, token=None)
        assert agent.call_count == 0

    def test_agent_failure_returns_500(self):
        did, store, agent = make_env()
        agent.raise_on_call = RuntimeError("LLM rate limit")
        resp = post(did, store, agent)
        assert resp.status_code == 500

    def test_agent_failure_body_has_detail(self):
        did, store, agent = make_env()
        agent.raise_on_call = RuntimeError("timeout")
        assert "detail" in post(did, store, agent).json()

    def test_separate_calls_use_separate_agents(self):
        did_a, store_a, agent_a = make_env()
        did_b, store_b, agent_b = make_env()
        post(did_a, store_a, agent_a, question="q1")
        post(did_b, store_b, agent_b, question="q2")
        assert agent_a.calls[0]["question"] == "q1"
        assert agent_b.calls[0]["question"] == "q2"


# ─────────────────────────────────────────────────────────────────────────────
# Request validation — question field
# ─────────────────────────────────────────────────────────────────────────────

class TestQuestionValidation:

    def test_empty_question_returns_422(self):
        did, store, agent = make_env()
        assert post(did, store, agent, question="").status_code == 422

    def test_whitespace_only_question_returns_422(self):
        did, store, agent = make_env()
        assert post(did, store, agent, question="   ").status_code == 422

    def test_newline_only_question_returns_422(self):
        did, store, agent = make_env()
        assert post(did, store, agent, question="\n\t").status_code == 422

    def test_422_body_has_detail(self):
        did, store, agent = make_env()
        assert "detail" in post(did, store, agent, question="").json()

    def test_single_word_question_accepted(self):
        did, store, agent = make_env()
        assert post(did, store, agent, question="revenue").status_code == 200

    def test_long_question_accepted(self):
        q = "what is the quarter-over-quarter growth rate of gross margin " * 20
        did, store, agent = make_env()
        assert post(did, store, agent, question=q).status_code == 200

    def test_question_with_special_chars_accepted(self):
        did, store, agent = make_env()
        assert post(did, store, agent, question="what's the MoM Δ in ARR (%)?"
                    ).status_code == 200

    def test_question_with_unicode_accepted(self):
        did, store, agent = make_env()
        assert post(did, store, agent, question="売上を地域別に表示してください"
                    ).status_code == 200

    def test_valid_question_produces_200_not_422(self):
        did, store, agent = make_env()
        assert post(did, store, agent, question="show revenue by region"
                    ).status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# Request validation — domain field
# ─────────────────────────────────────────────────────────────────────────────

class TestDomainValidation:

    def test_unknown_domain_returns_422(self):
        did, store, agent = make_env()
        assert post(did, store, agent, domain="astronomy").status_code == 422

    def test_422_body_mentions_domain(self):
        did, store, agent = make_env()
        body = post(did, store, agent, domain="invalid_domain").json()
        assert "domain" in body["detail"].lower() or "invalid_domain" in body["detail"]

    def test_finance_domain_accepted(self):
        did, store, agent = make_env()
        assert post(did, store, agent, domain="finance").status_code == 200

    def test_healthcare_domain_accepted(self):
        did, store, agent = make_env()
        assert post(did, store, agent, domain="healthcare").status_code == 200

    def test_retail_domain_accepted(self):
        did, store, agent = make_env()
        assert post(did, store, agent, domain="retail").status_code == 200

    def test_marketing_domain_accepted(self):
        did, store, agent = make_env()
        assert post(did, store, agent, domain="marketing").status_code == 200

    def test_operations_domain_accepted(self):
        did, store, agent = make_env()
        assert post(did, store, agent, domain="operations").status_code == 200

    def test_other_domain_accepted(self):
        did, store, agent = make_env()
        assert post(did, store, agent, domain="other").status_code == 200

    def test_all_valid_domains_return_200(self):
        for domain in VALID_DOMAINS:
            did, store, agent = make_env()
            assert post(did, store, agent, domain=domain).status_code == 200, \
                f"Domain '{domain}' should be accepted"

    def test_domain_case_sensitive_uppercase_rejected(self):
        did, store, agent = make_env()
        assert post(did, store, agent, domain="Finance").status_code == 422

    def test_empty_domain_returns_422(self):
        did, store, agent = make_env()
        assert post(did, store, agent, domain="").status_code == 422

    def test_domain_sent_to_agent(self):
        did, store, agent = make_env()
        post(did, store, agent, domain="retail")
        assert agent.calls[0]["domain"] == "retail"


# ─────────────────────────────────────────────────────────────────────────────
# 404 — dataset not found
# ─────────────────────────────────────────────────────────────────────────────

class TestNotFound:

    def test_unregistered_id_returns_404(self):
        store = DatasetStore()
        agent = MockIntentAgent()
        assert post(new_id(), store, agent).status_code == 404

    def test_404_body_has_detail(self):
        store = DatasetStore()
        body = post(new_id(), store, MockIntentAgent()).json()
        assert "detail" in body

    def test_404_detail_mentions_dataset_id(self):
        did = new_id()
        store = DatasetStore()
        body = post(did, store, MockIntentAgent()).json()
        assert did in body["detail"]

    def test_404_ok_is_false(self):
        store = DatasetStore()
        assert post(new_id(), store, MockIntentAgent()).ok is False

    def test_registered_id_does_not_return_404(self):
        did, store, agent = make_env()
        assert post(did, store, agent).status_code != 404

    def test_wrong_id_for_existing_dataset_returns_404(self):
        did, store, agent = make_env()
        assert post(new_id(), store, agent).status_code == 404

    def test_multiple_unknown_ids_all_404(self):
        store = DatasetStore()
        for _ in range(5):
            assert post(new_id(), store, MockIntentAgent()).status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# 401 — authentication
# ─────────────────────────────────────────────────────────────────────────────

class TestAuthentication:

    def test_no_token_returns_401(self):
        did, store, agent = make_env()
        assert post(did, store, agent, token=None).status_code == 401

    def test_empty_token_returns_401(self):
        did, store, agent = make_env()
        assert post(did, store, agent, token="").status_code == 401

    def test_whitespace_token_returns_401(self):
        did, store, agent = make_env()
        assert post(did, store, agent, token="   ").status_code == 401

    def test_401_has_www_authenticate_header(self):
        did, store, agent = make_env()
        resp = post(did, store, agent, token=None)
        assert "WWW-Authenticate" in resp.headers

    def test_401_www_authenticate_is_bearer(self):
        did, store, agent = make_env()
        assert post(did, store, agent, token=None).headers["WWW-Authenticate"] == "Bearer"

    def test_401_body_has_detail(self):
        did, store, agent = make_env()
        assert "detail" in post(did, store, agent, token=None).json()

    def test_invalid_token_for_dataset_returns_401(self):
        did, store, agent = make_env()
        store.set_unauthorized(did)
        assert post(did, store, agent).status_code == 401

    def test_valid_token_returns_200(self):
        did, store, agent = make_env()
        assert post(did, store, agent, token="Bearer my-token").status_code == 200

    def test_agent_not_called_on_missing_token(self):
        did, store, agent = make_env()
        post(did, store, agent, token=None)
        assert agent.call_count == 0


# ─────────────────────────────────────────────────────────────────────────────
# 403 — authorisation
# ─────────────────────────────────────────────────────────────────────────────

class TestAuthorisation:

    def test_forbidden_dataset_returns_403(self):
        did, store, agent = make_env()
        store.set_forbidden(did)
        assert post(did, store, agent).status_code == 403

    def test_403_body_has_detail(self):
        did, store, agent = make_env()
        store.set_forbidden(did)
        assert "detail" in post(did, store, agent).json()

    def test_403_ok_is_false(self):
        did, store, agent = make_env()
        store.set_forbidden(did)
        assert post(did, store, agent).ok is False

    def test_own_dataset_not_forbidden(self):
        did, store, agent = make_env()
        assert post(did, store, agent).status_code == 200

    def test_forbidden_on_one_does_not_affect_another(self):
        did_bad, store, agent = make_env()
        did_good = new_id()
        store.register(did_good)
        store.set_forbidden(did_bad)
        assert post(did_bad, store, agent).status_code == 403
        assert post(did_good, store, agent).status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# 409 — pipeline not ready (cleaning not complete)
# ─────────────────────────────────────────────────────────────────────────────

class TestPipelineNotReady:

    def test_pipeline_not_ready_returns_409(self):
        did, store, agent = make_env()
        store.set_pipeline_not_ready(did)
        assert post(did, store, agent).status_code == 409

    def test_409_body_has_detail(self):
        did, store, agent = make_env()
        store.set_pipeline_not_ready(did)
        assert "detail" in post(did, store, agent).json()

    def test_409_body_has_status_pipeline_not_ready(self):
        did, store, agent = make_env()
        store.set_pipeline_not_ready(did)
        assert post(did, store, agent).json()["status"] == "pipeline_not_ready"

    def test_409_ok_is_false(self):
        did, store, agent = make_env()
        store.set_pipeline_not_ready(did)
        assert post(did, store, agent).ok is False

    def test_ready_dataset_not_409(self):
        did, store, agent = make_env()
        assert post(did, store, agent).status_code == 200

    def test_agent_not_called_on_409(self):
        did, store, agent = make_env()
        store.set_pipeline_not_ready(did)
        post(did, store, agent)
        assert agent.call_count == 0


# ─────────────────────────────────────────────────────────────────────────────
# 500 — internal server error
# ─────────────────────────────────────────────────────────────────────────────

class TestServerError:

    def test_store_error_returns_500(self):
        did, store, agent = make_env()
        store.set_error(did)
        assert post(did, store, agent).status_code == 500

    def test_500_body_has_detail(self):
        did, store, agent = make_env()
        store.set_error(did)
        assert "detail" in post(did, store, agent).json()

    def test_500_ok_is_false(self):
        did, store, agent = make_env()
        store.set_error(did)
        assert post(did, store, agent).ok is False

    def test_agent_exception_returns_500(self):
        did, store, agent = make_env()
        agent.raise_on_call = RuntimeError("LLM unavailable")
        assert post(did, store, agent).status_code == 500

    def test_error_on_one_dataset_does_not_affect_another(self):
        did_bad, store, agent = make_env()
        did_good = new_id()
        store.register(did_good)
        store.set_error(did_bad)
        assert post(did_bad, store, agent).status_code == 500
        assert post(did_good, store, agent).status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# Domain-specific intent scenarios (HITL #3 realistic flows)
# ─────────────────────────────────────────────────────────────────────────────

class TestDomainSpecificIntentScenarios:

    def test_finance_revenue_by_region(self):
        spec = _default_spec(
            dimensions=["region"],
            measures=["revenue"],
            suggested_chart_types=["bar"],
            restatement="Show total revenue grouped by region for all periods",
            confidence=0.95,
        )
        did, store, agent = make_env(spec)
        body = post(did, store, agent,
                    question="show me revenue by region",
                    domain="finance").json()
        assert body["analysis_spec"]["dimensions"] == ["region"]
        assert body["analysis_spec"]["measures"] == ["revenue"]
        assert "bar" in body["analysis_spec"]["suggested_chart_types"]
        assert body["confidence"] == 0.95

    def test_healthcare_los_by_ward(self):
        spec = _default_spec(
            dimensions=["ward"],
            measures=["length_of_stay"],
            suggested_chart_types=["bar", "table"],
            restatement="Show average length of stay per ward",
            confidence=0.88,
        )
        did, store, agent = make_env(spec)
        body = post(did, store, agent,
                    question="avg length of stay by ward",
                    domain="healthcare").json()
        assert body["analysis_spec"]["dimensions"] == ["ward"]
        assert "length_of_stay" in body["analysis_spec"]["measures"]

    def test_retail_sku_margin_by_channel(self):
        spec = _default_spec(
            dimensions=["channel", "sku"],
            measures=["margin", "units_sold"],
            suggested_chart_types=["table"],
            restatement="Show SKU margin and units sold by channel",
            confidence=0.82,
        )
        did, store, agent = make_env(spec)
        body = post(did, store, agent,
                    question="top SKUs by channel",
                    domain="retail").json()
        assert "channel" in body["analysis_spec"]["dimensions"]
        assert "sku" in body["analysis_spec"]["dimensions"]

    def test_marketing_ctr_by_campaign(self):
        spec = _default_spec(
            dimensions=["campaign"],
            measures=["ctr", "cpa"],
            suggested_chart_types=["bar"],
            restatement="Show CTR and CPA by campaign",
            confidence=0.91,
        )
        did, store, agent = make_env(spec)
        body = post(did, store, agent,
                    question="which campaigns have best CTR?",
                    domain="marketing").json()
        assert "campaign" in body["analysis_spec"]["dimensions"]
        assert "ctr" in body["analysis_spec"]["measures"]

    def test_low_confidence_ambiguous_question(self):
        spec = _default_spec(
            dimensions=[],
            measures=[],
            suggested_chart_types=["table"],
            restatement="Question is too ambiguous to map to available columns",
            confidence=0.15,
        )
        did, store, agent = make_env(spec)
        body = post(did, store, agent,
                    question="what about the thing?",
                    domain="other").json()
        assert body["confidence"] < 0.5
        assert body["hitl_status"] == "pending_confirmation"

    def test_time_series_question_returns_line_chart(self):
        spec = _default_spec(
            dimensions=["date"],
            measures=["revenue"],
            suggested_chart_types=["line"],
            restatement="Show revenue trend over time",
            confidence=0.93,
        )
        did, store, agent = make_env(spec)
        body = post(did, store, agent,
                    question="revenue over time",
                    domain="finance").json()
        assert "line" in body["analysis_spec"]["suggested_chart_types"]

    def test_confirmed_intent_passes_to_dashboard_pipeline(self):
        """
        User confirms the restatement → hitl_status = 'confirmed'
        which signals the pipeline to proceed to dashboard generation.
        """
        spec = _default_spec(confidence=0.90)
        did, store, agent = make_env(spec)
        body = post(did, store, agent, confirmed=True).json()
        assert body["hitl_status"] == "confirmed"

    def test_unconfirmed_intent_waits_for_user(self):
        """pending_confirmation signals the frontend to show the restatement for review."""
        spec = _default_spec(confidence=0.90)
        did, store, agent = make_env(spec)
        body = post(did, store, agent, confirmed=False).json()
        assert body["hitl_status"] == "pending_confirmation"


# ─────────────────────────────────────────────────────────────────────────────
# Suggested chart types validation
# ─────────────────────────────────────────────────────────────────────────────

class TestSuggestedChartTypes:

    def test_single_chart_type_bar_preserved(self):
        spec = _default_spec(suggested_chart_types=["bar"])
        did, store, agent = make_env(spec)
        assert post(did, store, agent).json()["analysis_spec"]["suggested_chart_types"] == ["bar"]

    def test_multiple_chart_types_preserved(self):
        spec = _default_spec(suggested_chart_types=["line", "bar", "table"])
        did, store, agent = make_env(spec)
        assert post(did, store, agent).json()["analysis_spec"]["suggested_chart_types"] == ["line", "bar", "table"]

    def test_all_valid_chart_types_accepted(self):
        for ct in VALID_CHART_TYPES:
            spec = _default_spec(suggested_chart_types=[ct])
            did, store, agent = make_env(spec)
            result = post(did, store, agent).json()["analysis_spec"]["suggested_chart_types"]
            assert ct in result

    def test_empty_chart_types_preserved(self):
        spec = _default_spec(suggested_chart_types=[])
        did, store, agent = make_env(spec)
        assert post(did, store, agent).json()["analysis_spec"]["suggested_chart_types"] == []


# ─────────────────────────────────────────────────────────────────────────────
# Edge cases
# ─────────────────────────────────────────────────────────────────────────────

class TestEdgeCases:

    def test_same_dataset_called_twice_returns_same_shape(self):
        did, store, agent = make_env()
        r1 = post(did, store, agent).json()
        r2 = post(did, store, agent).json()
        assert set(r1.keys()) == set(r2.keys())

    def test_agent_called_once_per_request(self):
        did, store, agent = make_env()
        post(did, store, agent)
        post(did, store, agent)
        assert agent.call_count == 2

    def test_multiline_question_sent_to_agent_verbatim(self):
        q = "compare revenue\nby region\nand channel"
        did, store, agent = make_env()
        post(did, store, agent, question=q)
        assert agent.calls[0]["question"] == q

    def test_dataset_id_with_hyphens_handled(self):
        did = str(uuid.uuid4())
        store = DatasetStore()
        store.register(did)
        agent = MockIntentAgent()
        assert post(did, store, agent).status_code == 200

    def test_empty_dimensions_and_measures_preserved(self):
        spec = _default_spec(dimensions=[], measures=[])
        did, store, agent = make_env(spec)
        body = post(did, store, agent).json()["analysis_spec"]
        assert body["dimensions"] == []
        assert body["measures"] == []

    def test_both_validation_errors_return_422_not_500(self):
        did, store, agent = make_env()
        resp_empty_q = post(did, store, agent, question="")
        resp_bad_domain = post(did, store, agent, domain="badvalue")
        assert resp_empty_q.status_code == 422
        assert resp_bad_domain.status_code == 422

    def test_response_body_is_json_serialisable(self):
        spec = _default_spec(
            filters=[{"col": "region", "op": "=", "val": "APAC"}],
            time_range={"start": "2024-01-01", "end": "2024-12-31"},
        )
        did, store, agent = make_env(spec)
        body = post(did, store, agent).json()
        try:
            json.dumps(body)
        except TypeError as exc:
            raise AssertionError(f"Response body not JSON-serialisable: {exc}") from exc

    def test_confirmed_false_is_default_behaviour(self):
        did, store, agent = make_env()
        body_default  = post(did, store, agent).json()
        body_explicit = post(did, store, agent, confirmed=False).json()
        assert body_default["hitl_status"] == body_explicit["hitl_status"]


# ═════════════════════════════════════════════════════════════════════════════
# Runner
# ═════════════════════════════════════════════════════════════════════════════

def _collect_all_test_classes():
    return [
        TestHappyPathStatus,
        TestResponseShape,
        TestDatasetIdEchoed,
        TestRestatement,
        TestAnalysisSpecShape,
        TestConfidenceField,
        TestHITLStatus,
        TestIntentAgentInteraction,
        TestQuestionValidation,
        TestDomainValidation,
        TestNotFound,
        TestAuthentication,
        TestAuthorisation,
        TestPipelineNotReady,
        TestServerError,
        TestDomainSpecificIntentScenarios,
        TestSuggestedChartTypes,
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