"""Tests for ``POST /api/auth/register`` (s12).

The endpoint is **public** (no JWT, no auth dependency): the test
client does not send any ``Authorization`` header. Validation is
Pydantic-driven (422); uniqueness is enforced both at the application
level (pre-check → 409) and at the SQL constraint level (``catch
IntegrityError`` → 409, covers the race).
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.auth.passwords import hash_password, verify_password
from app.core.database.models import Base, User, UserRole
from app.core.database.session import get_db
from app.main import app

# ---------------------------------------------------------------------------
# DB fixture: an isolated in-memory SQLite shared across the TestClient
# requests and the assertions. SQLite needs ``check_same_thread=False``
# + ``StaticPool`` so the same connection is reused by the TestClient
# and the test.
# ---------------------------------------------------------------------------


@pytest.fixture()
def db_engine():
    """Yield a fresh in-memory SQLite engine; create the schema."""
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
    """A ``sessionmaker`` bound to the test engine — usable outside the request."""
    return sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)


@pytest.fixture()
def client(session_factory) -> Iterator[TestClient]:
    """TestClient backed by an isolated in-memory SQLite whose schema we control."""

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


class TestRegisterHappyPath:
    """AC1 + AC2 + AC6 — successful registration."""

    def test_register_happy_path_returns_201_with_pseudo(self, client: TestClient) -> None:
        resp = client.post(
            "/api/auth/register",
            json={"pseudo": "ali", "password": "correcthorse"},
        )
        assert resp.status_code == 201, resp.text
        assert resp.json() == {"pseudo": "ali"}

    def test_register_hashes_password_with_bcrypt(self, client: TestClient, session_factory) -> None:
        resp = client.post(
            "/api/auth/register",
            json={"pseudo": "ali", "password": "correcthorse"},
        )
        assert resp.status_code == 201

        # Reach into the DB through the same in-memory engine.
        with session_factory() as db:
            user = db.query(User).filter(User.pseudo == "ali").one()

        assert user.password_hash.startswith("$2b$12$")
        assert user.password_hash != "correcthorse"
        assert verify_password("correcthorse", user.password_hash) is True

    def test_register_default_role_is_eleve(self, client: TestClient, session_factory) -> None:
        """AC6 — newly registered users get ``role='eleve'`` by default."""
        resp = client.post(
            "/api/auth/register",
            json={"pseudo": "ali", "password": "correcthorse"},
        )
        assert resp.status_code == 201

        with session_factory() as db:
            user = db.query(User).filter(User.pseudo == "ali").one()

        assert user.role is UserRole.ELEVE

    def test_register_preserves_pseudo_case(self, client: TestClient, session_factory) -> None:
        """D3 — the pseudo's original case is preserved in the row and the response."""
        resp = client.post(
            "/api/auth/register",
            json={"pseudo": "Ali_Baba", "password": "correcthorse"},
        )
        assert resp.status_code == 201
        assert resp.json() == {"pseudo": "Ali_Baba"}

        with session_factory() as db:
            user = db.query(User).filter(User.pseudo == "Ali_Baba").one()
        assert user.pseudo == "Ali_Baba"


class TestRegisterDuplicatePseudo:
    """AC3 — duplicate pseudo (case-insensitive) returns 409."""

    def test_register_duplicate_pseudo_returns_409(self, client: TestClient) -> None:
        first = client.post(
            "/api/auth/register",
            json={"pseudo": "ali", "password": "correcthorse"},
        )
        assert first.status_code == 201

        second = client.post(
            "/api/auth/register",
            json={"pseudo": "ali", "password": "differentpw1"},
        )
        assert second.status_code == 409
        body = second.json()
        assert body["detail"]["code"] == "pseudo_taken"
        assert "déjà" in body["detail"]["error"].lower() or "pris" in body["detail"]["error"].lower()

    def test_register_duplicate_pseudo_case_insensitive_returns_409(self, client: TestClient, session_factory) -> None:
        first = client.post(
            "/api/auth/register",
            json={"pseudo": "Ali", "password": "correcthorse"},
        )
        assert first.status_code == 201

        second = client.post(
            "/api/auth/register",
            json={"pseudo": "ali", "password": "differentpw1"},
        )
        assert second.status_code == 409
        assert second.json()["detail"]["code"] == "pseudo_taken"

        # The pre-existing row is preserved under its original case.
        with session_factory() as db:
            assert db.query(User).count() == 1
            row = db.query(User).one()
            assert row.pseudo == "Ali"

    def test_register_race_condition_raises_integrityerror_returns_409(
        self, client: TestClient, session_factory
    ) -> None:
        """Race condition — pre-check sees no row, but DB constraint catches it.

        We simulate by directly inserting a row that bypasses the router's
        pre-check, then calling the endpoint with a case-different variant
        of the same pseudo. The SQL constraint catches the duplicate and
        the router must map it to 409.
        """
        # Seed a row directly via the same engine.
        with session_factory() as db:
            db.add(
                User(
                    pseudo="Ali",
                    password_hash=hash_password("seedpassword1"),
                    role=UserRole.ELEVE,
                )
            )
            db.commit()

        resp = client.post(
            "/api/auth/register",
            json={"pseudo": "ali", "password": "correcthorse"},
        )
        assert resp.status_code == 409
        assert resp.json()["detail"]["code"] == "pseudo_taken"

        # No extra row was inserted.
        with session_factory() as db:
            assert db.query(User).count() == 1

    def test_register_race_condition_with_bypassed_precheck_returns_409(
        self, client: TestClient, session_factory, monkeypatch
    ) -> None:
        """Invariant 3 — even if the pre-check is bypassed, the SQL constraint
        plus the router's ``catch IntegrityError`` together return 409.

        We seed a row directly (bypassing the router's pre-check), then
        patch :meth:`Session.query` so the pre-check SELECT always
        returns ``None`` — the router proceeds to INSERT, the SQL
        constraint raises :class:`IntegrityError`, the router catches
        it and surfaces 409 (not 500).
        """
        # Seed a row that the SQL constraint will catch when the
        # router tries to insert a case-different variant.
        with session_factory() as db:
            db.add(
                User(
                    pseudo="Ali",
                    password_hash=hash_password("seedpassword1"),
                    role=UserRole.ELEVE,
                )
            )
            db.commit()

        from sqlalchemy.orm import Session

        original_query = Session.query

        def _query_bypassing_precheck(self, *entities, **kwargs):
            result = original_query(self, *entities, **kwargs)

            # Replace ``first()`` so the pre-check always returns None.
            def _always_none(self_):
                return None

            monkeypatch.setattr(type(result), "first", _always_none)
            return result

        monkeypatch.setattr(Session, "query", _query_bypassing_precheck)

        resp = client.post(
            "/api/auth/register",
            json={"pseudo": "ali", "password": "correcthorse"},
        )

        assert resp.status_code == 409, resp.text
        assert resp.json()["detail"]["code"] == "pseudo_taken"

        # The seeded row is still alone (no second row created).
        with session_factory() as db:
            assert db.query(User).count() == 1


class TestRegisterValidation:
    """AC4 + AC5 — invalid pseudo / weak password → 422."""

    def test_register_invalid_pseudo_too_short_returns_422(self, client: TestClient) -> None:
        resp = client.post(
            "/api/auth/register",
            json={"pseudo": "ab", "password": "correcthorse"},
        )
        assert resp.status_code == 422

    def test_register_invalid_pseudo_special_chars_returns_422(self, client: TestClient) -> None:
        resp = client.post(
            "/api/auth/register",
            json={"pseudo": "ali-baba", "password": "correcthorse"},
        )
        assert resp.status_code == 422

    def test_register_invalid_pseudo_too_long_returns_422(self, client: TestClient) -> None:
        resp = client.post(
            "/api/auth/register",
            json={"pseudo": "a" * 33, "password": "correcthorse"},
        )
        assert resp.status_code == 422

    def test_register_weak_password_too_short_returns_422(self, client: TestClient) -> None:
        resp = client.post(
            "/api/auth/register",
            json={"pseudo": "ali", "password": "short"},
        )
        assert resp.status_code == 422

    def test_register_password_too_long_bytes_returns_422(self, client: TestClient) -> None:
        """AC5 — ``"é" * 37`` is 37 chars (>= 8) but 74 octets → 422."""
        resp = client.post(
            "/api/auth/register",
            json={"pseudo": "ali", "password": "é" * 37},
        )
        assert resp.status_code == 422

    def test_register_missing_body_returns_422(self, client: TestClient) -> None:
        resp = client.post("/api/auth/register", json={})
        assert resp.status_code == 422


class TestRegisterLoggingHygiene:
    """No password or hash may leak through the logger."""

    def test_register_logs_never_contain_password_or_hash(self, client: TestClient) -> None:
        log_buffer: list[str] = []
        from loguru import logger

        handler_id = logger.add(lambda msg: log_buffer.append(str(msg)), level="DEBUG")
        try:
            client.post(
                "/api/auth/register",
                json={"pseudo": "ali", "password": "supersecretpw1"},
            )
            client.post(
                "/api/auth/register",
                json={"pseudo": "Ali", "password": "supersecretpw1"},
            )
        finally:
            logger.remove(handler_id)

        joined = "\n".join(log_buffer)
        assert "supersecretpw1" not in joined
        # The hash starts with $2b$12$ — make sure no log line carries it.
        assert "$2b$12$" not in joined
