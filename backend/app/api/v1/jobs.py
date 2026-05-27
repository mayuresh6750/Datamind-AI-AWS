"""Job status polling and audit log endpoints."""
import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.db import AuditLog, PipelineRun
from app.models.schemas import JobStatus

log = structlog.get_logger()
router = APIRouter()

CurrentUser = Annotated[dict, Depends(get_current_user)]

# In-memory job registry (P1 — BackgroundTasks has no persistent job store)
# Keyed job_id → {"status": str, "progress_pct": int, "current_step": str, "error": str | None}
_job_registry: dict[str, dict] = {}


def register_job(job_id: str) -> None:
    _job_registry[job_id] = {"status": "queued", "progress_pct": 0, "current_step": None, "error": None}


def update_job(job_id: str, status: str, progress_pct: int = 0, current_step: str | None = None, error: str | None = None) -> None:
    if job_id in _job_registry:
        _job_registry[job_id] = {"status": status, "progress_pct": progress_pct, "current_step": current_step, "error": error}


@router.get("/{job_id}", response_model=JobStatus)
async def get_job_status(job_id: str, current_user: CurrentUser):
    info = _job_registry.get(job_id)
    if info is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return JobStatus(job_id=job_id, **info)


@router.get("/{job_id}/audit")
async def get_audit_log(
    job_id: str,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PipelineRun).where(PipelineRun.run_id == uuid.UUID(job_id))
    )
    run = result.scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="Pipeline run not found.")

    audit_result = await db.execute(
        select(AuditLog).where(AuditLog.run_id == uuid.UUID(job_id)).order_by(AuditLog.created_at)
    )
    entries = audit_result.scalars().all()

    return JSONResponse(content=[
        {
            "entry_id": str(e.entry_id),
            "agent_name": e.agent_name,
            "action_type": e.action_type,
            "rows_affected": e.rows_affected,
            "rationale": e.rationale,
            "confidence": float(e.confidence) if e.confidence else None,
            "llm_provider": e.llm_provider,
            "llm_model": e.llm_model,
            "tokens_used": e.tokens_used,
            "created_at": e.created_at.isoformat(),
        }
        for e in entries
    ])
