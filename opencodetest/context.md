# DataMind AI — Session Context

## Current State (Session 10 — 2026-05-26)

**Tech stack**: Google Gemini 3.5 Flash | Supabase (DB + Vector/pgvector) | FastAPI BackgroundTasks | PostgreSQL | Python stdlib

**File processing pipeline**:
1. Upload any format (CSV, XLSX, JSON, Parquet) → archive original to `supabase://datamind-archive/`
2. Convert to JSON → agents operate on JSON in `supabase://datamind-json/`
3. Structured columns also dumped to typed PostgreSQL tables for SQL queries
4. Textual columns → embeddings → Supabase Vector (pgvector) for semantic search

**What's done**:
- All 22 documentation files + 2 DOCX files updated from old stack (Weaviate, DuckDB, Mistral/Moonshot, Celery+Redis, Pandas/PyArrow) to new stack
- `HLD.md` rewritten with new architecture
- `LLD.md` created (low-level design: API endpoints, DB schema, agent contracts, routing algorithm, HITL state machine, error codes, folder structure, env vars, security)
- `update_all_files.py` automation script created for bulk replacements
- `docs/PRD.md` (original location) also updated to match

**Original project instructions in**: `C:/Users/Smita/GenAI/Datamind/claude.md`
**Working directory**: `C:/Users/Smita/GenAI/Datamind/opencodetest/`
**Git branch**: `main` — no uncommitted changes

**What's next**: Not yet started on Phase 1 implementation (likely proceeding after user review).
