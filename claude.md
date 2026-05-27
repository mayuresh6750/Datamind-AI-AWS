# DataMind AI — Claude Project Instructions

**Tech Stack**: Google Gemini 3.5 Flash | Supabase (Auth + Storage + DB + Vector/pgvector) | FastAPI BackgroundTasks | PostgreSQL | Python stdlib | Next.js 14 | Qwen3-Embedding-0.6B

---

## Project Overview

DataMind AI is an agentic data intelligence platform that transforms raw business data into clean, contextual dashboards and actionable business decisions without requiring SQL or Python knowledge. The platform treats data preparation, analysis, and decision support as one continuous, agent-driven workflow that is explicitly aware of the user's business domain.

Built around four deliberate principles: (1) domain-first approach — ask users what domain they work in so all downstream agents apply domain-appropriate vocabulary, KPIs, and validation rules; (2) user-controlled data modeling — accept single or multiple files and let the user decide how files are merged; (3) human-in-the-loop cleaning — never run data cleaning silently, every step proposed, user approves/modifies/rejects; (4) type-aware storage routing — numeric/structured columns to PostgreSQL, free-text columns to Supabase Vector (pgvector).

---

## Core Principles

### Four Foundational Design Principles

1. **Domain-first approach**: Always ask users what domain they work in (Finance, Healthcare, Retail, Marketing, Operations, or Other) so all downstream agents apply domain-appropriate vocabulary, KPIs, and validation rules
2. **User-controlled data modeling**: Accept single or multiple files (CSV, XLSX, JSON, Parquet) and let the user decide how files should be merged or modeled
3. **Human-in-the-loop (HITL) cleaning**: Never run data cleaning silently — every cleaning step is proposed as a plan, the user approves/modifies/rejects each action, and only then does the agent execute
4. **Type-aware storage routing**: Route data by type — numeric/structured columns to PostgreSQL, free-text columns to Supabase Vector (pgvector) via pgvector — so analysis uses the right tool for each kind of question

---

## Target Users

### Primary Personas

| Persona | Role | Primary Goal | Tech Comfort |
|---------|------|--------------|--------------|
| Business Analyst | Any domain | Build weekly KPI views from raw exports with domain-aware framing | Medium |
| SMB Founder/Operator | Small business owner | Understand revenue, churn, unit economics from spreadsheets | Low–Medium |
| Product/Growth PM | Product manager | Tie product behavior to business outcomes | Medium |
| Tenant Admin | Platform operator | Manage users, configure LLMs, oversee billing and audit | Medium–High |

### Domain Categories

- **Finance**: revenue, COGS, gross margin, churn, MRR/ARR, runway, AR aging, cohort retention
- **Healthcare**: patient counts, episode of care, readmission rate, length of stay, ICD-10/CPT codes
- **Retail/eCommerce**: AOV, repeat purchase, SKU margin, inventory turn, return rate, channel attribution
- **Marketing**: CTR, CPA, CAC, LTV, attribution windows, channel mix
- **Operations**: throughput, cycle time, generic counts, sums-and-rates
- **Other**: free-text descriptor

---

## Technical Architecture

| Layer | Phase 1 Technology | Responsibility |
|-------|-------------------|----------------|
| Presentation — User UI | Next.js 14 (App Router), TypeScript, Tailwind CSS, shadcn/ui, Recharts | Domain selection, file upload, validation/merge UI, HITL cleaning review, intent capture, dashboard, audit view |
| Presentation — Admin UI | Next.js (route group /admin/*, RBAC-gated), shadcn/ui, Recharts | User management, LLM/domain config, system health, audit log, domain pack viewer |
| Authentication | Supabase Auth (email/password, JWT session management, email verification) | Sign-up, login, logout, JWT issuance, session refresh, role-based redirect |
| API Gateway | Python 3.11+, FastAPI, Pydantic v2, Supabase Auth JWT validation, RBAC middleware | REST API, request validation, async job dispatch, role enforcement |
| Embeddings | Qwen3-Embedding-0.6B (sentence-transformers, self-hosted in FastAPI container) | Text column embeddings for pgvector; user intent embeddings; 8K context, provider-neutral |
| Agent Orchestration | LangGraph (supervisor pattern), Pydantic-validated outputs | Multi-agent pipeline coordination, state machine, retry, HITL gates |
| LLM Provider Layer | LiteLLM-compatible abstraction; Google Gemini 3.5 Flash | Per-tenant model config; per-agent routing; cost & latency tracking |
| Ingestion / Conversion | openpyxl, python-magic, chardet, Python stdlib (csv, json) | Format detection, parsing, multi-file merge planning, JSON normalisation, type-routing classification |
| Layer 1 — Raw Storage | Supabase Storage (versioned bucket, per-user prefix) | Immutable source-of-truth for every uploaded file |
| Layer 2 — JSON Storage | Supabase Storage (JSON prefix) + Supabase Database (PostgreSQL) | Cleaned, queryable JSON data; typed tables for SQL |
| Layer 3 — Numeric/Structured | PostgreSQL | SQL queries, aggregates over numeric/structured columns |
| Layer 4 — Textual/Vector | Supabase Vector (pgvector) on PostgreSQL | Embeddings for free-text columns; semantic search |
| Metadata Store | Supabase Database (PostgreSQL) | Users, roles, datasets, jobs, HITL decisions, audit, billing meters |
| Job Queue | FastAPI BackgroundTasks (P1); dedicated worker pool (P2) | Async pipeline execution |
| Payments (P2) | Stripe | Plan tiers, usage-based charges, invoices, dunning |
| Observability | Structured logs → Prometheus/Grafana | Logs, metrics |

### LLM Provider Abstraction

All LLM calls go through a LiteLLM-compatible abstraction layer. Agents are model-agnostic. Admin controls default provider+model per tenant and can override per agent (e.g., cheaper model for profiling, frontier model for narrative).

| Concern | Handling |
|---------|----------|
| Provider list | P1: Google Gemini 3.5 Flash. P2: additional LiteLLM-compatible providers as needed |
| Per-agent routing | Admin sets per-agent {provider, model} in Admin UI |
| Output schema enforcement | All agents return Pydantic-validated JSON, provider-agnostic |
| Cost & latency tracking | Every call records tokens, cost, latency → metrics store |
| Secrets | Provider API keys in Supabase Vault, retrieved per tenant |

---

## Storage Architecture

### Four-Layer Storage Architecture

| Layer | Service | Content | Access |
|-------|---------|---------|--------|
| Layer 1 — Raw | Supabase Storage (versioned) | Original uploaded files, unmodified | Archive URI in dataset record |
| Layer 2 — JSON | Supabase Storage + PostgreSQL | JSON normalised data + typed PostgreSQL tables | All agents operate on JSON; SQL on typed tables |
| Layer 3 — Numeric/Structured | PostgreSQL | Numeric, boolean, datetime, low-cardinality categorical columns | SQL queries |
| Layer 4 — Textual/Semantic | Supabase Vector (pgvector) | Vector embeddings (Qwen3-Embedding-0.6B) of free-text columns | Semantic search (cosine similarity, HNSW index) |

### Data Type Classification Rules

| Class | Detection Rule | Storage Path |
|-------|----------------|--------------|
| Numeric/Structured | int/float/bool/date dtype, or low-cardinality categorical (≤50 distinct values) | PostgreSQL + JSON metadata |
| Textual/Semantic | String with avg length >40 chars or distinct count >50% of rows | pgvector embeddings + JSON metadata |
| Ambiguous | Does not fit above rules | Surfaced in HITL #1 for user decision |

### File Processing Pipeline

1. Upload any format (CSV, XLSX, JSON, Parquet) → archive original to `supabase://datamind-archive/{user_id}/{dataset_id}/{timestamp}/{filename}`
2. Convert to JSON → agents operate on JSON from `supabase://datamind-json/{user_id}/{dataset_id}/v{version}/data.json`
3. Structured columns also dumped to typed PostgreSQL tables for SQL queries
4. Textual columns → embeddings → Supabase Vector (pgvector) for semantic search

---

## Agent System

### Agent Definitions

| Agent | Role | Phase |
|-------|------|-------|
| Supervisor | Orchestrates pipeline; routes, retries, aggregates; enforces HITL gates | P1 |
| Domain | Loads domain prompt pack and exposes it to all downstream agents | P1 |
| Ingestion | Detects format, parses, profiles, classifies columns, drafts merge plan for multi-file | P1 |
| Cleaning Plan | Drafts numbered cleaning plan with rationale + confidence per step. Does NOT execute. | P1 |
| Cleaning Executor | Executes only user-approved steps, logs each action | P1 |
| Intent | Parses user's natural-language goal into structured analysis spec | P1 |
| Analysis | Runs SQL on PostgreSQL for numeric; semantic search on pgvector for textual | P1 |
| Dashboard | Converts analysis results into Vega-Lite specs (2-3 KPI cards + 2 charts) | P1 |
| Insights | Generates domain-flavoured narrative + recommended next action | P1 |
| Outlier (advanced) | Flags statistical outliers; recommends keep/clip/remove | P2 |
| Fuzzy Dedup | Detects near-duplicate rows using fuzzy string match | P2 |
| Smart Imputation | KNN imputation; LLM-assisted for high-cardinality categoricals | P2 |
| PII Detection | Detects emails, phones, common ID patterns; gates LLM context | P2 |

### HITL Checkpoints

| # | What User Sees | User Actions |
|---|----------------|--------------|
| #1 Schema & Merge Validation | Inferred schema per file, proposed type-routing, proposed merge plan | Approve, change merge key, change type-routing, exclude column/file |
| #2 Cleaning Plan Approval | Numbered list of proposed cleaning actions with rationale + confidence | Approve all, approve some, modify steps, reject |
| #3 Intent Confirmation | Restated interpretation of user's question | Approve, refine intent |
| #4 Dashboard Accept/Refine (P2) | Generated dashboard with feedback options | Accept, request changes, ask follow-up |

### Confidence Score Framework

| Score Range | Interpretation | HITL Presentation |
|-------------|----------------|-------------------|
| 0.90–1.00 | High confidence | Pre-checked for approval |
| 0.70–0.89 | Medium confidence | Pre-checked, flagged in yellow |
| 0.50–0.69 | Low confidence | Unchecked, flagged in orange |
| 0.00–0.49 | Very low confidence | Unchecked, flagged in red with warning |

---

## Data Flow

1. **Domain**: User picks domain; Domain Agent loads matching prompt pack
2. **Upload**: User drags files into UI; files upload directly to Layer 1 (Supabase Storage archive bucket)
3. **Detect & Profile**: Ingestion Agent inspects files (mime + content sniff), reports format, parses sample rows, classifies each column as numeric/structured or textual
4. **HITL #1 — Validate & Merge**: User sees inferred schema, proposed merge plan (union/join + key), proposed type-routing per column. User confirms or overrides before cleaning runs
5. **Cleaning Plan**: Cleaning Agent generates numbered plan (dedup, imputation, type coercion, outlier flags) with rationale + confidence per step. Nothing executes
6. **HITL #2 — Approve Cleaning**: User reviews plan, approves/modifies/excludes steps, submits. Audit log records decisions
7. **Execute & Route**: Approved cleaning runs. Cleaned data written to Layer 2 (JSON). Numeric/structured columns loaded into PostgreSQL typed tables; textual columns embedded into pgvector
8. **Intent Capture (HITL #3)**: Domain-tuned suggestion chips shown. Intent Agent embeds user's question and matches against schema. Restatement displayed for user confirmation
9. **Analyze**: Analysis Agent runs SQL on PostgreSQL for numeric questions, semantic search on pgvector for textual, combined queries when needed
10. **Dashboard**: Dashboard Agent generates Vega-Lite chart specs. Renders in User UI
11. **Insight**: Insights Agent generates short domain-flavoured narrative and recommended next action

---

## Key Features (Phase 1)

### F0a — Domain Selection
- Six options: Finance, Healthcare, Retail/eCommerce, Marketing, Operations, Other
- Persisted at user-profile level, editable anytime
- Domain Agent loads matching prompt pack for all downstream agents

### F1 — Multi-File, Multi-Format Data Ingestion
- Drag-and-drop or browse upload
- Formats: CSV, XLSX, JSON, Parquet
- Up to 10 files per upload, same format required
- 50MB per file, 250MB total limit

### F1b — Multi-File Validation & Merge (HITL #1)
- Schema preview for each file
- Proposed merge plan: UNION (same columns) or JOIN (different columns)
- User confirms or overrides before cleaning

### F1c — Type-Aware Storage Routing
- Automatic classification of columns as numeric/structured or textual
- Routing to PostgreSQL (numeric) or pgvector (textual)
- Ambiguous columns flagged for user decision

### F2 — JSON-Normalised Storage with Original Archiving
- Original files archived unmodified in Supabase Storage (Layer 1)
- All files normalised to JSON for processing (Layer 2)
- Structured data also dumped into typed PostgreSQL tables

### F3 — HITL Cleaning (Plan → Approve → Execute)
- **Plan phase**: Agent generates numbered list of proposed actions with rationale + confidence
- **Approve phase**: User reviews, approves/modifies/rejects
- **Execute phase**: Only approved steps run
- Operations: exact dedup, missing-value imputation, type coercion, basic outlier flagging

### F4 — Intent Capture (HITL #3)
- Free-text input: "What are you trying to learn from this data?"
- Domain-tuned suggestion chips
- Intent Agent restates interpretation for user confirmation

### F5 — Dashboard Generation
- 2-3 KPI cards plus 2 charts (line, bar, table)
- Domain-flavoured narrative from Insights Agent
- Rendered within 90 seconds

### F6 — Audit Log and Lineage
- Every transformation logged: agent, action type, rows affected, rationale, confidence
- Viewable in UI, downloadable as JSON/CSV

### F11 — Dual UI Surfaces
- **User UI** (`/app/*`): Upload, validation, HITL review, intent capture, dashboards
- **Admin UI** (`/admin/*`): User management, LLM config, domain pack viewer, system health, audit log
- RBAC enforced server-side

### F12 — Configurable LLM Provider
- LiteLLM-compatible abstraction
- Phase 1: Google Gemini 3.5 Flash
- Per-tenant defaults with per-agent overrides
- Cost and latency tracking per provider/agent

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

### Rate Limits

- 100 requests/minute per user
- 5 concurrent pipeline jobs per user (Phase 1)
- 10 concurrent pipeline jobs per user (Phase 2)

---

## Security Requirements

- Supabase Auth (JWT session management, email/password, email verification, refresh tokens)
- RBAC with two roles: user, admin (custom claims via Supabase Auth metadata)
- Per-user prefix isolation in Supabase Storage
- Encryption at rest: AES-256 (Supabase managed)
- Encryption in transit: TLS 1.3 minimum
- Secrets in Supabase Vault
- Input sanitization on all user-supplied strings
- Stripe webhook signature verification (P2)

---

## AI Safety and Governance

### Guardrails

- **HITL gates**: Cleaning never executes without user approval
- **Schema-enforced outputs**: All agent returns validated against Pydantic models
- **Confidence scoring**: 0.0–1.0 score on every cleaning decision
- **PII gating** (P2): PII columns excluded from LLM prompts unless user opts in
- **Prompt-injection defense**: User data in delimited blocks with explicit framing
- **SQL validation**: Generated SQL parsed and validated as read-only
- **Token/cost ceilings**: Per-pipeline budget caps total LLM tokens
- **Reversibility**: No destructive operation on user data is permanent (Layer 1 preserved)

### Bias Mitigation

- Statistical-first imputation (median, mode) rather than LLM-generated
- Insight narrative required to cite specific chart values
- Golden datasets include fairness-relevant attributes for evaluation

### Hallucination Handling

- Numerical claims in narratives programmatically validated against source data
- SQL outputs parsed before execution; non-SELECT operations blocked
- Agents see only schema metadata and ≤5 anonymized sample rows, not full datasets

---

## Phase 2 Additions

- Advanced cleaning: fuzzy dedup, KNN imputation, LLM-assisted imputation, outlier handling
- Additional LLM providers: additional LiteLLM-compatible providers as needed
- PII Detection Agent
- Iterative Q&A on same dataset
- Project/workspace organization
- Public REST API
- Stripe-backed monetization (Free/Pro/Team/Enterprise tiers)
- Domain pack editor (read-only viewer in P1 → full editing in P2)

---

## Timeline

### Phase 1 (6 May – 10 June 2026)

| Week | Focus | Exit Criteria |
|------|-------|---------------|
| Week 1 | Foundation: Supabase setup + Terraform, CI/CD, Postgres schema, FastAPI, Next.js shell, auth, LLM abstraction | User can sign up, log in, hit /health. CI/CD deploys to staging. |
| Week 2 | Domain selection, multi-file upload, format detection, HITL #1 | Domain persists. Multi-file upload works. HITL #1 renders. |
| Week 3 | JSON normalisation, type-routing, cleaning plan agent, HITL #2, cleaning executor | Cleaning plan generated. ≥60% acceptance on golden datasets 1-5. |
| Week 4 | Intent agent, analysis agent, dashboard agent, insights agent | End-to-end happy path for CSV and Parquet merge. |
| Week 5 | Admin UI, integration testing, golden dataset validation, hardening | Internal beta with 5 users for one week. |

### Phase 2 (11 June – 10 July 2026)

| Week | Focus |
|------|-------|
| Week 6 | Advanced cleaning agents, PII detection, XML/PDF ingestion |
| Week 7 | LLM provider expansion, domain pack editor, new domain packs |
| Week 8 | Iterative Q&A, expanded charts, public REST API, project organization |
| Week 9 | Stripe monetization, OpenTelemetry tracing, auto-scaling background workers |
| Week 10 | Closed beta launch (20-30 users), bug fixes, documentation |

### Scope Cut Priority (Phase 1)

If timeline slips, cut in this order:
1. Drop Parquet input
2. Drop two domains
3. Drop second LLM provider
4. Drop JSON ingestion
5. Drop XLSX

**Non-negotiable**: HITL, dual UI separation, type-aware storage

---

## Performance Targets

| Metric | Phase 1 Target | Phase 2 Target |
|--------|----------------|----------------|
| Time to First Insight (single file) | < 7 min | < 5 min |
| Time to First Insight (multi-file) | < 12 min | < 8 min |
| Pipeline Success Rate | ≥ 70% | ≥ 85% |
| Cleaning Plan Acceptance | ≥ 75% | ≥ 85% |
| HITL Cycle Time | < 90s | < 60s |
| Dashboard Latency (p95) | < 90s | < 60s |
| Cost per Pipeline | ≤ $0.30 | ≤ $0.15 |
| LLM Providers | Google Gemini 3.5 Flash | Additional as needed |

## Database Schema (Core Tables)

### users
- user_id (UUID PK, FK→auth.users.id), tenant_id (FK→tenants), email (UNIQUE), role (user/admin), active_domain (finance/healthcare/retail/marketing/operations/other), created_at
- Note: password management handled entirely by Supabase Auth (auth.users); no password_hash stored in this table

### datasets
- dataset_id (UUID PK), user_id (FK), original_filenames (TEXT[]), detected_format (csv/xlsx/json/parquet), file_count, merge_strategy (single/union/join/separate), merge_key_column, archive_uris, json_uri, row_count_raw, row_count_clean, status (state machine), created_at/updated_at

### hitl_decisions
- decision_id (UUID PK), dataset_id (FK), user_id (FK), checkpoint (schema_merge/cleaning_plan/intent/dashboard_accept), proposal_json (JSONB), decision_json (JSONB), latency_seconds, created_at

### pipeline_runs
- run_id (UUID PK), dataset_id (FK), status (queued/running/paused_for_hitl/complete/failed), started_at, completed_at, error_summary, audit_log_uri, llm_provider, total_llm_tokens, total_llm_cost_usd

### llm_provider_config
- config_id (UUID PK), tenant_id (FK), default_provider, default_model, per_agent_overrides (JSONB), secrets_vault_path

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

- 50 MB per file, 250 MB total per upload, 10 files maximum per upload
- Same format required within single upload
- 5 GB storage per user, 20 datasets per user
- Supported formats: CSV, XLSX, JSON, Parquet (P1)
- No streaming data, no native mobile, no on-prem, no custom ML training
- No write-back to source systems

### Permanently Out of Scope

- Real-time/streaming data (Kafka, Kinesis)
- Native mobile applications
- On-premise deployment
- Training custom ML models on user data
- Direct write-back to source systems

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
