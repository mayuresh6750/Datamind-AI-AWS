---
name: enterprise-ai
description: Use when someone asks how to build enterprise AI systems, pick the right agent for a task, combine agents and skills, structure an AI project, or needs a decision guide for the full Euron stack. Also use for architecture planning, guardrail setup, compliance patterns, or any question about which tool to reach for.
argument-hint: "[task or domain description]"
---

# Enterprise AI Development Guide

Master guide for building production-grade AI systems using the full Euron stack — agents, skills, coding rules, and compliance patterns.

## When to Use This Skill

- "How should I structure this AI project?"
- "Which agent should I use for X?"
- "How do I add security to my AI agent?"
- "I need to build a RAG system / multi-agent pipeline / database agent"
- "What's the right pattern for [enterprise scenario]?"
- "Help me plan this feature end-to-end"

---

## Step 1: Understand the Task

Before selecting tools, classify the request:

| Category | Examples | Primary Tools |
|----------|---------|--------------|
| Backend API | CRUD, auth, webhooks, services | `backend-builder` agent |
| Frontend UI | Pages, components, forms, dashboards | `frontend-builder` agent |
| Database | Schema design, migrations, RLS, queries | `db-architect` agent |
| AI Agent | RAG, tool-calling, multi-agent, planner | `backend-builder` + `guardrail-pipeline` skill |
| Security | Audit, hardening, OWASP scan | `security-auditor` agent |
| Deployment | Docker, Vercel, Modal, AWS | `deployer` agent + `modal-deploy` skill |
| Testing | Test coverage, missing tests, CI | `test-runner` agent |
| Integrations | OAuth, webhooks, third-party APIs | `api-integrator` agent |
| MCP servers | Connect Claude to databases/APIs | `mcp-builder` agent |
| Code review | Pre-merge review, PASS/FAIL | `code-reviewer` agent |
| New skill | Automate a workflow | `skill-builder` skill |

---

## Step 2: Agent Selection Decision Tree

```
Is the task primarily...

 Code generation (API, UI, DB)?
 └─ What layer?
  ├─ Backend Python/FastAPI → backend-builder (Opus)
  ├─ Frontend Next.js/React → frontend-builder (Sonnet)
  └─ Database schema/migrations → db-architect (Sonnet)

 Security / audit?
 └─ security-auditor (Opus) — OWASP, secrets, prompt injection

 Testing?
 └─ test-runner (Sonnet) — write + run tests

 Deployment / DevOps?
 └─ deployer (Sonnet) + modal-deploy skill for serverless

 Integration with external service?
 └─ api-integrator (Sonnet) — OAuth, REST, GraphQL, webhooks

 Build an MCP server?
 └─ mcp-builder (Sonnet)

 Research / explore codebase?
 └─ researcher (Sonnet)

 Review code before merging?
 └─ code-reviewer (Opus) — gives PASS or FAIL verdict
```

---

## Step 3: Enterprise AI Project Blueprint

For any full enterprise AI project, set up in this order:

### Phase 1 — Foundation
1. Write `docs/PRD.md` — requirements, users, modules, milestones
2. Write `docs/ARCHITECTURE.md` — layers, data flow, multi-tenancy decisions
3. Write `docs/DB_SCHEMA.md` — tables, columns, indexes, RLS policies
4. Use `db-architect` agent to implement schema with migrations

### Phase 2 — Backend
1. Use `backend-builder` agent to scaffold FastAPI service
 - Routes → Services → Repositories (3-layer architecture)
 - Pydantic v2 schemas for all I/O
 - Async I/O, dependency injection, health endpoint
2. Add Redis caching layer for expensive queries
3. Write `docs/API_SPEC.md` documenting all endpoints

### Phase 3 — AI Layer
1. Build RAG pipeline as a separate module:
 - Ingestion service (chunking, embedding, metadata)
 - Retrieval service (vector search, reranking)
 - Generation service (prompt assembly, LLM call)
2. Build agent orchestration:
 - Tool definitions (input schema, output schema, failure handling)
 - Planner/executor separation
 - Structured output validation
3. Apply `guardrail-pipeline` skill if agent touches sensitive data

### Phase 4 — Frontend
1. Use `frontend-builder` agent to build Next.js UI
 - TypeScript throughout
 - Centralized API client (no hardcoded URLs)
 - Loading / error / empty states for every data-fetching view

### Phase 5 — Security & Compliance
1. Run `security-auditor` agent on the full codebase
2. Apply guardrail pipeline to all agent endpoints
3. Add rate limiting to public endpoints
4. Verify RLS policies on all multi-tenant tables
5. Confirm `.env.example` covers all secrets, no real values committed

### Phase 6 — Deployment
1. Use `deployer` agent for Vercel (frontend) + Modal (backend) setup
2. Configure GitHub Actions CI: lint → test → build → deploy
3. Set all env vars in deployment dashboards
4. Add monitoring and health check alerts

---

## Core Patterns

### 3-Layer Architecture (non-negotiable)
```python
# Route — HTTP only
@router.post("/users")
async def create_user(body: CreateUserSchema, svc: UserService = Depends()):
 return await svc.create_user(body)

# Service — business logic
class UserService:
 async def create_user(self, data: CreateUserSchema) -> UserSchema:
  # validation, hashing, business rules
  return await self.repo.create(data)

# Repository — DB access only
class UserRepository:
 async def create(self, data: CreateUserSchema) -> UserSchema:
  # SQL / ORM only
```

### Multi-Tenant Guard (all queries)
```python
# Every repository query must filter by organization_id
async def get_records(self, org_id: UUID) -> list[Record]:
 return await db.execute(
  select(Record).where(Record.organization_id == org_id)
 )
```

### Agent Tool Schema Pattern
```python
# Every tool must have input schema, output schema, failure behavior
class SearchTool(BaseTool):
 name = "search_documents"
 description = "Search documents for relevant content"
 args_schema = SearchInput # Pydantic model
 
 async def _arun(self, query: str, org_id: str) -> SearchOutput:
  # validate inputs, execute, return typed output
  # log the call
  # handle failures explicitly
```

### Structured API Error Response
```python
# Consistent across ALL endpoints
raise HTTPException(
 status_code=400,
 detail={
  "error": "VALIDATION_ERROR",
  "code": "USER_EMAIL_TAKEN",
  "message": "An account with this email already exists",
  "details": {"field": "email"}
 }
)
```

### RAG Pipeline Separation
```
rag/
 ingestion/
 chunker.py  # Split documents into chunks
 embedder.py  # Generate embeddings
 indexer.py  # Store in vector DB with metadata
 retrieval/
 searcher.py  # Vector similarity search
 reranker.py  # Optional reranking step
 generation/
 prompter.py  # Assemble context + question into prompt
 generator.py  # LLM call + response parsing
```

---

## Guardrail Pipeline — When to Apply

Apply the `guardrail-pipeline` skill whenever:
- Agent queries a database (any type)
- Agent handles PII, financial data, or medical records
- Multi-role access (students vs. admins, customers vs. agents)
- Compliance requirements: HIPAA, PCI DSS, SOX, GDPR, SOC 2

```
/guardrail-pipeline university ["student", "admin", "viewer"] ["students", "courses", "transactions"]
```

This scaffolds all 6 layers in `guardrails/` + monitoring table + `GuardedAgent` class.

---

## Skill Combinations for Common Scenarios

### University AI Assistant
1. `db-architect` → design students/courses/transactions schema with RLS
2. `backend-builder` → FastAPI + LangChain ReAct agent
3. `/guardrail-pipeline university ["student","admin"] ["students","courses","transactions"]`
4. `frontend-builder` → Streamlit or Next.js chat interface
5. `security-auditor` → audit before go-live

### Banking / FinTech Agent
1. `db-architect` → accounts/transactions/loans schema, PCI DSS patterns
2. `backend-builder` → FastAPI + compliance-aware agent
3. `/guardrail-pipeline banking ["customer","agent","admin","auditor"] ["accounts","transactions","loans"]`
4. `api-integrator` → Plaid/Stripe/payment webhooks
5. `deployer` → AWS with VPC isolation

### SaaS Multi-Tenant Platform
1. `db-architect` → org-scoped schema, RLS by `organization_id`
2. `backend-builder` → FastAPI with tenant middleware
3. `frontend-builder` → Next.js with org context
4. `deployer` → Vercel + Supabase
5. `security-auditor` → SOC 2 readiness audit

### Internal Enterprise Chatbot
1. `backend-builder` → RAG pipeline on internal docs
2. `/guardrail-pipeline [company] [roles] [allowed_tables]` → RBAC on data access
3. `mcp-builder` → Connect to internal tools (Jira, Confluence, Slack)
4. `frontend-builder` → Chat UI
5. `security-auditor` → Prompt injection + data leakage audit

---

## Output

After analyzing the task ($ARGUMENTS), provide:

1. **Recommended approach** — which agents/skills to use and in what order
2. **Architecture diagram** — layered structure for this specific use case
3. **Setup sequence** — ordered steps from project init to deployment
4. **Key guardrails** — security/compliance requirements for the domain
5. **Reference patterns** — specific code patterns for the stack

Keep recommendations concrete and actionable. Reference specific agent names and skill commands. Point to `skills and agents/` subdirectories for examples.

---

## DataMind AI — Data Intelligence Platform Patterns

Use these patterns when building agentic data intelligence systems: platforms that ingest raw business files, clean them with human approval, type-route data to the right store, and generate domain-aware dashboards.

---

### Pattern 1 — HITL Pipeline (Human-in-the-Loop Agentic Pipeline)

The core pattern for any agent pipeline that mutates user data. Agents PROPOSE, users DISPOSE, then agents EXECUTE.

```python
# Phase 2 orchestration scaffold (supervisor.py) — two-phase gate per destructive step
# Phase 1 uses HTTP-driven HITL between tasks.py pipeline functions
from langgraph.graph import StateGraph

class PipelineState(BaseModel):
 dataset_id: str
 cleaning_plan: CleaningPlan | None = None
 hitl_decision: HITLDecision | None = None
 status: PipelineStatus = PipelineStatus.RUNNING

def cleaning_plan_node(state: PipelineState) -> PipelineState:
 # Agent PROPOSES — generates plan but NEVER executes
 plan = cleaning_plan_agent.generate(state.dataset_id)
 state.cleaning_plan = plan
 state.status = PipelineStatus.AWAITING_HITL_CLEANING
 # Persist state to Supabase Database + Supabase Storage before pausing
 persist_pipeline_state(state)
 return state

def hitl_gate(state: PipelineState) -> str:
 # Phase 2 conditional edge — pause until user decision is posted
 if state.status == PipelineStatus.AWAITING_HITL_CLEANING:
  return "wait"  # worker releases; state stored in DB
 return "execute"

def cleaning_execute_node(state: PipelineState) -> PipelineState:
 # Agent executes ONLY the steps the user approved
 for step in state.hitl_decision.approved_steps:
  cleaning_executor.run(step, state.dataset_id)
  audit_log.append(step, user_decision=state.hitl_decision)
 return state
```

**Key rule**: HITL-paused state must be durably persisted to Supabase Database + Supabase Storage before the worker releases. A worker crash must not require re-running upstream agents.

---

### Pattern 2 — Type-Aware Column Routing

After ingestion, every column is classified and routed to the right store. Do not put everything in one place.

```python
from enum import Enum
from statistics import mean

class ColumnClass(Enum):
 NUMERIC_STRUCTURED = "numeric_structured"
 TEXTUAL_SEMANTIC = "textual_semantic"
 AMBIGUOUS   = "ambiguous"

def classify_column(values: list) -> ColumnClass:
 # (a) All-numeric or all-date typed values
 if all(isinstance(v, (int, float, bool)) for v in values if v is not None):
  return ColumnClass.NUMERIC_STRUCTURED

 # (b) String-like values that mostly parse as numeric/date
 str_values = [v for v in values if isinstance(v, str) and v]
 if str_values:
  parseable = sum(1 for v in str_values if _try_parse_numeric_or_date(v)) / len(str_values)
  if parseable >= 0.95:
   return ColumnClass.NUMERIC_STRUCTURED

  # (c) Low-cardinality categorical
  distinct = len(set(str_values))
  avg_len = mean(len(v) for v in str_values)
  if distinct <= 50 and avg_len <= 40:
   return ColumnClass.NUMERIC_STRUCTURED

  # (d) Free-text (high-cardinality, long strings)
  distinct_ratio = distinct / max(len(str_values), 1)
  if avg_len > 40 and distinct_ratio > 0.50:
   return ColumnClass.TEXTUAL_SEMANTIC

 # (e) Ambiguous — surface to user at HITL #1
 return ColumnClass.AMBIGUOUS

def route_columns(data: dict[str, list]) -> dict[str, ColumnClass]:
 return {col: classify_column(values) for col, values in data.items()}
```

- `NUMERIC_STRUCTURED` → write to PostgreSQL typed table + JSON metadata
- `TEXTUAL_SEMANTIC` → embed with Qwen3-Embedding-0.6B (sentence-transformers, self-hosted) → store in Supabase Vector (pgvector, HNSW index, per-tenant schema)
- `AMBIGUOUS` → present to user at HITL #1; honour their choice

---

### Pattern 3 — LLM Provider Abstraction

Never hardcode a provider. Every agent calls a thin abstraction that resolves the active provider from tenant config.

```python
from pydantic import BaseModel
from typing import TypeVar, Type

T = TypeVar("T", bound=BaseModel)

class LLMClient:
 def __init__(self, tenant_id: str):
  self.config = LLMProviderConfig.for_tenant(tenant_id)

 async def structured_completion(
  self,
  schema: Type[T],
  prompt: str,
  agent_name: str,
  provider_override: str | None = None,
 ) -> T:
  provider = provider_override or self.config.provider_for_agent(agent_name)
  model = self.config.model_for_agent(agent_name)

  raw = await self._call_provider(provider, model, prompt)

  # Validate against Pydantic schema regardless of provider
  try:
   return schema.model_validate_json(raw)
  except ValidationError:
   # Retry up to 3 times, then raise pipeline failure
   raise LLMSchemaValidationFailed(agent=agent_name, provider=provider)

 async def _call_provider(self, provider: str, model: str, prompt: str) -> str:
   # Route to Google Gemini 3.5 Flash (P1) or additional LiteLLM-compatible providers (P2)
   ...
```

**Invariant**: every agent must pass its CI suite against ALL configured providers — a failure on one provider blocks merge.

---

### Pattern 4 — Confidence-Gated HITL Presentation

When presenting a list of agent proposals at a HITL gate, use confidence scores to drive the default UI state.

```python
from dataclasses import dataclass

@dataclass
class CleaningStep:
 action: str
 rationale: str
 confidence: float  # 0.0 – 1.0
 rows_affected: int

def get_default_checked(step: CleaningStep) -> bool:
 # Pre-checked only if confidence ≥ 0.70
 return step.confidence >= 0.70

def get_confidence_badge(step: CleaningStep) -> str:
 if step.confidence >= 0.90: return "high"
 if step.confidence >= 0.70: return "medium"
 if step.confidence >= 0.50: return "low"
 return "very_low"  # mandatory explicit user decision

# Frontend renders:
# high → green badge, pre-checked
# medium → yellow badge, pre-checked
# low → orange badge, unchecked by default
# very_low → red badge, unchecked, blocking modal before approval
```

---

### Pattern 5 — SQL Safety Gate (sqlglot)

All SQL generated by LLM agents must be validated before execution. Block anything that is not a read-only SELECT.

```python
import sqlglot
from sqlglot.expressions import Select

def validate_readonly_sql(sql: str, allowed_table: str) -> None:
 try:
  statements = sqlglot.parse(sql)
 except sqlglot.errors.ParseError as e:
  raise SQLValidationError(f"Could not parse generated SQL: {e}")

 for statement in statements:
  if not isinstance(statement, Select):
   raise SQLValidationError(
    f"Only SELECT statements are allowed. Got: {type(statement).__name__}"
   )
  # Ensure query is scoped to the allowed curated table
  tables = [t.name for t in statement.find_all(sqlglot.expressions.Table)]
  if allowed_table not in tables:
   raise SQLValidationError(
    f"Query references disallowed table(s): {tables}"
   )
```

---

### Skill Combination — Data Intelligence Pipeline

Full setup sequence for a DataMind-style platform:

1. `db-architect` → design 4-layer storage schema: users (FK→auth.users), datasets, pipeline_runs, hitl_decisions, llm_provider_config; PostgreSQL + pgvector
2. `backend-builder` → FastAPI with Supabase Auth JWT validation, RBAC middleware, FastAPI BackgroundTasks job dispatch, `tasks.py` pipeline (Phase 1); `supervisor.py` scaffold for Phase 2
3. `/guardrail-pipeline datamind ["user","admin"] ["datasets","hitl_decisions","audit_events"]`
4. `frontend-builder` → Next.js dual UI (`/app/*` and `/admin/*`) with Supabase Auth SDK and domain-aware components
5. `api-integrator` → LiteLLM-compatible provider abstraction for Google Gemini 3.5 Flash (P1); Qwen3-Embedding-0.6B (sentence-transformers) for embeddings; API keys from Supabase Vault
6. `deployer` → Docker Compose + Supabase via Terraform; GitHub Actions CI/CD
7. `security-auditor` → RBAC isolation tests, Supabase Auth JWT claim handling, prompt injection audit
