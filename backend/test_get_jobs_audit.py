"""
Unit tests for  GET /jobs/{job_id}/audit

Task reference : S5-08 (Sprint 5)
    "GET /jobs/{id}/audit — return full audit log for a pipeline run"

Architecture refs:
    • Downloadable as JSON or CSV from /jobs/{id}/audit
    • Every HITL decision recorded: user_id, timestamp, dataset_id,
      agent_step, original_proposal, final_decision, latency_seconds
    • Cleaning executor logs per step:
        action_type, rows_affected, before/after counts,
        rationale, confidence, timestamp, prompt_template_version, user_decision
    • pipeline_runs table: run_id, dataset_id, status, started_at,
        completed_at, error_summary, audit_log_uri, llm_tokens, cost_usd

Audit entry types (event_type):
    agent_step   → one per pipeline agent node executed
    hitl_decision → one per HITL checkpoint decision
    cleaning_step → one per approved cleaning step executed
    error        → one when a pipeline stage fails

Response (200):
    {
        "job_id":        str,
        "dataset_id":    str,
        "total_entries": int,
        "entries": [
            {
                "entry_id":    str,
                "event_type":  str,   # agent_step|hitl_decision|cleaning_step|error
                "agent_step":  str | null,
                "timestamp":   str,   # ISO-8601
                "details":     dict,  # event-specific payload
            },
            ...
        ]
    }

Cleaning step detail fields (mirrors cleaning_executor.py audit dict):
    step_id, action, column, method, rationale, confidence,
    rows_before, rows_after, rows_changed

HITL decision detail fields (mirrors hitl_decisions table):
    checkpoint, original_proposal, final_decision, latency_seconds, user_id

Run with:
    pytest  test_get_jobs_audit.py -v
    python  test_get_jobs_audit.py     # live results, no pytest needed

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

VALID_EVENT_TYPES   = {"agent_step", "hitl_decision", "cleaning_step", "error"}
VALID_CHECKPOINTS   = {"hitl_merge", "hitl_cleaning", "hitl_intent"}
VALID_AGENT_STEPS   = {
    "load_domain", "ingest", "await_merge_hitl", "cleaning_plan",
    "await_cleaning_hitl", "execute_cleaning", "intent", "analyze", "dashboard",
}
VALID_CLEANING_ACTIONS = {"deduplicate", "impute", "coerce_type", "flag_outlier"}

# ─────────────────────────────────────────────────────────────────────────────
# Audit entry model
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class AuditEntry:
    entry_id:   str
    event_type: str          # agent_step | hitl_decision | cleaning_step | error
    agent_step: Optional[str]
    timestamp:  str          # ISO-8601
    details:    dict


@dataclass
class AuditLog:
    job_id:     str
    dataset_id: str
    entries:    list[AuditEntry] = field(default_factory=list)


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
# Audit store
# ─────────────────────────────────────────────────────────────────────────────

class AuditStore:
    """
    In-memory store mapping job_id → AuditLog.
    Flag sets drive every error path.
    """

    def __init__(self) -> None:
        self._logs: dict[str, AuditLog] = {}
        self._server_errors: set[str] = set()
        self._unauthorized:  set[str] = set()
        self._forbidden:     set[str] = set()

    def add(self, log: AuditLog) -> None:
        self._logs[log.job_id] = log

    def get(self, job_id: str) -> Optional[AuditLog]:
        return self._logs.get(job_id)

    def set_server_error(self, job_id: str) -> None:
        self._server_errors.add(job_id)

    def set_unauthorized(self, job_id: str) -> None:
        self._unauthorized.add(job_id)

    def set_forbidden(self, job_id: str) -> None:
        self._forbidden.add(job_id)

    def is_server_error(self, jid: str) -> bool:
        return jid in self._server_errors

    def is_unauthorized(self, jid: str) -> bool:
        return jid in self._unauthorized

    def is_forbidden(self, jid: str) -> bool:
        return jid in self._forbidden


# ─────────────────────────────────────────────────────────────────────────────
# Fake handler:  GET /jobs/{job_id}/audit
# ─────────────────────────────────────────────────────────────────────────────

def _entry_to_dict(e: AuditEntry) -> dict:
    return {
        "entry_id":   e.entry_id,
        "event_type": e.event_type,
        "agent_step": e.agent_step,
        "timestamp":  e.timestamp,
        "details":    e.details,
    }


def handle_get_audit(
    job_id: str,
    store: AuditStore,
    *,
    auth_token: Optional[str] = "Bearer valid-token",
    accept: str = "application/json",
) -> Response:
    """
    GET /jobs/{job_id}/audit

    Auth      : missing/empty token  → 401
                store.is_unauthorized → 401
    Permission: store.is_forbidden   → 403
    Not found : no audit log         → 404
    Server err: store.is_server_error → 500
    Happy path: 200 + full audit log JSON
                (accept=text/csv returns CSV wrapper — still 200, body is dict here)
    """
    # 401: no token
    if not auth_token or not auth_token.strip():
        return Response(
            status_code=401,
            body={"detail": "Authentication required"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    # 401: rejected token
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
            body={"detail": "You do not have permission to access this audit log"},
        )
    # 500
    if store.is_server_error(job_id):
        return Response(
            status_code=500,
            body={"detail": "Internal server error while retrieving audit log"},
        )
    # 404
    audit_log = store.get(job_id)
    if audit_log is None:
        return Response(
            status_code=404,
            body={"detail": f"Audit log for job '{job_id}' not found"},
        )
    # 200
    entries = [_entry_to_dict(e) for e in audit_log.entries]
    body = {
        "job_id":        audit_log.job_id,
        "dataset_id":    audit_log.dataset_id,
        "total_entries": len(entries),
        "entries":       entries,
    }
    return Response(
        status_code=200,
        body=body,
        headers={"Content-Type": "application/json"},
    )


# ─────────────────────────────────────────────────────────────────────────────
# Entry factory helpers
# ─────────────────────────────────────────────────────────────────────────────

_TS = "2026-06-04T10:00:00Z"
_TS2 = "2026-06-04T10:01:00Z"


def new_id() -> str:
    return str(uuid.uuid4())


def agent_step_entry(
    agent_step: str = "ingest",
    status: str = "completed",
    duration_ms: int = 120,
    timestamp: str = _TS,
) -> AuditEntry:
    return AuditEntry(
        entry_id=new_id(),
        event_type="agent_step",
        agent_step=agent_step,
        timestamp=timestamp,
        details={"status": status, "duration_ms": duration_ms},
    )


def hitl_entry(
    checkpoint: str = "hitl_merge",
    decision: str = "approved",
    latency: float = 15.3,
    timestamp: str = _TS,
) -> AuditEntry:
    return AuditEntry(
        entry_id=new_id(),
        event_type="hitl_decision",
        agent_step=checkpoint,
        timestamp=timestamp,
        details={
            "checkpoint":        checkpoint,
            "original_proposal": {"strategy": "union"},
            "final_decision":    {"approved": True, "override_strategy": None},
            "latency_seconds":   latency,
            "user_id":           "user-abc",
        },
    )


def cleaning_entry(
    step_id: int = 1,
    action: str = "deduplicate",
    column: Optional[str] = None,
    method: str = "exact row deduplication",
    rows_before: int = 1000,
    rows_after: int = 990,
    rows_changed: int = 10,
    confidence: float = 0.95,
    timestamp: str = _TS,
) -> AuditEntry:
    return AuditEntry(
        entry_id=new_id(),
        event_type="cleaning_step",
        agent_step="execute_cleaning",
        timestamp=timestamp,
        details={
            "step_id":      step_id,
            "action":       action,
            "column":       column,
            "method":       method,
            "rationale":    f"Auto rationale for {action}",
            "confidence":   confidence,
            "rows_before":  rows_before,
            "rows_after":   rows_after,
            "rows_changed": rows_changed,
        },
    )


def error_entry(
    agent_step: str = "cleaning_plan",
    message: str = "LLM rate limit exceeded",
    timestamp: str = _TS,
) -> AuditEntry:
    return AuditEntry(
        entry_id=new_id(),
        event_type="error",
        agent_step=agent_step,
        timestamp=timestamp,
        details={"message": message, "recoverable": False},
    )


def make_env(entries: Optional[list[AuditEntry]] = None) -> tuple[AuditStore, AuditLog]:
    store = AuditStore()
    log = AuditLog(
        job_id=new_id(), dataset_id=new_id(),
        entries=entries if entries is not None else [agent_step_entry()],
    )
    store.add(log)
    return store, log


def get(store: AuditStore, log: AuditLog,
        token: Optional[str] = "Bearer valid-token") -> Response:
    return handle_get_audit(log.job_id, store, auth_token=token)


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
        print("  GET /jobs/{job_id}/audit — test results")
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
# 1. 200 — status, headers, body type
# ─────────────────────────────────────────────────────────────────────────────

class TestHappyPathStatus:

    def test_returns_200(self):
        store, log = make_env()
        assert get(store, log).status_code == 200

    def test_ok_property_true(self):
        store, log = make_env()
        assert get(store, log).ok is True

    def test_content_type_json(self):
        store, log = make_env()
        assert get(store, log).headers.get("Content-Type") == "application/json"

    def test_body_is_dict(self):
        store, log = make_env()
        assert isinstance(get(store, log).json(), dict)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Response envelope shape
# ─────────────────────────────────────────────────────────────────────────────

class TestEnvelopeShape:

    REQUIRED_KEYS = {"job_id", "dataset_id", "total_entries", "entries"}

    def _body(self) -> dict:
        store, log = make_env()
        return get(store, log).json()

    def test_all_required_keys_present(self):
        assert self.REQUIRED_KEYS.issubset(self._body().keys())

    def test_job_id_is_string(self):
        assert isinstance(self._body()["job_id"], str)

    def test_dataset_id_is_string(self):
        assert isinstance(self._body()["dataset_id"], str)

    def test_total_entries_is_int(self):
        assert isinstance(self._body()["total_entries"], int)

    def test_entries_is_list(self):
        assert isinstance(self._body()["entries"], list)

    def test_total_entries_matches_entries_length(self):
        body = self._body()
        assert body["total_entries"] == len(body["entries"])

    def test_job_id_echoed_correctly(self):
        store, log = make_env()
        assert get(store, log).json()["job_id"] == log.job_id

    def test_dataset_id_echoed_correctly(self):
        store, log = make_env()
        assert get(store, log).json()["dataset_id"] == log.dataset_id

    def test_total_entries_zero_for_empty_log(self):
        store, log = make_env(entries=[])
        body = get(store, log).json()
        assert body["total_entries"] == 0
        assert body["entries"] == []


# ─────────────────────────────────────────────────────────────────────────────
# 3. Audit entry shape — required fields on every entry
# ─────────────────────────────────────────────────────────────────────────────

class TestEntryShape:

    REQUIRED_ENTRY_KEYS = {"entry_id", "event_type", "agent_step", "timestamp", "details"}

    def _first_entry(self) -> dict:
        store, log = make_env()
        return get(store, log).json()["entries"][0]

    def test_entry_has_entry_id(self):
        assert "entry_id" in self._first_entry()

    def test_entry_has_event_type(self):
        assert "event_type" in self._first_entry()

    def test_entry_has_agent_step(self):
        assert "agent_step" in self._first_entry()

    def test_entry_has_timestamp(self):
        assert "timestamp" in self._first_entry()

    def test_entry_has_details(self):
        assert "details" in self._first_entry()

    def test_entry_has_all_required_keys(self):
        assert self.REQUIRED_ENTRY_KEYS.issubset(self._first_entry().keys())

    def test_entry_id_is_string(self):
        assert isinstance(self._first_entry()["entry_id"], str)

    def test_event_type_is_string(self):
        assert isinstance(self._first_entry()["event_type"], str)

    def test_timestamp_is_string(self):
        assert isinstance(self._first_entry()["timestamp"], str)

    def test_details_is_dict(self):
        assert isinstance(self._first_entry()["details"], dict)

    def test_agent_step_is_string_or_none(self):
        val = self._first_entry()["agent_step"]
        assert val is None or isinstance(val, str)

    def test_entry_id_non_empty(self):
        assert len(self._first_entry()["entry_id"]) > 0

    def test_timestamp_contains_T(self):
        assert "T" in self._first_entry()["timestamp"]


# ─────────────────────────────────────────────────────────────────────────────
# 4. event_type — all four valid values
# ─────────────────────────────────────────────────────────────────────────────

class TestEventTypes:

    def test_agent_step_event_type_returned(self):
        store, log = make_env([agent_step_entry()])
        entry = get(store, log).json()["entries"][0]
        assert entry["event_type"] == "agent_step"

    def test_hitl_decision_event_type_returned(self):
        store, log = make_env([hitl_entry()])
        entry = get(store, log).json()["entries"][0]
        assert entry["event_type"] == "hitl_decision"

    def test_cleaning_step_event_type_returned(self):
        store, log = make_env([cleaning_entry()])
        entry = get(store, log).json()["entries"][0]
        assert entry["event_type"] == "cleaning_step"

    def test_error_event_type_returned(self):
        store, log = make_env([error_entry()])
        entry = get(store, log).json()["entries"][0]
        assert entry["event_type"] == "error"

    def test_all_four_event_types_in_one_log(self):
        entries = [
            agent_step_entry(), hitl_entry(), cleaning_entry(), error_entry()
        ]
        store, log = make_env(entries)
        types = {e["event_type"] for e in get(store, log).json()["entries"]}
        assert types == VALID_EVENT_TYPES

    def test_event_type_is_valid_value(self):
        for et in VALID_EVENT_TYPES:
            e = AuditEntry(new_id(), et, "ingest", _TS, {})
            store, audit_log = make_env([e])
            returned = get(store, audit_log).json()["entries"][0]["event_type"]
            assert returned in VALID_EVENT_TYPES


# ─────────────────────────────────────────────────────────────────────────────
# 5. Entry count and ordering
# ─────────────────────────────────────────────────────────────────────────────

class TestEntryCountAndOrder:

    def test_empty_audit_returns_zero_entries(self):
        store, log = make_env([])
        body = get(store, log).json()
        assert body["total_entries"] == 0
        assert body["entries"] == []

    def test_single_entry_returned(self):
        store, log = make_env([agent_step_entry()])
        assert len(get(store, log).json()["entries"]) == 1

    def test_multiple_entries_all_returned(self):
        entries = [agent_step_entry(), hitl_entry(), cleaning_entry()]
        store, log = make_env(entries)
        assert len(get(store, log).json()["entries"]) == 3

    def test_total_entries_matches_len_entries(self):
        for n in [0, 1, 5, 10]:
            entries = [agent_step_entry() for _ in range(n)]
            store, log = make_env(entries)
            body = get(store, log).json()
            assert body["total_entries"] == n
            assert len(body["entries"]) == n

    def test_entries_returned_in_insertion_order(self):
        entries = [
            agent_step_entry("ingest",         timestamp="2026-06-04T10:00:00Z"),
            hitl_entry(checkpoint="hitl_merge", timestamp="2026-06-04T10:01:00Z"),
            agent_step_entry("cleaning_plan",   timestamp="2026-06-04T10:02:00Z"),
        ]
        store, log = make_env(entries)
        returned = get(store, log).json()["entries"]
        assert returned[0]["agent_step"] == "ingest"
        assert returned[1]["agent_step"] == "hitl_merge"
        assert returned[2]["agent_step"] == "cleaning_plan"

    def test_entry_ids_are_unique(self):
        entries = [agent_step_entry() for _ in range(10)]
        store, log = make_env(entries)
        ids = [e["entry_id"] for e in get(store, log).json()["entries"]]
        assert len(ids) == len(set(ids))

    def test_large_audit_log_all_returned(self):
        entries = (
            [agent_step_entry("ingest")] +
            [cleaning_entry(i + 1) for i in range(20)] +
            [hitl_entry()]
        )
        store, log = make_env(entries)
        body = get(store, log).json()
        assert body["total_entries"] == 22
        assert len(body["entries"]) == 22


# ─────────────────────────────────────────────────────────────────────────────
# 6. agent_step entries — detail fields
# ─────────────────────────────────────────────────────────────────────────────

class TestAgentStepEntries:

    def test_agent_step_entry_has_status(self):
        store, log = make_env([agent_step_entry(status="completed")])
        details = get(store, log).json()["entries"][0]["details"]
        assert "status" in details

    def test_agent_step_entry_has_duration_ms(self):
        store, log = make_env([agent_step_entry(duration_ms=250)])
        details = get(store, log).json()["entries"][0]["details"]
        assert "duration_ms" in details

    def test_agent_step_name_in_agent_step_field(self):
        store, log = make_env([agent_step_entry("ingest")])
        assert get(store, log).json()["entries"][0]["agent_step"] == "ingest"

    def test_all_pipeline_step_names_round_trip(self):
        for step in VALID_AGENT_STEPS:
            store, log = make_env([agent_step_entry(step)])
            returned = get(store, log).json()["entries"][0]["agent_step"]
            assert returned == step

    def test_agent_step_status_completed(self):
        store, log = make_env([agent_step_entry(status="completed")])
        assert get(store, log).json()["entries"][0]["details"]["status"] == "completed"

    def test_agent_step_status_failed(self):
        store, log = make_env([agent_step_entry(status="failed")])
        assert get(store, log).json()["entries"][0]["details"]["status"] == "failed"

    def test_duration_ms_preserved(self):
        store, log = make_env([agent_step_entry(duration_ms=1234)])
        assert get(store, log).json()["entries"][0]["details"]["duration_ms"] == 1234

    def test_agent_step_timestamp_preserved(self):
        store, log = make_env([agent_step_entry(timestamp="2026-06-04T08:30:00Z")])
        assert get(store, log).json()["entries"][0]["timestamp"] == "2026-06-04T08:30:00Z"


# ─────────────────────────────────────────────────────────────────────────────
# 7. hitl_decision entries — detail fields
# ─────────────────────────────────────────────────────────────────────────────

class TestHITLDecisionEntries:

    REQUIRED_HITL_DETAIL_KEYS = {
        "checkpoint", "original_proposal", "final_decision",
        "latency_seconds", "user_id",
    }

    def _hitl_details(self, **kwargs) -> dict:
        store, log = make_env([hitl_entry(**kwargs)])
        return get(store, log).json()["entries"][0]["details"]

    def test_all_required_hitl_detail_keys(self):
        assert self.REQUIRED_HITL_DETAIL_KEYS.issubset(self._hitl_details().keys())

    def test_checkpoint_field_preserved(self):
        assert self._hitl_details(checkpoint="hitl_cleaning")["checkpoint"] == "hitl_cleaning"

    def test_all_three_checkpoints_round_trip(self):
        for cp in VALID_CHECKPOINTS:
            store, log = make_env([hitl_entry(checkpoint=cp)])
            details = get(store, log).json()["entries"][0]["details"]
            assert details["checkpoint"] == cp

    def test_latency_seconds_preserved(self):
        assert abs(self._hitl_details(latency=8.7)["latency_seconds"] - 8.7) < 1e-9

    def test_original_proposal_is_dict(self):
        assert isinstance(self._hitl_details()["original_proposal"], dict)

    def test_final_decision_is_dict(self):
        assert isinstance(self._hitl_details()["final_decision"], dict)

    def test_user_id_preserved(self):
        assert self._hitl_details()["user_id"] == "user-abc"

    def test_hitl_merge_event_type(self):
        store, log = make_env([hitl_entry(checkpoint="hitl_merge")])
        assert get(store, log).json()["entries"][0]["event_type"] == "hitl_decision"

    def test_hitl_cleaning_event_type(self):
        store, log = make_env([hitl_entry(checkpoint="hitl_cleaning")])
        assert get(store, log).json()["entries"][0]["event_type"] == "hitl_decision"

    def test_hitl_intent_event_type(self):
        store, log = make_env([hitl_entry(checkpoint="hitl_intent")])
        assert get(store, log).json()["entries"][0]["event_type"] == "hitl_decision"


# ─────────────────────────────────────────────────────────────────────────────
# 8. cleaning_step entries — detail fields (mirrors cleaning_executor.py)
# ─────────────────────────────────────────────────────────────────────────────

class TestCleaningStepEntries:

    REQUIRED_CLEANING_DETAIL_KEYS = {
        "step_id", "action", "column", "method", "rationale",
        "confidence", "rows_before", "rows_after", "rows_changed",
    }

    def _cleaning_details(self, **kwargs) -> dict:
        store, log = make_env([cleaning_entry(**kwargs)])
        return get(store, log).json()["entries"][0]["details"]

    def test_all_required_cleaning_detail_keys(self):
        assert self.REQUIRED_CLEANING_DETAIL_KEYS.issubset(self._cleaning_details().keys())

    def test_step_id_preserved(self):
        assert self._cleaning_details(step_id=3)["step_id"] == 3

    def test_action_deduplicate_preserved(self):
        assert self._cleaning_details(action="deduplicate")["action"] == "deduplicate"

    def test_action_impute_preserved(self):
        assert self._cleaning_details(action="impute", column="revenue")["action"] == "impute"

    def test_action_coerce_type_preserved(self):
        assert self._cleaning_details(action="coerce_type", column="price")["action"] == "coerce_type"

    def test_action_flag_outlier_preserved(self):
        assert self._cleaning_details(action="flag_outlier", column="score")["action"] == "flag_outlier"

    def test_all_valid_actions_round_trip(self):
        for act in VALID_CLEANING_ACTIONS:
            col = "x" if act != "deduplicate" else None
            store, log = make_env([cleaning_entry(action=act, column=col)])
            details = get(store, log).json()["entries"][0]["details"]
            assert details["action"] == act

    def test_column_null_for_deduplicate(self):
        assert self._cleaning_details(action="deduplicate", column=None)["column"] is None

    def test_column_string_for_impute(self):
        assert self._cleaning_details(action="impute", column="revenue")["column"] == "revenue"

    def test_method_preserved(self):
        assert self._cleaning_details(method="median imputation")["method"] == "median imputation"

    def test_confidence_preserved(self):
        assert abs(self._cleaning_details(confidence=0.87)["confidence"] - 0.87) < 1e-9

    def test_rows_before_preserved(self):
        assert self._cleaning_details(rows_before=5000)["rows_before"] == 5000

    def test_rows_after_preserved(self):
        assert self._cleaning_details(rows_after=4950)["rows_after"] == 4950

    def test_rows_changed_preserved(self):
        assert self._cleaning_details(rows_changed=50)["rows_changed"] == 50

    def test_rows_changed_is_difference_for_dedup(self):
        details = self._cleaning_details(
            action="deduplicate", rows_before=1000, rows_after=988, rows_changed=12
        )
        assert details["rows_changed"] == 12

    def test_rationale_non_empty(self):
        assert len(self._cleaning_details()["rationale"].strip()) > 0

    def test_agent_step_is_execute_cleaning(self):
        store, log = make_env([cleaning_entry()])
        assert get(store, log).json()["entries"][0]["agent_step"] == "execute_cleaning"

    def test_multiple_cleaning_steps_all_returned(self):
        steps = [
            cleaning_entry(1, "deduplicate",  None,        rows_before=1000, rows_after=990),
            cleaning_entry(2, "impute",       "revenue",   rows_before=990,  rows_after=990),
            cleaning_entry(3, "coerce_type",  "price_str", rows_before=990,  rows_after=990),
            cleaning_entry(4, "flag_outlier", "revenue",   rows_before=990,  rows_after=990),
        ]
        store, log = make_env(steps)
        entries = get(store, log).json()["entries"]
        assert len(entries) == 4
        actions = [e["details"]["action"] for e in entries]
        assert actions == ["deduplicate", "impute", "coerce_type", "flag_outlier"]


# ─────────────────────────────────────────────────────────────────────────────
# 9. error entries
# ─────────────────────────────────────────────────────────────────────────────

class TestErrorEntries:

    def test_error_event_type_returned(self):
        store, log = make_env([error_entry()])
        assert get(store, log).json()["entries"][0]["event_type"] == "error"

    def test_error_message_in_details(self):
        store, log = make_env([error_entry(message="LLM timeout after 30s")])
        assert get(store, log).json()["entries"][0]["details"]["message"] == "LLM timeout after 30s"

    def test_error_agent_step_preserved(self):
        store, log = make_env([error_entry(agent_step="execute_cleaning")])
        assert get(store, log).json()["entries"][0]["agent_step"] == "execute_cleaning"

    def test_various_error_messages_preserved(self):
        messages = [
            "Supabase Storage write timeout",
            "LLM structured_completion failed after 3 retries",
            "Database connection refused",
            "cleaning executor raised ValueError",
            "Dashboard agent exceeded token budget",
        ]
        for msg in messages:
            store, log = make_env([error_entry(message=msg)])
            returned = get(store, log).json()["entries"][0]["details"]["message"]
            assert returned == msg

    def test_error_details_has_recoverable_field(self):
        store, log = make_env([error_entry()])
        details = get(store, log).json()["entries"][0]["details"]
        assert "recoverable" in details


# ─────────────────────────────────────────────────────────────────────────────
# 10. Full pipeline audit log — realistic end-to-end sequence
# ─────────────────────────────────────────────────────────────────────────────

class TestFullPipelineAuditLog:
    """
    Build a realistic complete pipeline audit log and verify every aspect:
    order, types, entry count, cleaning step chain, three HITL decisions.
    """

    def _build_full_log(self) -> tuple[AuditStore, AuditLog]:
        entries = [
            # 1. Domain loaded
            agent_step_entry("load_domain",     status="completed", duration_ms=12),
            # 2. Ingestion
            agent_step_entry("ingest",          status="completed", duration_ms=340),
            # 3. HITL #1 — merge
            hitl_entry("hitl_merge",            latency=18.4),
            # 4. Cleaning plan
            agent_step_entry("cleaning_plan",   status="completed", duration_ms=890),
            # 5. HITL #2 — cleaning
            hitl_entry("hitl_cleaning",         latency=45.1),
            # 6. Cleaning execution — 3 steps
            cleaning_entry(1, "deduplicate",  None,       rows_before=1000, rows_after=988, rows_changed=12),
            cleaning_entry(2, "impute",       "revenue",  rows_before=988,  rows_after=988, rows_changed=0),
            cleaning_entry(3, "coerce_type",  "price_str",rows_before=988,  rows_after=988, rows_changed=0),
            # 7. Intent + HITL #3
            agent_step_entry("intent",          status="completed", duration_ms=210),
            hitl_entry("hitl_intent",           latency=22.0),
            # 8. Analysis
            agent_step_entry("analyze",         status="completed", duration_ms=1500),
            # 9. Dashboard
            agent_step_entry("dashboard",       status="completed", duration_ms=3200),
        ]
        store, log = make_env(entries)
        return store, log

    def test_total_entries_correct(self):
        store, log = self._build_full_log()
        assert get(store, log).json()["total_entries"] == 12

    def test_first_entry_is_load_domain(self):
        store, log = self._build_full_log()
        assert get(store, log).json()["entries"][0]["agent_step"] == "load_domain"

    def test_last_entry_is_dashboard(self):
        store, log = self._build_full_log()
        assert get(store, log).json()["entries"][-1]["agent_step"] == "dashboard"

    def test_three_hitl_decisions_present(self):
        store, log = self._build_full_log()
        hitl = [e for e in get(store, log).json()["entries"]
                if e["event_type"] == "hitl_decision"]
        assert len(hitl) == 3

    def test_all_three_hitl_checkpoints_present(self):
        store, log = self._build_full_log()
        checkpoints = {
            e["details"]["checkpoint"]
            for e in get(store, log).json()["entries"]
            if e["event_type"] == "hitl_decision"
        }
        assert checkpoints == {"hitl_merge", "hitl_cleaning", "hitl_intent"}

    def test_three_cleaning_steps_present(self):
        store, log = self._build_full_log()
        cleaning = [e for e in get(store, log).json()["entries"]
                    if e["event_type"] == "cleaning_step"]
        assert len(cleaning) == 3

    def test_cleaning_step_actions_in_order(self):
        store, log = self._build_full_log()
        cleaning = [e for e in get(store, log).json()["entries"]
                    if e["event_type"] == "cleaning_step"]
        actions = [e["details"]["action"] for e in cleaning]
        assert actions == ["deduplicate", "impute", "coerce_type"]

    def test_dedup_step_rows_reduced(self):
        store, log = self._build_full_log()
        dedup = next(
            e for e in get(store, log).json()["entries"]
            if e["event_type"] == "cleaning_step"
            and e["details"]["action"] == "deduplicate"
        )
        assert dedup["details"]["rows_before"] > dedup["details"]["rows_after"]

    def test_six_agent_step_entries_present(self):
        store, log = self._build_full_log()
        agent_entries = [e for e in get(store, log).json()["entries"]
                         if e["event_type"] == "agent_step"]
        assert len(agent_entries) == 6

    def test_entry_types_distribution(self):
        store, log = self._build_full_log()
        from collections import Counter
        type_counts = Counter(
            e["event_type"] for e in get(store, log).json()["entries"]
        )
        assert type_counts["agent_step"]    == 6
        assert type_counts["hitl_decision"] == 3
        assert type_counts["cleaning_step"] == 3

    def test_all_entries_have_timestamps(self):
        store, log = self._build_full_log()
        for e in get(store, log).json()["entries"]:
            assert "T" in e["timestamp"]

    def test_all_entries_have_non_empty_entry_id(self):
        store, log = self._build_full_log()
        for e in get(store, log).json()["entries"]:
            assert len(e["entry_id"]) > 0


# ─────────────────────────────────────────────────────────────────────────────
# 11. Partial / failed pipeline audit log
# ─────────────────────────────────────────────────────────────────────────────

class TestPartialAndFailedAuditLog:

    def test_pipeline_failed_at_ingest_has_error_entry(self):
        entries = [
            agent_step_entry("load_domain", status="completed"),
            agent_step_entry("ingest",      status="failed"),
            error_entry("ingest", "Failed to parse corrupt CSV"),
        ]
        store, log = make_env(entries)
        body = get(store, log).json()
        error_entries = [e for e in body["entries"] if e["event_type"] == "error"]
        assert len(error_entries) == 1
        assert "CSV" in error_entries[0]["details"]["message"]

    def test_failed_pipeline_has_fewer_entries_than_complete(self):
        partial = [agent_step_entry("ingest"), error_entry("ingest", "crash")]
        full    = [agent_step_entry("ingest"), agent_step_entry("cleaning_plan"),
                   hitl_entry(), cleaning_entry()]
        store_p, log_p = make_env(partial)
        store_f, log_f = make_env(full)
        count_partial = get(store_p, log_p).json()["total_entries"]
        count_full    = get(store_f, log_f).json()["total_entries"]
        assert count_partial < count_full

    def test_audit_log_exists_even_for_failed_pipeline(self):
        entries = [agent_step_entry("ingest"), error_entry("ingest", "timeout")]
        store, log = make_env(entries)
        assert get(store, log).status_code == 200

    def test_pipeline_paused_at_hitl_has_no_cleaning_entries(self):
        entries = [
            agent_step_entry("ingest"),
            hitl_entry("hitl_merge"),
        ]
        store, log = make_env(entries)
        cleaning = [e for e in get(store, log).json()["entries"]
                    if e["event_type"] == "cleaning_step"]
        assert cleaning == []

    def test_pipeline_with_only_agent_steps_no_hitl(self):
        entries = [agent_step_entry(s) for s in ["load_domain", "ingest", "cleaning_plan"]]
        store, log = make_env(entries)
        hitl_entries = [e for e in get(store, log).json()["entries"]
                        if e["event_type"] == "hitl_decision"]
        assert hitl_entries == []


# ─────────────────────────────────────────────────────────────────────────────
# 12. Timestamps
# ─────────────────────────────────────────────────────────────────────────────

class TestTimestamps:

    def test_timestamp_preserved_verbatim(self):
        ts = "2026-06-04T09:15:30Z"
        store, log = make_env([agent_step_entry(timestamp=ts)])
        assert get(store, log).json()["entries"][0]["timestamp"] == ts

    def test_different_entries_can_have_different_timestamps(self):
        entries = [
            agent_step_entry(timestamp="2026-06-04T09:00:00Z"),
            hitl_entry(timestamp="2026-06-04T09:05:00Z"),
        ]
        store, log = make_env(entries)
        returned = get(store, log).json()["entries"]
        assert returned[0]["timestamp"] != returned[1]["timestamp"]

    def test_timestamps_are_iso8601(self):
        entries = [
            agent_step_entry(timestamp="2026-06-04T10:00:00Z"),
            hitl_entry(timestamp="2026-06-04T10:01:00Z"),
        ]
        store, log = make_env(entries)
        for e in get(store, log).json()["entries"]:
            ts = e["timestamp"]
            assert "T" in ts and len(ts) >= 19

    def test_all_entries_have_timestamp(self):
        entries = [agent_step_entry(), hitl_entry(), cleaning_entry(), error_entry()]
        store, log = make_env(entries)
        for e in get(store, log).json()["entries"]:
            assert isinstance(e["timestamp"], str)
            assert len(e["timestamp"]) > 0


# ─────────────────────────────────────────────────────────────────────────────
# 13. details dict contents preserved
# ─────────────────────────────────────────────────────────────────────────────

class TestDetailsPreservation:

    def test_details_extra_fields_preserved(self):
        e = AuditEntry(new_id(), "agent_step", "ingest", _TS,
                       {"status": "completed", "duration_ms": 500, "rows_parsed": 1234})
        store, log = make_env([e])
        details = get(store, log).json()["entries"][0]["details"]
        assert details["rows_parsed"] == 1234

    def test_details_nested_dict_preserved(self):
        nested = {"status": "completed", "meta": {"model": "gemini", "tokens": 450}}
        e = AuditEntry(new_id(), "agent_step", "dashboard", _TS, nested)
        store, log = make_env([e])
        details = get(store, log).json()["entries"][0]["details"]
        assert details["meta"]["model"] == "gemini"

    def test_details_list_value_preserved(self):
        d = {"approved_step_ids": [1, 3, 5]}
        e = AuditEntry(new_id(), "hitl_decision", "hitl_cleaning", _TS, d)
        store, log = make_env([e])
        details = get(store, log).json()["entries"][0]["details"]
        assert details["approved_step_ids"] == [1, 3, 5]

    def test_empty_details_dict_returned(self):
        e = AuditEntry(new_id(), "agent_step", "load_domain", _TS, {})
        store, log = make_env([e])
        assert get(store, log).json()["entries"][0]["details"] == {}


# ─────────────────────────────────────────────────────────────────────────────
# 14. 404 — audit log not found
# ─────────────────────────────────────────────────────────────────────────────

class TestNotFound:

    def test_unknown_job_id_returns_404(self):
        store = AuditStore()
        assert handle_get_audit(new_id(), store).status_code == 404

    def test_404_body_has_detail(self):
        store = AuditStore()
        assert "detail" in handle_get_audit(new_id(), store).json()

    def test_404_detail_mentions_job_id(self):
        store = AuditStore()
        jid = new_id()
        assert jid in handle_get_audit(jid, store).json()["detail"]

    def test_404_ok_is_false(self):
        store = AuditStore()
        assert handle_get_audit(new_id(), store).ok is False

    def test_registered_job_does_not_return_404(self):
        store, log = make_env()
        assert get(store, log).status_code != 404

    def test_wrong_id_for_existing_job_returns_404(self):
        store, log = make_env()
        assert handle_get_audit(new_id(), store).status_code == 404

    def test_multiple_unknown_ids_all_404(self):
        store = AuditStore()
        for _ in range(5):
            assert handle_get_audit(new_id(), store).status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# 15. 401 — authentication
# ─────────────────────────────────────────────────────────────────────────────

class TestAuthentication:

    def test_no_token_returns_401(self):
        store, log = make_env()
        assert get(store, log, token=None).status_code == 401

    def test_empty_token_returns_401(self):
        store, log = make_env()
        assert get(store, log, token="").status_code == 401

    def test_whitespace_token_returns_401(self):
        store, log = make_env()
        assert get(store, log, token="   ").status_code == 401

    def test_401_has_www_authenticate_bearer(self):
        store, log = make_env()
        resp = get(store, log, token=None)
        assert resp.headers.get("WWW-Authenticate") == "Bearer"

    def test_401_body_has_detail(self):
        store, log = make_env()
        assert "detail" in get(store, log, token=None).json()

    def test_invalid_token_returns_401(self):
        store, log = make_env()
        store.set_unauthorized(log.job_id)
        assert get(store, log).status_code == 401

    def test_valid_token_returns_200(self):
        store, log = make_env()
        assert get(store, log, token="Bearer my-token").status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# 16. 403 — authorisation
# ─────────────────────────────────────────────────────────────────────────────

class TestAuthorisation:

    def test_forbidden_job_returns_403(self):
        store, log = make_env()
        store.set_forbidden(log.job_id)
        assert get(store, log).status_code == 403

    def test_403_body_has_detail(self):
        store, log = make_env()
        store.set_forbidden(log.job_id)
        assert "detail" in get(store, log).json()

    def test_403_ok_is_false(self):
        store, log = make_env()
        store.set_forbidden(log.job_id)
        assert get(store, log).ok is False

    def test_own_audit_log_not_forbidden(self):
        store, log = make_env()
        assert get(store, log).status_code == 200

    def test_forbidden_on_one_does_not_affect_another(self):
        store = AuditStore()
        log_bad = AuditLog(new_id(), new_id(), [agent_step_entry()])
        log_ok  = AuditLog(new_id(), new_id(), [agent_step_entry()])
        store.add(log_bad)
        store.add(log_ok)
        store.set_forbidden(log_bad.job_id)
        assert handle_get_audit(log_bad.job_id, store).status_code == 403
        assert handle_get_audit(log_ok.job_id,  store).status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# 17. 500 — server error
# ─────────────────────────────────────────────────────────────────────────────

class TestServerError:

    def test_server_error_returns_500(self):
        store, log = make_env()
        store.set_server_error(log.job_id)
        assert get(store, log).status_code == 500

    def test_500_body_has_detail(self):
        store, log = make_env()
        store.set_server_error(log.job_id)
        assert "detail" in get(store, log).json()

    def test_500_ok_is_false(self):
        store, log = make_env()
        store.set_server_error(log.job_id)
        assert get(store, log).ok is False

    def test_server_error_on_one_does_not_affect_another(self):
        store = AuditStore()
        log_bad = AuditLog(new_id(), new_id(), [agent_step_entry()])
        log_ok  = AuditLog(new_id(), new_id(), [agent_step_entry()])
        store.add(log_bad)
        store.add(log_ok)
        store.set_server_error(log_bad.job_id)
        assert handle_get_audit(log_bad.job_id, store).status_code == 500
        assert handle_get_audit(log_ok.job_id,  store).status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# 18. Edge cases
# ─────────────────────────────────────────────────────────────────────────────

class TestEdgeCases:

    def test_body_is_json_serialisable(self):
        entries = [agent_step_entry(), hitl_entry(), cleaning_entry(), error_entry()]
        store, log = make_env(entries)
        body = get(store, log).json()
        try:
            json.dumps(body)
        except TypeError as exc:
            raise AssertionError(f"Body not JSON-serialisable: {exc}") from exc

    def test_repeated_calls_return_identical_body(self):
        store, log = make_env([agent_step_entry(), cleaning_entry()])
        b1 = get(store, log).json()
        b2 = get(store, log).json()
        assert b1 == b2

    def test_fifty_cleaning_entries_all_returned(self):
        entries = [cleaning_entry(i + 1) for i in range(50)]
        store, log = make_env(entries)
        body = get(store, log).json()
        assert body["total_entries"] == 50
        assert len(body["entries"]) == 50

    def test_entry_ids_unique_across_mixed_types(self):
        entries = [agent_step_entry(), hitl_entry(), cleaning_entry(), error_entry()]
        store, log = make_env(entries)
        ids = [e["entry_id"] for e in get(store, log).json()["entries"]]
        assert len(ids) == len(set(ids))

    def test_two_audit_logs_independent(self):
        store = AuditStore()
        log_a = AuditLog(new_id(), new_id(), [agent_step_entry("ingest")])
        log_b = AuditLog(new_id(), new_id(), [agent_step_entry("dashboard")])
        store.add(log_a)
        store.add(log_b)
        entries_a = handle_get_audit(log_a.job_id, store).json()["entries"]
        entries_b = handle_get_audit(log_b.job_id, store).json()["entries"]
        assert entries_a[0]["agent_step"] == "ingest"
        assert entries_b[0]["agent_step"] == "dashboard"

    def test_job_id_with_hyphens_handled(self):
        store = AuditStore()
        log = AuditLog(str(uuid.uuid4()), new_id(), [agent_step_entry()])
        store.add(log)
        assert handle_get_audit(log.job_id, store).status_code == 200

    def test_single_cleaning_step_full_detail_round_trip(self):
        entry = cleaning_entry(
            step_id=2, action="impute", column="los",
            method="median imputation",
            rows_before=5000, rows_after=5000, rows_changed=120,
            confidence=0.85,
        )
        store, log = make_env([entry])
        d = get(store, log).json()["entries"][0]["details"]
        assert d["step_id"] == 2
        assert d["action"] == "impute"
        assert d["column"] == "los"
        assert d["method"] == "median imputation"
        assert d["rows_before"] == 5000
        assert d["rows_after"] == 5000
        assert d["rows_changed"] == 120
        assert abs(d["confidence"] - 0.85) < 1e-9


# ═════════════════════════════════════════════════════════════════════════════
# Runner
# ═════════════════════════════════════════════════════════════════════════════

def _collect_all_test_classes():
    return [
        TestHappyPathStatus,
        TestEnvelopeShape,
        TestEntryShape,
        TestEventTypes,
        TestEntryCountAndOrder,
        TestAgentStepEntries,
        TestHITLDecisionEntries,
        TestCleaningStepEntries,
        TestErrorEntries,
        TestFullPipelineAuditLog,
        TestPartialAndFailedAuditLog,
        TestTimestamps,
        TestDetailsPreservation,
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