"""Dashboard generation endpoint."""
import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.db import Dataset
from app.models.schemas import DashboardSpec, JobResponse

log = structlog.get_logger()
router = APIRouter()

CurrentUser = Annotated[dict, Depends(get_current_user)]

# In-memory dashboard cache: dataset_id → DashboardSpec dict
_dashboard_cache: dict[str, dict] = {}


@router.post("/generate", response_model=JobResponse)
async def generate_dashboard(
    dataset_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    job_id_override: str | None = None,
):
    result = await db.execute(
        select(Dataset).where(Dataset.dataset_id == dataset_id, Dataset.user_id == uuid.UUID(current_user["sub"]))
    )
    dataset = result.scalar_one_or_none()
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found.")
    if dataset.status != "ready":
        raise HTTPException(status_code=409, detail="Dataset not ready for dashboard generation.")

    job_id = job_id_override or str(uuid.uuid4())
    from app.workers.tasks import run_dashboard_pipeline
    background_tasks.add_task(run_dashboard_pipeline, str(dataset_id), str(current_user["sub"]), job_id)

    return JobResponse(job_id=job_id, status="queued")


@router.get("/{dataset_id}", response_model=DashboardSpec)
async def get_dashboard(
    dataset_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Dataset).where(Dataset.dataset_id == dataset_id, Dataset.user_id == uuid.UUID(current_user["sub"]))
    )
    dataset = result.scalar_one_or_none()
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found.")

    cached = _dashboard_cache.get(str(dataset_id))
    if cached is None:
        raise HTTPException(status_code=404, detail="Dashboard not yet generated.")

    return DashboardSpec.model_validate(cached)


def cache_dashboard(dataset_id: str, spec: DashboardSpec) -> None:
    _dashboard_cache[dataset_id] = spec.model_dump()
