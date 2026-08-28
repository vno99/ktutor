"""SQLAlchemy engine, session factory, and FastAPI dependency for the DB."""

from __future__ import annotations

from collections.abc import Generator
from typing import TYPE_CHECKING

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.database.models import Base

if TYPE_CHECKING:
    from fastapi import Depends  # noqa: F401  - re-export for callers


def _build_engine():
    settings = get_settings()
    return create_engine(
        settings.database_url,
        pool_size=settings.database_pool_size,
        future=True,
    )


_engine = None
_SessionLocal: sessionmaker[Session] | None = None


def get_engine():
    """Lazily build the SQLAlchemy engine (deferred so tests can override env)."""
    global _engine
    if _engine is None:
        _engine = _build_engine()
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    """Lazily build the session factory."""
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)
    return _SessionLocal


def reset_engine() -> None:
    """Reset the cached engine / session factory (test-only)."""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None


def init_db() -> None:
    """Create all tables. Used at CLI startup; Alembic will own migrations later."""
    Base.metadata.create_all(bind=get_engine())


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: yield a session, ensure close."""
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()
