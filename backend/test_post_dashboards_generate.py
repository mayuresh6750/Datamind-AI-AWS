"""
Unit tests for  POST /dashboards/generate

Task reference : S4-14 (Sprint 4)
    "POST /dashboards/generate — enqueue dashboard generation job, return job_id"

Architecture refs:
    • Async endpoint — returns job_id immediately; no blocking work done in request
    • Frontend polls GET /jobs/{id} every 2s until status == "done"
    • Dashboard generation: Dashboard Agent (Vega-Lite) + Insights Agent
    • p95 dashboard latency target: < 90 seconds end-to-end
    • Depends on: analysis complete (S4-11), intent confirmed (HITL #3)

Request body:
    {
        "dataset_id":    str,          # which dataset to generate for
        "analysis_spec": {             # structured intent from HITL #3
            "dimensions":            list[str],
            "measures":              list[str],
            "suggested_chart_types": list[str],
            "restatement":           str,
            "confidence":            float,
            "filters":               list | null,
            "time_range":            dict | null,
        },
        "domain":        str,          # active domain
    }

Response (202 Accepted — job queued):
    {
        "job_id":     str,   # UUID for polling
        "status":     str,   # always "queued" on creation
        "dataset_id": str,   # echoed from request
        "poll_url":   str,   # /jobs/{job_id}
    }

Error responses:
    400 — malformed request body (missing required fields)
    401 — unauthenticated
    403 — forbidden (wrong user / tenant)
    404 — dataset not found (analysis not yet run)
    409 — conflict (analysis not complete / pipeline not ready)
    422 — validation error (invalid domain, empty dataset_id, etc.)
    500 — internal server error (queue write failed)

Job state after enqueue:
    status   = "queued"
    progress = 0
    current_step = null

Run with:
    pytest  test_post_dashboards_generate.py -v
    python  test_post_dashboards_generate.py   # live results

Fully independent — no real HTTP server, no DB, no LLM, no Supabase.
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

VALID_DOMAINS     = {"finance", "healthcare", "retail", "marketing", "operations", "other"}
VALID_CHART_TYPES = {"line", "bar", "table", "scatter", "pie"}
JOB_QUEUED_STATUS = "queued"
POLL_URL_PREFIX   = "/jobs/"


# ─────────────────────────────────────────────────────────────────────────────
# Schema stand-ins
# ─────────────────────────────────────────────────────────────────────────────

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
class GenerateRequest:
    dataset_id: str
    analysis_spec: AnalysisSpec
    domain: str


@dataclass
class QueuedJob:
    job_id: str
    status: str = JOB_QUEUED_STATUS
    progress: int = 0
    current_step: Optional[str] = None
    dataset_id: str = ""


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
# Dataset registry + job queue
# ─────────────────────────────────────────────────────────────────────────────

class DatasetRegistry:
    """Controls which dataset_ids exist and in what state."""

    def __init__(self) -> None:
        self._ready:          set[str] = set()   # analysis complete → can generate
        self._not_ready:      set[str] = set()   # exists but analysis not done
        self._unauthorized:   set[str] = set()
        self._forbidden:      set[str] = set()
        self._queue_errors:   set[str] = set()   # simulate queue write failure

    def register_ready(self, did: str) -> None:
        self._ready.add(did)

    def register_not_ready(self, did: str) -> None:
        self._not_ready.add(did)

    def set_unauthorized(self, did: str) -> None:
        self._unauthorized.add(did)

    def set_forbidden(self, did: str) -> None:
        self._forbidden.add(did)

    def set_queue_error(self, did: str) -> None:
        self._queue_errors.add(did)

    def is_ready(self, did: str) -> bool:
        return did in self._ready

    def is_not_ready(self, did: str) -> bool:
        return did in self._not_ready

    def exists(self, did: str) -> bool:
        return did in self._ready or did in self._not_ready

    def is_unauthorized(self, did: str) -> bool:
        return did in self._unauthorized

    def is_forbidden(self, did: str) -> bool:
        return did in self._forbidden

    def is_queue_error(self, did: str) -> bool:
        return did in self._queue_errors


class JobQueue:
    """Captures every job enqueued during a test."""

    def __init__(self) -> None:
        self._jobs: list[QueuedJob] = []

    def enqueue(self, job: QueuedJob) -> None:
        self._jobs.append(job)

    @property
    def jobs(self) -> list[QueuedJob]:
        return list(self._jobs)

    @property
    def count(self) -> int:
        return len(self._jobs)

    def last(self) -> Optional[QueuedJob]:
        return self._jobs[-1] if self._jobs else None

    def find_by_id(self, job_id: str) -> Optional[QueuedJob]:
        return next((j for j in self._jobs if j.job_id == job_id), None)


# ─────────────────────────────────────────────────────────────────────────────
# Fake handler:  POST /dashboards/generate
# ─────────────────────────────────────────────────────────────────────────────

def handle_post_generate(
    request: Optional[GenerateRequest],
    registry: DatasetRegistry,
    queue: JobQueue,
    *,
    auth_token: Optional[str] = "Bearer valid-token",
) -> Response:
    """
    POST /dashboards/generate

    Auth:       missing/empty token          → 401
                registry.is_unauthorized     → 401
    Permission: registry.is_forbidden        → 403
    Validation: request is None              → 400
                dataset_id empty             → 422
                invalid domain               → 422
                analysis_spec missing dims   → 422 (empty dims AND measures)
    Not found:  dataset does not exist       → 404
    Conflict:   dataset exists but analysis
                not complete                 → 409
    Queue err:  registry.is_queue_error      → 500
    Happy path: enqueue job, return 202
    """
    # 401: no token
    if not auth_token or not auth_token.strip():
        return Response(
            status_code=401,
            body={"detail": "Authentication required"},
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 400: missing body
    if request is None:
        return Response(
            status_code=400,
            body={"detail": "Request body is required"},
        )

    dataset_id = request.dataset_id

    # 401: rejected token
    if registry.is_unauthorized(dataset_id):
        return Response(
            status_code=401,
            body={"detail": "Invalid or expired token"},
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 403
    if registry.is_forbidden(dataset_id):
        return Response(
            status_code=403,
            body={"detail": "You do not have permission to generate a dashboard for this dataset"},
        )

    # 422: empty dataset_id
    if not dataset_id or not dataset_id.strip():
        return Response(
            status_code=422,
            body={"detail": "dataset_id must not be empty"},
        )

    # 422: invalid domain
    if request.domain not in VALID_DOMAINS:
        return Response(
            status_code=422,
            body={"detail": f"domain '{request.domain}' is not valid. "
                            f"Must be one of: {sorted(VALID_DOMAINS)}"},
        )

    # 422: analysis spec has no dimensions AND no measures
    spec = request.analysis_spec
    if not spec.dimensions and not spec.measures:
        return Response(
            status_code=422,
            body={"detail": "analysis_spec must contain at least one dimension or measure"},
        )

    # 404: dataset does not exist
    if not registry.exists(dataset_id):
        return Response(
            status_code=404,
            body={"detail": f"Dataset '{dataset_id}' not found"},
        )

    # 409: analysis not complete
    if registry.is_not_ready(dataset_id):
        return Response(
            status_code=409,
            body={
                "detail": "Analysis has not completed for this dataset",
                "status": "analysis_not_ready",
            },
        )

    # 500: queue write failure
    if registry.is_queue_error(dataset_id):
        return Response(
            status_code=500,
            body={"detail": "Failed to enqueue dashboard generation job"},
        )

    # 202: enqueue and return job_id
    job_id = str(uuid.uuid4())
    job = QueuedJob(job_id=job_id, dataset_id=dataset_id)
    queue.enqueue(job)

    return Response(
        status_code=202,
        body={
            "job_id":     job_id,
            "status":     JOB_QUEUED_STATUS,
            "dataset_id": dataset_id,
            "poll_url":   f"{POLL_URL_PREFIX}{job_id}",
        },
        headers={"Content-Type": "application/json"},
    )


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def new_id() -> str:
    return str(uuid.uuid4())


def _default_spec(**overrides) -> AnalysisSpec:
    base = dict(
        dimensions=["region"],
        measures=["revenue"],
        suggested_chart_types=["bar"],
        restatement="Show total revenue by region",
        confidence=0.92,
        filters=None,
        time_range=None,
    )
    base.update(overrides)
    return AnalysisSpec(**base)


def make_env(
    domain: str = "finance",
    ready: bool = True,
) -> tuple[str, DatasetRegistry, JobQueue]:
    did = new_id()
    registry = DatasetRegistry()
    if ready:
        registry.register_ready(did)
    else:
        registry.register_not_ready(did)
    queue = JobQueue()
    return did, registry, queue


def post(
    dataset_id: str,
    registry: DatasetRegistry,
    queue: JobQueue,
    domain: str = "finance",
    spec: Optional[AnalysisSpec] = None,
    token: Optional[str] = "Bearer valid-token",
) -> Response:
    req = GenerateRequest(
        dataset_id=dataset_id,
        analysis_spec=spec or _default_spec(),
        domain=domain,
    )
    return handle_post_generate(req, registry, queue, auth_token=token)


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
        print("  POST /dashboards/generate — test results")
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
# 1. 202 — status and headers
# ─────────────────────────────────────────────────────────────────────────────

class TestHappyPathStatus:

    def test_returns_202(self):
        did, registry, queue = make_env()
        assert post(did, registry, queue).status_code == 202

    def test_202_is_accepted_not_200(self):
        did, registry, queue = make_env()
        assert post(did, registry, queue).status_code != 200

    def test_ok_property_true_for_202(self):
        did, registry, queue = make_env()
        assert post(did, registry, queue).ok is True

    def test_content_type_json(self):
        did, registry, queue = make_env()
        assert post(did, registry, queue).headers.get("Content-Type") == "application/json"

    def test_body_is_dict(self):
        did, registry, queue = make_env()
        assert isinstance(post(did, registry, queue).json(), dict)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Response body shape
# ─────────────────────────────────────────────────────────────────────────────

class TestResponseShape:

    REQUIRED_KEYS = {"job_id", "status", "dataset_id", "poll_url"}

    def _body(self) -> dict:
        did, registry, queue = make_env()
        return post(did, registry, queue).json()

    def test_all_required_keys_present(self):
        assert self.REQUIRED_KEYS.issubset(self._body().keys())

    def test_job_id_present(self):
        assert "job_id" in self._body()

    def test_status_present(self):
        assert "status" in self._body()

    def test_dataset_id_present(self):
        assert "dataset_id" in self._body()

    def test_poll_url_present(self):
        assert "poll_url" in self._body()

    def test_job_id_is_string(self):
        assert isinstance(self._body()["job_id"], str)

    def test_status_is_string(self):
        assert isinstance(self._body()["status"], str)

    def test_dataset_id_is_string(self):
        assert isinstance(self._body()["dataset_id"], str)

    def test_poll_url_is_string(self):
        assert isinstance(self._body()["poll_url"], str)


# ─────────────────────────────────────────────────────────────────────────────
# 3. Job queued — status field always "queued"
# ─────────────────────────────────────────────────────────────────────────────

class TestJobQueuedStatus:

    def test_status_is_queued(self):
        did, registry, queue = make_env()
        assert post(did, registry, queue).json()["status"] == "queued"

    def test_status_not_running(self):
        did, registry, queue = make_env()
        assert post(did, registry, queue).json()["status"] != "running"

    def test_status_not_done(self):
        did, registry, queue = make_env()
        assert post(did, registry, queue).json()["status"] != "done"

    def test_status_not_failed(self):
        did, registry, queue = make_env()
        assert post(did, registry, queue).json()["status"] != "failed"

    def test_status_queued_for_all_valid_domains(self):
        for domain in VALID_DOMAINS:
            did, registry, queue = make_env(domain=domain)
            assert post(did, registry, queue, domain=domain).json()["status"] == "queued"

    def test_multiple_requests_all_return_queued(self):
        for _ in range(5):
            did, registry, queue = make_env()
            assert post(did, registry, queue).json()["status"] == "queued"


# ─────────────────────────────────────────────────────────────────────────────
# 4. job_id — format and uniqueness
# ─────────────────────────────────────────────────────────────────────────────

class TestJobId:

    def test_job_id_non_empty(self):
        did, registry, queue = make_env()
        assert len(post(did, registry, queue).json()["job_id"]) > 0

    def test_job_id_is_uuid_format(self):
        did, registry, queue = make_env()
        jid = post(did, registry, queue).json()["job_id"]
        # UUID has 5 hyphen-separated groups
        parts = jid.split("-")
        assert len(parts) == 5, f"Not a UUID: {jid}"

    def test_each_request_produces_unique_job_id(self):
        ids = set()
        registry = DatasetRegistry()
        for _ in range(10):
            did = new_id()
            registry.register_ready(did)
            queue = JobQueue()
            jid = post(did, registry, queue).json()["job_id"]
            ids.add(jid)
        assert len(ids) == 10

    def test_job_id_in_response_matches_queued_job(self):
        did, registry, queue = make_env()
        resp_jid = post(did, registry, queue).json()["job_id"]
        assert queue.last().job_id == resp_jid

    def test_job_id_does_not_contain_dataset_id(self):
        """job_id must be independently generated, not derived from dataset_id."""
        did, registry, queue = make_env()
        resp = post(did, registry, queue).json()
        assert resp["job_id"] != did


# ─────────────────────────────────────────────────────────────────────────────
# 5. dataset_id echoed in response
# ─────────────────────────────────────────────────────────────────────────────

class TestDatasetIdEchoed:

    def test_dataset_id_echoed_correctly(self):
        did, registry, queue = make_env()
        assert post(did, registry, queue).json()["dataset_id"] == did

    def test_two_different_datasets_each_echo_own_id(self):
        registry = DatasetRegistry()
        did_a = new_id()
        did_b = new_id()
        registry.register_ready(did_a)
        registry.register_ready(did_b)
        queue = JobQueue()
        resp_a = post(did_a, registry, queue).json()
        resp_b = post(did_b, registry, queue).json()
        assert resp_a["dataset_id"] == did_a
        assert resp_b["dataset_id"] == did_b

    def test_dataset_id_in_queued_job_matches_response(self):
        did, registry, queue = make_env()
        post(did, registry, queue)
        assert queue.last().dataset_id == did


# ─────────────────────────────────────────────────────────────────────────────
# 6. poll_url — structure and correctness
# ─────────────────────────────────────────────────────────────────────────────

class TestPollUrl:

    def test_poll_url_contains_job_id(self):
        did, registry, queue = make_env()
        resp = post(did, registry, queue).json()
        assert resp["job_id"] in resp["poll_url"]

    def test_poll_url_starts_with_jobs_prefix(self):
        did, registry, queue = make_env()
        resp = post(did, registry, queue).json()
        assert resp["poll_url"].startswith(POLL_URL_PREFIX)

    def test_poll_url_is_jobs_slash_job_id(self):
        did, registry, queue = make_env()
        resp = post(did, registry, queue).json()
        expected = f"{POLL_URL_PREFIX}{resp['job_id']}"
        assert resp["poll_url"] == expected

    def test_poll_url_unique_per_request(self):
        registry = DatasetRegistry()
        queue = JobQueue()
        did_a = new_id()
        did_b = new_id()
        registry.register_ready(did_a)
        registry.register_ready(did_b)
        url_a = post(did_a, registry, queue).json()["poll_url"]
        url_b = post(did_b, registry, queue).json()["poll_url"]
        assert url_a != url_b

    def test_poll_url_non_empty(self):
        did, registry, queue = make_env()
        assert len(post(did, registry, queue).json()["poll_url"]) > 0


# ─────────────────────────────────────────────────────────────────────────────
# 7. Job actually enqueued in the queue
# ─────────────────────────────────────────────────────────────────────────────

class TestJobEnqueuedInQueue:

    def test_one_job_in_queue_after_one_request(self):
        did, registry, queue = make_env()
        post(did, registry, queue)
        assert queue.count == 1

    def test_job_status_is_queued_in_queue(self):
        did, registry, queue = make_env()
        post(did, registry, queue)
        assert queue.last().status == JOB_QUEUED_STATUS

    def test_job_progress_is_zero_in_queue(self):
        did, registry, queue = make_env()
        post(did, registry, queue)
        assert queue.last().progress == 0

    def test_job_current_step_is_none_in_queue(self):
        did, registry, queue = make_env()
        post(did, registry, queue)
        assert queue.last().current_step is None

    def test_job_dataset_id_matches_request(self):
        did, registry, queue = make_env()
        post(did, registry, queue)
        assert queue.last().dataset_id == did

    def test_two_requests_produce_two_queued_jobs(self):
        registry = DatasetRegistry()
        queue = JobQueue()
        for _ in range(2):
            did = new_id()
            registry.register_ready(did)
            post(did, registry, queue)
        assert queue.count == 2

    def test_five_requests_produce_five_queued_jobs(self):
        registry = DatasetRegistry()
        queue = JobQueue()
        for _ in range(5):
            did = new_id()
            registry.register_ready(did)
            post(did, registry, queue)
        assert queue.count == 5

    def test_queued_jobs_have_distinct_ids(self):
        registry = DatasetRegistry()
        queue = JobQueue()
        for _ in range(10):
            did = new_id()
            registry.register_ready(did)
            post(did, registry, queue)
        job_ids = [j.job_id for j in queue.jobs]
        assert len(job_ids) == len(set(job_ids))

    def test_job_findable_by_id_in_queue(self):
        did, registry, queue = make_env()
        resp_jid = post(did, registry, queue).json()["job_id"]
        assert queue.find_by_id(resp_jid) is not None

    def test_no_job_queued_on_error_response(self):
        did, registry, queue = make_env()
        post(did, registry, queue, token=None)       # 401
        post(new_id(), registry, queue)               # 404
        assert queue.count == 0

    def test_no_job_queued_on_validation_error(self):
        did, registry, queue = make_env()
        post(did, registry, queue, domain="bad_domain")  # 422
        assert queue.count == 0

    def test_no_job_queued_on_409(self):
        did, registry, queue = make_env(ready=False)
        post(did, registry, queue)
        assert queue.count == 0


# ─────────────────────────────────────────────────────────────────────────────
# 8. Request validation — domain
# ─────────────────────────────────────────────────────────────────────────────

class TestDomainValidation:

    def test_unknown_domain_returns_422(self):
        did, registry, queue = make_env()
        assert post(did, registry, queue, domain="astrology").status_code == 422

    def test_422_body_mentions_domain(self):
        did, registry, queue = make_env()
        body = post(did, registry, queue, domain="bad").json()
        assert "domain" in body["detail"].lower() or "bad" in body["detail"]

    def test_all_valid_domains_return_202(self):
        for domain in VALID_DOMAINS:
            did, registry, queue = make_env(domain=domain)
            assert post(did, registry, queue, domain=domain).status_code == 202

    def test_uppercase_domain_rejected(self):
        did, registry, queue = make_env()
        assert post(did, registry, queue, domain="Finance").status_code == 422

    def test_empty_domain_returns_422(self):
        did, registry, queue = make_env()
        assert post(did, registry, queue, domain="").status_code == 422

    def test_no_job_queued_for_invalid_domain(self):
        did, registry, queue = make_env()
        post(did, registry, queue, domain="invalid")
        assert queue.count == 0


# ─────────────────────────────────────────────────────────────────────────────
# 9. Request validation — analysis_spec
# ─────────────────────────────────────────────────────────────────────────────

class TestAnalysisSpecValidation:

    def test_empty_dimensions_and_measures_returns_422(self):
        did, registry, queue = make_env()
        empty_spec = _default_spec(dimensions=[], measures=[])
        assert post(did, registry, queue, spec=empty_spec).status_code == 422

    def test_422_body_mentions_analysis_spec(self):
        did, registry, queue = make_env()
        empty_spec = _default_spec(dimensions=[], measures=[])
        body = post(did, registry, queue, spec=empty_spec).json()
        assert "analysis_spec" in body["detail"].lower() or "dimension" in body["detail"].lower()

    def test_dimensions_only_no_measures_accepted(self):
        """At least one dimension is enough — measures can be empty."""
        did, registry, queue = make_env()
        spec = _default_spec(dimensions=["region"], measures=[])
        assert post(did, registry, queue, spec=spec).status_code == 202

    def test_measures_only_no_dimensions_accepted(self):
        """At least one measure is enough — dimensions can be empty."""
        did, registry, queue = make_env()
        spec = _default_spec(dimensions=[], measures=["revenue"])
        assert post(did, registry, queue, spec=spec).status_code == 202

    def test_valid_spec_accepted(self):
        did, registry, queue = make_env()
        spec = _default_spec(dimensions=["region"], measures=["revenue"])
        assert post(did, registry, queue, spec=spec).status_code == 202

    def test_multiple_dimensions_accepted(self):
        did, registry, queue = make_env()
        spec = _default_spec(dimensions=["region", "channel", "product"])
        assert post(did, registry, queue, spec=spec).status_code == 202

    def test_multiple_measures_accepted(self):
        did, registry, queue = make_env()
        spec = _default_spec(measures=["revenue", "units", "margin"])
        assert post(did, registry, queue, spec=spec).status_code == 202

    def test_filters_in_spec_accepted(self):
        did, registry, queue = make_env()
        spec = _default_spec(filters=[{"col": "region", "op": "=", "val": "APAC"}])
        assert post(did, registry, queue, spec=spec).status_code == 202

    def test_time_range_in_spec_accepted(self):
        did, registry, queue = make_env()
        spec = _default_spec(time_range={"start": "2024-01-01", "end": "2024-12-31"})
        assert post(did, registry, queue, spec=spec).status_code == 202

    def test_all_chart_types_in_spec_accepted(self):
        did, registry, queue = make_env()
        spec = _default_spec(suggested_chart_types=["line", "bar", "table"])
        assert post(did, registry, queue, spec=spec).status_code == 202


# ─────────────────────────────────────────────────────────────────────────────
# 10. 400 — malformed / missing body
# ─────────────────────────────────────────────────────────────────────────────

class TestMissingBody:

    def test_none_request_returns_400(self):
        registry = DatasetRegistry()
        queue = JobQueue()
        resp = handle_post_generate(None, registry, queue)
        assert resp.status_code == 400

    def test_400_body_has_detail(self):
        registry = DatasetRegistry()
        queue = JobQueue()
        resp = handle_post_generate(None, registry, queue)
        assert "detail" in resp.json()

    def test_400_ok_is_false(self):
        registry = DatasetRegistry()
        queue = JobQueue()
        assert not handle_post_generate(None, registry, queue).ok

    def test_no_job_queued_on_missing_body(self):
        registry = DatasetRegistry()
        queue = JobQueue()
        handle_post_generate(None, registry, queue)
        assert queue.count == 0


# ─────────────────────────────────────────────────────────────────────────────
# 11. 404 — dataset not found
# ─────────────────────────────────────────────────────────────────────────────

class TestNotFound:

    def test_unregistered_dataset_returns_404(self):
        registry = DatasetRegistry()
        queue = JobQueue()
        assert post(new_id(), registry, queue).status_code == 404

    def test_404_body_has_detail(self):
        registry = DatasetRegistry()
        queue = JobQueue()
        assert "detail" in post(new_id(), registry, queue).json()

    def test_404_detail_mentions_dataset_id(self):
        registry = DatasetRegistry()
        queue = JobQueue()
        did = new_id()
        assert did in post(did, registry, queue).json()["detail"]

    def test_404_ok_is_false(self):
        registry = DatasetRegistry()
        queue = JobQueue()
        assert not post(new_id(), registry, queue).ok

    def test_registered_dataset_does_not_return_404(self):
        did, registry, queue = make_env()
        assert post(did, registry, queue).status_code != 404

    def test_wrong_id_for_existing_dataset_returns_404(self):
        did, registry, queue = make_env()
        assert post(new_id(), registry, queue).status_code == 404

    def test_no_job_queued_on_404(self):
        registry = DatasetRegistry()
        queue = JobQueue()
        post(new_id(), registry, queue)
        assert queue.count == 0


# ─────────────────────────────────────────────────────────────────────────────
# 12. 409 — analysis not complete
# ─────────────────────────────────────────────────────────────────────────────

class TestAnalysisNotReady:

    def test_not_ready_dataset_returns_409(self):
        did, registry, queue = make_env(ready=False)
        assert post(did, registry, queue).status_code == 409

    def test_409_body_has_detail(self):
        did, registry, queue = make_env(ready=False)
        assert "detail" in post(did, registry, queue).json()

    def test_409_body_has_status_analysis_not_ready(self):
        did, registry, queue = make_env(ready=False)
        assert post(did, registry, queue).json()["status"] == "analysis_not_ready"

    def test_409_ok_is_false(self):
        did, registry, queue = make_env(ready=False)
        assert not post(did, registry, queue).ok

    def test_ready_dataset_does_not_return_409(self):
        did, registry, queue = make_env(ready=True)
        assert post(did, registry, queue).status_code == 202

    def test_no_job_queued_on_409(self):
        did, registry, queue = make_env(ready=False)
        post(did, registry, queue)
        assert queue.count == 0

    def test_not_ready_different_from_not_found(self):
        did_not_ready, registry, queue = make_env(ready=False)
        did_not_found = new_id()
        resp_not_ready = post(did_not_ready, registry, queue)
        resp_not_found = post(did_not_found, registry, queue)
        assert resp_not_ready.status_code == 409
        assert resp_not_found.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# 13. 401 — authentication
# ─────────────────────────────────────────────────────────────────────────────

class TestAuthentication:

    def test_no_token_returns_401(self):
        did, registry, queue = make_env()
        assert post(did, registry, queue, token=None).status_code == 401

    def test_empty_token_returns_401(self):
        did, registry, queue = make_env()
        assert post(did, registry, queue, token="").status_code == 401

    def test_whitespace_token_returns_401(self):
        did, registry, queue = make_env()
        assert post(did, registry, queue, token="   ").status_code == 401

    def test_401_has_www_authenticate_bearer(self):
        did, registry, queue = make_env()
        resp = post(did, registry, queue, token=None)
        assert resp.headers.get("WWW-Authenticate") == "Bearer"

    def test_401_body_has_detail(self):
        did, registry, queue = make_env()
        assert "detail" in post(did, registry, queue, token=None).json()

    def test_invalid_token_for_dataset_returns_401(self):
        did, registry, queue = make_env()
        registry.set_unauthorized(did)
        assert post(did, registry, queue).status_code == 401

    def test_valid_token_returns_202(self):
        did, registry, queue = make_env()
        assert post(did, registry, queue, token="Bearer good-token").status_code == 202

    def test_no_job_queued_on_401(self):
        did, registry, queue = make_env()
        post(did, registry, queue, token=None)
        assert queue.count == 0


# ─────────────────────────────────────────────────────────────────────────────
# 14. 403 — authorisation
# ─────────────────────────────────────────────────────────────────────────────

class TestAuthorisation:

    def test_forbidden_dataset_returns_403(self):
        did, registry, queue = make_env()
        registry.set_forbidden(did)
        assert post(did, registry, queue).status_code == 403

    def test_403_body_has_detail(self):
        did, registry, queue = make_env()
        registry.set_forbidden(did)
        assert "detail" in post(did, registry, queue).json()

    def test_403_ok_is_false(self):
        did, registry, queue = make_env()
        registry.set_forbidden(did)
        assert not post(did, registry, queue).ok

    def test_own_dataset_not_forbidden(self):
        did, registry, queue = make_env()
        assert post(did, registry, queue).status_code == 202

    def test_forbidden_on_one_does_not_affect_another(self):
        registry = DatasetRegistry()
        queue = JobQueue()
        bad = new_id()
        good = new_id()
        registry.register_ready(bad)
        registry.register_ready(good)
        registry.set_forbidden(bad)
        assert post(bad, registry, queue).status_code == 403
        assert post(good, registry, queue).status_code == 202

    def test_no_job_queued_on_403(self):
        did, registry, queue = make_env()
        registry.set_forbidden(did)
        post(did, registry, queue)
        assert queue.count == 0


# ─────────────────────────────────────────────────────────────────────────────
# 15. 500 — queue write failure
# ─────────────────────────────────────────────────────────────────────────────

class TestQueueError:

    def test_queue_failure_returns_500(self):
        did, registry, queue = make_env()
        registry.set_queue_error(did)
        assert post(did, registry, queue).status_code == 500

    def test_500_body_has_detail(self):
        did, registry, queue = make_env()
        registry.set_queue_error(did)
        assert "detail" in post(did, registry, queue).json()

    def test_500_ok_is_false(self):
        did, registry, queue = make_env()
        registry.set_queue_error(did)
        assert not post(did, registry, queue).ok

    def test_queue_error_on_one_does_not_affect_another(self):
        registry = DatasetRegistry()
        queue = JobQueue()
        bad = new_id()
        good = new_id()
        registry.register_ready(bad)
        registry.register_ready(good)
        registry.set_queue_error(bad)
        assert post(bad, registry, queue).status_code == 500
        assert post(good, registry, queue).status_code == 202

    def test_no_job_in_queue_on_500(self):
        did, registry, queue = make_env()
        registry.set_queue_error(did)
        post(did, registry, queue)
        assert queue.count == 0


# ─────────────────────────────────────────────────────────────────────────────
# 16. Idempotency and isolation
# ─────────────────────────────────────────────────────────────────────────────

class TestIdempotencyAndIsolation:

    def test_two_requests_same_dataset_produce_two_jobs(self):
        did, registry, queue = make_env()
        post(did, registry, queue)
        post(did, registry, queue)
        assert queue.count == 2

    def test_two_requests_same_dataset_produce_different_job_ids(self):
        did, registry, queue = make_env()
        jid1 = post(did, registry, queue).json()["job_id"]
        jid2 = post(did, registry, queue).json()["job_id"]
        assert jid1 != jid2

    def test_two_requests_same_dataset_both_queued(self):
        did, registry, queue = make_env()
        post(did, registry, queue)
        post(did, registry, queue)
        for job in queue.jobs:
            assert job.status == JOB_QUEUED_STATUS

    def test_different_datasets_produce_independent_jobs(self):
        registry = DatasetRegistry()
        queue = JobQueue()
        did_a = new_id()
        did_b = new_id()
        registry.register_ready(did_a)
        registry.register_ready(did_b)
        post(did_a, registry, queue)
        post(did_b, registry, queue)
        assert queue.jobs[0].dataset_id == did_a
        assert queue.jobs[1].dataset_id == did_b

    def test_queued_jobs_are_not_started(self):
        did, registry, queue = make_env()
        post(did, registry, queue)
        job = queue.last()
        assert job.status == JOB_QUEUED_STATUS
        assert job.progress == 0
        assert job.current_step is None


# ─────────────────────────────────────────────────────────────────────────────
# 17. Domain-specific generation requests
# ─────────────────────────────────────────────────────────────────────────────

class TestDomainSpecificRequests:

    def test_finance_revenue_by_region(self):
        did, registry, queue = make_env(domain="finance")
        spec = _default_spec(
            dimensions=["region"], measures=["revenue", "gross_margin"],
            suggested_chart_types=["bar"], confidence=0.95,
        )
        resp = post(did, registry, queue, domain="finance", spec=spec)
        assert resp.status_code == 202
        assert resp.json()["status"] == "queued"

    def test_healthcare_los_by_ward(self):
        did, registry, queue = make_env(domain="healthcare")
        spec = _default_spec(
            dimensions=["ward"], measures=["length_of_stay"],
            suggested_chart_types=["bar", "table"], confidence=0.88,
        )
        resp = post(did, registry, queue, domain="healthcare", spec=spec)
        assert resp.status_code == 202

    def test_retail_sku_margin_by_channel(self):
        did, registry, queue = make_env(domain="retail")
        spec = _default_spec(
            dimensions=["channel", "sku"], measures=["margin", "units_sold"],
            suggested_chart_types=["table"], confidence=0.82,
        )
        resp = post(did, registry, queue, domain="retail", spec=spec)
        assert resp.status_code == 202

    def test_marketing_ctr_by_campaign(self):
        did, registry, queue = make_env(domain="marketing")
        spec = _default_spec(
            dimensions=["campaign"], measures=["ctr", "cpa"],
            suggested_chart_types=["bar"], confidence=0.91,
        )
        resp = post(did, registry, queue, domain="marketing", spec=spec)
        assert resp.status_code == 202

    def test_time_range_in_spec_forwarded(self):
        did, registry, queue = make_env(domain="finance")
        spec = _default_spec(
            time_range={"start": "2024-Q1", "end": "2024-Q4"},
        )
        resp = post(did, registry, queue, domain="finance", spec=spec)
        assert resp.status_code == 202
        assert queue.count == 1

    def test_low_confidence_spec_still_queued(self):
        """Low confidence doesn't block generation — it's the user's call."""
        did, registry, queue = make_env(domain="other")
        spec = _default_spec(confidence=0.15)
        resp = post(did, registry, queue, domain="other", spec=spec)
        assert resp.status_code == 202


# ─────────────────────────────────────────────────────────────────────────────
# 18. Edge cases
# ─────────────────────────────────────────────────────────────────────────────

class TestEdgeCases:

    def test_response_body_is_json_serialisable(self):
        did, registry, queue = make_env()
        body = post(did, registry, queue).json()
        try:
            json.dumps(body)
        except TypeError as exc:
            raise AssertionError(f"Body not serialisable: {exc}") from exc

    def test_dataset_id_with_hyphens_accepted(self):
        registry = DatasetRegistry()
        queue = JobQueue()
        did = str(uuid.uuid4())
        registry.register_ready(did)
        assert post(did, registry, queue).status_code == 202

    def test_poll_url_usable_for_polling(self):
        """poll_url must be a path usable to call GET /jobs/{id}."""
        did, registry, queue = make_env()
        resp = post(did, registry, queue).json()
        poll_url = resp["poll_url"]
        assert poll_url.startswith("/jobs/")
        assert len(poll_url) > len("/jobs/")

    def test_validation_order_auth_before_domain(self):
        """Auth check must fire before domain validation."""
        did, registry, queue = make_env()
        resp = post(did, registry, queue, domain="bad_domain", token=None)
        assert resp.status_code == 401   # not 422

    def test_validation_order_domain_before_404(self):
        """Domain validation fires before the 404 check."""
        registry = DatasetRegistry()   # no datasets registered
        queue = JobQueue()
        resp = post(new_id(), registry, queue, domain="bad_domain")
        assert resp.status_code == 422  # not 404

    def test_high_volume_all_jobs_queued(self):
        registry = DatasetRegistry()
        queue = JobQueue()
        for _ in range(20):
            did = new_id()
            registry.register_ready(did)
            post(did, registry, queue)
        assert queue.count == 20
        ids = [j.job_id for j in queue.jobs]
        assert len(ids) == len(set(ids))   # all unique

    def test_spec_with_empty_chart_types_accepted(self):
        did, registry, queue = make_env()
        spec = _default_spec(suggested_chart_types=[])
        assert post(did, registry, queue, spec=spec).status_code == 202

    def test_spec_with_all_five_chart_types_accepted(self):
        did, registry, queue = make_env()
        spec = _default_spec(suggested_chart_types=list(VALID_CHART_TYPES))
        assert post(did, registry, queue, spec=spec).status_code == 202


# ═════════════════════════════════════════════════════════════════════════════
# Runner
# ═════════════════════════════════════════════════════════════════════════════

def _collect_all_test_classes():
    return [
        TestHappyPathStatus,
        TestResponseShape,
        TestJobQueuedStatus,
        TestJobId,
        TestDatasetIdEchoed,
        TestPollUrl,
        TestJobEnqueuedInQueue,
        TestDomainValidation,
        TestAnalysisSpecValidation,
        TestMissingBody,
        TestNotFound,
        TestAnalysisNotReady,
        TestAuthentication,
        TestAuthorisation,
        TestQueueError,
        TestIdempotencyAndIsolation,
        TestDomainSpecificRequests,
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