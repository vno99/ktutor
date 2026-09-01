"""FastAPI application entry point (s09).

The application is intentionally minimal:

* :func:`lifespan` initializes the database schema via
  :func:`app.core.database.session.init_db`. No LLM / ChromaDB warm-up
  (YAGNI: the first request pays the cost; subsequent requests hit
  the cached client).
* :class:`fastapi.middleware.cors.CORSMiddleware` is registered with
  the operator-configured allow-list (``Settings.cors_allow_origins``).
  The default is ``http://localhost:3000`` (Next.js dev server).
* The :mod:`app.api.chat.router` router is mounted under ``/api/chat``.

Subsequent stories (s10 documents, s12 auth, etc.) will add their own
routers here.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.chat.router import router as chat_router
from app.core.config import get_settings
from app.core.database.session import init_db


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Initialize the database schema on startup.

    ``init_db`` is idempotent (``Base.metadata.create_all`` is a no-op
    when the tables already exist) so the lifespan can be invoked
    safely on every reload.
    """
    init_db()
    yield


settings = get_settings()

app = FastAPI(
    title="ktutor API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router)


__all__ = ["app"]
