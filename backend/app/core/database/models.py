"""SQLAlchemy ORM models for ktutor."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Enum, Integer, String, func
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
