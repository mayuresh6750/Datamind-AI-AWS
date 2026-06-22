# DataMind AI — HITL Pipeline: Frontend & Backend Reference Guide

> **Purpose:** This document is a complete reference for the HITL (Human-In-The-Loop) pipeline work implemented for DataMind AI. It is written for a new team member joining the project, covering every file changed, every bug fixed, every design decision made, and every technical concept involved.

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Technical Stack](#2-technical-stack)
3. [Key Concept: HITL (Human-In-The-Loop)](#3-key-concept-hitl-human-in-the-loop)
4. [Architecture: How the Pipeline Works](#4-architecture-how-the-pipeline-works)
5. [Bug Fixes — Backend](#5-bug-fixes--backend)
   - 5.1 [Column Classification Bug](#51-column-classification-bug)
   - 5.2 [Union Multi-File Profile Merging Bug](#52-union-multi-file-profile-merging-bug)
6. [Frontend — Type System Fixes](#6-frontend--type-system-fixes)
   - 6.1 [pipeline.ts](#61-frontendtypespipelinetsts)
   - 6.2 [api.ts](#62-frontenddtypesapits)
7. [Frontend — HITL Checkpoint #1: Schema & Merge Validation](#7-frontend--hitl-checkpoint-1-schema--merge-validation)
   - 7.1 [validate/[id]/page.tsx](#71-appuservalidateidpagetsx)
   - 7.2 [SchemaTable.tsx](#72-componentsuserSchematTabletsx)
   - 7.3 [MergeProposal.tsx](#73-componentsusermergeproposaltsx)
8. [Frontend — HITL Checkpoint #2: Cleaning Plan Review](#8-frontend--hitl-checkpoint-2-cleaning-plan-review)
   - 8.1 [clean/[id]/page.tsx](#81-appusercleanidpagetsx)
   - 8.2 [Polling Mechanism](#82-polling-mechanism)
9. [Frontend — Shared Infrastructure](#9-frontend--shared-infrastructure)
   - 9.1 [pipelineApi.ts](#91-libpipelineapits)
   - 9.2 [next.config.js](#92-nextconfigjs)
10. [Upload Page Bug Fix](#10-upload-page-bug-fix)
11. [Test Data Files](#11-test-data-files)
12. [Confidence Score Framework](#12-confidence-score-framework)
13. [Data Type Classification Rules](#13-data-type-classification-rules)
14. [API Contract Reference](#14-api-contract-reference)
15. [End-to-End Flow Walkthrough](#15-end-to-end-flow-walkthrough)
16. [Known Limitations & Future Work](#16-known-limitations--future-work)

---

## 1. Project Overview

DataMind AI is an agentic data intelligence platform that transforms raw business data (CSV, XLSX, JSON, Parquet) into clean, contextual dashboards and actionable business insights — without requiring SQL or Python knowledge.

The platform is built around four core principles:

| Principle | Description |
|-----------|-------------|
| **Domain-first** | Users select their business domain (Finance, Healthcare, Retail, Marketing, Operations, Other) so all downstream agents use domain-appropriate vocabulary and KPIs |
| **User-controlled data modeling** | Users decide how multiple files are merged (union, join, separate) |
| **Human-In-The-Loop (HITL)** | No cleaning or analysis runs without explicit user approval at defined checkpoints |
| **Type-aware storage routing** | Numeric/structured columns go to PostgreSQL; free-text columns go to pgvector (Supabase Vector) |

---

## 2. Technical Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 14 (App Router), TypeScript, Tailwind CSS, shadcn/ui |
| Backend | Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy (async) |
| Database | Supabase (PostgreSQL + pgvector) |
| Auth | Supabase Auth (JWT-based, email/password) |
| Storage | Supabase Storage (presigned upload URLs) |
| LLM | Google Gemini 3.5 Flash via LiteLLM-compatible abstraction |
| Embeddings | Qwen3-Embedding-0.6B (self-hosted, sentence-transformers) |
| Agent Orchestration | LangGraph (supervisor pattern) |
| Package Manager (Frontend) | pnpm |
| Package Manager (Backend) | uv |

---

## 3. Key Concept: HITL (Human-In-The-Loop)

HITL checkpoints are explicit pauses in the automated pipeline where the user must review and approve what the AI has produced before execution continues. Nothing runs silently.

### The Three HITL Checkpoints (Phase 1)

| # | Checkpoint | What the user sees | User actions |
|---|------------|-------------------|--------------|
| **#1** | Schema & Merge Validation | Inferred column schema, proposed merge strategy, per-column classification | Approve, change merge key, change type routing, exclude columns |
| **#2** | Cleaning Plan Approval | Numbered list of proposed cleaning steps with rationale and confidence | Approve all, approve some, reject some |
| **#3** | Intent Confirmation | AI restatement of the user's analysis question | Approve, refine |

### Why HITL Matters

Without HITL, an AI agent might:
- Silently drop rows that look like outliers but are actually valid edge cases
- Misclassify a column (e.g., treating "patient_id" as a numeric field to sum)
- Choose the wrong merge strategy for multi-file datasets

HITL gives the user full control and creates an audit trail for every decision.

---

## 4. Architecture: How the Pipeline Works

```
User uploads file(s)
        ↓
Ingestion Agent: detect format → parse → profile columns → propose merge plan
        ↓
[HITL #1] User reviews schema, merge strategy, column types → Approves
        ↓
Cleaning Plan Agent: generates numbered list of proposed cleaning actions
        ↓
[HITL #2] User approves/rejects individual steps → Submits
        ↓
Cleaning Executor Agent: runs only approved steps → writes cleaned data
        ↓
[HITL #3] User submits analysis intent (natural language question)
        ↓
Analysis Agent → Dashboard Agent → Insights Agent
        ↓
Dashboard rendered in UI
```

### Dataset Status State Machine

The `datasets` table has a `status` column that tracks pipeline progress:

```
uploaded → profiling → awaiting_hitl_merge
                               ↓ (user approves HITL #1)
                        cleaning_plan → awaiting_hitl_cleaning
                                               ↓ (user approves HITL #2)
                                          executing → ready
```

### Job vs Pipeline Step

The job registry tracks two separate things — new team members often confuse these:

| Field | What it is | Example values |
|-------|------------|----------------|
| `job.status` | Whether the background task is running | `queued`, `running`, `complete`, `error` |
| `job.current_step` | Which pipeline stage is active | `awaiting_hitl_merge`, `awaiting_hitl_cleaning` |

The frontend must check `job.current_step` (not `job.status`) to know when to redirect to a HITL page.

---

## 5. Bug Fixes — Backend

### 5.1 Column Classification Bug

**File:** `backend/app/agents/ingestion.py` — `profile_columns()` method, lines ~120–131

**What was wrong:**

The `profile_columns()` method classifies each column as `numeric`, `textual`, or `ambiguous`. The original logic checked conditions in the wrong order:

```python
# BEFORE (buggy order)
if numeric_ratio >= 0.9:
    classification = "numeric"          # ✓ correct
elif distinct_count <= 50:
    classification = "numeric"          # ✗ WRONG — fires for all text columns in small files
elif avg_length >= 40 or distinct_count > 0.5 * len(rows):
    classification = "textual"          # never reached for small datasets
else:
    classification = "ambiguous"
```

**Why it broke:** The low-cardinality check (`distinct_count <= 50`) always fired for free-text columns in small test files. A 10-row file with columns like `patient_name`, `diagnosis`, and `notes` would all have distinct_count ≤ 10, trivially satisfying `<= 50`, so they all got classified as `numeric/categorical` before the textual check ever ran.

**The fix — reorder conditions:**

```python
# AFTER (correct order)
if numeric_ratio >= 0.9:
    classification = "numeric"          # step 1: most values parse as float
    dtype = "float"
elif avg_length >= 40 or distinct_count > 0.5 * len(rows):
    classification = "textual"          # step 2: long text OR high cardinality ratio
    dtype = "text"
elif distinct_count <= 50:
    classification = "numeric"          # step 3: short, low-cardinality — categorical
    dtype = "categorical"
else:
    classification = "ambiguous"
    dtype = "text"
```

**Rule:** Textual check must come before the low-cardinality check, because a column can be both low-cardinality and long-text (e.g., `notes` in a 5-row file).

**Classification rules reference (from CLAUDE.md):**

| Class | Detection rule | Storage path |
|-------|---------------|--------------|
| Numeric/Structured | ≥90% values parse as float, OR low-cardinality categorical (≤50 distinct values) with short text | PostgreSQL |
| Textual/Semantic | Avg string length > 40 chars OR distinct count > 50% of total rows | pgvector (Supabase Vector) |
| Ambiguous | Neither rule matches — shown to user in HITL #1 | User decides |

---

### 5.2 Union Multi-File Profile Merging Bug

**Files changed:**
- `backend/app/agents/ingestion.py` — `propose_merge_plan()` method
- `backend/app/workers/tasks.py` — `run_ingest_pipeline()` function

**What was wrong:**

When two files with identical column schemas are uploaded together, the system recommends a UNION merge strategy (stack all rows). But the `propose_merge_plan()` function was returning column profiles taken only from the **first file**:

```python
# BEFORE (buggy)
if all(s == all_col_sets[0] for s in all_col_sets):
    all_profiles = file_profiles[0][1]   # ← only first file's stats!
    return MergePlan(strategy="union", confidence=0.92, column_profiles=all_profiles)
```

This meant the schema table on the validate page showed stats (null counts, distinct counts, avg lengths) reflecting only the first file — not the true combined dataset.

**Symptom:** Uploading two 10-row healthcare CSV files showed `distinct_count = 10` for `patient_id` instead of `20`.

**The fix:**

Added an optional `all_rows` parameter to `propose_merge_plan()` and recompute profiles over the combined row set for UNION:

```python
# AFTER (fixed)
def propose_merge_plan(
    self,
    file_profiles: list[tuple[str, list[ColumnProfile]]],
    all_rows: list[dict] | None = None,   # ← new optional parameter
) -> MergePlan:
    ...
    if all(s == all_col_sets[0] for s in all_col_sets):
        # Recompute profiles over ALL rows combined for accurate stats
        all_profiles = self.profile_columns(all_rows) if all_rows is not None else file_profiles[0][1]
        return MergePlan(strategy="union", confidence=0.92, column_profiles=all_profiles)
```

Updated the call site in `tasks.py` to pass the accumulated rows:

```python
# tasks.py — run_ingest_pipeline()
all_rows: list[dict] = []   # accumulates rows from every file
...
for filename, path in zip(...):
    rows = ingestion.parse_content(fmt, content)
    file_profiles.append((filename, profiles))
    all_rows.extend(rows)      # ← rows from each file added here

merge_plan = ingestion.propose_merge_plan(file_profiles, all_rows)  # ← passed in
```

**Important:** The `supervisor.py` call site was NOT changed because it only ever handles single-file datasets (always takes the `len == 1` branch). The `all_rows` parameter is optional with a `None` default for backward compatibility with the supervisor and tests.

---

## 6. Frontend — Type System Fixes

The frontend had types that did not match the real backend Pydantic schemas. This caused runtime crashes when API responses were received.

### 6.1 `frontend/types/pipeline.ts`

This file is the single source of truth for all pipeline-related TypeScript types. It was rewritten twice during this work.

**HITL #1 types fixed (MergePlan mismatch):**

Old incorrect shape assumed `plan.files[]` grouping (files array, nested column schemas). Real backend sends a flat list of column profiles:

```typescript
// BEFORE (wrong — crashed with "Cannot read properties of undefined (reading 'length')")
interface FileSchema { filename: string; columns: ColumnSchema[] }
interface MergePlan { files: FileSchema[]; ... }  // ← doesn't exist in backend

// AFTER (correct — matches backend/app/models/schemas.py: MergePlan)
export interface ColumnProfile {
  name: string
  dtype: string
  null_count: number
  distinct_count: number
  avg_length: number | null
  classification: ColumnClassification   // 'numeric' | 'textual' | 'ambiguous'
}
export interface MergePlan {
  strategy: 'single' | 'union' | 'join' | 'separate'
  join_key: string | null
  confidence: number
  column_profiles: ColumnProfile[]   // ← flat list, not nested by file
}
```

**HITL #2 types fixed (CleaningPlan mismatch):**

```typescript
// BEFORE (wrong — used 'actions', 'id', 'title' — none exist in backend)
interface CleaningAction { id: string; type: ...; title: string; ... }
interface CleaningPlan { dataset_id: string; actions: CleaningAction[]; ... }

// AFTER (correct — matches backend/app/models/schemas.py: CleaningStep, CleaningPlan)
export interface CleaningStep {
  step_id: number        // integer, not string
  action: 'deduplicate' | 'impute' | 'coerce_type' | 'flag_outlier'
  column: string | null  // which column is affected (null for dedup)
  method: string         // human-readable description of the method
  rationale: string      // why this step is proposed
  confidence: number
  rows_affected: number
  before_sample: Record<string, any> | null
  after_sample: Record<string, any> | null
}
export interface CleaningPlan {
  steps: CleaningStep[]         // 'steps', not 'actions'
  total_rows_before: number
  total_rows_after: number
}
```

### 6.2 `frontend/types/api.ts`

Holds request/response types for API calls. Two interfaces were fixed:

**MergePlanDecision** (updated to include all backend fields):

```typescript
// Matches backend/app/models/schemas.py: MergePlanDecision
export interface MergePlanDecision {
  approved: boolean
  merge_strategy_override?: string | null   // user-chosen strategy override
  join_key_override?: string | null          // user-chosen join key override
  excluded_columns?: string[]               // columns to drop
  type_routing_overrides?: Record<string, string>  // column → 'numeric'|'textual'
}
```

**CleaningDecision → CleaningPlanDecision** (renamed and reshaped):

```typescript
// BEFORE (wrong shape — backend doesn't accept this)
interface CleaningDecision {
  step_id: string
  status: 'approved' | 'modified' | 'rejected'
  override: string | null
}

// AFTER (correct — matches backend/app/models/schemas.py: CleaningPlanDecision)
export interface CleaningPlanDecision {
  approved_step_ids: number[]                       // list of step_ids user approved
  step_modifications: Record<number, Record<string, any>>  // optional per-step overrides
}
```

---

## 7. Frontend — HITL Checkpoint #1: Schema & Merge Validation

### 7.1 `app/(user)/validate/[id]/page.tsx`

This is the HITL #1 review page. It fetches the merge plan, shows the schema table and merge proposal, and submits the user's decision.

**Key state variables:**

| State | Type | Purpose |
|-------|------|---------|
| `plan` | `MergePlan \| null` | The merge plan fetched from the backend |
| `typeOverrides` | `Record<string, string>` | Per-column classification overrides chosen by the user |
| `excludedColumns` | `string[]` | Columns the user has unchecked (excluded from the dataset) |
| `strategy` | `string \| null` | Effective merge strategy (defaults to `plan.strategy`, overridable) |
| `joinKey` | `string \| null` | Effective join key (for JOIN strategy) |
| `saving` | `boolean` | Prevents double-submit while API call is in progress |
| `error` | `string \| null` | Displays backend error detail if submission fails |

**Key functions:**

```typescript
// Resets join key when strategy changes away from 'join'
const handleStrategyChange = (next: string) => {
  setStrategy(next)
  if (next !== 'join') setJoinKey(null)
}

// Handles both approve (approved=true) and reject (approved=false) paths
const submitDecision = async (approved: boolean) => {
  await api.post(`/datasets/${id}/merge-plan/decision`, {
    approved,
    merge_strategy_override: strategy !== plan.strategy ? strategy : null,
    join_key_override: joinKey,
    excluded_columns: excludedColumns,
    type_routing_overrides: typeOverrides,
  })
  router.push(approved ? `/clean/${id}` : '/')
}
```

**Decision logic:**
- `merge_strategy_override` is only sent when the user has changed it from the agent's recommendation (avoids sending a no-op override)
- On **Confirm**: redirects to `/clean/${id}` (cleaning plan review)
- On **Reject & start over**: posts `approved: false` → backend resets dataset status to `"uploaded"` → redirects to `/` (upload page)

---

### 7.2 `components/user/SchemaTable.tsx`

Displays a table of column profiles with per-column controls.

**Props:**

| Prop | Type | Purpose |
|------|------|---------|
| `columns` | `ColumnProfile[]` | Array of column profiles from backend |
| `excludedColumns` | `string[]` | Which columns are currently excluded (controlled from parent) |
| `onClassificationChange` | `(col, classification) => void` | Called when user changes a column's type dropdown |
| `onExcludeToggle` | `(col, excluded) => void` | Called when user checks/unchecks the include checkbox |

**Columns rendered:**

| Column header | What it shows |
|---------------|--------------|
| *(checkbox)* | Include/exclude toggle; unchecked rows dim to 50% opacity, classification dropdown disables |
| Column | Column name in monospace font |
| Type | dtype from backend (float, text, categorical, etc.) |
| Nulls | Count of null/empty values |
| Distinct | Count of unique values |
| Avg length | Average string length rounded to 2 decimal places; `—` if null (numeric columns) |
| Classification | Dropdown: numeric (blue), textual (purple), ambiguous (orange) |

**Confidence colour map for classification badges:**

```typescript
const CLASSIFICATION_COLOURS = {
  numeric:   'bg-blue-50 text-blue-700',
  textual:   'bg-purple-50 text-purple-700',
  ambiguous: 'bg-orange-50 text-orange-700',
}
```

---

### 7.3 `components/user/MergeProposal.tsx`

Displays the agent's proposed merge strategy with a colour-coded confidence badge, and lets the user override both the strategy and the join key.

**Props:**

| Prop | Type | Purpose |
|------|------|---------|
| `plan` | `MergePlan` | The full merge plan (used for confidence + column list for join-key dropdown) |
| `strategy` | `string` | Currently selected strategy (controlled from parent) |
| `joinKey` | `string \| null` | Currently selected join key (controlled from parent) |
| `onStrategyChange` | `(strategy) => void` | Called when user picks a different strategy |
| `onJoinKeyChange` | `(joinKey) => void` | Called when user picks a different join key |

**Strategy options:**

| Value | Label |
|-------|-------|
| `single` | Single file — no merge needed |
| `union` | UNION — stack rows from all files |
| `join` | JOIN — combine files on a shared key |
| `separate` | Separate — keep files independent |

**Confidence badge colours:**

| Score range | Badge colour | Meaning |
|-------------|-------------|---------|
| ≥ 0.90 | Green | High confidence |
| 0.70–0.89 | Yellow | Medium confidence |
| 0.50–0.69 | Orange | Low confidence |
| < 0.50 | Red | Very low confidence |

**Behaviour notes:**
- The merge-key dropdown (`<select>`) only appears when the effective strategy is `join`
- When the user overrides strategy away from `join`, the join key resets to `null`
- A "(recommended: X)" hint appears next to the dropdown when the user has overridden the agent's original recommendation

---

## 8. Frontend — HITL Checkpoint #2: Cleaning Plan Review

### 8.1 `app/(user)/clean/[id]/page.tsx`

The HITL #2 review page. Fetches the cleaning plan, shows numbered steps with confidence indicators, and submits the user's approve/reject decisions.

**Key state variables:**

| State | Type | Purpose |
|-------|------|---------|
| `plan` | `CleaningPlan \| null` | Cleaning plan fetched from backend |
| `approvedIds` | `Set<number>` | Set of `step_id`s the user has approved |
| `pollAttempts` | `number` | Tracks how many polling retries have occurred |
| `saving` | `boolean` | Prevents double-submit |
| `error` | `string \| null` | Backend error detail on failure |

**Pre-checking logic (confidence framework):**

Steps are automatically pre-checked or unchecked based on confidence when the plan loads:

```typescript
function initialApproved(steps: CleaningStep[]): Set<number> {
  // Pre-check all steps with confidence >= 0.70
  return new Set(steps.filter((s) => s.confidence >= 0.7).map((s) => s.step_id))
}
```

| Confidence | Initial state | Badge colour | Left border |
|------------|--------------|-------------|-------------|
| ≥ 0.90 | Pre-checked | Green | None |
| 0.70–0.89 | Pre-checked | Yellow | Yellow left border |
| 0.50–0.69 | Unchecked | Orange | Orange left border |
| < 0.50 | Unchecked | Red | Red left border + warning text |

**Per-step toggle:**

```typescript
const toggle = (stepId: number) => {
  setApprovedIds((prev) => {
    const next = new Set(prev)
    next.has(stepId) ? next.delete(stepId) : next.add(stepId)
    return next
  })
}
```

**Decision payload submitted:**

```typescript
await submitCleaningDecisions(id, {
  approved_step_ids: [...approvedIds],   // converts Set<number> to number[]
  step_modifications: {},                 // reserved for future per-step overrides
})
```

**Step card UI elements:**

Each step card displays:
1. Step number (circular badge)
2. Action label (e.g., "Fix data type", "Fill missing values")
3. Affected column name in monospace code pill (if applicable)
4. Confidence percentage badge (colour-coded)
5. Rationale paragraph
6. Method and rows_affected on the same line
7. Warning text for very low confidence (< 0.50)
8. Approve checkbox (right-aligned)

Unchecked cards dim to 50% opacity.

---

### 8.2 Polling Mechanism

**The problem:** When the user confirms HITL #1, the validate page immediately redirects to `/clean/{id}`. But the cleaning plan agent runs asynchronously in the background — it takes a few seconds. The GET `/datasets/{id}/cleaning-plan` endpoint returns HTTP 409 ("Cleaning plan not ready yet") until the agent finishes.

Without polling, the page tries to fetch once, gets a 409, silently swallows the error, and shows "Loading cleaning plan…" forever. The user has to manually refresh.

**The solution — interval-based polling:**

```typescript
const pollerRef = useRef<ReturnType<typeof setInterval> | null>(null)

useEffect(() => {
  const tryFetch = () => {
    getCleaningPlan(id)
      .then((r) => {
        // Plan is ready — stop polling and render
        if (pollerRef.current) {
          clearInterval(pollerRef.current)
          pollerRef.current = null
        }
        setPlan(r.data)
        setApprovedIds(initialApproved(r.data.steps))
      })
      .catch(() => {
        // 409 = not ready yet; increment counter and keep polling
        setPollAttempts((n) => n + 1)
      })
  }

  tryFetch()                                        // immediate first attempt
  pollerRef.current = setInterval(tryFetch, 3000)  // retry every 3 seconds

  return () => {
    if (pollerRef.current) clearInterval(pollerRef.current) // cleanup on unmount
  }
}, [id])
```

**Why `useRef` for the interval?**

`useRef` stores a mutable value that persists across re-renders without triggering a re-render itself. This is the correct pattern for holding a timer ID — using `useState` would cause unnecessary re-renders on every poll, and a plain variable would lose its value on re-render.

**Why `clearInterval` in the cleanup function?**

If the user navigates away from the page before the plan loads, the cleanup function (returned from `useEffect`) fires and cancels the interval. Without this, the interval would keep running in the background and try to call `setPlan` on an unmounted component, causing a React memory leak warning.

---

## 9. Frontend — Shared Infrastructure

### 9.1 `lib/pipelineApi.ts`

Centralises all pipeline-related API calls. Updated to fix incorrect types and payload shapes.

**Key functions:**

```typescript
// HITL #1
export const getMergePlan = (datasetId: string) =>
  api.get(`/datasets/${datasetId}/merge-plan`)

export const confirmMerge = (datasetId: string, d: MergePlanDecision) =>
  api.post(`/datasets/${datasetId}/merge-plan/decision`, d)

// HITL #2
export const getCleaningPlan = (datasetId: string) =>
  api.get(`/datasets/${datasetId}/cleaning-plan`)

export const submitCleaningDecisions = (datasetId: string, body: CleaningPlanDecision) =>
  api.post(`/datasets/${datasetId}/cleaning-plan/decision`, body)  // flat body, no wrapper
```

**Critical fix — removed `{ decisions: [...] }` wrapper:**

The old `submitCleaningDecisions` was wrapping the payload in `{ decisions: [...] }`. The backend endpoint expects the `CleaningPlanDecision` body directly at the top level with `approved_step_ids` and `step_modifications`. Removing the wrapper fixed the 422 Unprocessable Entity error.

---

### 9.2 `next.config.js`

**The problem:** Next.js API Route Handlers (files in `app/api/...`) and the backend rewrite (`/api/v1/*` → `http://localhost:8000/api/v1/*`) were conflicting. When rewrites are specified as a plain array, Next.js applies them via `beforeFiles` semantics — which runs before checking local Route Handlers. This caused local mock routes to be bypassed.

**The fix — use `afterFiles` form:**

```javascript
async rewrites() {
  return {
    afterFiles: [   // ← "afterFiles" runs AFTER Next.js checks local routes
      {
        source: "/api/v1/:path*",
        destination: `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/v1/:path*`,
      },
    ],
  }
}
```

**Rewrite precedence order in Next.js:**

1. `beforeFiles` — runs before filesystem routes (would override local routes)
2. Filesystem routes — Next.js checks local pages/Route Handlers
3. `afterFiles` — runs after filesystem routes (local routes take precedence)
4. `fallback` — runs only if no route matched at all

Using `afterFiles` ensures any locally-defined `/api/v1/...` Route Handler takes precedence over the rewrite, while still proxying all other `/api/v1/...` calls to the FastAPI backend.

---

## 10. Upload Page Bug Fix

**File:** `frontend/app/(user)/page.tsx`

**The bug:** After a file was uploaded and the pipeline ran to completion, the upload page never redirected to the validate page. It just sat there showing "Pipeline: complete — awaiting_hitl_merge".

**Root cause:** The page was checking `job.status === "awaiting_hitl_merge"` to decide when to redirect. But the `status` field only ever holds lifecycle values: `queued`, `running`, `complete`, `error`. The pipeline stage lives in a completely separate field: `job.current_step`.

```typescript
// BEFORE (wrong — 'awaiting_hitl_merge' is never in job.status)
const TERMINAL_STATUSES = ['awaiting_hitl_merge', 'complete', 'error']
if (TERMINAL_STATUSES.includes(job.status)) { ... }

// AFTER (correct — check job.current_step for the pipeline stage)
const TERMINAL_STEPS = ['awaiting_hitl_merge']
const jobFailed = job.status === 'error'
const stepIsTerminal = job.current_step !== null && TERMINAL_STEPS.includes(job.current_step)

if (jobFailed || stepIsTerminal) {
  clearInterval(pollerRef.current)
  if (job.current_step === 'awaiting_hitl_merge') {
    window.location.href = `/validate/${dataset_id}`   // redirect to HITL #1
  } else if (jobFailed) {
    setError(job.error ?? 'Pipeline failed.')
  }
}
```

**Key distinction to remember:**

| Field | Example values | What it means |
|-------|---------------|----------------|
| `job.status` | `"queued"`, `"running"`, `"complete"`, `"error"` | Is the background worker running? |
| `job.current_step` | `"awaiting_hitl_merge"`, `"awaiting_hitl_cleaning"` | What stage is the pipeline at? |

---

## 11. Test Data Files

Two CSV files were created for end-to-end testing. They have identical schemas (8 columns) for UNION merge testing.

### `test_healthcare.csv` (10 rows — patients P001–P010, February 2024)

```
patient_id, patient_name, diagnosis, admission_date, discharge_date,
length_of_stay_days, readmitted, notes
```

### `test_healthcare_2.csv` (10 rows — patients P011–P020, March 2024)

Same 8 columns as above, different patients and dates.

**Location:** `C:\Users\PriyankaKoujalagi\Documents\EURON\DataMindAI\`

**Use cases:**

| Test | Files to upload |
|------|----------------|
| Single-file flow | `test_healthcare.csv` only |
| UNION merge flow | Both files together in one upload batch |
| Column classification | Either file — verifies free-text columns show `textual` |
| Confidence badge colours | Either file — cleaning plan steps include 95%, 90%, 85% steps |

---

## 12. Confidence Score Framework

All agent outputs carry a confidence score (0.0–1.0). The frontend renders these consistently across HITL #1 and HITL #2:

| Range | Interpretation | Badge colour | HITL #2 pre-check | Left border |
|-------|----------------|-------------|-------------------|-------------|
| 0.90–1.00 | High confidence | Green | Pre-checked | None |
| 0.70–0.89 | Medium confidence | Yellow | Pre-checked | Yellow |
| 0.50–0.69 | Low confidence | Orange | Unchecked | Orange |
| 0.00–0.49 | Very low confidence | Red | Unchecked + warning | Red |

---

## 13. Data Type Classification Rules

Defined in `backend/app/agents/ingestion.py`:

```python
MAX_CARDINALITY_FOR_STRUCTURED = 50    # ≤50 distinct values → numeric/categorical
MIN_AVG_LENGTH_FOR_TEXTUAL = 40        # avg length ≥40 chars → textual
```

**Classification algorithm (correct order after fix):**

```
1. Calculate numeric_ratio = (values that parse as float) / (total non-null values)
2. Calculate avg_length = average character length of non-numeric string values

3. if numeric_ratio >= 0.9:
       → "numeric" (dtype: float)
   elif avg_length >= 40 OR distinct_count > 50% of rows:
       → "textual" (dtype: text)
   elif distinct_count <= 50:
       → "numeric" (dtype: categorical)
   else:
       → "ambiguous" (dtype: text)
```

**Important known behaviour:** Date columns (e.g., `admission_date: "2024-02-01"`) are not parsed as dates by the current classifier — they fail the float check and fall into the textual/distinct-ratio check. With typical small datasets where dates are mostly unique, they often classify as `textual`. This is a known limitation and is acceptable for Phase 1; per CLAUDE.md, users can override classification via the dropdown in HITL #1.

---

## 14. API Contract Reference

### HITL #1 Endpoints

#### `GET /api/v1/datasets/{dataset_id}/merge-plan`

**Returns:** `MergePlan`

```json
{
  "strategy": "single",
  "join_key": null,
  "confidence": 0.99,
  "column_profiles": [
    {
      "name": "patient_id",
      "dtype": "text",
      "null_count": 0,
      "distinct_count": 10,
      "avg_length": 4.0,
      "classification": "textual"
    }
  ]
}
```

**Status guard:** Returns HTTP 409 if dataset status is not `awaiting_hitl_merge`.

#### `POST /api/v1/datasets/{dataset_id}/merge-plan/decision`

**Body:** `MergePlanDecision`

```json
{
  "approved": true,
  "merge_strategy_override": null,
  "join_key_override": null,
  "excluded_columns": ["notes"],
  "type_routing_overrides": { "patient_id": "numeric" }
}
```

**Returns:** `{ "job_id": "...", "status": "queued" }` (triggers cleaning plan agent)

**If `approved: false`:** Dataset status resets to `"uploaded"`, no job started.

---

### HITL #2 Endpoints

#### `GET /api/v1/datasets/{dataset_id}/cleaning-plan`

**Returns:** `CleaningPlan`

```json
{
  "steps": [
    {
      "step_id": 1,
      "action": "coerce_type",
      "column": "admission_date",
      "method": "Parse string to datetime format YYYY-MM-DD",
      "rationale": "The admission_date is stored as text...",
      "confidence": 0.95,
      "rows_affected": 20,
      "before_sample": null,
      "after_sample": null
    }
  ],
  "total_rows_before": 20,
  "total_rows_after": 20
}
```

**Status guard:** Returns HTTP 409 if dataset status is not `awaiting_hitl_cleaning`.

#### `POST /api/v1/datasets/{dataset_id}/cleaning-plan/decision`

**Body:** `CleaningPlanDecision`

```json
{
  "approved_step_ids": [1, 2, 3],
  "step_modifications": {}
}
```

**Returns:** `{ "job_id": "...", "status": "queued" }` (triggers cleaning executor)

---

## 15. End-to-End Flow Walkthrough

This section walks through the full HITL #1 + HITL #2 flow as tested manually.

### Step 1 — Upload

1. Navigate to `/` (upload page)
2. Select domain: **Healthcare**
3. Drag and drop `test_healthcare.csv` (or both files for UNION test)
4. Upload progress bar reaches 100%, "Pipeline: running" shown
5. Page polls `GET /jobs/{job_id}` every 2 seconds
6. When `job.current_step === "awaiting_hitl_merge"`, auto-redirects to `/validate/{dataset_id}`

### Step 2 — HITL #1 (Validate Page)

1. Page fetches `GET /datasets/{id}/merge-plan`
2. Schema table renders with 8 columns, each with type/nulls/distinct/avg-length/classification
3. Merge proposal shows: **Single file — no merge needed** (99% confidence, green badge)
4. User can:
   - Uncheck columns to exclude them
   - Change classification dropdown (numeric/textual/ambiguous)
   - Change strategy dropdown (to JOIN/UNION/separate)
   - If JOIN: select merge key from dropdown
5. Click **Confirm & proceed to cleaning** → POSTs decision → redirects to `/clean/{dataset_id}`
6. Click **Reject & start over** → POSTs `approved: false` → redirects to `/` (upload page)

### Step 3 — HITL #2 (Cleaning Page)

1. Page starts polling `GET /datasets/{id}/cleaning-plan` every 3 seconds
2. Initially returns 409 (backend is running cleaning plan agent)
3. After ~5–10 seconds, plan is ready — poller detects success, stops polling, renders plan
4. Steps shown (from actual test with healthcare data):
   - Step 1: Fix data type — `admission_date` — 95% (green)
   - Step 2: Fix data type — `discharge_date` — 95% (green)
   - Step 3: Fix data type — `readmitted` — 90% (green)
   - Step 4: Fill missing values — `notes` — 85% (yellow)
5. All 4 pre-checked (all ≥ 0.70). HITL banner shows "4 of 4 steps approved"
6. User can uncheck individual steps to reject them
7. Submit button shows count: "Submit 4 approved steps"
8. Click Submit → POSTs `{ approved_step_ids: [1,2,3,4], step_modifications: {} }`
9. Backend runs `run_cleaning_executor_pipeline` for approved steps
10. Redirects to `/intent/{dataset_id}` (intent capture — next task to build)

---

## 16. Known Limitations & Future Work

### Currently Out of Scope (Phase 1 → Phase 2)

| Item | Status |
|------|--------|
| Date-string detection in column classifier | Known gap — dates classify as textual; user can override in HITL #1 |
| Intent capture page (`/intent/[id]`) | Not yet built — redirect from clean page is a TODO |
| Dashboard page | Not yet built |
| Reject path for HITL #2 | No formal "Reject all & restart" button on cleaning page |
| Step modification | `step_modifications` field in payload is reserved but UI for it not built |
| Polling timeout on cleaning page | Poller runs indefinitely — should stop after N attempts and show an error |

### Pending Next Tasks (HITL #3 onwards)

1. Build intent capture page (`/intent/[id]`) — HITL #3
2. Build dashboard generation page
3. Build insights/narrative display
4. Admin UI (user management, LLM config, audit log)
5. End-to-end integration tests across all HITL checkpoints

---

*Document generated: June 2026. Covers work from project sessions on 2026-06-16 and 2026-06-17.*
*Branch: `Priyanka-K/feat-backend`*
