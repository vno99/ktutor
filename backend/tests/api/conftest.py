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


@pytest.fixture()
def fresh_settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    """A :class:`Settings` instance with a known CORS allow-list."""
    get_settings.cache_clear()  # type: ignore[attr-defined]
    settings = Settings(
        cors_allow_origins="http://localhost:3000",
    )
    monkeypatch.setattr("app.core.config.get_settings", lambda: settings)
    return settings
