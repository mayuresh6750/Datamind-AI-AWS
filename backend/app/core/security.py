from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from supabase import Client

from app.core.database import get_supabase

bearer_scheme = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    supabase: Client = Depends(get_supabase),
) -> dict:
    """Validate Supabase Auth JWT and return the user payload."""
    token = credentials.credentials
    try:
        response = supabase.auth.get_user(token)
        if response.user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"error": "AUTHENTICATION_ERROR", "code": "AUTH_TOKEN_INVALID"},
            )
        return {
            "user_id": response.user.id,
            "email": response.user.email,
            "role": (response.user.user_metadata or {}).get("role", "user"),
        }
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "AUTHENTICATION_ERROR", "code": "AUTH_TOKEN_INVALID"},
        )


async def require_admin(
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Require the caller to have the admin role."""
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "AUTHORIZATION_ERROR", "code": "RBAC_INSUFFICIENT_ROLE"},
        )
    return current_user
