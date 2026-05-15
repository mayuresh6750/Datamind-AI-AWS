# DataMind AI — Phase 1 Detailed Execution Plan

**Phase 1 Target:** 10 June 2026 | **Duration:** ≤ 30 working days
**Delivery:** Internal-use only. No payments. No public access.

---

## Features Overview

All Phase 1 features are tagged **P0** (must ship). Every P0 feature requires a demonstrable end-to-end run on a real file before shipping.

| Feature ID | Feature Name | Priority |
|---|---|---|
| F0a | Domain Selection | P0 |
| F1 | Multi-File, Multi-Format Ingestion | P0 |
| F1b | Multi-File Validation & Merge (HITL #1) | P0 |
| F2 | Storage Architecture — Type-Aware Routing | P0 |
| F3 | Cleaning Plan Generation | P0 |
| F3b | HITL Cleaning Approval (HITL #2) | P0 |
| F3c | Cleaning Execution + Audit Log | P0 |
| F4 | LLM Provider Abstraction | P0 |
| F5 | Intent Capture | P0 |
| F6 | Analysis Agent (SQL + Semantic) | P0 |
| F7 | Dashboard Generation (Vega-Lite) | P0 |
| F8 | Insights Narrative | P0 |
| F9 | Auth, RBAC, Dual UI | P0 |
| F10 | Operational Essentials (CI/CD, logging, observability) | P0 |

---

## Feature Details

### F0a — Domain Selection

**User story:** As a user, I want to tell DataMind which business domain I'm in so the agents use my language and propose the right KPIs.

**What ships:**
- Domain selector shown on first login with 6 options: Finance, Healthcare, Retail/eCommerce, Marketing, Operations, Other (+ free-text descriptor)
- Selection persisted at user-profile level; editable at any time
- Domain Agent loads matching prompt pack (vocabulary, KPIs, validation rules, chart preferences)
- Pack injected as context into all downstream agents

**Acceptance criteria:**
- Domain selector shown on first login
- User profile records the selected domain
- Subsequent pipelines pull the active domain pack into agent prompts (verifiable in trace)
- Changing domain takes effect on next pipeline; existing pipelines retain original domain
- 'Other' with free-text → generic pack + descriptor injected into prompt

**Edge cases:**
- User selects Other → generic pack used with free-text descriptor
- Domain change mid-session → applies to next pipeline only

---

### F1 — Multi-File, Multi-Format Ingestion

**User story:** As a user, I want to drag one or more files into the app and have them stored safely without thinking about formats.

**What ships:**
- Drag-and-drop or click-to-browse upload
- Formats: CSV, XLSX, JSON, Parquet (XML/PDF deferred to Phase 2)
- Single or multiple files per upload (max 10 files in Phase 1)
- All files in one upload must be the same format; mixing returns a clear error
- File size cap: 50MB per file, 250MB total per upload
- Frontend requests presigned S3 URLs; uploads directly to Layer 1 (raw bucket)
- Job ID returned within 2 seconds; format detection completes within 15 seconds

**Acceptance criteria:**
- Multi-file upload accepted; single job_id returned within 2s
- Format detection completes within 15s for entire file set
- Mixed-format upload returns clear error message
- Parquet files treated as already-columnar (skip conversion step)

**Edge cases:**
- Zero-byte files → reject with error
- Non-UTF-8 encoding → detect and flag
- CSVs with mixed delimiters → handle or surface to user
- XLSX with multiple sheets → prompt user to pick one per file (Phase 1)
- Parquet with incompatible schemas across files → surfaced in HITL #1

---

### F1b — Multi-File Validation & Merge (HITL #1)

**User story:** As a user, I want to see what the system thinks about my files and decide how they should be combined before anything changes.

**What ships:**
- Inferred schema preview per file shown to user
- System proposes: union (same columns, append rows) or join (different columns, merge on key)
- User can confirm or override: change merge key, change type-routing per column, exclude a column or file
- Nothing proceeds until user confirms

**HITL #1 — what the user sees and can do:**

| User sees | User can do |
|---|---|
| Inferred schema per file | Approve as-is |
| Proposed type-routing per column (numeric / textual / ambiguous) | Change type-routing for any column |
| Proposed merge plan (union or join + key) | Change merge key or merge strategy |
| Any ambiguous columns flagged | Exclude a column or exclude a file |

**Acceptance criteria:**
- Schema preview shown for every uploaded file
- Merge plan (union/join) proposed with reasoning
- User approval required before any cleaning step begins
- All user decisions recorded in audit log

---

### F2 — Storage Architecture (Type-Aware Routing)

**What ships:**

| Layer | Technology | Purpose |
|---|---|---|
| Layer 1 — Raw | AWS S3 (versioned, per-user prefix) | Immutable source of truth; original files preserved |
| Layer 2 — Curated | AWS S3 (Apache Parquet) | Cleaned, queryable columnar data |
| Layer 3 — Numeric/Structured | Postgres + DuckDB (in-process) | SQL queries over numeric, boolean, datetime, categorical columns |
| Layer 4 — Textual/Vector | pgvector on Postgres | Embeddings for free-text columns; semantic search |
| Metadata | PostgreSQL (AWS RDS, single-AZ) | Users, roles, datasets, pipeline runs, HITL decisions, audit, usage meters |

**Column classification rules:**

| Class | Detection Rule | Storage |
|---|---|---|
| Numeric / structured | dtype is int/float/bool/date; or string that parses cleanly; or low-cardinality categorical (≤ 50 distinct values) | Postgres + Parquet |
| Textual / semantic | dtype is string with avg length > 40 chars or distinct count > 50% of rows | pgvector + Parquet |
| Ambiguous | Does not fit above cleanly | Surfaced in HITL #1 for user decision |

**Acceptance criteria:**
- Raw files never modified; preserved in S3 with versioning
- Every cleaned dataset written to curated Parquet
- Numeric columns queryable via SQL (Postgres/DuckDB)
- Text columns embedded and queryable via pgvector
- All decisions reproducible from raw layer

---

### F3 — Cleaning Plan Generation

**User story:** As a user, I want to see exactly what the system plans to do to my data before anything changes.

**What ships:**
- Cleaning Plan Agent generates a numbered list of proposed actions
- Each action includes: action description, rationale, confidence score (0.0–1.0)
- Low-confidence steps (< 0.50) highlighted in red on the HITL #2 screen
- Nothing executes until user approves

**Phase 1 cleaning operations available for proposal:**

| Operation | Description |
|---|---|
| Exact duplicate removal | Remove identical rows |
| Missing-value imputation | Median / mode / drop / leave — agent picks; user can override |
| Type coercion | Parse columns to correct types (e.g., string → ISO date) |
| Basic outlier flagging | Flag statistical outliers; no auto-fix in Phase 1 |

**Acceptance criteria:**
- Plan is a numbered list with rationale + confidence per step
- Low-confidence steps visually highlighted
- Plan is generated without executing any cleaning
- Plan is stored for audit

---

### F3b — HITL Cleaning Approval (HITL #2)

**User story:** As a user, I want to approve, modify, or reject each cleaning step so I stay in control of my data.

**What ships:**
- Full cleaning plan shown to user
- User can: Approve all, approve some, modify a step (e.g., switch median → mean imputation), reject a step
- Submit triggers execution of only approved steps
- No data mutation before user submits

**HITL #2 — what the user sees and can do:**

| User sees | User can do |
|---|---|
| Numbered list of proposed cleaning steps | Approve all |
| Rationale + confidence per step | Approve selected steps only |
| Low-confidence steps highlighted in red | Modify a step (change strategy) |
| | Reject a step |

**Acceptance criteria:**
- No cleaning executes without user submission
- Only approved steps run
- Every decision (approve/modify/reject + rationale) recorded in audit log with user_id, timestamp, dataset_id, agent_step, original_proposal, final_decision

---

### F3c — Cleaning Execution + Audit Log

**What ships:**
- Cleaning Executor runs only approved steps
- Each step writes to curated Parquet (Layer 2)
- Numeric/structured columns loaded into Postgres/DuckDB (Layer 3)
- Textual columns embedded and loaded into pgvector (Layer 4)
- Full audit log entry per step: who approved, when, which provider/model, what changed

**Acceptance criteria:**
- Raw layer (Layer 1) never modified
- Cleaned output reproducible from raw layer on re-run
- Every step auditable with full trace

---

### F4 — LLM Provider Abstraction

**What ships:**
- All agent LLM calls go through a LiteLLM-compatible abstraction layer
- Phase 1 providers: Anthropic Claude + OpenAI
- Admin can configure: provider, model, per-agent routing (e.g., cheap model for profiling, premium for insights)
- Provider API keys stored in AWS Secrets Manager; never in env files or repo
- Structured JSON output enforced: invalid outputs trigger retry, then escalation
- Every LLM call records: tokens used, cost, wall-clock latency, attributed to user + tenant + agent + pipeline

**Acceptance criteria:**
- Pipeline runs end-to-end on both Anthropic Claude and OpenAI without code changes
- Per-agent model routing configurable from Admin UI
- Cost and latency tracked per call

---

### F5 — Intent Capture

**User story:** As a user, I want to ask a plain-English question about my data and get a relevant dashboard back.

**What ships:**
- Intent modal opens after HITL #2 cleaning approval
- Free-text input: "What are you trying to learn from this data?"
- Domain-tuned suggestion chips drawn from active prompt pack (e.g., Retail: 'Margin by SKU', 'AOV trend by channel')
- Intent Agent parses question into a structured analysis spec; biased by domain pack and available schema

**Example suggestion chips by domain:**

| Domain | Chips |
|---|---|
| Finance | MRR trend, Gross margin by segment, Churn by cohort |
| Healthcare | Readmission rate by department, Length of stay distribution |
| Retail/eCommerce | Margin by SKU, Repeat purchase rate by cohort, AOV trend by channel |
| Marketing | CPA by channel, LTV vs CAC, CTR trend |

**Acceptance criteria:**
- Intent screen opens after cleaning approval
- Domain chips rendered from active domain pack
- Intent parsed into structured spec used by Analysis Agent
- HITL #3 (lightweight): restated interpretation shown; user can approve or refine

---

### F6 — Analysis Agent (SQL + Semantic)

**What ships:**
- SQL queries on Postgres/DuckDB for numeric, datetime, and categorical questions
- Semantic search on pgvector for textual/free-form questions
- Combined queries when question spans both data types
- SQL validated as read-only before execution; DDL and write operations blocked

**Acceptance criteria:**
- Numeric questions answered via SQL
- Textual questions answered via semantic search
- No write operations permitted on curated layer
- Analysis results passed to Dashboard Agent as structured output

---

### F7 — Dashboard Generation (Vega-Lite)

**What ships:**
- Dashboard Agent converts analysis results into Vega-Lite specs
- Output: 2–3 KPI cards + 2 charts (bar, line, or table)
- Chart types drawn from a fixed Vega-Lite spec set (controlled set, not open-ended)
- Domain-flavoured framing applied to labels and titles

**Acceptance criteria:**
- Dashboard renders within 60 seconds of intent submission (p95 < 90s)
- Charts are relevant to the user's stated intent (≥ 70% in internal review)
- KPI cards reflect domain-appropriate metrics

---

### F8 — Insights Narrative

**What ships:**
- Insights Agent generates one paragraph of plain-English narrative
- Domain-flavoured framing (uses vocabulary from active prompt pack)
- Includes: what the data shows + a recommended next action

**Acceptance criteria:**
- Narrative rendered below charts on dashboard
- Domain-specific vocabulary used (verifiable by domain)
- Recommended action is actionable and relevant to the intent

---

### F9 — Auth, RBAC, and Dual UI

**What ships:**
- Email + password authentication; JWT tokens
- Two roles in Phase 1: **user** and **admin**
- RBAC enforced server-side via FastAPI middleware on every endpoint
- Frontend hides admin routes from non-admins but never trusts frontend alone
- Single workspace per user in Phase 1 (multi-workspace deferred)
- Admins invited; users self-register

**User UI screens:**
1. Sign up / log in
2. Domain selection (first run; editable)
3. File upload (drag-and-drop)
4. Schema & merge validation (HITL #1)
5. Cleaning plan review (HITL #2)
6. Intent capture + domain chips
7. Dashboard (KPI cards + charts + narrative)
8. History (past pipeline runs + audit log view)

**Admin UI screens:**
1. User & role management
2. LLM provider config (provider, model, per-agent routing)
3. Domain prompt pack viewer (read-only in Phase 1)
4. System health (pipeline status, error rates)
5. Audit log viewer (all HITL decisions)
6. Usage meter (pipeline counts, token usage — no billing)

**Acceptance criteria:**
- Admin routes return 403 for non-admin users (server-side enforced)
- JWT tokens validated on every protected endpoint
- SSO deferred to Phase 2

---

### F10 — Operational Essentials

**What ships:**
- CI/CD: GitHub Actions pipeline — lint, type-check, unit tests, image build, deploy to staging and prod on merge
- Structured JSON logging to CloudWatch
- Basic CloudWatch dashboards for key metrics
- Email alerting on error thresholds
- Celery + Redis for async job queue
- Pipeline state persisted to S3 + Postgres after every agent step (supports resume after HITL pause or failure)

**Acceptance criteria:**
- Every merge to main triggers full CI pipeline
- Logs are structured JSON queryable in CloudWatch
- Failed pipeline can be resumed from last completed agent step without re-running upstream

---

## HITL Checkpoint Summary

| Checkpoint | When | What user sees | What user can do |
|---|---|---|---|
| HITL #1 — Schema & Merge | After ingestion | Schema per file, type-routing per column, proposed merge plan | Approve, change merge key, change type-routing, exclude column/file |
| HITL #2 — Cleaning Plan | After plan generation | Numbered cleaning steps, rationale, confidence | Approve all/some, modify step, reject step |
| HITL #3 — Intent Confirmation | After intent capture | Restated interpretation of question | Approve or refine (lightweight in Phase 1) |

*HITL #4 (Dashboard Accept/Refine) — accept-only in Phase 1; full refinement in Phase 2.*

---

## Sprint Breakdown (30 Working Days)

### Sprint 1 — Days 1–5: Foundation

| Task | Owner Area |
|---|---|
| Git repo, branch strategy, PR templates | Eng |
| GitHub Actions: lint, type-check, test, build | DevOps |
| AWS infra: S3 buckets (raw + curated), RDS Postgres, Redis | Infra |
| FastAPI project structure, Pydantic v2 models | Backend |
| JWT auth + RBAC middleware | Backend |
| DB schema: users, roles, datasets, pipeline_runs, hitl_decisions, audit_log | Backend |
| Next.js 14 project setup, Tailwind, shadcn/ui | Frontend |
| Sign up / log in screens | Frontend |

### Sprint 2 — Days 6–10: Ingestion + Domain

| Task | Owner Area |
|---|---|
| File upload UI (drag-and-drop, presigned S3 URLs) | Frontend |
| Ingestion Agent: format detection, parsing (CSV, XLSX, JSON, Parquet) | Backend/AI |
| Multi-file merge plan generation (union vs join) | Backend/AI |
| Column type classification (numeric / textual / ambiguous) | Backend/AI |
| Domain Agent: prompt pack loader, Postgres lookup | Backend/AI |
| 4 domain prompt packs (Finance, Healthcare, Retail, Marketing) + generic | Backend/AI |
| Domain selection screen (first-run modal) | Frontend |

### Sprint 3 — Days 11–15: HITL #1 + Cleaning Plan

| Task | Owner Area |
|---|---|
| Schema & merge validation screen (HITL #1 UI) | Frontend |
| User override: merge key, type-routing, column exclusion | Frontend |
| HITL #1 API endpoint + audit log write | Backend |
| Cleaning Plan Agent: dedup, imputation, type coercion, outlier flagging | Backend/AI |
| Confidence scoring per cleaning step | Backend/AI |
| Cleaning plan API endpoint (returns plan, does not execute) | Backend |
| Celery job queue wiring for async pipeline steps | Backend |

### Sprint 4 — Days 16–20: HITL #2 + Storage Routing

| Task | Owner Area |
|---|---|
| Cleaning plan review screen (HITL #2 UI) | Frontend |
| Step-level approve / modify / reject interactions | Frontend |
| HITL #2 API endpoint + audit log write | Backend |
| Cleaning Executor: run approved steps only | Backend/AI |
| Write cleaned data to curated Parquet (Layer 2) | Backend |
| Load numeric columns into Postgres/DuckDB (Layer 3) | Backend |
| Embed textual columns into pgvector (Layer 4) | Backend |
| Pipeline state persistence (S3 + Postgres after each step) | Backend |

### Sprint 5 — Days 21–25: Intent + Dashboard + Insights

| Task | Owner Area |
|---|---|
| Intent capture screen + domain suggestion chips | Frontend |
| Intent Agent: parse free-text → structured analysis spec | Backend/AI |
| HITL #3: lightweight intent confirmation (show restated interpretation) | Frontend/Backend |
| Analysis Agent: SQL builder + DuckDB runner | Backend/AI |
| Analysis Agent: pgvector semantic search | Backend/AI |
| Dashboard Agent: Vega-Lite spec generation (2–3 KPIs + 2 charts) | Backend/AI |
| Dashboard render in User UI (Recharts / Vega-Lite embed) | Frontend |
| Insights Agent: domain-flavoured narrative + recommended action | Backend/AI |
| LLM provider abstraction layer (LiteLLM-compatible, Claude + OpenAI) | Backend/AI |

### Sprint 6 — Days 26–30: Admin UI + QA + Hardening

| Task | Owner Area |
|---|---|
| Admin UI: user & role management | Frontend |
| Admin UI: LLM provider config (provider, model, per-agent routing) | Frontend/Backend |
| Admin UI: domain pack viewer (read-only) | Frontend |
| Admin UI: system health, audit log viewer, usage meter | Frontend/Backend |
| AWS Secrets Manager integration for API keys | Backend/Infra |
| Structured JSON logging → CloudWatch, alerting | Infra |
| End-to-end pipeline testing (all 4 domains, multi-file, multi-provider) | QA |
| Performance testing: 50MB files, p95 dashboard latency < 90s | QA |
| Security: RBAC enforcement testing (403s for non-admin routes) | QA |
| Bug fix and polish | All |

---

## Phase 1 Acceptance Checklist

- [ ] Domain selector shown on first login; selection persists and affects agent prompts
- [ ] Multi-file upload (CSV, XLSX, JSON, Parquet) accepted; mixed-format returns error
- [ ] HITL #1 screen shows schema + merge plan; user override captured and logged
- [ ] Cleaning plan generated with numbered steps, rationale, and confidence scores
- [ ] HITL #2 screen allows step-level approve / modify / reject; nothing runs before submit
- [ ] Only approved cleaning steps execute; raw data never modified
- [ ] Cleaned data written to curated Parquet; numeric → Postgres/DuckDB; textual → pgvector
- [ ] Intent capture with domain suggestion chips; intent parsed into structured spec
- [ ] Dashboard renders (2–3 KPI cards + 2 charts) within 60s of intent submission
- [ ] Insights narrative generated with domain vocabulary
- [ ] Full audit log: every HITL decision recorded (user_id, timestamp, decision, rationale)
- [ ] Pipeline reproducible from raw layer (100%)
- [ ] Admin UI: all 6 screens functional; LLM config admin-controlled
- [ ] RBAC: admin routes return 403 for non-admin users (server-side enforced)
- [ ] Pipeline runs end-to-end on Anthropic Claude and OpenAI without code changes
- [ ] CI/CD: lint, type-check, tests pass on every merge to main
- [ ] CloudWatch logging and alerting live
- [ ] Cost per pipeline ≤ $0.30 verified in test runs

---

## What is Out of Scope for Phase 1

| Item | Deferred to |
|---|---|
| XML, PDF, OCR ingestion | Phase 2 |
| Cross-format multi-file merging | Phase 2 |
| Fuzzy/near-duplicate detection | Phase 2 |
| KNN and LLM-assisted imputation | Phase 2 |
| Database connectors (Postgres, BigQuery, Snowflake) | Phase 2 |
| Team workspaces, sharing, collaboration | Phase 2 |
| Full PII detection (opt-in checkbox only in P1) | Phase 2 |
| Stripe billing and paid plans | Phase 2 |
| SSO | Phase 2 |
| Domain prompt pack editor (read-only in P1) | Phase 2 |
| Webhook events, public REST API | Phase 2 |
| Scheduled pipeline refresh | Phase 2 |
| Google Gemini, Azure OpenAI, AWS Bedrock, Ollama | Phase 2 |
| Dashboard drill-down, export to PDF/PNG | Phase 2 |
| Iterative Q&A on same dataset | Phase 2 |
| OpenTelemetry tracing | Phase 2 |
| Mobile app, on-prem deployment | Permanently out of scope |
| Real-time / streaming ingestion | Permanently out of scope |
| Training custom ML models on user data | Permanently out of scope |
