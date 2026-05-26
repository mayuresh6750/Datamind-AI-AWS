# DataMind AI — Low-Level Design Document

**Version**: 1.0 (Phase 1)
**Date**: May 2026
**Stack**: Google Gemini 3.5 Flash | Supabase Vector (pgvector) | FastAPI BackgroundTasks | PostgreSQL | JSON

---

## 1. API Endpoints

### 1.1 Authentication

| Method | Endpoint | Purpose | Request Body | Response |
|--------|----------|---------|--------------|----------|
| POST | /api/v1/auth/signup | Create account | `{email, password}` | `{user_id, message}` |
| POST | /api/v1/auth/login | Issue JWT | `{email, password}` | `{token, refresh_token, role}` |
| POST | /api/v1/auth/refresh | Refresh token | `{refresh_token}` | `{token}` |

### 1.2 User Profile

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | /api/v1/me | Current user profile |
| PATCH | /api/v1/me/domain | Update active domain |

### 1.3 Datasets

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | /api/v1/datasets/upload-url | Get presigned upload URLs |
| POST | /api/v1/datasets/{id}/ingest | Trigger format detection + JSON normalisation |
| GET | /api/v1/datasets/{id}/merge-plan | Schema + type-routing preview (HITL #1) |
| POST | /api/v1/datasets/{id}/merge-plan/decision | Submit HITL #1 decision |
| GET | /api/v1/datasets/{id}/cleaning-plan | Cleaning steps with confidence (HITL #2) |
| POST | /api/v1/datasets/{id}/cleaning-plan/decision | Submit HITL #2 decision |
| GET | /api/v1/datasets/{id}/archive | Download original archived files |

### 1.4 Jobs

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | /api/v1/jobs/{job_id} | Poll job status |
| GET | /api/v1/jobs/{job_id}/audit | Download audit log |

### 1.5 Dashboards

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | /api/v1/datasets/{id}/intent | Submit user intent (HITL #3) |
| POST | /api/v1/dashboards/generate | Generate dashboard |
| GET | /api/v1/dashboards/{id} | Retrieve dashboard spec + narrative |

### 1.6 Admin

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET/POST | /api/v1/admin/users | List/invite/suspend/change role |
| GET/PUT | /api/v1/admin/llm-providers | Read/write LLM config |
| GET | /api/v1/admin/llm-providers/usage | Per-provider cost/latency |
| GET | /api/v1/admin/domain-packs | List domain prompt packs |
| GET | /api/v1/admin/health | System health metrics |
| GET | /api/v1/admin/audit | Search audit log |

---

## 2. Database Schema (PostgreSQL)

### 2.1 users

```sql
CREATE TABLE users (
    user_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(tenant_id),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(20) NOT NULL DEFAULT 'user'
        CHECK (role IN ('user', 'admin')),
    active_domain VARCHAR(20) NOT NULL DEFAULT 'other'
        CHECK (active_domain IN ('finance','healthcare','retail','marketing','operations','other')),
    other_domain_descriptor VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_users_tenant ON users(tenant_id);
CREATE INDEX idx_users_email ON users(email);
```

### 2.2 tenants

```sql
CREATE TABLE tenants (
    tenant_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    default_llm_provider VARCHAR(50) NOT NULL DEFAULT 'google_gemini',
    default_llm_model VARCHAR(100) NOT NULL DEFAULT 'gemini-3.5-flash',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### 2.3 datasets

```sql
CREATE TABLE datasets (
    dataset_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(user_id),
    original_filenames TEXT[] NOT NULL,
    detected_format VARCHAR(20) NOT NULL
        CHECK (detected_format IN ('csv','xlsx','json','parquet')),
    file_count INT NOT NULL DEFAULT 1,
    merge_strategy VARCHAR(20)
        CHECK (merge_strategy IN ('single','union','join','separate')),
    merge_key_column VARCHAR(255),
    domain_at_creation VARCHAR(20),
    archive_uris TEXT[],
    json_uri TEXT NOT NULL,
    row_count_raw BIGINT,
    row_count_clean BIGINT,
    status VARCHAR(30) NOT NULL DEFAULT 'uploaded'
        CHECK (status IN ('uploaded','profiling','awaiting_hitl_merge',
                          'cleaning_plan','awaiting_hitl_cleaning',
                          'executing','ready','error')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_datasets_user ON datasets(user_id);
CREATE INDEX idx_datasets_status ON datasets(status);
```

### 2.4 hitl_decisions

```sql
CREATE TABLE hitl_decisions (
    decision_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dataset_id UUID NOT NULL REFERENCES datasets(dataset_id),
    user_id UUID NOT NULL REFERENCES users(user_id),
    checkpoint VARCHAR(30) NOT NULL
        CHECK (checkpoint IN ('schema_merge','cleaning_plan','intent','dashboard_accept')),
    proposal_json JSONB NOT NULL,
    decision_json JSONB NOT NULL,
    latency_seconds INT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_hitl_dataset ON hitl_decisions(dataset_id);
```

### 2.5 pipeline_runs

```sql
CREATE TABLE pipeline_runs (
    run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dataset_id UUID NOT NULL REFERENCES datasets(dataset_id),
    status VARCHAR(20) NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued','running','paused_for_hitl','complete','failed')),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    error_summary TEXT,
    audit_log_uri TEXT,
    llm_provider VARCHAR(50) NOT NULL DEFAULT 'google_gemini',
    total_llm_tokens BIGINT,
    total_llm_cost_usd DECIMAL(10,6),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_pipeline_dataset ON pipeline_runs(dataset_id);
CREATE INDEX idx_pipeline_status ON pipeline_runs(status);
```

### 2.6 llm_provider_config

```sql
CREATE TABLE llm_provider_config (
    config_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(tenant_id),
    default_provider VARCHAR(50) NOT NULL DEFAULT 'google_gemini',
    default_model VARCHAR(100) NOT NULL DEFAULT 'gemini-3.5-flash',
    per_agent_overrides JSONB DEFAULT '{}',
    secrets_vault_path TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by_user_id UUID REFERENCES users(user_id)
);
```

### 2.7 audit_log

```sql
CREATE TABLE audit_log (
    entry_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dataset_id UUID REFERENCES datasets(dataset_id),
    run_id UUID REFERENCES pipeline_runs(run_id),
    user_id UUID REFERENCES users(user_id),
    agent_name VARCHAR(50) NOT NULL,
    action_type VARCHAR(50) NOT NULL,
    rows_affected INT,
    rationale TEXT,
    confidence DECIMAL(3,2),
    llm_provider VARCHAR(50),
    llm_model VARCHAR(100),
    tokens_used INT,
    before_snapshot JSONB,
    after_snapshot JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_audit_dataset ON audit_log(dataset_id);
CREATE INDEX idx_audit_user ON audit_log(user_id);
CREATE INDEX idx_audit_created ON audit_log(created_at);
```

---

## 3. Storage Architecture

### 3.1 Archive Store (Original Files)

- **Service**: Supabase Storage (versioned bucket)
- **Path**: `supabase://datamind-archive/{user_id}/{dataset_id}/{timestamp}/{filename}`
- **Access**: Per-user prefix isolation
- **Encryption**: AES-256
- **Retention**: 90 days (P1)
- **Immutability**: Files never modified; retrievable on user request

### 3.2 JSON Processing Layer

- **Service**: Supabase Storage + Supabase Database (PostgreSQL)
- **Path**: `supabase://datamind-json/{user_id}/{dataset_id}/v{version}/data.json`
- **Processing**: All agents operate on JSON data
- **Mirror**: Structured data also written to typed PostgreSQL tables for SQL queries

### 3.3 Numeric/Structured Store (PostgreSQL)

- **Service**: Supabase Database (PostgreSQL)
- **Columns**: Numeric (int, float), boolean, date/datetime, low-cardinality categorical
- **Access**: SQL via Analysis Agent

### 3.4 Textual/Semantic Store (pgvector)

- **Service**: Supabase Vector (pgvector) on PostgreSQL
- **Index**: HNSW for cosine similarity
- **Embedding model**: Google Gemini 3.5 Flash
- **Access**: Semantic search via Analysis Agent

---

## 4. Agent Contracts (Pydantic Models)

### 4.1 Ingestion Agent Output

```python
from pydantic import BaseModel
from typing import Optional

class ColumnProfile(BaseModel):
    name: str
    dtype: str
    null_count: int
    distinct_count: int
    avg_length: Optional[float]
    classification: str  # "numeric", "textual", "ambiguous"

class MergePlan(BaseModel):
    strategy: str  # "single", "union", "join", "separate"
    join_key: Optional[str]
    confidence: float
    column_profiles: list[ColumnProfile]
```

### 4.2 Cleaning Plan Agent Output

```python
class CleaningStep(BaseModel):
    step_id: int
    action: str       # "deduplicate", "impute", "coerce_type", "flag_outlier"
    column: Optional[str]
    method: str       # "exact_dedup", "median", "mode", "drop", "leave", etc.
    rationale: str
    confidence: float
    rows_affected: int
    before_sample: Optional[dict]
    after_sample: Optional[dict]

class CleaningPlan(BaseModel):
    steps: list[CleaningStep]
    total_rows_before: int
    total_rows_after: int
```

### 4.3 Intent Agent Output

```python
class AnalysisSpec(BaseModel):
    dimensions: list[str]
    measures: list[str]
    time_range: Optional[dict]
    filters: Optional[list[dict]]
    suggested_chart_types: list[str]
    confidence: float
```

### 4.4 Dashboard Agent Output

```python
class KPICard(BaseModel):
    label: str
    value: str
    change: Optional[str]
    change_pct: Optional[float]

class ChartSpec(BaseModel):
    chart_type: str  # "line", "bar", "table"
    title: str
    data: list[dict]
    x_field: str
    y_field: str
    color_field: Optional[str]

class DashboardSpec(BaseModel):
    kpi_cards: list[KPICard]
    charts: list[ChartSpec]
    narrative: str
```

---

## 5. Column Routing Algorithm

```python
def classify_column(series) -> str:
    dtype = series.dtype
    n = len(series)
    distinct = series.nunique()
    avg_len = series.astype(str).str.len().mean() if dtype == 'object' else 0

    # Numeric / structured
    if dtype in ('int64', 'float64', 'bool', 'datetime64[ns]'):
        return 'numeric'
    if dtype == 'object' and avg_len <= 40 and distinct <= 50:
        return 'numeric'
    if dtype == 'object' and distinct / n <= 0.05:
        return 'numeric'

    # Textual / semantic
    if dtype == 'object' and avg_len > 40 and distinct > n * 0.5:
        return 'textual'

    # Ambiguous
    return 'ambiguous'

def route_columns(df) -> dict:
    return {col: classify_column(df[col]) for col in df.columns}
```

---

## 6. HITL State Machine

```
UPLOADED → PROFILING → AWAITING_HITL_MERGE
    → CLEANING_PLAN → AWAITING_HITL_CLEANING
    → EXECUTING → READY
    → (INTENT_CAPTURE → DASHBOARD_READY)
```

Transitions:
- `UPLOADED`: files received → trigger profiling via FastAPI BackgroundTasks
- `PROFILING`: profile complete → state changes to AWAITING_HITL_MERGE
- `AWAITING_HITL_MERGE`: user submits merge decision → trigger cleaning plan
- `CLEANING_PLAN`: plan generated → state changes to AWAITING_HITL_CLEANING
- `AWAITING_HITL_CLEANING`: user submits cleaning approval → trigger execution
- `EXECUTING`: execution complete → state changes to READY
- `READY`: intent captured → state changes to DASHBOARD_READY

---

## 7. LLM Provider Abstraction

```python
from typing import Protocol
from pydantic import BaseModel

class LLMProvider(Protocol):
    async def structured_completion(
        self, prompt: str, schema: type[BaseModel]
    ) -> BaseModel: ...

    async def embed_text(self, text: str) -> list[float]: ...

class GoogleGeminiProvider:
    def __init__(self, api_key: str, model: str = "gemini-3.5-flash"):
        self.api_key = api_key
        self.model = model

    async def structured_completion(self, prompt, schema):
        # Returns JSON matching the Pydantic schema
        ...

    async def embed_text(self, text):
        # Returns embedding vector
        ...
```

---

## 8. Error Codes

| Code | Description | Retryable |
|------|-------------|-----------|
| STORAGE_UPLOAD_FAILED | File upload to Supabase Storage failed | Yes (3×) |
| STORAGE_ARCHIVE_FAILED | Archiving original file failed | Yes (3×) |
| FORMAT_DETECTION_FAILED | Cannot detect file format | No |
| FORMAT_UNSUPPORTED | File format not in supported list | No |
| JSON_NORMALISATION_FAILED | Conversion to JSON failed | Yes (3×) |
| COLUMN_CLASSIFICATION_FAILED | Column type routing failed | Yes (2×) |
| CLEANING_PLAN_FAILED | Cleaning plan generation failed | Yes (3× with backoff) |
| CLEANING_EXECUTION_FAILED | Cleaning step execution failed | Yes (3×) |
| PGVECTOR_UPSERT_FAILED | Embedding storage in pgvector failed | Yes (3×) |
| POSTGRES_WRITE_FAILED | Writing to PostgreSQL failed | Yes (3×) |
| LLM_COMPLETION_FAILED | LLM call returned error | Yes (3× with backoff) |
| LLM_SCHEMA_VALIDATION_FAILED | LLM output didn't match Pydantic schema | Yes (2×) |
| LLM_RATE_LIMITED | LLM provider rate limit hit | Yes (exponential backoff) |
| INTENT_PARSING_FAILED | Cannot parse user intent | Yes (2×) |
| DASHBOARD_GENERATION_FAILED | Dashboard chart generation failed | Yes (2×) |
| HITL_DECISION_TIMEOUT | HITL decision pending too long | No (blocks) |
| AUTH_TOKEN_EXPIRED | JWT has expired | No (refresh) |
| AUTH_INVALID_ROLE | User lacks required role | No |

---

## 9. Folder Structure

```
DataMind-AI/
├── backend/
│   ├── app/
│   │   ├── agents/          # LangGraph agents (Domain, Ingestion, Cleaning, Intent, Analysis, Dashboard, Insights)
│   │   ├── api/v1/          # FastAPI route handlers
│   │   │   ├── auth.py
│   │   │   ├── datasets.py
│   │   │   ├── jobs.py
│   │   │   ├── dashboards.py
│   │   │   └── admin/
│   │   ├── core/            # Config, database, security, Supabase Storage client
│   │   ├── models/          # Pydantic models + SQLAlchemy ORM models
│   │   └── main.py          # FastAPI app entry point
│   ├── workers/             # FastAPI BackgroundTasks handlers
│   │   └── tasks.py         # Background task definitions
│   └── tests/
├── frontend/
│   ├── app/
│   │   ├── (user)/          # User UI routes
│   │   └── admin/           # Admin UI routes
│   ├── components/          # Shared UI components (shadcn/ui)
│   └── lib/                 # API client, hooks, TypeScript types
├── infra/
│   └── terraform/           # IaC definitions
└── docs/                    # Project documentation
```

---

## 10. Environment Variables

| Variable | Source | Default |
|----------|--------|---------|
| DATABASE_URL | Supabase Vault | - |
| SUPABASE_URL | .env | http://localhost:54321 |
| SUPABASE_SERVICE_KEY | Supabase Vault | - |
| JWT_SIGNING_KEY | Supabase Vault | - |
| LLM_API_KEY | Supabase Vault | - |
| LLM_MODEL | .env | gemini-3.5-flash |
| STORAGE_ARCHIVE_BUCKET | .env | datamind-archive |
| STORAGE_JSON_BUCKET | .env | datamind-json |

---

## 11. Observability Metrics

| Metric | Type | Labels |
|--------|------|--------|
| pipeline_duration_seconds | Histogram | stage |
| hitl_decision_latency_seconds | Histogram | checkpoint |
| hitl_approval_rate | Gauge | checkpoint, domain |
| agent_confidence | Gauge | agent |
| cleaning_rows_changed_total | Counter | action_type |
| llm_tokens_used | Counter | provider, agent |
| llm_cost_usd | Counter | provider, agent |
| llm_provider_error_rate | Rate | provider |
| type_routing_distribution | Counter | class |

---

## 12. Security Implementation

- **Authentication**: JWT (HS256, 1-hour expiry, refresh tokens). Argon2 password hashing.
- **RBAC**: Roles: `user`, `admin`. Enforced via FastAPI middleware on every endpoint.
- **UI separation**: `/admin/*` blocked at API level for non-admin tokens (HTTP 403).
- **Per-user prefix isolation**: Supabase Storage paths include `{user_id}`.
- **Encryption at rest**: AES-256 (Supabase managed).
- **Encryption in transit**: TLS 1.3 minimum.
- **Secrets**: Supabase Vault for all API keys and credentials.
- **Input sanitisation**: Length-bounded, control-characters stripped on all user strings.
