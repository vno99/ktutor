"""Shared fixtures for the API tests (s09).

The :func:`client` fixture exposes a FastAPI :class:`TestClient` against
the application built from the live :class:`Settings`. The application
is created once per session and the supervisor is replaced by a stub
via :func:`supervisor_dependency` so the tests do not need a real LLM
or ChromaDB.

The stub supervisor implements the :class:`SubjectAgent` Protocol with
two pre-canned behaviours (configured per-test via
:func:`supervisor_dependency`):

* ``"happy"`` — yields a fixed sequence of tokens then a done event.
* ``"cross_tenant"`` — raises ``ValueError("different pseudo requested")``
  for any request whose ``pseudo`` is not ``"alice"``. The router
  catches the error and forwards it as an ``error`` SSE event.
* ``"reject_subject"`` — raises ``ValueError("Unknown subject: histoire")``
  so the ``_map_code`` helper is exercised.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass, field
from typing import Any, Literal

import pytest
from fastapi.testclient import TestClient

# Force a known CORS allow-list BEFORE the app module reads the settings
# singleton, so the test environment is deterministic regardless of any
# ``.env`` file the operator may have. ``get_settings`` is a plain
# function (not a ``functools.lru_cache``) that internally caches via a
# module-level ``_settings`` variable, so we reset that cache here.
from app.core import config as _config_module
from app.core.config import Settings, get_settings
from app.main import app
from app.services.agents import StreamChunk
from app.services.agents.supervisor import SubjectSupervisor
from app.services.agents.types import SourceCitation

_config_module.reset_settings()


@dataclass
class _StubAgent:
    """A minimal SubjectAgent double for the TestClient suite.

    The :class:`SubjectSupervisor` constructor validates the subject
    keys against the canonical :class:`Subject` enum, so this stub
    must be registered under ``"maths"`` and ``"francais"``.
    """

    subject: str
    tokens: list[str] = field(default_factory=list)
    sources: list[SourceCitation] = field(default_factory=list)
    behaviour: Literal["happy", "raise_subject", "raise_cross_tenant", "raise_unknown"] = "happy"
    ask_calls: list[tuple[str, str, str]] = field(default_factory=list)
    astream_calls: list[tuple[str, str, str]] = field(default_factory=list)

    def ask(self, subject: str, pseudo: str, question: str) -> Any:
        self.ask_calls.append((subject, pseudo, question))
        return None

    async def astream(
        self, subject: str, pseudo: str, question: str
    ) -> AsyncIterator[StreamChunk]:
        self.astream_calls.append((subject, pseudo, question))
        if self.behaviour == "raise_subject":
            raise ValueError(f"Unknown subject: {subject}")
        if self.behaviour == "raise_cross_tenant":
            raise ValueError("Cannot query a different pseudo collection.")
        if self.behaviour == "raise_unknown":
            raise ValueError("Boom.")
        for token in self.tokens:
            yield StreamChunk(content=token, event="token")
        yield StreamChunk(content="", event="done", sources=list(self.sources))


@pytest.fixture()
def maths_stub() -> _StubAgent:
    return _StubAgent(subject="maths", tokens=["Hel", "lo ", "world"])


@pytest.fixture()
def francais_stub() -> _StubAgent:
    return _StubAgent(subject="francais", tokens=["Une ", "métaphore."])


@pytest.fixture()
def supervisor_stub(
    maths_stub: _StubAgent, francais_stub: _StubAgent
) -> SubjectSupervisor:
    """Build a supervisor whose agents are the :class:`_StubAgent` doubles."""
    return SubjectSupervisor(
        {"maths": maths_stub, "francais": francais_stub}
    )


@pytest.fixture()
def override_supervisor(supervisor_stub: SubjectSupervisor) -> Iterator[None]:
    """Replace the FastAPI dependency ``_build_supervisor_dep`` for one test."""
    from app.api.chat.router import _build_supervisor_dep

    app.dependency_overrides[_build_supervisor_dep] = lambda: supervisor_stub
    yield
    app.dependency_overrides.pop(_build_supervisor_dep, None)


@pytest.fixture()
def client(override_supervisor: None) -> Iterator[TestClient]:
    """A :class:`TestClient` bound to ``app`` with the stub supervisor."""
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# s10 — documents upload fixtures
# ---------------------------------------------------------------------------
#
# The documents router calls ``app.api.documents.factory.get_upload_service_dep``
# per request. Tests inject a configurable stub via FastAPI's
# ``dependency_overrides`` so the real S3 / Chroma / OCR backends are
# never touched. The stub's ``upload`` method can be parametrized per test
# to return a successful ``UploadResult`` or raise a controlled
# ``UploadError``.


class _StubUploadService:
    """Programmable double for :class:`UploadService`.

    By default returns a successful ``UploadResult`` with a fixed
    ``document_id``, ``chunks_count=3`` and ``status=INDEXED``. Tests
    can override:

    * :attr:`return_result` to control the returned object
    * :attr:`raise_with` to raise a controlled ``UploadError``
    * :attr:`call_log` to inspect the arguments the router passed
    """

    def __init__(self) -> None:
        from app.core.database.models import DocumentStatus
        from app.services.rag.upload_service import UploadResult

        self.calls: list[tuple[str, str, str]] = []
        self.raise_with: Exception | None = None
        self.return_result: object = UploadResult(
            document_id=uuid.UUID("12345678-1234-5678-1234-567812345678"),
            chunks_count=3,
            duration_ms=42,
            status=DocumentStatus.INDEXED,
            collection="rag_maths_alice",
            s3_key="students/alice/12345678-1234-5678-1234-567812345678/cours.pdf",
            ocr_confidence=None,
        )

    def upload(self, file_path: str, pseudo: str, subject: str) -> object:
        self.calls.append((file_path, pseudo, subject))
        if self.raise_with is not None:
            raise self.raise_with
        return self.return_result


@pytest.fixture()
def upload_service_stub() -> _StubUploadService:
    """A programmable :class:`UploadService` double."""
    return _StubUploadService()


@pytest.fixture()
def override_upload_service(
    upload_service_stub: _StubUploadService,
) -> Iterator[None]:
    """Replace the FastAPI dependency ``get_upload_service_dep`` for one test."""
    from app.api.documents.factory import get_upload_service_dep

    app.dependency_overrides[get_upload_service_dep] = lambda: upload_service_stub
    yield
    app.dependency_overrides.pop(get_upload_service_dep, None)


@pytest.fixture()
def documents_client(override_upload_service: None) -> Iterator[TestClient]:
    """A :class:`TestClient` bound to ``app`` with the stub upload service.

    The supervisor override is NOT applied — these tests do not exercise
    the chat router. The lifespan still runs (init_db best-effort) but
    the upload service is fully stubbed.
    """
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def fresh_settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    """A :class:`Settings` instance with a known CORS allow-list."""
    get_settings.cache_clear()  # type: ignore[attr-defined]
    settings = Settings(
        cors_allow_origins="http://localhost:3000",
    )
    monkeypatch.setattr("app.core.config.get_settings", lambda: settings)
    return settings
