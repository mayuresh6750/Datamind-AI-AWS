# DataMind AI

**An Autonomous Agentic Platform for End-to-End Business Data Intelligence**

From raw data → cleaned data → context-aware dashboards → actionable business decisions.

DataMind AI is an enterprise-grade agentic data intelligence platform that guides business users from raw, heterogeneous data files to production-ready dashboards and decision narratives without writing a single line of SQL or Python.

---

## Pure AWS Cloud Architecture

DataMind AI is built natively on a **100% AWS Cloud Architecture**, replacing legacy third-party Backend-as-a-Service (BaaS) dependencies with managed AWS infrastructure under IAM governance, KMS encryption, and automated CI/CD.

```
                  ┌────────────────────────────────────────┐
                  │          Next.js Frontend UI           │
                  └──────────────────┬─────────────────────┘
                                     │ (REST / Native JWT)
                                     ▼
                  ┌────────────────────────────────────────┐
                  │       DataMind AI FastAPI Backend      │
                  └───────┬──────────┬──────────┬──────────┘
                          │          │          │
         ┌────────────────┘          │          └────────────────┐
         ▼                           ▼                           ▼
┌──────────────────┐       ┌──────────────────┐       ┌──────────────────┐
│    Amazon S3     │       │    Amazon RDS    │       │   AWS Secrets    │
│ (Raw & Curated   │       │  PostgreSQL 18.3 │       │     Manager      │
│  Object Storage) │       │   + pgvector     │       │ (Dynamic Master  │
│  Presigned URLs  │       │   Native Auth    │       │   Credentials)   │
└──────────────────┘       └──────────────────┘       └──────────────────┘
                                     ▲
                                     │ (Embeddings / Inference)
                           ┌──────────────────┐
                           │  Amazon Bedrock  │
                           │ Claude 3.5 &     │
                           │ Titan Embed v2   │
                           └──────────────────┘
```

---

## Core Principles

1. **Domain-First Intelligence** — Captures user domain (*Finance, Healthcare, Retail, Marketing, Operations*) so all autonomous agents apply domain-specific KPIs, vocabulary, and statistical rules.
2. **User-Controlled Data Modeling** — Ingests heterogeneous files (CSV, XLSX, JSON, Parquet) with intelligent schema reconciliation and user-governed merge strategies.
3. **Human-in-the-Loop (HITL) Governance** — AI agents propose numbered, deterministic data cleaning transformations; humans approve, modify, or reject each step before execution.
4. **Type-Aware Storage Routing** — Relational and structured business records route to PostgreSQL; semantic textual concept embeddings route to `pgvector`.
5. **Zero-Trust Credential Security** — Master database passwords and secrets are never committed or hardcoded; dynamic resolution via AWS Secrets Manager with client-side TTL caching.

---

## Technology Stack

| Layer | Service / Technology | Architecture Role |
|-------|----------------------|-------------------|
| **Frontend** | Next.js 14, TypeScript, Tailwind CSS, shadcn/ui | Reactive multi-agent dashboard & HITL checkpoint UI |
| **Authentication** | Native HS256 JWT + PBKDF2-HMAC-SHA256 | Self-hosted stateless authentication in Amazon RDS `users` table |
| **Backend** | Python 3.11+, FastAPI, SQLAlchemy (Async), Alembic | High-throughput async REST API & background task execution |
| **Object Storage (L1 & L2)** | **Amazon S3** (`boto3`, non-blocking I/O) | Raw uploaded files & curated JSON artifacts with Pre-Signed URLs |
| **Relational Database (L3)** | **Amazon RDS PostgreSQL 18.3** (`db.t4g.micro`) | Relational metadata, tenants, users, datasets, and audit trails |
| **Vector Storage (L4)** | **Amazon RDS `pgvector`** (HNSW / IVFFlat) | High-dimensional embedding storage & cosine similarity search (`<->`) |
| **Foundation Models (LLM)** | **Amazon Bedrock** (Anthropic Claude 3.5 Sonnet / Haiku) | Code generation, schema cleaning, SQL generation, and chart synthesis |
| **Embedding Model** | **Amazon Titan Embeddings v2** (`amazon.titan-embed-text-v2:0`) | 1024-dimensional normalized vector embeddings via AWS Bedrock Runtime |
| **Secrets Management** | **AWS Secrets Manager** (KMS encrypted) | Dynamic master credential rotation and zero plaintext passwords |
| **Observability** | Structlog, Prometheus, Grafana | Structured JSON logging, LLM token cost tracking, and pipeline latency |

---

## Four-Layer Storage Engine

| Storage Layer | Data Stored | AWS Service | Access Pattern |
|---|---|---|---|
| **Layer 1: Raw Ingestion** | Original files (CSV, XLSX, JSON, Parquet) | **Amazon S3** | Immutable upload; signed URL client offloading |
| **Layer 2: Curated Artifacts** | Cleaned JSON matrices & cleaning plans | **Amazon S3** | Versioned object storage |
| **Layer 3: Relational / Structured** | Numeric metrics, categorical, timestamps | **Amazon RDS PostgreSQL** | ACID transactions, SQL analytical queries |
| **Layer 4: Semantic / Vector** | Column descriptions & data catalog vectors | **Amazon RDS `pgvector`** | Vector cosine / Euclidean similarity search |

---

## Multi-Agent Pipeline

| Agent | Responsibility |
|---|---|
| **Supervisor** | Orchestrates stage transitions across background execution workers. |
| **Domain Agent** | Injects domain-specific prompts (financial metrics, healthcare ICD-10, retail AOV). |
| **Ingestion Agent** | Sniffs encoding/delimiters, profiles column types, detects schema conflicts. |
| **Cleaning Plan Agent** | Drafts numbered cleaning transformations with confidence scores and rationale. Does *not* execute. |
| **Cleaning Executor** | Executes *only* human-approved steps; writes before/after diffs to `audit_log`. |
| **Intent Agent** | Parses natural-language questions into structured analysis specifications. |
| **Analysis Agent** | Runs hybrid queries (numeric SQL joins on RDS + semantic search on `pgvector`). |
| **Dashboard Agent** | Generates declarative Vega-Lite visualization specifications for interactive charts. |
| **Insights Agent** | Produces contextual narratives with recommended strategic business decisions. |

---

## HITL (Human-in-the-Loop) Governance Checkpoints

```
Domain Selection → Upload → Detect & Profile → [HITL #1: Schema & Merge]
→ Cleaning Plan → [HITL #2: Cleaning Plan Approval] → Execute & Route
→ Intent Capture → [HITL #3: Intent Confirmation]
→ Analyze → Dashboard → Insights
```

1. **Checkpoint 1 (Schema & Merge):** User confirms or overrides merge strategy (*join, union, separate*), join keys, and column exclusions.
2. **Checkpoint 2 (Cleaning Plan Approval):** User approves, edits, or discards individual AI cleaning steps (*impute missing, trim whitespace, normalize dates*).
3. **Checkpoint 3 (Intent Confirmation):** User refines the AI's restated analytical goal before code execution.
4. **Checkpoint 4 (Dashboard Accept/Refine):** User accepts charts or triggers conversational follow-up iterations.

---

## Project Structure

```
DataMind-AI/
├── backend/
│   ├── alembic/              # Database schema migrations
│   ├── app/
│   │   ├── agents/           # Autonomous agent implementations
│   │   ├── api/v1/           # FastAPI endpoints (auth, datasets, jobs, admin)
│   │   ├── core/
│   │   │   ├── config.py     # Pydantic environment configuration
│   │   │   ├── database.py   # Async SQLAlchemy engine for Amazon RDS
│   │   │   ├── s3.py         # Threadpool-backed non-blocking Amazon S3 service
│   │   │   ├── secrets.py    # AWS Secrets Manager dynamic credential caching
│   │   │   ├── security.py   # Native HS256 JWT auth & PBKDF2 password hashing
│   │   │   ├── embeddings.py # Amazon Titan Embeddings v2 runtime
│   │   │   └── llm.py        # Amazon Bedrock & LiteLLM provider gateway
│   │   ├── models/           # SQLAlchemy ORM & Pydantic v2 schemas
│   │   └── workers/tasks.py  # BackgroundTasks multi-stage pipeline worker
│   └── tests/                # Automated pytest unit & integration test suite
├── frontend/
│   ├── app/                  # Next.js App Router (/app/* workspace, /admin/*)
│   ├── components/           # shadcn/ui & Recharts dashboard components
│   └── lib/                  # REST API client & state management hooks
├── infra/                    # Terraform / AWS Infrastructure as Code
└── README.md                 # Project Documentation
```

---

## Local Setup & Development

### Prerequisites
* Python 3.11+
* Node.js 20+
* AWS CLI configured (or IAM access keys in `.env`)

### Backend Setup
```bash
cd backend

# Install dependencies
pip install -r requirements.txt

# Run database migrations against Amazon RDS
alembic upgrade head

# Launch FastAPI development server
uvicorn app.main:app --reload --port 8000
```

### Frontend Setup
```bash
cd frontend

# Install dependencies
pnpm install

# Launch Next.js dev server
pnpm dev
```
Open [http://localhost:3000](http://localhost:3000) to access the DataMind AI interface.

---

## License
Internal — Enterprise Confidential
