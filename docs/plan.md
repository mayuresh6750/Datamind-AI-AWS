# DataMind AI — Phase 1 Project Plan

**Target:** 10 June 2026 | **Duration:** ≤ 30 working days | **Status:** Internal only, no billing

---

## 1. Objective

Deliver a working, end-to-end, multi-file, multi-domain agentic data pipeline with human-in-the-loop (HITL) cleaning and dual UI surfaces — at production quality — on a controlled internal surface.

---

## 2. Tech Stack

| Layer | Technology |
|---|---|
| Frontend (User + Admin UI) | Next.js 14 (App Router), TypeScript, Tailwind CSS, shadcn/ui, Recharts |
| Authentication | Supabase Auth (email/password, JWT session management, email verification, refresh tokens) |
| Backend / API Gateway | Python 3.11+, FastAPI, Pydantic v2, Supabase Auth JWT validation, RBAC middleware |
| Embeddings | Qwen3-Embedding-0.6B (sentence-transformers, self-hosted, 8K context, provider-neutral) |
| Agent Orchestration | FastAPI BackgroundTasks + `tasks.py` (Phase 1) |
| LLM Provider Layer | LiteLLM-compatible abstraction — Google Gemini 3.5 Flash |
| Ingestion / Conversion | Apache Arrow, Python stdlib (csv, json), openpyxl |
| Raw Storage (Layer 1) | Supabase Storage (versioned bucket, per-user prefix) |
| Curated Storage (Layer 2) | Supabase Storage — JSON |
| Numeric / Structured (Layer 3) | Supabase Database (PostgreSQL) + PostgreSQL (in-process) |
| Textual / Vector (Layer 4) | Supabase Vector (pgvector, HNSW index) |
| Metadata Store | Supabase Database (PostgreSQL, single-AZ) |
| Job Queue | FastAPI BackgroundTasks |
| Secrets | Supabase Vault |
| Observability | Prometheus + Grafana (metrics/alerts), structlog (JSON logs) |
| CI/CD | GitHub Actions + GitHub Container Registry (GHCR) |

---

## 3. Architecture Overview

DataMind is a three-tier, cloud-native system:

```
[User UI / Admin UI] → [FastAPI Gateway] → [BackgroundTasks → tasks.py → Agents]
               ↓
       [LiteLLM Abstraction — Google Gemini 3.5 Flash / Google Gemini 3.5 Flash]
               ↓
   [Supabase Storage Raw] [Supabase Storage Curated Parquet]
     [Supabase Database / PostgreSQL] [Supabase Vector (pgvector)]
```

**Data flow (11 steps):**
1. Domain selection → Domain Agent loads prompt pack
2. File upload → Supabase Storage raw (Layer 1)
3. Ingestion Agent: detect format, parse, profile, classify columns
4. **HITL #1** — schema + merge validation (user confirms union/join plan)
5. Cleaning Plan Agent: generate numbered plan with rationale + confidence
6. **HITL #2** — cleaning plan approval (user approves / modifies / rejects)
7. Cleaning Executor: run approved steps → write to Parquet (Layer 2), load Supabase Database/PostgreSQL + Supabase Vector (pgvector)
8. Intent capture: free-text question + domain-tuned suggestion chips
9. Analysis Agent: SQL (numeric) + semantic search on Supabase Vector (pgvector) (textual)
10. Dashboard Agent: generate Vega-Lite specs (2–3 KPI cards + 2 charts)
11. Insights Agent: plain-English narrative + recommended next action

---

## 4. Dual UI Surfaces

### User UI
| Screen | Purpose |
|---|---|
| Domain Selection | Pick domain on first run; editable anytime |
| File Upload | Drag-and-drop; single or multi-file (same format) |
| Schema & Merge Validation | HITL #1 — confirm/override union or join plan |
| Cleaning Plan Review | HITL #2 — approve / modify / reject each cleaning step |
| Intent Capture | Free-text question + domain-tuned suggestion chips |
| Dashboard | KPI cards + charts + narrative |
| History | View past pipeline runs and audit log |

### Admin UI
| Screen | Purpose |
|---|---|
| User & Role Management | Provision users, assign roles |
| LLM Provider Config | Set provider, model, per-agent routing |
| Domain Pack Viewer | Read-only view of domain prompt packs (P1) |
| System Health | Pipeline status, error rates |
| Audit Log Viewer | Every HITL decision recorded |
| Usage Meter | Pipeline run counts, token usage (no billing in P1) |

---

## 5. Agent Set (Phase 1)

| Agent | Role |
|---|---|
| Supervisor | Orchestrates pipeline; enforces HITL gates |
| Domain | Loads domain prompt pack; supplies context to all agents |
| Ingestion | Detects format, parses, profiles, classifies columns, drafts merge plan |
| Cleaning Plan | Generates numbered plan with rationale + confidence per step |
| Cleaning Executor | Executes only user-approved steps; writes audit log |
| Intent | Parses natural-language goal into structured analysis spec |
| Analysis | SQL on Supabase Database/PostgreSQL (numeric); semantic search on Supabase Vector (pgvector) (textual) |
| Dashboard | Converts analysis results into Vega-Lite chart specs |
| Insights | Generates domain-flavoured narrative + recommended next action |

---

## 6. Domain Prompt Packs (Phase 1)

| Domain | Key KPIs & Focus |
|---|---|
| Finance | Revenue, gross margin, MRR/ARR, churn, AR aging, cohort retention |
| Healthcare | Patient counts, readmission rate, length of stay, ICD-10/CPT codes |
| Retail/eCommerce | AOV, repeat purchase rate, SKU margin, inventory turn, return rate |
| Marketing | CTR, CPA, CAC, LTV, channel attribution, UTM hygiene |
| Other / Operations | Generic counts, throughput, cycle time (generic pack) |

---

## 7. Timeline — 30 Working Days

| Week | Focus | Key Deliverables |
|---|---|---|
| Week 1 (Days 1–5) | Foundation | Repo setup, CI/CD, Supabase Auth + RBAC, DB schema, Supabase Storage buckets + Database, FastAPI BackgroundTasks wiring |
| Week 2 (Days 6–10) | Ingestion + Domain | File upload UI, format detection, multi-file merge plan, Domain Agent + 4 prompt packs |
| Week 3 (Days 11–15) | HITL #1 + Cleaning | Schema/merge validation screen (HITL #1), Cleaning Plan Agent, confidence scoring |
| Week 4 (Days 16–20) | HITL #2 + Storage routing | Cleaning plan review screen (HITL #2), Cleaning Executor, Supabase Database/PostgreSQL + Supabase Vector (pgvector) loading |
| Week 5 (Days 21–25) | Intent + Dashboard | Intent capture UI, Analysis Agent (SQL + Supabase Vector (pgvector) semantic), Dashboard Agent (Vega-Lite), Insights Agent |
| Week 6 (Days 26–30) | Admin UI + QA | Admin UI (all screens), LLM provider config, end-to-end testing, observability, bug fix |

---

## 8. Non-Negotiables

These features cannot be cut regardless of schedule pressure:

- HITL cleaning review (users must approve before any data mutation)
- Dual UI separation (User UI and Admin UI as distinct surfaces)
- Type-aware storage routing (numeric → Supabase Database/PostgreSQL; textual → Supabase Vector (pgvector))

---

## 9. Scope Cut Order (if timeline slips)

1. Drop Parquet input format
2. Drop two domain packs (keep Finance + Retail; drop Healthcare + Marketing)
3. Drop second LLM provider (keep Google Gemini 3.5 Flash only)
4. Drop JSON ingestion
5. Drop XLSX ingestion

---

## 10. Phase 1 KPIs

| Metric | Target |
|---|---|
| Time to first insight (single file) | < 7 minutes (median) |
| Time to first insight (multi-file) | < 12 minutes |
| Pipeline success rate | ≥ 70% without manual intervention beyond HITL |
| Cleaning plan acceptance | ≥ 75% of steps approved without modification |
| HITL cycle time | < 90 seconds median |
| Intent–chart relevance | ≥ 70% rated relevant |
| Cost per pipeline | ≤ $0.30 (LLM + infra) |
| Dashboard latency (p95) | < 90 seconds |
| Internal activation | ≥ 80% of internal testers reach a dashboard end-to-end |
| Pipeline reproducibility | 100% re-runnable from raw layer |

---

## 11. Out of Scope (Phase 2+)

- XML, PDF, OCR ingestion
- Cross-format multi-file merging
- Fuzzy dedup, KNN imputation, LLM-assisted imputation
- Database connectors (Postgres, BigQuery, Snowflake)
- Team workspaces, sharing, collaboration
- Full PII detection (opt-in checkbox only in P1)
- Stripe billing and paid plans
- SSO, mobile app, on-prem deployment
- Domain pack editor (read-only in P1)
- Webhook events, public API, scheduled refresh
