"""SQLAlchemy ORM models for ktutor."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Index, Integer, String, func
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


class EvaluationStatus(str, enum.Enum):
    """Lifecycle status of an uploaded evaluation copy.

    An evaluation copy is **always** persisted (even if the score cannot
    be extracted); ``SCORED`` means the vision LLM produced a usable
    score, ``MANUAL_REVIEW_NEEDED`` means the score is missing or
    unreadable and a human must enter it (s18b). The two-state design
    (vs reusing :class:`DocumentStatus` which has an ``ERROR`` value)
    is recorded in ADR 013.
    """

    SCORED = "scored"
    MANUAL_REVIEW_NEEDED = "manual_review_needed"


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

    s15 — the ``student_pseudo`` column is now a real FK to
    ``users.pseudo`` (``ondelete="CASCADE"``). Deleting a user
    removes their documents automatically; the multi-tenancy
    contract is enforced at the DB level (last line of defence).
    """

    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    student_pseudo: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("users.pseudo", ondelete="CASCADE"),
        nullable=False,
        index=True,
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

    s15 — the ``student_pseudo`` FK to ``users.pseudo`` and the
    ``document_id`` FK to ``documents.id`` are now real DB constraints
    (``ondelete="CASCADE"``). The multi-tenancy contract is enforced
    at the DB level (last line of defence).
    """

    __tablename__ = "exercises"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    student_pseudo: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("users.pseudo", ondelete="CASCADE"),
        nullable=False,
        index=True,
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
        ForeignKey("documents.id", ondelete="CASCADE"),
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

    s15 — the FK to ``exercises.id`` and to ``users.pseudo`` are now
    real DB constraints (``ondelete="CASCADE"``). The multi-tenancy
    contract is enforced at the DB level (last line of defence).
    """

    __tablename__ = "attempts"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    exercise_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("exercises.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    student_pseudo: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("users.pseudo", ondelete="CASCADE"),
        nullable=False,
        index=True,
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


class Evaluation(Base):
    """A photo of a corrected exam copy uploaded by a student (s18).

    The model is the persistence target of the
    ``POST /api/evaluations/upload`` endpoint. The row is **always**
    written (even when the score cannot be extracted) so the student
    can be prompted to enter the score manually (s18b). The
    multi-tenancy contract is enforced at the DB level via the
    ``student_pseudo`` FK (``ondelete="CASCADE"``).

    Columns:

    * ``ocr_text`` keeps the full OCR transcript (s18b will
      re-process the same image without re-running the OCR).
    * ``ocr_confidence`` carries the multimodal LLM's confidence
      (None when the OCR returned ``ok=False``).
    * ``error_reason`` records why the extraction could not produce a
      score (low confidence, OCR unreachable, JSON parse failure).
    """

    __tablename__ = "evaluations"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    student_pseudo: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("users.pseudo", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    subject: Mapped[Subject] = mapped_column(
        Enum(Subject, name="subject_enum", native_enum=False, length=32),
        nullable=False,
    )
    s3_key: Mapped[str] = mapped_column(String(512), nullable=False)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[EvaluationStatus] = mapped_column(
        Enum(
            EvaluationStatus,
            name="evaluation_status_enum",
            native_enum=False,
            length=32,
        ),
        nullable=False,
    )
    score: Mapped[float | None] = mapped_column(nullable=True)
    max_score: Mapped[float | None] = mapped_column(nullable=True)
    annotations: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    teacher_comments: Mapped[str | None] = mapped_column(String(8192), nullable=True)
    ocr_text: Mapped[str | None] = mapped_column(String(8192), nullable=True)
    ocr_confidence: Mapped[float | None] = mapped_column(nullable=True)
    error_reason: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging only
        return (
            f"<Evaluation id={self.id} pseudo={self.student_pseudo!r} "
            f"subject={self.subject.value} status={self.status.value} "
            f"score={self.score}>"
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


class ParentChildLink(Base):
    """Many-to-many link between a parent and a child account (s14).

    The story authorises a parent to be linked to **any** other
    user — including another parent (the "sibling-as-parent" case
    in a recomposed family) or an admin. There is therefore no role
    constraint on ``child_pseudo``: only the FK to ``users.pseudo``
    is enforced. Cycle detection is intentionally absent at the
    s14 layer — the story says "for the POC, no cycle prevention",
    and any ``A → B → A`` would still be a valid edge in the
    composite-graph sense. A follow-up story (s15 or s18b) may
    revisit the question once the real parent-child workflows land.

    The composite primary key ``(parent_pseudo, child_pseudo)``
    blocks duplicate links at the DB level: the API router pre-checks
    before insert (UX), and the constraint catches the race where
    two concurrent requests pass the pre-check at the same time.
    The pre-check returns 200 (idempotence), not 409, on a hit.

    No Alembic migration is needed — ``init_db()``
    (``database/session.py:56``) creates the table via
    ``Base.metadata.create_all`` and SQLite in-memory tests pick
    it up at fixture time. The FKs are ``ondelete=CASCADE`` so
    removing a user cleans up the join table automatically.
    """

    __tablename__ = "parent_child_links"

    parent_pseudo: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("users.pseudo", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    child_pseudo: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("users.pseudo", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging only
        return (
            f"<ParentChildLink parent={self.parent_pseudo!r} "
            f"child={self.child_pseudo!r}>"
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
