"""
Unit tests for  GET /dashboards/{dataset_id}

The central test pattern — "404 before, spec after" — exercises the
lifecycle of a dashboard in two phases:

    Phase 1 (BEFORE generation completes):
        • dataset exists, pipeline complete, but no dashboard yet → 404
        • job still queued / running / paused → 202 (still generating)

    Phase 2 (AFTER generation completes):
        • dashboard stored → 200 + full DashboardSpec

Architecture refs (dashboard_agent.py + insights.py):
    DashboardSpec fields:
        kpi_cards           list[KpiCard]     # 2–3 KPI cards
        charts              list[ChartSpec]   # 2 charts (Vega-Lite style)
        narrative           str               # domain-flavoured executive summary
        recommended_action  str               # one concrete next step
        dataset_id          str
        domain              str
        generated_at        str               # ISO-8601 timestamp

    KpiCard fields:
        label       str
        value       str          # stringified number
        change      float | null # optional MoM/QoQ change
        change_pct  float | null

    ChartSpec fields:
        chart_type   str          # line | bar | table
        title        str
        data         list[dict]
        x_field      str
        y_field      str
        color_field  str | null

Response codes:
    200 — dashboard ready, full DashboardSpec returned
    202 — dashboard generation still in progress (job queued/running)
    401 — unauthenticated
    403 — forbidden
    404 — no dashboard (not generated yet, or dataset unknown)
    500 — internal server error

Run with:
    pytest  test_get_dashboards.py -v
    python  test_get_dashboards.py      # live results

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
VALID_CHART_TYPES = {"line", "bar", "table"}
GENERATION_STATES = {"queued", "running", "paused"}   # in-progress, not ready


# ─────────────────────────────────────────────────────────────────────────────
# DashboardSpec model (mirrors DashboardSpec + InsightsAgent output)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class KpiCard:
    label: str
    value: str
    change: Optional[float] = None
    change_pct: Optional[float] = None


@dataclass
class ChartSpec:
    chart_type: str      # line | bar | table
    title: str
    data: list[dict]
    x_field: str
    y_field: str
    color_field: Optional[str] = None


@dataclass
class DashboardSpec:
    dataset_id: str
    domain: str
    kpi_cards: list[KpiCard]
    charts: list[ChartSpec]
    narrative: str
    recommended_action: str
    generated_at: str = "2026-06-04T12:00:00Z"


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
# Dashboard store
# ─────────────────────────────────────────────────────────────────────────────

class DashboardStore:
    """
    Controls which dataset_ids exist in which state:

        register_no_dashboard(did)  — dataset known, pipeline done, but no dash yet
        register_in_progress(did, job_status)  — generation running/queued/paused
        register_dashboard(did, spec)          — generation complete, spec stored
        set_unauthorized / set_forbidden / set_server_error — error paths
    """

    def __init__(self) -> None:
        self._dashboards: dict[str, DashboardSpec] = {}
        self._no_dashboard: set[str] = set()    # known dataset, no dashboard
        self._in_progress: dict[str, str] = {}  # did → job_status
        self._unauthorized: set[str] = set()
        self._forbidden: set[str] = set()
        self._server_errors: set[str] = set()

    # ── registration ─────────────────────────────────────────────────────────
    def register_no_dashboard(self, did: str) -> None:
        self._no_dashboard.add(did)

    def register_in_progress(self, did: str, job_status: str = "running") -> None:
        self._in_progress[did] = job_status

    def register_dashboard(self, did: str, spec: DashboardSpec) -> None:
        self._dashboards[did] = spec
        # Remove from other states if previously set
        self._no_dashboard.discard(did)
        self._in_progress.pop(did, None)

    # ── flag setters ──────────────────────────────────────────────────────────
    def set_unauthorized(self, did: str) -> None:
        self._unauthorized.add(did)

    def set_forbidden(self, did: str) -> None:
        self._forbidden.add(did)

    def set_server_error(self, did: str) -> None:
        self._server_errors.add(did)

    # ── lookups ───────────────────────────────────────────────────────────────
    def get_dashboard(self, did: str) -> Optional[DashboardSpec]:
        return self._dashboards.get(did)

    def is_in_progress(self, did: str) -> bool:
        return did in self._in_progress

    def job_status(self, did: str) -> Optional[str]:
        return self._in_progress.get(did)

    def is_known(self, did: str) -> bool:
        return (did in self._dashboards or
                did in self._no_dashboard or
                did in self._in_progress)

    def is_unauthorized(self, did: str) -> bool:
        return did in self._unauthorized

    def is_forbidden(self, did: str) -> bool:
        return did in self._forbidden

    def is_server_error(self, did: str) -> bool:
        return did in self._server_errors


# ─────────────────────────────────────────────────────────────────────────────
# Serialisation helpers
# ─────────────────────────────────────────────────────────────────────────────

def _kpi_to_dict(k: KpiCard) -> dict:
    return {
        "label":      k.label,
        "value":      k.value,
        "change":     k.change,
        "change_pct": k.change_pct,
    }


def _chart_to_dict(c: ChartSpec) -> dict:
    return {
        "chart_type":  c.chart_type,
        "title":       c.title,
        "data":        c.data,
        "x_field":     c.x_field,
        "y_field":     c.y_field,
        "color_field": c.color_field,
    }


def _spec_to_dict(spec: DashboardSpec) -> dict:
    return {
        "dataset_id":         spec.dataset_id,
        "domain":             spec.domain,
        "kpi_cards":          [_kpi_to_dict(k) for k in spec.kpi_cards],
        "charts":             [_chart_to_dict(c) for c in spec.charts],
        "narrative":          spec.narrative,
        "recommended_action": spec.recommended_action,
        "generated_at":       spec.generated_at,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Fake handler:  GET /dashboards/{dataset_id}
# ─────────────────────────────────────────────────────────────────────────────

def handle_get_dashboard(
    dataset_id: str,
    store: DashboardStore,
    *,
    auth_token: Optional[str] = "Bearer valid-token",
) -> Response:
    """
    GET /dashboards/{dataset_id}

    401  : missing/empty token or store.is_unauthorized
    403  : store.is_forbidden
    500  : store.is_server_error
    202  : dashboard generation in progress (queued/running/paused)
    404  : dataset known but no dashboard, OR dataset completely unknown
    200  : dashboard ready — full DashboardSpec JSON
    """
    # 401: no token
    if not auth_token or not auth_token.strip():
        return Response(
            status_code=401,
            body={"detail": "Authentication required"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    # 401: rejected
    if store.is_unauthorized(dataset_id):
        return Response(
            status_code=401,
            body={"detail": "Invalid or expired token"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    # 403
    if store.is_forbidden(dataset_id):
        return Response(
            status_code=403,
            body={"detail": "You do not have permission to view this dashboard"},
        )
    # 500
    if store.is_server_error(dataset_id):
        return Response(
            status_code=500,
            body={"detail": "Internal server error while retrieving dashboard"},
        )
    # 202: still generating
    if store.is_in_progress(dataset_id):
        return Response(
            status_code=202,
            body={
                "detail":     "Dashboard is still being generated",
                "status":     store.job_status(dataset_id),
                "dataset_id": dataset_id,
            },
        )
    # 200: ready
    spec = store.get_dashboard(dataset_id)
    if spec is not None:
        return Response(
            status_code=200,
            body=_spec_to_dict(spec),
            headers={"Content-Type": "application/json"},
        )
    # 404: not found (no dashboard, dataset unknown or pipeline not run)
    return Response(
        status_code=404,
        body={"detail": f"No dashboard found for dataset '{dataset_id}'"},
    )


# ─────────────────────────────────────────────────────────────────────────────
# Fixture helpers
# ─────────────────────────────────────────────────────────────────────────────

def new_id() -> str:
    return str(uuid.uuid4())


def _default_kpis(domain: str = "finance") -> list[KpiCard]:
    if domain == "finance":
        return [
            KpiCard("Total Revenue",  "$2.4M",   change=120000.0, change_pct=5.2),
            KpiCard("Gross Margin",   "62%",     change=None,     change_pct=None),
            KpiCard("MRR",            "$200K",   change=8000.0,   change_pct=4.2),
        ]
    if domain == "healthcare":
        return [
            KpiCard("Patient Volume", "1,240",   change=None,  change_pct=None),
            KpiCard("Avg LOS",        "4.2 days",change=-0.3,  change_pct=-6.7),
        ]
    return [KpiCard("Metric A", "100", change=None, change_pct=None)]


def _default_charts(domain: str = "finance") -> list[ChartSpec]:
    return [
        ChartSpec(
            chart_type="bar", title=f"{domain.title()} Revenue by Region",
            data=[{"region": "APAC", "revenue": 800000},
                  {"region": "EMEA", "revenue": 960000},
                  {"region": "AMER", "revenue": 640000}],
            x_field="region", y_field="revenue",
        ),
        ChartSpec(
            chart_type="line", title="Revenue Trend (MoM)",
            data=[{"month": "Jan", "revenue": 180000},
                  {"month": "Feb", "revenue": 200000},
                  {"month": "Mar", "revenue": 220000}],
            x_field="month", y_field="revenue",
        ),
    ]


def make_spec(
    dataset_id: Optional[str] = None,
    domain: str = "finance",
    narrative: str = "Revenue grew 5.2% MoM driven by EMEA.",
    recommended_action: str = "Expand EMEA sales team by Q3.",
    kpi_cards: Optional[list[KpiCard]] = None,
    charts: Optional[list[ChartSpec]] = None,
    generated_at: str = "2026-06-04T12:00:00Z",
) -> DashboardSpec:
    did = dataset_id or new_id()
    return DashboardSpec(
        dataset_id=did,
        domain=domain,
        kpi_cards=kpi_cards if kpi_cards is not None else _default_kpis(domain),
        charts=charts if charts is not None else _default_charts(domain),
        narrative=narrative,
        recommended_action=recommended_action,
        generated_at=generated_at,
    )


def get(
    store: DashboardStore,
    dataset_id: str,
    token: Optional[str] = "Bearer valid-token",
) -> Response:
    return handle_get_dashboard(dataset_id, store, auth_token=token)


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
        print("  GET /dashboards/{dataset_id} — test results")
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
# 1. THE CORE PATTERN — 404 before generation, 200 after
# ─────────────────────────────────────────────────────────────────────────────

class TestCoreLifecycle:
    """
    Verifies the central "404 before, spec after" contract end-to-end.
    One dataset transitions through all three meaningful states.
    """

    def test_404_before_any_generation(self):
        """Completely unknown dataset_id → 404."""
        store = DashboardStore()
        assert get(store, new_id()).status_code == 404

    def test_404_when_dataset_known_but_no_dashboard(self):
        """Dataset registered but pipeline never ran → still 404."""
        store = DashboardStore()
        did = new_id()
        store.register_no_dashboard(did)
        assert get(store, did).status_code == 404

    def test_202_while_generation_in_progress(self):
        """Generation job queued/running → 202, not 404 or 200."""
        store = DashboardStore()
        did = new_id()
        store.register_in_progress(did, "running")
        assert get(store, did).status_code == 202

    def test_200_after_generation_complete(self):
        """Dashboard stored → 200 + full spec."""
        store = DashboardStore()
        did = new_id()
        spec = make_spec(dataset_id=did)
        store.register_dashboard(did, spec)
        assert get(store, did).status_code == 200

    def test_full_lifecycle_404_to_202_to_200(self):
        """Simulate the exact frontend polling sequence."""
        store = DashboardStore()
        did = new_id()

        # Phase 0: unknown
        assert get(store, did).status_code == 404

        # Phase 1: no dashboard yet (dataset registered, pipeline not run)
        store.register_no_dashboard(did)
        assert get(store, did).status_code == 404

        # Phase 2: generation started
        store.register_in_progress(did, "queued")
        assert get(store, did).status_code == 202

        # Phase 2b: generation running
        store.register_in_progress(did, "running")
        assert get(store, did).status_code == 202

        # Phase 3: generation complete
        spec = make_spec(dataset_id=did)
        store.register_dashboard(did, spec)
        assert get(store, did).status_code == 200

    def test_transition_from_202_to_200_on_same_id(self):
        """Once generation completes, the same dataset_id returns 200, not 202."""
        store = DashboardStore()
        did = new_id()
        store.register_in_progress(did, "running")
        assert get(store, did).status_code == 202

        spec = make_spec(dataset_id=did)
        store.register_dashboard(did, spec)   # generation done
        assert get(store, did).status_code == 200   # no longer 202

    def test_transition_from_404_to_200_directly(self):
        """If generation completes before any poll, goes 404 → 200 without 202."""
        store = DashboardStore()
        did = new_id()
        assert get(store, did).status_code == 404   # not known

        spec = make_spec(dataset_id=did)
        store.register_dashboard(did, spec)
        assert get(store, did).status_code == 200   # now available

    def test_200_is_stable_after_generation(self):
        """Repeated polls after generation always return 200."""
        store = DashboardStore()
        did = new_id()
        store.register_dashboard(did, make_spec(dataset_id=did))
        for _ in range(5):
            assert get(store, did).status_code == 200

    def test_different_datasets_independent_lifecycles(self):
        """Two datasets at different lifecycle stages don't interfere."""
        store = DashboardStore()
        did_before = new_id()
        did_after  = new_id()
        store.register_no_dashboard(did_before)
        store.register_dashboard(did_after, make_spec(dataset_id=did_after))
        assert get(store, did_before).status_code == 404
        assert get(store, did_after).status_code  == 200


# ─────────────────────────────────────────────────────────────────────────────
# 2. 404 — all "before" scenarios
# ─────────────────────────────────────────────────────────────────────────────

class TestNotFoundBeforeGeneration:

    def test_completely_unknown_id_returns_404(self):
        store = DashboardStore()
        assert get(store, new_id()).status_code == 404

    def test_dataset_registered_no_dashboard_returns_404(self):
        store = DashboardStore()
        did = new_id()
        store.register_no_dashboard(did)
        assert get(store, did).status_code == 404

    def test_404_body_has_detail(self):
        store = DashboardStore()
        body = get(store, new_id()).json()
        assert "detail" in body

    def test_404_detail_mentions_dataset_id(self):
        store = DashboardStore()
        did = new_id()
        assert did in get(store, did).json()["detail"]

    def test_404_ok_is_false(self):
        store = DashboardStore()
        assert get(store, new_id()).ok is False

    def test_multiple_unknown_ids_all_return_404(self):
        store = DashboardStore()
        for _ in range(5):
            assert get(store, new_id()).status_code == 404

    def test_wrong_id_for_existing_dashboard_returns_404(self):
        store = DashboardStore()
        did = new_id()
        store.register_dashboard(did, make_spec(dataset_id=did))
        assert get(store, new_id()).status_code == 404

    def test_empty_store_always_404(self):
        store = DashboardStore()
        for _ in range(3):
            assert get(store, new_id()).status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# 3. 202 — generation in progress
# ─────────────────────────────────────────────────────────────────────────────

class TestInProgress:

    def test_queued_job_returns_202(self):
        store = DashboardStore()
        did = new_id()
        store.register_in_progress(did, "queued")
        assert get(store, did).status_code == 202

    def test_running_job_returns_202(self):
        store = DashboardStore()
        did = new_id()
        store.register_in_progress(did, "running")
        assert get(store, did).status_code == 202

    def test_paused_job_returns_202(self):
        store = DashboardStore()
        did = new_id()
        store.register_in_progress(did, "paused")
        assert get(store, did).status_code == 202

    def test_all_generation_states_return_202(self):
        for state in GENERATION_STATES:
            store = DashboardStore()
            did = new_id()
            store.register_in_progress(did, state)
            assert get(store, did).status_code == 202, \
                f"State '{state}' should return 202"

    def test_202_body_has_detail(self):
        store = DashboardStore()
        did = new_id()
        store.register_in_progress(did, "running")
        assert "detail" in get(store, did).json()

    def test_202_body_has_status_field(self):
        store = DashboardStore()
        did = new_id()
        store.register_in_progress(did, "running")
        assert "status" in get(store, did).json()

    def test_202_status_field_matches_job_state(self):
        for state in GENERATION_STATES:
            store = DashboardStore()
            did = new_id()
            store.register_in_progress(did, state)
            assert get(store, did).json()["status"] == state

    def test_202_body_has_dataset_id(self):
        store = DashboardStore()
        did = new_id()
        store.register_in_progress(did, "running")
        assert get(store, did).json()["dataset_id"] == did

    def test_202_is_not_404(self):
        store = DashboardStore()
        did = new_id()
        store.register_in_progress(did, "queued")
        assert get(store, did).status_code != 404

    def test_202_ok_is_true(self):
        store = DashboardStore()
        did = new_id()
        store.register_in_progress(did, "running")
        assert get(store, did).ok is True


# ─────────────────────────────────────────────────────────────────────────────
# 4. 200 — dashboard ready: response shape
# ─────────────────────────────────────────────────────────────────────────────

class TestDashboardReadyShape:

    REQUIRED_KEYS = {
        "dataset_id", "domain", "kpi_cards", "charts",
        "narrative", "recommended_action", "generated_at",
    }

    def _body(self, domain: str = "finance") -> dict:
        store = DashboardStore()
        did = new_id()
        store.register_dashboard(did, make_spec(dataset_id=did, domain=domain))
        return get(store, did).json()

    def test_200_status_code(self):
        store = DashboardStore()
        did = new_id()
        store.register_dashboard(did, make_spec(dataset_id=did))
        assert get(store, did).status_code == 200

    def test_200_ok_is_true(self):
        store = DashboardStore()
        did = new_id()
        store.register_dashboard(did, make_spec(dataset_id=did))
        assert get(store, did).ok is True

    def test_content_type_json(self):
        store = DashboardStore()
        did = new_id()
        store.register_dashboard(did, make_spec(dataset_id=did))
        assert get(store, did).headers.get("Content-Type") == "application/json"

    def test_body_is_dict(self):
        assert isinstance(self._body(), dict)

    def test_all_required_keys_present(self):
        assert self.REQUIRED_KEYS.issubset(self._body().keys())

    def test_dataset_id_is_string(self):
        assert isinstance(self._body()["dataset_id"], str)

    def test_domain_is_string(self):
        assert isinstance(self._body()["domain"], str)

    def test_kpi_cards_is_list(self):
        assert isinstance(self._body()["kpi_cards"], list)

    def test_charts_is_list(self):
        assert isinstance(self._body()["charts"], list)

    def test_narrative_is_string(self):
        assert isinstance(self._body()["narrative"], str)

    def test_recommended_action_is_string(self):
        assert isinstance(self._body()["recommended_action"], str)

    def test_generated_at_is_string(self):
        assert isinstance(self._body()["generated_at"], str)

    def test_generated_at_is_iso8601(self):
        assert "T" in self._body()["generated_at"]


# ─────────────────────────────────────────────────────────────────────────────
# 5. dataset_id and domain fields
# ─────────────────────────────────────────────────────────────────────────────

class TestDatasetIdAndDomain:

    def test_dataset_id_echoed_in_200(self):
        store = DashboardStore()
        did = new_id()
        store.register_dashboard(did, make_spec(dataset_id=did))
        assert get(store, did).json()["dataset_id"] == did

    def test_domain_echoed_in_200(self):
        store = DashboardStore()
        did = new_id()
        store.register_dashboard(did, make_spec(dataset_id=did, domain="healthcare"))
        assert get(store, did).json()["domain"] == "healthcare"

    def test_all_valid_domains_returned_correctly(self):
        for domain in VALID_DOMAINS:
            store = DashboardStore()
            did = new_id()
            store.register_dashboard(did, make_spec(dataset_id=did, domain=domain))
            assert get(store, did).json()["domain"] == domain

    def test_dataset_id_non_empty(self):
        store = DashboardStore()
        did = new_id()
        store.register_dashboard(did, make_spec(dataset_id=did))
        assert len(get(store, did).json()["dataset_id"]) > 0

    def test_two_datasets_echo_own_ids(self):
        store = DashboardStore()
        did_a = new_id()
        did_b = new_id()
        store.register_dashboard(did_a, make_spec(dataset_id=did_a, domain="finance"))
        store.register_dashboard(did_b, make_spec(dataset_id=did_b, domain="healthcare"))
        assert get(store, did_a).json()["dataset_id"] == did_a
        assert get(store, did_b).json()["dataset_id"] == did_b
        assert get(store, did_a).json()["domain"] == "finance"
        assert get(store, did_b).json()["domain"] == "healthcare"


# ─────────────────────────────────────────────────────────────────────────────
# 6. KPI cards
# ─────────────────────────────────────────────────────────────────────────────

class TestKpiCards:

    REQUIRED_KPI_KEYS = {"label", "value", "change", "change_pct"}

    def _kpis(self, kpi_cards: Optional[list[KpiCard]] = None) -> list[dict]:
        store = DashboardStore()
        did = new_id()
        spec = make_spec(dataset_id=did, kpi_cards=kpi_cards)
        store.register_dashboard(did, spec)
        return get(store, did).json()["kpi_cards"]

    def test_kpi_cards_is_list(self):
        assert isinstance(self._kpis(), list)

    def test_two_kpi_cards_returned(self):
        cards = [KpiCard("Revenue", "$1M"), KpiCard("Margin", "60%")]
        assert len(self._kpis(cards)) == 2

    def test_three_kpi_cards_returned(self):
        cards = _default_kpis("finance")
        assert len(self._kpis(cards)) == 3

    def test_kpi_card_has_required_keys(self):
        card = self._kpis([KpiCard("Revenue", "$1M")])[0]
        assert self.REQUIRED_KPI_KEYS.issubset(card.keys())

    def test_kpi_label_preserved(self):
        card = self._kpis([KpiCard("Total Revenue", "$2.4M")])[0]
        assert card["label"] == "Total Revenue"

    def test_kpi_value_preserved(self):
        card = self._kpis([KpiCard("Gross Margin", "62%")])[0]
        assert card["value"] == "62%"

    def test_kpi_change_preserved(self):
        card = self._kpis([KpiCard("MRR", "$200K", change=8000.0)])[0]
        assert card["change"] == 8000.0

    def test_kpi_change_pct_preserved(self):
        card = self._kpis([KpiCard("MRR", "$200K", change_pct=4.2)])[0]
        assert abs(card["change_pct"] - 4.2) < 1e-9

    def test_kpi_change_none_when_absent(self):
        card = self._kpis([KpiCard("Metric", "100")])[0]
        assert card["change"] is None

    def test_kpi_change_pct_none_when_absent(self):
        card = self._kpis([KpiCard("Metric", "100")])[0]
        assert card["change_pct"] is None

    def test_kpi_cards_count_2_to_3(self):
        """Architecture spec: 2-3 KPI cards."""
        for n in [2, 3]:
            cards = [KpiCard(f"KPI {i}", str(i * 100)) for i in range(n)]
            count = len(self._kpis(cards))
            assert count == n

    def test_kpi_cards_order_preserved(self):
        cards = [KpiCard("A", "1"), KpiCard("B", "2"), KpiCard("C", "3")]
        returned = self._kpis(cards)
        assert [r["label"] for r in returned] == ["A", "B", "C"]

    def test_healthcare_kpi_cards(self):
        cards = _default_kpis("healthcare")
        returned = self._kpis(cards)
        labels = [r["label"] for r in returned]
        assert "Patient Volume" in labels
        assert "Avg LOS" in labels


# ─────────────────────────────────────────────────────────────────────────────
# 7. Charts
# ─────────────────────────────────────────────────────────────────────────────

class TestCharts:

    REQUIRED_CHART_KEYS = {
        "chart_type", "title", "data", "x_field", "y_field", "color_field"
    }

    def _charts(self, charts: Optional[list[ChartSpec]] = None) -> list[dict]:
        store = DashboardStore()
        did = new_id()
        spec = make_spec(dataset_id=did, charts=charts)
        store.register_dashboard(did, spec)
        return get(store, did).json()["charts"]

    def test_charts_is_list(self):
        assert isinstance(self._charts(), list)

    def test_two_charts_returned(self):
        assert len(self._charts(_default_charts())) == 2

    def test_chart_has_required_keys(self):
        chart = self._charts()[0]
        assert self.REQUIRED_CHART_KEYS.issubset(chart.keys())

    def test_bar_chart_type_preserved(self):
        charts = [ChartSpec("bar", "Revenue", [], "region", "revenue")]
        assert self._charts(charts)[0]["chart_type"] == "bar"

    def test_line_chart_type_preserved(self):
        charts = [ChartSpec("line", "Trend", [], "month", "revenue")]
        assert self._charts(charts)[0]["chart_type"] == "line"

    def test_table_chart_type_preserved(self):
        charts = [ChartSpec("table", "Detail", [], "sku", "margin")]
        assert self._charts(charts)[0]["chart_type"] == "table"

    def test_all_valid_chart_types_returned(self):
        for ct in VALID_CHART_TYPES:
            charts = [ChartSpec(ct, "Title", [], "x", "y")]
            assert self._charts(charts)[0]["chart_type"] == ct

    def test_chart_title_preserved(self):
        charts = [ChartSpec("bar", "Revenue by Region Q2", [], "region", "revenue")]
        assert self._charts(charts)[0]["title"] == "Revenue by Region Q2"

    def test_chart_data_preserved(self):
        data = [{"region": "APAC", "revenue": 800000}]
        charts = [ChartSpec("bar", "T", data, "region", "revenue")]
        assert self._charts(charts)[0]["data"] == data

    def test_chart_x_field_preserved(self):
        charts = [ChartSpec("bar", "T", [], "channel", "cpa")]
        assert self._charts(charts)[0]["x_field"] == "channel"

    def test_chart_y_field_preserved(self):
        charts = [ChartSpec("bar", "T", [], "channel", "cpa")]
        assert self._charts(charts)[0]["y_field"] == "cpa"

    def test_chart_color_field_none_when_absent(self):
        charts = [ChartSpec("bar", "T", [], "x", "y")]
        assert self._charts(charts)[0]["color_field"] is None

    def test_chart_color_field_preserved_when_set(self):
        charts = [ChartSpec("bar", "T", [], "x", "y", color_field="category")]
        assert self._charts(charts)[0]["color_field"] == "category"

    def test_chart_data_is_list(self):
        assert isinstance(self._charts()[0]["data"], list)

    def test_chart_order_preserved(self):
        charts = [ChartSpec("bar", "First", [], "x", "y"),
                  ChartSpec("line", "Second", [], "x", "y")]
        returned = self._charts(charts)
        assert returned[0]["title"] == "First"
        assert returned[1]["title"] == "Second"

    def test_charts_with_large_data_all_returned(self):
        data = [{"x": i, "y": i * 100} for i in range(50)]
        charts = [ChartSpec("bar", "Big Chart", data, "x", "y")]
        returned = self._charts(charts)[0]["data"]
        assert len(returned) == 50


# ─────────────────────────────────────────────────────────────────────────────
# 8. Narrative and recommended_action (InsightsAgent output)
# ─────────────────────────────────────────────────────────────────────────────

class TestNarrativeAndAction:

    def _body(self, narrative: str, action: str, domain: str = "finance") -> dict:
        store = DashboardStore()
        did = new_id()
        spec = make_spec(dataset_id=did, domain=domain,
                         narrative=narrative, recommended_action=action)
        store.register_dashboard(did, spec)
        return get(store, did).json()

    def test_narrative_preserved_verbatim(self):
        text = "Revenue grew 5.2% MoM driven by EMEA, reaching $2.4M total."
        body = self._body(text, "act")
        assert body["narrative"] == text

    def test_recommended_action_preserved_verbatim(self):
        action = "Expand EMEA sales team headcount by 3 before Q3."
        body = self._body("narrative text", action)
        assert body["recommended_action"] == action

    def test_narrative_is_non_empty(self):
        body = self._body("Some narrative.", "Some action.")
        assert len(body["narrative"].strip()) > 0

    def test_recommended_action_is_non_empty(self):
        body = self._body("Some narrative.", "Some action.")
        assert len(body["recommended_action"].strip()) > 0

    def test_finance_narrative_with_domain_vocabulary(self):
        narrative = ("MRR grew 4.2% to $200K. Gross margin held at 62% "
                     "despite rising COGS in APAC.")
        body = self._body(narrative, "Review APAC cost structure.", "finance")
        assert body["narrative"] == narrative

    def test_healthcare_narrative_preserved(self):
        narrative = ("Average LOS decreased 6.7% to 4.2 days. "
                     "ICU readmission rate within benchmark at 3.1%.")
        body = self._body(narrative, "Investigate ICU discharge protocols.", "healthcare")
        assert body["narrative"] == narrative

    def test_narrative_and_action_independent(self):
        n = "Revenue at $2.4M."
        a = "Hire 5 sales reps in EMEA."
        body = self._body(n, a)
        assert body["narrative"] == n
        assert body["recommended_action"] == a


# ─────────────────────────────────────────────────────────────────────────────
# 9. generated_at timestamp
# ─────────────────────────────────────────────────────────────────────────────

class TestGeneratedAt:

    def test_generated_at_preserved(self):
        ts = "2026-06-04T14:30:00Z"
        store = DashboardStore()
        did = new_id()
        store.register_dashboard(did, make_spec(dataset_id=did, generated_at=ts))
        assert get(store, did).json()["generated_at"] == ts

    def test_generated_at_contains_T(self):
        store = DashboardStore()
        did = new_id()
        store.register_dashboard(did, make_spec(dataset_id=did))
        assert "T" in get(store, did).json()["generated_at"]

    def test_generated_at_non_empty(self):
        store = DashboardStore()
        did = new_id()
        store.register_dashboard(did, make_spec(dataset_id=did))
        assert len(get(store, did).json()["generated_at"]) > 0

    def test_two_dashboards_can_have_different_timestamps(self):
        store = DashboardStore()
        did_a, did_b = new_id(), new_id()
        store.register_dashboard(did_a, make_spec(dataset_id=did_a, generated_at="2026-06-01T10:00:00Z"))
        store.register_dashboard(did_b, make_spec(dataset_id=did_b, generated_at="2026-06-02T10:00:00Z"))
        ts_a = get(store, did_a).json()["generated_at"]
        ts_b = get(store, did_b).json()["generated_at"]
        assert ts_a != ts_b


# ─────────────────────────────────────────────────────────────────────────────
# 10. Domain-specific dashboard specs
# ─────────────────────────────────────────────────────────────────────────────

class TestDomainSpecificDashboards:

    def test_finance_dashboard_has_mrr_kpi(self):
        store = DashboardStore()
        did = new_id()
        spec = make_spec(dataset_id=did, domain="finance",
                         kpi_cards=_default_kpis("finance"))
        store.register_dashboard(did, spec)
        labels = [k["label"] for k in get(store, did).json()["kpi_cards"]]
        assert any("MRR" in l or "Revenue" in l for l in labels)

    def test_healthcare_dashboard_has_los_kpi(self):
        store = DashboardStore()
        did = new_id()
        spec = make_spec(dataset_id=did, domain="healthcare",
                         kpi_cards=_default_kpis("healthcare"))
        store.register_dashboard(did, spec)
        labels = [k["label"] for k in get(store, did).json()["kpi_cards"]]
        assert any("LOS" in l or "Patient" in l for l in labels)

    def test_retail_dashboard(self):
        store = DashboardStore()
        did = new_id()
        charts = [
            ChartSpec("table", "SKU Margin by Channel", [], "sku", "margin"),
            ChartSpec("bar",   "Units Sold by Channel",  [], "channel", "units"),
        ]
        spec = make_spec(dataset_id=did, domain="retail", charts=charts)
        store.register_dashboard(did, spec)
        body = get(store, did).json()
        assert body["domain"] == "retail"
        assert len(body["charts"]) == 2

    def test_marketing_dashboard(self):
        store = DashboardStore()
        did = new_id()
        cards = [KpiCard("CTR", "3.4%"), KpiCard("CPA", "$12.50")]
        spec = make_spec(dataset_id=did, domain="marketing", kpi_cards=cards)
        store.register_dashboard(did, spec)
        body = get(store, did).json()
        assert body["domain"] == "marketing"
        labels = [k["label"] for k in body["kpi_cards"]]
        assert "CTR" in labels

    def test_all_domains_return_200(self):
        for domain in VALID_DOMAINS:
            store = DashboardStore()
            did = new_id()
            store.register_dashboard(did, make_spec(dataset_id=did, domain=domain))
            assert get(store, did).status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# 11. 401 — authentication
# ─────────────────────────────────────────────────────────────────────────────

class TestAuthentication:

    def test_no_token_returns_401(self):
        store = DashboardStore()
        did = new_id()
        store.register_dashboard(did, make_spec(dataset_id=did))
        assert get(store, did, token=None).status_code == 401

    def test_empty_token_returns_401(self):
        store = DashboardStore()
        did = new_id()
        store.register_dashboard(did, make_spec(dataset_id=did))
        assert get(store, did, token="").status_code == 401

    def test_whitespace_token_returns_401(self):
        store = DashboardStore()
        did = new_id()
        store.register_dashboard(did, make_spec(dataset_id=did))
        assert get(store, did, token="   ").status_code == 401

    def test_401_has_www_authenticate_bearer(self):
        store = DashboardStore()
        did = new_id()
        store.register_dashboard(did, make_spec(dataset_id=did))
        resp = get(store, did, token=None)
        assert resp.headers.get("WWW-Authenticate") == "Bearer"

    def test_401_body_has_detail(self):
        store = DashboardStore()
        did = new_id()
        store.register_dashboard(did, make_spec(dataset_id=did))
        assert "detail" in get(store, did, token=None).json()

    def test_invalid_token_returns_401(self):
        store = DashboardStore()
        did = new_id()
        store.register_dashboard(did, make_spec(dataset_id=did))
        store.set_unauthorized(did)
        assert get(store, did).status_code == 401

    def test_valid_token_returns_200(self):
        store = DashboardStore()
        did = new_id()
        store.register_dashboard(did, make_spec(dataset_id=did))
        assert get(store, did, token="Bearer my-token").status_code == 200

    def test_no_token_on_404_returns_401_not_404(self):
        """Auth check fires before the 404 check."""
        store = DashboardStore()
        resp = get(store, new_id(), token=None)
        assert resp.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# 12. 403 — authorisation
# ─────────────────────────────────────────────────────────────────────────────

class TestAuthorisation:

    def test_forbidden_dataset_returns_403(self):
        store = DashboardStore()
        did = new_id()
        store.register_dashboard(did, make_spec(dataset_id=did))
        store.set_forbidden(did)
        assert get(store, did).status_code == 403

    def test_403_body_has_detail(self):
        store = DashboardStore()
        did = new_id()
        store.register_dashboard(did, make_spec(dataset_id=did))
        store.set_forbidden(did)
        assert "detail" in get(store, did).json()

    def test_403_ok_is_false(self):
        store = DashboardStore()
        did = new_id()
        store.register_dashboard(did, make_spec(dataset_id=did))
        store.set_forbidden(did)
        assert get(store, did).ok is False

    def test_own_dashboard_not_forbidden(self):
        store = DashboardStore()
        did = new_id()
        store.register_dashboard(did, make_spec(dataset_id=did))
        assert get(store, did).status_code == 200

    def test_forbidden_on_one_does_not_affect_another(self):
        store = DashboardStore()
        bad = new_id()
        good = new_id()
        store.register_dashboard(bad,  make_spec(dataset_id=bad))
        store.register_dashboard(good, make_spec(dataset_id=good))
        store.set_forbidden(bad)
        assert get(store, bad).status_code  == 403
        assert get(store, good).status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# 13. 500 — server error
# ─────────────────────────────────────────────────────────────────────────────

class TestServerError:

    def test_server_error_returns_500(self):
        store = DashboardStore()
        did = new_id()
        store.register_dashboard(did, make_spec(dataset_id=did))
        store.set_server_error(did)
        assert get(store, did).status_code == 500

    def test_500_body_has_detail(self):
        store = DashboardStore()
        did = new_id()
        store.register_dashboard(did, make_spec(dataset_id=did))
        store.set_server_error(did)
        assert "detail" in get(store, did).json()

    def test_500_ok_is_false(self):
        store = DashboardStore()
        did = new_id()
        store.register_dashboard(did, make_spec(dataset_id=did))
        store.set_server_error(did)
        assert get(store, did).ok is False

    def test_server_error_on_one_does_not_affect_another(self):
        store = DashboardStore()
        bad  = new_id()
        good = new_id()
        store.register_dashboard(bad,  make_spec(dataset_id=bad))
        store.register_dashboard(good, make_spec(dataset_id=good))
        store.set_server_error(bad)
        assert get(store, bad).status_code  == 500
        assert get(store, good).status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# 14. Edge cases
# ─────────────────────────────────────────────────────────────────────────────

class TestEdgeCases:

    def test_body_is_json_serialisable(self):
        store = DashboardStore()
        did = new_id()
        store.register_dashboard(did, make_spec(dataset_id=did))
        body = get(store, did).json()
        try:
            json.dumps(body)
        except TypeError as exc:
            raise AssertionError(f"Body not serialisable: {exc}") from exc

    def test_repeated_calls_return_identical_body(self):
        store = DashboardStore()
        did = new_id()
        store.register_dashboard(did, make_spec(dataset_id=did))
        b1 = get(store, did).json()
        b2 = get(store, did).json()
        assert b1 == b2

    def test_dataset_id_with_hyphens_handled(self):
        store = DashboardStore()
        did = str(uuid.uuid4())
        store.register_dashboard(did, make_spec(dataset_id=did))
        assert get(store, did).status_code == 200

    def test_ten_dashboards_all_independent(self):
        store = DashboardStore()
        dids = [new_id() for _ in range(10)]
        for did in dids:
            store.register_dashboard(did, make_spec(dataset_id=did))
        for did in dids:
            resp = get(store, did)
            assert resp.status_code == 200
            assert resp.json()["dataset_id"] == did

    def test_validation_order_auth_before_404(self):
        """401 fires before 404 even for unknown ids."""
        store = DashboardStore()
        resp = get(store, new_id(), token=None)
        assert resp.status_code == 401

    def test_validation_order_403_before_404(self):
        """A forbidden-but-existing dataset returns 403, not 404."""
        store = DashboardStore()
        did = new_id()
        store.register_dashboard(did, make_spec(dataset_id=did))
        store.set_forbidden(did)
        assert get(store, did).status_code == 403

    def test_single_kpi_card_accepted(self):
        store = DashboardStore()
        did = new_id()
        spec = make_spec(dataset_id=did, kpi_cards=[KpiCard("Revenue", "$1M")])
        store.register_dashboard(did, spec)
        assert len(get(store, did).json()["kpi_cards"]) == 1

    def test_single_chart_accepted(self):
        store = DashboardStore()
        did = new_id()
        spec = make_spec(dataset_id=did,
                         charts=[ChartSpec("bar", "Revenue", [], "region", "revenue")])
        store.register_dashboard(did, spec)
        assert len(get(store, did).json()["charts"]) == 1

    def test_chart_with_empty_data_accepted(self):
        store = DashboardStore()
        did = new_id()
        spec = make_spec(dataset_id=did,
                         charts=[ChartSpec("bar", "Empty", [], "x", "y")])
        store.register_dashboard(did, spec)
        assert get(store, did).json()["charts"][0]["data"] == []

    def test_404_then_200_body_schema_correct(self):
        """After transition, 200 body must pass full shape checks."""
        store = DashboardStore()
        did = new_id()
        assert get(store, did).status_code == 404   # before
        store.register_dashboard(did, make_spec(dataset_id=did))
        body = get(store, did).json()               # after
        assert body["dataset_id"] == did
        assert isinstance(body["kpi_cards"], list)
        assert isinstance(body["charts"], list)
        assert isinstance(body["narrative"], str)
        assert isinstance(body["recommended_action"], str)


# ═════════════════════════════════════════════════════════════════════════════
# Runner
# ═════════════════════════════════════════════════════════════════════════════

def _collect_all_test_classes():
    return [
        TestCoreLifecycle,
        TestNotFoundBeforeGeneration,
        TestInProgress,
        TestDashboardReadyShape,
        TestDatasetIdAndDomain,
        TestKpiCards,
        TestCharts,
        TestNarrativeAndAction,
        TestGeneratedAt,
        TestDomainSpecificDashboards,
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