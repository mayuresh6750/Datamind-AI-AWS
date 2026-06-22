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
You are a SQL generator for a {domain} dataset.

Table name: "{table_name}"
Columns available: {columns}

Analysis spec:
- dimensions: {dimensions}
- measures: {measures}
- filters: {filters}
- time_range: {time_range}

Generate a single read-only SELECT statement that:
1. Groups by the dimension columns
2. Aggregates the measure columns (use SUM or AVG as appropriate)
3. Applies any filters from the spec
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
        all_cols = spec.dimensions + spec.measures
        prompt = _SQL_GEN_PROMPT.format(
            domain=domain,
            table_name=table_name,
            columns=", ".join(all_cols),
            dimensions=spec.dimensions,
            measures=spec.measures,
            filters=json.dumps(spec.filters or []),
            time_range=json.dumps(spec.time_range or {}),
        )

        from app.core.llm import LLMClient
        from pydantic import BaseModel

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
            sql = self._heuristic_sql(spec, table_name)

        # Safety: only allow SELECT statements
        if not sql.strip().upper().startswith("SELECT"):
            log.error("analysis_non_select_sql_blocked", sql=sql[:100])
            return []

        try:
            result = await db.execute(text(sql))
            rows = [dict(zip(result.keys(), row)) for row in result.fetchall()]
            log.info("analysis_sql_executed", rows=len(rows), table=table_name)
            return rows
        except Exception as exc:
            log.error("analysis_sql_failed", error=str(exc), sql=sql[:200])
            return []

    def _heuristic_sql(self, spec: AnalysisSpec, table_name: str) -> str:
        # Only use measures in the numeric table; dimensions may be textual cols not present there
        if spec.measures:
            aggs = ", ".join(f'AVG(CAST("{m}" AS FLOAT)) AS "{m}"' for m in spec.measures)
            return f'SELECT {aggs} FROM "{table_name}" LIMIT 100'
        return f'SELECT * FROM "{table_name}" LIMIT 100'

    async def run_textual(
        self,
        question: str,
        dataset_id: str,
        db: AsyncSession,
        top_k: int = 10,
    ) -> list[dict]:
        embedding_model = get_embedding_model()
        query_embedding = embedding_model.embed(question)
        embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

        sql = text("""
            SELECT content, metadata, 1 - (embedding <=> CAST(:embedding AS vector)) AS similarity
            FROM dataset_embeddings
            WHERE dataset_id = :dataset_id
            ORDER BY embedding <=> CAST(:embedding AS vector)
            LIMIT :top_k
        """)

        try:
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
