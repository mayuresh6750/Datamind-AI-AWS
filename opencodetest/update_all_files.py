"""
Comprehensive update: apply new tech stack across all documentation files.
New stack: Google Gemini 3.5 Flash | pgvector | FastAPI BackgroundTasks | PostgreSQL | JSON | Python stdlib
"""
import os, re

BASE = "C:/Users/Smita/GenAI/Datamind"

TARGETS = [
    # root files
    BASE+"/README.md",
    BASE+"/claude.md",
    BASE+"/skills.md",
    # opencodetest/
    BASE+"/opencodetest/architecture.md",
    BASE+"/opencodetest/errors.md",
    BASE+"/opencodetest/HLD.md",
    BASE+"/opencodetest/memory.md",
    BASE+"/opencodetest/plan.md",
    BASE+"/opencodetest/planphase.md",
    BASE+"/opencodetest/tasks.md",
    BASE+"/opencodetest/team-guide.md",
    BASE+"/opencodetest/DataMind_AI_Architecture_Diagram.md",
    # docs/
    BASE+"/docs/architecture.md",
    BASE+"/docs/errors.md",
    BASE+"/docs/memory.md",
    BASE+"/docs/plan.md",
    BASE+"/docs/planphase.md",
    BASE+"/docs/tasks.md",
    BASE+"/docs/team-guide.md",
    # PRD.md (already mostly done, sweep remaining)
    BASE+"/opencodetest/PRD.md",
]

def fix_file(fp):
    with open(fp, "r", encoding="utf-8") as f:
        c = f.read()
    orig = c

    # === 1. Weaviate → Supabase Vector (pgvector) ===
    c = c.replace("Weaviate (HNSW index, cosine similarity)", "Supabase Vector (pgvector, HNSW index)")
    c = c.replace("Weaviate for textual/semantic embeddings", "Supabase Vector (pgvector) for textual/semantic embeddings")
    c = c.replace("Weaviate for textual/semantic", "Supabase Vector (pgvector) for textual/semantic")
    c = c.replace("Weaviate hosts vector embeddings", "Supabase Vector (pgvector) hosts vector embeddings")
    c = c.replace("Weaviate on Postgres", "Supabase Vector (pgvector)")
    c = c.replace("Weaviate (P1); Pinecone optional (P2)", "Supabase Vector (pgvector)")
    c = c.replace("Weaviate (default settings; tuned in P2)", "pgvector (default settings; tuned in P2)")
    c = c.replace("Weaviate operations", "pgvector operations")
    c = c.replace("Weaviate ops", "pgvector ops")
    c = c.replace("Weaviate index of column-name", "pgvector index of column-name")
    c = c.replace("Weaviate index of textual content", "pgvector index of textual content")
    c = c.replace("Weaviate embeddings", "pgvector embeddings")
    c = c.replace("Weaviate for free-text columns", "Supabase Vector (pgvector) for free-text columns")
    c = c.replace("Weaviate collection", "pgvector collection")
    c = re.sub(r'\bWeaviate\b', 'Supabase Vector (pgvector)', c)

    # === 2. Celery + Redis → FastAPI BackgroundTasks ===
    c = c.replace("Celery + Redis (P1); Redis Streams + Celery workers (P2)", "FastAPI BackgroundTasks (P1); dedicated worker pool (P2)")
    c = c.replace("Celery + Redis (P1) → Redis Streams + Celery workers (P2)", "FastAPI BackgroundTasks (P1) → dedicated worker pool (P2)")
    c = c.replace("Celery + Redis (Phase 1); Redis Streams + Celery workers (Phase 2)", "FastAPI BackgroundTasks (P1); dedicated worker pool (P2)")
    c = c.replace("Celery + Redis (P1); Celery workers (P2)", "FastAPI BackgroundTasks (P1); background workers (P2)")
    c = c.replace("Celery + Redis (P1); AWS SQS + Fargate workers (P2)", "FastAPI BackgroundTasks (P1); background workers (P2)")
    c = c.replace("Redis Streams + Celery workers", "dedicated worker pool")
    c = c.replace("Celery workers", "background workers")
    c = c.replace("Celery job queue wiring", "Async job queue wiring")
    c = c.replace("Celery agent worker", "background worker")
    c = c.replace("Celery pipeline worker", "pipeline worker")
    c = c.replace("Celery monitoring UI", "worker monitoring UI")
    c = c.replace("enqueue Celery", "trigger via FastAPI BackgroundTasks")
    c = c.replace("Celery config", "BackgroundTasks config")
    c = c.replace("Celery + Redis wiring", "FastAPI BackgroundTasks wiring")
    c = c.replace("Celery + Redis", "FastAPI BackgroundTasks")
    c = re.sub(r'\bCelery\b', 'FastAPI BackgroundTasks', c)
    c = c.replace("FastAPI BackgroundTasks + Redis (P1); dedicated worker pool (P2)", "FastAPI BackgroundTasks (P1); dedicated worker pool (P2)")
    c = c.replace("FastAPI BackgroundTasks + Redis", "FastAPI BackgroundTasks")

    # Redis in job queue context (not Redis Streams which is P2)
    c = c.replace("Redis queue depth", "queue depth")
    c = c.replace("Redis/Celery (job queue)", "FastAPI BackgroundTasks (job queue)")
    c = c.replace("Redis connectivity", "Supabase Storage connectivity")
    c = c.replace("Redis CLI", "Supabase CLI")
    c = c.replace("start Postgres + Redis", "start Postgres")

    # === 3. Mistral/Moonshot → Google Gemini 3.5 Flash ===
    c = c.replace("Mistral (mistral-small, mistral-7b-instruct) + Moonshot Kimi (kimi-k2, moonshot-v1)", "Google Gemini 3.5 Flash")
    c = c.replace("Mistral (mistral-small, mistral-7b-instruct), Moonshot Kimi (kimi-k2, moonshot-v1)", "Google Gemini 3.5 Flash")
    c = c.replace("Mistral + Moonshot Kimi", "Google Gemini 3.5 Flash")
    c = c.replace("Mistral and Moonshot Kimi", "Google Gemini 3.5 Flash")
    c = c.replace("Mistral, Moonshot Kimi", "Google Gemini 3.5 Flash")
    c = c.replace("Mistral series (mistral-small, mistral-7b-instruct)", "Google Gemini 3.5 Flash")
    c = c.replace("Moonshot Kimi (kimi-k2, moonshot-v1)", "Google Gemini 3.5 Flash")
    c = c.replace("Moonshot Kimi", "Google Gemini 3.5 Flash")
    c = re.sub(r'\bMistral\b', 'Google Gemini 3.5 Flash', c)
    c = c.replace("Google Gemini 3.5 Flash Google Gemini 3.5 Flash", "Google Gemini 3.5 Flash")

    # Provider expansion (Phase 2)
    c = c.replace("Google Gemini Flash, Groq (Llama 3), self-hosted Ollama", "additional LiteLLM-compatible providers as needed")
    c = c.replace("Google Gemini Flash, Groq (Llama 3), and self-hosted Ollama", "additional LiteLLM-compatible providers as needed")

    # === 4. DuckDB → PostgreSQL ===
    c = c.replace("DuckDB (P1 and P2, in-process; scales with Supabase Storage)", "PostgreSQL")
    c = c.replace("DuckDB (P1 and P2)", "PostgreSQL")
    c = c.replace("DuckDB (P1 + P2)", "PostgreSQL")
    c = c.replace("DuckDB (P1, in-process); Athena (P2)", "PostgreSQL")
    c = c.replace("DuckDB in-process", "PostgreSQL")
    c = c.replace("DuckDB queries", "PostgreSQL queries")
    c = c.replace("DuckDB for fast analytical queries", "PostgreSQL")
    c = c.replace("DuckDB / Athena", "PostgreSQL")
    c = c.replace("DuckDB streaming", "PostgreSQL streaming")
    c = c.replace("DuckDB attached for fast analytical queries", "PostgreSQL")
    c = c.replace("DuckDB as the query engine", "PostgreSQL as the query engine")
    c = re.sub(r'\bDuckDB\b', 'PostgreSQL', c)

    # === 5. Pandas → Python stdlib ===
    c = c.replace("Pandas profile", "Python stdlib profiling")
    c = c.replace("Pandas tools (sandboxed): profile_df, deduplicate_exact, impute_median, impute_mode, coerce_types, classify_column_type",
                  "Python stdlib data tools (sandboxed): profile_dataset, deduplicate_exact, impute_statistic, coerce_types, classify_column_type")
    c = c.replace("Pandas, openpyxl, python-magic, chardet", "openpyxl, python-magic, chardet, Python stdlib (csv, json)")
    c = c.replace("Pandas, PyArrow, PostgreSQL", "PostgreSQL")
    c = c.replace("Pandas, Pydantic", "Python stdlib (csv, json, statistics), Pydantic")
    c = c.replace("Pandas,", "Python stdlib (csv, json),")
    c = c.replace("Pandas", "Python stdlib (csv, json)")
    c = c.replace("Python stdlib (csv, json) profile", "Python stdlib profiling")

    # === 6. PyArrow ===
    c = c.replace("PyArrow,", "")
    c = c.replace(", PyArrow", "")
    c = c.replace("PyArrow", "")
    c = c.replace("openpyxl, Python stdlib (csv, json), ,", "openpyxl, Python stdlib (csv, json),")
    c = c.replace("openpyxl,  , Python stdlib", "openpyxl, Python stdlib")
    c = c.replace("openpyxl, python-magic, chardet, Python stdlib (csv, json),", "openpyxl, python-magic, chardet, Python stdlib (csv, json)")

    # === 7. Parquet → JSON (internal processing) ===
    # Only replace Parquet in internal processing context, not input format
    c = c.replace("Apache Parquet (P1); JSON format (P2)", "JSON (P1 + P2)")
    c = c.replace("Amazon S3 + Apache Parquet", "Supabase Storage + JSON")
    c = c.replace("Apache Parquet", "JSON")
    c = c.replace("Parquet conversion", "JSON normalisation")
    c = c.replace("Parquet copy", "JSON copy")

    # === 8. Path conventions ===
    c = c.replace("/data.parquet", "/data.json")
    c = c.replace("data.parquet", "data.json")
    c = c.replace("datamind-curated", "datamind-json")
    c = c.replace("curated bucket", "JSON bucket")
    c = c.replace("curated Parquet", "JSON")
    c = c.replace("curated S3 bucket", "JSON bucket")
    c = c.replace("raw S3 bucket", "archive bucket")
    c = c.replace("raw S3", "archive")
    c = c.replace("raw bucket", "archive bucket")
    c = c.replace("raw/curated", "archive/JSON")

    # === 9. S3 → Supabase Storage ===
    c = c.replace("s3://datamind-raw/", "supabase://datamind-archive/")
    c = c.replace("S3-based", "Supabase Storage-based")
    c = c.replace("S3 bucket", "Supabase Storage bucket")
    c = c.replace("S3 paths", "Supabase Storage paths")
    c = c.replace("S3 path", "Supabase Storage path")
    c = c.replace("S3 URIs", "storage URIs")
    c = c.replace("S3 URI", "storage URI")

    # === 10. Clean up artifacts ===
    c = c.replace("  ", " ")
    c = c.replace("  ", " ")
    c = c.replace("PostgreSQL PostgreSQL", "PostgreSQL")
    c = c.replace("PostgreSQL + PostgreSQL", "PostgreSQL")
    c = c.replace("PostgreSQL (PostgreSQL)", "PostgreSQL")
    c = c.replace("PostgreSQL / PostgreSQL", "PostgreSQL")
    c = c.replace("PostgreSQL database", "PostgreSQL")
    c = c.replace("JSON JSON", "JSON")
    c = c.replace("Supabase Vector (pgvector) Supabase Vector (pgvector)", "Supabase Vector (pgvector)")

    # Some context-specific fixes
    c = c.replace(""""Pandas" profile_df""", '"Python stdlib" profile_dataset')
    c = c.replace("store in Supabase Vector (pgvector) (HNSW index, per-tenant collection namespace)", "store in Supabase Vector (pgvector, HNSW index, per-tenant schema)")
    c = c.replace("Postgres-managed columns (and PostgreSQL)", "PostgreSQL")
    c = c.replace("PostgreSQL managed columns", "PostgreSQL")
    c = c.replace("Postgres/PostgreSQL", "PostgreSQL")

    if c != orig:
        with open(fp, "w", encoding="utf-8") as f:
            f.write(c)
        return True
    return False

count = 0
for fp in TARGETS:
    if not os.path.exists(fp):
        print(f"SKIP (not found): {os.path.basename(fp)}")
        continue
    if fix_file(fp):
        count += 1
        print(f"UPDATED: {os.path.relpath(fp, BASE)}")
    else:
        print(f"CHECKED: {os.path.relpath(fp, BASE)} (no changes)")

# === Now create LLD.md ===
print("\n--- Creating LLD.md ---")
# LLD.md will be created separately below

# === Now create README.md ===
print("\n--- Creating README.md ---")
# README.md will be created separately below

print(f"\nDone. {count} files updated.")
