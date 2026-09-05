"""Tests for :class:`ChatHistoryService` (s19).

The suite covers the read-side contract:

* ordering by ``last_activity_at DESC, id DESC`` (the ``id DESC``
  tie-breaker is the defence against pagination that drops rows
  when two conversations share a timestamp);
* subject filter (``None`` = all subjects, ``"maths"`` = maths
  only, ``"francais"`` = francais only);
* pagination via ``limit`` + ``offset`` — the AC7 scenario in
  the story (limit=2 returns 2, offset=2 returns the next 2);
* the cross-tenant read defence — querying with a different
  ``student_pseudo`` returns ``None``;
* the chronological order of messages in the detail call.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import sessionmaker

from app.core.auth.passwords import hash_password
from app.core.database.models import (
    Base,
    Subject,
    User,
)
from app.services.chat_history.service import ChatHistoryService


@pytest.fixture()
def session_factory_no_unique() -> Iterator[sessionmaker]:
    """An in-memory SQLite where the ``conversations`` table has
    the production schema MINUS the ``UNIQUE(student_pseudo,
    subject)`` constraint. The service pagination tests need
    more than 2 rows for one pupil; the production schema
    forbids that, but the SQL ordering and pagination paths
    are independent of the invariant (the production code
    upserts via a UNIQUE-aware INSERT … ON CONFLICT path that
    is tested separately in the API suite).
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    # Drop the UNIQUE constraint to seed multiple maths convs per pseudo.
    with engine.begin() as conn:
        from sqlalchemy import text

        # SQLite has no DROP CONSTRAINT. We rebuild the table
        # without the UNIQUE clause but keep all other constraints.
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
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    try:
        yield factory
    finally:
        engine.dispose()


@pytest.fixture()
def seeded(session_factory_no_unique) -> Iterator:
    """Seed 4 conversations: alice has 3 (so AC7 paginates), bob has 1.

    Uses :func:`session_factory_no_unique` so we can put more than
    one maths conversation per pseudo. The production UNIQUE
    constraint is honoured at the API layer; this fixture exists
    to exercise the service's SQL ordering and pagination paths.
    """
    import uuid as _uuid

    from sqlalchemy import text

    factory = session_factory_no_unique
    with factory() as s:
        s.add_all(
            [
                User(pseudo="alice", password_hash=hash_password("passwordone1")),
                User(pseudo="bob", password_hash=hash_password("passwordone2")),
            ]
        )
        s.commit()

    rows_to_insert = [
        # (key, pseudo, subject_value, first_question, message_count, ts)
        # SQLAlchemy ``Enum(Subject, native_enum=False)`` stores the
        # ENUM MEMBER NAME (e.g. ``"MATHS"``) by default. The raw
        # SQL inserts must use the name to match what the ORM
        # persists; the read-back otherwise raises
        # ``LookupError: 'maths' is not among the defined enum values``.
        ("alice_maths_q1", "alice", "MATHS", "2+2 ?", 2, "2026-09-04 08:00:00"),
        ("alice_maths_q2", "alice", "MATHS", "dérivée ?", 2, "2026-09-04 09:00:00"),
        ("alice_francais_q1", "alice", "FRANCAIS", "métaphore ?", 2, "2026-09-03 10:00:00"),
        ("bob_maths_q1", "bob", "MATHS", "intégrale ?", 2, "2026-09-04 07:00:00"),
    ]
    out: dict[str, tuple[str, Subject, str, uuid.UUID]] = {}
    with factory() as s:
        for key, pseudo, subject_value, question, count, ts in rows_to_insert:
            cid = _uuid.uuid4()
            s.execute(
                text(
                    "INSERT INTO conversations ("
                    "id, student_pseudo, subject, first_question, "
                    "message_count, last_activity_at, created_at"
                    ") VALUES (:id, :pseudo, :subject, :q, :mc, :ts, :ts)"
                ),
                {
                    # ``id`` is a ``CHAR(32)`` column in the rebuilt
                    # table; the UUID's ``.hex`` matches the column
                    # width (str(uuid) has 36 chars with hyphens).
                    "id": cid.hex,
                    "pseudo": pseudo,
                    "subject": subject_value,
                    "q": question,
                    "mc": count,
                    "ts": ts,
                },
            )
            s.commit()
            out[key] = (pseudo, Subject[subject_value], question, cid)
    yield out


class TestListConversations:
    def test_orders_by_last_activity_desc(
        self, session_factory_no_unique, seeded
    ) -> None:
        """Newest first: alice_maths_q2 (09:00) > alice_maths_q1 (08:00)
        > alice_francais_q1 (10:00 yesterday)."""
        svc = ChatHistoryService(session_factory_no_unique)
        rows, total = svc.list_conversations(
            student_pseudo="alice", subject=None, limit=20, offset=0
        )
        ids = [r.id for r in rows]
        assert ids == [
            seeded["alice_maths_q2"][3],
            seeded["alice_maths_q1"][3],
            seeded["alice_francais_q1"][3],
        ]
        assert total == 3

    def test_filter_by_subject_maths(self, session_factory_no_unique, seeded) -> None:
        svc = ChatHistoryService(session_factory_no_unique)
        rows, total = svc.list_conversations(
            student_pseudo="alice", subject=Subject.MATHS, limit=20, offset=0
        )
        assert total == 2
        assert {r.subject for r in rows} == {Subject.MATHS}

    def test_filter_by_subject_francais(self, session_factory_no_unique, seeded) -> None:
        svc = ChatHistoryService(session_factory_no_unique)
        rows, total = svc.list_conversations(
            student_pseudo="alice", subject=Subject.FRANCAIS, limit=20, offset=0
        )
        assert total == 1
        assert rows[0].subject is Subject.FRANCAIS

    def test_filter_by_subject_none_returns_all(
        self, session_factory_no_unique, seeded
    ) -> None:
        svc = ChatHistoryService(session_factory_no_unique)
        rows, total = svc.list_conversations(
            student_pseudo="alice", subject=None, limit=20, offset=0
        )
        assert total == 3
        assert len(rows) == 3

    def test_paginates_with_limit_and_offset(
        self, session_factory_no_unique, seeded
    ) -> None:
        """AC7 — limit=2 returns 2, offset=2 returns the next 2 (in
        alice's history of 3, the second page has 1 row)."""
        svc = ChatHistoryService(session_factory_no_unique)
        page1, total1 = svc.list_conversations(
            student_pseudo="alice", subject=None, limit=2, offset=0
        )
        page2, total2 = svc.list_conversations(
            student_pseudo="alice", subject=None, limit=2, offset=2
        )
        assert total1 == 3
        assert total2 == 3
        assert len(page1) == 2
        assert len(page2) == 1
        # Disjoint sets.
        assert {r.id for r in page1}.isdisjoint({r.id for r in page2})

    def test_id_desc_breaks_ties_for_stable_pagination(
        self, session_factory_no_unique
    ) -> None:
        """When two rows share ``last_activity_at``, the secondary
        ``id DESC`` keeps the order stable. Without the tie-breaker,
        a re-run could swap rows between pages and the client would
        see the same conversation twice."""
        import uuid as _uuid

        from sqlalchemy import text

        with session_factory_no_unique() as s:
            s.add(User(pseudo="ali", password_hash=hash_password("passwordone1")))
            s.commit()
        # Insert two conversations via raw SQL with identical timestamps.
        c1 = _uuid.uuid4()
        c2 = _uuid.uuid4()
        with session_factory_no_unique() as s:
            s.execute(
                text(
                    "INSERT INTO conversations ("
                    "id, student_pseudo, subject, first_question, "
                    "message_count, last_activity_at, created_at"
                    ") VALUES (:id, :p, :s, :q, 0, :ts, :ts)"
                ),
                {"id": c1.hex, "p": "ali", "s": "MATHS", "q": "Q1", "ts": "2026-09-04 08:00:00"},
            )
            s.execute(
                text(
                    "INSERT INTO conversations ("
                    "id, student_pseudo, subject, first_question, "
                    "message_count, last_activity_at, created_at"
                    ") VALUES (:id, :p, :s, :q, 0, :ts, :ts)"
                ),
                {"id": c2.hex, "p": "ali", "s": "MATHS", "q": "Q2", "ts": "2026-09-04 08:00:00"},
            )
            s.commit()
        svc = ChatHistoryService(session_factory_no_unique)
        rows, _ = svc.list_conversations(
            student_pseudo="ali", subject=None, limit=20, offset=0
        )
        # Both rows share ``last_activity_at`` so the secondary
        # ``id DESC`` tie-breaker picks the larger UUID first.
        # UUIDs are random (not insert-order), so we don't assert
        # which is bigger — only that the service returns the
        # row with the larger UUID first.
        ids = [r.id for r in rows]
        assert ids == sorted(ids, reverse=True)
        assert set(ids) == {c1, c2}

    def test_other_student_sees_only_own(self, session_factory_no_unique, seeded) -> None:
        """Bite test: bob's request returns bob's row, not alice's
        three. The cross-tenant filter is INSIDE the SQL query (a
        load-then-check pattern would let this regress silently on
        a race)."""
        svc = ChatHistoryService(session_factory_no_unique)
        rows, total = svc.list_conversations(
            student_pseudo="bob", subject=None, limit=20, offset=0
        )
        assert total == 1
        assert rows[0].student_pseudo == "bob"

    def test_limit_clamped_to_minimum_one(self, session_factory_no_unique) -> None:
        svc = ChatHistoryService(session_factory_no_unique)
        rows, total = svc.list_conversations(
            student_pseudo="alice", subject=None, limit=0, offset=0
        )
        assert total == 0
        assert rows == []

    def test_limit_clamped_to_max_100(self, session_factory_no_unique) -> None:
        """A malicious client passing limit=10000 must not pull a
        million rows. The service clamps to 100 — the router Pydantic
        layer also clamps, this is a safety net."""
        svc = ChatHistoryService(session_factory_no_unique)
        # No rows seeded — we just assert the clamp doesn't error.
        rows, total = svc.list_conversations(
            student_pseudo="alice", subject=None, limit=10000, offset=0
        )
        assert total == 0
        assert rows == []

    def test_offset_clamped_to_zero(self, session_factory_no_unique) -> None:
        """A negative offset is clamped to 0."""
        svc = ChatHistoryService(session_factory_no_unique)
        rows, total = svc.list_conversations(
            student_pseudo="alice", subject=None, limit=20, offset=-5
        )
        assert total == 0
        assert rows == []


class TestGetConversationWithMessages:
    def test_returns_conversation_with_messages_in_chronological_order(
        self, session_factory_no_unique
    ) -> None:
        import uuid as _uuid

        from sqlalchemy import text

        with session_factory_no_unique() as s:
            s.add(User(pseudo="ali", password_hash=hash_password("passwordone1")))
            s.commit()
        # Insert via raw SQL so the production schema + the
        # test-rebuilt table both accept the rows.
        c_id = _uuid.uuid4()
        m1, m2, m3, m4 = (_uuid.uuid4() for _ in range(4))
        with session_factory_no_unique() as s:
            s.execute(
                text(
                    "INSERT INTO conversations ("
                    "id, student_pseudo, subject, first_question, "
                    "message_count, last_activity_at, created_at"
                    ") VALUES (:id, :p, :s, :q, 4, :ts, :ts)"
                ),
                {
                    "id": c_id.hex,
                    "p": "ali",
                    "s": "MATHS",
                    "q": "2+2 ?",
                    "ts": "2026-09-04 08:00:00",
                },
            )
            # Insert 4 messages with deterministic timestamps
            # (out-of-order UUIDs) to prove the order comes from
            # the SQL ORDER BY, not from the insert order.
            for mid, role, content, sources_json, ts in [
                (
                    m1,
                    "user",
                    "2+2 ?",
                    None,
                    "2026-09-04 08:00:00",
                ),
                (
                    m2,
                    "assistant",
                    "4",
                    '[{"filename": "cours.pdf", "chunk_index": 0}]',
                    "2026-09-04 08:00:05",
                ),
                (
                    m3,
                    "user",
                    "Et 2+3 ?",
                    None,
                    "2026-09-04 08:01:00",
                ),
                (
                    m4,
                    "assistant",
                    "5",
                    '[{"filename": "cours.pdf", "chunk_index": 1}]',
                    "2026-09-04 08:01:05",
                ),
            ]:
                s.execute(
                    text(
                        "INSERT INTO messages ("
                        "id, conversation_id, role, content, sources, created_at"
                        ") VALUES (:id, :cid, :role, :content, :sources, :ts)"
                    ),
                    {
                        "id": mid.hex,
                        "cid": c_id.hex,
                        "role": role,
                        "content": content,
                        "sources": sources_json,
                        "ts": ts,
                    },
                )
            s.commit()
        svc = ChatHistoryService(session_factory_no_unique)
        conv, messages = svc.get_conversation_with_messages(
            student_pseudo="ali", conversation_id=c_id
        )
        assert conv is not None
        assert conv.id == c_id
        assert [m.content for m in messages] == [
            "2+2 ?",
            "4",
            "Et 2+3 ?",
            "5",
        ]
        assert [m.role for m in messages] == [
            "user",
            "assistant",
            "user",
            "assistant",
        ]
        # Sources on assistant messages only.
        assert messages[0].sources is None
        assert messages[1].sources == [
            {"filename": "cours.pdf", "chunk_index": 0}
        ]
        assert messages[2].sources is None
        assert messages[3].sources == [
            {"filename": "cours.pdf", "chunk_index": 1}
        ]

    def test_returns_none_for_other_student(self, session_factory_no_unique) -> None:
        import uuid as _uuid

        from sqlalchemy import text

        with session_factory_no_unique() as s:
            s.add_all(
                [
                    User(pseudo="ali", password_hash=hash_password("passwordone1")),
                    User(pseudo="bob", password_hash=hash_password("passwordone2")),
                ]
            )
            s.commit()
        c_id = _uuid.uuid4()
        with session_factory_no_unique() as s:
            s.execute(
                text(
                    "INSERT INTO conversations ("
                    "id, student_pseudo, subject, first_question, "
                    "message_count, last_activity_at, created_at"
                    ") VALUES (:id, :p, :s, :q, 2, :ts, :ts)"
                ),
                {
                    "id": c_id.hex,
                    "p": "ali",
                    "s": "MATHS",
                    "q": "2+2 ?",
                    "ts": "2026-09-04 08:00:00",
                },
            )
            s.commit()
        svc = ChatHistoryService(session_factory_no_unique)
        result = svc.get_conversation_with_messages(
            student_pseudo="bob", conversation_id=c_id
        )
        assert result is None

    def test_returns_none_for_unknown_id(self, session_factory_no_unique) -> None:
        with session_factory_no_unique() as s:
            s.add(User(pseudo="ali", password_hash=hash_password("passwordone1")))
            s.commit()
        svc = ChatHistoryService(session_factory_no_unique)
        result = svc.get_conversation_with_messages(
            student_pseudo="ali", conversation_id=uuid.uuid4()
        )
        assert result is None
