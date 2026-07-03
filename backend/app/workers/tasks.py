"""FastAPI BackgroundTasks handlers — one function per pipeline stage."""
import asyncio
import json
import uuid

# asyncpg hard limit is 32 767 parameters per statement.
# 500 rows × ≤65 columns stays safely under that ceiling for PostgreSQL inserts.
# pgvector inserts use 4 params/row, so 500 rows = 2 000 params — well under.
_INSERT_CHUNK = 500
_EMBED_CHUNK = 500

import structlog

from app.api.v1.jobs import register_job, update_job

log = structlog.get_logger()


def _apply_merge(
    parsed_files: dict[str, list[dict]],
    proposal: dict,
    decision: dict,
) -> list[dict]:
    """Apply the HITL-confirmed merge strategy to produce a single dataset.

    - union: vertical stack of all files (same schema required)
    - join:  left-join on a key column; first file is the left table
    - single: only one file, return it as-is
    - separate: files have incompatible schemas; stack with a _source_file tag
    """
    strategy = decision.get("merge_strategy_override") or proposal.get("strategy") or "union"
    join_key = decision.get("join_key_override") or proposal.get("join_key")
    excluded: set[str] = set(decision.get("excluded_columns") or [])

    file_names = list(parsed_files.keys())
    if not file_names:
        return []

    if strategy in ("single",) or len(file_names) == 1:
        rows: list[dict] = list(parsed_files[file_names[0]])

    elif strategy == "union":
        rows = []
        for file_rows in parsed_files.values():
            rows.extend(file_rows)

    elif strategy == "join" and join_key:
        # Left-join: largest file drives (fact/transaction table), smaller files are lookups.
        # Using upload order would make a 15-row dimension table drive a 100-row fact table,
        # losing all but one transaction per dimension row.
        driver = max(parsed_files, key=lambda f: len(parsed_files[f]))
        lookup_files = [f for f in file_names if f != driver]
        rows = list(parsed_files[driver])
        for fname in lookup_files:
            lookup: dict[str, dict] = {}
            for r in parsed_files[fname]:
                lookup[str(r.get(join_key, ""))] = r
            merged: list[dict] = []
            for row in rows:
                right = lookup.get(str(row.get(join_key, "")), {})
                merged_row = dict(row)
                for col, val in right.items():
                    if col != join_key:
                        merged_row[col] = val
                merged.append(merged_row)
            rows = merged

    else:
        # separate / unknown — stack with a _source_file marker so rows stay distinguishable
        rows = []
        for fname, file_rows in parsed_files.items():
            for row in file_rows:
                rows.append({"_source_file": fname, **row})

    if excluded:
        rows = [{k: v for k, v in row.items() if k not in excluded} for row in rows]

    return rows


async def run_ingest_pipeline(dataset_id: str, user_id: str, job_id: str) -> None:
    """Detect format, parse files, profile columns, store merge plan in HITL table."""
    register_job(job_id)
    update_job(job_id, "running", progress_pct=5, current_step="loading_files")

    from app.core.database import AsyncSessionLocal
    from app.core.storage import StorageClient
    from app.models.db import Dataset, HITLDecision, PipelineRun
    from app.agents.ingestion import IngestionAgent
    from sqlalchemy import select

    ingestion = IngestionAgent()

    async with AsyncSessionLocal() as db:
        try:
            # Fetch dataset record
            result = await db.execute(select(Dataset).where(Dataset.dataset_id == uuid.UUID(dataset_id)))
            dataset = result.scalar_one()

            storage = StorageClient()
            all_rows: list[dict] = []
            file_profiles = []
            file_formats: list[str] = []
            per_file_counts: list[dict] = []

            update_job(job_id, "running", progress_pct=20, current_step="downloading_files")

            archive_paths = dataset.archive_uris or [
                f"{user_id}/{dataset_id}/{filename}" for filename in dataset.original_filenames
            ]
            if len(archive_paths) != len(dataset.original_filenames):
                raise ValueError("Stored archive paths do not match original filenames.")

            for filename, path in zip(dataset.original_filenames, archive_paths, strict=True):
                content = storage.download_archive(path)

                fmt = ingestion.detect_format(filename, content)
                rows = ingestion.parse_content(fmt, content)

                # Extract upload timestamp from archive path: user/dataset/YYYYMMDDTHHMMSS/file
                uploaded_at: str | None = None
                parts = path.split("/")
                if len(parts) >= 3:
                    try:
                        from datetime import datetime as _dt
                        uploaded_at = _dt.strptime(parts[2], "%Y%m%dT%H%M%S").strftime("%Y-%m-%dT%H:%M:%SZ")
                    except ValueError:
                        pass

                per_file_counts.append({
                    "filename": filename,
                    "row_count": len(rows),
                    "uploaded_at": uploaded_at,
                    "archive_path": path,
                })
                profiles = ingestion.profile_columns(rows)
                file_profiles.append((filename, profiles))
                file_formats.append(fmt)
                all_rows.extend(rows)

            update_job(job_id, "running", progress_pct=60, current_step="generating_merge_plan")

            merge_plan = ingestion.propose_merge_plan(file_profiles, all_rows)

            # Enrich merge plan with per-file and merged row counts for HITL #1 display
            from app.models.schemas import FileRowCount
            from app.models.schemas import MergePlan as MergePlanSchema
            enriched_plan = MergePlanSchema(
                **{**merge_plan.model_dump(), "source_file_counts": per_file_counts, "merged_row_count": len(all_rows)}
            )

            # Create pipeline run
            run = PipelineRun(
                dataset_id=uuid.UUID(dataset_id),
                status="paused_for_hitl",
            )
            db.add(run)
            await db.flush()

            # Store merge plan as HITL proposal
            hitl = HITLDecision(
                dataset_id=uuid.UUID(dataset_id),
                user_id=uuid.UUID(user_id),
                checkpoint="schema_merge",
                proposal_json=enriched_plan.model_dump(),
                decision_json={},
            )
            db.add(hitl)

            # Update dataset status, format, and row counts
            dataset.status = "awaiting_hitl_merge"
            dataset.detected_format = file_formats[0] if file_formats else "csv"
            dataset.row_count_raw = len(all_rows)
            dataset.source_file_counts = per_file_counts

            await db.commit()

            # Upload _summary.json — non-fatal; Postgres is the source of truth.
            # merged_row_count here is the raw sum; it is updated to the actual post-merge
            # count once the cleaning executor runs and applies the confirmed strategy.
            try:
                from datetime import datetime as _dt
                summary = {
                    "dataset_id": dataset_id,
                    "generated_at": _dt.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "source_files": per_file_counts,   # each entry has filename, row_count, uploaded_at, archive_path
                    "proposed_merge_strategy": enriched_plan.strategy,
                    "source_combined_row_count": len(all_rows),
                    "status": "awaiting_hitl_merge",
                }
                storage.upload_summary(user_id, dataset_id, json.dumps(summary, indent=2).encode())
            except Exception as summary_exc:
                log.warning("summary_upload_skipped", error=str(summary_exc))

            update_job(job_id, "complete", progress_pct=100, current_step="awaiting_hitl_merge")
            log.info("ingest_pipeline_complete", dataset_id=dataset_id, rows=len(all_rows), files=len(per_file_counts))

        except Exception as exc:
            await db.rollback()
            update_job(job_id, "failed", error=str(exc))
            log.error("ingest_pipeline_failed", dataset_id=dataset_id, error=str(exc))


async def run_cleaning_plan_pipeline(dataset_id: str, merge_decision: dict, job_id: str) -> None:
    """Generate cleaning plan after merge decision approved."""
    register_job(job_id)
    update_job(job_id, "running", progress_pct=10, current_step="loading_data")

    from app.core.database import AsyncSessionLocal
    from app.core.storage import StorageClient
    from app.models.db import Dataset, HITLDecision, PipelineRun
    from app.agents.cleaning_plan import CleaningPlanAgent
    from app.agents.ingestion import IngestionAgent
    from app.core.llm import LLMClient
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        try:
            result = await db.execute(select(Dataset).where(Dataset.dataset_id == uuid.UUID(dataset_id)))
            dataset = result.scalar_one()

            # Re-download and parse data using stored archive URIs.
            storage = StorageClient()
            ingestion = IngestionAgent()

            archive_paths = dataset.archive_uris or [
                f"{dataset.user_id}/{dataset_id}/{filename}" for filename in dataset.original_filenames
            ]
            parsed_files: dict[str, list[dict]] = {}
            for filename, path in zip(dataset.original_filenames, archive_paths, strict=True):
                content = storage.download_archive(path)
                fmt = ingestion.detect_format(filename, content)
                parsed_files[filename] = ingestion.parse_content(fmt, content)

            # Load the HITL #1 proposal to get the default strategy/join_key
            merge_hitl_res = await db.execute(
                select(HITLDecision)
                .where(HITLDecision.dataset_id == uuid.UUID(dataset_id), HITLDecision.checkpoint == "schema_merge")
                .order_by(HITLDecision.created_at.desc())
                .limit(1)
            )
            merge_hitl = merge_hitl_res.scalar_one_or_none()
            merge_proposal = merge_hitl.proposal_json if merge_hitl else {}

            # Apply the user-confirmed merge strategy before generating the cleaning plan
            all_rows = _apply_merge(parsed_files, merge_proposal, merge_decision)
            profiles = ingestion.profile_columns(all_rows)

            update_job(job_id, "running", progress_pct=50, current_step="generating_cleaning_plan")

            # Fetch user domain
            from app.models.db import User
            user_result = await db.execute(select(User).where(User.user_id == dataset.user_id))
            user = user_result.scalar_one()
            domain = user.active_domain

            # One shared LLMClient — its total_tokens/total_cost_usd accumulate across all agent calls
            llm_client = LLMClient()
            cleaning_agent = CleaningPlanAgent(llm=llm_client)
            plan = await cleaning_agent.propose(all_rows, profiles, domain)

            hitl = HITLDecision(
                dataset_id=uuid.UUID(dataset_id),
                user_id=dataset.user_id,
                checkpoint="cleaning_plan",
                proposal_json=plan.model_dump(),
                decision_json={},
            )
            db.add(hitl)
            dataset.status = "awaiting_hitl_cleaning"

            # Persist token usage for this run — previously these columns were always NULL
            run = PipelineRun(
                dataset_id=uuid.UUID(dataset_id),
                status="complete",
                llm_provider=llm_client._provider,
                total_llm_tokens=llm_client.total_tokens,
                total_llm_cost_usd=llm_client.total_cost_usd,
            )
            db.add(run)
            await db.commit()

            update_job(job_id, "complete", progress_pct=100, current_step="awaiting_hitl_cleaning")
            log.info(
                "cleaning_plan_pipeline_complete",
                dataset_id=dataset_id,
                steps=len(plan.steps),
                total_tokens=llm_client.total_tokens,
                total_cost_usd=round(llm_client.total_cost_usd, 6),
            )

        except Exception as exc:
            await db.rollback()
            update_job(job_id, "failed", error=str(exc))
            log.error("cleaning_plan_pipeline_failed", dataset_id=dataset_id, error=str(exc))


async def run_cleaning_executor_pipeline(dataset_id: str, cleaning_decision: dict, job_id: str) -> None:
    """Execute approved cleaning steps; route data to PostgreSQL and pgvector."""
    register_job(job_id)
    update_job(job_id, "running", progress_pct=10, current_step="loading_data")

    from app.core.database import AsyncSessionLocal
    from app.core.storage import StorageClient
    from app.models.db import AuditLog, Dataset, HITLDecision, PipelineRun
    from app.agents.cleaning_executor import CleaningExecutorAgent
    from app.agents.ingestion import IngestionAgent
    from app.models.schemas import CleaningPlanDecision, CleaningStep
    from app.core.embeddings import get_embedding_model
    from sqlalchemy import select, text

    async with AsyncSessionLocal() as db:
        try:
            result = await db.execute(select(Dataset).where(Dataset.dataset_id == uuid.UUID(dataset_id)))
            dataset = result.scalar_one()

            storage = StorageClient()
            ingestion = IngestionAgent()

            archive_paths = dataset.archive_uris or [
                f"{dataset.user_id}/{dataset_id}/{filename}" for filename in dataset.original_filenames
            ]
            parsed_files: dict[str, list[dict]] = {}
            for filename, path in zip(dataset.original_filenames, archive_paths, strict=True):
                content = storage.download_archive(path)
                fmt = ingestion.detect_format(filename, content)
                parsed_files[filename] = ingestion.parse_content(fmt, content)

            # Load the HITL #1 proposal + decision to apply the correct merge strategy.
            from app.models.schemas import ColumnProfile as ColumnProfileSchema
            merge_hitl_res = await db.execute(
                select(HITLDecision)
                .where(HITLDecision.dataset_id == uuid.UUID(dataset_id), HITLDecision.checkpoint == "schema_merge")
                .order_by(HITLDecision.created_at.desc())
                .limit(1)
            )
            merge_hitl = merge_hitl_res.scalar_one_or_none()
            merge_proposal = merge_hitl.proposal_json if merge_hitl else {}
            merge_decision_data = merge_hitl.decision_json if merge_hitl else {}

            # Apply merge strategy — JOIN produces fewer rows than raw stack; UNION keeps all.
            all_rows = _apply_merge(parsed_files, merge_proposal, merge_decision_data)

            # Update row_count_raw to the actual post-merge count (may differ from ingest-time sum).
            dataset.row_count_raw = len(all_rows)

            # For JOIN/SEPARATE the column set changes after merge, so always re-profile.
            # For UNION the stored profiles are accurate but re-profiling is cheap.
            effective_strategy = (
                merge_decision_data.get("merge_strategy_override")
                or merge_proposal.get("strategy")
                or "union"
            )
            if effective_strategy == "union" and merge_hitl and merge_hitl.proposal_json.get("column_profiles"):
                profiles = [ColumnProfileSchema(**p) for p in merge_hitl.proposal_json["column_profiles"]]
            else:
                profiles = ingestion.profile_columns(all_rows)

            # Load cleaning plan proposal
            hitl_result = await db.execute(
                select(HITLDecision)
                .where(HITLDecision.dataset_id == uuid.UUID(dataset_id), HITLDecision.checkpoint == "cleaning_plan")
                .order_by(HITLDecision.created_at.desc())
                .limit(1)
            )
            hitl = hitl_result.scalar_one()
            steps = [CleaningStep(**s) for s in hitl.proposal_json["steps"]]
            decision = CleaningPlanDecision(**cleaning_decision)

            update_job(job_id, "running", progress_pct=40, current_step="executing_cleaning")
            executor = CleaningExecutorAgent()
            cleaned_rows, audit_entries = executor.execute(all_rows, steps, decision)

            update_job(job_id, "running", progress_pct=65, current_step="storing_json")

            # Layer 2: JSON upload — non-fatal; warn and continue if bucket missing
            json_path: str | None = None
            try:
                json_bytes = json.dumps(cleaned_rows, default=str).encode("utf-8")
                json_path = storage.upload_json(str(dataset.user_id), dataset_id, json_bytes)
            except Exception as upload_exc:
                log.warning("json_upload_skipped", error=str(upload_exc))

            update_job(job_id, "running", progress_pct=75, current_step="routing_to_postgresql")

            # Layer 3: Route numeric columns to PostgreSQL — non-fatal savepoint
            numeric_cols = [p.name for p in profiles if p.classification == "numeric"]
            textual_cols = [p.name for p in profiles if p.classification == "textual"]
            table_name = f"ds_{dataset_id.replace('-', '_')}"

            try:
                async with await db.begin_nested():
                    if numeric_cols and cleaned_rows:
                        col_defs = ", ".join(f'"{c}" TEXT' for c in numeric_cols)
                        await db.execute(text(f'CREATE TABLE IF NOT EXISTS "{table_name}" ({col_defs})'))
                        # Bulk insert all rows in a single executemany call instead of
                        # one INSERT per row, reducing N database round-trips to 1.
                        col_names = ", ".join(f'"{c}"' for c in numeric_cols)
                        placeholders = ", ".join(f":{c}" for c in numeric_cols)
                        insert_sql = text(f'INSERT INTO "{table_name}" ({col_names}) VALUES ({placeholders})')
                        # Chunk to stay under asyncpg's 32 767-parameter limit and
                        # avoid building a single huge in-memory list for large datasets.
                        for i in range(0, len(cleaned_rows), _INSERT_CHUNK):
                            chunk_vals = [
                                {c: str(row.get(c, "")) for c in numeric_cols}
                                for row in cleaned_rows[i:i + _INSERT_CHUNK]
                            ]
                            await db.execute(insert_sql, chunk_vals)
            except Exception as pg_exc:
                log.warning("postgresql_routing_skipped", error=str(pg_exc))

            update_job(job_id, "running", progress_pct=85, current_step="embedding_textual_columns")

            # Layer 4: pgvector embeddings — non-fatal savepoint
            try:
                async with await db.begin_nested():
                    if textual_cols and cleaned_rows:
                        embedding_model = get_embedding_model()
                        await db.execute(text("""
                            CREATE TABLE IF NOT EXISTS dataset_embeddings (
                                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                                dataset_id UUID NOT NULL,
                                content TEXT NOT NULL,
                                metadata JSONB,
                                embedding vector(1024)
                            )
                        """))
                        loop = asyncio.get_event_loop()
                        insert_emb = text(
                            "INSERT INTO dataset_embeddings "
                            "(dataset_id, content, metadata, embedding) "
                            "VALUES (:did, :content, :meta, CAST(:emb AS vector))"
                        )
                        total = len(cleaned_rows)
                        # Process in chunks: each chunk embeds in a thread pool then
                        # inserts immediately, bounding both CPU time per slice and
                        # peak RAM usage regardless of dataset size.
                        for i in range(0, total, _EMBED_CHUNK):
                            chunk_rows = cleaned_rows[i:i + _EMBED_CHUNK]
                            # 512-char cap: Qwen3 supports 8K but shorter inputs embed
                            # ~10x faster on CPU with negligible semantic quality loss.
                            chunk_texts = [
                                " ".join(str(row.get(c, "")) for c in textual_cols)[:512]
                                for row in chunk_rows
                            ]
                            chunk_embeddings = await loop.run_in_executor(
                                None, embedding_model.embed_batch, chunk_texts
                            )
                            emb_params = [
                                {
                                    "did": dataset_id,
                                    "content": text_val,
                                    "meta": json.dumps({k: row.get(k) for k in list(row.keys())[:5]}),
                                    "emb": "[" + ",".join(str(x) for x in emb) + "]",
                                }
                                for text_val, emb, row in zip(chunk_texts, chunk_embeddings, chunk_rows)
                            ]
                            await db.execute(insert_emb, emb_params)
                            done = i + len(chunk_rows)
                            pct = 85 + int(14 * done / max(total, 1))
                            update_job(
                                job_id, "running", progress_pct=pct,
                                current_step=f"embedding_textual_columns ({done}/{total} rows)",
                            )
            except Exception as emb_exc:
                log.warning("embedding_skipped", error=str(emb_exc))

            # Audit log — non-fatal savepoint
            try:
                async with await db.begin_nested():
                    run = PipelineRun(dataset_id=uuid.UUID(dataset_id), status="complete")
                    db.add(run)
                    await db.flush()
                    for entry in audit_entries:
                        log_entry = AuditLog(
                            dataset_id=uuid.UUID(dataset_id),
                            run_id=run.run_id,
                            user_id=dataset.user_id,
                            agent_name="cleaning_executor",
                            action_type=entry["action"],
                            rows_affected=entry.get("rows_changed"),
                            rationale=entry.get("rationale"),
                            confidence=entry.get("confidence"),
                        )
                        db.add(log_entry)
            except Exception as audit_exc:
                log.warning("audit_log_skipped", error=str(audit_exc))

            # Critical: always mark dataset ready regardless of optional step failures
            dataset.status = "ready"
            dataset.row_count_clean = len(cleaned_rows)
            dataset.json_uri = json_path
            await db.commit()

            # Update _summary.json — merged_row_count now reflects the actual post-merge count,
            # not the raw sum of all source files.
            try:
                merged = dataset.row_count_raw or 0  # updated above to post-merge count
                clean = len(cleaned_rows)
                strategy = (
                    merge_decision_data.get("merge_strategy_override")
                    or merge_proposal.get("strategy")
                    or "union"
                )
                from datetime import datetime as _dt
                summary = {
                    "dataset_id": dataset_id,
                    "generated_at": _dt.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "source_files": dataset.source_file_counts or [],
                    "merge_strategy": strategy,
                    "merged_row_count": merged,
                    "clean_row_count": clean,
                    "dropped_rows": merged - clean,
                    "status": "ready",
                }
                storage.upload_summary(str(dataset.user_id), dataset_id, json.dumps(summary, indent=2).encode())
            except Exception as summary_exc:
                log.warning("summary_update_skipped", error=str(summary_exc))

            update_job(job_id, "complete", progress_pct=100, current_step="ready")
            log.info("cleaning_executor_pipeline_complete", dataset_id=dataset_id, cleaned_rows=len(cleaned_rows))

        except Exception as exc:
            await db.rollback()
            update_job(job_id, "failed", error=str(exc))
            log.error("cleaning_executor_pipeline_failed", dataset_id=dataset_id, error=str(exc))


async def run_intent_analysis_pipeline(dataset_id: str, question: str, user_id: str, job_id: str) -> None:
    """Parse intent, run analysis, generate dashboard + insights."""
    register_job(job_id)
    update_job(job_id, "running", progress_pct=10, current_step="parsing_intent")

    from app.core.database import AsyncSessionLocal
    from app.models.db import Dataset, PipelineRun, User
    from app.agents.intent import IntentAgent
    from app.agents.analysis import AnalysisAgent
    from app.agents.dashboard_agent import DashboardAgent
    from app.agents.insights import InsightsAgent
    from app.agents.ingestion import IngestionAgent
    from app.models.schemas import ColumnProfile
    from app.core.storage import StorageClient
    from app.core.llm import LLMClient
    from sqlalchemy import select, text

    async with AsyncSessionLocal() as db:
        try:
            ds_result = await db.execute(select(Dataset).where(Dataset.dataset_id == uuid.UUID(dataset_id)))
            dataset = ds_result.scalar_one()

            user_result = await db.execute(select(User).where(User.user_id == dataset.user_id))
            user = user_result.scalar_one()
            domain = user.active_domain

            # Reload cleaned JSON — fall back to re-parsing from archive if not yet uploaded
            storage = StorageClient()
            ingestion_fallback = IngestionAgent()
            try:
                json_path = storage.json_path(str(dataset.user_id), dataset_id)
                cleaned_rows = json.loads(storage.download_json(json_path))
            except Exception:
                archive_paths = dataset.archive_uris or [
                    f"{dataset.user_id}/{dataset_id}/{fn}" for fn in dataset.original_filenames
                ]
                cleaned_rows = []
                for filename, path in zip(dataset.original_filenames, archive_paths, strict=True):
                    content = storage.download_archive(path)
                    fmt = ingestion_fallback.detect_format(filename, content)
                    cleaned_rows.extend(ingestion_fallback.parse_content(fmt, content))
                log.warning("json_download_fallback", dataset_id=dataset_id, rows=len(cleaned_rows))

            profiles = ingestion_fallback.profile_columns(cleaned_rows)

            # One shared LLMClient passed to all 4 agents — accumulates tokens for the full run
            llm_client = LLMClient()

            intent_agent = IntentAgent(llm=llm_client)
            spec = await intent_agent.parse(question, profiles, domain)
            update_job(job_id, "running", progress_pct=40, current_step="running_analysis")

            analysis_agent = AnalysisAgent(llm=llm_client)
            table_name = f"ds_{dataset_id.replace('-', '_')}"
            numeric_results = await analysis_agent.run_numeric(spec, table_name, db, domain)
            textual_results = await analysis_agent.run_textual(question, dataset_id, db)
            # Ensure the transaction is clean before committing pipeline_runs.
            # run_numeric / run_textual use savepoints internally, but asyncpg can
            # still leave the session in a bad state if the savepoint itself failed
            # to roll back cleanly. A no-op SELECT confirms the session is usable.
            try:
                await db.execute(text("SELECT 1"))
            except Exception:
                await db.rollback()

            update_job(job_id, "running", progress_pct=75, current_step="generating_dashboard")
            dashboard_agent = DashboardAgent(llm=llm_client)
            dashboard = await dashboard_agent.generate(spec, numeric_results, textual_results, domain)

            update_job(job_id, "running", progress_pct=90, current_step="generating_insights")
            insights_agent = InsightsAgent(llm=llm_client)
            final_dashboard = await insights_agent.enrich(dashboard, domain)

            from app.api.v1.dashboards import cache_dashboard
            cache_dashboard(dataset_id, final_dashboard)

            # Persist token usage for this run — previously these columns were always NULL
            run = PipelineRun(
                dataset_id=uuid.UUID(dataset_id),
                status="complete",
                llm_provider=llm_client._provider,
                total_llm_tokens=llm_client.total_tokens,
                total_llm_cost_usd=llm_client.total_cost_usd,
            )
            db.add(run)

            await db.commit()
            update_job(job_id, "complete", progress_pct=100, current_step="dashboard_ready")
            log.info(
                "intent_analysis_pipeline_complete",
                dataset_id=dataset_id,
                total_tokens=llm_client.total_tokens,
                total_cost_usd=round(llm_client.total_cost_usd, 6),
            )

        except Exception as exc:
            await db.rollback()
            update_job(job_id, "failed", error=str(exc))
            log.error("intent_analysis_pipeline_failed", dataset_id=dataset_id, error=str(exc))


async def run_dashboard_pipeline(dataset_id: str, user_id: str, job_id: str) -> None:
    """Alias for re-generating the dashboard on demand."""
    await run_intent_analysis_pipeline(dataset_id, "Give me an overview of this dataset", user_id, job_id)
