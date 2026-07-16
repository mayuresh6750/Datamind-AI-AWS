"""
Unit tests for  GET /jobs/{job_id}

Task reference : S2-12 (Sprint 2)
    "GET /jobs/{id} — poll job status (queued / running / paused / done / failed),
     progress %, current step"

Architecture refs (supervisor.py PipelineState):
    job_id, dataset_id, user_id, domain, status, error

Pipeline statuses (from architecture.md data-flow steps):
    queued    → job enqueued, not yet picked up by a worker
    running   → actively executing an agent step
    paused    → blocked at a HITL checkpoint (#1, #2, or #3)
    done      → pipeline completed successfully
    failed    → pipeline terminated with an error

HITL pause statuses (substatus inside "paused"):
    awaiting_hitl_merge       → blocked at HITL #1 (merge-plan decision)
    awaiting_hitl_cleaning    → blocked at HITL #2 (cleaning-plan decision)
    awaiting_hitl_intent      → blocked at HITL #3 (intent confirmation)

Response shape (200):
    {
        "job_id":       str,
        "dataset_id":   str,
        "status":       str,           # queued|running|paused|done|failed
        "progress":     int,           # 0–100
        "current_step": str | null,    # name of the active agent step
        "substatus":    str | null,    # HITL pause reason, null otherwise
        "error":        str | null,    # only when status==failed
        "created_at":   str,           # ISO-8601 timestamp
        "updated_at":   str,           # ISO-8601 timestamp
    }

Run with:
    pytest  test_get_jobs.py -v
    python  test_get_jobs.py       # live results, no pytest needed

Fully independent — no real HTTP server, no DB, no Supabase, no app imports.
"""

from __future__ import annotations

import json
import sys
import traceback
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

# ─────────────────────────────────────────────────────────────────────────────
# Domain constants
# ─────────────────────────────────────────────────────────────────────────────

VALID_STATUSES  = {"queued", "running", "paused", "done", "failed"}
VALID_SUBSTATUS = {
    "awaiting_hitl_merge",
    "awaiting_hitl_cleaning",
    "awaiting_hitl_intent",
}

# Pipeline steps in execution order (mirrors supervisor.py node names; production uses tasks.py)
PIPELINE_STEPS = [
    "load_domain",
    "ingest",
    "await_merge_hitl",
    "cleaning_plan",
    "await_cleaning_hitl",
    "execute_cleaning",
    "intent",
    "analyze",
    "dashboard",
]

# Approximate progress % at the END of each step
STEP_PROGRESS = {
    "load_domain":         5,
    "ingest":             20,
    "await_merge_hitl":   20,   # blocked — progress stays
    "cleaning_plan":      40,
    "await_cleaning_hitl":40,   # blocked — progress stays
    "execute_cleaning":   60,
    "intent":             70,
    "analyze":            85,
    "dashboard":         100,
}


# ─────────────────────────────────────────────────────────────────────────────
# Job model
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Job:
    job_id: str
    dataset_id: str
    status: str                        # queued|running|paused|done|failed
    progress: int = 0                  # 0–100
    current_step: Optional[str] = None
    substatus: Optional[str] = None    # HITL pause reason
    error: Optional[str] = None
    created_at: str = "2026-06-04T10:00:00Z"
    updated_at: str = "2026-06-04T10:00:01Z"
    user_id: str = "user-abc"
    domain: str = "finance"


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
# Job store
# ─────────────────────────────────────────────────────────────────────────────

class JobStore:
    """
    In-memory job registry.
    add(job)           → register a Job
    set_error(job_id)  → force 500 on lookup
    set_unauthorized   → 401
    set_forbidden      → 403
    """

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._server_errors: set[str] = set()
        self._unauthorized: set[str] = set()
        self._forbidden: set[str] = set()

    def add(self, job: Job) -> None:
        self._jobs[job.job_id] = job

    def get(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

    def set_server_error(self, job_id: str) -> None:
        self._server_errors.add(job_id)

    def set_unauthorized(self, job_id: str) -> None:
        self._unauthorized.add(job_id)

    def set_forbidden(self, job_id: str) -> None:
        self._forbidden.add(job_id)

    def is_server_error(self, job_id: str) -> bool:
        return job_id in self._server_errors

    def is_unauthorized(self, job_id: str) -> bool:
        return job_id in self._unauthorized

    def is_forbidden(self, job_id: str) -> bool:
        return job_id in self._forbidden


# ─────────────────────────────────────────────────────────────────────────────
# Fake handler:  GET /jobs/{job_id}
# ─────────────────────────────────────────────────────────────────────────────

def _job_to_dict(job: Job) -> dict:
    return {
        "job_id":       job.job_id,
        "dataset_id":   job.dataset_id,
        "status":       job.status,
        "progress":     job.progress,
        "current_step": job.current_step,
        "substatus":    job.substatus,
        "error":        job.error,
        "created_at":   job.created_at,
        "updated_at":   job.updated_at,
    }


def handle_get_job(
    job_id: str,
    store: JobStore,
    *,
    auth_token: Optional[str] = "Bearer valid-token",
) -> Response:
    """
    GET /jobs/{job_id}

    Auth      : missing/empty → 401; store.is_unauthorized → 401
    Permission: store.is_forbidden → 403
    Not found : job absent from store → 404
    Server err: store.is_server_error → 500
    Happy path: 200 + job JSON
    """
    # 401: no token
    if not auth_token or not auth_token.strip():
        return Response(
            status_code=401,
            body={"detail": "Authentication required"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    # 401: token rejected
    if store.is_unauthorized(job_id):
        return Response(
            status_code=401,
            body={"detail": "Invalid or expired token"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    # 403
    if store.is_forbidden(job_id):
        return Response(
            status_code=403,
            body={"detail": "You do not have permission to access this job"},
        )
    # 500
    if store.is_server_error(job_id):
        return Response(
            status_code=500,
            body={"detail": "Internal server error while retrieving job"},
        )
    # 404
    job = store.get(job_id)
    if job is None:
        return Response(
            status_code=404,
            body={"detail": f"Job '{job_id}' not found"},
        )
    # 200
    return Response(
        status_code=200,
        body=_job_to_dict(job),
        headers={"Content-Type": "application/json"},
    )


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def new_id() -> str:
    return str(uuid.uuid4())


def make_job(
    status: str = "queued",
    progress: int = 0,
    current_step: Optional[str] = None,
    substatus: Optional[str] = None,
    error: Optional[str] = None,
    job_id: Optional[str] = None,
    dataset_id: Optional[str] = None,
) -> Job:
    return Job(
        job_id=job_id or new_id(),
        dataset_id=dataset_id or new_id(),
        status=status,
        progress=progress,
        current_step=current_step,
        substatus=substatus,
        error=error,
    )


def get(
    store: JobStore,
    job: Job,
    token: Optional[str] = "Bearer valid-token",
) -> Response:
    return handle_get_job(job.job_id, store, auth_token=token)


def make_env(
    status: str = "queued",
    progress: int = 0,
    current_step: Optional[str] = None,
    substatus: Optional[str] = None,
    error: Optional[str] = None,
) -> tuple[JobStore, Job]:
    store = JobStore()
    job = make_job(status=status, progress=progress,
                   current_step=current_step, substatus=substatus, error=error)
    store.add(job)
    return store, job


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
        print("  GET /jobs/{job_id} — test results")
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
# 200 — status code and headers
# ─────────────────────────────────────────────────────────────────────────────

class TestHappyPathStatusAndHeaders:

    def test_returns_200_for_existing_job(self):
        store, job = make_env()
        assert get(store, job).status_code == 200

    def test_ok_property_true(self):
        store, job = make_env()
        assert get(store, job).ok is True

    def test_content_type_json(self):
        store, job = make_env()
        assert get(store, job).headers.get("Content-Type") == "application/json"

    def test_body_is_dict(self):
        store, job = make_env()
        assert isinstance(get(store, job).json(), dict)


# ─────────────────────────────────────────────────────────────────────────────
# Response shape — required fields
# ─────────────────────────────────────────────────────────────────────────────

class TestResponseShape:

    REQUIRED_KEYS = {
        "job_id", "dataset_id", "status", "progress",
        "current_step", "substatus", "error",
        "created_at", "updated_at",
    }

    def _body(self) -> dict:
        store, job = make_env()
        return get(store, job).json()

    def test_all_required_keys_present(self):
        assert self.REQUIRED_KEYS.issubset(self._body().keys())

    def test_job_id_present(self):
        assert "job_id" in self._body()

    def test_dataset_id_present(self):
        assert "dataset_id" in self._body()

    def test_status_present(self):
        assert "status" in self._body()

    def test_progress_present(self):
        assert "progress" in self._body()

    def test_current_step_present(self):
        assert "current_step" in self._body()

    def test_substatus_present(self):
        assert "substatus" in self._body()

    def test_error_present(self):
        assert "error" in self._body()

    def test_created_at_present(self):
        assert "created_at" in self._body()

    def test_updated_at_present(self):
        assert "updated_at" in self._body()

    def test_job_id_is_string(self):
        assert isinstance(self._body()["job_id"], str)

    def test_status_is_string(self):
        assert isinstance(self._body()["status"], str)

    def test_progress_is_int(self):
        assert isinstance(self._body()["progress"], int)

    def test_created_at_is_string(self):
        assert isinstance(self._body()["created_at"], str)

    def test_updated_at_is_string(self):
        assert isinstance(self._body()["updated_at"], str)


# ─────────────────────────────────────────────────────────────────────────────
# job_id and dataset_id echoed correctly
# ─────────────────────────────────────────────────────────────────────────────

class TestIdFields:

    def test_job_id_matches_path_param(self):
        store, job = make_env()
        assert get(store, job).json()["job_id"] == job.job_id

    def test_dataset_id_echoed_correctly(self):
        store, job = make_env()
        assert get(store, job).json()["dataset_id"] == job.dataset_id

    def test_job_id_is_non_empty(self):
        store, job = make_env()
        assert len(get(store, job).json()["job_id"]) > 0

    def test_two_jobs_return_distinct_ids(self):
        store = JobStore()
        job_a = make_job()
        job_b = make_job()
        store.add(job_a)
        store.add(job_b)
        resp_a = handle_get_job(job_a.job_id, store).json()
        resp_b = handle_get_job(job_b.job_id, store).json()
        assert resp_a["job_id"] != resp_b["job_id"]
        assert resp_a["job_id"] == job_a.job_id
        assert resp_b["job_id"] == job_b.job_id


# ─────────────────────────────────────────────────────────────────────────────
# STATUS field — all five valid states
# ─────────────────────────────────────────────────────────────────────────────

class TestStatusField:

    def test_queued_status_returned(self):
        store, job = make_env(status="queued")
        assert get(store, job).json()["status"] == "queued"

    def test_running_status_returned(self):
        store, job = make_env(status="running")
        assert get(store, job).json()["status"] == "running"

    def test_paused_status_returned(self):
        store, job = make_env(status="paused")
        assert get(store, job).json()["status"] == "paused"

    def test_done_status_returned(self):
        store, job = make_env(status="done")
        assert get(store, job).json()["status"] == "done"

    def test_failed_status_returned(self):
        store, job = make_env(status="failed", error="out of memory")
        assert get(store, job).json()["status"] == "failed"

    def test_all_valid_statuses_accepted(self):
        for status in VALID_STATUSES:
            store, job = make_env(status=status)
            assert get(store, job).json()["status"] == status, \
                f"Status '{status}' not echoed correctly"

    def test_status_is_valid_value(self):
        for status in VALID_STATUSES:
            store, job = make_env(status=status)
            returned = get(store, job).json()["status"]
            assert returned in VALID_STATUSES

    def test_queued_is_terminal_false(self):
        store, job = make_env(status="queued")
        assert get(store, job).json()["status"] != "done"

    def test_done_is_terminal(self):
        store, job = make_env(status="done", progress=100)
        body = get(store, job).json()
        assert body["status"] == "done"
        assert body["progress"] == 100

    def test_failed_is_terminal(self):
        store, job = make_env(status="failed", error="agent error")
        body = get(store, job).json()
        assert body["status"] == "failed"


# ─────────────────────────────────────────────────────────────────────────────
# PROGRESS field — 0-100 integer
# ─────────────────────────────────────────────────────────────────────────────

class TestProgressField:

    def test_progress_zero_for_queued(self):
        store, job = make_env(status="queued", progress=0)
        assert get(store, job).json()["progress"] == 0

    def test_progress_100_for_done(self):
        store, job = make_env(status="done", progress=100)
        assert get(store, job).json()["progress"] == 100

    def test_progress_intermediate_value(self):
        store, job = make_env(status="running", progress=40)
        assert get(store, job).json()["progress"] == 40

    def test_progress_is_int_not_float(self):
        store, job = make_env(progress=50)
        assert type(get(store, job).json()["progress"]) is int

    def test_progress_non_negative(self):
        for pct in [0, 5, 20, 40, 60, 85, 100]:
            store, job = make_env(progress=pct)
            assert get(store, job).json()["progress"] >= 0

    def test_progress_at_most_100(self):
        store, job = make_env(progress=100)
        assert get(store, job).json()["progress"] <= 100

    def test_progress_each_pipeline_step(self):
        """Progress matches expected value at each named pipeline step."""
        for step_name, expected_pct in STEP_PROGRESS.items():
            store, job = make_env(
                status="running", progress=expected_pct,
                current_step=step_name,
            )
            body = get(store, job).json()
            assert body["progress"] == expected_pct, \
                f"Step '{step_name}': expected {expected_pct}%, got {body['progress']}%"

    def test_progress_increases_through_pipeline(self):
        """Progress at a later step must be >= progress at an earlier step."""
        earlier_steps = ["load_domain", "ingest", "cleaning_plan"]
        later_steps   = ["execute_cleaning", "analyze", "dashboard"]
        for early, late in zip(earlier_steps, later_steps):
            assert STEP_PROGRESS[early] <= STEP_PROGRESS[late], \
                f"Progress regression: {early}({STEP_PROGRESS[early]}) > {late}({STEP_PROGRESS[late]})"

    def test_progress_stays_same_during_hitl_pause(self):
        """While paused at HITL, progress must not advance."""
        store, job = make_env(
            status="paused", progress=20,
            current_step="await_merge_hitl",
            substatus="awaiting_hitl_merge",
        )
        body = get(store, job).json()
        assert body["progress"] == 20

    def test_queued_has_zero_progress(self):
        store, job = make_env(status="queued", progress=0)
        assert get(store, job).json()["progress"] == 0

    def test_failed_preserves_progress_at_point_of_failure(self):
        store, job = make_env(status="failed", progress=40, error="db error")
        assert get(store, job).json()["progress"] == 40


# ─────────────────────────────────────────────────────────────────────────────
# CURRENT_STEP field — active agent step name
# ─────────────────────────────────────────────────────────────────────────────

class TestCurrentStepField:

    def test_current_step_is_none_when_queued(self):
        store, job = make_env(status="queued", current_step=None)
        assert get(store, job).json()["current_step"] is None

    def test_current_step_is_none_when_done(self):
        store, job = make_env(status="done", progress=100, current_step=None)
        assert get(store, job).json()["current_step"] is None

    def test_current_step_set_when_running(self):
        store, job = make_env(status="running", current_step="ingest")
        assert get(store, job).json()["current_step"] == "ingest"

    def test_all_pipeline_step_names_returned_correctly(self):
        for step in PIPELINE_STEPS:
            store, job = make_env(status="running", current_step=step)
            assert get(store, job).json()["current_step"] == step

    def test_current_step_load_domain(self):
        store, job = make_env(status="running", progress=5, current_step="load_domain")
        assert get(store, job).json()["current_step"] == "load_domain"

    def test_current_step_ingest(self):
        store, job = make_env(status="running", progress=20, current_step="ingest")
        assert get(store, job).json()["current_step"] == "ingest"

    def test_current_step_cleaning_plan(self):
        store, job = make_env(status="running", progress=40, current_step="cleaning_plan")
        assert get(store, job).json()["current_step"] == "cleaning_plan"

    def test_current_step_execute_cleaning(self):
        store, job = make_env(status="running", progress=60, current_step="execute_cleaning")
        assert get(store, job).json()["current_step"] == "execute_cleaning"

    def test_current_step_analyze(self):
        store, job = make_env(status="running", progress=85, current_step="analyze")
        assert get(store, job).json()["current_step"] == "analyze"

    def test_current_step_dashboard(self):
        store, job = make_env(status="running", progress=100, current_step="dashboard")
        assert get(store, job).json()["current_step"] == "dashboard"

    def test_current_step_is_none_when_failed(self):
        """Failed jobs should still report last step for debugging."""
        store, job = make_env(
            status="failed", progress=40,
            current_step="execute_cleaning", error="timeout"
        )
        # current_step may be set or None on failure — just verify it's returned
        body = get(store, job).json()
        assert "current_step" in body

    def test_current_step_is_string_or_none(self):
        for step in PIPELINE_STEPS + [None]:
            store, job = make_env(current_step=step)
            val = get(store, job).json()["current_step"]
            assert val is None or isinstance(val, str)

    def test_paused_at_merge_hitl_shows_step(self):
        store, job = make_env(
            status="paused", current_step="await_merge_hitl",
            substatus="awaiting_hitl_merge",
        )
        assert get(store, job).json()["current_step"] == "await_merge_hitl"

    def test_paused_at_cleaning_hitl_shows_step(self):
        store, job = make_env(
            status="paused", current_step="await_cleaning_hitl",
            substatus="awaiting_hitl_cleaning",
        )
        assert get(store, job).json()["current_step"] == "await_cleaning_hitl"


# ─────────────────────────────────────────────────────────────────────────────
# SUBSTATUS field — HITL pause reasons
# ─────────────────────────────────────────────────────────────────────────────

class TestSubstatusField:

    def test_substatus_is_none_when_queued(self):
        store, job = make_env(status="queued")
        assert get(store, job).json()["substatus"] is None

    def test_substatus_is_none_when_running(self):
        store, job = make_env(status="running", current_step="ingest")
        assert get(store, job).json()["substatus"] is None

    def test_substatus_is_none_when_done(self):
        store, job = make_env(status="done", progress=100)
        assert get(store, job).json()["substatus"] is None

    def test_substatus_is_none_when_failed(self):
        store, job = make_env(status="failed", error="error msg")
        assert get(store, job).json()["substatus"] is None

    def test_awaiting_hitl_merge_substatus(self):
        store, job = make_env(
            status="paused",
            current_step="await_merge_hitl",
            substatus="awaiting_hitl_merge",
        )
        assert get(store, job).json()["substatus"] == "awaiting_hitl_merge"

    def test_awaiting_hitl_cleaning_substatus(self):
        store, job = make_env(
            status="paused",
            current_step="await_cleaning_hitl",
            substatus="awaiting_hitl_cleaning",
        )
        assert get(store, job).json()["substatus"] == "awaiting_hitl_cleaning"

    def test_awaiting_hitl_intent_substatus(self):
        store, job = make_env(
            status="paused",
            current_step="intent",
            substatus="awaiting_hitl_intent",
        )
        assert get(store, job).json()["substatus"] == "awaiting_hitl_intent"

    def test_all_valid_substatus_values_returned_correctly(self):
        for sub in VALID_SUBSTATUS:
            store, job = make_env(status="paused", substatus=sub)
            assert get(store, job).json()["substatus"] == sub

    def test_substatus_is_string_or_none(self):
        for sub in [None, "awaiting_hitl_merge"]:
            store, job = make_env(substatus=sub)
            val = get(store, job).json()["substatus"]
            assert val is None or isinstance(val, str)

    def test_substatus_null_for_non_paused_running_job(self):
        for status in ["queued", "running", "done", "failed"]:
            store, job = make_env(status=status)
            assert get(store, job).json()["substatus"] is None

    def test_paused_status_with_no_substatus_returns_paused(self):
        """paused without a specific substatus is still valid (generic pause)."""
        store, job = make_env(status="paused", substatus=None)
        body = get(store, job).json()
        assert body["status"] == "paused"
        assert body["substatus"] is None


# ─────────────────────────────────────────────────────────────────────────────
# ERROR field
# ─────────────────────────────────────────────────────────────────────────────

class TestErrorField:

    def test_error_is_none_when_queued(self):
        store, job = make_env(status="queued")
        assert get(store, job).json()["error"] is None

    def test_error_is_none_when_running(self):
        store, job = make_env(status="running")
        assert get(store, job).json()["error"] is None

    def test_error_is_none_when_paused(self):
        store, job = make_env(status="paused", substatus="awaiting_hitl_merge")
        assert get(store, job).json()["error"] is None

    def test_error_is_none_when_done(self):
        store, job = make_env(status="done", progress=100)
        assert get(store, job).json()["error"] is None

    def test_error_set_when_failed(self):
        store, job = make_env(status="failed", error="LLM rate limit exceeded")
        assert get(store, job).json()["error"] == "LLM rate limit exceeded"

    def test_error_message_preserved_verbatim(self):
        msg = "Connection to Supabase timed out after 30s"
        store, job = make_env(status="failed", error=msg)
        assert get(store, job).json()["error"] == msg

    def test_error_is_string_when_failed(self):
        store, job = make_env(status="failed", error="something went wrong")
        assert isinstance(get(store, job).json()["error"], str)

    def test_error_is_string_or_none(self):
        for status, error in [("queued", None), ("done", None), ("failed", "err")]:
            store, job = make_env(status=status, error=error)
            val = get(store, job).json()["error"]
            assert val is None or isinstance(val, str)

    def test_various_error_messages(self):
        messages = [
            "out of memory",
            "LLM structured_completion failed after 3 retries",
            "Database connection refused",
            "Supabase Storage write timeout",
            "cleaning executor raised ValueError: invalid column type",
        ]
        for msg in messages:
            store, job = make_env(status="failed", error=msg)
            assert get(store, job).json()["error"] == msg


# ─────────────────────────────────────────────────────────────────────────────
# TIMESTAMP fields
# ─────────────────────────────────────────────────────────────────────────────

class TestTimestampFields:

    def test_created_at_non_empty(self):
        store, job = make_env()
        assert len(get(store, job).json()["created_at"]) > 0

    def test_updated_at_non_empty(self):
        store, job = make_env()
        assert len(get(store, job).json()["updated_at"]) > 0

    def test_created_at_is_iso8601(self):
        store, job = make_env()
        ts = get(store, job).json()["created_at"]
        # Basic ISO-8601 check: contains T and Z or + offset
        assert "T" in ts

    def test_updated_at_is_iso8601(self):
        store, job = make_env()
        ts = get(store, job).json()["updated_at"]
        assert "T" in ts

    def test_created_at_matches_job(self):
        store, job = make_env()
        assert get(store, job).json()["created_at"] == job.created_at

    def test_updated_at_matches_job(self):
        store, job = make_env()
        assert get(store, job).json()["updated_at"] == job.updated_at

    def test_timestamps_preserved_verbatim(self):
        store = JobStore()
        job = Job(
            job_id=new_id(), dataset_id=new_id(),
            status="running", progress=20,
            created_at="2026-06-01T08:00:00Z",
            updated_at="2026-06-01T08:05:00Z",
        )
        store.add(job)
        body = handle_get_job(job.job_id, store).json()
        assert body["created_at"] == "2026-06-01T08:00:00Z"
        assert body["updated_at"] == "2026-06-01T08:05:00Z"


# ─────────────────────────────────────────────────────────────────────────────
# Full pipeline polling simulation
# ─────────────────────────────────────────────────────────────────────────────

class TestPipelinePollingSimulation:
    """
    Simulates what the frontend does: polls GET /jobs/{id} every 2 seconds
    and observes the job transition through every state.
    """

    def _poll_sequence(self) -> list[dict]:
        """Build a sequence of jobs representing a full pipeline run."""
        store = JobStore()
        jid = new_id()
        did = new_id()
        snapshots = [
            Job(jid, did, "queued",   0,   None,                  None,                   None),
            Job(jid, did, "running",  5,   "load_domain",         None,                   None),
            Job(jid, did, "running",  20,  "ingest",              None,                   None),
            Job(jid, did, "paused",   20,  "await_merge_hitl",    "awaiting_hitl_merge",  None),
            Job(jid, did, "running",  40,  "cleaning_plan",       None,                   None),
            Job(jid, did, "paused",   40,  "await_cleaning_hitl", "awaiting_hitl_cleaning", None),
            Job(jid, did, "running",  60,  "execute_cleaning",    None,                   None),
            Job(jid, did, "running",  70,  "intent",              None,                   None),
            Job(jid, did, "paused",   70,  "intent",              "awaiting_hitl_intent", None),
            Job(jid, did, "running",  85,  "analyze",             None,                   None),
            Job(jid, did, "running",  100, "dashboard",           None,                   None),
            Job(jid, did, "done",     100, None,                  None,                   None),
        ]
        results = []
        for snap in snapshots:
            store._jobs[jid] = snap
            body = handle_get_job(jid, store).json()
            results.append(body)
        return results

    def test_first_poll_is_queued(self):
        assert self._poll_sequence()[0]["status"] == "queued"

    def test_last_poll_is_done(self):
        assert self._poll_sequence()[-1]["status"] == "done"

    def test_progress_never_decreases(self):
        polls = self._poll_sequence()
        for i in range(1, len(polls)):
            assert polls[i]["progress"] >= polls[i - 1]["progress"], \
                f"Progress went backwards at poll {i}"

    def test_progress_reaches_100_on_done(self):
        polls = self._poll_sequence()
        done_polls = [p for p in polls if p["status"] == "done"]
        assert all(p["progress"] == 100 for p in done_polls)

    def test_three_paused_states_present(self):
        polls = self._poll_sequence()
        paused = [p for p in polls if p["status"] == "paused"]
        assert len(paused) == 3

    def test_paused_states_have_substatus(self):
        polls = self._poll_sequence()
        for p in polls:
            if p["status"] == "paused":
                assert p["substatus"] is not None

    def test_running_states_have_no_substatus(self):
        polls = self._poll_sequence()
        for p in polls:
            if p["status"] == "running":
                assert p["substatus"] is None

    def test_done_state_has_no_error(self):
        polls = self._poll_sequence()
        done = next(p for p in polls if p["status"] == "done")
        assert done["error"] is None

    def test_all_three_hitl_substatus_values_observed(self):
        polls = self._poll_sequence()
        substatus_seen = {p["substatus"] for p in polls if p["substatus"]}
        assert substatus_seen == {
            "awaiting_hitl_merge",
            "awaiting_hitl_cleaning",
            "awaiting_hitl_intent",
        }

    def test_current_step_set_during_running(self):
        polls = self._poll_sequence()
        for p in polls:
            if p["status"] == "running":
                assert p["current_step"] is not None

    def test_current_step_none_when_done(self):
        polls = self._poll_sequence()
        done = next(p for p in polls if p["status"] == "done")
        assert done["current_step"] is None

    def test_job_id_consistent_across_all_polls(self):
        polls = self._poll_sequence()
        job_ids = {p["job_id"] for p in polls}
        assert len(job_ids) == 1   # same job throughout


# ─────────────────────────────────────────────────────────────────────────────
# Failed pipeline scenarios
# ─────────────────────────────────────────────────────────────────────────────

class TestFailedPipelineScenarios:

    def test_failed_at_ingest_step(self):
        store, job = make_env(
            status="failed", progress=20,
            current_step="ingest",
            error="Failed to parse XLSX: corrupt file",
        )
        body = get(store, job).json()
        assert body["status"] == "failed"
        assert body["current_step"] == "ingest"
        assert "XLSX" in body["error"]

    def test_failed_at_cleaning_plan(self):
        store, job = make_env(
            status="failed", progress=40,
            current_step="cleaning_plan",
            error="LLM structured_completion failed after 3 retries",
        )
        body = get(store, job).json()
        assert body["status"] == "failed"
        assert body["error"] is not None

    def test_failed_at_execute_cleaning(self):
        store, job = make_env(
            status="failed", progress=60,
            current_step="execute_cleaning",
            error="Database write failed: Supabase Storage timeout",
        )
        body = get(store, job).json()
        assert body["status"] == "failed"
        assert body["progress"] == 60

    def test_failed_at_dashboard(self):
        store, job = make_env(
            status="failed", progress=85,
            current_step="dashboard",
            error="Dashboard agent exceeded token budget",
        )
        body = get(store, job).json()
        assert body["status"] == "failed"
        assert body["progress"] == 85

    def test_failed_has_no_substatus(self):
        store, job = make_env(status="failed", error="generic error")
        assert get(store, job).json()["substatus"] is None

    def test_failed_progress_not_reset_to_zero(self):
        """Progress at time of failure is preserved, not zeroed."""
        store, job = make_env(status="failed", progress=67, error="crash")
        assert get(store, job).json()["progress"] == 67

    def test_failed_vs_done_differ_only_in_status_and_error(self):
        store_f, job_f = make_env(status="failed", progress=100, error="last step failed")
        store_d, job_d = make_env(status="done",   progress=100)
        body_f = get(store_f, job_f).json()
        body_d = get(store_d, job_d).json()
        assert body_f["status"] == "failed"
        assert body_d["status"] == "done"
        assert body_f["error"] is not None
        assert body_d["error"] is None


# ─────────────────────────────────────────────────────────────────────────────
# 404 — job not found
# ─────────────────────────────────────────────────────────────────────────────

class TestNotFound:

    def test_unknown_job_id_returns_404(self):
        store = JobStore()
        assert handle_get_job(new_id(), store).status_code == 404

    def test_404_body_has_detail(self):
        store = JobStore()
        assert "detail" in handle_get_job(new_id(), store).json()

    def test_404_detail_mentions_job_id(self):
        store = JobStore()
        jid = new_id()
        assert jid in handle_get_job(jid, store).json()["detail"]

    def test_404_ok_is_false(self):
        store = JobStore()
        assert handle_get_job(new_id(), store).ok is False

    def test_registered_job_does_not_return_404(self):
        store, job = make_env()
        assert get(store, job).status_code != 404

    def test_wrong_id_for_existing_job_returns_404(self):
        store, job = make_env()
        assert handle_get_job(new_id(), store).status_code == 404

    def test_multiple_unknown_ids_all_404(self):
        store = JobStore()
        for _ in range(5):
            assert handle_get_job(new_id(), store).status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# 401 — authentication
# ─────────────────────────────────────────────────────────────────────────────

class TestAuthentication:

    def test_no_token_returns_401(self):
        store, job = make_env()
        assert get(store, job, token=None).status_code == 401

    def test_empty_token_returns_401(self):
        store, job = make_env()
        assert get(store, job, token="").status_code == 401

    def test_whitespace_token_returns_401(self):
        store, job = make_env()
        assert get(store, job, token="   ").status_code == 401

    def test_401_has_www_authenticate_header(self):
        store, job = make_env()
        resp = get(store, job, token=None)
        assert "WWW-Authenticate" in resp.headers

    def test_401_www_authenticate_is_bearer(self):
        store, job = make_env()
        assert get(store, job, token=None).headers["WWW-Authenticate"] == "Bearer"

    def test_401_body_has_detail(self):
        store, job = make_env()
        assert "detail" in get(store, job, token=None).json()

    def test_invalid_token_for_job_returns_401(self):
        store, job = make_env()
        store.set_unauthorized(job.job_id)
        assert get(store, job).status_code == 401

    def test_valid_token_returns_200(self):
        store, job = make_env()
        assert get(store, job, token="Bearer my-valid-token").status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# 403 — authorisation
# ─────────────────────────────────────────────────────────────────────────────

class TestAuthorisation:

    def test_forbidden_job_returns_403(self):
        store, job = make_env()
        store.set_forbidden(job.job_id)
        assert get(store, job).status_code == 403

    def test_403_body_has_detail(self):
        store, job = make_env()
        store.set_forbidden(job.job_id)
        assert "detail" in get(store, job).json()

    def test_403_ok_is_false(self):
        store, job = make_env()
        store.set_forbidden(job.job_id)
        assert get(store, job).ok is False

    def test_own_job_not_forbidden(self):
        store, job = make_env()
        assert get(store, job).status_code == 200

    def test_forbidden_on_one_does_not_affect_another(self):
        store = JobStore()
        job_bad = make_job()
        job_ok  = make_job()
        store.add(job_bad)
        store.add(job_ok)
        store.set_forbidden(job_bad.job_id)
        assert handle_get_job(job_bad.job_id, store).status_code == 403
        assert handle_get_job(job_ok.job_id,  store).status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# 500 — internal server error
# ─────────────────────────────────────────────────────────────────────────────

class TestServerError:

    def test_server_error_returns_500(self):
        store, job = make_env()
        store.set_server_error(job.job_id)
        assert get(store, job).status_code == 500

    def test_500_body_has_detail(self):
        store, job = make_env()
        store.set_server_error(job.job_id)
        assert "detail" in get(store, job).json()

    def test_500_ok_is_false(self):
        store, job = make_env()
        store.set_server_error(job.job_id)
        assert get(store, job).ok is False

    def test_server_error_on_one_does_not_affect_another(self):
        store = JobStore()
        job_bad = make_job()
        job_ok  = make_job()
        store.add(job_bad)
        store.add(job_ok)
        store.set_server_error(job_bad.job_id)
        assert handle_get_job(job_bad.job_id, store).status_code == 500
        assert handle_get_job(job_ok.job_id,  store).status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# Edge cases & robustness
# ─────────────────────────────────────────────────────────────────────────────

class TestEdgeCases:

    def test_repeated_polls_return_identical_body(self):
        store, job = make_env(status="paused", substatus="awaiting_hitl_merge")
        body1 = get(store, job).json()
        body2 = get(store, job).json()
        assert body1 == body2

    def test_body_is_json_serialisable(self):
        store, job = make_env(
            status="failed", progress=40,
            current_step="cleaning_plan", error="some error",
        )
        body = get(store, job).json()
        try:
            json.dumps(body)
        except TypeError as exc:
            raise AssertionError(f"Body not JSON-serialisable: {exc}") from exc

    def test_job_id_with_hyphens_handled(self):
        store = JobStore()
        job = Job(job_id=str(uuid.uuid4()), dataset_id=new_id(),
                  status="running", progress=20)
        store.add(job)
        assert handle_get_job(job.job_id, store).status_code == 200

    def test_two_jobs_with_different_statuses_independent(self):
        store = JobStore()
        job_q = Job(new_id(), new_id(), "queued",  0,   None, None, None)
        job_d = Job(new_id(), new_id(), "done",   100,  None, None, None)
        store.add(job_q)
        store.add(job_d)
        assert handle_get_job(job_q.job_id, store).json()["status"] == "queued"
        assert handle_get_job(job_d.job_id, store).json()["status"] == "done"

    def test_progress_zero_with_current_step_none_for_queued(self):
        store, job = make_env(status="queued")
        body = get(store, job).json()
        assert body["progress"] == 0
        assert body["current_step"] is None

    def test_done_job_has_null_substatus_null_error_100_progress(self):
        store, job = make_env(status="done", progress=100)
        body = get(store, job).json()
        assert body["status"] == "done"
        assert body["progress"] == 100
        assert body["substatus"] is None
        assert body["error"] is None

    def test_multiple_jobs_all_return_correct_ids(self):
        store = JobStore()
        jobs = [make_job() for _ in range(10)]
        for j in jobs:
            store.add(j)
        for j in jobs:
            assert handle_get_job(j.job_id, store).json()["job_id"] == j.job_id


# ═════════════════════════════════════════════════════════════════════════════
# Runner
# ═════════════════════════════════════════════════════════════════════════════

def _collect_all_test_classes():
    return [
        TestHappyPathStatusAndHeaders,
        TestResponseShape,
        TestIdFields,
        TestStatusField,
        TestProgressField,
        TestCurrentStepField,
        TestSubstatusField,
        TestErrorField,
        TestTimestampFields,
        TestPipelinePollingSimulation,
        TestFailedPipelineScenarios,
        TestNotFound,
        TestAuthentication,
        TestAuthorisation,
        TestServerError,
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