# DataMind AI — Architecture Diagram

> *Present this as a visual slide deck. Each section corresponds to one slide.*

---

## Slide 1: High-Level System Architecture

```mermaid
graph TB
 subgraph "User Layer"
  U[Business User<br/>Analyst / Founder / PM]
  A[Tenant Admin<br/>Platform Operator]
 end

 subgraph "UI Layer - Next.js 14 + Tailwind + shadcn/ui"
  UUI["User UI (/app/*)<br/>Cool Blue Accent"]
  AUI["Admin UI (/admin/*)<br/>Warm Orange Accent"]
  RBAC[RBAC Middleware<br/>Server-Side Enforcement]
 end

 subgraph "API Gateway - FastAPI (Python 3.11+)"
  GW[API Gateway<br/>JWT Auth + Rate Limiting]
 end

 subgraph "Agent Orchestration - LangGraph"
  SUP[Supervisor Agent<br/>Orchestrates, Routes, Retries]
  DOM[Domain Agent]
  ING[Ingestion Agent]
  CLP[Cleaning Plan Agent]
  CLE[Cleaning Executor]
  INT[Intent Agent]
  ANL[Analysis Agent]
  DSH[Dashboard Agent]
  INS[Insights Agent]
 end

 subgraph "LLM Provider Abstraction - LiteLLM"
  MIST[Google Gemini 3.5 Flash<br/>mistral-small<br/>mistral-7b-instruct]
  OPN[OpenAI<br/>GPT-4o / GPT-4o-mini]
  GEM[Google Gemini Flash<br/>Phase 2]
  OLL[Ollama Self-Hosted<br/>Phase 2]
 end

 subgraph "Job Queue"
  CEL[FastAPI BackgroundTasks<br/>Async Agent Workers]
 end

 subgraph "Four-Layer Storage Architecture"
  L1["Layer 1: Raw Storage<br/>Supabase Storage Bucket<br/>Original files, versioned"]
  L2["Layer 2: Curated Storage<br/>Supabase Storage Bucket<br/>Cleaned JSON"]
  L3["Layer 3: Numeric/Structured<br/>Supabase Database (PostgreSQL)<br/>+ PostgreSQL (Analytical Queries)"]
  L4["Layer 4: Textual/Semantic<br/>Supabase Vector (pgvector) Vector Store<br/>HNSW Index, Cosine Similarity"]
 end

 subgraph "Infrastructure & Observability"
  PROM[Prometheus + Grafana<br/>Metrics & Alerts]
  TEMPO[Grafana Tempo<br/>Distributed Tracing - Phase 2]
  GHCR[GitHub Container Registry<br/>Docker Images]
  TF[Terraform<br/>Infrastructure as Code]
 end

 subgraph "Security & Secrets"
  VAULT[Supabase Vault<br/>Secrets Management]
  JWT[JWT Auth HS256<br/>1h Expiry + Refresh]
 end

 subgraph "Monetization - Phase 2"
  STRIPE[Stripe<br/>Checkout + Customer Portal<br/>Webhooks + Metering]
 end

 U --> UUI
 A --> AUI
 UUI --> RBAC
 AUI --> RBAC
 RBAC --> GW
 GW --> SUP
 SUP --> DOM
 SUP --> ING
 SUP --> CLP
 SUP --> CLE
 SUP --> INT
 SUP --> ANL
 SUP --> DSH
 SUP --> INS
 DOM --> MIST
 DOM --> OPN
 CLP --> MIST
 CLP --> OPN
 INS --> GEM
 INS --> OLL
 SUP --> CEL
 ING --> L1
 CLE --> L2
 CLE --> L3
 CLE --> L4
 ANL --> L3
 ANL --> L4
 DSH --> L3
 GW --- PROM
 CEL --- PROM
 GW --- VAULT
 AUI --- STRIPE
```

---

## Slide 2: End-to-End Data Pipeline Flow

```mermaid
flowchart LR
 %% Styling
 classDef domain fill:#e1f5fe,stroke:#0288d1,color:#01579b
 classDef ingest fill:#fff3e0,stroke:#f57c00,color:#bf360c
 classDef cleaning fill:#e8f5e9,stroke:#388e3c,color:#1b5e20
 classDef intent fill:#f3e5f5,stroke:#7b1fa2,color:#4a148c
 classDef dashboard fill:#fff8e1,stroke:#f9a825,color:#f57f17
 classDef storage fill:#eceff1,stroke:#546e7a,color:#263238
 classDef hitl fill:#ffcc02,stroke:#f57f17,color:#e65100

 %% Phase 1: Domain
 D[Domain Selection<br/>Finance / Healthcare / Retail /<br/>Marketing / Operations / Other]:::domain
 DP[Domain Prompt Pack Loaded<br/>Vocabulary, KPIs, Validation Rules]:::domain

 %% Phase 2: Upload
 UP[Upload Files<br/>CSV / XLSX / JSON / Parquet<br/>Up to 10 files, 50MB each]:::ingest
 L1[(Layer 1: Raw Storage<br/>Supabase Storage)]:::storage

 %% Phase 3: Detect & Profile
 DET[Format Detection +<br/>Column Profiling +<br/>Type Classification]:::ingest
 TCLASS{Type Classification<br/>Numeric/Structured vs<br/>Textual/Semantic}

 %% Phase 4: HITL #1
 H1{HITL #1<br/>Schema & Merge Validation}:::hitl
 MERGE[Approve/Modify Merge Plan<br/>UNION / JOIN / Keep Separate<br/>Edit Type Routing]:::ingest

 %% Phase 5: Conversion
 CONV[Convert to Parquet<br/>Apply Approved Merge]:::cleaning

 %% Phase 6: Cleaning Plan
 CP[Cleaning Plan Agent<br/>Generates Numbered Steps<br/>Dedup / Impute / Type Coercion]:::cleaning

 %% Phase 7: HITL #2
 H2{HITL #2<br/>Cleaning Plan Review}:::hitl
 APPROVE[User Approves / Modifies / Rejects<br/>Each Step Individually]:::cleaning

 %% Phase 8: Execute
 EXEC[Cleaning Executor<br/>Runs Only Approved Steps<br/>Logs Every Action]:::cleaning
 L2[(Layer 2: Curated Storage<br/>JSON)]:::storage
 L3[(Layer 3: Supabase DB<br/>+ PostgreSQL)]:::storage
 L4[(Layer 4: Supabase Vector (pgvector)<br/>Vector Store)]:::storage

 %% Phase 9: Intent
 IC[User States Question<br/>Free-text + Suggestion Chips]:::intent
 H3{HITL #3<br/>Intent Confirmation}:::hitl
 IR[Intent Agent Restates<br/>Interpretation]:::intent

 %% Phase 10: Analyze
 ALZ[Analysis Agent<br/>SQL on Numeric /<br/>Semantic Search on Text]:::intent

 %% Phase 11: Dashboard
 DG[Dashboard Agent<br/>KPI Cards + 2 Charts<br/>Vega-Lite Specs]:::dashboard
 IG[Insights Agent<br/>Domain-Flavored Narrative<br/>+ Recommended Action]:::dashboard
 AUDIT[(Audit Log<br/>Every Decision Logged)]:::storage

 %% Flow Connections
 D --> DP
 DP --> UP
 UP --> L1
 L1 --> DET
 DET --> TCLASS
 TCLASS --> H1
 H1 --> MERGE
 MERGE --> CONV
 CONV --> CP
 CP --> H2
 H2 --> APPROVE
 APPROVE --> EXEC
 EXEC --> L2
 EXEC --> L3
 EXEC --> L4
 L2 --> IC
 L3 --> IC
 L4 --> IC
 IC --> H3
 H3 --> IR
 IR --> ALZ
 ALZ --> DG
 ALZ --> IG
 DG --> AUDIT
 IG --> AUDIT
```

---

## Slide 3: Four-Layer Storage Architecture

```mermaid
graph TD
 %% Style
 classDef raw fill:#ffebee,stroke:#c62828,color:#b71c1c
 classDef curated fill:#fff3e0,stroke:#ef6c00,color:#bf360c
 classDef numeric fill:#e8f5e9,stroke:#2e7d32,color:#1b5e20
 classDef textual fill:#e1f5fe,stroke:#1565c0,color:#0d47a1
 classDef arrow fill:none,stroke:#666,stroke-width:2

 subgraph "Storage Layers"
  L1["Layer 1: Raw Storage<br/>─────────────<br/>Supabase Storage Bucket<br/>Versioned, Per-User Prefix<br/>Original files preserved unmodified<br/>Formats: CSV, XLSX, JSON, Parquet"]:::raw
  L2["Layer 2: Curated Storage<br/>─────────────<br/>Supabase Storage Bucket<br/>Cleaned data in JSON format<br/>Column statistics + schema embedded"]:::curated
  L3["Layer 3: Numeric / Structured<br/>─────────────<br/>Supabase Database (PostgreSQL)<br/>+ PostgreSQL for fast in-process analytics<br/>Stores: int, float, bool, date,<br/>low-cardinality categorical (≤50 distinct)"]:::numeric
  L4["Layer 4: Textual / Semantic<br/>─────────────<br/>Supabase Vector (pgvector) Vector Store<br/>HNSW index, Cosine Similarity<br/>Stores: strings avg length > 40 chars<br/>or distinct count > 50% of rows"]:::textual
 end

 L1 -->|"Format Detection + Profiling"| L2
 L2 -->|"Type-Aware Routing"| L3
 L2 -->|"Type-Aware Routing"| L4

 subgraph "Classification Rules"
  R1["Numeric/Structured:<br/>int/float/bool/date dtype<br/>OR ≤50 distinct values"]
  R2["Textual/Semantic:<br/>Avg string length > 40 chars<br/>OR distinct > 50% of rows"]
  R3["Ambiguous:<br/>Does not fit above rules<br/>→ Surfaced to user in HITL #1"]
 end
```

---

## Slide 4: Agent System & Confidence Scoring

```mermaid
graph LR
 %% Style
 classDef supervisor fill:#ffcc02,stroke:#f57f17,color:#e65100,stroke-width:3
 classDef agent fill:#e3f2fd,stroke:#1565c0,color:#0d47a1
 classDef p2 fill:#f5f5f5,stroke:#9e9e9e,color:#616161,stroke-dasharray: 5 5

 SUP["Supervisor Agent<br/>═══════════════<br/>Orchestrates pipeline<br/>Routes between agents<br/>Handles retries & aggregation<br/>Enforces HITL gates"]:::supervisor

 subgraph "Phase 1 Agents (Supervised)"
  direction TB
  DA[Domain Agent<br/>Loads domain prompt pack]:::agent
  IA[Ingestion Agent<br/>Format detection, profiling,<br/>column classification]:::agent
  CPA[Cleaning Plan Agent<br/>Drafts cleaning plan,<br/>does NOT execute]:::agent
  CEA[Cleaning Executor<br/>Executes approved steps<br/>Logs every action]:::agent
  ITA[Intent Agent<br/>Parses NL goal into<br/>structured analysis spec]:::agent
  ANA[Analysis Agent<br/>SQL on numeric (PostgreSQL/Postgres)<br/>Semantic search on text (Supabase Vector (pgvector))]:::agent
  DSA[Dashboard Agent<br/>Converts analysis results<br/>into Vega-Lite specs]:::agent
  INA[Insights Agent<br/>Generates domain-flavored<br/>narrative + next action]:::agent
 end

 subgraph "Phase 2 Agents"
  OA[Outlier Agent<br/>Statistical outlier detection<br/>IQR + Isolation Forest]:::p2
  FDA[Fuzzy Dedup Agent<br/>Near-duplicate detection<br/>using fuzzy string match]:::p2
  SIA[Smart Imputation Agent<br/>KNN imputation<br/>LLM-assisted for high-cardinality]:::p2
  PII[PII Detection Agent<br/>Detects emails, phones, IDs<br/>Gates LLM context]:::p2
 end

 SUP --> DA
 SUP --> IA
 SUP --> CPA
 SUP --> CEA
 SUP --> ITA
 SUP --> ANA
 SUP --> DSA
 SUP --> INA
 SUP --> OA
 SUP --> FDA
 SUP --> SIA
 SUP --> PII

 subgraph "Confidence Score Framework"
  C1["0.90-1.00: High<br/>Pre-checked for approval"]
  C2["0.70-0.89: Medium<br/>Pre-checked, flagged yellow"]
  C3["0.50-0.69: Low<br/>Unchecked, flagged orange"]
  C4["0.00-0.49: Very Low<br/>Unchecked, flagged red"]
 end
```

---

## Slide 5: HITL (Human-in-the-Loop) Checkpoints

```mermaid
flowchart TB
 %% Style
 classDef hitl fill:#ffcc02,stroke:#f57f17,color:#e65100,stroke-width:3
 classDef user fill:#e1f5fe,stroke:#0288d1,color:#01579b
 classDef system fill:#e8f5e9,stroke:#388e3c,color:#1b5e20
 classDef decision fill:#fff3e0,stroke:#f57c00,color:#bf360c

 START([Upload Complete]):::system

 H1{HITL #1<br/>Schema & Merge Validation}:::hitl
 H1_CONTENT[User Sees:<br/>• Inferred schema per file<br/>• Proposed type-routing badges<br/>• Proposed merge plan (UNION/JOIN)<br/>• Sample rows preview<br/><br/>User Can:<br/>• Approve all<br/>• Change merge key<br/>• Change type-routing<br/>• Exclude columns/files]:::user

 H1_DECISION{User Decision}:::decision
 H1_APP[Approve]:::system
 H1_MOD[Modify & Approve]:::system

 H2{HITL #2<br/>Cleaning Plan Approval}:::hitl
 H2_CONTENT[User Sees:<br/>• Numbered cleaning actions<br/>• Rationale per step<br/>• Confidence badge per step<br/>• Before/after sample tables<br/><br/>User Can:<br/>• Approve all / Reject all<br/>• Approve/modify/reject per step<br/>• Switch imputation strategies]:::user

 H2_DECISION{User Decision}:::decision
 H2_APP[Approve All]:::system
 H2_MOD[Modify Some]:::system
 H2_REJ[Reject Some]:::system

 H3{HITL #3<br/>Intent Confirmation}:::hitl
 H3_CONTENT[User Sees:<br/>• Free-text input with domain-tuned placeholder<br/>• 3 suggestion chips<br/>• Agent restates interpretation<br/><br/>User Can:<br/>• Confirm intent<br/>• Refine / rephrase]:::user

 H3_DECISION{User Decision}:::decision
 H3_APP[Confirm]:::system
 H3_REF[Refine]:::system

 H4{HITL #4 - Phase 2<br/>Dashboard Accept/Refine}:::hitl
 H4_CONTENT[User Sees:<br/>• Generated dashboard<br/>• KPI cards + charts + narrative<br/><br/>User Can:<br/>• Accept dashboard<br/>• Request changes<br/>• Ask follow-up question]:::user

 H4_DECISION{User Decision}:::decision
 H4_APP[Accept]:::system
 H4_REQ[Request Changes]:::system
 H4_FUP[Follow-up Q&A]:::system

 DONE([Dashboard Ready]):::system

 %% Connections
 START --> H1
 H1 --> H1_CONTENT
 H1_CONTENT --> H1_DECISION
 H1_DECISION --> H1_APP
 H1_DECISION --> H1_MOD
 H1_APP --> H2
 H1_MOD --> H2
 H2 --> H2_CONTENT
 H2_CONTENT --> H2_DECISION
 H2_DECISION --> H2_APP
 H2_DECISION --> H2_MOD
 H2_DECISION --> H2_REJ
 H2_APP --> H3
 H2_MOD --> H3
 H2_REJ --> H3
 H3 --> H3_CONTENT
 H3_CONTENT --> H3_DECISION
 H3_DECISION --> H3_APP
 H3_DECISION --> H3_REF
 H3_REF --> H3_CONTENT
 H3_APP --> H4
 H4 --> H4_CONTENT
 H4_CONTENT --> H4_DECISION
 H4_DECISION --> H4_APP
 H4_DECISION --> H4_REQ
 H4_DECISION --> H4_FUP
 H4_REQ --> H4_CONTENT
 H4_FUP --> H4_CONTENT
 H4_APP --> DONE
```

---

## Slide 6: Technology Stack & Deployment

```mermaid
graph TB
 %% Style
 classDef frontend fill:#e1f5fe,stroke:#0288d1,color:#01579b
 classDef backend fill:#fff3e0,stroke:#f57c00,color:#bf360c
 classDef storage fill:#e8f5e9,stroke:#388e3c,color:#1b5e20
 classDef infra fill:#f3e5f5,stroke:#7b1fa2,color:#4a148c
 classDef ci fill:#ffebee,stroke:#c62828,color:#b71c1c

 subgraph "Frontend"
  NEXT[Next.js 14 + TypeScript]:::frontend
  TW[Tailwind CSS + shadcn/ui]:::frontend
  RC[Recharts / Vega-Lite]:::frontend
  UI[User UI /app/*]:::frontend
  ADM[Admin UI /admin/*]:::frontend
 end

 subgraph "Backend"
  API[FastAPI Python 3.11+<br/>Pydantic v2 Schemas]:::backend
  JWT[JWT Auth HS256<br/>RBAC Middleware]:::backend
  CELERY[FastAPI BackgroundTasks Workers<br/>Async Agent Tasks]:::backend
  REDIS[Redis<br/>Message Broker + Cache]:::backend
 end

 subgraph "Storage & Data"
  SUPABASE[Supabase<br/>PostgreSQL + Storage]:::storage
  DUCKDB[PostgreSQL<br/>Analytical Query Engine]:::storage
  WEAV[Supabase Vector (pgvector)<br/>Vector Embeddings]:::storage
  PARQUET[JSON<br/>Columnar Format]:::storage
 end

 subgraph "AI / LLM"
  LG[LangGraph<br/>Agent Orchestration]:::backend
  LITELLM[LiteLLM<br/>Provider Abstraction]:::backend
  MISTRAL[Google Gemini 3.5 Flash AI]:::backend
  OPENAI[OpenAI]:::backend
  GEMINI[Google Gemini Flash<br/>Phase 2]:::backend
  OLLAMA[Ollama Self-Hosted<br/>Phase 2]:::backend
 end

 subgraph "Infrastructure"
  DOCKER[Docker Containers<br/>python:3.11-slim / node:20-alpine]:::infra
  ECS[AWS ECS<br/>Blue/Green Deploy]:::infra
  GHCR[GitHub Container Registry]:::infra
  TF[Terraform<br/>Infrastructure as Code]:::infra
 end

 subgraph "CI/CD"
  GHA[GitHub Actions]:::ci
  LINT[Ruff + ESLint]:::ci
  TYPE[mypy + tsc]:::ci
  TEST[Pytest + Vitest<br/>Golden Dataset Evaluation]:::ci
  DEPLOY[Deploy to Staging → Prod<br/>Auto-rollback on >1% errors]:::ci
 end

 subgraph "Observability"
  PROM[Prometheus Metrics]:::infra
  GRAF[Grafana Dashboards]:::infra
  STRUC[Structlog<br/>Structured JSON Logging]:::infra
  OTEL[OpenTelemetry<br/>Phase 2]:::infra
 end

 subgraph "Security"
  VAULT[Supabase Vault<br/>Secrets]:::infra
  ARGON[Argon2<br/>Password Hashing]:::infra
  TLS[TLS 1.3<br/>Encryption in Transit]:::infra
  AES[AES-256<br/>Encryption at Rest]:::infra
 end

 subgraph "Monetization - Phase 2"
  STRIPE[Stripe<br/>Checkout + Portal<br/>Webhooks + Metering]:::infra
  PLAN[Free | Pro $49 | Team $199<br/>Enterprise Custom]:::infra
 end

 %% Connections
 NEXT --> TW
 NEXT --> RC
 NEXT --> UI
 NEXT --> ADM
 UI --> API
 ADM --> API
 API --> JWT
 API --> CELERY
 CELERY --> REDIS
 API --> SUPABASE
 API --> DUCKDB
 API --> WEAV
 SUPABASE --> PARQUET
 LG --> LITELLM
 LITELLM --> MISTRAL
 LITELLM --> OPENAI
 LITELLM --> GEMINI
 LITELLM --> OLLAMA
 DOCKER --> ECS
 GHCR --> ECS
 TF --> ECS
 GHA --> LINT
 GHA --> TYPE
 GHA --> TEST
 GHA --> DEPLOY
 API --> PROM
 CELERY --> PROM
 PROM --> GRAF
 API --> STRUC
 API --> OTEL
 API --> VAULT
 API --> ARGON
 API --> TLS
 API --> AES
 ADM --> STRIPE
 STRIPE --> PLAN
```

---

## Slide 7: Performance Targets & Key Metrics

```mermaid
quadrantChart
 title Pipeline Success Metrics
 x-axis "Low Performance" --> "High Performance"
 y-axis "Phase 1 Target" --> "Phase 2 Target"
 quadrant-1 "Exceeded Targets"
 quadrant-2 "Phase 2 Goals"
 quadrant-3 "Needs Improvement"
 quadrant-4 "Phase 1 Goals"
 "Time to First Insight: <7min": [0.35, 0.45]
 "Time to First Insight: <5min": [0.65, 0.85]
 "Cleaning Acceptance: 70%": [0.30, 0.40]
 "Cleaning Acceptance: 85%": [0.70, 0.80]
 "Pipeline Success: 70%": [0.40, 0.35]
 "Pipeline Success: 85%": [0.75, 0.75]
 "HITL Cycle: <90s": [0.50, 0.30]
 "HITL Cycle: <60s": [0.80, 0.70]
 "Dashboard Latency: <90s": [0.45, 0.25]
 "Dashboard Latency: <60s": [0.75, 0.65]
 "Cost per Pipeline: $0.30": [0.25, 0.20]
 "Cost per Pipeline: $0.15": [0.55, 0.55]
```

---

## Slide 8: Deployment Pipeline & Environments

```mermaid
graph LR
 %% Style
 classDef dev fill:#e8f5e9,stroke:#388e3c,color:#1b5e20
 classDef staging fill:#fff3e0,stroke:#f57c00,color:#bf360c
 classDef prod fill:#ffebee,stroke:#c62828,color:#b71c1c
 classDef ci fill:#e1f5fe,stroke:#0288d1,color:#01579b

 DEV[Dev Environment<br/>Local Docker Compose<br/>+ LocalStack<br/>Synthetic Data]:::dev
 STAG[Staging Environment<br/>Single ECS Service<br/>25% Prod Capacity<br/>Anonymized Prod Data]:::staging
 PROD[Production Environment<br/>Auto-scaling ECS<br/>Multi-AZ RDS (P2)<br/>Live Traffic]:::prod

 subgraph "CI/CD Pipeline - GitHub Actions"
  PR[PR Opened<br/>Lint → TypeCheck<br/>→ Unit Tests → Docker Build<br/>< 5 min]:::ci
  MERGE[Merge to Main<br/>Tests → Deploy to Staging<br/>→ E2E Happy Path<br/>< 10 min]:::ci
  PROMOTE[Manual Promote to Prod<br/>Blue/Green Deploy<br/>10-min Health Check<br/>Auto-rollback >1% errors<br/>< 15 min]:::ci
  NIGHTLY[Nightly<br/>Full Agent Evaluation<br/>→ Internal Dashboard<br/>Background]:::ci
 end

 PR --> MERGE
 MERGE --> STAG
 STAG --> PROMOTE
 PROMOTE --> PROD
 NIGHTLY --> STAG
 DEV --> PR
```

---

## Slide 9: Timeline — Phase 1 (6 May – 10 June 2026)

```mermaid
gantt
 title Phase 1: MVP Timeline (30 Working Days)
 dateFormat YYYY-MM-DD
 axisFormat %b %d

 section Week 1 - Foundation
 Supabase + Terraform + CI/CD   :w1a, 2026-05-06, 2d
 Postgres Schema + JWT Auth   :w1b, 2026-05-08, 2d
 FastAPI + Next.js Shell + RBAC  :w1c, 2026-05-12, 1d
 LLM Provider Abstraction    :w1d, 2026-05-12, 1d

 section Week 2 - Domain & Upload
 Domain Selection + Domain Agent  :w2a, 2026-05-13, 3d
 Multi-file Upload + Format Detection :w2b, 2026-05-13, 3d
 Schema Classification + HITL #1  :w2c, 2026-05-16, 2d

 section Week 3 - Cleaning & Routing
 Parquet Conversion + Type Routing  :w3a, 2026-05-20, 2d
 Cleaning Plan Agent + HITL #2   :w3b, 2026-05-22, 3d
 Cleaning Executor + Audit Log   :w3c, 2026-05-22, 3d

 section Week 4 - Intelligence
 Intent Agent + HITL #3    :w4a, 2026-05-27, 2d
 Analysis Agent + Dashboard Agent  :w4b, 2026-05-29, 3d
 Insights Agent + Admin UI    :w4c, 2026-06-01, 2d

 section Week 5 - Hardening
 Testing + Golden Dataset Eval   :w5a, 2026-06-03, 3d
 Security Review + Bug Fixes   :w5b, 2026-06-05, 3d
 Internal Beta + Demo Prep    :w5c, 2026-06-08, 2d
 BUFFER        :buf, 2026-06-09, 2d
```

---

## Slide 10: Competitive Positioning

```mermaid
quadrantChart
 title Competitive Landscape
 x-axis "Low Automation" --> "High Automation"
 y-axis "Basic Cleaning" --> "Advanced Intelligence"
 quadrant-1 "DataMind Target Zone"
 quadrant-2 "Enterprise BI"
 quadrant-3 "Basic Tools"
 quadrant-4 "Conversational AI"
 "DataMind AI": [0.75, 0.75]
 "Tableau / Power BI": [0.25, 0.80]
 "Julius AI / ChatGPT Code": [0.70, 0.40]
 "Alteryx / Trifacta": [0.40, 0.60]
 "Hex / Mode": [0.30, 0.50]
 "Akkio / Pecan AI": [0.60, 0.55]
 "Databricks AI/BI": [0.35, 0.85]
 "Copilot / Tableau Pulse": [0.30, 0.75]
```

> **Note:** Mermaid diagrams render in GitHub, GitLab, Notion, Obsidian, and most modern markdown viewers. For PowerPoint/Google Slides, export these as SVG or PNG using a Mermaid live editor (https://mermaid.live).
