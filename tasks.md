# DataMind AI — Phase 1 Task List

**Project:** DataMind AI | **Phase:** 1 | **Timeline:** May 6 – June 10, 2026 (5 Sprints)
**Team Lead:** Smita | **Total Tasks:** 78

---

## Team Roles

| Role Code | Role | Responsibility |
|---|---|---|
| **FE** | Frontend Developer | Next.js 14, TypeScript, Tailwind, shadcn/ui, Recharts, Vega-Lite |
| **BE** | Backend Developer | FastAPI, Pydantic v2, Supabase Database (PostgreSQL), Alembic, Celery, Redis |
| **AI** | AI / Agent Engineer | LangGraph agents, LLM abstraction (Mistral + Kimi), Weaviate, DuckDB, domain packs |
| **DO** | DevOps / Infra Engineer | Supabase (Storage + Database + Vault), Docker, GitHub Actions CI/CD, GHCR, Prometheus/Grafana |
| **QA** | QA Engineer | Unit tests, integration tests, E2E tests, golden datasets, performance |

---

## Task ID Convention

```
S{sprint}-{seq}   e.g. S1-01, S3-07
```

Priority: **P1** = Must-have (blocks release) | **P2** = High | **P3** = Medium

---

## Sprint 1 — Foundation
**Dates:** May 6–9, 2026 | **Goal:** Repo live, auth working, infra provisioned, CI/CD green

**Exit criteria:** User can sign up, log in, hit `/health`. CI/CD deploys to staging.

| Task ID | Task | Role | Priority | Points | Depends On |
|---|---|---|---|---|---|
| S1-01 | Set up Git repo, branch strategy, PR template, CODEOWNERS | DO | P1 | 1 | — |
| S1-02 | GitHub Actions CI/CD — lint (ruff, eslint), typecheck (mypy, tsc), unit tests, Docker build, push to GHCR, staging deploy | DO | P1 | 3 | S1-01 |
| S1-03 | Provision Supabase project — Storage buckets (raw + curated), Database (PostgreSQL, single-AZ), Vault for secrets, Redis | DO | P1 | 3 | — |
| S1-04 | Docker Compose for local dev — Supabase local emulator (Postgres) + Weaviate + Redis | DO | P1 | 2 | — |
| S1-05 | FastAPI project structure — routers, middleware, dependencies, pyproject.toml, uv workspace | BE | P1 | 2 | S1-04 |
| S1-06 | Database schema + Alembic migrations — users, tenants, datasets, pipeline_runs, hitl_decisions, audit_events, jobs, llm_provider_config | BE | P1 | 3 | S1-03, S1-04 |
| S1-07 | JWT auth endpoints — POST /auth/signup, /auth/login, /auth/refresh, /auth/logout | BE | P1 | 3 | S1-06 |
| S1-08 | RBAC middleware — role claim enforcement on every FastAPI route | BE | P1 | 2 | S1-07 |
| S1-09 | GET /health endpoint — checks Supabase Database, Redis, Supabase Storage connectivity | BE | P1 | 1 | S1-05, S1-03 |
| S1-10 | Next.js 14 project setup — TypeScript, Tailwind CSS, shadcn/ui, pnpm workspace | FE | P1 | 2 | — |
| S1-11 | Sign up / Sign in screens (U1) — form validation, JWT storage, redirect logic | FE | P1 | 3 | S1-07, S1-10 |
| S1-12 | .env.example, local dev README, team onboarding docs | DO | P2 | 1 | S1-04 |

**Sprint 1 Total: 12 tasks | 26 points**

---

## Sprint 2 — Ingestion + Domain Awareness
**Dates:** May 12–16, 2026 | **Goal:** Multi-file upload working. Domain persists. HITL #1 screen renders.

**Exit criteria:** Domain persists to DB. Multi-file upload accepted. Schema preview visible.

| Task ID | Task | Role | Priority | Points | Depends On |
|---|---|---|---|---|---|
| S2-01 | Domain selection screen (U2) — first-run modal, 6 options, free-text for Other, persist to user profile | FE | P1 | 2 | S1-11 |
| S2-02 | PATCH /me/domain API endpoint — update active domain on user profile | BE | P1 | 1 | S1-08 |
| S2-03 | File upload screen (U3) — drag-and-drop, browse, multi-file, format validation, progress bar | FE | P1 | 3 | S1-11 |
| S2-04 | POST /datasets/upload-url — generate presigned Supabase Storage URLs for direct browser upload (per file) | BE | P1 | 2 | S1-08 |
| S2-05 | POST /datasets/{id}/ingest — enqueue Celery ingestion job, return job_id | BE | P1 | 2 | S2-04 |
| S2-06 | Ingestion Agent — format detection (mime sniff + content sniff) for CSV, XLSX, JSON, Parquet | AI | P1 | 3 | S1-05 |
| S2-07 | Ingestion Agent — parsing + column profiling (row count, dtype, null count, distinct count, avg string length) | AI | P1 | 3 | S2-06 |
| S2-08 | Ingestion Agent — multi-file merge plan (UNION vs JOIN detection, merge key proposal, confidence) | AI | P1 | 3 | S2-07 |
| S2-09 | Column type classification — numeric / textual / ambiguous routing rules | AI | P1 | 2 | S2-07 |
| S2-10 | Domain Agent — prompt pack loader, Supabase Database lookup per domain, pack injection into agent context | AI | P1 | 2 | S1-06 |
| S2-11 | Domain prompt packs — Finance, Healthcare, Retail/eCommerce, Marketing, Other (YAML/JSON, versioned) | AI | P1 | 4 | S2-10 |
| S2-12 | GET /jobs/{id} — poll job status (queued / running / paused / done / failed), progress %, current step | BE | P1 | 2 | S2-05 |

**Sprint 2 Total: 12 tasks | 29 points**

---

## Sprint 3 — HITL #1 + Cleaning Plan + LLM Abstraction
**Dates:** May 19–23, 2026 | **Goal:** Cleaning plan generated. HITL #1 + #2 screens rendered. LLM abstraction live.

**Exit criteria:** Cleaning plan generated and displayed. ≥ 60% acceptance on golden datasets 1–5.

| Task ID | Task | Role | Priority | Points | Depends On |
|---|---|---|---|---|---|
| S3-01 | Schema & merge validation screen (HITL #1, U4) — per-file schema table, type-routing badges, merge plan card | FE | P1 | 4 | S2-03, S2-12 |
| S3-02 | HITL #1 interaction — column type-routing override, merge key change, exclude column/file | FE | P1 | 3 | S3-01 |
| S3-03 | GET /datasets/{id}/merge-plan — return ingestion profile with schema, type-routing, merge proposal | BE | P1 | 2 | S2-05 |
| S3-04 | POST /datasets/{id}/merge-plan/decision — record user decision in hitl_decisions, enqueue next step | BE | P1 | 2 | S3-03 |
| S3-05 | LangGraph Supervisor — state machine setup, step routing, HITL pause/resume, retry on failure | AI | P1 | 4 | S1-05 |
| S3-06 | HITL Gate Manager — pause_pipeline_for_decision(), resume_pipeline_with_decision(), state snapshot to Supabase Storage | AI | P1 | 3 | S3-05 |
| S3-07 | Pipeline state persistence — serialise full pipeline state to Supabase Storage + Supabase Database after every agent step | BE | P1 | 3 | S3-05, S1-03 |
| S3-08 | LLM Provider Abstraction — LiteLLM-compatible interface, structured_completion(), Pydantic output validation, retry logic (3×) | AI | P1 | 4 | S1-05 |
| S3-09 | Mistral provider — API key from Supabase Vault, structured JSON mode, token/cost/latency logging | AI | P1 | 2 | S3-08 |
| S3-10 | Moonshot Kimi provider — API key from Supabase Vault, structured JSON mode, token/cost/latency logging | AI | P1 | 2 | S3-08 |
| S3-11 | Cleaning Plan Agent — exact dedup detection + imputation strategy (median/mean/mode/drop/leave) | AI | P1 | 3 | S3-05, S3-08 |
| S3-12 | Cleaning Plan Agent — type coercion proposals + basic outlier flagging (no auto-fix) | AI | P1 | 3 | S3-11 |
| S3-13 | Confidence scoring — 0.0–1.0 per step, colour thresholds (red <0.50, orange <0.70, yellow <0.90) | AI | P1 | 2 | S3-11 |
| S3-14 | GET /datasets/{id}/cleaning-plan — return numbered steps with rationale + confidence | BE | P1 | 1 | S3-11 |

**Sprint 3 Total: 14 tasks | 38 points**

---

## Sprint 4 — HITL #2 + Storage Routing + Analysis + Dashboard
**Dates:** May 26–30, 2026 | **Goal:** End-to-end happy path working for CSV and Parquet merge.

**Exit criteria:** Full pipeline runs end-to-end. Dashboard renders within 90s. Analysis returns correct results.

| Task ID | Task | Role | Priority | Points | Depends On |
|---|---|---|---|---|---|
| S4-01 | Cleaning plan review screen (HITL #2, U5) — numbered steps, confidence badges, per-step approve/modify/reject | FE | P1 | 4 | S3-01, S3-14 |
| S4-02 | Modify step UI — imputation strategy picker, column exclusion, custom value input | FE | P1 | 3 | S4-01 |
| S4-03 | POST /datasets/{id}/cleaning-plan/decision — record approved/modified/rejected steps, enqueue executor | BE | P1 | 2 | S3-04 |
| S4-04 | Cleaning Executor Agent — run only approved steps against curated Parquet, write audit event per step | AI | P1 | 3 | S3-11, S4-03 |
| S4-05 | Write cleaned data to curated Supabase Storage Parquet (Layer 2) — versioned per cleaning run | BE | P1 | 2 | S4-04 |
| S4-06 | Load numeric/structured columns into Supabase Database table (Layer 3) — one typed table per dataset_id | BE | P1 | 3 | S4-05 |
| S4-07 | Embed textual columns + load into Weaviate (Layer 4) — HNSW index, per-tenant collection namespace | AI | P1 | 3 | S4-05 |
| S4-08 | Intent capture screen (U6) — free-text input, domain-tuned suggestion chips, HITL #3 confirmation | FE | P1 | 3 | S4-01 |
| S4-09 | POST /datasets/{id}/intent — submit intent text, return restated interpretation for HITL #3 | BE | P1 | 1 | S4-05 |
| S4-10 | Intent Agent — parse free-text goal into structured AnalysisSpec, biased by domain pack + schema | AI | P1 | 3 | S3-08, S3-05 |
| S4-11 | Analysis Agent — SQL builder (sqlglot) + DuckDB runner for numeric questions (Layer 3) | AI | P1 | 3 | S4-06, S4-10 |
| S4-12 | Analysis Agent — Weaviate semantic search for textual questions (Layer 4) | AI | P1 | 3 | S4-07, S4-10 |
| S4-13 | SQL safety validation — sqlglot parse, block all non-SELECT statements before execution | BE | P1 | 2 | S4-11 |
| S4-14 | POST /dashboards/generate — enqueue dashboard generation job, return job_id | BE | P1 | 1 | S4-11 |
| S4-15 | Dashboard Agent — Vega-Lite spec generation (2–3 KPI cards + 2 charts: bar/line/table) | AI | P1 | 4 | S4-11, S4-12 |
| S4-16 | Insights Agent — domain-flavoured narrative + recommended next action, factual consistency check | AI | P1 | 3 | S4-15 |
| S4-17 | Dashboard screen (U7) — render KPI cards + Vega-Lite charts + narrative, polling until ready | FE | P1 | 4 | S4-15 |

**Sprint 4 Total: 17 tasks | 46 points**

---

## Sprint 5 — Admin UI + QA + Hardening
**Dates:** Jun 2–6, 2026 | **Goal:** Internal beta ready. All acceptance criteria met.

**Exit criteria:** Internal beta with 5 users for 1 week. All Phase 1 NFR targets met.

| Task ID | Task | Role | Priority | Points | Depends On |
|---|---|---|---|---|---|
| S5-01 | Admin UI — System Health screen (A1): pipeline status, job queue depth, error rates | FE | P1 | 2 | S1-11 |
| S5-02 | Admin UI — User & Role Management screen (A2): list, invite, suspend, change role | FE | P1 | 3 | S5-01 |
| S5-03 | Admin UI — LLM Provider Config screen (A3): provider, model, per-agent routing | FE | P1 | 3 | S5-01 |
| S5-04 | Admin UI — Domain Pack Viewer screen (A4): read-only pack viewer | FE | P2 | 2 | S5-01 |
| S5-05 | Admin UI — Audit Log Viewer screen (A5): search HITL decisions + cleaning actions | FE | P1 | 2 | S5-01 |
| S5-06 | History / Audit screen for users (U8): past pipeline runs, downloadable audit log (JSON/CSV) | FE | P2 | 2 | S4-17 |
| S5-07 | All admin API endpoints — /admin/users, /admin/llm-providers, /admin/domain-packs, /admin/health, /admin/audit | BE | P1 | 4 | S1-08 |
| S5-08 | GET /jobs/{id}/audit — return full audit log for a pipeline run | BE | P1 | 1 | S4-04 |
| S5-09 | Supabase Vault integration — store and retrieve LLM API keys per tenant at runtime; never from env files or repo | DO | P1 | 2 | S3-09, S3-10 |
| S5-10 | Prometheus metrics endpoint + structlog JSON logging — per request and per agent step, log level per env | DO | P1 | 2 | S1-02 |
| S5-11 | Grafana dashboards + alerting — all 7 alert conditions (job failure, latency, Supabase Storage write, LLM error, HITL queue, spend, confidence) | DO | P1 | 3 | S5-10 |
| S5-12 | Staging deployment — Docker Compose / Render, GHCR image pull, Supabase Database migration on deploy | DO | P1 | 3 | S1-02, S1-03 |
| S5-13 | Unit tests — agent functions, transform logic, API handlers (≥ 70% coverage) | QA | P1 | 3 | S4-16 |
| S5-14 | Integration tests — agent-to-agent, Supabase Storage reads/writes, DuckDB, Weaviate (happy paths + key errors) | QA | P1 | 3 | S4-16 |
| S5-15 | E2E tests — single-file pipeline for all 4 formats (CSV, XLSX, JSON, Parquet) | QA | P1 | 4 | S4-17 |
| S5-16 | E2E tests — multi-file pipeline (2-file + 5-file, union + join paths) | QA | P1 | 3 | S4-17 |
| S5-17 | HITL flow tests — all decision branches per gate (#1, #2, #3): approve / modify / reject | QA | P1 | 3 | S4-17 |
| S5-18 | RBAC enforcement tests — 403 for all admin routes with non-admin token (full matrix) | QA | P1 | 2 | S5-07 |
| S5-19 | LLM portability tests — run full pipeline on Mistral + Moonshot Kimi, verify no quality regression | QA | P1 | 3 | S5-14 |
| S5-20 | Performance tests — 50MB single file, p95 dashboard latency < 90s, HITL cycle time < 90s median | QA | P1 | 2 | S5-15 |
| S5-21 | Golden dataset validation — 10 datasets, ≥ 70% cleaning acceptance rate | QA | P1 | 4 | S5-15 |
| S5-22 | Bug fixes + polish from QA findings | ALL | P1 | 4 | S5-21 |
| S5-23 | Internal beta setup — 5 users onboarded, staging access, feedback collection | DO | P1 | 2 | S5-12 |

**Sprint 5 Total: 23 tasks | 63 points**

---

## Summary

| Sprint | Dates | Tasks | Points | Primary Roles |
|---|---|---|---|---|
| Sprint 1 — Foundation | May 6–9 | 12 | 26 | BE, DO, FE |
| Sprint 2 — Ingestion + Domain | May 12–16 | 12 | 29 | AI, BE, FE |
| Sprint 3 — HITL #1 + Cleaning + LLM | May 19–23 | 14 | 38 | AI, BE, FE |
| Sprint 4 — HITL #2 + Storage + Dashboard | May 26–30 | 17 | 46 | AI, BE, FE |
| Sprint 5 — Admin UI + QA + Hardening | Jun 2–6 | 23 | 63 | ALL |
| **Total** | | **78 tasks** | **202 points** | |

---

## Task Assignment Guide

Assign tasks to individuals within each role. Recommended team composition for Phase 1:

| Slot | Role | Sprints Most Active | Key Tasks |
|---|---|---|---|
| Member 1 | Frontend Lead | All | S1-11, S2-01/03, S3-01/02, S4-01/02/08/17, S5-01–06 |
| Member 2 | Backend Lead | All | S1-06/07/08, S2-04/05/12, S3-03/04/07, S4-03/05/06/09/13/14, S5-07/08 |
| Member 3 | AI / Agent Lead | S2–S4 | S2-06–11, S3-05/06/08–13, S4-04/07/10–12/15/16 |
| Member 4 | DevOps / Infra | S1, S5 | S1-01–04/12, S5-09–12/23 |
| Member 5 | QA Engineer | S5 (+ test writing S3–S4) | S5-13–22 |

---

## Definition of Done (per task)

A task is **Done** when:
- [ ] Code is written with tests (unit or integration as appropriate)
- [ ] PR opened against `development` with the PR template filled
- [ ] CI passes (lint + typecheck + tests + build)
- [ ] At least one reviewer has approved
- [ ] Squash-merged to `development`
- [ ] Team lead updated the sprint tracker (Excel planner)

---

## Phase 1 Acceptance Checklist (End of Sprint 5)

- [ ] Domain selector shown on first login; persists and affects agent prompts
- [ ] Multi-file upload (CSV, XLSX, JSON, Parquet) accepted; mixed-format returns clear error
- [ ] HITL #1 screen shows schema + merge plan; user override captured and logged
- [ ] Cleaning plan generated with numbered steps, rationale, confidence scores
- [ ] HITL #2 allows step-level approve/modify/reject; nothing runs before submit
- [ ] Only approved cleaning steps execute; raw data (Layer 1) never modified
- [ ] Cleaned data in curated Parquet (Supabase Storage); numeric → Supabase Database/DuckDB; textual → Weaviate
- [ ] Intent capture with domain chips; parsed into structured analysis spec
- [ ] Dashboard renders (2–3 KPI cards + 2 charts) within 90s of intent submission
- [ ] Insights narrative generated with domain vocabulary
- [ ] Full audit log: every HITL decision recorded
- [ ] Pipeline re-runnable from raw layer (100%)
- [ ] Admin UI — all 5 screens functional; LLM config admin-controlled
- [ ] RBAC: admin routes return 403 for non-admin users (server-side enforced)
- [ ] Pipeline runs end-to-end on Mistral AND Moonshot Kimi
- [ ] CI/CD: lint + typecheck + tests pass on every merge; images pushed to GHCR
- [ ] Prometheus metrics + Grafana alerting live
- [ ] Cost per pipeline ≤ $0.30 verified in test runs
- [ ] Internal beta with 5 users for 1 week completed
