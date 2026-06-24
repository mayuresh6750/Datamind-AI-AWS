"""Analysis Agent — SQL on PostgreSQL for numeric, semantic search on pgvector for textual."""
import json

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.embeddings import get_embedding_model
from app.core.llm import LLMClient
from app.models.schemas import AnalysisSpec

log = structlog.get_logger()

_SQL_GEN_PROMPT = """
You are a SQL generator for a {domain} dataset stored in PostgreSQL.

Table name: "{table_name}"
Columns available in this table: {columns}

IMPORTANT — all columns are stored as TEXT.
- For numeric aggregations: AVG(NULLIF(col_name, '')::FLOAT)  (handles empty strings stored as missing values)
- For count queries (when measures is empty): COUNT(*) grouped by the dimension columns
- Use the EXACT column names listed above (they are case-sensitive)

Analysis spec:
- dimensions: {dimensions}
- measures: {measures}
- filters: {filters}
- time_range: {time_range}

Generate a single read-only SELECT statement that:
1. If measures is non-empty: SELECT each dimension + AVG(NULLIF(measure_col, '')::FLOAT) AS col_name, GROUP BY dimensions
2. If measures is empty but dimensions exist: SELECT dimension_col, COUNT(*) AS count, GROUP BY dimension_col ORDER BY count DESC
3. Use ONLY the exact column names from the list above
4. Returns at most 1000 rows

Return ONLY the raw SQL — no explanation, no markdown, no semicolon at the end.
""".strip()


class AnalysisAgent:
    """Runs SQL (numeric) and vector search (textual) based on AnalysisSpec."""

    def __init__(self, llm: LLMClient | None = None) -> None:
        self.llm = llm or LLMClient()

    async def run_numeric(
        self,
        spec: AnalysisSpec,
        table_name: str,
        db: AsyncSession,
        domain: str,
    ) -> list[dict]:
        from app.core.llm import LLMClient
        from pydantic import BaseModel

        # Discover which columns actually exist in the table before generating SQL.
        # Spec dimensions/measures may reference textual columns not routed to PostgreSQL.
        available_cols: set[str] = set()
        try:
            async with await db.begin_nested():
                col_res = await db.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = :t AND table_schema = 'public'"
                    ),
                    {"t": table_name},
                )
                available_cols = {row[0] for row in col_res.fetchall()}
        except Exception as exc:
            log.warning("analysis_table_column_discovery_failed", error=str(exc), table=table_name)

        if not available_cols:
            log.warning("analysis_table_not_found_or_empty", table=table_name)
            return []

        # Case-insensitive matching: CSV headers like "Department" vs spec "department"
        col_lower_map = {c.lower(): c for c in available_cols}

        def _resolve(name: str) -> str | None:
            return name if name in available_cols else col_lower_map.get(name.lower())

        dims = [r for d in spec.dimensions if (r := _resolve(d))]
        measures = [r for m in spec.measures if (r := _resolve(m))]

        # Detect count-type queries: user asked for counts but no numeric measure was found
        is_count_query = dims and not measures

        if is_count_query:
            # Short-circuit: generate COUNT(*) SQL directly without an LLM call
            sql = self._heuristic_sql(dims, [], table_name, count_mode=True)
            log.info("analysis_count_query_shortcircuit", dims=dims, table=table_name)
            try:
                async with await db.begin_nested():
                    result = await db.execute(text(sql))
                    rows = [dict(zip(result.keys(), row)) for row in result.fetchall()]
                log.info("analysis_count_sql_executed", rows=len(rows))
                return rows
            except Exception as exc:
                log.error("analysis_count_sql_failed", error=str(exc), sql=sql[:200])
                return []

        if not dims and not measures:
            log.warning("analysis_no_matching_columns", spec_dims=spec.dimensions, spec_measures=spec.measures, available=list(available_cols))
            # Last resort: COUNT all rows
            sql = f'SELECT COUNT(*) AS total_records FROM "{table_name}"'
            try:
                async with await db.begin_nested():
                    result = await db.execute(text(sql))
                    rows = [dict(zip(result.keys(), row)) for row in result.fetchall()]
                return rows
            except Exception:
                return []

        prompt = _SQL_GEN_PROMPT.format(
            domain=domain,
            table_name=table_name,
            columns=", ".join(sorted(available_cols)),
            dimensions=dims,
            measures=measures,
            filters=json.dumps(spec.filters or []),
            time_range=json.dumps(spec.time_range or {}),
        )

        class SQLOutput(BaseModel):
            sql: str

        try:
            sql_result = await self.llm.structured_completion(
                f"Return JSON: {{\"sql\": \"<your SELECT here>\"}} for: {prompt}",
                SQLOutput,
                agent_name="analysis_sql_gen",
            )
            sql = sql_result.sql.strip().rstrip(";")
        except Exception as exc:
            log.warning("analysis_sql_gen_llm_failed", error=str(exc))
            sql = self._heuristic_sql(dims, measures, table_name)

        # Safety: only allow SELECT statements
        if not sql.strip().upper().startswith("SELECT"):
            log.error("analysis_non_select_sql_blocked", sql=sql[:100])
            return []

        try:
            # Use a savepoint so a bad SQL statement only aborts the savepoint,
            # not the outer transaction — allowing pipeline_runs INSERT to succeed.
            async with await db.begin_nested():
                result = await db.execute(text(sql))
                rows = [dict(zip(result.keys(), row)) for row in result.fetchall()]
            log.info("analysis_sql_executed", rows=len(rows), table=table_name)
            return rows
        except Exception as exc:
            log.error("analysis_sql_failed", error=str(exc), sql=sql[:200])
            # Retry with a guaranteed-safe heuristic query
            safe_sql = self._heuristic_sql(dims, measures, table_name)
            try:
                async with await db.begin_nested():
                    result = await db.execute(text(safe_sql))
                    rows = [dict(zip(result.keys(), row)) for row in result.fetchall()]
                log.info("analysis_heuristic_sql_executed", rows=len(rows))
                return rows
            except Exception as exc2:
                log.error("analysis_heuristic_sql_failed", error=str(exc2))
                return []

    def _heuristic_sql(
        self,
        dims: list[str],
        measures: list[str],
        table_name: str,
        count_mode: bool = False,
    ) -> str:
        """Build a guaranteed-safe GROUP BY query."""
        dim_selects = [f'"{d}"' for d in dims]
        group_by_clause = f' GROUP BY {", ".join(f"{chr(34)}{d}{chr(34)}" for d in dims)}' if dims else ""

        if count_mode or (dims and not measures):
            # COUNT(*) grouped by dimensions — for "how many", "count of", etc.
            selects = dim_selects + ["COUNT(*) AS count"]
            return (
                f'SELECT {", ".join(selects)} FROM "{table_name}"'
                f'{group_by_clause} ORDER BY count DESC LIMIT 100'
            )

        # NULLIF converts empty string → NULL before casting, preventing CAST errors
        agg_selects = [f'AVG(NULLIF("{m}", \'\')::FLOAT) AS "{m}"' for m in measures]
        selects = dim_selects + agg_selects or ["COUNT(*) AS total_records"]
        order_by = f' ORDER BY {chr(34)}{dims[0]}{chr(34)}' if dims else ""
        return (
            f'SELECT {", ".join(selects)} FROM "{table_name}"'
            f'{group_by_clause}{order_by} LIMIT 100'
        )

    async def run_textual(
        self,
        question: str,
        dataset_id: str,
        db: AsyncSession,
        top_k: int = 10,
    ) -> list[dict]:
        import asyncio
        loop = asyncio.get_event_loop()
        embedding_model = get_embedding_model()
        # embed() is CPU-bound (Qwen3 on CPU). Run in thread so the event loop stays responsive.
        query_embedding = await loop.run_in_executor(None, embedding_model.embed, question)
        embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

        sql = text("""
            SELECT content, metadata, 1 - (embedding <=> CAST(:embedding AS vector)) AS similarity
            FROM dataset_embeddings
            WHERE dataset_id = :dataset_id
            ORDER BY embedding <=> CAST(:embedding AS vector)
            LIMIT :top_k
        """)

        try:
            # Savepoint: vector table may not exist for this dataset — isolate failure.
            async with await db.begin_nested():
                result = await db.execute(sql, {
                    "embedding": embedding_str,
                    "dataset_id": dataset_id,
                    "top_k": top_k,
                })
                rows = [{"content": r.content, "metadata": r.metadata, "similarity": float(r.similarity)} for r in result]
            log.info("analysis_vector_search_done", hits=len(rows), dataset_id=dataset_id)
            return rows
        except Exception as exc:
            log.error("analysis_vector_search_failed", error=str(exc))
            return []
