# DataMind AI

**An Agentic Platform for End-to-End Business Data Intelligence**

From raw data → cleaned data → context-aware dashboards → business decisions.

DataMind AI is an agentic data intelligence platform that takes a business user from raw, messy files to a clean, contextual dashboard — and a recommended business decision — without writing a line of SQL or Python. Built around four deliberate principles: domain-first, user-controlled data modeling, human-in-the-loop cleaning, and type-aware storage routing.

---

## Technology Stack

| Layer | Technology |
|-------|------------|
| Frontend | Next.js 14, TypeScript, Tailwind CSS, shadcn/ui, Recharts |
| Backend | Python 3.11+, FastAPI, Pydantic v2 |
| Job Queue | FastAPI BackgroundTasks |
| Agent Orchestration | LangGraph (supervisor pattern) |
| LLM Provider | LiteLLM abstraction; Google Gemini 3.5 Flash |
| Layer 1 — Raw Storage | Supabase Storage (versioned, per-user prefix) |
| Layer 2 — JSON Processing | Supabase Storage + Supabase DB (PostgreSQL) |
| Layer 3 — Numeric/Structured | PostgreSQL |
| Layer 4 — Textual/Semantic | Supabase Vector (pgvector, HNSW index) |
| Metadata Store | Supabase Database (PostgreSQL) |
| Secrets | Supabase Vault |
| Observability | Prometheus + Grafana |
| CI/CD | GitHub Actions |
| IaC | Terraform |

---

## Core Principles

1. **Domain-first approach** — Ask users their domain (Finance, Healthcare, Retail, Marketing, Operations, Other) so all agents apply domain-appropriate vocabulary, KPIs, and validation rules
2. **User-controlled data modeling** — Accept single or multiple files (CSV, XLSX, JSON, Parquet) and let users decide how to merge/model them
3. **Human-in-the-loop (HITL) cleaning** — Every cleaning step is proposed as a plan; users approve/modify/reject before execution
4. **Type-aware storage routing** — Numeric/structured data → PostgreSQL; free-text → pgvector for semantic search

---

## Storage Architecture

### Four-Layer Storage

| Layer | Content | Engine |
|-------|---------|--------|
| Layer 1 | Original uploaded files (immutable, versioned) | Supabase Storage |
| Layer 2 | Cleaned JSON data + typed PostgreSQL tables | Supabase Storage + Supabase DB |
| Layer 3 | Numeric, boolean, date, low-cardinality categorical | PostgreSQL |
| Layer 4 | Vector embeddings of free-text columns | Supabase Vector (pgvector) |

### File Processing Pipeline

1. Upload any format (CSV, XLSX, JSON, Parquet) → archive original to `supabase://datamind-archive/`
2. Convert to JSON → agents operate on JSON at `supabase://datamind-json/`
3. Structured columns also dumped to typed PostgreSQL tables for SQL queries
4. Textual columns → embeddings → Supabase Vector (pgvector) for semantic search

---

## Agent System

| Agent | Role | Phase |
|-------|------|-------|
| Supervisor | Orchestrates pipeline; routes, retries, aggregates; enforces HITL gates | P1 |
| Domain | Loads domain prompt pack (vocabulary, KPIs, validation rules) | P1 |
| Ingestion | Detects format, parses, profiles, classifies columns, drafts merge plan | P1 |
| Cleaning Plan | Drafts numbered cleaning plan with rationale + confidence. Does NOT execute. | P1 |
| Cleaning Executor | Executes only user-approved steps, logs each action | P1 |
| Intent | Parses natural-language goal into structured analysis spec | P1 |
| Analysis | Runs SQL on numeric data (PostgreSQL); semantic search on text (pgvector) | P1 |
| Dashboard | Converts analysis results into Vega-Lite specs (2-3 KPI cards + 2 charts) | P1 |
| Insights | Generates domain-flavored narrative + recommended next action | P1 |
| Outlier (advanced) | Flags statistical outliers; recommends keep/clip/remove | P2 |
| Fuzzy Dedup | Detects near-duplicate rows using fuzzy string match | P2 |
| Smart Imputation | KNN imputation; LLM-assisted for high-cardinality categoricals | P2 |
| PII Detection | Detects emails, phones, common ID patterns; gates LLM context | P2 |

---

## Data Flow

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
│   │   ├── agents/       # LangGraph agents (Domain, Ingestion, Cleaning, Intent, Analysis, Dashboard, Insights)
│   │   ├── api/v1/       # API endpoints (auth, datasets, dashboards, jobs, admin)
│   │   ├── core/         # Config, database, security, Supabase Storage client
│   │   └── models/       # Pydantic models + SQLAlchemy ORM models
│   ├── workers/          # FastAPI BackgroundTasks handlers
│   │   └── tasks.py      # Background task definitions
│   └── tests/
├── frontend/             # Next.js 14 application
│   ├── app/
│   │   ├── (user)/       # User UI routes (/app/*)
│   │   └── admin/        # Admin UI routes (/admin/*)
│   ├── components/       # Reusable UI components (shadcn/ui)
│   └── lib/              # API client, hooks, TypeScript types
├── infra/                # Infrastructure as Code
│   └── terraform/
├── docs/                 # Project documentation
│   ├── PRD.md            # Product Requirements Document
│   ├── HLD.md            # High-Level Design
│   ├── LLD.md            # Low-Level Design
│   ├── architecture.md   # Architecture overview
│   ├── errors.md         # Error codes reference
│   ├── memory.md         # Full project context
│   └── prompt.md         # Session prompt log
├── claude.md             # Developer reference (API, security, architecture)
├── skills.md             # AI skill patterns
└── README.md             # This file
```

---

## API Design

### Core Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | /api/v1/auth/signup | Create account |
| POST | /api/v1/auth/login | Issue JWT |
| PATCH | /api/v1/me/domain | Update active domain |
| POST | /api/v1/datasets/upload-url | Get presigned upload URLs |
| POST | /api/v1/datasets/{id}/ingest | Trigger format detection + JSON normalisation |
| GET | /api/v1/datasets/{id}/merge-plan | Get HITL #1 data |
| POST | /api/v1/datasets/{id}/merge-plan/decision | Submit HITL #1 decision |
| GET | /api/v1/datasets/{id}/cleaning-plan | Get HITL #2 data |
| POST | /api/v1/datasets/{id}/cleaning-plan/decision | Submit HITL #2 decision |
| POST | /api/v1/datasets/{id}/intent | Submit user intent |
| POST | /api/v1/dashboards/generate | Generate dashboard |
| GET | /api/v1/jobs/{job_id} | Poll job status |
| GET | /api/v1/jobs/{job_id}/audit | Download audit log |

### Admin Endpoints (role=admin required)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET/POST | /api/v1/admin/users | List, invite, suspend, change role |
| GET/PUT | /api/v1/admin/llm-providers | Read/write tenant LLM provider config |
| GET | /api/v1/admin/llm-providers/usage | Per-provider token/cost/latency rollup |
| GET | /api/v1/admin/domain-packs | List/view domain prompt packs |
| GET | /api/v1/admin/health | Job queue depth, error rates, p95 latency |
| GET | /api/v1/admin/audit | Search HITL decisions, cleaning actions, admin actions |

---

## Phase 1 Timeline

| Week | Dates | Focus | Exit Criteria |
|------|-------|-------|---------------|
| 1 | May 6–12 | Foundation | User can sign up, log in, hit /health. CI/CD deploys to staging. |
| 2 | May 13–19 | Domain + Ingestion | Domain persists. Multi-file upload works. HITL #1 renders. |
| 3 | May 20–26 | Cleaning + Type-Routing | Cleaning plan generated. ≥60% acceptance on golden datasets 1–5. |
| 4 | May 27 – Jun 2 | Analysis + Dashboard | E2E happy path for CSV and Parquet merge. |
| 5 | Jun 3–10 | Admin UI + QA + Hardening | Internal beta with 5 users for one week. |

### Scope Cut Priority

If timeline slips, cut in order:
1. Drop Parquet input
2. Drop two domains
3. Drop second LLM provider
4. Drop JSON ingestion
5. Drop XLSX

**Non-negotiable**: HITL, dual UI separation, type-aware storage

---

## Performance Targets

| Metric | Phase 1 | Phase 2 |
|--------|---------|---------|
| Time to First Insight (single file) | < 7 min | < 5 min |
| Time to First Insight (multi-file) | < 12 min | < 8 min |
| Pipeline Success Rate | ≥ 70% | ≥ 85% |
| Cleaning Plan Acceptance | ≥ 75% | ≥ 85% |
| HITL Cycle Time | < 90s | < 60s |
| Dashboard Latency (p95) | < 90s | < 60s |
| Cost per Pipeline | ≤ $0.30 | ≤ $0.15 |
| LLM Providers | Google Gemini 3.5 Flash | Additional as needed |

---

## Domain Packs

| Domain | KPIs |
|--------|------|
| Finance | revenue, COGS, gross margin, churn, MRR/ARR, runway, AR aging, cohort retention |
| Healthcare | patient counts, episode of care, readmission rate, length of stay, ICD-10/CPT codes |
| Retail/eCommerce | AOV, repeat purchase, SKU margin, inventory turn, return rate, channel attribution |
| Marketing | CTR, CPA, CAC, LTV, attribution windows, channel mix |
| Operations | throughput, cycle time, generic counts, sums-and-rates |
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

## Key Constraints

| Constraint | Limit |
|------------|-------|
| File size per upload | 50 MB |
| Total upload size | 250 MB |
| Max files per upload | 10 |
| Format rule | Same format within single upload |
| Storage per user | 5 GB |
| Datasets per user | 20 |
| Supported formats (P1) | CSV, XLSX, JSON, Parquet |
| API rate limit | 100 req/min per user |
| Concurrent pipelines | 5 per user (P1), 10 (P2) |

### Permanently Out of Scope

- Real-time/streaming data (Kafka, Kinesis)
- Native mobile applications
- On-premise deployment
- Training custom ML models on user data
- Direct write-back to source systems

---

## Security

- JWT authentication (HS256, 1-hour expiry, refresh tokens)
- Argon2 password hashing
- RBAC with two roles: user, admin
- Per-user prefix isolation in Supabase Storage
- Encryption at rest: AES-256 (Supabase managed)
- Encryption in transit: TLS 1.3 minimum
- Secrets in Supabase Vault
- Input sanitization on all user-supplied strings
- Stripe webhook signature verification (P2)

---

## Definition of Done (Phase 1)

- [ ] End-to-end pipeline works for CSV, XLSX, JSON, Parquet
- [ ] Cleaning Plan acceptance ≥ 70% on 10-dataset golden set
- [ ] HITL #1 + HITL #2 cycle time < 90s median
- [ ] Audit log present for every agent and HITL decision
- [ ] Four-layer storage architecture operational
- [ ] LLM Provider Abstraction live with Google Gemini 3.5 Flash
- [ ] Dual UI shipped with server-side RBAC enforcement
- [ ] CI/CD pipeline shipping to staging and prod
- [ ] Internal beta with 5 users for one week
- [ ] All Phase 1 NFR targets met

---

## License

Internal — Confidential
