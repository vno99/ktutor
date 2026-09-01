"""Tests for the SQLAlchemy ``Document`` model."""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database.models import (
    Attempt,
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

    def test_create_probleme_exercise_with_statement_expected_answer_and_grading_criteria(
        self, session
    ) -> None:
        """s06 — ``probleme`` exercises store the statement/solution/criteria triple."""
        document_id = uuid.uuid4()
        statement = (
            "Un train part de Paris à 14h00 et roule à 120 km/h. Un autre train part de "
            "Lyon à 15h00 et roule à 150 km/h. À quelle heure se croisent-ils ?"
        )
        expected_answer = (
            "Étape 1 : la distance Paris-Lyon est 465 km.\n"
            "Étape 2 : le train 1 a 1h d'avance, il a parcouru 120 km au départ du train 2.\n"
            "Étape 3 : la distance restante est 465 - 120 = 345 km.\n"
            "Étape 4 : la vitesse relative est 120 + 150 = 270 km/h.\n"
            "Étape 5 : le temps de croisement est 345 / 270 = 1.28 h ≈ 1h17.\n"
            "Réponse : ils se croisent à 16h17 environ."
        )
        grading_criteria = [
            "L'élève identifie la distance Paris-Lyon",
            "L'élève calcule la vitesse relative",
            "L'élève convertit le temps en heures/minutes",
        ]
        ex = Exercise(
            student_pseudo="ali",
            subject=Subject.MATHS,
            type=ExerciseType.PROBLEME,
            document_id=document_id,
            statement=statement,
            expected_answer=expected_answer,
            grading_criteria=grading_criteria,
        )
        session.add(ex)
        session.commit()
        session.refresh(ex)

        assert ex.type is ExerciseType.PROBLEME
        assert ex.statement == statement
        assert ex.expected_answer == expected_answer
        assert ex.grading_criteria == grading_criteria
        # QCM payload stays None.
        assert ex.questions is None

    def test_create_redaction_exercise_with_statement_expected_answer_and_grading_criteria(
        self, session
    ) -> None:
        """s06 — ``redaction`` exercises store the statement/solution/criteria triple."""
        document_id = uuid.uuid4()
        statement = (
            "Rédige une nouvelle de 300 à 400 mots, registre narratif, dont le thème est "
            "un objet trouvé qui change la vie du protagoniste. Présente ton texte avec "
            "une introduction, un développement et une conclusion."
        )
        expected_answer = (
            "Introduction : présenter le contexte et l'objet mystérieux.\n"
            "Développement : raconter la découverte, le doute initial, puis le changement.\n"
            "Conclusion : la nouvelle situation du protagoniste."
        )
        grading_criteria = [
            "L'élève respecte la fourchette 300-400 mots",
            "L'élève utilise un registre narratif cohérent",
            "L'élève structure introduction, développement, conclusion",
        ]
        ex = Exercise(
            student_pseudo="ali",
            subject=Subject.FRANCAIS,
            type=ExerciseType.REDACTION,
            document_id=document_id,
            statement=statement,
            expected_answer=expected_answer,
            grading_criteria=grading_criteria,
        )
        session.add(ex)
        session.commit()
        session.refresh(ex)

        assert ex.type is ExerciseType.REDACTION
        assert ex.statement == statement
        assert ex.expected_answer == expected_answer
        assert ex.grading_criteria == grading_criteria
        assert ex.questions is None


class TestAttemptModel:
    def test_create_attempt_with_raw_answers(self, session) -> None:
        document_id = uuid.uuid4()
        exercise = Exercise(
            student_pseudo="ali",
            subject=Subject.MATHS,
            type=ExerciseType.QCM,
            document_id=document_id,
            questions=[
                {"question": "Q1", "options": ["a", "b", "c", "d"], "correct_index": 0}
            ],
        )
        session.add(exercise)
        session.commit()
        session.refresh(exercise)

        attempt = Attempt(
            exercise_id=exercise.id,
            student_pseudo="ali",
            attempt_number=1,
            is_success=True,
            raw_answers=[0],
        )
        session.add(attempt)
        session.commit()
        session.refresh(attempt)

        assert isinstance(attempt.id, uuid.UUID)
        assert attempt.exercise_id == exercise.id
        assert attempt.student_pseudo == "ali"
        assert attempt.attempt_number == 1
        assert attempt.is_success is True
        assert attempt.raw_answers == [0]
        assert attempt.answer_text is None
        assert attempt.correction_level is None
        assert isinstance(attempt.submitted_at, datetime)

    def test_two_attempts_have_distinct_ids(self, session) -> None:
        document_id = uuid.uuid4()
        exercise = Exercise(
            student_pseudo="ali",
            subject=Subject.MATHS,
            type=ExerciseType.QCM,
            document_id=document_id,
            questions=[
                {"question": "Q", "options": ["a", "b", "c", "d"], "correct_index": 0}
            ],
        )
        session.add(exercise)
        session.commit()
        session.refresh(exercise)

        a1 = Attempt(
            exercise_id=exercise.id,
            student_pseudo="ali",
            attempt_number=1,
            is_success=True,
            raw_answers=[0],
        )
        a2 = Attempt(
            exercise_id=exercise.id,
            student_pseudo="ali",
            attempt_number=2,
            is_success=False,
            raw_answers=[1],
        )
        session.add_all([a1, a2])
        session.commit()

        assert a1.id != a2.id

    def test_filter_by_pseudo_returns_only_matching_rows(self, session) -> None:
        document_id = uuid.uuid4()
        exercise = Exercise(
            student_pseudo="ali",
            subject=Subject.MATHS,
            type=ExerciseType.QCM,
            document_id=document_id,
            questions=[
                {"question": "Q", "options": ["a", "b", "c", "d"], "correct_index": 0}
            ],
        )
        session.add(exercise)
        session.commit()
        session.refresh(exercise)

        for pseudo, n in [("ali", 1), ("ali", 2), ("bob", 1)]:
            session.add(
                Attempt(
                    exercise_id=exercise.id,
                    student_pseudo=pseudo,
                    attempt_number=n,
                    is_success=True,
                    raw_answers=[0],
                )
            )
        session.commit()

        ali = session.query(Attempt).filter(Attempt.student_pseudo == "ali").all()
        bob = session.query(Attempt).filter(Attempt.student_pseudo == "bob").all()
        assert len(ali) == 2
        assert len(bob) == 1
