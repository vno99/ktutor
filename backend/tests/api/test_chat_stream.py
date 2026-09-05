"""Tests for ``POST /api/chat/stream`` (s09, s15).

The suite covers every acceptance criterion in the original story
plus the s15 cross-tenant bite required by the repo Definition
of Done (AGENTS.md):

* AC1 — JSON body, ``text/event-stream`` content type.
* AC2 — Each event carries one token chunk.
* AC3 — Final event is ``{done: True, sources: [...]}``.
* AC4 — Agent error becomes an ``{error, code}`` event and the
  connection closes.
* AC5 — CORS preflight works for the allow-listed origin and is
  refused for any other.
* AC6 — Tokens arrive in order.
* AC7 — A request with missing fields returns 422 BEFORE any stream
  is opened.

The s15 cross-tenant bite is :class:`TestChatStreamCrossTenant` — a
bearer token for ``bob`` is forged, the body has no ``pseudo``,
and the supervisor is observed to receive ``pseudo="bob"`` (not
``"alice"``). A regression that hard-coded ``"alice"`` in the
router, or read the body ``pseudo`` after s15 retired the field,
would be caught here. The HTTP-level bite
:func:`TestChatStreamJwtRequired` proves the endpoint rejects
unauthenticated callers with 401.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import sessionmaker

from app.core.auth.jwt import create_access_token
from app.core.auth.passwords import hash_password
from app.core.database.models import Base, User, UserRole
from app.core.database.session import get_db
from app.main import app


def _events_from_response(response) -> list[dict]:
    """Parse an SSE response body into a list of payload dicts."""
    events: list[dict] = []
    for line in response.text.splitlines():
        if not line.startswith("data: "):
            continue
        payload = line[len("data: ") :]
        events.append(json.loads(payload))
    return events


# ---------------------------------------------------------------------------
# JWT fixtures — duplicated from tests/api/test_users_create.py (AGENTS.md:
# « Pas de refactor transverse »). The chat tests need a real seeded
# User whose ``pseudo`` the JWT can carry — the s09 chat tests did not
# authenticate, so the fixtures were simpler. After s15 the router
# requires ``Depends(get_current_user)``; this is the matching setup.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def rsa_keypair(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    tmp = tmp_path_factory.mktemp("jwt_keys_chat_stream")
    private_path = tmp / "jwt_private.pem"
    public_path = tmp / "jwt_public.pem"
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    private_path.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    public_path.write_bytes(
        public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    return {"private": private_path, "public": public_path}


@pytest.fixture(autouse=True)
def _point_settings(
    monkeypatch: pytest.MonkeyPatch, rsa_keypair: dict[str, Path]
) -> None:
    monkeypatch.setenv("JWT_PRIVATE_KEY_PATH", str(rsa_keypair["private"]))
    monkeypatch.setenv("JWT_PUBLIC_KEY_PATH", str(rsa_keypair["public"]))
    monkeypatch.setenv("JWT_ALGORITHM", "RS256")
    monkeypatch.setenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "30")
    monkeypatch.setenv("JWT_REFRESH_TOKEN_EXPIRE_DAYS", "7")
    # Force an in-memory SQLite so the lifespan ``init_db()`` does
    # not try to dial a PostgreSQL server that may not be reachable
    # in CI. The fixture's ``db_engine`` ignores this and creates
    # its own engine; this is only for the lifespan.
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")


@pytest.fixture()
def db_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture()
def session_factory(db_engine):
    return sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)


@pytest.fixture()
def jwt_client(
    session_factory, override_supervisor: None
) -> Iterator[TestClient]:
    """A TestClient bound to an isolated in-memory SQLite + the stub
    supervisor. The ``get_db`` dependency is overridden so each
    request sees the seeded users. The session factory
    used by the stream's persistence block (T5) is also
    overridden so the writes land in the test's in-memory
    engine (not the global factory's, which is a different
    in-memory SQLite). Mirrors the pattern from
    ``test_users_create.py::client``."""

    def _override_get_db() -> Iterator:
        s = session_factory()
        try:
            yield s
        finally:
            s.close()

    def _override_session_factory():
        return session_factory

    app.dependency_overrides[get_db] = _override_get_db
    # T5: the stream's persistence block uses a
    # dependency-injected session factory. Override it so
    # the writes hit the test's in-memory engine.
    from app.api.chat.router import _build_session_factory_dep

    app.dependency_overrides[_build_session_factory_dep] = (
        _override_session_factory
    )
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(_build_session_factory_dep, None)


@pytest.fixture()
def seeded_eleve_alice(session_factory) -> User:
    with session_factory() as db:
        user = User(
            pseudo="alice",
            password_hash=hash_password("studentpassword"),
            role=UserRole.ELEVE,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user


@pytest.fixture()
def seeded_eleve_bob(session_factory) -> User:
    with session_factory() as db:
        user = User(
            pseudo="bob",
            password_hash=hash_password("studentpassword"),
            role=UserRole.ELEVE,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user


@pytest.fixture()
def seeded_admin(session_factory) -> User:
    with session_factory() as db:
        user = User(
            pseudo="boss",
            password_hash=hash_password("adminpassword"),
            role=UserRole.ADMIN,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user


def _bearer(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.pseudo, user.role)}"}


# ---------------------------------------------------------------------------
# AC7 — request validation
# ---------------------------------------------------------------------------


class TestRequestValidation:
    def test_missing_question_returns_422(
        self, jwt_client: TestClient, seeded_eleve_alice: User
    ) -> None:
        """Bite test: Pydantic validates BEFORE the handler runs, so a
        body without ``question`` yields 422 and no stream is opened.
        """
        response = jwt_client.post(
            "/api/chat/stream",
            json={"subject": "maths"},
            headers=_bearer(seeded_eleve_alice),
        )
        assert response.status_code == 422
        # The error payload must mention the missing field.
        body = response.json()
        assert any(
            err.get("loc", [])[-1] == "question" for err in body.get("detail", [])
        )

    def test_unknown_subject_returns_422(
        self, jwt_client: TestClient, seeded_eleve_alice: User
    ) -> None:
        response = jwt_client.post(
            "/api/chat/stream",
            json={"subject": "histoire", "question": "Q"},
            headers=_bearer(seeded_eleve_alice),
        )
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# AC1, AC2, AC3, AC6 — happy path
# ---------------------------------------------------------------------------


class TestStreamHappyPath:
    def test_stream_returns_text_event_stream(
        self, jwt_client: TestClient, seeded_eleve_alice: User
    ) -> None:
        response = jwt_client.post(
            "/api/chat/stream",
            json={"subject": "maths", "question": "2+2 ?"},
            headers=_bearer(seeded_eleve_alice),
        )
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")

    def test_stream_emits_one_event_per_token(
        self, jwt_client: TestClient, seeded_eleve_alice: User
    ) -> None:
        response = jwt_client.post(
            "/api/chat/stream",
            json={"subject": "maths", "question": "2+2 ?"},
            headers=_bearer(seeded_eleve_alice),
        )
        events = _events_from_response(response)
        # 3 tokens + 1 done event.
        assert [e for e in events if "token" in e] == [
            {"token": "Hel"},
            {"token": "lo "},
            {"token": "world"},
        ]

    def test_stream_ends_with_done_event(
        self, jwt_client: TestClient, seeded_eleve_alice: User, maths_stub
    ) -> None:
        from app.services.agents.types import SourceCitation

        maths_stub.sources = [SourceCitation(filename="cours.pdf", chunk_index=0)]
        response = jwt_client.post(
            "/api/chat/stream",
            json={"subject": "maths", "question": "2+2 ?"},
            headers=_bearer(seeded_eleve_alice),
        )
        events = _events_from_response(response)
        # The last event must be ``done: True`` with the sources list.
        assert events[-1] == {
            "done": True,
            "sources": [{"filename": "cours.pdf", "chunk_index": 0}],
        }

    def test_stream_chunks_arrive_in_order(
        self, jwt_client: TestClient, seeded_eleve_alice: User
    ) -> None:
        """Bite test: the chunks must arrive in the order the supervisor
        yielded them. A bug that re-ordered or re-grouped them would
        silently scramble the response text in the browser.
        """
        response = jwt_client.post(
            "/api/chat/stream",
            json={"subject": "francais", "question": "métaphore ?"},
            headers=_bearer(seeded_eleve_alice),
        )
        events = _events_from_response(response)
        token_events = [e for e in events if "token" in e]
        assert [e["token"] for e in token_events] == ["Une ", "métaphore."]


# ---------------------------------------------------------------------------
# AC4 — error events
# ---------------------------------------------------------------------------


class TestStreamError:
    def test_error_event_emitted_with_code(
        self, jwt_client: TestClient, seeded_eleve_alice: User, maths_stub
    ) -> None:
        """Bite test: a ``ValueError`` from the agent must be caught and
        forwarded as an ``{error, code}`` event. The ``code`` is mapped
        from the error message (``"subject"`` substring → ``no_subject``).
        """
        maths_stub.behaviour = "raise_subject"
        response = jwt_client.post(
            "/api/chat/stream",
            json={"subject": "maths", "question": "Q"},
            headers=_bearer(seeded_eleve_alice),
        )
        # The HTTP status stays 200 — the error is in the SSE body. The
        # connection closes cleanly after the error event.
        assert response.status_code == 200
        events = _events_from_response(response)
        # The error event must be present with the right code.
        assert any(
            e.get("code") == "no_subject" and "Unknown subject" in e.get("error", "")
            for e in events
        )
        # No ``done`` event after an error.
        assert not any("done" in e for e in events)

    def test_cross_tenant_via_body_swap(
        self, jwt_client: TestClient, seeded_eleve_bob: User, maths_stub
    ) -> None:
        """Bite test: a request whose bearer is for ``bob`` but the
        agent is configured to refuse any non-``"alice"`` request must
        yield a ``cross_tenant`` code in the error event. The router
        MUST pass the JWT ``pseudo`` to the supervisor — a regression
        that hardcoded ``"alice"`` in the router would not be caught
        by any other test. (s15 migration: the body no longer carries
        a ``pseudo``; the identity comes from the JWT.)
        """
        maths_stub.behaviour = "raise_cross_tenant"
        response = jwt_client.post(
            "/api/chat/stream",
            json={"subject": "maths", "question": "Q"},
            headers=_bearer(seeded_eleve_bob),
        )
        events = _events_from_response(response)
        # The supervisor was called with the JWT pseudo, not a
        # hardcoded value. The agent's guard raised, the router caught
        # it, and ``_map_code`` matched the "different" substring.
        assert any(
            e.get("code") == "cross_tenant" and "different" in e.get("error", "")
            for e in events
        )
        # The supervisor MUST have been called with the JWT pseudo.
        assert maths_stub.astream_calls[-1][1] == "bob"

    def test_unknown_error_maps_to_unknown_code(
        self, jwt_client: TestClient, seeded_eleve_alice: User, maths_stub
    ) -> None:
        maths_stub.behaviour = "raise_unknown"
        response = jwt_client.post(
            "/api/chat/stream",
            json={"subject": "maths", "question": "Q"},
            headers=_bearer(seeded_eleve_alice),
        )
        events = _events_from_response(response)
        assert any(e.get("code") == "unknown" for e in events)


# ---------------------------------------------------------------------------
# SSE format
# ---------------------------------------------------------------------------


class TestSseFormat:
    def test_each_event_ends_with_double_newline(
        self, jwt_client: TestClient, seeded_eleve_alice: User
    ) -> None:
        """Bite test: each SSE event MUST end with ``\\n\\n`` so the
        browser fires ``onmessage``. Removing the trailing newline
        from :func:`format_sse` would break every frontend consumer.
        """
        response = jwt_client.post(
            "/api/chat/stream",
            json={"subject": "maths", "question": "Q"},
            headers=_bearer(seeded_eleve_alice),
        )
        # ``iter_lines`` preserves the wire format including the blank
        # line that separates events.
        lines = list(response.iter_lines())
        # The body alternates ``data: ...`` and ``""`` (the blank
        # separator). There must be no ``data: ...`` line followed by
        # a non-empty line — every event must be self-contained.
        for i, line in enumerate(lines):
            if line.startswith("data: ") and i + 1 < len(lines) and lines[i + 1] != "":
                # If we ever see ``data: foo`` immediately followed
                # by ``data: bar`` without a blank line, the test
                # fails. The current TestClient may merge lines,
                # so we instead assert the raw text format.
                pytest.fail(
                    f"Event at line {i} not followed by a blank separator: {lines[i:i+3]!r}"
                )
        # The body text itself must match the canonical
        # ``data: <json>\n\n`` regex on every event block.
        blocks = re.findall(r"data: [^\n]+\n\n", response.text)
        assert blocks, f"No SSE blocks found in body: {response.text!r}"
        for block in blocks:
            assert re.match(r"^data: \{.*\}\n\n$", block), (
                f"Block does not match canonical SSE format: {block!r}"
            )

    def test_preserves_non_ascii_characters(
        self, jwt_client: TestClient, seeded_eleve_alice: User
    ) -> None:
        """Bite test: ``ensure_ascii=False`` keeps French characters
        intact in the wire bytes. The frontend's ``new TextDecoder``
        does not have to handle ``\\u00xx`` escapes.
        """
        response = jwt_client.post(
            "/api/chat/stream",
            json={"subject": "francais", "question": "Q"},
            headers=_bearer(seeded_eleve_alice),
        )
        # The French token ``métaphore`` must appear verbatim.
        assert "métaphore" in response.text


# ---------------------------------------------------------------------------
# AC5 — CORS
# ---------------------------------------------------------------------------


class TestCors:
    def test_cors_preflight_allowed_for_allowlisted_origin(self, client) -> None:
        response = client.options(
            "/api/chat/stream",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        assert response.status_code in (200, 204)
        assert (
            response.headers.get("access-control-allow-origin")
            == "http://localhost:3000"
        )

    def test_cors_preflight_rejected_for_other_origin(self, client) -> None:
        """Bite test: an origin NOT in the allow-list must NOT receive
        the CORS allow headers. Using ``allow_origins=["*"]`` would
        weaken the test to a no-op.
        """
        response = client.options(
            "/api/chat/stream",
            headers={
                "Origin": "http://evil.example",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        # Starlette's CORS middleware refuses the preflight with 400.
        assert response.status_code == 400
        assert "access-control-allow-origin" not in {
            k.lower() for k in response.headers
        }

    def test_actual_post_includes_allow_origin_header(
        self, jwt_client: TestClient, seeded_eleve_alice: User
    ) -> None:
        response = jwt_client.post(
            "/api/chat/stream",
            json={"subject": "maths", "question": "Q"},
            headers={**_bearer(seeded_eleve_alice), "Origin": "http://localhost:3000"},
        )
        assert (
            response.headers.get("access-control-allow-origin")
            == "http://localhost:3000"
        )


# ---------------------------------------------------------------------------
# Chat stream safety net
# ---------------------------------------------------------------------------


class TestSafetyNet:
    def test_max_chunks_safety_net_stops_runaway_stream(
        self,
        maths_stub,
        supervisor_stub,
        seeded_eleve_alice: User,
        session_factory,
    ) -> None:
        """Bite test: the ``chat_stream_max_chunks`` setting caps the
        stream. A bug that ignored the cap would let a runaway LLM
        flood the SSE channel.
        """
        from fastapi.testclient import TestClient

        from app.api.chat.router import _build_supervisor_dep
        from app.core.config import Settings
        from app.core.database.session import get_db as _get_db
        from app.main import app

        # Many tokens -> exceeds the cap.
        maths_stub.tokens = [f"t{i}" for i in range(20)]
        tiny = Settings(chat_stream_max_chunks=5, cors_allow_origins="http://localhost:3000")

        # Wire both the stub supervisor and the per-test DB so the
        # bearer token can resolve to the seeded user.
        def _override_get_db():
            s = session_factory()
            try:
                yield s
            finally:
                s.close()

        app.dependency_overrides[_build_supervisor_dep] = lambda: supervisor_stub
        app.dependency_overrides[_get_db] = _override_get_db
        # Override the get_settings dependency to return the tiny cap.
        from app.core import config as config_module

        original_get_settings = config_module.get_settings
        config_module._settings = tiny  # populate the cache directly
        try:
            with TestClient(app) as c:
                response = c.post(
                    "/api/chat/stream",
                    json={"subject": "maths", "question": "Q"},
                    headers=_bearer(seeded_eleve_alice),
                )
            events = _events_from_response(response)
            token_events = [e for e in events if "token" in e]
            assert len(token_events) <= 5
            assert any(
                e.get("code") == "unknown" and "safety net" in e.get("error", "")
                for e in events
            )
        finally:
            config_module._settings = None
            config_module.get_settings = original_get_settings
            app.dependency_overrides.pop(_build_supervisor_dep, None)
            app.dependency_overrides.pop(_get_db, None)


# ---------------------------------------------------------------------------
# s15 — JWT-required (AC1, AC3)
# ---------------------------------------------------------------------------


class TestChatStreamJwtRequired:
    """The endpoint MUST require a valid bearer token (s15)."""

    def test_no_token_returns_401_invalid_token(
        self, jwt_client: TestClient
    ) -> None:
        """AC1: the endpoint rejects anonymous callers with 401
        ``invalid_token``. The response body is JSON, not an SSE
        stream — the auth check happens before the handler runs.
        """
        response = jwt_client.post(
            "/api/chat/stream",
            json={"subject": "maths", "question": "2+2 ?"},
        )
        assert response.status_code == 401
        assert response.headers["content-type"].startswith("application/json")
        body = response.json()
        assert body["detail"]["code"] == "invalid_token"

    def test_junk_token_returns_401_invalid_token(
        self, jwt_client: TestClient
    ) -> None:
        response = jwt_client.post(
            "/api/chat/stream",
            json={"subject": "maths", "question": "2+2 ?"},
            headers={"Authorization": "Bearer not-a-jwt"},
        )
        assert response.status_code == 401
        assert response.json()["detail"]["code"] == "invalid_token"

    def test_expired_token_returns_401_invalid_token(
        self, jwt_client: TestClient, seeded_eleve_alice: User
    ) -> None:
        """AC1: an expired token is rejected with the same generic
        401 ``invalid_token`` body as a missing token (Piège 2 bis
        in ``middleware.py``)."""
        token = create_access_token(
            seeded_eleve_alice.pseudo,
            seeded_eleve_alice.role,
            expires_delta=timedelta(seconds=-1),
        )
        response = jwt_client.post(
            "/api/chat/stream",
            json={"subject": "maths", "question": "2+2 ?"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 401
        assert response.json()["detail"]["code"] == "invalid_token"


# ---------------------------------------------------------------------------
# s15 — cross-tenant (AC2, AC3, AC5)
# ---------------------------------------------------------------------------


class TestChatStreamCrossTenant:
    """The s15 cross-tenant bite (plan § s15-restrictions-rbac)."""

    def test_eleve_bob_token_with_no_body_pseudo_streams_for_bob(
        self,
        jwt_client: TestClient,
        seeded_eleve_bob: User,
        maths_stub,
    ) -> None:
        """AC2 + AC5: a JWT for ``bob`` (no body ``pseudo``) is
        accepted, the stream opens, and the supervisor receives
        ``pseudo="bob"`` (NOT a hard-coded value or a body field).
        A regression that hard-coded ``"alice"`` in the router, or
        that read ``body.pseudo`` after s15 retired the field,
        would be caught here.
        """
        response = jwt_client.post(
            "/api/chat/stream",
            json={"subject": "maths", "question": "2+2 ?"},
            headers=_bearer(seeded_eleve_bob),
        )
        assert response.status_code == 200
        # The body of the events is implementation-specific (a real
        # supervisor returns tokens; a stub can return anything);
        # the load-bearing assertion is that the supervisor saw
        # ``bob`` — not a hard-coded value, not a body field that
        # no longer exists.
        assert maths_stub.astream_calls, "supervisor was not invoked"
        last_call = maths_stub.astream_calls[-1]
        # (subject, pseudo, question)
        assert last_call[1] == "bob"

    def test_eleve_bob_token_with_body_pseudo_alice_returns_422(
        self,
        jwt_client: TestClient,
        seeded_eleve_bob: User,
    ) -> None:
        """s15 hard cut: the schema no longer accepts ``body.pseudo``.
        A client that still sends one gets 422 from Pydantic BEFORE
        the handler runs. The cross-tenant log line is NOT emitted
        on this branch (Pydantic rejects before the handler).
        """
        response = jwt_client.post(
            "/api/chat/stream",
            json={"pseudo": "alice", "subject": "maths", "question": "Q"},
            headers=_bearer(seeded_eleve_bob),
        )
        assert response.status_code == 422
        body = response.json()
        # Pydantic must point at the rejected field.
        assert any(
            err.get("loc", [])[-1] == "pseudo" for err in body.get("detail", [])
        )

    def test_admin_token_can_stream_for_admin_itself(
        self,
        jwt_client: TestClient,
        seeded_admin: User,
        maths_stub,
    ) -> None:
        """AC2 — admin bypass: an admin can stream. The admin's
        identity is taken from the JWT, not from a body field
        (s15 does NOT implement admin impersonation via body,
        per plan OQ 2)."""
        response = jwt_client.post(
            "/api/chat/stream",
            json={"subject": "maths", "question": "2+2 ?"},
            headers=_bearer(seeded_admin),
        )
        assert response.status_code == 200
        # The supervisor was invoked with the admin's pseudo (no
        # impersonation).
        assert maths_stub.astream_calls, "supervisor was not invoked"
        assert maths_stub.astream_calls[-1][1] == seeded_admin.pseudo

    def test_existing_stream_happy_path_unchanged(
        self,
        jwt_client: TestClient,
        seeded_eleve_alice: User,
    ) -> None:
        """Regression: the pre-s09/s15 happy path still works after
        the migration — alice's token, body ``{subject, question}``,
        3 tokens + 1 done event. Guards against any incidental
        change in the response shape introduced by the
        ``get_current_user`` dependency."""
        response = jwt_client.post(
            "/api/chat/stream",
            json={"subject": "maths", "question": "2+2 ?"},
            headers=_bearer(seeded_eleve_alice),
        )
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        events = _events_from_response(response)
        assert events[-1] == {
            "done": True,
            "sources": [],
        }


# ---------------------------------------------------------------------------
# s19 — stream-side persistence (T5)
# ---------------------------------------------------------------------------


class TestStreamPersistence:
    """The stream's persistence block (T5, ADR 015 § Decision 4).

    The block lives in a ``try/finally`` AFTER the SSE loop
    closes, so the existing s09 wire format is unchanged.
    Persistence is gated by the ``chat_persist_history``
    setting (default ``True``); the s09 happy-path tests above
    do not exercise it because the JWT + supervisor override
    does not seed ``Conversation`` rows.
    """

    def test_stream_persists_user_and_assistant_messages(
        self,
        jwt_client: TestClient,
        seeded_eleve_alice: User,
        session_factory,
        maths_stub,
    ) -> None:
        """Happy path: after a successful stream, the DB has
        one ``Conversation`` row + 2 ``Message`` rows, with
        ``first_question == body.question`` and
        ``message_count == 2``.
        """
        from app.services.agents.types import SourceCitation

        maths_stub.sources = [SourceCitation(filename="cours.pdf", chunk_index=0)]
        response = jwt_client.post(
            "/api/chat/stream",
            json={"subject": "maths", "question": "2+2 ?"},
            headers=_bearer(seeded_eleve_alice),
        )
        assert response.status_code == 200
        # Drain the stream to make sure the finally block runs.
        _ = response.text

        from app.core.database.models import Conversation, Message, Subject

        with session_factory() as db:
            convs = (
                db.query(Conversation)
                .filter(Conversation.student_pseudo == "alice")
                .all()
            )
            assert len(convs) == 1
            conv = convs[0]
            assert conv.subject is Subject.MATHS
            assert conv.first_question == "2+2 ?"
            assert conv.message_count == 2

            msgs = (
                db.query(Message)
                .filter(Message.conversation_id == conv.id)
                .order_by(Message.created_at.asc())
                .all()
            )
            assert len(msgs) == 2
            assert msgs[0].role == "user"
            assert msgs[0].content == "2+2 ?"
            assert msgs[0].sources is None
            assert msgs[1].role == "assistant"
            # The assistant content is the concatenation of the
            # stub's tokens ("Hel" + "lo " + "world" = "Hello world").
            assert msgs[1].content == "Hello world"
            assert msgs[1].sources == [
                {"filename": "cours.pdf", "chunk_index": 0}
            ]

    def test_stream_persists_reuses_existing_conversation(
        self,
        jwt_client: TestClient,
        seeded_eleve_alice: User,
        session_factory,
    ) -> None:
        """Two streams for the same (student, subject) hit the
        same ``Conversation`` row; the second call's
        ``+2`` bumps ``message_count`` to 4.
        """
        for _ in range(2):
            response = jwt_client.post(
                "/api/chat/stream",
                json={"subject": "maths", "question": "2+2 ?"},
                headers=_bearer(seeded_eleve_alice),
            )
            assert response.status_code == 200
            _ = response.text

        from app.core.database.models import Conversation, Message

        with session_factory() as db:
            convs = (
                db.query(Conversation)
                .filter(Conversation.student_pseudo == "alice")
                .all()
            )
            assert len(convs) == 1
            assert convs[0].message_count == 4
            msgs = (
                db.query(Message)
                .filter(Message.conversation_id == convs[0].id)
                .all()
            )
            assert len(msgs) == 4

    def test_stream_persists_with_persist_flag_off_does_not_write(
        self,
        jwt_client: TestClient,
        seeded_eleve_alice: User,
        session_factory,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When ``chat_persist_history=False``, the stream
        is a no-op on the DB. This is the gate that keeps
        the s09 test suite (3-token stub) free of DB
        writes — the existing s09 tests stay green with
        zero schema side-effects.
        """
        # Patch the settings singleton's chat_persist_history
        # to False. The router reads ``get_settings()`` per
        # request, so the new value is honoured for the next
        # call. The monkeypatch fixture restores the
        # previous value automatically.
        from app.core import config as config_module
        from app.core.config import Settings

        current = config_module._settings
        if current is None:
            current = Settings()
        config_module._settings = current.model_copy(
            update={"chat_persist_history": False}
        )
        try:
            response = jwt_client.post(
                "/api/chat/stream",
                json={"subject": "maths", "question": "2+2 ?"},
                headers=_bearer(seeded_eleve_alice),
            )
            assert response.status_code == 200
            _ = response.text
        finally:
            # Restore — the autouse ``_point_settings`` will
            # rebuild a fresh instance for the next test.
            config_module._settings = None

        from app.core.database.models import Conversation, Message

        with session_factory() as db:
            assert db.query(Conversation).count() == 0
            assert db.query(Message).count() == 0

    def test_stream_persists_error_event_does_not_write(
        self,
        jwt_client: TestClient,
        seeded_eleve_alice: User,
        session_factory,
        maths_stub,
    ) -> None:
        """The bite on ADR 015 § Decision 4: a ``ValueError``
        mid-stream (the stub raises) must leave NO
        ``Conversation`` and NO ``Message`` row. The user
        never saw a response — the conversation was never
        started, so no half-written row is persisted.
        """
        maths_stub.behaviour = "raise_unknown"
        response = jwt_client.post(
            "/api/chat/stream",
            json={"subject": "maths", "question": "2+2 ?"},
            headers=_bearer(seeded_eleve_alice),
        )
        assert response.status_code == 200
        # The error event is in the body; the stream is short.
        events = _events_from_response(response)
        assert any(e.get("code") == "unknown" for e in events)

        from app.core.database.models import Conversation, Message

        with session_factory() as db:
            assert db.query(Conversation).count() == 0
            assert db.query(Message).count() == 0
