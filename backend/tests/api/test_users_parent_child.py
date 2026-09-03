"""Tests for ``POST /api/users/{parent_pseudo}/children`` and
``GET /api/users/{parent_pseudo}/children`` (s14).

The endpoints are **owner-or-admin** (not admin-only): the caller
can be an admin or the parent themselves. The router uses
:func:`app.core.auth.middleware.get_current_user` (NOT
:func:`require_role` — that would wrongly reject every parent,
research fact 1) and checks ``current_user.pseudo == parent.pseudo
OR current_user.role is ADMIN`` in the handler.

The auth contract differs from s13b on one precise point: a
*parent* can call these endpoints on their own URL. s13b rejects
all parents with 403. Pinning that distinction in a test is the
whole point of ``TestAddChildHappyPath::test_parent_self_link``
and ``TestListChildrenHappyPath::test_parent_lists_own_children``.

The other load-bearing contracts pinned here:

* **404 before 403** — a non-existent ``parent_pseudo`` returns
  404 ``user_not_found`` even for an unauthenticated caller, so
  the response does not leak the existence of the parent (research
  trap 5).
* **Idempotence** — the second ``POST`` with the same pair returns
  200 and creates **no** new row (research trap 1).
* **Cross-tenant isolation** — a parent ``B`` cannot list the
  children of parent ``A`` (AGENTS.md § DoD).

The fixtures are duplicated from ``test_users_create.py`` and
``test_users_role.py`` by design (AGENTS.md "Pas de refactor
transverse"); ``seeded_another_parent`` and
``seeded_another_eleve`` are added locally for the cross-tenant
tests.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.auth.jwt import create_access_token
from app.core.auth.passwords import hash_password
from app.core.database.models import Base, ParentChildLink, User, UserRole
from app.core.database.session import get_db
from app.main import app

# ---------------------------------------------------------------------------
# RSA keypair fixture — same pattern as ``test_users_create.py``.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def rsa_keypair(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    tmp = tmp_path_factory.mktemp("jwt_keys_parent_child")
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


# ---------------------------------------------------------------------------
# DB fixture: an isolated in-memory SQLite shared across the TestClient
# requests and the assertions. Mirrors ``test_users_create.py``.
# ---------------------------------------------------------------------------


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
def client(session_factory) -> Iterator[TestClient]:
    def _override_get_db() -> Iterator[Session]:
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


def _seeded(role: UserRole, pseudo: str) -> User:
    return User(
        pseudo=pseudo,
        password_hash=hash_password("seedpassword1"),
        role=role,
    )


@pytest.fixture()
def seeded_admin(session_factory) -> User:
    with session_factory() as db:
        user = _seeded(UserRole.ADMIN, "boss")
        db.add(user)
        db.commit()
        db.refresh(user)
        return user


@pytest.fixture()
def seeded_parent(session_factory) -> User:
    with session_factory() as db:
        user = _seeded(UserRole.PARENT, "pat")
        db.add(user)
        db.commit()
        db.refresh(user)
        return user


@pytest.fixture()
def seeded_eleve(session_factory) -> User:
    with session_factory() as db:
        user = _seeded(UserRole.ELEVE, "ali")
        db.add(user)
        db.commit()
        db.refresh(user)
        return user


@pytest.fixture()
def seeded_another_parent(session_factory) -> User:
    """A second parent — used for the cross-tenant isolation tests."""
    with session_factory() as db:
        user = _seeded(UserRole.PARENT, "sam")
        db.add(user)
        db.commit()
        db.refresh(user)
        return user


@pytest.fixture()
def seeded_another_eleve(session_factory) -> User:
    """A second eleve — used for cross-tenant isolation tests."""
    with session_factory() as db:
        user = _seeded(UserRole.ELEVE, "bob")
        db.add(user)
        db.commit()
        db.refresh(user)
        return user


def _bearer(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.pseudo, user.role)}"}


# ---------------------------------------------------------------------------
# POST /api/users/{parent_pseudo}/children — happy path
# ---------------------------------------------------------------------------


class TestAddChildHappyPath:
    def test_admin_link_parent_to_eleve_returns_201(
        self,
        client: TestClient,
        seeded_admin: User,
        seeded_parent: User,
        seeded_eleve: User,
        session_factory,
    ) -> None:
        resp = client.post(
            f"/api/users/{seeded_parent.pseudo}/children",
            json={"child_pseudo": seeded_eleve.pseudo},
            headers=_bearer(seeded_admin),
        )
        assert resp.status_code == 201, resp.text
        assert resp.json() == {
            "parent_pseudo": seeded_parent.pseudo,
            "child_pseudo": seeded_eleve.pseudo,
        }

        # The link row must be persisted with the canonical pseudos.

        with session_factory() as db:
            row = (
                db.query(ParentChildLink)
                .filter(ParentChildLink.parent_pseudo == seeded_parent.pseudo)
                .one()
            )
        assert row.child_pseudo == seeded_eleve.pseudo

    def test_parent_self_link_returns_201(
        self,
        client: TestClient,
        seeded_parent: User,
        seeded_eleve: User,
        session_factory,
    ) -> None:
        """AC1 — the parent (owner) can link a child to themselves.

        This is the test that fails when the implementation uses
        ``require_role(UserRole.ADMIN)`` instead of
        ``get_current_user``: every parent — including the right
        one — would be rejected with 403. The plan calls this out
        as "the point everything turns on" (research fact 1).
        """
        resp = client.post(
            f"/api/users/{seeded_parent.pseudo}/children",
            json={"child_pseudo": seeded_eleve.pseudo},
            headers=_bearer(seeded_parent),
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["parent_pseudo"] == seeded_parent.pseudo
        assert resp.json()["child_pseudo"] == seeded_eleve.pseudo

        with session_factory() as db:
            assert (
                db.query(ParentChildLink)
                .filter(ParentChildLink.parent_pseudo == seeded_parent.pseudo)
                .count()
                == 1
            )

    def test_duplicate_link_returns_200_with_same_body(
        self,
        client: TestClient,
        seeded_admin: User,
        seeded_parent: User,
        seeded_eleve: User,
        session_factory,
    ) -> None:
        """AC3 — idempotence: re-POSTing the same pair returns 200, body identical, DB unchanged."""
        url = f"/api/users/{seeded_parent.pseudo}/children"
        body = {"child_pseudo": seeded_eleve.pseudo}
        first = client.post(url, json=body, headers=_bearer(seeded_admin))
        second = client.post(url, json=body, headers=_bearer(seeded_admin))

        assert first.status_code == 201, first.text
        assert second.status_code == 200, second.text
        # Same body — the parent_pseudo/child_pseudo are the canonical DB values
        # in both cases.
        assert second.json() == first.json()


        with session_factory() as db:
            count = (
                db.query(ParentChildLink)
                .filter(
                    ParentChildLink.parent_pseudo == seeded_parent.pseudo,
                    ParentChildLink.child_pseudo == seeded_eleve.pseudo,
                )
                .count()
            )
        assert count == 1


# ---------------------------------------------------------------------------
# POST .../children — auth
# ---------------------------------------------------------------------------


class TestAddChildAuth:
    def test_eleve_caller_returns_403(
        self,
        client: TestClient,
        seeded_eleve: User,
        seeded_parent: User,
    ) -> None:
        resp = client.post(
            f"/api/users/{seeded_parent.pseudo}/children",
            json={"child_pseudo": seeded_eleve.pseudo},
            headers=_bearer(seeded_eleve),
        )
        assert resp.status_code == 403, resp.text
        assert resp.json()["detail"]["code"] == "forbidden"

    def test_other_parent_caller_returns_403(
        self,
        client: TestClient,
        seeded_another_parent: User,
        seeded_parent: User,
        seeded_eleve: User,
    ) -> None:
        """A different parent cannot add a child on someone else's URL.

        Cross-tenant: ``sam`` is a parent but is not the URL's
        parent and is not an admin → 403.
        """
        resp = client.post(
            f"/api/users/{seeded_parent.pseudo}/children",
            json={"child_pseudo": seeded_eleve.pseudo},
            headers=_bearer(seeded_another_parent),
        )
        assert resp.status_code == 403, resp.text
        assert resp.json()["detail"]["code"] == "forbidden"

    def test_no_token_returns_401(
        self,
        client: TestClient,
        seeded_parent: User,
        seeded_eleve: User,
    ) -> None:
        resp = client.post(
            f"/api/users/{seeded_parent.pseudo}/children",
            json={"child_pseudo": seeded_eleve.pseudo},
        )
        assert resp.status_code == 401, resp.text
        assert resp.json()["detail"]["code"] == "invalid_token"

    def test_junk_token_returns_401(
        self,
        client: TestClient,
        seeded_parent: User,
        seeded_eleve: User,
    ) -> None:
        resp = client.post(
            f"/api/users/{seeded_parent.pseudo}/children",
            json={"child_pseudo": seeded_eleve.pseudo},
            headers={"Authorization": "Bearer not-a-jwt"},
        )
        assert resp.status_code == 401, resp.text
        assert resp.json()["detail"]["code"] == "invalid_token"


# ---------------------------------------------------------------------------
# POST .../children — 404 (anti-leak: 404 before 403)
# ---------------------------------------------------------------------------


class TestAddChildNotFound:
    def test_missing_parent_returns_404_not_403(
        self,
        client: TestClient,
        seeded_admin: User,
        seeded_eleve: User,
    ) -> None:
        """The URL names a parent that does not exist.

        We expect 404 ``user_not_found`` even for a legitimate
        admin caller — returning 403 here would leak the existence
        of the parent to a non-authorised caller (research trap 5).
        """
        resp = client.post(
            "/api/users/ghost/children",
            json={"child_pseudo": seeded_eleve.pseudo},
            headers=_bearer(seeded_admin),
        )
        assert resp.status_code == 404, resp.text
        assert resp.json()["detail"]["code"] == "user_not_found"

    def test_unauthorised_caller_on_missing_parent_returns_404_not_403(
        self,
        client: TestClient,
        seeded_eleve: User,
    ) -> None:
        """The 404-before-403 anti-leak invariant is **only** visible
        when the caller is not authorised.

        An eleve caller hits ``/api/users/ghost/children`` — a
        parent URL that does not exist. The caller is also not
        authorised. The 404 wins: the response is
        ``user_not_found``, not ``forbidden``. Returning 403 here
        would leak the (non-)existence of the parent to a
        non-authorised caller — research trap 5.
        """
        resp = client.post(
            "/api/users/ghost/children",
            json={"child_pseudo": seeded_eleve.pseudo},
            headers=_bearer(seeded_eleve),
        )
        assert resp.status_code == 404, resp.text
        assert resp.json()["detail"]["code"] == "user_not_found"

    def test_missing_child_returns_404(
        self,
        client: TestClient,
        seeded_admin: User,
        seeded_parent: User,
    ) -> None:
        resp = client.post(
            f"/api/users/{seeded_parent.pseudo}/children",
            json={"child_pseudo": "ghost"},
            headers=_bearer(seeded_admin),
        )
        assert resp.status_code == 404, resp.text
        assert resp.json()["detail"]["code"] == "user_not_found"


# ---------------------------------------------------------------------------
# POST .../children — input validation (Pydantic)
# ---------------------------------------------------------------------------


class TestAddChildValidation:
    def test_child_pseudo_too_short_returns_422(
        self,
        client: TestClient,
        seeded_admin: User,
        seeded_parent: User,
    ) -> None:
        resp = client.post(
            f"/api/users/{seeded_parent.pseudo}/children",
            json={"child_pseudo": "ab"},
            headers=_bearer(seeded_admin),
        )
        assert resp.status_code == 422

    def test_child_pseudo_with_dash_returns_422(
        self,
        client: TestClient,
        seeded_admin: User,
        seeded_parent: User,
    ) -> None:
        resp = client.post(
            f"/api/users/{seeded_parent.pseudo}/children",
            json={"child_pseudo": "ali-baba"},
            headers=_bearer(seeded_admin),
        )
        assert resp.status_code == 422

    def test_child_pseudo_too_long_returns_422(
        self,
        client: TestClient,
        seeded_admin: User,
        seeded_parent: User,
    ) -> None:
        resp = client.post(
            f"/api/users/{seeded_parent.pseudo}/children",
            json={"child_pseudo": "a" * 33},
            headers=_bearer(seeded_admin),
        )
        assert resp.status_code == 422

    def test_missing_body_returns_422(
        self,
        client: TestClient,
        seeded_admin: User,
        seeded_parent: User,
    ) -> None:
        resp = client.post(
            f"/api/users/{seeded_parent.pseudo}/children",
            json={},
            headers=_bearer(seeded_admin),
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST .../children — idempotence (the load-bearing one)
# ---------------------------------------------------------------------------


class TestAddChildIdempotence:
    def test_double_link_same_admin_first_201_then_200(
        self,
        client: TestClient,
        seeded_admin: User,
        seeded_parent: User,
        seeded_eleve: User,
        session_factory,
    ) -> None:
        """The same admin POSTs twice — second must be 200, not 409, not 500."""
        url = f"/api/users/{seeded_parent.pseudo}/children"
        first = client.post(
            url,
            json={"child_pseudo": seeded_eleve.pseudo},
            headers=_bearer(seeded_admin),
        )
        second = client.post(
            url,
            json={"child_pseudo": seeded_eleve.pseudo},
            headers=_bearer(seeded_admin),
        )
        assert first.status_code == 201, first.text
        assert second.status_code == 200, second.text


        with session_factory() as db:
            assert (
                db.query(ParentChildLink)
                .filter(
                    ParentChildLink.parent_pseudo == seeded_parent.pseudo,
                    ParentChildLink.child_pseudo == seeded_eleve.pseudo,
                )
                .count()
                == 1
            )

    def test_double_link_by_parent_then_admin(
        self,
        client: TestClient,
        seeded_admin: User,
        seeded_parent: User,
        seeded_eleve: User,
        session_factory,
    ) -> None:
        """Parent links first (owner), admin re-POSTs (idempotent)."""
        url = f"/api/users/{seeded_parent.pseudo}/children"
        first = client.post(
            url,
            json={"child_pseudo": seeded_eleve.pseudo},
            headers=_bearer(seeded_parent),
        )
        second = client.post(
            url,
            json={"child_pseudo": seeded_eleve.pseudo},
            headers=_bearer(seeded_admin),
        )
        assert first.status_code == 201, first.text
        assert second.status_code == 200, second.text


        with session_factory() as db:
            assert (
                db.query(ParentChildLink)
                .filter(
                    ParentChildLink.parent_pseudo == seeded_parent.pseudo,
                    ParentChildLink.child_pseudo == seeded_eleve.pseudo,
                )
                .count()
                == 1
            )


# ---------------------------------------------------------------------------
# POST .../children — logging hygiene
# ---------------------------------------------------------------------------


class TestAddChildLoggingHygiene:
    def test_logs_never_contain_password_or_hash(
        self,
        client: TestClient,
        seeded_admin: User,
        seeded_parent: User,
        seeded_eleve: User,
    ) -> None:
        """The new ``users.children.*`` log lines must never include
        password material or JWT tokens. The conftest's
        ``_isolated_loguru_sink`` already buffers every log line
        for this test; we only need to assert on the buffer's
        contents.

        We exercise all three log topics — ``created``,
        ``duplicate``, ``forbidden`` — so the assertion is not
        only about the happy path.
        """
        from loguru import logger

        log_buffer: list[str] = []
        handler_id = logger.add(
            lambda message: log_buffer.append(str(message)), level="DEBUG"
        )
        try:
            # Happy path → users.children.created
            client.post(
                f"/api/users/{seeded_parent.pseudo}/children",
                json={"child_pseudo": seeded_eleve.pseudo},
                headers=_bearer(seeded_admin),
            )
            # Idempotent re-POST → users.children.duplicate
            client.post(
                f"/api/users/{seeded_parent.pseudo}/children",
                json={"child_pseudo": seeded_eleve.pseudo},
                headers=_bearer(seeded_admin),
            )
            # Forbidden case → users.children.forbidden
            client.post(
                f"/api/users/{seeded_parent.pseudo}/children",
                json={"child_pseudo": seeded_eleve.pseudo},
                headers=_bearer(seeded_eleve),
            )
        finally:
            logger.remove(handler_id)

        joined = "\n".join(log_buffer)
        # The password, its bcrypt hash, and the JWT must never appear
        # in the log stream.
        assert "seedpassword1" not in joined
        assert "$2b$12$" not in joined
        # We don't pin the exact JWT material, but the bearer prefix
        # would be a strong signal: the routers never log the header.
        assert "Bearer " not in joined

        # The audit log lines were emitted (at least the created one
        # is guaranteed by the happy path).
        assert "users.children.created" in joined
        assert "users.children.duplicate" in joined
        assert "users.children.forbidden" in joined


# ---------------------------------------------------------------------------
# GET /api/users/{parent_pseudo}/children — happy path
# ---------------------------------------------------------------------------


class TestListChildrenHappyPath:
    def _seed_link(self, session_factory, parent: str, child: str) -> None:

        with session_factory() as db:
            db.add(ParentChildLink(parent_pseudo=parent, child_pseudo=child))
            db.commit()

    def test_parent_lists_own_children(
        self,
        client: TestClient,
        seeded_parent: User,
        seeded_eleve: User,
        seeded_another_eleve: User,
        session_factory,
    ) -> None:
        self._seed_link(session_factory, seeded_parent.pseudo, seeded_eleve.pseudo)
        self._seed_link(
            session_factory, seeded_parent.pseudo, seeded_another_eleve.pseudo
        )

        resp = client.get(
            f"/api/users/{seeded_parent.pseudo}/children",
            headers=_bearer(seeded_parent),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert isinstance(body, list)
        # Order is not guaranteed — compare as sets.
        assert {c["child_pseudo"] for c in body} == {
            seeded_eleve.pseudo,
            seeded_another_eleve.pseudo,
        }
        # Each element carries the role.
        for c in body:
            assert c["role"] in ("eleve", "parent", "admin")

    def test_admin_lists_a_parents_children(
        self,
        client: TestClient,
        seeded_admin: User,
        seeded_parent: User,
        seeded_eleve: User,
        session_factory,
    ) -> None:
        self._seed_link(session_factory, seeded_parent.pseudo, seeded_eleve.pseudo)

        resp = client.get(
            f"/api/users/{seeded_parent.pseudo}/children",
            headers=_bearer(seeded_admin),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body == [
            {"child_pseudo": seeded_eleve.pseudo, "role": "eleve"}
        ]

    def test_parent_with_no_children_returns_empty_list(
        self,
        client: TestClient,
        seeded_parent: User,
    ) -> None:
        """AC4 — empty list (NOT 404) when the parent has no children linked."""
        resp = client.get(
            f"/api/users/{seeded_parent.pseudo}/children",
            headers=_bearer(seeded_parent),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json() == []


# ---------------------------------------------------------------------------
# GET .../children — auth (incl. cross-tenant)
# ---------------------------------------------------------------------------


class TestListChildrenAuth:
    def test_eleve_caller_returns_403(
        self,
        client: TestClient,
        seeded_eleve: User,
        seeded_parent: User,
    ) -> None:
        resp = client.get(
            f"/api/users/{seeded_parent.pseudo}/children",
            headers=_bearer(seeded_eleve),
        )
        assert resp.status_code == 403, resp.text
        assert resp.json()["detail"]["code"] == "forbidden"

    def test_other_parent_caller_returns_403(
        self,
        client: TestClient,
        seeded_parent: User,
        seeded_another_parent: User,
        seeded_eleve: User,
        session_factory,
    ) -> None:
        """AC6 — multi-tenant isolation: parent B cannot list A's children.

        We seed a link for parent A first, so that a leakage would
        show up in the response. The test asserts both the 403 and
        the absence of any link in the response body.
        """

        with session_factory() as db:
            db.add(
                ParentChildLink(
                    parent_pseudo=seeded_parent.pseudo,
                    child_pseudo=seeded_eleve.pseudo,
                )
            )
            db.commit()

        resp = client.get(
            f"/api/users/{seeded_parent.pseudo}/children",
            headers=_bearer(seeded_another_parent),
        )
        assert resp.status_code == 403, resp.text
        assert resp.json()["detail"]["code"] == "forbidden"

        # The link must still be present (the 403 is the right answer,
        # not a silent drop of the data).
        with session_factory() as db:
            assert (
                db.query(ParentChildLink)
                .filter(ParentChildLink.parent_pseudo == seeded_parent.pseudo)
                .count()
                == 1
            )

    def test_no_token_returns_401(
        self,
        client: TestClient,
        seeded_parent: User,
    ) -> None:
        resp = client.get(f"/api/users/{seeded_parent.pseudo}/children")
        assert resp.status_code == 401, resp.text
        assert resp.json()["detail"]["code"] == "invalid_token"


# ---------------------------------------------------------------------------
# GET .../children — 404
# ---------------------------------------------------------------------------


class TestListChildrenNotFound:
    def test_missing_parent_returns_404(
        self,
        client: TestClient,
        seeded_admin: User,
    ) -> None:
        """Anti-leak: a non-existent parent returns 404, not 403."""
        resp = client.get(
            "/api/users/ghost/children",
            headers=_bearer(seeded_admin),
        )
        assert resp.status_code == 404, resp.text
        assert resp.json()["detail"]["code"] == "user_not_found"

    def test_unauthorised_caller_on_missing_parent_returns_404_not_403(
        self,
        client: TestClient,
        seeded_eleve: User,
    ) -> None:
        """Anti-leak 404-before-403 invariant for the GET endpoint.

        An eleve caller hits ``/api/users/ghost/children`` — a
        parent URL that does not exist. The 404 wins, exactly
        like the POST endpoint.
        """
        resp = client.get(
            "/api/users/ghost/children",
            headers=_bearer(seeded_eleve),
        )
        assert resp.status_code == 404, resp.text
        assert resp.json()["detail"]["code"] == "user_not_found"


# ---------------------------------------------------------------------------
# GET .../children — case insensitivity
# ---------------------------------------------------------------------------


class TestListChildrenCaseInsensitive:
    def test_url_capitalised_pseudo_resolves_to_lowercase_row(
        self,
        client: TestClient,
        seeded_admin: User,
        seeded_parent: User,
        seeded_eleve: User,
        session_factory,
    ) -> None:
        """``Ali`` in the URL matches the row stored as ``ali``."""

        with session_factory() as db:
            db.add(
                ParentChildLink(
                    parent_pseudo=seeded_parent.pseudo,
                    child_pseudo=seeded_eleve.pseudo,
                )
            )
            db.commit()

        resp = client.get(
            f"/api/users/{seeded_parent.pseudo.upper()}/children",
            headers=_bearer(seeded_admin),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert {c["child_pseudo"] for c in body} == {seeded_eleve.pseudo}


# ---------------------------------------------------------------------------
# GET .../children — response shape
# ---------------------------------------------------------------------------


class TestListChildrenResponseShape:
    def test_response_is_list_of_child_pseudo_role_pairs(
        self,
        client: TestClient,
        seeded_parent: User,
        seeded_eleve: User,
        seeded_another_eleve: User,
        session_factory,
    ) -> None:

        with session_factory() as db:
            db.add(
                ParentChildLink(
                    parent_pseudo=seeded_parent.pseudo,
                    child_pseudo=seeded_eleve.pseudo,
                )
            )
            db.add(
                ParentChildLink(
                    parent_pseudo=seeded_parent.pseudo,
                    child_pseudo=seeded_another_eleve.pseudo,
                )
            )
            db.commit()

        resp = client.get(
            f"/api/users/{seeded_parent.pseudo}/children",
            headers=_bearer(seeded_parent),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()

        # Top-level shape: JSON array.
        assert isinstance(body, list)
        assert len(body) == 2

        # Each element: {"child_pseudo": str, "role": <one of three>}.
        for element in body:
            assert set(element.keys()) == {"child_pseudo", "role"}
            assert isinstance(element["child_pseudo"], str)
            assert element["role"] in ("eleve", "parent", "admin")
