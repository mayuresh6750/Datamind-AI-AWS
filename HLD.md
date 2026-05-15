# DataMind AI — High Level Design (HLD)

**Version:** 1.0 | **Phase:** 1 | **Date:** May 2026

---

## 1. Purpose

This document describes the high-level design of DataMind AI — an agentic data intelligence platform that takes a business user from raw, messy files to a clean, contextual dashboard and a recommended business decision, without writing SQL or Python. It covers system goals, architecture layers, component responsibilities, data flow, technology choices, and non-functional requirements.

---

## 2. System Goals

| Goal | Description |
|---|---|
| End-to-end pipeline | Raw file → cleaned data → dashboard → decision in one continuous workflow |
| Domain awareness | Every agent uses the user's business domain (Finance, Healthcare, Retail, Marketing, Operations, Other) to apply correct vocabulary, KPIs, and validation |
| Human-in-the-loop | No data is mutated silently — every cleaning step is proposed, reviewed, and approved by the user |
| Type-aware storage | Numeric/structured data routed to relational store; free-text data routed to vector store |
| LLM agnosticism | All LLM calls go through a provider abstraction — Anthropic Claude and OpenAI in Phase 1 |
| Dual UI | Separate authenticated surfaces for end-users and tenant admins |
| Auditability | Every agent action, HITL decision, and LLM call is logged with full traceability |

---

## 3. High-Level Architecture

DataMind is a three-tier, cloud-native system split into five logical layers:

```
┌──────────────────────────────────────────────────────────────────┐
│  PRESENTATION LAYER                                              │
│                                                                  │
│   User UI  (/app/*)                Admin UI  (/admin/*)          │
│   Next.js 14 · TypeScript          Next.js 14 · TypeScript       │
│   Tailwind CSS · shadcn/ui         RBAC-gated (403 non-admins)   │
│   Blue accent                      Orange accent                 │
└────────────────────────┬─────────────────────────────────────────┘
                         │  HTTPS / JWT Bearer
┌────────────────────────▼─────────────────────────────────────────┐
│  API GATEWAY LAYER                                               │
│                                                                  │
│   FastAPI (Python 3.11+) · Pydantic v2                          │
│   JWT Auth Middleware · RBAC Middleware                          │
│   Synchronous endpoints → direct response (< 300ms p95)         │
│   Async endpoints → enqueue job → return job_id immediately      │
│   Frontend polls /jobs/{id} every 2s for status                  │
└────────────────────────┬─────────────────────────────────────────┘
                         │  Celery + Redis job queue
┌────────────────────────▼─────────────────────────────────────────┐
│  AGENT ORCHESTRATION LAYER                                       │
│                                                                  │
│   LangGraph Supervisor (state machine)                           │
│   ┌──────────┐ ┌──────────┐ ┌──────────────┐ ┌──────────────┐  │
│   │  Domain  │ │Ingestion │ │Cleaning Plan │ │  Cleaning    │  │
│   │  Agent   │ │  Agent   │ │    Agent     │ │  Executor    │  │
│   └──────────┘ └──────────┘ └──────────────┘ └──────────────┘  │
│   ┌──────────┐ ┌──────────┐ ┌──────────────┐ ┌──────────────┐  │
│   │  Intent  │ │ Analysis │ │  Dashboard   │ │   Insights   │  │
│   │  Agent   │ │  Agent   │ │    Agent     │ │    Agent     │  │
│   └──────────┘ └──────────┘ └──────────────┘ └──────────────┘  │
│                                                                  │
│   HITL Gate Manager — pauses pipeline at checkpoints #1/#2/#3   │
└────────────────────────┬─────────────────────────────────────────┘
                         │
┌────────────────────────▼─────────────────────────────────────────┐
│  LLM PROVIDER ABSTRACTION LAYER                                  │
│                                                                  │
│   LiteLLM-compatible uniform interface                           │
│   Phase 1: Anthropic Claude · OpenAI                             │
│   Phase 2: + Google Gemini · Azure OpenAI · AWS Bedrock · Ollama │
│   Per-tenant defaults · Per-agent routing overrides              │
│   Pydantic-validated structured JSON output                      │
│   Cost + latency tracking per call                               │
│   API keys in AWS Secrets Manager                                │
└────────────────────────┬─────────────────────────────────────────┘
                         │
┌────────────────────────▼─────────────────────────────────────────┐
│  FOUR-LAYER STORAGE                                              │
│                                                                  │
│  Layer 1 — Raw (S3, versioned, immutable)                        │
│  Layer 2 — Curated Parquet (S3)                                  │
│  Layer 3 — Numeric/Structured (Postgres + DuckDB)                │
│  Layer 4 — Textual/Semantic (pgvector on Postgres RDS)           │
│  Metadata — PostgreSQL (AWS RDS, single-AZ in P1)               │
│  Job Queue — Redis (Celery broker + result backend)              │
└──────────────────────────────────────────────────────────────────┘
```

---

## 4. Component Responsibilities

### 4.1 Presentation Layer

| Surface | Route | Responsibility |
|---|---|---|
| User UI | `/app/*` | Domain selection, file upload, HITL #1 schema validation, HITL #2 cleaning review, intent capture, dashboard view, history/audit |
| Admin UI | `/admin/*` | User & role management, LLM provider config, domain pack viewer, system health, audit log viewer, usage meter |

Both surfaces share the same Next.js 14 codebase, design system (shadcn/ui), and Recharts library. They are visually differentiated by accent colour (blue for user, orange for admin) and route-level RBAC enforcement.

### 4.2 API Gateway Layer

- Validates every request via Pydantic v2
- Enforces JWT authentication and RBAC on every endpoint
- Returns `job_id` immediately for long-running operations; frontend polls for status
- Rate limit: 100 requests/minute per user
- Pauses pipeline at HITL gates and resumes on user decision POST

### 4.3 Agent Orchestration Layer

- LangGraph Supervisor coordinates the pipeline as a state machine
- Each agent has a narrow scope, a defined tool set, and a Pydantic-validated output schema
- Pipeline state is persisted to S3 + Postgres after every agent step so paused (HITL) or failed pipelines can be resumed
- HITL Gate Manager blocks execution at checkpoints #1, #2, and #3 until user submits a decision

### 4.4 LLM Provider Abstraction Layer

- All agents call a uniform LiteLLM-compatible interface — no direct SDK calls
- Provider, model, and per-agent routing configured per tenant by admin
- Invalid LLM outputs trigger retry (up to 3 attempts), then pipeline failure
- Every call is logged: tokens used, cost (USD), latency (ms), provider, model, agent, pipeline run

### 4.5 Storage Layer

| Layer | Technology | Contents |
|---|---|---|
| Layer 1 — Raw | AWS S3 (versioned) | Original uploaded files — never modified |
| Layer 2 — Curated | AWS S3 (Apache Parquet) | Cleaned, queryable columnar data — versioned per cleaning run |
| Layer 3 — Numeric | Postgres + DuckDB (in-process) | Numeric, boolean, datetime, categorical columns — accessed via SQL |
| Layer 4 — Textual | pgvector on Postgres | Embeddings for free-text columns — accessed via semantic search |
| Metadata | PostgreSQL (RDS) | Users, datasets, pipeline runs, HITL decisions, audit events, LLM config |
| Job Queue | Redis | Celery broker and result backend for async pipeline steps |

---

## 5. End-to-End Data Flow

```
User picks domain
      ↓
Domain Agent loads prompt pack (vocabulary, KPIs, validation rules)
      ↓
User uploads 1–10 files (same format) → S3 Layer 1 (raw)
      ↓
Ingestion Agent: detect format → parse → profile → classify columns
      ↓
══ HITL #1 ══ User confirms schema + merge plan + type-routing
      ↓
Merge executed → curated Parquet (Layer 2)
Numeric columns → Postgres/DuckDB (Layer 3)
Textual columns → pgvector embeddings (Layer 4)
      ↓
Cleaning Plan Agent: generate numbered plan (dedup, impute, coerce, flag)
      ↓
══ HITL #2 ══ User approves / modifies / rejects each step
      ↓
Cleaning Executor: run approved steps → update Layer 2 → write audit log
      ↓
══ HITL #3 ══ User types intent question (domain chips shown)
              Intent Agent restates interpretation → user confirms
      ↓
Analysis Agent: SQL on Layer 3 (numeric) + semantic search on Layer 4 (text)
      ↓
Dashboard Agent: generate Vega-Lite specs (2–3 KPI cards + 2 charts)
      ↓
Insights Agent: domain-flavoured narrative + recommended next action
      ↓
Dashboard rendered in User UI (< 90s p95 from intent submission)
      ↓
Audit log available for every step
```

---

## 6. HITL Checkpoints

| Checkpoint | When | What the user sees | What the user can do |
|---|---|---|---|
| #1 Schema & Merge | After ingestion & profiling | Per-file schema, type-routing per column, proposed merge plan | Approve, change merge key, change type-routing, exclude column/file |
| #2 Cleaning Plan | After plan generation | Numbered steps with rationale + confidence scores | Approve all/some, modify a step, reject a step |
| #3 Intent Confirmation | After intent capture | Restated interpretation of the question | Approve or refine |

Pipeline is blocked at each gate until the user posts a decision. Every decision is recorded in the `hitl_decisions` table with full traceability.

---

## 7. Agent Set (Phase 1)

| Agent | Role |
|---|---|
| Supervisor | Orchestrates pipeline; enforces HITL gates; retries on failure |
| Domain | Loads domain prompt pack; injects context into all downstream agents |
| Ingestion | Detects format, parses, profiles, classifies columns, drafts merge plan |
| Cleaning Plan | Generates numbered plan with rationale + confidence — does NOT execute |
| Cleaning Executor | Executes only user-approved steps; writes audit log |
| Intent | Parses natural-language goal into structured analysis spec |
| Analysis | SQL on Postgres/DuckDB (numeric); semantic search on pgvector (textual) |
| Dashboard | Converts analysis results into Vega-Lite chart specs |
| Insights | Generates domain-flavoured narrative + recommended next action |

---

## 8. Domain Prompt Packs (Phase 1)

| Domain | Key KPIs | Validation |
|---|---|---|
| Finance | Revenue, gross margin, MRR/ARR, churn, AR aging, cohort retention | Fiscal-period dates, currency normalisation |
| Healthcare | Patient counts, readmission rate, length of stay, ICD-10/CPT | PHI detection cues |
| Retail/eCommerce | AOV, repeat purchase rate, SKU margin, inventory turn, return rate | SKU duplicates, negative quantities |
| Marketing | CTR, CPA, CAC, LTV, attribution windows, channel mix | UTM hygiene, date-window alignment |
| Other / Operations | Generic counts, throughput, cycle time | No domain-specific validators |

---

## 9. Technology Stack Summary

| Area | Phase 1 Technology | Phase 2 Successor |
|---|---|---|
| Frontend | Next.js 14, TypeScript, Tailwind, shadcn/ui, Recharts | + Vega-Lite advanced charts |
| Backend API | Python 3.11+, FastAPI, Pydantic v2 | Same |
| Agent orchestration | LangGraph | Same |
| LLM providers | Anthropic Claude + OpenAI | + Gemini, Azure OpenAI, Bedrock, Ollama |
| LLM abstraction | LiteLLM-compatible interface | Same + provider failover |
| Async jobs | Celery + Redis | AWS SQS + Fargate workers |
| Raw storage | AWS S3 (versioned) | Same |
| Curated storage | AWS S3 (Apache Parquet) | + Athena for serverless query |
| Numeric/structured | Postgres + DuckDB (in-process) | Same + Athena |
| Vector/textual | pgvector on Postgres RDS | + Pinecone (optional) |
| Metadata DB | PostgreSQL RDS (single-AZ) | Multi-AZ |
| Auth | JWT HS256 + Argon2 | + SSO (SAML/OIDC) |
| Secrets | AWS Secrets Manager | Same |
| CI/CD | GitHub Actions | Same |
| Observability | CloudWatch (logs + metrics + alerts) | + OpenTelemetry + Grafana |

---

## 10. Dual UI Design

### User UI Screens

| Screen | ID | Description |
|---|---|---|
| Sign up / Sign in | U1 | Email + password auth |
| Domain Selection | U2 | First-run modal; editable anytime |
| File Upload | U3 | Drag-and-drop; 1–10 files, same format |
| Schema & Merge Validation | U4 | HITL #1 |
| Cleaning Plan Review | U5 | HITL #2 |
| Intent Capture | U6 | Free-text + domain chips; HITL #3 |
| Dashboard | U7 | KPI cards + charts + narrative |
| History / Audit | U8 | Past pipeline runs + downloadable audit log |

### Admin UI Screens

| Screen | ID | Description |
|---|---|---|
| System Health | A1 | Pipeline status, job queue depth, error rates |
| User & Role Management | A2 | Provision users, assign roles, suspend |
| LLM Provider Config | A3 | Set provider, model, per-agent routing |
| Domain Pack Viewer | A4 | Read-only in P1; full editor in P2 |
| Audit Log Viewer | A5 | Search HITL decisions and cleaning actions |
| Billing & Plans | A6 | Phase 2 only (Stripe) |

---

## 11. Security Overview

| Concern | Approach |
|---|---|
| Authentication | JWT HS256, 1-hour expiry, refresh tokens; Argon2 password hashing |
| Authorisation | RBAC (user / admin) enforced server-side on every endpoint |
| S3 isolation | Per-user prefix; IAM scoped to `{user_id}/` prefix |
| Tenant isolation | `tenant_id` scoping on every Postgres query; per-tenant pgvector namespace |
| Encryption at rest | AES-256 SSE-S3 (P1) → SSE-KMS (P2) |
| Encryption in transit | TLS 1.3 minimum |
| API key storage | AWS Secrets Manager — never in env files or repo |
| Prompt injection | User data delivered inside delimited blocks; outputs validated against Pydantic schemas |
| SQL safety | Generated SQL parsed by sqlglot; DDL and write operations blocked |
| Cost safety | Per-pipeline token cap (150K input + 25K output); exceeding halts the pipeline |

---

## 12. Non-Functional Requirements

| Requirement | Phase 1 Target | Phase 2 Target |
|---|---|---|
| Time to first insight (single file) | < 7 min (median) | < 5 min |
| Time to first insight (multi-file) | < 12 min | < 8 min |
| Dashboard render latency (p95) | < 90s from intent submission | < 60s |
| Pipeline success rate | ≥ 70% without intervention beyond HITL | ≥ 85% |
| Cleaning plan acceptance | ≥ 75% of steps approved without modification | ≥ 85% |
| HITL cycle time | < 90s median | < 60s |
| Cost per pipeline | ≤ $0.30 (LLM + infra) | ≤ $0.15 |
| LLM provider portability | ≥ 2 providers | ≥ 4 providers |
| Pipeline reproducibility | 100% re-runnable from raw layer | 100% |
| Sync API response time | < 300ms p95 | < 300ms |
| Internal activation | ≥ 80% of internal testers reach a dashboard | ≥ 90% |

---

## 13. Deployment Architecture

| Environment | Compute | Database | Notes |
|---|---|---|---|
| Local dev | Docker Compose + LocalStack | Postgres (Docker) + Redis (Docker) | Synthetic data only |
| Staging | Single ECS service | Single-AZ RDS | Anonymised production-shape data |
| Production (P1) | Single ECS | Single-AZ RDS | Per-user S3 prefix isolation, full encryption |
| Production (P2) | Auto-scaling Fargate | Multi-AZ RDS | SQS queue-depth driven autoscaling |

**CI/CD (GitHub Actions):**
- PR opened → lint + typecheck + unit tests + Docker build (< 5 min)
- Merge to main → integration tests → deploy to staging → E2E happy path (< 10 min)
- Promote to prod → blue/green deploy on ECS → 10-min health-check with auto-rollback on > 1% error spike

---

## 14. Phase Boundaries

| Area | Phase 1 | Phase 2 |
|---|---|---|
| File formats | CSV, XLSX, JSON, Parquet | + XML, PDF (text extraction) |
| Multi-file merging | Same-format only | Cross-format merging |
| Cleaning operations | Exact dedup, imputation, type coercion, outlier flagging | + Fuzzy dedup, KNN imputation, LLM-assisted imputation |
| LLM providers | Anthropic Claude + OpenAI | + Gemini, Azure OpenAI, Bedrock, Ollama |
| Domain packs | 4 full packs + generic | 7+ packs + admin editor |
| Billing | None (architecture in place) | Stripe subscriptions + metered usage |
| Auth | Email + password | + SSO (SAML/OIDC) |
| Dashboard | 2 chart types + KPI cards | + Drill-down, export, iterative Q&A |
| Observability | CloudWatch | + OpenTelemetry + Grafana + PagerDuty |
| PII detection | Opt-in checkbox only | Full automated PII detection (Presidio) |
| API | Internal only | Public versioned REST API |
