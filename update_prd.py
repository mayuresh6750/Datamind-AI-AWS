"""
Update DataMind_AI_PRD.docx with the following changes:
  1. AWS S3 / AWS RDS / AWS Secrets Manager / AWS SQS+Fargate → Supabase equivalents
  2. pgvector → Weaviate (textual/semantic layer)
  3. LLM providers → Mistral series + Moonshot Kimi (free models)
"""

import zipfile, shutil, os, re

INPUT = "DataMind_AI_PRD.docx"
OUTPUT = "DataMind_AI_PRD.docx"   # overwrite in-place
BACKUP = "DataMind_AI_PRD_original_backup.docx"

# Ordered replacements – longer/more-specific strings first to avoid partial clobbers
REPLACEMENTS = [
    # ── Storage: AWS S3 ──────────────────────────────────────────────────────
    ("AWS S3 for raw and curated storage",
     "Supabase Storage for raw and curated storage"),
    ("AWS S3 bucket with versioning, per-user prefix isolation",
     "Supabase Storage bucket with versioning, per-user prefix isolation"),
    ("AWS S3 bucket holding cleaned data in Apache Parquet format",
     "Supabase Storage bucket holding cleaned data in Apache Parquet format"),
    ("AWS S3 (versioned bucket, per-user prefix)",
     "Supabase Storage (versioned bucket, per-user prefix)"),
    ("AWS S3 (curated prefix), Apache Parquet",
     "Supabase Storage (curated prefix), Apache Parquet"),
    ("AWS-based data and AI infrastructure layer",
     "Supabase-based data and AI infrastructure layer"),
    ("AWS S3",   "Supabase Storage"),
    ("S3 + Athena", "Supabase Storage + DuckDB"),
    ("S3 bucket", "Supabase Storage bucket"),

    # ── Metadata DB: AWS RDS ─────────────────────────────────────────────────
    ("PostgreSQL (AWS RDS, single-AZ in P1, Multi-AZ in P2)",
     "Supabase Database (PostgreSQL, single-AZ in P1, Multi-AZ in P2)"),
    ("PostgreSQL (RDS)",        "Supabase Database (PostgreSQL)"),
    ("Postgres (RDS)",          "Supabase Database (PostgreSQL)"),
    ("AWS RDS",                 "Supabase Database"),

    # ── Job Queue: AWS SQS + Fargate ─────────────────────────────────────────
    ("Celery + Redis (P1); AWS SQS + Fargate workers (P2)",
     "Celery + Redis (P1); Redis Streams + Celery workers (P2)"),
    ("AWS SQS + Fargate workers", "Redis Streams + Celery workers"),
    ("AWS SQS + Fargate",         "Redis Streams + Celery"),
    ("SQS + Fargate",             "Redis Streams + Celery"),

    # ── Secrets ──────────────────────────────────────────────────────────────
    ("AWS Secrets Manager",     "Supabase Vault"),

    # ── Encryption ───────────────────────────────────────────────────────────
    ("SSE-S3 in P1, SSE-KMS in P2",
     "AES-256 at rest (Supabase managed, P1+P2)"),
    ("SSE-KMS",  "Supabase AES-256 managed encryption"),
    ("SSE-S3",   "Supabase AES-256 encryption"),

    # ── Vector store: pgvector → Weaviate ────────────────────────────────────
    ("pgvector on PostgreSQL",  "Weaviate"),
    ("pgvector hosts embeddings for free-text columns",
     "Weaviate hosts vector embeddings for free-text columns"),
    ("pgvector for textual embeddings",
     "Weaviate for textual/semantic embeddings"),
    ("pgvector HNSW index",     "Weaviate HNSW index"),
    ("pgvector, Pinecone",      "Weaviate"),
    ("pgvector",                "Weaviate"),
    # Layer 4 description
    ("Layer 4 (Textual / semantic): pgvector",
     "Layer 4 (Textual / semantic): Weaviate"),
    ("Textual/Vector (Layer 4) | pgvector on PostgreSQL",
     "Textual/Vector (Layer 4) | Weaviate"),

    # ── LLM Providers: Phase 1 ───────────────────────────────────────────────
    # Long form with full list
    ("Anthropic Claude, OpenAI, Google Gemini, Azure OpenAI, AWS Bedrock, or self-hosted models (Ollama)",
     "Mistral (mistral-small, mistral-7b-instruct), Moonshot Kimi (kimi-k2, moonshot-v1), Google Gemini Flash, or self-hosted models (Ollama)"),
    ("Anthropic Claude + OpenAI (Phase 1)",
     "Mistral + Moonshot Kimi (Phase 1)"),
    ("Anthropic Claude + OpenAI",
     "Mistral (mistral-small) + Moonshot Kimi (kimi-k2)"),
    ("Anthropic + one other",
     "Mistral + Moonshot Kimi"),
    ("Anthropic Claude",        "Mistral"),
    ("Anthropic",               "Mistral"),

    # Phase 2 LLM expansion list
    ("Google Gemini, Azure OpenAI, AWS Bedrock, self-hosted Ollama",
     "Google Gemini Flash, Groq (Llama 3), self-hosted Ollama"),
    ("Google Gemini, Azure OpenAI, AWS Bedrock",
     "Google Gemini Flash, Groq (Llama 3)"),
    ("Azure OpenAI, AWS Bedrock, Ollama",
     "Groq (Llama 3), Ollama (self-hosted)"),
    ("Azure OpenAI",            "Groq (Llama 3)"),
    ("AWS Bedrock",             "Groq (Llama 3)"),

    # Phase 1 note about providers
    ("at least two providers in Phase 1 (Anthropic + one other)",
     "at least two providers in Phase 1 (Mistral + Moonshot Kimi)"),

    # ── Catch-all: remaining bare "AWS" not already replaced ─────────────────
    # (anything left is minor infra mention — map to Supabase / generic cloud)
    ("AWS-based",               "Supabase-based"),
]


def apply_replacements(xml: str) -> str:
    """Replace text inside <w:t>...</w:t> tags, preserving XML structure."""
    def replace_in_wt(m):
        inner = m.group(1)
        for old, new in REPLACEMENTS:
            inner = inner.replace(old, new)
        return f"<w:t>{inner}</w:t>"

    # Also try a global pass for any that span xml-preserved text
    result = re.sub(r"<w:t>(.*?)</w:t>", replace_in_wt, xml, flags=re.DOTALL)

    # Second pass: replacements on the raw XML string for cases where text is
    # not split across runs (common in plain paragraphs & table cells).
    for old, new in REPLACEMENTS:
        result = result.replace(old, new)

    return result


def fix_content_types(ct_xml: str) -> str:
    """Add an entry for the .undefined media file so python-docx stops erroring."""
    if 'Extension="undefined"' not in ct_xml:
        ct_xml = ct_xml.replace(
            "</Types>",
            '<Default Extension="undefined" ContentType="application/octet-stream"/></Types>',
        )
    return ct_xml


def main():
    # Back up the original
    if not os.path.exists(BACKUP):
        shutil.copy2(INPUT, BACKUP)
        print(f"Backup created: {BACKUP}")

    # Read all files from the original docx
    all_files: dict[str, bytes] = {}
    with zipfile.ZipFile(INPUT, "r") as zin:
        for name in zin.namelist():
            all_files[name] = zin.read(name)

    # Modify document.xml
    doc_xml = all_files["word/document.xml"].decode("utf-8")
    doc_xml = apply_replacements(doc_xml)
    all_files["word/document.xml"] = doc_xml.encode("utf-8")

    # Fix [Content_Types].xml
    ct_xml = all_files["[Content_Types].xml"].decode("utf-8")
    ct_xml = fix_content_types(ct_xml)
    all_files["[Content_Types].xml"] = ct_xml.encode("utf-8")

    # Write the updated docx
    tmp = OUTPUT + ".tmp"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for name, data in all_files.items():
            zout.writestr(name, data)
    os.replace(tmp, OUTPUT)

    print(f"Updated PRD saved: {OUTPUT}")

    # ── Verify: print all remaining occurrences of key old terms ─────────────
    with zipfile.ZipFile(OUTPUT, "r") as z:
        new_xml = z.read("word/document.xml").decode("utf-8")
    plain = re.sub(r"<[^>]+>", " ", new_xml)
    plain = re.sub(r"\s+", " ", plain)

    check_terms = ["AWS S3", "pgvector", "AWS RDS", "AWS Bedrock",
                   "Anthropic Claude", "SSE-S3", "SSE-KMS",
                   "AWS Secrets Manager", "AWS SQS"]
    print("\n── Residual occurrences check ──")
    for term in check_terms:
        count = plain.count(term)
        status = "OK (0 left)" if count == 0 else f"WARNING: {count} still present"
        print(f"  {term:30s}  {status}")

    # Count replacements applied
    print("\n── Replacement targets now in updated PRD ──")
    new_terms = ["Supabase Storage", "Supabase Database", "Weaviate",
                 "Mistral", "Moonshot Kimi", "Supabase Vault",
                 "Supabase AES-256", "Redis Streams"]
    for term in new_terms:
        count = plain.count(term)
        print(f"  {term:30s}  {count} occurrence(s)")


if __name__ == "__main__":
    main()
