from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

# ─── SQLAlchemy async engine ──────────────────────────────────────────────────
import ssl as _ssl

_raw_url = settings.database_url
if not _raw_url:
    try:
        from app.core.secrets import build_database_url
        _raw_url = build_database_url(sync=False)
    except Exception:
        _raw_url = "postgresql+asyncpg://localhost/postgres"

_db_url = _raw_url.split("?")[0]  # strip ?ssl=require from URL

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


# ─── Legacy client stub (Supabase fully deprecated in favor of AWS) ──────────
def get_supabase():
    return None
