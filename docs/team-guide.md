# DataMind AI — Team Member Guide

Your single starting point. Read this once, refer back any time.

---

## 1. Read these first (~15 min, in order)

| # | File | Why |
|---|---|---|
| 1 | [claude.md](claude.md) | Project context — stack, conventions, agent definitions, API design, guardrails. **Read before touching code.** |
| 2 | [planphase.md](planphase.md) | Find your role. Read the tasks for your current phase. |
| 3 | [PRD.md](PRD.md) | Product spec — when you need to know what a feature *means*. |
| 4 | [architecture.md](architecture.md) | Engineering reference — when you need to know *how* something works. |
| 5 | [errors.md](errors.md) | Known errors and resolutions — check here before raising a blocker. |

You do **not** need to memorize these. Just know where to find them.

---

## 2. Find your assignment

Open [planphase.md](planphase.md) and `Ctrl-F` your role label (e.g., "Backend", "Frontend", "AI/Agent", "QA", "Infra"). Your tasks for the current phase are listed under your area with three lines each:

> **What you build** — the work in plain English
> **Files** — the paths you'll touch
> **Done when** — the acceptance criteria

Pick the first task that has no unmet dependencies. Confirm it in your morning standup.

---

## 3. Set up your environment (Day 1, ~30 min)

```bash
# 1. Clone + switch to the integration branch
git clone <repo-url> datamind
cd datamind
git checkout development

# 2. Environment
cp .env.example .env
# → fill in the keys you need (ask team lead in #datamind-secrets)
# Required: DATABASE_URL, REDIS_URL, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY,
#   S3_RAW_BUCKET, S3_CURATED_BUCKET, ANTHROPIC_API_KEY, OPENAI_API_KEY

# 3. Python backend
uv sync       # installs every Python package in the workspace

# 4. JS workspace (Next.js frontend)
pnpm install

# 5. Local services (Postgres with pgvector + Redis)
docker compose up -d    # starts Postgres (with pgvector), Redis

# 6. Apply DB migrations
uv run alembic upgrade head  # creates users, datasets, pipeline_runs, audit_log tables

# 7. Start backend services
uv run uvicorn apps.api.main:app --reload   # FastAPI on :8000

# 8. Start frontend
pnpm --filter web dev        # Next.js on :3000

# 9. Sanity check
curl http://localhost:8000/health
# → {"status": "ok", "db": "ok"}
```

If step 9 returns OK, you're set up. Open the README in your owned folder (e.g., `apps/web/README.md`, `apps/api/README.md`, `packages/agents/README.md`) — it explains what code goes there.

---

## 4. The git workflow — branches + PRs

**Every piece of work goes on its own branch and ships via a PR to `development`. No direct pushes to `development` or `main`.**

### Branch structure

| Branch | Purpose | Direct pushes? |
|---|---|---|
| `main` | Production — what's live | **Never.** PRs from `development` only, on release. |
| `development` | Integration — what's about to be tested | **Never.** PRs from feature branches only. |
| `<your-name>/feat-<short-slug>` | Your work in progress | Yes — push freely to your own branch. |

### Branch naming convention

```
<your-name>/feat-<short-slug>  ← new feature / new code
<your-name>/fix-<short-slug>  ← bug fix
<your-name>/chore-<short-slug>  ← refactor / cleanup / docs
<your-name>/test-<short-slug>  ← test-only work
```

Use your real name (kebab-case) — `jane-doe`, not initials, not role IDs. The slug is what the work *is*, in 2–5 words.

**Examples:**

```
jane-doe/feat-auth-jwt
priya-r/feat-cleaning-plan-agent
sam-k/fix-hitl-confidence-score
ana-s/feat-domain-prompt-packs
marco-l/feat-vegalite-dashboard
```

If you have **two unrelated tasks in flight**, that's **two branches** — never bundle.

### The daily loop

```bash
# Start of day — get the latest development
git checkout development
git pull origin development

# Start a new task
git checkout -b jane-doe/feat-hitl-cleaning-screen

# Code. Commit often, small commits OK.
git add apps/web/app/\(user\)/cleaning-plan/page.tsx
git commit -m "feat(web/hitl): scaffold cleaning plan approval screen"

# Push — first time creates the remote branch
git push -u origin jane-doe/feat-hitl-cleaning-screen

# When ready, open a PR via the GitHub UI or:
gh pr create --base development \
 --title "[Phase 1] HITL #2 — cleaning plan approval screen" \
 --body-file .github/pr-template.md

# Address review comments, push more commits to the same branch
git push
```

### PR title format

```
[Phase N] <one-line description>
```

Examples:
- `[Phase 1] Auth — JWT signup, login, RBAC middleware`
- `[Phase 1] Ingestion Agent — CSV, XLSX, JSON, Parquet detection`
- `[Phase 1] HITL #1 — schema and merge validation screen`
- `[Phase 1] Cleaning Plan Agent — dedup, imputation, type coercion`
- `[Phase 1] Dashboard Agent — Vega-Lite spec generation`

### PR description (use this template)

```markdown
## What
<1–2 sentences describing the change>

## Why
<link to the task in planphase.md, e.g., "Phase 1 → Sprint 3 → Cleaning Plan Agent">

## How to test
<exact commands or steps a reviewer can run>

## Acceptance criteria
- [ ] <criterion from planphase.md "Done when">
- [ ] <criterion>
- [ ] <criterion>

## Safety checks
- [ ] All LLM calls go through the provider abstraction layer — no direct Anthropic/OpenAI SDK calls in agent code
- [ ] HITL gate enforced — no cleaning step executes without a recorded user decision
- [ ] Raw Layer 1 (S3) never modified — only curated Layer 2 is written by Cleaning Executor
- [ ] RBAC enforced server-side — admin endpoints return 403 for non-admin users
- [ ] No user data (rows, cell values) logged — only schema metadata and action types
- [ ] Every agent output validated against its Pydantic schema before use
- [ ] SQL generated by Analysis/Dashboard Agent validated as read-only (no DDL, no writes)
- [ ] Tests included
```

### When a PR is mergeable

- CI green (lint + typecheck + unit tests + build).
- At least one required reviewer approved (file owner per planphase.md if you touched their files).
- All review comments addressed or explicitly waived by the reviewer.
- No merge conflicts with `development`.

**Squash-merge** is the default. The PR title becomes the commit message on `development`.

---

## 5. Before you write a single line of code

Run through this checklist:

- [ ] I read the task in `planphase.md` carefully. I know what success looks like.
- [ ] My task is one of the 14 Phase 1 P0 features (F0a, F1, F1b, F2, F3, F3b, F3c, F4, F5, F6, F7, F8, F9, F10). If it's not, I raise it in standup — don't silently expand scope.
- [ ] I checked the file-ownership map. If I'll touch a file outside my zone, I message the owner *first*.
- [ ] I know which invariant could break: HITL gate integrity, RBAC enforcement, raw-layer immutability, audit log completeness, LLM provider abstraction.

---

## 6. Daily standup (Slack thread by 9:30 AM IST)

```
Yesterday: <what you finished>
Today:  <what you'll work on>
Files:  <files you'll edit today>
Blockers: <who you're waiting on, or "none">
```

Team lead scans the thread, flags conflicts, resolves before 10:30 AM.

---

## 7. When you're stuck

| Stuck on… | Ask… |
|---|---|
| What a feature should do | Product Lead (PRD owner) |
| How something is built | The file owner (see planphase.md) |
| Agent design / pipeline orchestration (`tasks.py`) | AI/Agent Lead |
| LLM provider config / cost / model choice | AI/Agent Lead |
| API design / FastAPI / Pydantic | Backend Lead |
| Frontend / Next.js / Vega-Lite / shadcn | Frontend Lead |
| AWS infra / S3 / RDS / FastAPI BackgroundTasks / Redis | Infra Engineer |
| CI failure | Infra Engineer |
| Test failure / golden datasets | QA Engineer |
| UX / HITL screen design | Designer |

**Stuck for more than 2 hours?** Post in `#datamind-help` with the ticket name, what you tried, and the exact error. Don't sit alone.

---

## 8. Cheat sheet — commands

```bash
# Python
uv sync            # install Python workspace
uv run pytest          # run all tests
uv run pytest tests/agents/       # agent-specific tests
uv run pytest tests/hitl/       # HITL flow tests
uv run ruff check .         # lint
uv run black --check .        # format check
uv run black .          # apply formatting
uv run mypy packages/agents       # strict typecheck on agents

# Run backend services
uv run uvicorn apps.api.main:app --reload   # FastAPI on :8000
uv run celery -A apps.worker.celery_app worker  # pipeline worker
uv run celery -A apps.worker.celery_app flower  # worker monitoring UI on :5555

# Run frontend
pnpm --filter web dev        # Next.js (User + Admin UI) on :3000

# Database
docker compose up -d        # start Postgres
uv run alembic upgrade head       # apply migrations
uv run alembic revision --autogenerate -m "msg"  # generate new migration
uv run alembic downgrade -1       # roll back one migration
psql $DATABASE_URL         # direct DB access

# Storage (local S3 via LocalStack or real AWS)
aws s3 ls s3://$S3_RAW_BUCKET/      # list raw uploads
aws s3 ls s3://$S3_CURATED_BUCKET/     # list JSON files

# Job queue
redis-cli monitor         # watch FastAPI BackgroundTasks job events

# Git
git checkout development && git pull    # sync integration branch
git checkout -b your-name/feat-thing    # new feature branch
gh pr create --base development     # open PR
```

---

## 9. Rule for Claude (or any AI assistant) generating code in this repo

When Claude Code (or any AI agent) is asked to generate code:

1. **Create a branch first** — named `claude/feat-<slug>`.
2. **Commit on that branch** — never on `development` or `main` directly.
3. **Open a PR against `development`** with the full PR template above, including all safety checks.
4. **The human owns the merge.** Claude reviews its own PR for the safety checklist; the human reviewer approves.

This rule is the same as for human contributors — **no exceptions for AI-generated code.**

Pay particular attention to DataMind-specific invariants:
- Never bypass a HITL gate.
- Never call an LLM provider SDK directly — always through the provider abstraction layer.
- Never write to Layer 1 (archive) from any agent other than the Ingestion Agent's initial upload.
- Never log row-level user data — schema metadata only.

---

## 10. The shortest possible summary

> Read your role's tasks in `planphase.md`. Branch off `development` as `your-name/feat-thing`. Write code with tests. Open a PR. Wait for green CI + a reviewer. Squash-merge.

That's the loop. Everything else in this file is detail you only need when something specific comes up.
