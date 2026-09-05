"""Tests for the SQLAlchemy ``Document`` model."""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.core.auth.passwords import hash_password, verify_password
from app.core.database.models import (
    Attempt,
    Base,
    Document,
    DocumentStatus,
    Evaluation,
    EvaluationStatus,
    Exercise,
    ExerciseType,
    ParentChildLink,
    Subject,
    User,
    UserRole,
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

    def test_create_flashcards_exercise_with_cards(self, session) -> None:
        """s06b — ``flashcards`` exercises store the deck in the ``cards`` JSON column."""
        document_id = uuid.uuid4()
        cards = [
            {"front": "Quelle est la dérivée de x^2 ?", "back": "2x", "topic": "dérivées"},
            {"front": "Qu'est-ce qu'une primitive ?", "back": "Une fonction dont la dérivée...", "topic": None},
        ]
        ex = Exercise(
            student_pseudo="ali",
            subject=Subject.MATHS,
            type=ExerciseType.FLASHCARDS,
            document_id=document_id,
            cards=cards,
        )
        session.add(ex)
        session.commit()
        session.refresh(ex)

        assert ex.type is ExerciseType.FLASHCARDS
        assert ex.cards == cards
        # All other polymorphic columns stay None.
        assert ex.questions is None
        assert ex.statement is None
        assert ex.expected_answer is None
        assert ex.grading_criteria is None


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


class TestUserModel:
    """SQLAlchemy ``User`` model — s12 (auth).

    Covers:

    * basic row creation with default role;
    * case-insensitive uniqueness at the SQL constraint level
      (``UniqueConstraint(func.lower(User.pseudo), ...)``);
    * the bcrypt guarantee: ``password_hash`` is never plain text and
      round-trips through :func:`verify_password`.
    """

    def test_create_user_with_minimal_fields(self, session) -> None:
        user = User(
            pseudo="ali_baba",
            password_hash=hash_password("correcthorsebatterystaple"),
            role=UserRole.ELEVE,
        )
        session.add(user)
        session.commit()
        session.refresh(user)

        assert user.pseudo == "ali_baba"
        assert user.role is UserRole.ELEVE
        assert isinstance(user.created_at, datetime)

    def test_default_role_is_eleve(self, session) -> None:
        user = User(
            pseudo="ali",
            password_hash=hash_password("correcthorsebatterystaple"),
        )
        session.add(user)
        session.commit()
        session.refresh(user)

        assert user.role is UserRole.ELEVE

    def test_two_users_with_different_pseudos_coexist(self, session) -> None:
        a = User(pseudo="ali", password_hash=hash_password("passwordone1"))
        b = User(pseudo="bob", password_hash=hash_password("passwordtwo2"))
        session.add_all([a, b])
        session.commit()
        assert session.query(User).count() == 2

    def test_pseudo_unique_case_insensitive(self, session) -> None:
        """AC3 — pseudo unique case-insensitive at the SQL constraint level."""
        session.add(User(pseudo="Ali", password_hash=hash_password("passwordone1")))
        session.commit()
        session.add(User(pseudo="ali", password_hash=hash_password("passwordtwo2")))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

    def test_pseudo_unique_exact_case(self, session) -> None:
        """Sanity check: two distinct pseudos (different case + different chars) coexist."""
        session.add(User(pseudo="ali", password_hash=hash_password("passwordone1")))
        session.add(User(pseudo="bob", password_hash=hash_password("passwordtwo2")))
        session.commit()
        assert session.query(User).count() == 2

    def test_password_hash_not_plaintext(self, session) -> None:
        """AC2 — ``password_hash`` is bcrypt, never the plain text the user typed."""
        plain = "correcthorsebatterystaple"
        user = User(pseudo="ali", password_hash=hash_password(plain))
        session.add(user)
        session.commit()
        session.refresh(user)

        assert user.password_hash != plain
        assert user.password_hash.startswith("$2b$12$")
        # Round-trip: the wrapper accepts the original plain password.
        assert verify_password(plain, user.password_hash) is True
        # And rejects a different password.
        assert verify_password("wrong-horse", user.password_hash) is False


class TestParentChildLinkModel:
    """s14 — ``parent_child_links`` join table (many-to-many between ``User`` rows).

    Carries the contract for the persistence shape:

    * the table name and the column types are stable across the s14
      router (the router queries by ``func.lower`` over both FK
      columns, so the schema is the source of truth for that query);
    * the composite primary key ``(parent_pseudo, child_pseudo)``
      blocks duplicate links at the DB level (the router pre-check is
      UX, not security);
    * the FKs cascade on delete so an admin who removes a user via
      the DB does not leave orphan links;
    * there is **no** role constraint on ``child_pseudo`` — a parent
      can be linked to another parent (sibling-as-parent case),
      because the story explicitly authorises that.
    """

    def test_tablename_is_parent_child_links(self) -> None:
        assert ParentChildLink.__tablename__ == "parent_child_links"

    def test_table_is_registered_in_base_metadata(self) -> None:
        assert "parent_child_links" in Base.metadata.tables

    def test_create_link_minimal_fields(self, session) -> None:
        # Pre-condition — the FKs reference ``users.pseudo`` so the
        # parents and children must exist before the link can be
        # inserted.
        session.add_all(
            [
                User(
                    pseudo="pat", password_hash=hash_password("passwordone1"), role=UserRole.PARENT
                ),
                User(
                    pseudo="ali", password_hash=hash_password("passwordtwo2"), role=UserRole.ELEVE
                ),
            ]
        )
        session.commit()

        link = ParentChildLink(parent_pseudo="pat", child_pseudo="ali")
        session.add(link)
        session.commit()
        session.refresh(link)

        assert link.parent_pseudo == "pat"
        assert link.child_pseudo == "ali"
        assert isinstance(link.created_at, datetime)

    def test_composite_pk_rejects_duplicate_link(self, session) -> None:
        """The same ``(parent_pseudo, child_pseudo)`` pair cannot be inserted twice."""
        session.add_all(
            [
                User(
                    pseudo="pat", password_hash=hash_password("passwordone1"), role=UserRole.PARENT
                ),
                User(
                    pseudo="ali", password_hash=hash_password("passwordtwo2"), role=UserRole.ELEVE
                ),
            ]
        )
        session.commit()

        session.add(ParentChildLink(parent_pseudo="pat", child_pseudo="ali"))
        session.commit()

        session.add(ParentChildLink(parent_pseudo="pat", child_pseudo="ali"))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

    def test_child_pseudo_has_no_role_constraint(self, session) -> None:
        """A parent can be linked to another parent (sibling-as-parent case).

        The model must not enforce ``child.role is ELEVE`` — the
        router does not either, by design (research open question 4).
        """
        session.add_all(
            [
                User(
                    pseudo="pat", password_hash=hash_password("passwordone1"), role=UserRole.PARENT
                ),
                User(
                    pseudo="sam", password_hash=hash_password("passwordtwo2"), role=UserRole.PARENT
                ),
            ]
        )
        session.commit()

        link = ParentChildLink(parent_pseudo="pat", child_pseudo="sam")
        session.add(link)
        session.commit()
        session.refresh(link)
        assert link.child_pseudo == "sam"

    def test_filter_by_parent_returns_only_matching_links(self, session) -> None:
        for p, c in [("pat", "ali"), ("pat", "bob"), ("sam", "ali")]:
            session.add(
                ParentChildLink(parent_pseudo=p, child_pseudo=c)
            )
        session.commit()

        pat_links = (
            session.query(ParentChildLink)
            .filter(ParentChildLink.parent_pseudo == "pat")
            .all()
        )
        sam_links = (
            session.query(ParentChildLink)
            .filter(ParentChildLink.parent_pseudo == "sam")
            .all()
        )
        assert {l.child_pseudo for l in pat_links} == {"ali", "bob"}
        assert {l.child_pseudo for l in sam_links} == {"ali"}


class TestEvaluationModel:
    """SQLAlchemy ``Evaluation`` model (s18).

    Locks the persistence shape of the evaluation copy table:

    * UUID PK is auto-generated and survives a commit/refresh round-trip;
    * the minimum required fields (student_pseudo, subject, s3_key,
      filename, status) are enough to insert a row — every extracted
      field is nullable and will be filled by the service layer;
    * the :class:`EvaluationStatus` enum carries exactly the two
      values used by s18 and s18b (locked here so adding a third
      value is a deliberate decision, not an accident).
    """

    def test_evaluation_persists_with_minimum_fields(self, session) -> None:
        """Insert + read round-trip with only the required columns populated."""
        # The student_pseudo FK references ``users.pseudo`` so the
        # student must exist before the row can be inserted.
        session.add(
            User(pseudo="ali", password_hash=hash_password("passwordone1"))
        )
        session.commit()

        ev = Evaluation(
            student_pseudo="ali",
            subject=Subject.MATHS,
            s3_key="students/ali/abc",
            filename="copie.png",
            status=EvaluationStatus.SCORED,
            score=12.0,
            max_score=20.0,
        )
        session.add(ev)
        session.commit()
        session.refresh(ev)

        assert isinstance(ev.id, uuid.UUID)
        assert ev.student_pseudo == "ali"
        assert ev.subject is Subject.MATHS
        assert ev.status is EvaluationStatus.SCORED
        assert ev.score == 12.0
        assert ev.max_score == 20.0
        # Optional columns default to None on a minimum-field insert.
        assert ev.annotations is None
        assert ev.teacher_comments is None
        assert ev.ocr_text is None
        assert ev.ocr_confidence is None
        assert ev.error_reason is None
        assert isinstance(ev.created_at, datetime)

    def test_evaluation_status_enum_has_two_values(self) -> None:
        """s18b reuses this enum — lock the surface here so a third
        value cannot sneak in by accident (the manual-review workflow
        is the only extension point)."""
        assert {status.value for status in EvaluationStatus} == {
            "scored",
            "manual_review_needed",
        }

    def test_evaluation_persists_manual_review_when_score_missing(
        self, session
    ) -> None:
        """An evaluation copy without a score is still persisted
        (the row carries ``status=MANUAL_REVIEW_NEEDED`` and
        ``score=None``). A regression that treated "no score" as
        "don't persist" would break the manual review workflow in
        s18b."""
        session.add(
            User(pseudo="ali", password_hash=hash_password("passwordone1"))
        )
        session.commit()

        ev = Evaluation(
            student_pseudo="ali",
            subject=Subject.MATHS,
            s3_key="students/ali/xyz",
            filename="copie.png",
            status=EvaluationStatus.MANUAL_REVIEW_NEEDED,
            score=None,
            max_score=None,
        )
        session.add(ev)
        session.commit()
        session.refresh(ev)

        assert ev.status is EvaluationStatus.MANUAL_REVIEW_NEEDED
        assert ev.score is None
        assert ev.max_score is None
