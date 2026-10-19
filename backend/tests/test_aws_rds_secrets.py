import pytest
from app.core.secrets import get_database_credentials, build_database_url
from app.core.config import settings

def test_secrets_manager_retrieval():
    """Verify Secrets Manager successfully fetches database credentials."""
    creds = get_database_credentials()
    assert isinstance(creds, dict)
    assert "username" in creds
    assert "password" in creds
    assert creds["username"] == "postgres"

def test_build_database_url():
    """Verify database URL builder constructs proper asyncpg & psycopg2 connection strings."""
    url_async = build_database_url(sync=False)
    url_sync = build_database_url(sync=True)

    assert url_async.startswith("postgresql+asyncpg://")
    assert url_sync.startswith("postgresql+psycopg2://")
    assert "database-1.crimi0cgox0o.eu-north-1.rds.amazonaws.com" in url_async
    assert "database-1.crimi0cgox0o.eu-north-1.rds.amazonaws.com" in url_sync
    assert "ssl=require" in url_async
