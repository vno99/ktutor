"""Tests for ``GET /api/chat/history`` and ``GET /api/chat/history/{id}`` (s19).

The suite covers the AC1-AC7 surface plus the T4 cross-tenant
4-edge RBAC matrix and the T6 router-mounting bite. The
``chat_stream`` stub supervisor is NOT exercised here — the
history endpoints do not call the supervisor. The
``override_supervisor`` fixture is only needed because the
``client`` fixture in :mod:`tests.api.conftest` builds the
TestClient on top of the supervisor override.

Test families:

* **Auth** — no bearer → 401 (the only auth shape in the ACs).
* **AC1 / AC5 / AC7** — list endpoint paginates and is sorted
  newest-first.
* **AC2** — the JSON keys are exactly the doc-named ones
  (``id``, ``subject``, ``first_question``, ``last_activity_at``,
  ``message_count``).
* **AC3** — detail endpoint returns the conversation + the
  messages in chronological order, with sources on assistant
  messages and ``None`` on user messages.
* **AC6** — bob's token does not surface alice's conversations.
* **T4 RBAC** — 4 edges (eleve own / eleve other / parent
  linked / parent unlinked / admin).
* **T6 mounting** — the test that fires the requests against
  the live ``app`` instance; a missed ``include_router`` is
  caught by 404 on the new paths.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import sessionmaker

from app.core.auth.jwt import create_access_token
from app.core.auth.passwords import hash_password
from app.core.database.models import (
    Base,
    Conversation,
    Message,
    ParentChildLink,
    User,
    UserRole,
)
from app.core.database.session import get_db
from app.main import app

# ---------------------------------------------------------------------------
# RSA keypair + settings (duplicated from test_chat_stream /
# test_dashboard_eleve per AGENTS.md « Pas de refactor transverse »).
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def rsa_keypair(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    tmp = tmp_path_factory.mktemp("jwt_keys_chat_history")
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
    # The production schema has ``UNIQUE(student_pseudo, subject)``
    # on ``conversations`` (T1, ADR 015 § Decision 1). The API
    # pagination tests need MORE than 2 conversations per
    # student to exercise the AC7 path; the constraint is
    # enforced at the DB level (last line of defence) and the
    # upsert path in the stream-side persistence (T5) is
    # covered separately by the persistence tests. The
    # ``session_factory_no_unique`` fixture in the service
    # tests does the same thing.
    from sqlalchemy import text

    with engine.begin() as conn:
        conn.execute(text("DROP TABLE conversations"))
        conn.execute(
            text(
                "CREATE TABLE conversations ("
                "id CHAR(32) NOT NULL PRIMARY KEY,"
                "student_pseudo VARCHAR(32) NOT NULL,"
                "subject VARCHAR(32) NOT NULL,"
                "first_question VARCHAR(2000) NOT NULL,"
                "message_count INTEGER NOT NULL,"
                "last_activity_at DATETIME NOT NULL,"
                "created_at DATETIME NOT NULL,"
                "FOREIGN KEY(student_pseudo) REFERENCES users (pseudo) "
                "ON DELETE CASCADE"
                ")"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX ix_conversations_student_pseudo "
                "ON conversations (student_pseudo)"
            )
        )
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture()
def session_factory(db_engine):
    return sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)


@pytest.fixture()
def history_client(
    session_factory, override_supervisor: None
) -> Iterator[TestClient]:
    """A TestClient bound to an isolated in-memory SQLite.

    The supervisor override is applied (so the lifespan does
    not try to build a real LLM supervisor) but the history
    endpoints never call it. The ``get_db`` override lets
    the seeded users and conversations be visible to the
    handlers.
    """

    def _override_get_db() -> Iterator:
        s = session_factory()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _override_get_db
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# Seeded users
# ---------------------------------------------------------------------------


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
def seeded_parent(session_factory) -> User:
    with session_factory() as db:
        user = User(
            pseudo="parent",
            password_hash=hash_password("parentpassword"),
            role=UserRole.PARENT,
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
# Seeded conversations (id-keyed; the tests reference the ids)
# ---------------------------------------------------------------------------


@pytest.fixture()
def alice_conversations(session_factory) -> dict[str, Conversation]:
    """3 maths + 2 francais conversations for alice.

    The ids are time-ordered (oldest first). The list
    endpoint is expected to return them in reverse order
    (newest first).

    The production schema's ``UNIQUE(student_pseudo, subject)``
    constraint is dropped in the ``db_engine`` fixture so we
    can exercise the pagination paths with more than one
    maths conversation per student. The constraint is
    enforced at the DB level (last line of defence) and the
    upsert path in the stream-side persistence (T5) is
    covered separately by the persistence tests.

    The inserts go through raw SQL with explicit
    ``last_activity_at`` / ``created_at`` values so the
    rebuilt table (which has no ``server_default`` on those
    columns) accepts the rows. The ORM's read-back works
    because the Enum stores the member NAME (``"MATHS"`` /
    ``"FRANCAIS"``), matching what the raw INSERT writes.
    """
    import uuid as _uuid

    from sqlalchemy import text

    convs: dict[str, Conversation] = {}
    with session_factory() as db:
        for key, ts_offset, subj_name in [
            ("oldest_maths", 0, "MATHS"),
            ("mid_maths", 1, "MATHS"),
            ("newest_maths", 2, "MATHS"),
            ("old_francais", 3, "FRANCAIS"),
            ("new_francais", 4, "FRANCAIS"),
        ]:
            cid = _uuid.uuid4()
            db.execute(
                text(
                    "INSERT INTO conversations ("
                    "id, student_pseudo, subject, first_question, "
                    "message_count, last_activity_at, created_at"
                    ") VALUES (:id, :p, :s, :q, 2, :ts, :ts)"
                ),
                {
                    "id": cid.hex,
                    "p": "alice",
                    "s": subj_name,
                    "q": f"Question {key}",
                    "ts": f"2026-09-04 08:0{ts_offset}:00",
                },
            )
            db.commit()
            # Re-read the row via the ORM so callers get a
            # fully-populated :class:`Conversation` instance.
            c = db.get(Conversation, cid)
            assert c is not None
            convs[key] = c
    return convs


@pytest.fixture()
def bob_conversation(session_factory) -> Conversation:
    import uuid as _uuid

    from sqlalchemy import text

    cid = _uuid.uuid4()
    with session_factory() as db:
        db.execute(
            text(
                "INSERT INTO conversations ("
                "id, student_pseudo, subject, first_question, "
                "message_count, last_activity_at, created_at"
                ") VALUES (:id, :p, :s, :q, 2, :ts, :ts)"
            ),
            {
                "id": cid.hex,
                "p": "bob",
                "s": "MATHS",
                "q": "Bob's question",
                "ts": "2026-09-04 08:00:00",
            },
        )
        db.commit()
        c = db.get(Conversation, cid)
        assert c is not None
        return c


# ---------------------------------------------------------------------------
# T6 — router mounting
# ---------------------------------------------------------------------------


class TestRouterMounting:
    def test_list_history_endpoint_is_mounted(
        self, history_client: TestClient, seeded_eleve_alice: User
    ) -> None:
        """Bite test: the absence of this test is what allows a
        missed ``include_router`` to ship. Hitting the live
        ``app`` and getting 200 (not 404) is the only way to
        confirm the router is wired.
        """
        response = history_client.get(
            "/api/chat/history?limit=20&offset=0",
            headers=_bearer(seeded_eleve_alice),
        )
        assert response.status_code == 200

    def test_get_history_endpoint_is_mounted(
        self, history_client: TestClient, seeded_eleve_alice: User
    ) -> None:
        response = history_client.get(
            f"/api/chat/history/{uuid.uuid4()}",
            headers=_bearer(seeded_eleve_alice),
        )
        # 404 not_found is the expected response (the random
        # uuid does not match any conversation). The
        # important thing is that the path is routed (404
        # not_found, not 404 not_found on the framework's
        # default handler).
        assert response.status_code == 404
        assert response.json()["detail"]["code"] == "not_found"


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


class TestAuth:
    def test_list_history_returns_401_without_bearer(
        self, history_client: TestClient
    ) -> None:
        response = history_client.get("/api/chat/history")
        assert response.status_code == 401
        assert response.json()["detail"]["code"] == "invalid_token"

    def test_get_history_returns_401_without_bearer(
        self, history_client: TestClient
    ) -> None:
        response = history_client.get(f"/api/chat/history/{uuid.uuid4()}")
        assert response.status_code == 401
        assert response.json()["detail"]["code"] == "invalid_token"


# ---------------------------------------------------------------------------
# AC1 + AC5 — list endpoint paginates, newest first
# ---------------------------------------------------------------------------


class TestListHistory:
    def test_list_history_returns_200_with_default_pagination(
        self,
        history_client: TestClient,
        seeded_eleve_alice: User,
        alice_conversations: dict[str, Conversation],
    ) -> None:
        """AC1 — the list endpoint returns the user's past
        conversations, newest first, with the default
        ``limit=20, offset=0`` shape.
        """
        response = history_client.get(
            "/api/chat/history",
            headers=_bearer(seeded_eleve_alice),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["limit"] == 20
        assert body["offset"] == 0
        assert body["total"] == 5
        # Newest first: ts = 4, 3, 2, 1, 0.
        ids = [item["id"] for item in body["items"]]
        assert ids == [
            str(alice_conversations["new_francais"].id),
            str(alice_conversations["old_francais"].id),
            str(alice_conversations["newest_maths"].id),
            str(alice_conversations["mid_maths"].id),
            str(alice_conversations["oldest_maths"].id),
        ]

    def test_list_history_item_shape(
        self,
        history_client: TestClient,
        seeded_eleve_alice: User,
        alice_conversations: dict[str, Conversation],
    ) -> None:
        """AC2 — each item's JSON keys are exactly the doc's
        AC2 list. The Pydantic ``extra='forbid'`` model
        config is the safeguard.
        """
        response = history_client.get(
            "/api/chat/history?limit=1",
            headers=_bearer(seeded_eleve_alice),
        )
        body = response.json()
        assert len(body["items"]) == 1
        item = body["items"][0]
        assert set(item.keys()) == {
            "id",
            "subject",
            "first_question",
            "last_activity_at",
            "message_count",
        }

    def test_list_history_paginates_with_limit_and_offset(
        self,
        history_client: TestClient,
        seeded_eleve_alice: User,
        alice_conversations: dict[str, Conversation],
    ) -> None:
        """AC7 — ``limit=2&offset=0`` returns 2 rows;
        ``limit=2&offset=2`` returns the next 2 (5 total
        for alice, so the second page has 1 row). The two
        pages must be disjoint and the ``total`` must be
        the same (5).
        """
        page1 = history_client.get(
            "/api/chat/history?limit=2&offset=0",
            headers=_bearer(seeded_eleve_alice),
        ).json()
        page2 = history_client.get(
            "/api/chat/history?limit=2&offset=2",
            headers=_bearer(seeded_eleve_alice),
        ).json()
        assert page1["total"] == 5
        assert page2["total"] == 5
        assert len(page1["items"]) == 2
        assert len(page2["items"]) == 2
        # Disjoint sets.
        ids1 = {item["id"] for item in page1["items"]}
        ids2 = {item["id"] for item in page2["items"]}
        assert ids1.isdisjoint(ids2)

    def test_list_history_filters_by_subject_maths(
        self,
        history_client: TestClient,
        seeded_eleve_alice: User,
        alice_conversations: dict[str, Conversation],
    ) -> None:
        response = history_client.get(
            "/api/chat/history?subject=maths",
            headers=_bearer(seeded_eleve_alice),
        )
        body = response.json()
        assert body["total"] == 3
        assert all(item["subject"] == "maths" for item in body["items"])

    def test_list_history_filters_by_subject_francais(
        self,
        history_client: TestClient,
        seeded_eleve_alice: User,
        alice_conversations: dict[str, Conversation],
    ) -> None:
        response = history_client.get(
            "/api/chat/history?subject=francais",
            headers=_bearer(seeded_eleve_alice),
        )
        body = response.json()
        assert body["total"] == 2
        assert all(item["subject"] == "francais" for item in body["items"])

    def test_list_history_rejects_unknown_subject(
        self,
        history_client: TestClient,
        seeded_eleve_alice: User,
    ) -> None:
        response = history_client.get(
            "/api/chat/history?subject=histoire",
            headers=_bearer(seeded_eleve_alice),
        )
        assert response.status_code == 422

    def test_list_history_rejects_limit_above_100(
        self,
        history_client: TestClient,
        seeded_eleve_alice: User,
    ) -> None:
        response = history_client.get(
            "/api/chat/history?limit=101",
            headers=_bearer(seeded_eleve_alice),
        )
        assert response.status_code == 422

    def test_list_history_rejects_negative_offset(
        self,
        history_client: TestClient,
        seeded_eleve_alice: User,
    ) -> None:
        response = history_client.get(
            "/api/chat/history?offset=-1",
            headers=_bearer(seeded_eleve_alice),
        )
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# AC3 — detail endpoint
# ---------------------------------------------------------------------------


class TestGetHistory:
    def test_get_history_returns_full_thread(
        self,
        history_client: TestClient,
        seeded_eleve_alice: User,
        session_factory,
    ) -> None:
        """AC3 — the detail endpoint returns the conversation
        and its messages in chronological order. Sources are
        attached to assistant messages and ``None`` on user
        messages.
        """
        conv_id = uuid.uuid4()
        from sqlalchemy import text

        with session_factory() as db:
            # Raw INSERT so the rebuilt ``conversations`` table
            # (the ``db_engine`` fixture drops the UNIQUE
            # constraint) accepts the row — the rebuilt
            # schema has no ``server_default`` on the timestamp
            # columns, so the ORM's auto-fill does not apply.
            db.execute(
                text(
                    "INSERT INTO conversations ("
                    "id, student_pseudo, subject, first_question, "
                    "message_count, last_activity_at, created_at"
                    ") VALUES (:id, :p, :s, :q, 2, :ts, :ts)"
                ),
                {
                    "id": conv_id.hex,
                    "p": "alice",
                    "s": "MATHS",
                    "q": "2+2 ?",
                    "ts": "2026-09-04 08:00:00",
                },
            )
            # 2 messages — user then assistant — inserted
            # in REVERSE chronological order to prove the
            # ORDER BY drives the order, not the insert
            # order.
            m_assistant = Message(
                conversation_id=conv_id,
                role="assistant",
                content="4",
                sources=[{"filename": "cours.pdf", "chunk_index": 0}],
            )
            m_user = Message(
                conversation_id=conv_id,
                role="user",
                content="2+2 ?",
                sources=None,
            )
            db.add_all([m_assistant, m_user])
            db.commit()
            # Stamp deterministic timestamps via raw SQL.
            db.execute(
                text(
                    "UPDATE messages SET created_at = '2026-09-04 08:00:00' "
                    "WHERE id = :id"
                ),
                {"id": m_user.id.hex},
            )
            db.execute(
                text(
                    "UPDATE messages SET created_at = '2026-09-04 08:00:05' "
                    "WHERE id = :id"
                ),
                {"id": m_assistant.id.hex},
            )
            db.commit()

        response = history_client.get(
            f"/api/chat/history/{conv_id}",
            headers=_bearer(seeded_eleve_alice),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["id"] == str(conv_id)
        assert body["first_question"] == "2+2 ?"
        assert body["message_count"] == 2
        assert [m["role"] for m in body["messages"]] == ["user", "assistant"]
        assert [m["content"] for m in body["messages"]] == ["2+2 ?", "4"]
        assert body["messages"][0]["sources"] is None
        assert body["messages"][1]["sources"] == [
            {"filename": "cours.pdf", "chunk_index": 0}
        ]

    def test_get_history_returns_404_for_unknown_id(
        self,
        history_client: TestClient,
        seeded_eleve_alice: User,
    ) -> None:
        response = history_client.get(
            f"/api/chat/history/{uuid.uuid4()}",
            headers=_bearer(seeded_eleve_alice),
        )
        assert response.status_code == 404
        body = response.json()
        assert body["detail"]["code"] == "not_found"
        assert body["detail"]["error"]


# ---------------------------------------------------------------------------
# T4 — 4-edge RBAC matrix
# ---------------------------------------------------------------------------


class TestRbacCrossTenant:
    def test_list_history_other_eleve_sees_only_own(
        self,
        history_client: TestClient,
        seeded_eleve_alice: User,
        seeded_eleve_bob: User,
        alice_conversations: dict[str, Conversation],
        bob_conversation: Conversation,
    ) -> None:
        """AC6 — bob's token returns only bob's row, not
        alice's three. A regression that filters in Python
        after a load (``rows = [r for r in rows if
        r.student_pseudo == user.pseudo]``) breaks this
        test on a sufficiently large dataset, but the
        service-level ``WHERE`` predicate is the closer
        defence.
        """
        bob_response = history_client.get(
            "/api/chat/history",
            headers=_bearer(seeded_eleve_bob),
        )
        assert bob_response.status_code == 200
        body = bob_response.json()
        assert body["total"] == 1
        assert body["items"][0]["id"] == str(bob_conversation.id)

    def test_get_history_other_eleve_gets_404(
        self,
        history_client: TestClient,
        seeded_eleve_bob: User,
        alice_conversations: dict[str, Conversation],
    ) -> None:
        """The cross-tenant detail: bob's token + alice's
        conversation id → 404 ``not_found`` (same body as
        "unknown id" so a cross-tenant attacker cannot
        distinguish them — ADR 015 § Decision 3).
        """
        alice_conv = alice_conversations["newest_maths"]
        response = history_client.get(
            f"/api/chat/history/{alice_conv.id}",
            headers=_bearer(seeded_eleve_bob),
        )
        assert response.status_code == 404
        assert response.json()["detail"]["code"] == "not_found"

    def test_get_history_linked_parent_succeeds(
        self,
        history_client: TestClient,
        seeded_parent: User,
        seeded_eleve_alice: User,
        alice_conversations: dict[str, Conversation],
        session_factory,
    ) -> None:
        """A parent linked to a child can read the child's
        conversation. The link is set up via
        :class:`ParentChildLink`.
        """
        with session_factory() as db:
            db.add(
                ParentChildLink(
                    parent_pseudo="parent", child_pseudo="alice"
                )
            )
            db.commit()
        alice_conv = alice_conversations["newest_maths"]
        response = history_client.get(
            f"/api/chat/history/{alice_conv.id}",
            headers=_bearer(seeded_parent),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["id"] == str(alice_conv.id)

    def test_get_history_unlinked_parent_gets_404(
        self,
        history_client: TestClient,
        seeded_parent: User,
        seeded_eleve_alice: User,
        alice_conversations: dict[str, Conversation],
    ) -> None:
        """A parent NOT linked to a child gets 404, not 403,
        not 500. The plan's "4-edge bite" — a regression
        that calls ``assert_jwt_pseudo_matches_or_403`` for
        the parent (instead of
        ``assert_parent_linked_to_child_or_403``) blocks
        every parent.
        """
        alice_conv = alice_conversations["newest_maths"]
        response = history_client.get(
            f"/api/chat/history/{alice_conv.id}",
            headers=_bearer(seeded_parent),
        )
        assert response.status_code == 404
        assert response.json()["detail"]["code"] == "not_found"

    def test_get_history_admin_succeeds_for_any_student(
        self,
        history_client: TestClient,
        seeded_admin: User,
        alice_conversations: dict[str, Conversation],
    ) -> None:
        """Admin impersonation (ADR 005)."""
        alice_conv = alice_conversations["newest_maths"]
        response = history_client.get(
            f"/api/chat/history/{alice_conv.id}",
            headers=_bearer(seeded_admin),
        )
        assert response.status_code == 200
        assert response.json()["id"] == str(alice_conv.id)

    def test_list_history_admin_sees_all(
        self,
        history_client: TestClient,
        seeded_admin: User,
        alice_conversations: dict[str, Conversation],
        bob_conversation: Conversation,
    ) -> None:
        """Admin sees both alice's and bob's rows (no
        ``student_pseudo`` filter).
        """
        response = history_client.get(
            "/api/chat/history?limit=100",
            headers=_bearer(seeded_admin),
        )
        body = response.json()
        assert body["total"] == 6
        ids = {item["id"] for item in body["items"]}
        assert str(bob_conversation.id) in ids
        # All 5 of alice's convs are also in the list.
        for key in [
            "newest_maths",
            "mid_maths",
            "oldest_maths",
            "old_francais",
            "new_francais",
        ]:
            assert str(alice_conversations[key].id) in ids

    def test_list_history_parent_sees_only_own(
        self,
        history_client: TestClient,
        seeded_parent: User,
        alice_conversations: dict[str, Conversation],
    ) -> None:
        """A parent calling the list endpoint sees their
        OWN (empty) history — the linked children's
        history is surfaced through the parent dashboard
        (out of s19 scope — ADR 015 § Decision 3).
        """
        response = history_client.get(
            "/api/chat/history",
            headers=_bearer(seeded_parent),
        )
        body = response.json()
        assert body["total"] == 0
        assert body["items"] == []
