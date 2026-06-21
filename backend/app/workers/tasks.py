"""FastAPI BackgroundTasks handlers — one function per pipeline stage."""
import json
import uuid

import structlog

from app.api.v1.jobs import register_job, update_job

log = structlog.get_logger()


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

                profiles = ingestion.profile_columns(rows)
                file_profiles.append((filename, profiles))
                file_formats.append(fmt)
                all_rows.extend(rows)

            update_job(job_id, "running", progress_pct=60, current_step="generating_merge_plan")

            merge_plan = ingestion.propose_merge_plan(file_profiles)

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
                proposal_json=merge_plan.model_dump(),
                decision_json={},
            )
            db.add(hitl)

            # Update dataset status and format
            dataset.status = "awaiting_hitl_merge"
            dataset.detected_format = file_formats[0] if file_formats else "csv"
            dataset.row_count_raw = len(all_rows)

            await db.commit()
            update_job(job_id, "complete", progress_pct=100, current_step="awaiting_hitl_merge")
            log.info("ingest_pipeline_complete", dataset_id=dataset_id, rows=len(all_rows))

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
            all_rows: list[dict] = []
            for filename, path in zip(dataset.original_filenames, archive_paths, strict=True):
                content = storage.download_archive(path)
                fmt = ingestion.detect_format(filename, content)
                rows = ingestion.parse_content(fmt, content)
                all_rows.extend(rows)

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
            all_rows: list[dict] = []
            for filename, path in zip(dataset.original_filenames, archive_paths, strict=True):
                content = storage.download_archive(path)
                fmt = ingestion.detect_format(filename, content)
                all_rows.extend(ingestion.parse_content(fmt, content))

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

            # Store cleaned JSON in Supabase Storage (Layer 2)
            json_path = storage.json_path(str(dataset.user_id), dataset_id)
            await storage.upload_json(json_path, cleaned_rows)

            update_job(job_id, "running", progress_pct=75, current_step="routing_to_postgresql")

            # Route numeric columns to PostgreSQL (typed table)
            numeric_cols = [p.name for p in profiles if p.classification == "numeric"]
            textual_cols = [p.name for p in profiles if p.classification == "textual"]
            table_name = f"ds_{dataset_id.replace('-', '_')}"

            if numeric_cols and cleaned_rows:
                col_defs = ", ".join(f'"{c}" TEXT' for c in numeric_cols)
                await db.execute(text(f'CREATE TABLE IF NOT EXISTS "{table_name}" ({col_defs})'))
                for row in cleaned_rows:
                    vals = {c: str(row.get(c, "")) for c in numeric_cols}
                    placeholders = ", ".join(f":{c}" for c in numeric_cols)
                    col_names = ", ".join(f'"{c}"' for c in numeric_cols)
                    await db.execute(text(f'INSERT INTO "{table_name}" ({col_names}) VALUES ({placeholders})'), vals)

            update_job(job_id, "running", progress_pct=85, current_step="embedding_textual_columns")

            # Embed textual columns into pgvector
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
                texts = [" ".join(str(row.get(c, "")) for c in textual_cols) for row in cleaned_rows]
                embeddings = embedding_model.embed_batch(texts)
                for text_val, emb, row in zip(texts, embeddings, cleaned_rows):
                    emb_str = "[" + ",".join(str(x) for x in emb) + "]"
                    await db.execute(
                        text("INSERT INTO dataset_embeddings (dataset_id, content, metadata, embedding) VALUES (:did, :content, :meta, :emb::vector)"),
                        {"did": dataset_id, "content": text_val, "meta": json.dumps({k: row.get(k) for k in list(row.keys())[:5]}), "emb": emb_str},
                    )

            # Create audit log entries
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

            dataset.status = "ready"
            dataset.row_count_clean = len(cleaned_rows)
            dataset.json_uri = json_path
            await db.commit()

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
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        try:
            ds_result = await db.execute(select(Dataset).where(Dataset.dataset_id == uuid.UUID(dataset_id)))
            dataset = ds_result.scalar_one()

            user_result = await db.execute(select(User).where(User.user_id == dataset.user_id))
            user = user_result.scalar_one()
            domain = user.active_domain

            # Reload cleaned JSON for column profiles
            storage = StorageClient()
            json_path = storage.json_path(str(dataset.user_id), dataset_id)
            cleaned_rows = await storage.download_json(json_path)

            ingestion = IngestionAgent()
            profiles = ingestion.profile_columns(cleaned_rows)

            # One shared LLMClient passed to all 4 agents — accumulates tokens for the full run
            llm_client = LLMClient()

            intent_agent = IntentAgent(llm=llm_client)
            spec = await intent_agent.parse(question, profiles, domain)
            update_job(job_id, "running", progress_pct=40, current_step="running_analysis")

            analysis_agent = AnalysisAgent(llm=llm_client)
            table_name = f"ds_{dataset_id.replace('-', '_')}"
            numeric_results = await analysis_agent.run_numeric(spec, table_name, db, domain)
            textual_results = await analysis_agent.run_textual(question, dataset_id, db)

            update_job(job_id, "running", progress_pct=75, current_step="generating_dashboard")
            dashboard_agent = DashboardAgent(llm=llm_client)
            dashboard = await dashboard_agent.generate(spec, numeric_results, textual_results, domain)

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
