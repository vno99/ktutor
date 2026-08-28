"""SQLAlchemy ORM models for ktutor."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
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
    minio_key: Mapped[str] = mapped_column(String(512), nullable=False)
    chunks_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus, name="document_status_enum", native_enum=False, length=32),
        nullable=False,
        default=DocumentStatus.INDEXED,
    )
    error_reason: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
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
