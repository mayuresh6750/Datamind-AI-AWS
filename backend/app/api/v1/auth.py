"""Auth endpoints — signup, login, refresh, logout via Supabase Auth."""
import uuid
import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_supabase, get_db
from app.models.schemas import AuthResponse, LoginRequest, SignUpRequest

log = structlog.get_logger()
router = APIRouter()


async def _get_active_domain(user_id: str, db: AsyncSession) -> str | None:
    """Fetch the user's active_domain from the users table — non-fatal."""
    try:
        from app.models.db import User
        result = await db.execute(select(User).where(User.user_id == uuid.UUID(user_id)))
        user = result.scalar_one_or_none()
        return user.active_domain if user else None
    except Exception:
        return None


@router.post("/signup", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def signup(body: SignUpRequest):
    supabase = get_supabase()
    try:
        res = supabase.auth.sign_up({"email": body.email, "password": body.password})
    except Exception as exc:
        log.warning("signup_failed", email=body.email, error=str(exc))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    if res.user is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Signup failed — check email/password.")

    if res.session is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User already registered. Please use the login endpoint instead.",
        )

    return AuthResponse(
        access_token=res.session.access_token,
        refresh_token=res.session.refresh_token,
        user_id=str(res.user.id),
        role=(res.user.user_metadata or {}).get("role", "user"),
    )


@router.post("/login", response_model=AuthResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    supabase = get_supabase()
    try:
        res = supabase.auth.sign_in_with_password({"email": body.email, "password": body.password})
    except Exception as exc:
        log.warning("login_failed", error=str(exc))
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials.")

    if res.session is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials.")

    role = (res.user.user_metadata or {}).get("role", "user") if res.user else "user"
    user_id = str(res.user.id)
    active_domain = await _get_active_domain(user_id, db)

    return AuthResponse(
        access_token=res.session.access_token,
        refresh_token=res.session.refresh_token,
        user_id=user_id,
        role=role,
        active_domain=active_domain,
    )


@router.post("/refresh", response_model=AuthResponse)
async def refresh(refresh_token: str):
    supabase = get_supabase()
    try:
        res = supabase.auth.refresh_session(refresh_token)
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token.")

    role = (res.user.user_metadata or {}).get("role", "user") if res.user else "user"
    return AuthResponse(
        access_token=res.session.access_token,
        refresh_token=res.session.refresh_token,
        user_id=str(res.user.id),
        role=role,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(access_token: str):
    supabase = get_supabase()
    try:
        supabase.auth.sign_out()
    except Exception:
        pass  # best-effort logout
