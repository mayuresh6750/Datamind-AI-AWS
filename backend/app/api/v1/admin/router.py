"""Admin endpoints — users, LLM provider config, domain packs, health, audit."""
import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, get_supabase
from app.core.security import require_admin
from app.models.db import AuditLog, Dataset, LLMProviderConfig, PipelineRun, User

log = structlog.get_logger()
router = APIRouter()

AdminUser = Annotated[dict, Depends(require_admin)]


# ─── Request/Response Models ──────────────────────────────────────────────────

class CreateUserRequest(BaseModel):
    email: EmailStr
    password: str
    role: str = "user"  # 'user' or 'admin'

    class Config:
        example = {"email": "newuser@example.com", "password": "SecurePass123!", "role": "user"}


class UserResponse(BaseModel):
    user_id: str
    email: str
    role: str
    active_domain: str
    created_at: str


# ─── Users ───────────────────────────────────────────────────────────────────

@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: CreateUserRequest,
    current_user: AdminUser,
    db: AsyncSession = Depends(get_db),
):
    """Create a new user with specified role. Admin only.

    Sets role in Supabase Auth metadata so JWT contains the role.
    """
    if body.role not in ("user", "admin"):
        raise HTTPException(status_code=400, detail="role must be 'user' or 'admin'.")

    supabase = get_supabase()

    # Create user in Supabase Auth with role in metadata
    try:
        auth_response = supabase.auth.admin.create_user(
            email=body.email,
            password=body.password,
            user_metadata={"role": body.role},
            email_confirm=True,  # Auto-confirm email for admin-created users
        )
    except Exception as exc:
        log.warning("create_user_auth_failed", email=body.email, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to create user in auth: {str(exc)}"
        )

    if auth_response.user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to create user — unknown error."
        )

    # Create user record in public.users table
    user_id = uuid.UUID(str(auth_response.user.id))
    user = User(
        user_id=user_id,
        tenant_id=uuid.UUID(current_user["user_id"]),  # Assign to same tenant as admin
        email=body.email,
        role=body.role,
        active_domain="other",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    return UserResponse(
        user_id=str(user.user_id),
        email=user.email,
        role=user.role,
        active_domain=user.active_domain,
        created_at=user.created_at.isoformat(),
    )


@router.get("/users")
async def list_users(current_user: AdminUser, db: AsyncSession = Depends(get_db)):
    """List all users. Admin only."""
    result = await db.execute(select(User))
    users = result.scalars().all()
    return [
        {
            "user_id": str(u.user_id),
            "email": u.email,
            "role": u.role,
            "active_domain": u.active_domain,
            "created_at": u.created_at.isoformat(),
        }
        for u in users
    ]


@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: uuid.UUID,
    current_user: AdminUser,
    db: AsyncSession = Depends(get_db),
):
    """Get a specific user. Admin only."""
    result = await db.execute(select(User).where(User.user_id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")

    return UserResponse(
        user_id=str(user.user_id),
        email=user.email,
        role=user.role,
        active_domain=user.active_domain,
        created_at=user.created_at.isoformat(),
    )


@router.patch("/users/{user_id}/role")
async def update_user_role(
    user_id: uuid.UUID,
    role: str,
    current_user: AdminUser,
    db: AsyncSession = Depends(get_db),
):
    """Promote/demote a user role. Admin only.

    Updates both the local database and Supabase Auth metadata.
    """
    if role not in ("user", "admin"):
        raise HTTPException(status_code=400, detail="role must be 'user' or 'admin'.")

    result = await db.execute(select(User).where(User.user_id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")

    # Update in local database
    user.role = role
    await db.commit()

    # Update in Supabase Auth metadata
    supabase = get_supabase()
    try:
        supabase.auth.admin.update_user_by_id(
            str(user_id),
            {"user_metadata": {"role": role}}
        )
    except Exception as exc:
        log.warning("update_user_role_auth_failed", user_id=str(user_id), error=str(exc))
        # Don't fail if auth update fails; local DB is source of truth

    return {"user_id": str(user_id), "role": role}


# ─── LLM Provider Config ─────────────────────────────────────────────────────

@router.get("/llm-providers")
async def get_llm_config(current_user: AdminUser, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(LLMProviderConfig))
    configs = result.scalars().all()
    return [
        {
            "config_id": str(c.config_id),
            "tenant_id": str(c.tenant_id),
            "default_provider": c.default_provider,
            "default_model": c.default_model,
            "per_agent_overrides": c.per_agent_overrides,
            "updated_at": c.updated_at.isoformat(),
        }
        for c in configs
    ]


@router.put("/llm-providers/{config_id}")
async def update_llm_config(
    config_id: uuid.UUID,
    default_provider: str,
    default_model: str,
    current_user: AdminUser,
    db: AsyncSession = Depends(get_db),
    per_agent_overrides: dict = {},
):
    result = await db.execute(select(LLMProviderConfig).where(LLMProviderConfig.config_id == config_id))
    config = result.scalar_one_or_none()
    if config is None:
        raise HTTPException(status_code=404, detail="Config not found.")

    config.default_provider = default_provider
    config.default_model = default_model
    config.per_agent_overrides = per_agent_overrides
    config.updated_by_user_id = uuid.UUID(current_user["user_id"])
    await db.commit()
    return {"updated": True}


@router.get("/llm-providers/usage")
async def get_llm_usage(current_user: AdminUser, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(
            PipelineRun.llm_provider,
            func.sum(PipelineRun.total_llm_tokens).label("total_tokens"),
            func.sum(PipelineRun.total_llm_cost_usd).label("total_cost_usd"),
            func.count(PipelineRun.run_id).label("pipeline_count"),
        ).group_by(PipelineRun.llm_provider)
    )
    rows = result.all()
    return [
        {
            "provider": r.llm_provider,
            "total_tokens": r.total_tokens or 0,
            "total_cost_usd": float(r.total_cost_usd or 0),
            "pipeline_count": r.pipeline_count,
        }
        for r in rows
    ]


# ─── Domain Packs ────────────────────────────────────────────────────────────

@router.get("/domain-packs")
async def list_domain_packs(current_user: AdminUser):
    from app.agents.domain import DOMAIN_PACKS
    return [{"domain": k, "kpis": v.get("kpis", []), "vocab_count": len(v.get("vocab", []))} for k, v in DOMAIN_PACKS.items()]


# ─── System Health ───────────────────────────────────────────────────────────

@router.get("/health")
async def system_health(current_user: AdminUser, db: AsyncSession = Depends(get_db)):
    queued = await db.scalar(
        select(func.count(PipelineRun.run_id)).where(PipelineRun.status.in_(["queued", "running"]))
    )
    failed_24h = await db.scalar(
        select(func.count(PipelineRun.run_id)).where(
            PipelineRun.status == "failed",
        )
    )
    return {"queued_jobs": queued, "failed_24h": failed_24h}


# ─── Audit Log ───────────────────────────────────────────────────────────────

@router.get("/audit")
async def search_audit(
    current_user: AdminUser,
    checkpoint: str | None = None,
    agent_name: str | None = None,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
):
    query = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(min(limit, 1000))
    if agent_name:
        query = query.where(AuditLog.agent_name == agent_name)
    result = await db.execute(query)
    entries = result.scalars().all()
    return [
        {
            "entry_id": str(e.entry_id),
            "dataset_id": str(e.dataset_id) if e.dataset_id else None,
            "run_id": str(e.run_id) if e.run_id else None,
            "agent_name": e.agent_name,
            "action_type": e.action_type,
            "rows_affected": e.rows_affected,
            "rationale": e.rationale,
            "confidence": float(e.confidence) if e.confidence else None,
            "created_at": e.created_at.isoformat(),
        }
        for e in entries
    ]
