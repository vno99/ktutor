"""Tests for :func:`app.core.auth.middleware.assert_parent_linked_to_child_or_403`.

The helper is the cross-tenant guard for the parent dashboard
(s17, plan ``s17-dashboard-parent``). It complements
:func:`assert_jwt_pseudo_matches_or_403` (s15) but answers a
different question: **is ``claimed`` linked to ``user`` via
:class:`ParentChildLink`?** rather than "does ``claimed``
match ``user.pseudo``?".

Behaviour matrix proven here (the rule lives in
:func:`app.core.auth.middleware`, the callers just invoke it):

* ``claimed=None`` is a no-op — the endpoint did not receive
  a ``child_pseudo`` (e.g. ``GET /api/dashboard/parent``
  aggregates *all* linked children).
* ``claimed == user.pseudo`` (case-insensitive) is a no-op —
  a parent may inspect their own dashboard.
* ``user.role is UserRole.ADMIN`` is a no-op (admin bypass,
  ADR 005). No ``security.cross_tenant_attempt`` log.
* ``claimed`` is linked to ``user`` via :class:`ParentChildLink`
  → no-op.
* Otherwise → 403 ``forbidden`` + INFO
  ``security.cross_tenant_attempt`` log line.
"""
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import sessionmaker

from app.core.auth.middleware import assert_parent_linked_to_child_or_403
from app.core.auth.passwords import hash_password
from app.core.database.models import Base, ParentChildLink, User, UserRole

# ---------------------------------------------------------------------------
# RSA keypair + settings (duplicated from test_middleware.py per AGENTS.md
# "Pas de refactor transverse"). The helper does not need the keys, but
# importing middleware triggers a JWT-keypath lookup in ``get_db``'s
# dependency chain when other fixtures run.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def rsa_keypair(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    tmp = tmp_path_factory.mktemp("jwt_keys_parent_linked_helper")
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
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture()
def session_factory(db_engine):
    return sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)


@pytest.fixture()
def isolated_log_buffer() -> Iterator[list[str]]:
    """Drop the production loguru sink and yield a per-test buffer.

    The helper emits ``security.cross_tenant_attempt`` at INFO
    level on a block. We capture it so the tests can assert the
    line was emitted and that no token material leaks into it.
    """
    from loguru import logger

    buffer: list[str] = []
    handler_id = logger.add(lambda message: buffer.append(str(message)), level="DEBUG")
    try:
        yield buffer
    finally:
        logger.remove(handler_id)


# ---------------------------------------------------------------------------
# Seed helpers (duplicated from test_middleware / test_users_parent_child).
# ---------------------------------------------------------------------------


def _seeded_user(session_factory, pseudo: str, role: UserRole) -> User:
    with session_factory() as db:
        user = User(
            pseudo=pseudo,
            password_hash=hash_password("seedpassword1"),
            role=role,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user


def _seeded_link(session_factory, parent_pseudo: str, child_pseudo: str) -> None:
    with session_factory() as db:
        db.add(
            ParentChildLink(parent_pseudo=parent_pseudo, child_pseudo=child_pseudo)
        )
        db.commit()


@pytest.fixture()
def seeded_parent_alice(session_factory) -> User:
    return _seeded_user(session_factory, "alice", UserRole.PARENT)


@pytest.fixture()
def seeded_eleve_bob(session_factory) -> User:
    return _seeded_user(session_factory, "bob", UserRole.ELEVE)


@pytest.fixture()
def seeded_eleve_charlie(session_factory) -> User:
    return _seeded_user(session_factory, "charlie", UserRole.ELEVE)


@pytest.fixture()
def seeded_admin(session_factory) -> User:
    return _seeded_user(session_factory, "boss", UserRole.ADMIN)


# ---------------------------------------------------------------------------
# The rule, pinned at itself.
# ---------------------------------------------------------------------------


class TestAssertParentLinkedToChild:
    def test_claimed_none_is_noop(
        self,
        seeded_parent_alice: User,
        isolated_log_buffer: list[str],
        session_factory,
    ) -> None:
        """``claimed=None`` is the aggregation path (``GET /api/dashboard/parent``).
        No DB lookup, no INFO log on the no-op."""
        with session_factory() as db:
            assert_parent_linked_to_child_or_403(
                seeded_parent_alice, None, route="/api/dashboard/parent", db=db
            )
        joined = "\n".join(isolated_log_buffer)
        assert "security.cross_tenant_attempt" not in joined

    def test_claimed_self_is_noop(
        self,
        seeded_parent_alice: User,
        isolated_log_buffer: list[str],
        session_factory,
    ) -> None:
        """A parent asking for their own dashboard is allowed (edge case
        from s14 — a parent can be linked to any user, including a
        'self' link). No INFO log."""
        with session_factory() as db:
            assert_parent_linked_to_child_or_403(
                seeded_parent_alice,
                seeded_parent_alice.pseudo,
                route="/api/dashboard/parent/bob",
                db=db,
            )
        joined = "\n".join(isolated_log_buffer)
        assert "security.cross_tenant_attempt" not in joined

    def test_claimed_linked_child_passes(
        self,
        seeded_parent_alice: User,
        seeded_eleve_bob: User,
        isolated_log_buffer: list[str],
        session_factory,
    ) -> None:
        """The happy path: the parent is linked to ``claimed`` via a
        :class:`ParentChildLink` row. No exception, no INFO log."""
        _seeded_link(session_factory, seeded_parent_alice.pseudo, seeded_eleve_bob.pseudo)
        with session_factory() as db:
            assert_parent_linked_to_child_or_403(
                seeded_parent_alice,
                seeded_eleve_bob.pseudo,
                route="/api/dashboard/parent/bob",
                db=db,
            )
        joined = "\n".join(isolated_log_buffer)
        assert "security.cross_tenant_attempt" not in joined

    def test_claimed_unlinked_child_raises_403(
        self,
        seeded_parent_alice: User,
        seeded_eleve_bob: User,
        seeded_eleve_charlie: User,
        isolated_log_buffer: list[str],
        session_factory,
    ) -> None:
        """Cross-tenant attempt: Alice is linked to Bob but asks for
        Charlie. 403 ``forbidden``, and the INFO log carries the
        caller, the claimed pseudo, the role and the route — but
        NO token / jti / body material."""
        _seeded_link(session_factory, seeded_parent_alice.pseudo, seeded_eleve_bob.pseudo)
        with session_factory() as db, pytest.raises(HTTPException) as exc_info:
            assert_parent_linked_to_child_or_403(
                seeded_parent_alice,
                seeded_eleve_charlie.pseudo,
                route="/api/dashboard/parent/charlie",
                db=db,
            )
        assert exc_info.value.status_code == 403
        assert exc_info.value.detail == {
            "error": "Accès refusé.",
            "code": "forbidden",
        }

        joined = "\n".join(isolated_log_buffer)
        assert "security.cross_tenant_attempt" in joined
        assert "alice" in joined
        assert "charlie" in joined
        assert "parent" in joined
        assert "/api/dashboard/parent/charlie" in joined
        # The log must NOT carry token material (AGENTS.md § Backend
        # logging).
        assert "Bearer" not in joined
        assert "jti" not in joined

    def test_admin_bypasses_link_check(
        self,
        seeded_admin: User,
        seeded_eleve_bob: User,
        isolated_log_buffer: list[str],
        session_factory,
    ) -> None:
        """An admin can ask for any child's dashboard without a
        :class:`ParentChildLink` row (ADR 005). The admin-bypass
        log line is emitted at DEBUG; the cross-tenant INFO line
        is NOT emitted."""
        # No ``_seeded_link`` — admin is not in any link row.
        with session_factory() as db:
            assert_parent_linked_to_child_or_403(
                seeded_admin,
                seeded_eleve_bob.pseudo,
                route="/api/dashboard/parent/bob",
                db=db,
            )
        joined = "\n".join(isolated_log_buffer)
        assert "security.cross_tenant_attempt" not in joined
        assert "auth.middleware.admin_bypass" in joined

    def test_case_insensitive_match(
        self,
        seeded_parent_alice: User,
        seeded_eleve_bob: User,
        isolated_log_buffer: list[str],
        session_factory,
    ) -> None:
        """The functional index ``uq_users_pseudo_lower`` is the source
        of truth for case-insensitive pseudo equality. The helper
        must align: ``"BOB"`` resolves to the ``"bob"`` link row."""
        _seeded_link(session_factory, seeded_parent_alice.pseudo, seeded_eleve_bob.pseudo)
        with session_factory() as db:
            assert_parent_linked_to_child_or_403(
                seeded_parent_alice,
                "BOB",
                route="/api/dashboard/parent/bob",
                db=db,
            )
        joined = "\n".join(isolated_log_buffer)
        assert "security.cross_tenant_attempt" not in joined
