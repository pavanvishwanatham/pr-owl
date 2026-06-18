"""
Async database engine and session factory.
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from core.config import get_settings

_engine = None
_SessionLocal = None


def _get_engine():
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            get_settings().database_url,
            echo=False,
            pool_pre_ping=True,
        )
    return _engine


def get_session_factory():
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            bind=_get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _SessionLocal


async def init_db():
    """Create all tables on startup."""
    from db import models  # noqa: F401 — ensures models are registered
    async with _get_engine().begin() as conn:
        await conn.run_sync(lambda c: SQLModel.metadata.create_all(c, checkfirst=True))


async def get_session() -> AsyncSession:
    """FastAPI dependency for getting a DB session."""
    factory = get_session_factory()
    async with factory() as session:
        yield session
