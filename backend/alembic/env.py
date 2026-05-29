import os
from logging.config import fileConfig

from sqlalchemy import create_engine, pool

from alembic import context

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

from app.core.database import Base
from app.models import db as _models  # noqa: F401 — ensures models are registered

target_metadata = Base.metadata


def get_sync_url() -> str:
    """
    Convert asyncpg URL to psycopg2 for Alembic (sync driver required).
    Also strips ?ssl=require from URL and passes it via connect_args instead.
    """
    url = os.environ.get("DATABASE_URL") or config.get_main_option("sqlalchemy.url", "")
    url = url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")
    url = url.replace("postgresql://", "postgresql+psycopg2://")
    # Remove ssl param from URL — passed via connect_args below
    url = url.split("?")[0]
    return url


def run_migrations_offline() -> None:
    context.configure(
        url=get_sync_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(
        get_sync_url(),
        poolclass=pool.NullPool,
        connect_args={"sslmode": "require"},
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
