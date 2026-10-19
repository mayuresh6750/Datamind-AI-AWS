"""Analysis Agent — SQL on PostgreSQL for numeric, semantic search on pgvector for textual."""
import json
import re

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.embeddings import get_embedding_model
from app.core.llm import LLMClient
from app.models.schemas import AnalysisSpec, AnalysisResult

log = structlog.get_logger()

_SQL_GEN_PROMPT = """
You are a True NL-to-SQL expert for a {domain} dataset stored in PostgreSQL.

User's exact question:
"{original_question}"

Table name: "{table_name}"
Columns available in this table: {columns}

Analysis hints (use these as guidance, but the question above is the ultimate source of truth):
- Grouping dimensions: {dimensions}
- Measures (numeric columns): {measures}
- Requested aggregation: {aggregation}
  → "sum" = SUM(...)
  → "avg" = AVG(...)
  → "count" = COUNT(*)
  → "max" = MAX(...)
  → "min" = MIN(...)
- Filters: {filters}
- Time range: {time_range}

IMPORTANT RULES — you MUST follow all of these:
1. ALL column names MUST be wrapped in double quotes: "Column_Name" — never unquoted.
2. All columns are stored as TEXT. For numeric aggregations use:
   {aggregation_upper}(NULLIF(REGEXP_REPLACE("col_name", '[^0-9.-]', '', 'g'), '')::FLOAT)
   This strips currency symbols ($, £, €), commas, and spaces before casting.
3. The query MUST answer the user's exact question. If the user asked for TOP N, use ORDER BY + LIMIT N.
   If the user asked for a filter (e.g. "in 2023", "Electronics only"), add a WHERE clause.
   If the user asked for a comparison, write the comparison in SQL.
4. Only generate a read-only SELECT statement. No INSERT, UPDATE, DELETE, DROP, or CREATE.
5. Only use column names that are in the list above — never invent columns.
6. Return at most 1000 rows.
7. Return ONLY the raw SQL — no explanation, no markdown fences, no trailing semicolon.
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

        log.info("analysis_table_columns_found", table=table_name, columns=sorted(available_cols))

        if not available_cols:
            log.warning("analysis_table_not_found_or_empty", table=table_name)
            return []

        # Case-insensitive matching: CSV headers like "Department" vs spec "department"
        col_lower_map = {c.lower(): c for c in available_cols}

        def _resolve(name: str) -> str | None:
            return name if name in available_cols else col_lower_map.get(name.lower())

        dims = [r for d in spec.dimensions if (r := _resolve(d))]
        measures = [r for m in spec.measures if (r := _resolve(m))]
        log.info("analysis_resolved_spec", spec_dims=spec.dimensions, spec_measures=spec.measures, resolved_dims=dims, resolved_measures=measures)

        # Sample each "measure" column to check whether it actually contains numeric values.
        # If a measure column is categorical (e.g. "Medication", "Treatment"), demote it to
        # an additional dimension so we fall through to COUNT(*) grouping instead of AVG().
        if measures:
            numeric_measures: list[str] = []
            text_as_dims: list[str] = []
            for m in measures:
                try:
                    async with await db.begin_nested():
                        samp = await db.execute(
                            text(
                                f'SELECT "{m}" FROM "{table_name}" '
                                f"WHERE \"{m}\" IS NOT NULL AND \"{m}\" != '' LIMIT 5"
                            ),
                        )
                        vals = [row[0] for row in samp.fetchall()]
                    # A column is numeric if at least one sample value yields a non-empty
                    # string after stripping all non-digit/decimal characters.
                    is_numeric = any(re.sub(r"[^0-9.]", "", str(v)) for v in vals)
                    (numeric_measures if is_numeric else text_as_dims).append(m)
                except Exception:
                    text_as_dims.append(m)  # safe fallback: treat as dim
            if text_as_dims:
                dims = dims + text_as_dims
                measures = numeric_measures
                log.info("analysis_text_measures_demoted_to_dims", text_as_dims=text_as_dims)

        # Defend against parameter bounds and check for empty semantic match
        clean_filters: list[dict] = []
        for f in (spec.filters or []):
            f_copy = dict(f)
            val = f_copy.get("val") if "val" in f_copy else f_copy.get("value")
            op = (f_copy.get("op") or "=").upper()
            if op == "IN" and isinstance(val, (list, tuple, set)):
                if len(val) == 0:
                    log.warning(
                        "analysis_zero_matching_semantic_ids",
                        concept=getattr(spec, "semantic_filter_concept", None),
                        table=table_name,
                    )
                    return []
                # Cap at 500 IDs to avoid query bloat
                f_copy["val"] = list(val)[:500]
            clean_filters.append(f_copy)

        # Detect count-type queries: user asked for counts but no numeric measure was found
        is_count_query = (dims or clean_filters) and (not measures or getattr(spec, "aggregation", "") == "count")
        if is_count_query:
            measures = []
            # Short-circuit: generate COUNT(*) SQL directly without an LLM call
            sql = self._heuristic_sql(dims, [], table_name, count_mode=True, filters=clean_filters, available_cols=available_cols)
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

        aggregation = getattr(spec, "aggregation", "sum")

        # Standard aggregations with or without ID filters are deterministic — use safe heuristic SQL
        if measures and not spec.time_range:
            sql = self._heuristic_sql(
                dims, measures, table_name, count_mode=False,
                aggregation=aggregation, filters=clean_filters, available_cols=available_cols
            )
            log.info("analysis_heuristic_sql_shortcircuit", sql=sql, dims=dims, measures=measures, aggregation=aggregation)
            try:
                async with await db.begin_nested():
                    result = await db.execute(text(sql))
                    rows = [dict(zip(result.keys(), row)) for row in result.fetchall()]
                log.info("analysis_heuristic_sql_executed", rows=len(rows), table=table_name)
                return rows
            except Exception as exc:
                log.error("analysis_heuristic_sql_failed", error=str(exc), sql=sql[:200])
                # Fall through to LLM path below

        if not dims and not measures:
            log.warning("analysis_no_matching_columns", spec_dims=spec.dimensions, spec_measures=spec.measures, available=list(available_cols))
            # Last resort: COUNT all rows (with filters applied if present)
            where_c = self._build_where_clause(clean_filters, available_cols)
            sql = f'SELECT COUNT(*) AS total_records FROM "{table_name}"{where_c}'
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
            original_question=getattr(spec, "original_question", "") or spec.restatement,
            columns=", ".join(f'"{c}"' for c in sorted(available_cols)),
            dimensions=dims,
            measures=measures,
            aggregation=aggregation,
            aggregation_upper=aggregation.upper(),
            filters=json.dumps(clean_filters),
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
            sql = self._heuristic_sql(
                dims, measures, table_name, count_mode=is_count_query,
                aggregation=aggregation, filters=clean_filters, available_cols=available_cols
            )

        log.info("analysis_sql_generated", sql=sql, dims=dims, measures=measures)

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
            safe_sql = self._heuristic_sql(
                dims, measures, table_name, count_mode=is_count_query,
                aggregation=getattr(spec, "aggregation", "sum"),
                filters=clean_filters, available_cols=available_cols
            )
            try:
                async with await db.begin_nested():
                    result = await db.execute(text(safe_sql))
                    rows = [dict(zip(result.keys(), row)) for row in result.fetchall()]
                log.info("analysis_heuristic_sql_executed", rows=len(rows))
                return rows
            except Exception as exc2:
                log.error("analysis_heuristic_sql_failed", error=str(exc2))
                return []

    def _build_where_clause(
        self,
        filters: list[dict] | None,
        available_cols: set[str] | None = None,
    ) -> str:
        """Construct a safe SQL WHERE clause from spec filters, escaping strings and capping IN sets."""
        if not filters:
            return ""
        clauses = []
        col_lower_map = {c.lower(): c for c in available_cols} if available_cols else {}
        for f in filters:
            raw_col = f.get("col") or f.get("column")
            if not raw_col:
                continue
            col_name = col_lower_map.get(raw_col.lower(), raw_col)
            safe_col = f'"{col_name}"'
            op = (f.get("op") or "=").upper()
            val = f.get("val") if "val" in f else f.get("value")

            if op == "IN" and isinstance(val, (list, tuple, set)):
                if not val:
                    clauses.append("1 = 0")
                else:
                    capped = list(val)[:500]
                    escaped_vals = ", ".join(f"'{str(v).replace(chr(39), chr(39)+chr(39))}'" for v in capped)
                    clauses.append(f"{safe_col} IN ({escaped_vals})")
            elif op == "=":
                escaped = str(val).replace("'", "''")
                clauses.append(f"{safe_col} = '{escaped}'")
            elif op in (">", "<", ">=", "<=", "!=", "<>"):
                escaped = str(val).replace("'", "''")
                clauses.append(f"{safe_col} {op} '{escaped}'")
            elif op == "LIKE":
                escaped = str(val).replace("'", "''")
                clauses.append(f"{safe_col} ILIKE '{escaped}'")

        return f" WHERE {' AND '.join(clauses)}" if clauses else ""

    def _heuristic_sql(
        self,
        dims: list[str],
        measures: list[str],
        table_name: str,
        count_mode: bool = False,
        aggregation: str = "sum",
        filters: list[dict] | None = None,
        available_cols: set[str] | None = None,
    ) -> str:
        """Build a guaranteed-safe GROUP BY query using the requested aggregation and filters."""
        where_clause = self._build_where_clause(filters, available_cols)
        dim_selects = [f'"{d}"' for d in dims]
        group_by_clause = f' GROUP BY {", ".join(f"{chr(34)}{d}{chr(34)}" for d in dims)}' if dims else ""

        if count_mode or (dims and not measures):
            # COUNT(*) grouped by dimensions — for "how many", "count of", etc.
            selects = dim_selects + ["COUNT(*) AS count"]
            return (
                f'SELECT {", ".join(selects)} FROM "{table_name}"'
                f'{where_clause}{group_by_clause} ORDER BY count DESC LIMIT 100'
            )

        # Map aggregation keyword to SQL function
        agg_fn = {
            "sum": "SUM",
            "avg": "AVG",
            "max": "MAX",
            "min": "MIN",
            "count": "COUNT",
        }.get(aggregation.lower(), "SUM")

        # Strip currency symbols/commas before casting — handles $1,234.56 style values
        if agg_fn == "COUNT":
            agg_selects = [
                f'COUNT(*) AS "{m}_count"'
                for m in measures
            ]
        else:
            agg_selects = [
                f'{agg_fn}(NULLIF(REGEXP_REPLACE("{m}", \'[^0-9.-]\', \'\', \'g\'), \'\')::FLOAT) AS "{m}"'
                for m in measures
            ]
        selects = dim_selects + agg_selects or ["COUNT(*) AS total_records"]
        order_col = f'"{measures[0]}"' if measures else (f'"{dims[0]}"' if dims else "")
        order_by = f" ORDER BY {order_col} DESC" if order_col else ""
        return (
            f'SELECT {", ".join(selects)} FROM "{table_name}"'
            f'{where_clause}{group_by_clause}{order_by} LIMIT 100'
        )

    async def retrieve_semantic_row_ids(
        self,
        concept: str,
        dataset_id: str,
        db: AsyncSession,
        threshold: float = 0.70,
        limit: int = 500,
        id_column: str | None = None,
    ) -> list[str]:
        """Query pgvector for rows matching concept semantically, returning their row IDs."""
        import asyncio
        loop = asyncio.get_running_loop()
        embedding_model = get_embedding_model()

        try:
            query_embedding = await loop.run_in_executor(None, embedding_model.embed, concept)
            embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"
        except Exception as emb_err:
            log.warning("semantic_row_id_embedding_failed", error=str(emb_err), concept=concept)
            return []

        sql = text("""
            SELECT content, metadata, 1 - (embedding <=> CAST(:embedding AS vector)) AS similarity
            FROM dataset_embeddings
            WHERE dataset_id = :dataset_id
            ORDER BY embedding <=> CAST(:embedding AS vector)
            LIMIT :limit
        """)

        matched_ids: list[str] = []
        try:
            async with await db.begin_nested():
                result = await db.execute(sql, {
                    "embedding": embedding_str,
                    "dataset_id": dataset_id,
                    "limit": limit,
                })
                for r in result:
                    similarity = float(r.similarity) if r.similarity is not None else 0.0
                    if similarity < threshold:
                        continue

                    meta = r.metadata
                    if isinstance(meta, str):
                        try:
                            meta = json.loads(meta)
                        except Exception:
                            meta = {}
                    elif not isinstance(meta, dict):
                        meta = {}

                    row_id = None
                    if id_column and id_column in meta and meta[id_column] is not None:
                        row_id = str(meta[id_column])
                    else:
                        for k in ("_row_id", "id", "ID", "Id"):
                            if k in meta and meta[k] is not None:
                                row_id = str(meta[k])
                                break
                        if not row_id:
                            for k, v in meta.items():
                                if k.lower().endswith(("_id", "id")) and v is not None:
                                    row_id = str(v)
                                    break
                        if not row_id and meta:
                            first_val = next((v for v in meta.values() if v is not None), None)
                            if first_val is not None:
                                row_id = str(first_val)

                    if row_id and row_id not in matched_ids:
                        matched_ids.append(row_id)
                        if len(matched_ids) >= limit:
                            break

            log.info(
                "retrieve_semantic_row_ids_done",
                concept=concept,
                dataset_id=dataset_id,
                matched_count=len(matched_ids),
                threshold=threshold,
            )
            return matched_ids
        except Exception as exc:
            log.warning("retrieve_semantic_row_ids_failed", error=str(exc), concept=concept)
            return []

    async def run_textual(
        self,
        question: str,
        dataset_id: str,
        db: AsyncSession,
        top_k: int = 10,
    ) -> list[dict]:
        import asyncio
        loop = asyncio.get_running_loop()
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

    async def run_adk_analysis(
        self,
        spec: AnalysisSpec,
        table_name: str,
        dataset_id: str,
        db: AsyncSession,
        domain: str = "general",
        available_cols: list[str] | None = None,
    ) -> AnalysisResult:
        """
        Autonomous ReAct Analysis using Google GenAI SDK.
        Gemini is provided execute_sql_query and search_semantic_feedback as native tools
        to decide whether to query pure SQL, run vector search first, or synthesize hybrid results.
        Falls back to deterministic heuristic SQL on any error.
        """
        import asyncio
        from app.core.adk import create_data_tools
        from app.core.config import settings

        # 1. Discover available columns if not passed
        if available_cols is None:
            try:
                async with await db.begin_nested():
                    cols_result = await db.execute(
                        text(
                            "SELECT column_name FROM information_schema.columns "
                            "WHERE table_name = :t ORDER BY ordinal_position"
                        ),
                        {"t": table_name},
                    )
                    available_cols = [r[0] for r in cols_result.fetchall()]
            except Exception:
                available_cols = []

        tools = create_data_tools(db, table_name, dataset_id)
        executed_rows: list[dict] = []
        executed_sqls: list[str] = []
        matched_semantic_ids: list[str] = []

        # Tool wrappers to capture execution outcomes
        async def tracking_execute_sql(sql: str) -> str:
            executed_sqls.append(sql)
            res = await tools.execute_sql_query(sql)
            try:
                parsed = json.loads(res)
                if isinstance(parsed, list):
                    executed_rows.clear()
                    executed_rows.extend(parsed)
            except Exception:
                pass
            return res

        async def tracking_search_semantic(concept: str) -> str:
            res = await tools.search_semantic_feedback(concept)
            try:
                parsed = json.loads(res)
                if isinstance(parsed, dict) and "matched_row_ids" in parsed:
                    matched_semantic_ids.extend(parsed["matched_row_ids"])
            except Exception:
                pass
            return res

        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=settings.llm_api_key)
            model_name = settings.llm_model.split("/")[-1]

            cols_formatted = ", ".join(f'"{c}"' for c in available_cols)
            user_q = getattr(spec, "original_question", "") or spec.restatement
            sem_filter = getattr(spec, "semantic_filter_concept", None)

            prompt = (
                f"You are an autonomous data analysis agent for a {domain} dataset.\n"
                f'Question: "{user_q}"\n'
                f'Table name: "{table_name}"\n'
                f"Available columns: {cols_formatted}\n"
                f"Semantic concept filter if present: {sem_filter}\n\n"
                "Instructions:\n"
                "1. If the question asks about qualitative issues (e.g. complaints, delays, defects), "
                "call search_semantic_feedback to retrieve matching row IDs.\n"
                f'2. Use execute_sql_query to perform quantitative aggregations on "{table_name}". All column names '
                "MUST be double-quoted. All data columns are TEXT, so cast numbers using "
                "NULLIF(REGEXP_REPLACE(\"col\", '[^0-9.-]', '', 'g'), '')::FLOAT.\n"
                "3. Synthesize your final conclusions."
            )

            config = types.GenerateContentConfig(
                tools=[tracking_execute_sql, tracking_search_semantic],
                system_instruction="You are a data analysis agent. Query PostgreSQL and pgvector using your tools to answer the user's question.",
            )

            response = await asyncio.wait_for(
                client.aio.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=config,
                ),
                timeout=60,
            )

            summary = response.text or "Autonomous analysis complete."
            if not executed_rows:
                # If tool was not called or yielded no rows, run deterministic fallback
                executed_rows = await self.run_numeric(spec, table_name, db, domain)

            return AnalysisResult(
                summary=summary,
                rows=executed_rows,
                sql_query=executed_sqls[-1] if executed_sqls else getattr(self, "_last_sql", None),
                semantic_matches=matched_semantic_ids if matched_semantic_ids else None,
                confidence=spec.confidence or 0.95,
            )

        except Exception as exc:
            log.warning("adk_autonomous_analysis_fallback", error=str(exc))
            # Fall back to existing deterministic heuristic SQL path
            rows = await self.run_numeric(spec, table_name, db, domain)
            return AnalysisResult(
                summary=f"Analysis computed {len(rows)} results using deterministic SQL.",
                rows=rows,
                sql_query=getattr(self, "_last_sql", None),
                semantic_matches=getattr(spec, "semantic_filter_concept", None) and [],
                confidence=0.85,
            )

