import pytest
from datetime import timedelta
from fastapi import HTTPException

from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
    require_admin,
)
from fastapi.security import HTTPAuthorizationCredentials


def test_password_hashing():
    """Verify password hashing produces salted, verifiable hashes."""
    pwd = "SecurePassword123!"
    h1 = hash_password(pwd)
    h2 = hash_password(pwd)

    # Different salts must produce different hashes
    assert h1 != h2
    assert verify_password(pwd, h1) is True
    assert verify_password(pwd, h2) is True
    assert verify_password("WrongPassword", h1) is False


def test_token_creation_and_decoding():
    """Verify JWT access and refresh token creation and decoding."""
    payload = {"sub": "123e4567-e89b-12d3-a456-426614174000", "email": "test@datamind.ai", "role": "admin"}
    token = create_access_token(payload)
    decoded = decode_token(token)

    assert decoded["sub"] == payload["sub"]
    assert decoded["email"] == payload["email"]
    assert decoded["role"] == "admin"
    assert decoded["type"] == "access"
    assert "exp" in decoded


def test_expired_token_raises_401():
    """Verify expired token raises 401."""
    payload = {"sub": "123", "email": "exp@datamind.ai"}
    # Token expired 10 minutes ago
    token = create_access_token(payload, expires_delta=timedelta(minutes=-10))

    with pytest.raises(HTTPException) as exc_info:
        decode_token(token)
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_valid_token():
    """Verify get_current_user extracts credentials properly."""
    payload = {"sub": "123e4567-e89b-12d3-a456-426614174000", "email": "analyst@datamind.ai", "role": "user"}
    token = create_access_token(payload)
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    user = await get_current_user(creds)
    assert user["user_id"] == payload["sub"]
    assert user["email"] == payload["email"]
    assert user["role"] == "user"


@pytest.mark.asyncio
async def test_require_admin_guard():
    """Verify require_admin permits admin and rejects non-admin."""
    admin_user = {"user_id": "1", "role": "admin"}
    regular_user = {"user_id": "2", "role": "user"}

    # Should succeed for admin
    assert await require_admin(admin_user) == admin_user

    # Should fail for standard user
    with pytest.raises(HTTPException) as exc:
        await require_admin(regular_user)
    assert exc.value.status_code == 403
