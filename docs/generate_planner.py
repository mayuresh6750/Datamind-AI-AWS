import openpyxl
from openpyxl.styles import (
    PatternFill, Font, Alignment, Border, Side, GradientFill
)
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

wb = openpyxl.Workbook()

# ── Colour palette ──────────────────────────────────────────────────────────
C = {
    "navy":      "1B3A6B",
    "blue":      "2563EB",
    "light_blue":"DBEAFE",
    "green":     "16A34A",
    "light_green":"DCFCE7",
    "orange":    "EA580C",
    "light_orange":"FEF3C7",
    "red":       "DC2626",
    "light_red": "FEE2E2",
    "purple":    "7C3AED",
    "light_purple":"EDE9FE",
    "teal":      "0D9488",
    "light_teal":"CCFBF1",
    "white":     "FFFFFF",
    "light_gray":"F8FAFC",
    "mid_gray":  "E2E8F0",
    "dark_gray":  "64748B",
    "yellow":    "FEF08A",
    "header_bg": "0F172A",
}

ROLE_COLORS = {
    "BE":  ("DBEAFE", "1D4ED8"),
    "FE":  ("FCE7F3", "9D174D"),
    "AI":  ("EDE9FE", "5B21B6"),
    "DO":  ("DCFCE7", "15803D"),
    "QA":  ("FEF3C7", "92400E"),
    "ALL": ("F1F5F9", "334155"),
}

PRIORITY_COLORS = {
    "P1": ("FEE2E2", "DC2626"),
    "P2": ("FEF3C7", "92400E"),
    "P3": ("F0FDF4", "15803D"),
}

STATUS_COLORS = {
    "Not Started": ("F8FAFC", "64748B"),
    "In Progress": ("DBEAFE", "1D4ED8"),
    "Done":        ("DCFCE7", "15803D"),
    "Blocked":     ("FEE2E2", "DC2626"),
}

def fill(hex_color):
    return PatternFill("solid", fgColor=hex_color)

def font(bold=False, color="000000", size=11, italic=False):
    return Font(bold=bold, color=color, size=size, italic=italic,
                name="Calibri")

def border(style="thin"):
    s = Side(style=style, color="CBD5E1")
    return Border(left=s, right=s, top=s, bottom=s)

def center():
    return Alignment(horizontal="center", vertical="center", wrap_text=True)

def left():
    return Alignment(horizontal="left", vertical="center", wrap_text=True)

def apply_header(ws, row, col, value, bg=C["header_bg"], fg=C["white"],
                 bold=True, size=11):
    c = ws.cell(row=row, column=col, value=value)
    c.fill = fill(bg)
    c.font = font(bold=bold, color=fg, size=size)
    c.alignment = center()
    c.border = border()
    return c

def apply_cell(ws, row, col, value, bg=C["white"], fg="000000",
               bold=False, align="left"):
    c = ws.cell(row=row, column=col, value=value)
    c.fill = fill(bg)
    c.font = font(bold=bold, color=fg)
    c.alignment = left() if align == "left" else center()
    c.border = border()
    return c

# ────────────────────────────────────────────────────────────────────────────
# DATA
# ────────────────────────────────────────────────────────────────────────────

SPRINTS = [
    {
        "name": "Sprint 1 — Foundation",
        "dates": "May 6–9, 2026",
        "goal": "Repo live, auth working, infra provisioned, CI/CD green",
        "exit": "User can sign up, log in, hit /health. CI/CD deploys to staging.",
        "color": "DBEAFE",
        "tasks": [
            ("S1-01","Set up Git repo, branch strategy, PR template, CODEOWNERS","DO","P1",1,"—"),
            ("S1-02","GitHub Actions CI/CD — lint, typecheck, unit tests, Docker build, staging deploy","DO","P1",3,"S1-01"),
            ("S1-03","Provision AWS infra — S3 buckets (raw/curated/state/audit), RDS Postgres, Redis, IAM","DO","P1",3,"—"),
            ("S1-04","Docker Compose for local dev — Postgres (pgvector) + Redis","DO","P1",2,"—"),
            ("S1-05","FastAPI project structure — routers, middleware, dependencies, pyproject.toml","BE","P1",2,"S1-04"),
            ("S1-06","DB schema + Alembic migrations — users, tenants, datasets, pipeline_runs, hitl_decisions, audit_events, jobs, llm_provider_config","BE","P1",3,"S1-03,S1-04"),
            ("S1-07","JWT auth endpoints — /auth/signup, /auth/login, /auth/refresh, /auth/logout","BE","P1",3,"S1-06"),
            ("S1-08","RBAC middleware — role claim enforcement on every FastAPI route","BE","P1",2,"S1-07"),
            ("S1-09","GET /health — checks DB, Redis, S3 connectivity","BE","P1",1,"S1-05,S1-03"),
            ("S1-10","Next.js 14 setup — TypeScript, Tailwind CSS, shadcn/ui, pnpm workspace","FE","P1",2,"—"),
            ("S1-11","Sign up / Sign in screens (U1) — form validation, JWT storage, redirect logic","FE","P1",3,"S1-07,S1-10"),
            ("S1-12",".env.example, local dev README, team onboarding docs","DO","P2",1,"S1-04"),
        ]
    },
    {
        "name": "Sprint 2 — Ingestion + Domain",
        "dates": "May 12–16, 2026",
        "goal": "Multi-file upload working. Domain persists. HITL #1 screen renders.",
        "exit": "Domain persists to DB. Multi-file upload accepted. Schema preview visible.",
        "color": "EDE9FE",
        "tasks": [
            ("S2-01","Domain selection screen (U2) — first-run modal, 6 options, free-text for Other","FE","P1",2,"S1-11"),
            ("S2-02","PATCH /me/domain — update active domain on user profile","BE","P1",1,"S1-08"),
            ("S2-03","File upload screen (U3) — drag-and-drop, multi-file, format validation, progress bar","FE","P1",3,"S1-11"),
            ("S2-04","POST /datasets/upload-url — generate presigned S3 URLs for direct browser upload","BE","P1",2,"S1-08"),
            ("S2-05","POST /datasets/{id}/ingest — enqueue Celery ingestion job, return job_id","BE","P1",2,"S2-04"),
            ("S2-06","Ingestion Agent — format detection (mime + content sniff) CSV/XLSX/JSON/Parquet","AI","P1",3,"S1-05"),
            ("S2-07","Ingestion Agent — parsing + column profiling (dtype, null count, distinct, avg length)","AI","P1",3,"S2-06"),
            ("S2-08","Ingestion Agent — multi-file merge plan (UNION vs JOIN, merge key, confidence)","AI","P1",3,"S2-07"),
            ("S2-09","Column type classification — numeric / textual / ambiguous routing rules","AI","P1",2,"S2-07"),
            ("S2-10","Domain Agent — prompt pack loader, Postgres lookup per domain","AI","P1",2,"S1-06"),
            ("S2-11","Domain prompt packs — Finance, Healthcare, Retail, Marketing, Other (YAML, versioned)","AI","P1",4,"S2-10"),
            ("S2-12","GET /jobs/{id} — poll job status, progress %, current step","BE","P1",2,"S2-05"),
        ]
    },
    {
        "name": "Sprint 3 — HITL #1 + Cleaning Plan + LLM Abstraction",
        "dates": "May 19–23, 2026",
        "goal": "Cleaning plan generated. HITL #1 screen done. LLM abstraction live.",
        "exit": "Cleaning plan generated and displayed. ≥ 60% acceptance on golden datasets 1–5.",
        "color": "DCFCE7",
        "tasks": [
            ("S3-01","Schema & merge validation screen (HITL #1, U4) — schema table, type-routing badges, merge plan","FE","P1",4,"S2-03,S2-12"),
            ("S3-02","HITL #1 interactions — type-routing override, merge key change, exclude column/file","FE","P1",3,"S3-01"),
            ("S3-03","GET /datasets/{id}/merge-plan — return ingestion profile with schema + merge proposal","BE","P1",2,"S2-05"),
            ("S3-04","POST /datasets/{id}/merge-plan/decision — record decision in hitl_decisions, enqueue next","BE","P1",2,"S3-03"),
            ("S3-05","Pipeline supervisor — state machine, step routing, HITL pause/resume, retry on failure","AI","P1",4,"S1-05"),
            ("S3-06","HITL Gate Manager — pause_pipeline_for_decision(), resume_pipeline_with_decision()","AI","P1",3,"S3-05"),
            ("S3-07","Pipeline state persistence — serialise state to S3 + Postgres after every agent step","BE","P1",3,"S3-05,S1-03"),
            ("S3-08","LLM Provider Abstraction — LiteLLM-compatible, structured_completion(), Pydantic validation, retry (3×)","AI","P1",4,"S1-05"),
            ("S3-09","Anthropic Claude provider — Secrets Manager key, structured JSON, token/cost/latency logging","AI","P1",2,"S3-08"),
            ("S3-10","OpenAI provider — Secrets Manager key, structured JSON, token/cost/latency logging","AI","P1",2,"S3-08"),
            ("S3-11","Cleaning Plan Agent — exact dedup + imputation strategy (median/mean/mode/drop/leave)","AI","P1",3,"S3-05,S3-08"),
            ("S3-12","Cleaning Plan Agent — type coercion proposals + basic outlier flagging (no auto-fix)","AI","P1",3,"S3-11"),
            ("S3-13","Confidence scoring — 0.0–1.0 per step, colour thresholds (red/orange/yellow)","AI","P1",2,"S3-11"),
            ("S3-14","GET /datasets/{id}/cleaning-plan — return numbered steps with rationale + confidence","BE","P1",1,"S3-11"),
        ]
    },
    {
        "name": "Sprint 4 — HITL #2 + Storage + Analysis + Dashboard",
        "dates": "May 26–30, 2026",
        "goal": "Full end-to-end pipeline working. Dashboard renders within 90s.",
        "exit": "E2E happy path works for CSV and Parquet merge. Dashboard renders within 90s.",
        "color": "FEF3C7",
        "tasks": [
            ("S4-01","Cleaning plan review screen (HITL #2, U5) — numbered steps, confidence badges, per-step controls","FE","P1",4,"S3-01,S3-14"),
            ("S4-02","Modify step UI — imputation strategy picker, column exclusion, custom value input","FE","P1",3,"S4-01"),
            ("S4-03","POST /datasets/{id}/cleaning-plan/decision — record approved/modified/rejected steps","BE","P1",2,"S3-04"),
            ("S4-04","Cleaning Executor Agent — run only approved steps, write audit event per step","AI","P1",3,"S3-11,S4-03"),
            ("S4-05","Write cleaned data to curated S3 Parquet (Layer 2) — versioned per cleaning run","BE","P1",2,"S4-04"),
            ("S4-06","Load numeric columns into Postgres table (Layer 3) — one typed table per dataset_id","BE","P1",3,"S4-05"),
            ("S4-07","Embed textual columns + load into pgvector (Layer 4) — HNSW index, per-tenant namespace","AI","P1",3,"S4-05"),
            ("S4-08","Intent capture screen (U6) — free-text input, domain suggestion chips, HITL #3 confirmation","FE","P1",3,"S4-01"),
            ("S4-09","POST /datasets/{id}/intent — submit intent, return restated interpretation for HITL #3","BE","P1",1,"S4-05"),
            ("S4-10","Intent Agent — free-text → structured AnalysisSpec, biased by domain pack + schema","AI","P1",3,"S3-08,S3-05"),
            ("S4-11","Analysis Agent — SQL builder (sqlglot) + DuckDB runner for numeric (Layer 3)","AI","P1",3,"S4-06,S4-10"),
            ("S4-12","Analysis Agent — pgvector semantic search for textual questions (Layer 4)","AI","P1",3,"S4-07,S4-10"),
            ("S4-13","SQL safety validation — sqlglot parse, block all non-SELECT statements","BE","P1",2,"S4-11"),
            ("S4-14","POST /dashboards/generate — enqueue dashboard job, return job_id","BE","P1",1,"S4-11"),
            ("S4-15","Dashboard Agent — Vega-Lite spec (2–3 KPI cards + 2 charts: bar/line/table)","AI","P1",4,"S4-11,S4-12"),
            ("S4-16","Insights Agent — domain-flavoured narrative + recommended action, factual consistency check","AI","P1",3,"S4-15"),
            ("S4-17","Dashboard screen (U7) — render KPI cards + Vega-Lite charts + narrative, poll until ready","FE","P1",4,"S4-15"),
        ]
    },
    {
        "name": "Sprint 5 — Admin UI + QA + Hardening",
        "dates": "Jun 2–6, 2026",
        "goal": "Internal beta ready. All Phase 1 acceptance criteria met.",
        "exit": "Internal beta with 5 users for 1 week. All NFR targets verified.",
        "color": "FEE2E2",
        "tasks": [
            ("S5-01","Admin UI — System Health (A1): pipeline status, queue depth, error rates","FE","P1",2,"S1-11"),
            ("S5-02","Admin UI — User & Role Management (A2): list, invite, suspend, change role","FE","P1",3,"S5-01"),
            ("S5-03","Admin UI — LLM Provider Config (A3): provider, model, per-agent routing","FE","P1",3,"S5-01"),
            ("S5-04","Admin UI — Domain Pack Viewer (A4): read-only pack viewer","FE","P2",2,"S5-01"),
            ("S5-05","Admin UI — Audit Log Viewer (A5): search HITL decisions + cleaning actions","FE","P1",2,"S5-01"),
            ("S5-06","History / Audit screen for users (U8): past runs, downloadable audit log (JSON/CSV)","FE","P2",2,"S4-17"),
            ("S5-07","All admin API endpoints — /admin/users, /admin/llm-providers, /admin/domain-packs, /admin/health, /admin/audit","BE","P1",4,"S1-08"),
            ("S5-08","GET /jobs/{id}/audit — return full audit log for a pipeline run","BE","P1",1,"S4-04"),
            ("S5-09","AWS Secrets Manager integration — retrieve LLM API keys per tenant at runtime","DO","P1",2,"S3-09,S3-10"),
            ("S5-10","CloudWatch structured logging — JSON logs per request + per agent step","DO","P1",2,"S1-02"),
            ("S5-11","CloudWatch alerting — all 7 alert conditions (failure rate, latency, S3, LLM error, HITL queue, spend, confidence)","DO","P1",3,"S5-10"),
            ("S5-12","Staging deployment — ECS task definition, ECR image, RDS migration on deploy","DO","P1",3,"S1-02,S1-03"),
            ("S5-13","Unit tests — agent functions, transform logic, API handlers (≥ 70% coverage)","QA","P1",3,"S4-16"),
            ("S5-14","Integration tests — agent-to-agent, S3, DuckDB, pgvector (happy paths + key errors)","QA","P1",3,"S4-16"),
            ("S5-15","E2E tests — single-file pipeline for all 4 formats (CSV, XLSX, JSON, Parquet)","QA","P1",4,"S4-17"),
            ("S5-16","E2E tests — multi-file (2-file + 5-file, union + join paths)","QA","P1",3,"S4-17"),
            ("S5-17","HITL flow tests — all decision branches per gate (#1, #2, #3)","QA","P1",3,"S4-17"),
            ("S5-18","RBAC enforcement tests — 403 for all admin routes with non-admin token","QA","P1",2,"S5-07"),
            ("S5-19","LLM portability tests — full pipeline on Claude + OpenAI, no quality regression","QA","P1",3,"S5-14"),
            ("S5-20","Performance tests — 50MB file, p95 dashboard latency < 90s, HITL cycle < 90s median","QA","P1",2,"S5-15"),
            ("S5-21","Golden dataset validation — 10 datasets, ≥ 70% cleaning acceptance","QA","P1",4,"S5-15"),
            ("S5-22","Bug fixes + polish from QA findings","ALL","P1",4,"S5-21"),
            ("S5-23","Internal beta setup — 5 users onboarded, staging access, feedback collection","DO","P1",2,"S5-12"),
        ]
    },
]

COLUMNS = [
    ("Task ID",     10),
    ("Task Name",   52),
    ("Role",         8),
    ("Assignee",    16),
    ("Priority",     9),
    ("Points",       7),
    ("Status",      14),
    ("Start Date",  13),
    ("Due Date",    13),
    ("Depends On",  14),
    ("Notes",       22),
]

STATUS_OPTIONS = '"Not Started,In Progress,Done,Blocked"'

# ────────────────────────────────────────────────────────────────────────────
# SHEET 1 — OVERVIEW
# ────────────────────────────────────────────────────────────────────────────

ws_ov = wb.active
ws_ov.title = "📊 Overview"
ws_ov.sheet_view.showGridLines = False
ws_ov.column_dimensions["A"].width = 32
ws_ov.column_dimensions["B"].width = 16
ws_ov.column_dimensions["C"].width = 16
ws_ov.column_dimensions["D"].width = 16
ws_ov.column_dimensions["E"].width = 16
ws_ov.column_dimensions["F"].width = 16

# Title
ws_ov.merge_cells("A1:F1")
c = ws_ov["A1"]
c.value = "DataMind AI — Phase 1 Sprint Planner"
c.fill = fill(C["header_bg"])
c.font = Font(bold=True, color=C["white"], size=18, name="Calibri")
c.alignment = center()
ws_ov.row_dimensions[1].height = 36

ws_ov.merge_cells("A2:F2")
c = ws_ov["A2"]
c.value = "Team Lead: Smita  |  Phase 1: May 6 – June 10, 2026  |  5 Sprints  |  78 Tasks"
c.fill = fill(C["blue"])
c.font = Font(bold=False, color=C["white"], size=11, name="Calibri")
c.alignment = center()
ws_ov.row_dimensions[2].height = 22

ws_ov.row_dimensions[3].height = 8

# Sprint summary headers
headers_ov = ["Sprint", "Dates", "Tasks", "Points", "Status", "Completion %"]
for i, h in enumerate(headers_ov, 1):
    apply_header(ws_ov, 4, i, h, bg=C["navy"])
ws_ov.row_dimensions[4].height = 24

sprint_summary = [
    ("Sprint 1 — Foundation",                 "May 6–9",   12, 26),
    ("Sprint 2 — Ingestion + Domain",         "May 12–16", 12, 29),
    ("Sprint 3 — HITL #1 + Cleaning + LLM",  "May 19–23", 14, 38),
    ("Sprint 4 — HITL #2 + Storage + Dashboard","May 26–30",17, 46),
    ("Sprint 5 — Admin UI + QA + Hardening",  "Jun 2–6",   23, 63),
]

row_colors = [C["light_blue"], "EDE9FE", C["light_green"], "FEF3C7", C["light_red"]]
for idx, (name, dates, tasks, pts) in enumerate(sprint_summary):
    r = 5 + idx
    bg = row_colors[idx]
    apply_cell(ws_ov, r, 1, name,  bg=bg, bold=True)
    apply_cell(ws_ov, r, 2, dates, bg=bg, align="center")
    apply_cell(ws_ov, r, 3, tasks, bg=bg, align="center")
    apply_cell(ws_ov, r, 4, pts,   bg=bg, align="center")
    apply_cell(ws_ov, r, 5, "Not Started", bg=bg, align="center")
    apply_cell(ws_ov, r, 6, "0%",          bg=bg, align="center")
    ws_ov.row_dimensions[r].height = 22

# Total row
r = 10
apply_cell(ws_ov, r, 1, "TOTAL", bg=C["navy"], fg=C["white"], bold=True, align="center")
apply_cell(ws_ov, r, 2, "May 6 – Jun 10", bg=C["navy"], fg=C["white"], align="center")
apply_cell(ws_ov, r, 3, 78,  bg=C["navy"], fg=C["white"], align="center")
apply_cell(ws_ov, r, 4, 202, bg=C["navy"], fg=C["white"], align="center")
apply_cell(ws_ov, r, 5, "",  bg=C["navy"], fg=C["white"], align="center")
apply_cell(ws_ov, r, 6, "",  bg=C["navy"], fg=C["white"], align="center")
ws_ov.row_dimensions[r].height = 24

# Role legend
ws_ov.row_dimensions[12].height = 8
apply_header(ws_ov, 13, 1, "Role Legend", bg=C["dark_gray"], size=10)
ws_ov.merge_cells("B13:F13")
apply_header(ws_ov, 13, 2, "", bg=C["dark_gray"])

roles = [
    ("BE — Backend Developer", ROLE_COLORS["BE"]),
    ("FE — Frontend Developer", ROLE_COLORS["FE"]),
    ("AI — AI / Agent Engineer", ROLE_COLORS["AI"]),
    ("DO — DevOps / Infra", ROLE_COLORS["DO"]),
    ("QA — QA Engineer", ROLE_COLORS["QA"]),
]
for i, (label, (bg, fg)) in enumerate(roles):
    apply_cell(ws_ov, 14 + i, 1, label, bg=bg, fg=fg, bold=True)
    ws_ov.merge_cells(f"B{14+i}:F{14+i}")
    apply_cell(ws_ov, 14 + i, 2, "", bg=bg)

# Status legend
ws_ov.row_dimensions[20].height = 8
apply_header(ws_ov, 21, 1, "Status Legend", bg=C["dark_gray"], size=10)
ws_ov.merge_cells("B21:F21")
apply_header(ws_ov, 21, 2, "", bg=C["dark_gray"])

statuses = [
    ("Not Started", STATUS_COLORS["Not Started"]),
    ("In Progress", STATUS_COLORS["In Progress"]),
    ("Done",        STATUS_COLORS["Done"]),
    ("Blocked",     STATUS_COLORS["Blocked"]),
]
for i, (label, (bg, fg)) in enumerate(statuses):
    apply_cell(ws_ov, 22 + i, 1, label, bg=bg, fg=fg, bold=True)
    ws_ov.merge_cells(f"B{22+i}:F{22+i}")
    apply_cell(ws_ov, 22 + i, 2, "", bg=bg)

# ────────────────────────────────────────────────────────────────────────────
# SPRINT SHEETS
# ────────────────────────────────────────────────────────────────────────────

for sprint in SPRINTS:
    short = sprint["name"].split("—")[0].strip().replace(" ", "")  # "Sprint1"
    ws = wb.create_sheet(title=short)
    ws.sheet_view.showGridLines = False

    # Set column widths
    for col_i, (_, width) in enumerate(COLUMNS, 1):
        ws.column_dimensions[get_column_letter(col_i)].width = width

    # Title row
    ws.merge_cells(f"A1:{get_column_letter(len(COLUMNS))}1")
    c = ws["A1"]
    c.value = sprint["name"]
    c.fill = fill(C["header_bg"])
    c.font = Font(bold=True, color=C["white"], size=14, name="Calibri")
    c.alignment = center()
    ws.row_dimensions[1].height = 32

    # Dates + goal row
    ws.merge_cells(f"A2:{get_column_letter(len(COLUMNS))}2")
    c = ws["A2"]
    c.value = f"{sprint['dates']}  |  Goal: {sprint['goal']}"
    c.fill = fill(sprint["color"])
    c.font = Font(bold=False, color="1E293B", size=10, name="Calibri")
    c.alignment = center()
    ws.row_dimensions[2].height = 20

    # Exit criteria row
    ws.merge_cells(f"A3:{get_column_letter(len(COLUMNS))}3")
    c = ws["A3"]
    c.value = f"Exit Criteria: {sprint['exit']}"
    c.fill = fill(C["mid_gray"])
    c.font = Font(bold=False, color=C["dark_gray"], size=9, italic=True, name="Calibri")
    c.alignment = center()
    ws.row_dimensions[3].height = 18

    ws.row_dimensions[4].height = 6  # spacer

    # Column headers
    for col_i, (name, _) in enumerate(COLUMNS, 1):
        apply_header(ws, 5, col_i, name, bg=C["navy"])
    ws.row_dimensions[5].height = 24

    # Freeze panes
    ws.freeze_panes = "A6"

    # Data rows
    dv = DataValidation(type="list", formula1=STATUS_OPTIONS, allow_blank=True)
    ws.add_data_validation(dv)

    for row_idx, task in enumerate(sprint["tasks"]):
        task_id, name, role, priority, points, depends = task
        r = 6 + row_idx
        ws.row_dimensions[r].height = 22

        role_bg, role_fg = ROLE_COLORS.get(role, ("FFFFFF", "000000"))
        pri_bg, pri_fg = PRIORITY_COLORS.get(priority, ("FFFFFF", "000000"))
        row_bg = C["white"] if row_idx % 2 == 0 else C["light_gray"]

        apply_cell(ws, r, 1,  task_id,  bg=row_bg, bold=True, align="center")
        apply_cell(ws, r, 2,  name,     bg=row_bg)
        apply_cell(ws, r, 3,  role,     bg=role_bg, fg=role_fg, bold=True, align="center")
        apply_cell(ws, r, 4,  "",       bg=row_bg)           # Assignee (blank)
        apply_cell(ws, r, 5,  priority, bg=pri_bg, fg=pri_fg, bold=True, align="center")
        apply_cell(ws, r, 6,  points,   bg=row_bg, align="center")
        # Status cell with dropdown
        status_cell = ws.cell(row=r, column=7, value="Not Started")
        status_cell.fill = fill(STATUS_COLORS["Not Started"][0])
        status_cell.font = font(color=STATUS_COLORS["Not Started"][1])
        status_cell.alignment = center()
        status_cell.border = border()
        dv.sqref = dv.sqref
        dv.add(status_cell)

        apply_cell(ws, r, 8,  "",       bg=row_bg, align="center")  # Start date
        apply_cell(ws, r, 9,  "",       bg=row_bg, align="center")  # Due date
        apply_cell(ws, r, 10, depends,  bg=row_bg, align="center")
        apply_cell(ws, r, 11, "",       bg=row_bg)                   # Notes

    # Summary row
    r = 6 + len(sprint["tasks"])
    total_pts = sum(t[4] for t in sprint["tasks"])
    ws.merge_cells(f"A{r}:E{r}")
    c = ws.cell(row=r, column=1, value=f"Sprint Total: {len(sprint['tasks'])} tasks")
    c.fill = fill(C["navy"])
    c.font = Font(bold=True, color=C["white"], size=11, name="Calibri")
    c.alignment = center()
    c.border = border()

    pts_c = ws.cell(row=r, column=6, value=total_pts)
    pts_c.fill = fill(C["navy"])
    pts_c.font = Font(bold=True, color=C["white"], size=11, name="Calibri")
    pts_c.alignment = center()
    pts_c.border = border()

    for col in range(7, len(COLUMNS) + 1):
        c = ws.cell(row=r, column=col, value="")
        c.fill = fill(C["navy"])
        c.border = border()

    ws.row_dimensions[r].height = 24

# ────────────────────────────────────────────────────────────────────────────
# SHEET — MASTER TRACKER (all sprints in one view)
# ────────────────────────────────────────────────────────────────────────────

ws_m = wb.create_sheet(title="🗂 Master Tracker")
ws_m.sheet_view.showGridLines = False

for col_i, (_, width) in enumerate(COLUMNS, 1):
    ws_m.column_dimensions[get_column_letter(col_i)].width = width

ws_m.merge_cells(f"A1:{get_column_letter(len(COLUMNS))}1")
c = ws_m["A1"]
c.value = "DataMind AI — Phase 1 Master Task Tracker"
c.fill = fill(C["header_bg"])
c.font = Font(bold=True, color=C["white"], size=14, name="Calibri")
c.alignment = center()
ws_m.row_dimensions[1].height = 32

for col_i, (name, _) in enumerate(COLUMNS, 1):
    apply_header(ws_m, 2, col_i, name, bg=C["navy"])
ws_m.row_dimensions[2].height = 24
ws_m.freeze_panes = "A3"

dv_m = DataValidation(type="list", formula1=STATUS_OPTIONS, allow_blank=True)
ws_m.add_data_validation(dv_m)

current_row = 3
row_colors_sprint = ["DBEAFE", "EDE9FE", "DCFCE7", "FEF3C7", "FEE2E2"]

for s_idx, sprint in enumerate(SPRINTS):
    # Sprint banner
    ws_m.merge_cells(f"A{current_row}:{get_column_letter(len(COLUMNS))}{current_row}")
    c = ws_m.cell(row=current_row, column=1, value=f"  {sprint['name']}  |  {sprint['dates']}")
    c.fill = fill(C["navy"])
    c.font = Font(bold=True, color=C["white"], size=11, name="Calibri")
    c.alignment = left()
    c.border = border()
    ws_m.row_dimensions[current_row].height = 22
    current_row += 1

    for row_idx, task in enumerate(sprint["tasks"]):
        task_id, name, role, priority, points, depends = task
        r = current_row
        ws_m.row_dimensions[r].height = 20

        role_bg, role_fg = ROLE_COLORS.get(role, ("FFFFFF", "000000"))
        pri_bg, pri_fg = PRIORITY_COLORS.get(priority, ("FFFFFF", "000000"))
        row_bg = C["white"] if row_idx % 2 == 0 else C["light_gray"]

        apply_cell(ws_m, r, 1,  task_id,  bg=row_bg, bold=True, align="center")
        apply_cell(ws_m, r, 2,  name,     bg=row_bg)
        apply_cell(ws_m, r, 3,  role,     bg=role_bg, fg=role_fg, bold=True, align="center")
        apply_cell(ws_m, r, 4,  "",       bg=row_bg)
        apply_cell(ws_m, r, 5,  priority, bg=pri_bg, fg=pri_fg, bold=True, align="center")
        apply_cell(ws_m, r, 6,  points,   bg=row_bg, align="center")
        sc = ws_m.cell(row=r, column=7, value="Not Started")
        sc.fill = fill(STATUS_COLORS["Not Started"][0])
        sc.font = font(color=STATUS_COLORS["Not Started"][1])
        sc.alignment = center()
        sc.border = border()
        dv_m.add(sc)
        apply_cell(ws_m, r, 8,  "", bg=row_bg, align="center")
        apply_cell(ws_m, r, 9,  "", bg=row_bg, align="center")
        apply_cell(ws_m, r, 10, depends, bg=row_bg, align="center")
        apply_cell(ws_m, r, 11, "", bg=row_bg)
        current_row += 1

    current_row += 1  # spacer between sprints

# ────────────────────────────────────────────────────────────────────────────
# Save
# ────────────────────────────────────────────────────────────────────────────
out_path = r"C:\Users\Smita\GenAI\Datamind\DataMind_Phase1_Planner.xlsx"
wb.save(out_path)
print(f"Saved: {out_path}")
