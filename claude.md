# DataMind AI - Claude Project Instructions

## Project Overview

DataMind AI is an agentic data intelligence platform that transforms raw business data into clean, contextual dashboards and actionable business decisions without requiring SQL or Python knowledge. The platform treats data preparation, analysis, and decision support as one continuous, agent-driven workflow that is explicitly aware of the user's business domain.

---

## Core Principles

### Four Foundational Design Principles

1. **Domain-first approach**: Always ask users what domain they work in (Finance, Healthcare, Retail, Marketing, Operations, or Other) so all downstream agents apply domain-appropriate vocabulary, KPIs, and validation rules

2. **User-controlled data modeling**: Accept single or multiple files (CSV, XLSX, JSON, Parquet) and let the user decide how files should be merged or modeled

3. **Human-in-the-loop (HITL) cleaning**: Never run data cleaning silently — every cleaning step is proposed as a plan, the user approves/modifies/rejects each action, and only then does the agent execute

4. **Type-aware storage routing**: Route data by type — numeric/structured columns to relational stores, free-text columns to vector stores — so analysis uses the right tool for each kind of question

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

- **Finance**: revenue, COGS, gross margin, churn, MRR/ARR, runway
- **Healthcare**: patient counts, readmission rate, length of stay, ICD-10/CPT codes
- **Retail/eCommerce**: AOV, repeat purchase, SKU margin, inventory turn
- **Marketing**: CTR, CPA, CAC, LTV, attribution windows
- **Operations**: throughput, cycle time, generic counts
- **Other**: with free-text descriptor

---

## Technical Architecture

### Technology Stack

| Layer | Technology |
|-------|------------|
| Frontend - User UI | Next.js 14, TypeScript, Tailwind CSS, shadcn/ui, Recharts |
| Frontend - Admin UI | Next.js (route group /admin/*), RBAC-gated |
| API Gateway | Python 3.11+, FastAPI, Pydantic v2, JWT auth |
| Agent Orchestration | LangGraph (supervisor pattern), Pydantic-validated outputs |
| LLM Provider Layer | LiteLLM-compatible abstraction; Anthropic Claude + OpenAI (Phase 1) |
| Raw Storage (Layer 1) | AWS S3 (versioned bucket, per-user prefix) |
| Curated Storage (Layer 2) | AWS S3, Apache Parquet format |
| Numeric/Structured (Layer 3) | PostgreSQL + DuckDB |
| Textual/Vector (Layer 4) | pgvector on PostgreSQL |
| Metadata Store | PostgreSQL (AWS RDS) |
| Job Queue | Celery + Redis (Phase 1); AWS SQS + Fargate (Phase 2) |

### Four-Layer Storage Architecture

1. **Layer 1 (Raw)**: AWS S3 bucket with versioning — original files preserved unmodified
2. **Layer 2 (Curated)**: AWS S3 bucket with cleaned data in Apache Parquet format
3. **Layer 3 (Numeric/Structured)**: PostgreSQL for numeric, boolean, datetime, and low-cardinality categorical data
4. **Layer 4 (Textual/Semantic)**: pgvector for embeddings of free-text columns

### Data Type Classification Rules

| Class | Detection Rule | Storage Path |
|-------|----------------|--------------|
| Numeric/Structured | int/float/bool/date dtype, or low-cardinality categorical (≤50 distinct values) | PostgreSQL + Parquet |
| Textual/Semantic | String with avg length >40 chars or distinct count >50% of rows | pgvector + Parquet |
| Ambiguous | Does not fit above rules | Surfaced in HITL #1 for user decision |

---

## Agent System

### Agent Definitions

| Agent | Role | Phase |
|-------|------|-------|
| Supervisor | Orchestrates pipeline; routes, retries, aggregates; enforces HITL gates | P1 |
| Domain | Loads domain prompt pack and exposes it to all downstream agents | P1 |
| Ingestion | Detects format, parses, profiles, classifies columns, drafts merge plan | P1 |
| Cleaning Plan | Drafts numbered cleaning plan with rationale + confidence. Does NOT execute. | P1 |
| Cleaning Executor | Executes only user-approved steps, logs each action | P1 |
| Intent | Parses user's natural-language goal into structured analysis spec | P1 |
| Analysis | Runs SQL on PostgreSQL/DuckDB for numeric; semantic search on pgvector for textual | P1 |
| Dashboard | Converts analysis results into Vega-Lite specs | P1 |
| Insights | Generates domain-flavored narrative + recommended next action | P1 |
| Outlier (advanced) | Flags statistical outliers; recommends keep/clip/remove | P2 |
| Fuzzy Dedup | Detects near-duplicate rows using fuzzy string match | P2 |
| Smart Imputation | KNN imputation; LLM-assisted for high-cardinality categoricals | P2 |
| PII Detection | Detects emails, phones, common ID patterns; gates LLM context | P2 |

### HITL Checkpoints

| Checkpoint | What User Sees | User Actions |
|------------|----------------|--------------|
| #1 Schema & Merge Validation | Inferred schema per file, proposed type-routing, proposed merge plan | Approve, change merge key, change type-routing, exclude column/file |
| #2 Cleaning Plan Approval | Numbered list of proposed cleaning actions with rationale and confidence | Approve all, approve some, modify steps, reject |
| #3 Intent Confirmation | Restated interpretation of user's question | Approve, refine intent |
| #4 Dashboard Accept/Refine | Generated dashboard with feedback options | Accept, request changes, ask follow-up (P2) |

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
2. **Upload**: User drags files into UI; files upload directly to Layer 1 (raw S3)
3. **Detect & Profile**: Ingestion Agent inspects files, classifies columns
4. **HITL #1**: User confirms schema, merge plan, type-routing
5. **Cleaning Plan**: Cleaning Agent generates numbered plan (no execution)
6. **HITL #2**: User reviews and approves/modifies cleaning steps
7. **Execute & Route**: Approved cleaning runs; data routes to appropriate storage layers
8. **Intent**: User states question; Intent Agent embeds and matches against schema
9. **Analyze**: Analysis Agent runs SQL or semantic search as appropriate
10. **Dashboard**: Dashboard Agent generates Vega-Lite chart specs
11. **Insight**: Insights Agent generates narrative and recommended action

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
- Automatic classification of columns
- Routing to PostgreSQL/DuckDB or pgvector based on type
- Ambiguous columns flagged for user decision

### F2 — Two-Layer Storage
- Layer 1: Original files preserved unmodified
- Layer 2: Cleaned data in Apache Parquet

### F3 — HITL Cleaning
- **Plan phase**: Agent generates numbered list of proposed actions
- **Approve phase**: User reviews, approves/modifies/rejects
- **Execute phase**: Only approved steps run
- Operations: exact dedup, missing-value imputation, type coercion, basic outlier flagging

### F4 — Intent Capture (HITL #3)
- Free-text input: "What are you trying to learn?"
- Domain-tuned suggestion chips
- Intent Agent restates interpretation for user confirmation

### F5 — Dashboard Generation
- 2–3 KPI cards plus 2 charts (line, bar, table)
- Domain-flavored narrative from Insights Agent
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
- Phase 1: Anthropic Claude + OpenAI
- Per-tenant defaults with per-agent overrides
- Cost and latency tracking per provider/agent

---

## Phase 2 Additions

- Advanced cleaning: fuzzy dedup, KNN imputation, LLM-assisted imputation, outlier handling
- Additional LLM providers: Google Gemini, Azure OpenAI, AWS Bedrock, Ollama
- PII Detection Agent
- Iterative Q&A on same dataset
- Project/workspace organization
- Public REST API
- Stripe-backed monetization (Free/Pro/Team/Enterprise tiers)
- Domain pack editor (full editing vs. read-only in P1)

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
| LLM Provider Portability | ≥ 2 providers | ≥ 4 providers |

---

## API Design

### Core Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | /api/v1/auth/signup | Create account |
| POST | /api/v1/auth/login | Issue JWT |
| PATCH | /api/v1/me/domain | Update active domain |
| POST | /api/v1/datasets/upload-url | Get presigned S3 URLs |
| POST | /api/v1/datasets/{id}/ingest | Trigger format detection |
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

- JWT authentication (HS256, 1-hour expiry, refresh tokens)
- Argon2 password hashing
- RBAC with two roles: user, admin
- Per-user prefix isolation in S3
- Encryption at rest: AES-256 (SSE-S3 in P1, SSE-KMS in P2)
- Encryption in transit: TLS 1.3 minimum
- Secrets in AWS Secrets Manager
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
- **Reversibility**: No destructive operation on user data is permanent

### Bias Mitigation

- Statistical-first imputation (median, mode) rather than LLM-generated
- Insight narrative required to cite specific chart values
- Golden datasets include fairness-relevant attributes for evaluation

### Hallucination Handling

- Numerical claims in narratives programmatically validated against source data
- SQL outputs parsed before execution; non-SELECT operations blocked
- Agents see only schema metadata and ≤5 anonymized sample rows, not full datasets

---

## Domain Prompt Packs

Each pack includes: domain vocabulary, common KPI definitions, sample-question library, validation rules, chart-type preferences.

### Finance Pack
- **KPIs**: revenue, COGS, gross margin, churn, MRR/ARR, runway, AR aging, cohort retention
- **Validation**: dates as fiscal periods, currency normalization

### Healthcare Pack
- **KPIs**: patient counts, episode of care, readmission rate, length of stay
- **Recognition**: ICD-10/CPT codes
- **Validation**: PHI detection cues

### Retail/eCommerce Pack
- **KPIs**: AOV, repeat purchase, SKU margin, inventory turn, return rate, channel attribution
- **Validation**: SKU duplicates, negative quantities

### Marketing Pack
- **KPIs**: CTR, CPA, CAC, LTV, attribution windows, channel mix
- **Validation**: UTM hygiene, date-window alignment

### Operations/Other Pack
- **KPIs**: generic counts, throughput, cycle time, sums-and-rates
- **Validation**: No domain-specific validators

---

## UI/UX Requirements

### Design Principles

1. **Progressive disclosure**: Show only what's needed at current step
2. **Confidence transparency**: Every agent action shows confidence indicator
3. **HITL as first-class affordance**: Full pages, not afterthought modals
4. **Domain-aware copy**: Use vocabulary from active domain pack
5. **Fail loudly, fail clearly**: Specific, actionable error states
6. **Don't punish exploration**: Nothing destroys data

### Visual Distinction

- **User UI**: Cool blue accent
- **Admin UI**: Warm orange-tinted accent
- **HITL screens**: Yellow/orange affordance band

### Key User UI Screens

- U1: Sign-up / Sign-in
- U2: Domain Selection (first-run)
- U3: Upload Screen (single or multi-file)
- U4: Schema & Merge Validation (HITL #1)
- U5: HITL Cleaning Plan Review (HITL #2)
- U6: Intent Capture (HITL #3)
- U7: Dashboard View
- U8: Audit Log View

### Key Admin UI Screens

- A1: Admin Home (System Health)
- A2: User & Role Management
- A3: LLM Provider Configuration
- A4: Domain Prompt Pack Viewer (P1) / Editor (P2)
- A5: Audit Log Viewer
- A6: Billing & Plans (P2)

### Accessibility

- WCAG 2.1 AA compliance target
- Keyboard navigation fully supported
- Color contrast ≥ 4.5:1
- Charts include accessible alt-text and data-table fallback

---

## Testing Strategy

### Test Layers

| Layer | Scope | Coverage Target |
|-------|-------|-----------------|
| Unit | Agent functions, transform logic, API handlers | ≥ 70% (P1), ≥ 85% (P2) |
| Integration | Agent-to-agent, S3, DuckDB, pgvector | Happy paths + key errors |
| E2E (single-file) | Upload → HITL #1 → HITL #2 → dashboard per format | All formats |
| E2E (multi-file) | 2-file and 5-file uploads with union/join | Union + Join paths |
| HITL Flow | All decision branches per gate | Complete |
| RBAC | Admin endpoint protection | Full matrix |
| LLM Portability | Each agent on each provider | All configured providers |
| Agent Evaluation | Cleaning acceptance on golden datasets | ≥ 75% (P1), ≥ 85% (P2) |
| Domain Regression | Per-domain prompt-pack output validation | 4 domains × 5 fixtures |

### Golden Dataset

- 10 datasets in Phase 1, 20+ in Phase 2
- Known data-quality issues, expected outcomes, labeled correct cleaning decisions
- Run nightly against all configured LLM providers
- Includes: Stripe export, Salesforce export, survey CSV, finance Excel, IoT JSON, Shopify exports (union/join), multi-sheet Excel, Parquet, edge cases

---

## Timeline

### Phase 1 (6 May – 10 June 2026)

| Week | Focus | Exit Criteria |
|------|-------|---------------|
| Week 1 | Foundation: AWS infra, CI/CD, Postgres schema, FastAPI, Next.js shell, auth, LLM abstraction | User can sign up, log in, hit /health. CI/CD deploys to staging. |
| Week 2 | Domain selection, multi-file upload, format detection, HITL #1 | Domain persists. Multi-file upload works. HITL #1 renders. |
| Week 3 | Parquet conversion, type-routing, cleaning plan agent, HITL #2, cleaning executor | Cleaning plan generated. ≥60% acceptance on golden datasets 1-5. |
| Week 4 | Intent agent, analysis agent, dashboard agent, insights agent | End-to-end happy path for CSV and Parquet merge. |
| Week 5 | Admin UI, integration testing, golden dataset validation, hardening | Internal beta with 5 users for one week. |

### Phase 2 (11 June – 10 July 2026)

| Week | Focus |
|------|-------|
| Week 6 | Advanced cleaning agents, PII detection, XML/PDF ingestion |
| Week 7 | LLM provider expansion, domain pack editor, new domain packs |
| Week 8 | Iterative Q&A, expanded charts, public REST API, project organization |
| Week 9 | Stripe monetization, OpenTelemetry tracing, auto-scaling, Multi-AZ RDS |
| Week 10 | Closed beta launch (20-30 users), bug fixes, documentation |

### Scope Cut Priority (Phase 1)

If timeline slips, cut in this order:
1. Drop Parquet input
2. Drop two domains (keep Finance + Retail)
3. Drop second LLM provider
4. Drop JSON ingestion
5. Drop XLSX

**Non-negotiable**: HITL, dual UI separation, type-aware storage

---

## Business Model

### Pricing Tiers (Phase 2)

| Tier | Price | Pipelines/Month | Storage | Features |
|------|-------|-----------------|---------|----------|
| Free | $0 | 10 | 1 GB | Single user, basic cleaning |
| Pro | ~$29/mo | 50 | 10 GB | Advanced cleaning, priority support |
| Team | ~$99/mo | 250 | 50 GB | Multi-user, admin console |
| Enterprise | Custom | Unlimited | Custom | SSO, SLA, dedicated support |

### Cost Targets

| Cost Driver | Phase 1 | Phase 2 | Year 1 Target |
|-------------|---------|---------|---------------|
| LLM cost per pipeline | ≤ $0.30 | ≤ $0.15 | ≤ $0.08 |
| Infra cost per pipeline | ≤ $0.05 | ≤ $0.02 | ≤ $0.01 |
| Target gross margin | — | ~90% | ≥ 75% |

---

## Key Constraints

### File Limits (Phase 1)

- 50 MB per file
- 250 MB total per upload
- 10 files maximum per upload
- Same format required within single upload
- 5 GB storage per user
- 20 datasets per user

### Supported Formats

- **Phase 1**: CSV, XLSX, JSON, Parquet
- **Phase 2**: +XML, PDF (text extraction)

### Permanently Out of Scope

- Real-time/streaming data (Kafka, Kinesis)
- Native mobile applications
- On-premise deployment
- Training custom ML models on user data
- Direct write-back to source systems

---

## Monitoring and Observability

### Key Metrics

- `pipeline_duration_seconds` (by stage, excluding HITL wait)
- `hitl_decision_latency_seconds` (by checkpoint)
- `hitl_approval_rate` (by checkpoint, by domain)
- `agent_confidence` (by agent type, by domain)
- `cleaning_rows_changed_total` (by action type, by HITL outcome)
- `llm_tokens_used` (by agent, provider, model)
- `llm_cost_usd` (by agent, provider, model)
- `llm_provider_error_rate` (by provider)
- `type_routing_distribution` (numeric/textual/ambiguous)

### Alerting Conditions

| Condition | Severity |
|-----------|----------|
| Job failure rate > 5% over 15 min | Page |
| API p95 latency > 2s for 5 min | Page |
| S3 write failure | Page |
| LLM error rate > 10% over 15 min | Page |
| HITL pause queue depth > 100 | Page |
| Daily LLM spend > 130% of 7-day average | Email |
| Confidence score average < 0.6 over 24h | Email |

---

## Open Questions (Target: 12 May 2026)

| # | Question | Owner |
|---|----------|-------|
| OQ-01 | Final scope-cut sequence order | Product |
| OQ-02 | Which four domains ship full prompt packs in P1 | Product + Domain SMEs |
| OQ-03 | Second LLM provider confirmation (OpenAI vs Bedrock) | Engineering + Procurement |
| OQ-04 | Default per-agent model routing | Engineering |
| OQ-05 | Embedding model selection strategy | Engineering + AI |
| OQ-06 | Audit log WORM requirement timing | Legal + Product |

---

## Definition of Done (Phase 1)

- [ ] End-to-end pipeline works for CSV, XLSX, JSON, Parquet
- [ ] Cleaning Plan acceptance ≥ 70% on 10-dataset golden set
- [ ] HITL #1 + HITL #2 cycle time < 90s median
- [ ] Audit log present for every agent and HITL decision
- [ ] Four-layer storage architecture operational
- [ ] LLM Provider Abstraction live with 2 providers
- [ ] Dual UI shipped with server-side RBAC enforcement
- [ ] CI/CD pipeline shipping to staging and prod
- [ ] Internal beta with 5 users for one week
- [ ] All Phase 1 NFR targets met

---

## Definition of Done (Phase 2)

- [ ] All Phase 2 features shipped
- [ ] Cleaning Plan acceptance ≥ 85% on 20+ dataset golden set
- [ ] HITL cycle time < 60s median
- [ ] Public API live and documented
- [ ] Closed beta with 20-30 external users
- [ ] Stripe billing end-to-end operational
- [ ] Auto-scaling handles 1,000 concurrent pipelines
- [ ] ≥ 4 LLM providers operational with failover
- [ ] NPS ≥ 40 from beta survey
