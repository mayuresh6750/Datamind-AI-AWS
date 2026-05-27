"""Dataset endpoints — upload, ingest, HITL merge, HITL cleaning, intent."""
import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.storage import StorageClient
from app.models.db import Dataset, HITLDecision
from app.models.schemas import (
    CleaningPlan,
    CleaningPlanDecision,
    DomainUpdateRequest,
    IngestRequest,
    IntentRequest,
    JobResponse,
    MergePlan,
    MergePlanDecision,
    UploadURLRequest,
    UploadURLResponse,
)

log = structlog.get_logger()
router = APIRouter()

CurrentUser = Annotated[dict, Depends(get_current_user)]


# ─── Domain ───────────────────────────────────────────────────────────────────

@router.patch("/me/domain", status_code=status.HTTP_204_NO_CONTENT)
async def update_domain(
    body: DomainUpdateRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    from app.models.db import User
    result = await db.execute(select(User).where(User.user_id == uuid.UUID(current_user["sub"])))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")
    user.active_domain = body.domain
    user.other_domain_descriptor = body.other_descriptor
    await db.commit()


# ─── Upload ───────────────────────────────────────────────────────────────────

@router.post("/upload-url", response_model=UploadURLResponse)
async def get_upload_urls(
    body: UploadURLRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    if len(body.filenames) > 10:
        raise HTTPException(status_code=400, detail="Maximum 10 files per upload.")

    dataset_id = uuid.uuid4()
    storage = StorageClient()

    upload_urls: dict[str, str] = {}
    for filename in body.filenames:
        path = storage.archive_path(str(current_user["sub"]), str(dataset_id), filename)
        upload_urls[filename] = storage.get_archive_upload_url(path)

    dataset = Dataset(
        dataset_id=dataset_id,
        user_id=uuid.UUID(current_user["sub"]),
        original_filenames=body.filenames,
        detected_format="csv",  # overwritten during ingest
        file_count=len(body.filenames),
        status="uploaded",
    )
    db.add(dataset)
    await db.commit()

    return UploadURLResponse(dataset_id=str(dataset_id), upload_urls=upload_urls)


# ─── Ingest ───────────────────────────────────────────────────────────────────

@router.post("/{dataset_id}/ingest", response_model=JobResponse)
async def ingest_dataset(
    dataset_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    dataset = await _get_owned_dataset(db, dataset_id, current_user["sub"])
    if dataset.status != "uploaded":
        raise HTTPException(status_code=409, detail=f"Dataset status is '{dataset.status}', expected 'uploaded'.")

    from app.workers.tasks import run_ingest_pipeline
    job_id = str(uuid.uuid4())
    background_tasks.add_task(run_ingest_pipeline, str(dataset_id), str(current_user["sub"]), job_id)

    dataset.status = "profiling"
    await db.commit()

    return JobResponse(job_id=job_id, status="queued")


# ─── HITL #1 — Merge Plan ─────────────────────────────────────────────────────

@router.get("/{dataset_id}/merge-plan", response_model=MergePlan)
async def get_merge_plan(
    dataset_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    dataset = await _get_owned_dataset(db, dataset_id, current_user["sub"])
    if dataset.status != "awaiting_hitl_merge":
        raise HTTPException(status_code=409, detail="Merge plan not ready yet.")

    decision = await _latest_hitl(db, dataset_id, "schema_merge")
    if decision is None:
        raise HTTPException(status_code=404, detail="Merge plan not found.")

    return MergePlan.model_validate(decision.proposal_json)


@router.post("/{dataset_id}/merge-plan/decision", response_model=JobResponse)
async def submit_merge_decision(
    dataset_id: uuid.UUID,
    body: MergePlanDecision,
    background_tasks: BackgroundTasks,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    dataset = await _get_owned_dataset(db, dataset_id, current_user["sub"])
    if dataset.status != "awaiting_hitl_merge":
        raise HTTPException(status_code=409, detail="No pending merge decision.")

    hitl = HITLDecision(
        dataset_id=dataset_id,
        user_id=uuid.UUID(current_user["sub"]),
        checkpoint="schema_merge",
        proposal_json=await _latest_hitl_json(db, dataset_id, "schema_merge"),
        decision_json=body.model_dump(),
    )
    db.add(hitl)

    job_id = str(uuid.uuid4())
    if body.approved:
        from app.workers.tasks import run_cleaning_plan_pipeline
        background_tasks.add_task(run_cleaning_plan_pipeline, str(dataset_id), body.model_dump(), job_id)
        dataset.status = "cleaning_plan"
    else:
        dataset.status = "uploaded"

    await db.commit()
    return JobResponse(job_id=job_id, status="queued" if body.approved else "cancelled")


# ─── HITL #2 — Cleaning Plan ─────────────────────────────────────────────────

@router.get("/{dataset_id}/cleaning-plan", response_model=CleaningPlan)
async def get_cleaning_plan(
    dataset_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    dataset = await _get_owned_dataset(db, dataset_id, current_user["sub"])
    if dataset.status != "awaiting_hitl_cleaning":
        raise HTTPException(status_code=409, detail="Cleaning plan not ready yet.")

    decision = await _latest_hitl(db, dataset_id, "cleaning_plan")
    if decision is None:
        raise HTTPException(status_code=404, detail="Cleaning plan not found.")

    return CleaningPlan.model_validate(decision.proposal_json)


@router.post("/{dataset_id}/cleaning-plan/decision", response_model=JobResponse)
async def submit_cleaning_decision(
    dataset_id: uuid.UUID,
    body: CleaningPlanDecision,
    background_tasks: BackgroundTasks,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    dataset = await _get_owned_dataset(db, dataset_id, current_user["sub"])
    if dataset.status != "awaiting_hitl_cleaning":
        raise HTTPException(status_code=409, detail="No pending cleaning decision.")

    hitl = HITLDecision(
        dataset_id=dataset_id,
        user_id=uuid.UUID(current_user["sub"]),
        checkpoint="cleaning_plan",
        proposal_json=await _latest_hitl_json(db, dataset_id, "cleaning_plan"),
        decision_json=body.model_dump(),
    )
    db.add(hitl)

    job_id = str(uuid.uuid4())
    from app.workers.tasks import run_cleaning_executor_pipeline
    background_tasks.add_task(run_cleaning_executor_pipeline, str(dataset_id), body.model_dump(), job_id)
    dataset.status = "executing"

    await db.commit()
    return JobResponse(job_id=job_id, status="queued")


# ─── Intent (HITL #3) ────────────────────────────────────────────────────────

@router.post("/{dataset_id}/intent", response_model=JobResponse)
async def submit_intent(
    dataset_id: uuid.UUID,
    body: IntentRequest,
    background_tasks: BackgroundTasks,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    dataset = await _get_owned_dataset(db, dataset_id, current_user["sub"])
    if dataset.status != "ready":
        raise HTTPException(status_code=409, detail="Dataset not ready for analysis.")

    job_id = str(uuid.uuid4())
    from app.workers.tasks import run_intent_analysis_pipeline
    background_tasks.add_task(run_intent_analysis_pipeline, str(dataset_id), body.question, str(current_user["sub"]), job_id)

    return JobResponse(job_id=job_id, status="queued")


# ─── Helpers ─────────────────────────────────────────────────────────────────

async def _get_owned_dataset(db: AsyncSession, dataset_id: uuid.UUID, user_id: str) -> Dataset:
    result = await db.execute(
        select(Dataset).where(Dataset.dataset_id == dataset_id, Dataset.user_id == uuid.UUID(user_id))
    )
    dataset = result.scalar_one_or_none()
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found.")
    return dataset


async def _latest_hitl(db: AsyncSession, dataset_id: uuid.UUID, checkpoint: str) -> HITLDecision | None:
    result = await db.execute(
        select(HITLDecision)
        .where(HITLDecision.dataset_id == dataset_id, HITLDecision.checkpoint == checkpoint)
        .order_by(HITLDecision.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _latest_hitl_json(db: AsyncSession, dataset_id: uuid.UUID, checkpoint: str) -> dict:
    decision = await _latest_hitl(db, dataset_id, checkpoint)
    return decision.proposal_json if decision else {}
