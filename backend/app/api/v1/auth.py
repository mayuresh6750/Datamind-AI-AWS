"""Auth endpoints — signup, login, refresh, logout via Native RDS & JWT."""
import uuid
import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.models.db import User, Tenant
from app.models.schemas import AuthResponse, LoginRequest, SignUpRequest

log = structlog.get_logger()
router = APIRouter()


async def _get_or_create_default_tenant(db: AsyncSession) -> Tenant:
    """Ensure at least one tenant exists for users."""
    res = await db.execute(select(Tenant).limit(1))
    tenant = res.scalar_one_or_none()
    if tenant is None:
        tenant = Tenant(name="Default Tenant")
        db.add(tenant)
        await db.commit()
        await db.refresh(tenant)
    return tenant


@router.post("/signup", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def signup(body: SignUpRequest, db: AsyncSession = Depends(get_db)):
    # Check if user already exists
    res = await db.execute(select(User).where(User.email == body.email))
    existing_user = res.scalar_one_or_none()
    if existing_user is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User already registered. Please use the login endpoint instead.",
        )

    tenant = await _get_or_create_default_tenant(db)
    pwd_hash = hash_password(body.password)

    new_user = User(
        tenant_id=tenant.tenant_id,
        email=body.email,
        hashed_password=pwd_hash,
        role="user",
        active_domain="other",
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    user_id_str = str(new_user.user_id)
    token_payload = {"sub": user_id_str, "email": new_user.email, "role": new_user.role}

    return AuthResponse(
        access_token=create_access_token(token_payload),
        refresh_token=create_refresh_token(token_payload),
        user_id=user_id_str,
        role=new_user.role,
        active_domain=new_user.active_domain,
    )


@router.post("/login", response_model=AuthResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(User).where(User.email == body.email))
    user = res.scalar_one_or_none()

    if user is None or not user.hashed_password:
        log.warning("login_failed_user_not_found", email=body.email)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials.")

    if not verify_password(body.password, user.hashed_password):
        log.warning("login_failed_password_mismatch", email=body.email)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials.")

    user_id_str = str(user.user_id)
    token_payload = {"sub": user_id_str, "email": user.email, "role": user.role}

    return AuthResponse(
        access_token=create_access_token(token_payload),
        refresh_token=create_refresh_token(token_payload),
        user_id=user_id_str,
        role=user.role,
        active_domain=user.active_domain,
    )


@router.post("/refresh", response_model=AuthResponse)
async def refresh(refresh_token: str, db: AsyncSession = Depends(get_db)):
    try:
        payload = decode_token(refresh_token)
        if payload.get("type") != "refresh":
            raise ValueError("Not a refresh token")
        user_id_str = payload.get("sub")
        if not user_id_str:
            raise ValueError("Missing subject")
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token.",
        )

    res = await db.execute(select(User).where(User.user_id == uuid.UUID(user_id_str)))
    user = res.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found.")

    token_payload = {"sub": str(user.user_id), "email": user.email, "role": user.role}

    return AuthResponse(
        access_token=create_access_token(token_payload),
        refresh_token=create_refresh_token(token_payload),
        user_id=str(user.user_id),
        role=user.role,
        active_domain=user.active_domain,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(access_token: str):
    # Stateless JWT logout
    return None
