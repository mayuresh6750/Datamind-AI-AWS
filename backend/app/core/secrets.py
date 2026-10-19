"""AWS Secrets Manager integration for secure credential retrieval."""
import json
import logging
import time
from typing import Any
import urllib.parse

import boto3
from botocore.exceptions import ClientError

from app.core.config import settings

logger = logging.getLogger(__name__)

# In-memory secret cache with TTL to avoid calling AWS on every single DB request
_SECRETS_CACHE: dict[str, tuple[float, Any]] = {}
_CACHE_TTL_SECONDS = 300.0  # 5 minutes


def get_secret(
    secret_id: str,
    region_name: str | None = None,
    ttl_seconds: float = _CACHE_TTL_SECONDS,
) -> Any:
    """
    Retrieve and parse a secret from AWS Secrets Manager with TTL caching.
    """
    region = region_name or getattr(settings, "aws_db_region", "eu-north-1")
    cache_key = f"{region}:{secret_id}"
    now = time.monotonic()

    if cache_key in _SECRETS_CACHE:
        cached_at, value = _SECRETS_CACHE[cache_key]
        if now - cached_at < ttl_seconds:
            return value

    client = boto3.client(
        "secretsmanager",
        region_name=region,
        aws_access_key_id=settings.aws_access_key_id or None,
        aws_secret_access_key=settings.aws_secret_access_key or None,
    )

    try:
        response = client.get_secret_value(SecretId=secret_id)
    except ClientError as e:
        logger.error("Failed to retrieve secret '%s' from region '%s': %s", secret_id, region, e)
        raise

    secret_str = response.get("SecretString")
    if secret_str:
        try:
            parsed = json.loads(secret_str)
            _SECRETS_CACHE[cache_key] = (now, parsed)
            return parsed
        except json.JSONDecodeError:
            _SECRETS_CACHE[cache_key] = (now, secret_str)
            return secret_str

    binary_data = response.get("SecretBinary")
    _SECRETS_CACHE[cache_key] = (now, binary_data)
    return binary_data


def get_database_credentials() -> dict[str, str]:
    """
    Fetch RDS master credentials from AWS Secrets Manager.
    Returns dict containing at minimum 'username' and 'password'.
    """
    secret_id = getattr(settings, "aws_db_secret_name", "")
    if not secret_id:
        raise ValueError("AWS DB secret name is not configured in settings.")
    region = getattr(settings, "aws_db_region", "eu-north-1")
    creds = get_secret(secret_id, region_name=region)
    if not isinstance(creds, dict):
        raise ValueError(f"Expected dict secret for RDS credentials, got {type(creds)}")
    return creds


def build_database_url(sync: bool = False) -> str:
    """
    Dynamically build SQLAlchemy DATABASE_URL using AWS Secrets Manager.
    If database_url is already explicitly set in settings, it will use that.
    """
    # If explicitly configured and valid, use it
    if settings.database_url and "change-me" not in settings.database_url:
        url = settings.database_url
        if sync:
            url = url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")
            url = url.replace("postgresql://", "postgresql+psycopg2://")
        return url

    # Otherwise construct dynamically from AWS Secrets Manager
    creds = get_database_credentials()
    user = urllib.parse.quote_plus(creds.get("username", "postgres"))
    pwd = urllib.parse.quote_plus(creds.get("password", ""))
    host = getattr(settings, "aws_db_host", "localhost")
    port = getattr(settings, "aws_db_port", 5432)
    db = getattr(settings, "aws_db_name", "postgres")

    driver = "postgresql+psycopg2" if sync else "postgresql+asyncpg"
    return f"{driver}://{user}:{pwd}@{host}:{port}/{db}?ssl=require"
