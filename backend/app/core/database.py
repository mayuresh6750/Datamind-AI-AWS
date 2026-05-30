from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from supabase import Client, create_client

from app.core.config import settings

# ─── SQLAlchemy async engine ──────────────────────────────────────────────────
import ssl as _ssl

_db_url = settings.database_url.split("?")[0]  # strip ?ssl=require from URL

_ssl_ctx = _ssl.create_default_context()
_ssl_ctx.check_hostname = False
_ssl_ctx.verify_mode = _ssl.CERT_NONE

engine = create_async_engine(
    _db_url,
    echo=False,
    connect_args={"ssl": _ssl_ctx},
    pool_size=5,
    max_overflow=10,
)

AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ─── Supabase client (service role — server-side only) ───────────────────────
supabase_client: Client = create_client(
    settings.supabase_url,
    settings.supabase_service_role_key,
)


def get_supabase() -> Client:
    return supabase_client
