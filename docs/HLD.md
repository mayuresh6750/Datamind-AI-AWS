# DataMind AI — High-Level Design

**Document Type:** Architecture HLD | **Phase:** 1 | **Status:** Draft

---

## 1. System Overview

DataMind AI is an agentic data intelligence platform that transforms raw business data into clean, contextual dashboards and actionable business decisions. The system is built around a supervisor‑pattern LangGraph pipeline with four human‑in‑the‑loop (HITL) gates, a LiteLLM‑compatible provider abstraction, and a four‑layer storage architecture.

---

## 2. Architecture Diagram

```
 ┌─────────────────────────────────────────────────────────────┐
 │      Client Tier        │
 │ ┌─────────────────────┐ ┌───────────────────────────┐ │
 │ │ User UI (/app/*) │ │ Admin UI (/admin/*)  │ │
 │ │ Next.js 14 + TS │ │ Next.js 14 + TS + RBAC │ │
 │ └─────────┬───────────┘ └───────────┬───────────────┘ │
 └────────────┼────────────────────────────┼───────────────────┘
    │   HTTPS + JWT  │
    ▼        ▼
 ┌─────────────────────────────────────────────────────────────┐
 │      API Gateway        │
 │  FastAPI + Pydantic v2 + Supabase Auth + RBAC   │
 │  ┌──────────────────────────────────────────────────┐ │
 │  │ REST Endpoints (/api/v1/*)      │ │
 │  │ Auth | Datasets | Jobs | Dashboards | Admin  │ │
 │  └──────────────────────────────────────────────────┘ │
 └────────────┬────────────────────────────────────────────────┘
    │
    ▼
 ┌─────────────────────────────────────────────────────────────┐
 │    Agent Orchestration (LangGraph)    │
 │                │
 │ ┌──────────┐ ┌────────┐ ┌─────────────┐    │
 │ │Supervisor│──▶│ Domain │──▶│ Ingestion │    │
 │ │(State │ │ Agent │ │ Agent │    │
 │ │ Machine) │ └────────┘ └──────┬──────┘    │
 │ └──────────┘      │      │
 │  │       ▼      │
 │  │     ┌──────────────┐    │
 │  │     │ HITL #1  │◄── User  │
 │  │     │ (Merge Plan) │    │
 │  │     └──────┬───────┘    │
 │  │       ▼      │
 │  │     ┌──────────────┐    │
 │  │     │ Cleaning │    │
 │  │     │ Plan Agent │    │
 │  │     └──────┬───────┘    │
 │  │       ▼      │
 │  │     ┌──────────────┐    │
 │  │     │ HITL #2  │◄── User  │
 │  │     │ (Approve) │    │
 │  │     └──────┬───────┘    │
 │  │       ▼      │
 │  │     ┌──────────────┐    │
 │  │     │ Cleaning │    │
 │  │     │ Executor │    │
 │  │     └──────┬───────┘    │
 │  │       ▼      │
 │  │     ┌──────────────┐    │
 │  │     │ Intent  │    │
 │  │     │ Agent  │    │
 │  │     └──────┬───────┘    │
 │  │       ▼      │
 │  │     ┌──────────────┐    │
 │  │     │ HITL #3  │◄── User  │
 │  │     │ (Confirm) │    │
 │  │     └──────┬───────┘    │
 │  │       ▼      │
 │  │     ┌──────────────┐    │
 │  │     │ Analysis │    │
 │  │     │ Agent  │    │
 │  │     └──────┬───────┘    │
 │  │       ▼      │
 │  │     ┌──────────────┐    │
 │  │     │ Dashboard │    │
 │  │     │ Agent  │    │
 │  │     └──────┬───────┘    │
 │  │       ▼      │
 │  │     ┌──────────────┐    │
 │  │     │ Insights │    │
 │  │     │ Agent  │    │
 │  │     └──────────────┘    │
 └────────┼──────────────────────────────────────────────────┘
   │
   ▼
 ┌─────────────────────────────────────────────────────────────┐
 │    LLM Provider Abstraction      │
 │   LiteLLM-compatible interface layer     │
 │                │
 │ ┌────────────────────────────────────────────────────────┐ │
 │ │   Google Gemini 3.5 Flash (Phase 1)    │ │
 │ │ structured_completion() + Pydantic validation  │ │
 │ │ retry logic (3x) + token/cost/latency logging  │ │
 │ └────────────────────────────────────────────────────────┘ │
 │ ┌────────────────────────────────────────────────────────┐ │
 │ │ Phase 2: + Groq (Llama 3), Ollama (self-hosted)  │ │
 │ └────────────────────────────────────────────────────────┘ │
 └─────────────────────────────────────────────────────────────┘

 Storage Layer (Four-Layer Architecture):

 ┌──────────┐ ┌──────────┐ ┌──────────────┐ ┌──────────┐
 │ Layer 1 │ │ Layer 2 │ │ Layer 3 │ │ Layer 4 │
 │ Raw │ │ Curated │ │Numeric/Struct│ │ Textual │
 │ Supabase │───▶│ Supabase │───▶│ Supabase DB │ │ Supabase Vector (pgvector) │
 │ Storage │ │ Parquet │ │ + PostgreSQL │ │ (Vector) │
 │(Immutable│ │(Cleaned) │ │ (SQL/OLAP) │ │ (HNSW) │
 └──────────┘ └──────────┘ └──────────────┘ └──────────┘
```

---

## 3. Component Breakdown

### 3.1 Client Tier

| Component | Technology | Description |
|-----------|-----------|-------------|
| User UI | Next.js 14, TypeScript, Tailwind, shadcn/ui, Recharts | Screens: domain selection, upload, HITL #1–#3, dashboard, audit log |
| Admin UI | Next.js 14 (route group /admin/*) | Screens: system health, user management, LLM config, domain packs, audit viewer |
| Auth | Supabase Auth (email/password, JWT, email verification, refresh tokens) | Sign-up, login, logout, session management, role-based redirect |

### 3.2 API Gateway (FastAPI)

| Module | Responsibility |
|--------|---------------|
| Auth Router | POST /auth/signup, /login, /refresh, /logout |
| Dataset Router | Upload URLs, ingest trigger, merge plan, cleaning plan, intent submission |
| Dashboard Router | Dashboard generation trigger |
| Job Router | Job status polling, audit log retrieval |
| Admin Router | User management, LLM config, domain packs, system health, audit search |
| Middleware | JWT validation, RBAC enforcement (user vs admin), rate limiting (100 req/min) |

### 3.3 Agent Pipeline (LangGraph)

| Agent | Input | Output | Key Logic |
|-------|-------|--------|-----------|
| Supervisor | Pipeline event | Next agent / HITL gate | State machine routing; retry on failure; HITL pause/resume |
| Domain | User domain | Prompt pack context | Loads domain vocabulary + KPIs from Supabase Database |
| Ingestion | File list | Schema profile + merge plan | Format detection, parsing, profiling, column classification |
| Cleaning Plan | Schema profile + domain context | Numbered cleaning plan | Dedup detection, imputation proposals, type coercion, outlier flagging, confidence scoring |
| Cleaning Executor | Approved step list | Cleaned Parquet | Run only approved steps, log each action to audit |
| Intent | Free-text question | Structured analysis spec | Domain-biased parsing, schema-aware |
| Analysis | Analysis spec | Query results | SQL (PostgreSQL) for numeric; semantic search (Supabase Vector (pgvector)) for textual |
| Dashboard | Analysis results | Vega-Lite specs | 2–3 KPI cards + 2 charts (bar/line/table) |
| Insights | Dashboard specs + analysis | Narrative + recommendation | Domain-flavoured, factually grounded |

### 3.4 LLM Provider Abstraction

- LiteLLM-compatible interface: `structured_completion(prompt, schema, provider, model)`
- Phase 1 provider: **Google Gemini 3.5 Flash**
- Phase 2: Groq (Llama 3), Ollama (self-hosted)
- Per-tenant default provider + per-agent override
- Structured JSON output validated against Pydantic schemas (3 retry attempts)
- Token budget: 150K input / 25K output per pipeline
- Cost ceiling: $0.30 per pipeline
- All calls logged: tokens, cost_usd, latency_ms, provider, model, agent_name

### 3.5 Storage Architecture

| Layer | Service | Contents | Access |
|-------|---------|----------|--------|
| L1 Raw | Supabase Storage (versioned) | Original files — never modified | Immutable source |
| L2 Curated | Supabase Storage + Parquet | Cleaned columnar data | PostgreSQL |
| L3 Numeric/Structured | Supabase Database (PostgreSQL) + PostgreSQL | Numeric, bool, date, low-cardinality categorical | SQL |
| L4 Textual/Semantic | Supabase Vector (pgvector, HNSW index) | Vector embeddings via Qwen3-Embedding-0.6B (free-text columns) | Cosine similarity |
| Metadata | Supabase Database (PostgreSQL) | users, datasets, pipeline_runs, decisions, config | SQL |

### 3.6 Async Job Queue

- **FastAPI BackgroundTasks** (Phase 1) for pipeline job dispatch
- Long-running endpoints return `job_id` immediately; frontend polls `/jobs/{id}`
- Pipeline state persisted to Supabase Database + Supabase Storage before every HITL pause

---

## 4. Data Flow (End-to-End)

```
┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
│ Domain │──▶│ Upload │──▶│ Ingest & │──▶│ HITL #1 │──▶│ Cleaning │
│ Select │ │ Files │ │ Profile │ │(Merge) │ │ Plan │
└──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘
                 │
                 ▼
┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
│ Dashboard│◀──│ Analyze │◀──│ HITL #3 │◀──│ Intent │◀──│ HITL #2 │
│ +Chart │ │(SQL+Vec) │ │(Confirm) │ │ Capture │ │(Approve) │
└──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘
  │
  ▼
┌──────────┐
│ Insights │──▶ User sees KPI cards + charts + narrative
└──────────┘
```

---

## 5. Security Architecture

| Concern | Implementation |
|---------|---------------|
| Authentication | Supabase Auth — JWT session management, email/password, email verification, refresh token rotation |
| Authorization | RBAC with `user` / `admin` roles via Supabase Auth custom claims; server-side enforcement on all `/admin/*` routes |
| Data encryption | AES-256 at rest (Supabase managed), TLS 1.3 in transit |
| Secrets management | Supabase Vault — API keys never in env files or source code |
| SQL injection | sqlglot validates all generated SQL as read-only before execution |
| Prompt injection | User data delivered in delimited blocks with explicit framing |
| PII mitigation | Agent sees only schema metadata + ≤5 anonymised sample rows |
| Audit immutability | No API delete for audit entries; WORM storage considered in P2 |
| Rate limiting | 100 req/min per user; 5 concurrent pipelines per user (Phase 1) |

---

## 6. Scalability Considerations

| Constraint | Phase 1 | Phase 2 |
|-----------|---------|---------|
| File size | 50MB per file, 250MB total | 100MB per file, 500MB total |
| Files per upload | 10 | 20 |
| Dataset storage | 5GB per user | 50GB per user |
| Concurrent pipelines | 5 per user | 10 per user |
| Job queue | FastAPI BackgroundTasks (single worker) | Redis Streams + auto-scaling workers |
| Database | PostgreSQL single-AZ | Multi-AZ with read replicas |

---

## 7. Monitoring & Observability

- **Metrics** (Prometheus): `pipeline_duration_seconds`, `hitl_decision_latency_seconds`, `hitl_approval_rate`, `llm_tokens_used`, `llm_cost_usd`, `type_routing_distribution`
- **Logging** (structlog): Structured JSON logs per request and per agent step
- **Alerting** (Grafana): Job failure rate >5%, API p95 >2s, LLM error rate >10%, HITL queue >100, daily spend >130% of 7-day avg
- **Dashboards**: Pipeline health, LLM cost per agent/domain, HITL approval trends

---

## 8. Key API Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | /api/v1/auth/signup | Create account |
| POST | /api/v1/auth/login | Issue JWT |
| PATCH | /api/v1/me/domain | Update active domain |
| POST | /api/v1/datasets/upload-url | Get presigned Supabase Storage URLs |
| POST | /api/v1/datasets/{id}/ingest | Trigger format detection |
| GET | /api/v1/datasets/{id}/merge-plan | Get HITL #1 data |
| POST | /api/v1/datasets/{id}/merge-plan/decision | Submit HITL #1 decision |
| GET | /api/v1/datasets/{id}/cleaning-plan | Get HITL #2 data |
| POST | /api/v1/datasets/{id}/cleaning-plan/decision | Submit HITL #2 decision |
| POST | /api/v1/datasets/{id}/intent | Submit user intent |
| POST | /api/v1/dashboards/generate | Generate dashboard |
| GET | /api/v1/jobs/{job_id} | Poll job status |
| GET | /api/v1/jobs/{job_id}/audit | Download audit log |

---

## 9. Phase 2 Extensions

- Additional LLM providers: Groq (Llama 3), Ollama (self-hosted)
- Advanced cleaning: fuzzy dedup, KNN imputation, PII detection
- Iterative Q&A on same dataset
- Stripe-backed monetization (Free/Pro/Team/Enterprise)
- Domain Pack Editor in Admin UI
- Public REST API + OpenAPI docs
- Cross-format multi-file merging
- OpenTelemetry tracing + Grafana Tempo
