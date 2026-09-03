"""SQLAlchemy ORM models for ktutor."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Enum, Index, Integer, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base shared by all ORM models."""


class DocumentStatus(str, enum.Enum):
    """Lifecycle status of an uploaded document."""

    INDEXED = "indexed"
    ERROR = "error"
    MANUAL_REVIEW_NEEDED = "manual_review_needed"


class Subject(str, enum.Enum):
    """Supported school subjects. Extensible; keep in sync with the CLI choices."""

    MATHS = "maths"
    FRANCAIS = "francais"


class ExerciseType(str, enum.Enum):
    """Discriminator for the ``exercises`` table.

    The QCM type is wired in s03; the others are reserved for s06/s06b and
    stay nullable on the model so the same table can carry them.
    """

    QCM = "qcm"
    # s06 — free-style exercises (maths probleme, francais redaction).
    # Note: s06b-flashcards adds FLASHCARDS to this same enum. The two
    # additions don't collide; the conflict on merge is a trivial union.
    PROBLEME = "probleme"
    REDACTION = "redaction"
    # s06b — flashcards (recto: question, verso: réponse). Polymorphique
    # via la colonne ``cards`` (JSON), distincte de ``questions`` (QCM)
    # et de ``statement``/``expected_answer``/``grading_criteria``
    # (probleme / redaction).
    FLASHCARDS = "flashcards"


class Document(Base):
    """A document uploaded by a student and indexed in their RAG.

    The foreign key to ``users.pseudo`` is documented in string form because
    the ``users`` table is owned by story s12 (auth). The constraint will be
    materialised by the s15 Alembic migration.
    """

    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    student_pseudo: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        # FK intentionally deferred to s15 migration (users table not yet created).
    )
    subject: Mapped[Subject] = mapped_column(
        Enum(Subject, name="subject_enum", native_enum=False, length=32),
        nullable=False,
    )
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    s3_key: Mapped[str] = mapped_column(String(512), nullable=False)
    chunks_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus, name="document_status_enum", native_enum=False, length=32),
        nullable=False,
        default=DocumentStatus.INDEXED,
    )
    error_reason: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging only
        return (
            f"<Document id={self.id} pseudo={self.student_pseudo!r} "
            f"subject={self.subject.value} status={self.status.value} "
            f"chunks={self.chunks_count}>"
        )


class Exercise(Base):
    """A generated exercise attached to a (student, subject, document).

    The model is polymorphic by ``type``. QCMs carry their full structure
    in ``questions`` (JSON); future types (probleme, redaction, flashcards)
    will use ``statement`` / ``expected_answer`` / ``grading_criteria``.

    The foreign key to ``users.pseudo`` is documented in string form because
    the ``users`` table is owned by story s12 (auth). The FK to ``documents``
    is also deferred: the constraint will be materialised by the s15
    Alembic migration.
    """

    __tablename__ = "exercises"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    student_pseudo: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        # FK intentionally deferred to s15 migration (users table not yet created).
    )
    subject: Mapped[Subject] = mapped_column(
        Enum(Subject, name="subject_enum", native_enum=False, length=32),
        nullable=False,
    )
    type: Mapped[ExerciseType] = mapped_column(
        Enum(ExerciseType, name="exercise_type_enum", native_enum=False, length=32),
        nullable=False,
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        # FK to ``documents.id`` (deferred to s15).
        nullable=False,
        index=True,
    )
    # Future-type payload (probleme / redaction / flashcards). Nullable for QCM.
    statement: Mapped[str | None] = mapped_column(String(8192), nullable=True)
    expected_answer: Mapped[str | None] = mapped_column(String(8192), nullable=True)
    grading_criteria: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    # QCM payload — list of {question, options, correct_index}.
    questions: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    # s06b — flashcards payload — list of {front, back, topic}.
    cards: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging only
        return (
            f"<Exercise id={self.id} pseudo={self.student_pseudo!r} "
            f"type={self.type.value} subject={self.subject.value}>"
        )


class Attempt(Base):
    """A single submission to an exercise by a student.

    QCM attempts (s04) populate ``raw_answers`` only — ``answer_text`` and
    ``correction_level`` stay NULL until s07 (rédaction) and s08 (correction
    progressive) wire them. The columns are pre-created here so the schema
    is stable across the s04 → s08 stories; no Alembic migration is needed
    because ``init_db()`` applies the full ``Base`` metadata in dev/CI.

    The foreign key to ``users.pseudo`` and to ``exercises.id`` is
    documented in string form because the ``users`` table is owned by
    story s12 (auth). The constraints will be materialised by the s15
    Alembic migration.
    """

    __tablename__ = "attempts"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    exercise_id: Mapped[uuid.UUID] = mapped_column(
        # FK to ``exercises.id`` (deferred to s15).
        nullable=False,
        index=True,
    )
    student_pseudo: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        # FK intentionally deferred to s15 migration (users table not yet created).
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    is_success: Mapped[bool] = mapped_column(nullable=False)
    raw_answers: Mapped[list[int]] = mapped_column(JSON, nullable=False)
    answer_text: Mapped[str | None] = mapped_column(String(8192), nullable=True)
    correction_level: Mapped[str | None] = mapped_column(String(32), nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging only
        return (
            f"<Attempt id={self.id} pseudo={self.student_pseudo!r} "
            f"exercise_id={self.exercise_id} attempt_number={self.attempt_number} "
            f"is_success={self.is_success}>"
        )


class UserRole(str, enum.Enum):
    """Role discriminator for the ``users`` table.

    Aligned with ADR 005 § « register public crée ``eleve`` uniquement »:
    ``parent`` and ``admin`` are created by an admin via
    ``POST /api/users`` (s13b); ``POST /api/auth/register`` creates
    ``eleve`` only (s12).
    """

    ELEVE = "eleve"
    PARENT = "parent"
    ADMIN = "admin"


class User(Base):
    """An end-user account (student, parent, or admin).

    Owned by story s12 (auth). The case-insensitive uniqueness of
    ``pseudo`` is enforced at the DB level via
    ``UniqueConstraint(func.lower(pseudo), ...)`` so the database is
    the last line of defence against duplicates (``Ali`` vs ``ali``).
    The router applies a pre-check to fail fast on the common case,
    but the constraint catches the race condition where two concurrent
    requests pass the pre-check at the same time.

    The password is stored as a bcrypt hash (``$2b$12$...``); the
    schema in :mod:`app.api.auth.schemas` is the entry point that
    enforces length and encoding invariants.
    """

    __tablename__ = "users"
    __table_args__ = ()  # The functional unique index is appended after the class is built.

    pseudo: Mapped[str] = mapped_column(
        String(32),
        primary_key=True,
        nullable=False,
    )
    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role_enum", native_enum=False, length=16),
        nullable=False,
        default=UserRole.ELEVE,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging only
        return (
            f"<User pseudo={self.pseudo!r} role={self.role.value}>"
        )


# Case-insensitive uniqueness (AC3, D3): a functional unique index on
# ``LOWER(pseudo)``. ``UniqueConstraint`` would expand ``func.lower``
# to a virtual column in the CREATE TABLE, which SQLite refuses
# (``no such column: pseudo_lower``); an ``Index`` is the idiomatic
# SQLAlchemy 2.0 way and is supported by both SQLite (tests) and
# PostgreSQL (production). The DB is the *only* source of truth —
# the router pre-check is UX, not security.
Index(
    "uq_users_pseudo_lower",
    func.lower(User.__table__.c.pseudo),
    unique=True,
)
