# DataMind AI — Error Reference

All API errors follow a consistent JSON envelope. Pipeline errors have a structured state machine with explicit recovery paths.

---

## Error Response Envelope

```json
{
  "error": "ERROR_CODE",
  "code": "SPECIFIC_CODE",
  "message": "Human-readable description of what went wrong.",
  "details": { "field": "...", "context": "..." }
}
```

- `error` — high-level category (maps to HTTP status)
- `code` — machine-readable specific code for programmatic handling
- `message` — plain English for display or logs
- `details` — optional structured context (field name, value, expected format)

---

## HTTP Status Code Mapping

| HTTP Status | Error Category | When Used |
|---|---|---|
| 400 | `VALIDATION_ERROR` | Malformed request body, missing required fields, invalid enum value |
| 401 | `AUTHENTICATION_ERROR` | Missing, expired, or invalid JWT |
| 403 | `AUTHORIZATION_ERROR` | Valid JWT but insufficient role (e.g., non-admin hitting `/admin/*`) |
| 404 | `NOT_FOUND` | Dataset, job, dashboard, or domain pack does not exist or belongs to another user |
| 409 | `CONFLICT` | Duplicate resource creation (e.g., email already registered) |
| 413 | `PAYLOAD_TOO_LARGE` | File exceeds 50MB per file or 250MB total (Phase 1 limits) |
| 422 | `UNPROCESSABLE_ENTITY` | Structurally valid request but semantically invalid (e.g., incompatible merge key) |
| 429 | `RATE_LIMIT_EXCEEDED` | > 100 req/min per user or > 5 concurrent pipelines |
| 500 | `INTERNAL_ERROR` | Unhandled server exception; always logged with `request_id` |
| 503 | `SERVICE_UNAVAILABLE` | LLM provider down, Supabase Storage unreachable, or agent worker offline |

---

## Authentication & Authorization Errors

| Code | HTTP | Message | Resolution |
|---|---|---|---|
| `AUTH_TOKEN_MISSING` | 401 | No JWT provided in Authorization header. | Include `Authorization: Bearer <token>` |
| `AUTH_TOKEN_EXPIRED` | 401 | JWT has expired. Please refresh. | Use refresh token to obtain a new access token |
| `AUTH_TOKEN_INVALID` | 401 | JWT signature verification failed. | Re-authenticate |
| `AUTH_REFRESH_TOKEN_INVALID` | 401 | Refresh token is invalid or has been revoked. | Re-authenticate from scratch |
| `AUTH_EMAIL_TAKEN` | 409 | An account with this email already exists. | Log in or use password reset |
| `AUTH_INVALID_CREDENTIALS` | 401 | Email or password is incorrect. | Check credentials |
| `RBAC_INSUFFICIENT_ROLE` | 403 | Your role does not permit access to this resource. | Admin access required; contact your tenant admin |
| `RBAC_ADMIN_DEMOTED` | 401 | Your admin role has been revoked. Please re-authenticate. | Re-login with updated role |

---

## File Upload Errors

| Code | HTTP | Message | Resolution |
|---|---|---|---|
| `UPLOAD_FILE_TOO_LARGE` | 413 | File "{filename}" exceeds the 50MB per-file limit. | Reduce file size or split the dataset |
| `UPLOAD_TOTAL_TOO_LARGE` | 413 | Total upload size exceeds the 250MB limit for this upload set. | Reduce the number of files or split uploads |
| `UPLOAD_FORMAT_MIXED` | 400 | All files in a single upload must be the same format. Found: CSV and XLSX. | Upload files of the same format together |
| `UPLOAD_FORMAT_UNSUPPORTED` | 400 | Format "{ext}" is not supported. Accepted: CSV, XLSX, JSON, Parquet. | Convert to a supported format |
| `UPLOAD_FILE_EMPTY` | 400 | File "{filename}" has zero bytes. | Provide a non-empty file |
| `UPLOAD_ENCODING_INVALID` | 422 | Could not detect encoding for "{filename}". | Re-save as UTF-8 |
| `UPLOAD_PRESIGNED_URL_EXPIRED` | 400 | The presigned Supabase Storage URL has expired. Please request a new one. | Retry the upload-url endpoint |
| `UPLOAD_PARQUET_SCHEMA_MISMATCH` | 422 | Parquet files in this upload have incompatible schemas. | Review column differences in HITL #1 |
| `UPLOAD_XLSX_MULTI_SHEET` | 422 | XLSX file "{filename}" has multiple sheets. Please select one to proceed. | User prompted to pick a sheet in HITL #1 |
| `UPLOAD_STORAGE_WRITE_FAILED` | 503 | Could not write file to raw storage. Please retry. | Transient Supabase Storage issue; retry with backoff |

---

## Ingestion & Profiling Errors

| Code | HTTP | Message | Resolution |
|---|---|---|---|
| `INGEST_FORMAT_DETECTION_FAILED` | 422 | Could not determine file format for "{filename}". | Ensure file extension matches content |
| `INGEST_PARSE_ERROR` | 422 | Failed to parse "{filename}" as {format}: {detail}. | Check for malformed rows or encoding issues |
| `INGEST_PROFILE_TIMEOUT` | 503 | Profiling timed out for this dataset. | Retry; if persistent, contact support |
| `INGEST_MERGE_KEY_NOT_FOUND` | 422 | Proposed join key "{column}" does not exist in all files. | Select a valid join key in HITL #1 |
| `INGEST_CARTESIAN_WARNING` | 422 | The selected join key produces a Cartesian product (estimated rows: {n}). Confirm to proceed. | Review join key choice in HITL #1 |
| `INGEST_COLUMN_COUNT_ZERO` | 422 | Dataset "{filename}" has no readable columns after parsing. | Check file structure |

---

## HITL & Pipeline State Errors

| Code | HTTP | Message | Resolution |
|---|---|---|---|
| `HITL_NOT_PENDING` | 409 | This HITL checkpoint is not awaiting a decision (status: {status}). | Check current pipeline status via /jobs/{id} |
| `HITL_DECISION_INVALID` | 400 | Decision payload is missing required fields or contains invalid values. | Review the expected decision schema |
| `PIPELINE_NOT_FOUND` | 404 | Pipeline job {job_id} not found or does not belong to your account. | Verify job_id |
| `PIPELINE_ALREADY_RUNNING` | 409 | A pipeline is already running for dataset {dataset_id}. | Wait for it to complete or reach a HITL gate |
| `PIPELINE_CONCURRENCY_LIMIT` | 429 | You have reached the limit of 5 concurrent pipeline jobs. | Wait for an existing job to complete |
| `PIPELINE_RESUME_FAILED` | 503 | Could not resume pipeline from persisted state. | Contact support with run_id |
| `PIPELINE_TOKEN_BUDGET_EXCEEDED` | 503 | This pipeline exceeded the LLM token budget (150K input / 25K output). Pipeline halted. | Split dataset or simplify intent; review cost settings with admin |

---

## Cleaning Errors

| Code | HTTP | Message | Resolution |
|---|---|---|---|
| `CLEAN_PLAN_GENERATION_FAILED` | 503 | Cleaning Plan Agent could not generate a plan. LLM returned an invalid response after 3 retries. | Retry; check LLM provider status in Admin UI |
| `CLEAN_EXECUTION_STEP_FAILED` | 500 | Cleaning step #{n} ("{action}") failed during execution: {detail}. | Partial results available in audit log; retry or skip step |
| `CLEAN_NO_STEPS_APPROVED` | 200 | No cleaning steps were approved. Pipeline will proceed with uncleaned data. | Expected state — a banner is shown in the UI |
| `CLEAN_IMPUTATION_COLUMN_NOT_FOUND` | 422 | Column "{col}" specified for imputation no longer exists in the dataset. | Re-run profiling |
| `CLEAN_COERCION_FAILED` | 422 | Could not coerce column "{col}" to type {type}: {sample_value} is incompatible. | Change type-routing at HITL #1 or skip this step |

---

## LLM Provider Errors

| Code | HTTP | Message | Resolution |
|---|---|---|---|
| `LLM_PROVIDER_UNAVAILABLE` | 503 | LLM provider "{provider}" is unreachable. Please retry. | Check provider status; admin can switch provider in Admin UI |
| `LLM_SCHEMA_VALIDATION_FAILED` | 503 | LLM output did not conform to expected schema after 3 retries. | Check prompt template version; report to engineering |
| `LLM_RATE_LIMIT` | 429 | LLM provider rate limit hit for this tenant. Retry after {retry_after}s. | Wait and retry; P2 will add automatic failover |
| `LLM_CONTEXT_WINDOW_EXCEEDED` | 422 | The dataset profile is too large to fit in the LLM context window. | Reduce file size or number of columns |
| `LLM_COST_CEILING_HIT` | 503 | Pipeline cost ceiling reached. LLM calls halted. | Admin can adjust cost ceiling; split the dataset |
| `LLM_PROVIDER_CONFIG_MISSING` | 500 | No LLM provider is configured for this tenant. | Admin must configure a provider in Admin UI → LLM Config |
| `LLM_SECRETS_FETCH_FAILED` | 500 | Could not retrieve API key from Supabase Vault. | Check Vault access permissions; contact support |

---

## Dashboard & Analysis Errors

| Code | HTTP | Message | Resolution |
|---|---|---|---|
| `ANALYSIS_NO_NUMERIC_COLUMNS` | 422 | No numeric/structured columns are available for SQL analysis. | All columns were routed to vector store; rephrase intent for textual query |
| `ANALYSIS_NO_TEXTUAL_COLUMNS` | 422 | No textual columns are available for semantic search. | All columns are numeric/structured; use SQL-based intent |
| `ANALYSIS_SQL_INVALID` | 422 | Generated SQL failed validation. DDL and write operations are blocked. | Report to engineering with intent_id |
| `ANALYSIS_EMPTY_RESULT` | 200 | Query returned no rows matching the intent. | Check cleaning results or rephrase intent |
| `DASHBOARD_CHART_UNSUPPORTED` | 422 | Requested chart type "{type}" is not available in Phase 1. Available: line, bar, table. | Use a supported chart type |
| `DASHBOARD_DATA_INSUFFICIENT` | 200 | Dataset has insufficient columns to render the requested chart type. Fell back to distribution chart. | Expected fallback state |
| `INTENT_NOT_ANSWERABLE` | 200 | This data does not appear to support the stated intent: "{intent}". | Rephrase intent or check that the relevant columns are present |

---

## Storage Errors

| Code | HTTP | Message | Resolution |
|---|---|---|---|
| `STORAGE_RAW_READ_FAILED` | 503 | Could not read raw file from Supabase Storage. Please retry. | Transient Supabase Storage issue |
| `STORAGE_CURATED_WRITE_FAILED` | 503 | Could not write curated Parquet to Supabase Storage. | Transient issue; pipeline will retry automatically (up to 3 attempts) |
| `STORAGE_PARQUET_CORRUPT` | 422 | Curated Parquet file for dataset {dataset_id} version {v} is corrupt. | Re-run cleaning from raw |
| `STORAGE_QUOTA_EXCEEDED` | 429 | Storage quota exceeded (5GB limit in Phase 1). Please delete old datasets. | Clean up old datasets; quota raised in Phase 2 plans |
| `STORAGE_DUCKDB_QUERY_FAILED` | 500 | DuckDB query execution failed: {detail}. | Report with dataset_id and intent_id |
| `STORAGE_WEAVIATE_UPSERT_FAILED` | 503 | Failed to write embeddings to Weaviate. | Transient Weaviate issue; retry |

---

## Admin Errors

| Code | HTTP | Message | Resolution |
|---|---|---|---|
| `ADMIN_LAST_ADMIN_GUARD` | 409 | Cannot demote or delete the last admin in this tenant. | Promote another user to admin first |
| `ADMIN_USER_NOT_FOUND` | 404 | User {user_id} not found in this tenant. | Verify user_id |
| `ADMIN_DOMAIN_PACK_NOT_FOUND` | 404 | Domain pack "{domain}" does not exist. | List available packs via GET /admin/domain-packs |
| `ADMIN_LLM_CONFIG_INVALID` | 400 | Per-agent override specifies an unsupported provider "{provider}". | Use a supported provider (mistral, kimi in P1) |

---

## Pipeline Status State Machine

```
uploaded
    │
    ▼
profiling ──── error (INGEST_*) ──────────────────────────► failed
    │
    ▼
awaiting_hitl_merge  ◄── user reviews HITL #1
    │
    ▼ (user POSTs decision)
cleaning_plan ──── error (CLEAN_PLAN_*) ──────────────────► failed
    │
    ▼
awaiting_hitl_cleaning  ◄── user reviews HITL #2
    │
    ▼ (user POSTs decision)
executing ──── error (CLEAN_EXECUTION_*) ─────────────────► failed
    │
    ▼
awaiting_hitl_intent  ◄── user submits intent HITL #3
    │
    ▼
analysing ──── error (ANALYSIS_*) ────────────────────────► failed
    │
    ▼
dashboard_generating ──── error (DASHBOARD_*) ───────────► failed
    │
    ▼
ready  ✓
```

- **Paused states** (`awaiting_hitl_*`) persist full LangGraph state to Supabase Database + Supabase Storage. A worker crash does not lose user decisions.
- **Failed state** always produces a partial audit log up to the failure point.
- **Retry**: failed pipelines are retryable via `POST /jobs/{id}/retry` (3 attempts with exponential backoff: 2s, 8s, 32s).

---

## Retry Strategy

| Failure Type | Auto-retry | Max Attempts | Backoff |
|---|---|---|---|
| Supabase Storage read/write transient | Yes | 3 | Exponential (2s, 8s, 32s) |
| LLM schema validation failure | Yes | 3 | Immediate |
| LLM rate limit | Yes (P2 failover) | 1 + failover | After `retry_after` |
| Supabase Database transient | Yes | 3 | Exponential |
| HITL decision timeout | No auto-execute in P1 | n/a | User must return and submit |
| Pipeline manual retry | User-initiated | 3 total | Manual |

---

## Observability for Errors

Every error emitted in a pipeline step is logged with:

```json
{
  "level": "error",
  "request_id": "...",
  "user_id": "...",
  "tenant_id": "...",
  "dataset_id": "...",
  "run_id": "...",
  "agent_name": "cleaning_plan",
  "error_code": "CLEAN_PLAN_GENERATION_FAILED",
  "provider": "mistral",
  "model": "mistral-small-latest",
  "retry_attempt": 3,
  "timestamp": "2026-05-21T10:00:00Z"
}
```

Alerts fire when:
- Job failure rate > 5% over 15 minutes → Page
- LLM error rate > 10% over 15 minutes (any provider) → Page
- Supabase Storage write failure → Page

---

## UI Error States

- Failed pipeline: specific, actionable error state with **Retry** and **Contact Support** buttons — no generic "something went wrong" messages.
- HITL Cartesian warning: shown inline before the user can confirm a join key that would explode rows.
- Low-confidence steps: shown in red with a prominent warning at HITL #2; unchecked by default.
- Token budget exceeded: inline banner on the dashboard with a link to Admin UI → LLM Config.
- Empty dataset post-cleaning: "No data to visualise" state — not a pipeline error.
- Intent not answerable: inline note on the dashboard — not a pipeline error.
