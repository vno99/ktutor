"""Tests for the SQLAlchemy ``Document`` model."""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database.models import (
    Base,
    Document,
    DocumentStatus,
    Exercise,
    ExerciseType,
    Subject,
)


@pytest.fixture()
def session():
    """In-memory SQLite session, with ``Base.metadata.create_all`` applied."""
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    s = Session()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


class TestDocumentModel:
    def test_create_document_with_minimal_fields(self, session) -> None:
        doc = Document(
            student_pseudo="ali",
            subject=Subject.MATHS,
            filename="cours.pdf",
            s3_key="students/ali/abc.pdf",
            chunks_count=10,
            status=DocumentStatus.INDEXED,
        )
        session.add(doc)
        session.commit()
        session.refresh(doc)

        assert isinstance(doc.id, uuid.UUID)
        assert doc.student_pseudo == "ali"
        assert doc.subject is Subject.MATHS
        assert doc.status is DocumentStatus.INDEXED
        assert doc.chunks_count == 10
        assert doc.error_reason is None
        assert isinstance(doc.created_at, datetime)

    def test_two_documents_have_distinct_ids(self, session) -> None:
        a = Document(
            student_pseudo="ali",
            subject=Subject.MATHS,
            filename="a.pdf",
            s3_key="k1",
            chunks_count=1,
            status=DocumentStatus.INDEXED,
        )
        b = Document(
            student_pseudo="bob",
            subject=Subject.FRANCAIS,
            filename="b.pdf",
            s3_key="k2",
            chunks_count=2,
            status=DocumentStatus.MANUAL_REVIEW_NEEDED,
            error_reason="low_confidence",
        )
        session.add_all([a, b])
        session.commit()

        assert a.id != b.id

    def test_filter_by_pseudo_returns_only_matching_rows(self, session) -> None:
        for pseudo, subject in [
            ("ali", Subject.MATHS),
            ("ali", Subject.FRANCAIS),
            ("bob", Subject.MATHS),
        ]:
            session.add(
                Document(
                    student_pseudo=pseudo,
                    subject=subject,
                    filename=f"{pseudo}-{subject.value}.pdf",
                    s3_key="k",
                    chunks_count=0,
                    status=DocumentStatus.INDEXED,
                )
            )
        session.commit()

        ali_docs = session.query(Document).filter(Document.student_pseudo == "ali").all()
        bob_docs = session.query(Document).filter(Document.student_pseudo == "bob").all()
        assert len(ali_docs) == 2
        assert len(bob_docs) == 1

    def test_error_reason_can_be_recorded(self, session) -> None:
        doc = Document(
            student_pseudo="ali",
            subject=Subject.MATHS,
            filename="x.pdf",
            s3_key="k",
            chunks_count=0,
            status=DocumentStatus.ERROR,
            error_reason="ocr_low_confidence",
        )
        session.add(doc)
        session.commit()
        session.refresh(doc)
        assert doc.status is DocumentStatus.ERROR
        assert doc.error_reason == "ocr_low_confidence"


class TestExerciseModel:
    def test_create_qcm_exercise_with_questions(self, session) -> None:
        document_id = uuid.uuid4()
        questions = [
            {
                "question": "What is 2+2?",
                "options": ["1", "2", "3", "4"],
                "correct_index": 3,
            }
        ]
        ex = Exercise(
            student_pseudo="ali",
            subject=Subject.MATHS,
            type=ExerciseType.QCM,
            document_id=document_id,
            questions=questions,
        )
        session.add(ex)
        session.commit()
        session.refresh(ex)

        assert isinstance(ex.id, uuid.UUID)
        assert ex.student_pseudo == "ali"
        assert ex.type is ExerciseType.QCM
        assert ex.document_id == document_id
        assert ex.questions == questions
        assert ex.statement is None
        assert ex.expected_answer is None
        assert ex.grading_criteria is None
        assert isinstance(ex.created_at, datetime)

    def test_filter_by_pseudo_returns_only_matching_rows(self, session) -> None:
        document_id = uuid.uuid4()
        for pseudo in ("ali", "bob"):
            session.add(
                Exercise(
                    student_pseudo=pseudo,
                    subject=Subject.MATHS,
                    type=ExerciseType.QCM,
                    document_id=document_id,
                    questions=[{"question": "Q", "options": ["a", "b", "c", "d"], "correct_index": 0}],
                )
            )
        session.commit()

        ali = session.query(Exercise).filter(Exercise.student_pseudo == "ali").all()
        bob = session.query(Exercise).filter(Exercise.student_pseudo == "bob").all()
        assert len(ali) == 1
        assert len(bob) == 1
        assert ali[0].student_pseudo == "ali"
        assert bob[0].student_pseudo == "bob"
