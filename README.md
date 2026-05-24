# DataMind AI

**An Agentic Platform for End-to-End Business Data Intelligence**

From raw data → cleaned data → context-aware dashboards → business decisions.

DataMind AI is an agentic data intelligence platform that takes a business user from raw, messy files to a clean, contextual dashboard — and a recommended business decision — without writing a line of SQL or Python.

---

## Core Principles

1. **Domain-first approach** — Ask users their domain so all agents apply domain-appropriate vocabulary, KPIs, and validation rules
2. **User-controlled data modeling** — Accept multiple files (CSV, XLSX, JSON, Parquet) and let users decide how to merge/model them
3. **Human-in-the-loop (HITL) cleaning** — Every cleaning step is proposed as a plan; users approve/modify/reject before execution
4. **Type-aware storage routing** — Numeric/structured data → relational stores; free-text → vector stores

---

## Technology Stack

| Layer | Technology |
|-------|------------|
| Frontend | Next.js 14, TypeScript, Tailwind CSS, shadcn/ui, Recharts |
| Backend | Python 3.11+, FastAPI, Pydantic v2, Celery + Redis |
| Agent Orchestration | LangGraph (supervisor pattern) |
| LLM Provider | LiteLLM abstraction; Mistral + Moonshot Kimi (Phase 1) |
| Layer 1 — Raw Storage | Supabase Storage (versioned, per-user prefix) |
| Layer 2 — Curated Storage | Supabase Storage, Apache Parquet |
| Layer 3 — Numeric/Structured | Supabase Database (PostgreSQL) + DuckDB |
| Layer 4 — Textual/Semantic | Weaviate (HNSW index, cosine similarity) |
| Secrets | Supabase Vault |
| Observability | Prometheus + Grafana |
| CI/CD | GitHub Actions |
| IaC | Terraform |

---

## Architecture

### Four-Layer Storage

| Layer | Content | Engine |
|-------|---------|--------|
| Layer 1 | Original files (immutable) | Supabase Storage |
| Layer 2 | Cleaned Parquet | Supabase Storage |
| Layer 3 | Numeric, boolean, date, categorical | PostgreSQL + DuckDB |
| Layer 4 | Free-text embeddings | Weaviate |

### Agent System (Phase 1)

| Agent | Role |
|-------|------|
| Supervisor | Orchestrates pipeline; routes, retries, aggregates; enforces HITL gates |
| Domain | Loads domain prompt pack (vocabulary, KPIs, validation rules) |
| Ingestion | Detects format, parses, profiles, classifies columns, drafts merge plan |
| Cleaning Plan | Drafts numbered cleaning plan with rationale + confidence. Does NOT execute. |
| Cleaning Executor | Executes only user-approved steps, logs each action |
| Intent | Parses natural-language goal into structured analysis spec |
| Analysis | Runs SQL on numeric data (DuckDB/Postgres); semantic search on text (Weaviate) |
| Dashboard | Converts analysis results into Vega-Lite specs (KPI cards + charts) |
| Insights | Generates domain-flavored narrative + recommended next action |

### Data Flow

```
Domain Selection → Upload → Detect & Profile → HITL #1 (Schema & Merge)
→ Cleaning Plan → HITL #2 (Plan Approval) → Execute & Route
→ Intent Capture → HITL #3 (Intent Confirmation)
→ Analyze → Dashboard → Insights
```

### HITL Checkpoints

| # | Gate | User Action |
|---|------|-------------|
| 1 | Schema & Merge Validation | Approve/change merge key, type-routing, exclude columns/files |
| 2 | Cleaning Plan Approval | Approve/modify/reject each cleaning step |
| 3 | Intent Confirmation | Confirm or refine the agent's restated interpretation |
| 4 | Dashboard Accept/Refine (P2) | Accept, request changes, or ask follow-up |

---

## Project Structure

```
DataMind-AI/
├── backend/              # FastAPI application
│   ├── app/
│   │   ├── agents/       # LangGraph agents
│   │   ├── api/v1/       # API endpoints (auth, datasets, dashboards, etc.)
│   │   ├── core/         # Config, database, security, storage
│   │   └── models/       # Pydantic/SQLAlchemy models
│   ├── celery/           # Celery workers & tasks
│   └── tests/            # Unit, integration, E2E tests
├── frontend/             # Next.js 14 application
│   ├── app/              # Routes (/app/* user UI, /admin/* admin UI)
│   ├── components/       # Reusable UI components
│   └── lib/              # API client, hooks, types
├── infra/                # Terraform infrastructure
│   └── terraform/
├── docs/                 # Documentation
│   ├── PRD.md            # Product Requirements Document
│   ├── architecture.md   # Architecture overview
│   ├── prompt.md         # Session prompt log
│   └── ...
├── claude.md             # Developer reference (API, security, testing, UI/UX)
├── skills.md             # AI skill patterns
└── README.md             # This file
```

---

## Phase 1 Timeline

| Week | Dates | Focus | Exit Criteria |
|------|-------|-------|---------------|
| 1 | May 6–9 | Foundation | User can sign up, log in, hit /health. CI/CD deploys to staging. |
| 2 | May 12–16 | Domain + Ingestion | Domain persists. Multi-file upload works. HITL #1 renders. |
| 3 | May 19–23 | Cleaning + LLM | Cleaning plan generated. ≥60% acceptance on golden datasets 1–5. |
| 4 | May 26–30 | Analysis + Dashboard | E2E happy path for CSV and Parquet merge. |
| 5 | Jun 2–6 | Admin UI + QA + Hardening | Internal beta with 5 users for one week. |

---

## Performance Targets

| Metric | Phase 1 | Phase 2 |
|--------|---------|---------|
| Time to First Insight (single file) | < 7 min | < 5 min |
| Cleaning Plan Acceptance | ≥ 75% | ≥ 85% |
| HITL Cycle Time | < 90s | < 60s |
| Dashboard Latency (p95) | < 90s | < 60s |
| Cost per Pipeline | ≤ $0.30 | ≤ $0.15 |
| LLM Providers | ≥ 2 | ≥ 4 |

---

## Domain Packs

| Domain | KPIs |
|--------|------|
| Finance | revenue, COGS, gross margin, churn, MRR/ARR, runway |
| Healthcare | patient counts, readmission rate, length of stay, ICD-10/CPT codes |
| Retail/eCommerce | AOV, repeat purchase, SKU margin, inventory turn |
| Marketing | CTR, CPA, CAC, LTV, attribution windows |
| Operations | throughput, cycle time, generic counts |
| Other | Free-text descriptor |

---

## Development

### Prerequisites

- Python 3.11+
- Node.js 20+
- Docker Desktop
- pnpm

### Local Setup

```bash
# Start local dependencies
docker compose up -d

# Backend
cd backend
uv venv && source .venv/bin/activate
uv pip install -r requirements.txt
uv run alembic upgrade head
uv run uvicorn app.main:app --reload

# Frontend
cd frontend
pnpm install
pnpm dev
```

---

## License

Internal — Confidential
