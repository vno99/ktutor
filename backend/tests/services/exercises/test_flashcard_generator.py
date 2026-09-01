"""Tests for the ``FlashcardGenerator`` service (s06b).

Pattern: copy the ``_ScriptedLlm``, ``_TrackingSession``, ``memory_db``,
``_SessionFactory`` fixtures from ``test_qcm_generator.py``. The cross-tenant
bite (``test_flashcards_cross_tenant_raises_document_not_found``) is the
load-bearing assertion: removing the ``document.student_pseudo == pseudo``
check must turn it red.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from typing import Any

import chromadb
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
from app.services.rag.chroma_store import ChromaStore
from app.services.rag.embeddings import EmbeddingProvider
from app.services.rag.retriever import Retriever

# ---------------------------------------------------------------------------
# Test doubles (reused from test_qcm_generator.py)
# ---------------------------------------------------------------------------


class _FakeEmbeddings(EmbeddingProvider):
    """Constant-vector embeddings; the retriever does not use them in
    :meth:`get_chunks_for_document`, but the constructor requires one."""

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[0.1, 0.2, 0.3] for _ in texts]


class _ScriptedLlm:
    """Drop-in replacement for ``LlmClient`` returning a scripted sequence."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.calls: list[list[Any]] = []

    def invoke(self, messages: list[Any]) -> Any:
        from langchain_core.messages import AIMessage

        self.calls.append(list(messages))
        if not self._responses:
            raise AssertionError("LLM called more times than scripted responses.")
        text = self._responses.pop(0)
        return AIMessage(content=text)


class _TrackingSession:
    """Wraps a real SQLAlchemy session, recording every ``add`` call."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.added: list[Any] = []

    def add(self, obj: Any) -> None:
        self.added.append(obj)
        self._inner.add(obj)

    def commit(self) -> None:
        self._inner.commit()

    def rollback(self) -> None:
        self._inner.rollback()

    def get(self, *args: Any, **kwargs: Any) -> Any:
        return self._inner.get(*args, **kwargs)

    def refresh(self, *args: Any, **kwargs: Any) -> Any:
        return self._inner.refresh(*args, **kwargs)


def _good_flashcards_json(n: int = 3, *, with_topic: bool = True) -> str:
    """Return a well-formed flashcards JSON payload with ``n`` cards."""
    cards: list[dict[str, Any]] = []
    for i in range(n):
        cards.append(
            {
                "front": f"Question {i + 1} ?",
                "back": f"Reponse {i + 1}.",
                "topic": "algebre" if with_topic else None,
            }
        )
    return json.dumps({"cards": cards})


def _seed_document_for_pseudo(
    chroma: ChromaStore, pseudo: str, subject: str, document_id: uuid.UUID
) -> None:
    coll = chroma.get_collection(subject, pseudo)
    chunks = [
        {
            "id": f"{pseudo}-{document_id}-0",
            "content": "La derivee de x^2 est 2x.",
            "metadata": {
                "chunk_index": 0,
                "filename": "cours.pdf",
                "document_id": str(document_id),
            },
        },
        {
            "id": f"{pseudo}-{document_id}-1",
            "content": "La derivee de sin(x) est cos(x).",
            "metadata": {
                "chunk_index": 1,
                "filename": "cours.pdf",
                "document_id": str(document_id),
            },
        },
    ]
    chroma.add_chunks(coll, chunks, [[0.1, 0.2, 0.3] for _ in chunks])


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def chroma_store() -> ChromaStore:
    return ChromaStore(client=chromadb.EphemeralClient())


@pytest.fixture()
def retriever(chroma_store: ChromaStore) -> Retriever:
    return Retriever(chroma_store=chroma_store, embeddings=_FakeEmbeddings())


@pytest.fixture()
def unique_pseudo() -> str:
    return f"u{uuid.uuid4().hex[:10]}"


@pytest.fixture()
def sample_document_id() -> uuid.UUID:
    return uuid.UUID("11111111-1111-1111-1111-111111111111")


@pytest.fixture()
def seeded_chroma(
    chroma_store: ChromaStore,
    unique_pseudo: str,
    sample_document_id: uuid.UUID,
) -> tuple[ChromaStore, str, uuid.UUID]:
    _seed_document_for_pseudo(chroma_store, unique_pseudo, "maths", sample_document_id)
    return chroma_store, unique_pseudo, sample_document_id


@pytest.fixture()
def memory_db() -> Callable[[], Any]:
    """Factory returning a fresh in-memory session bound to an engine that
    has the ``Base`` metadata applied."""

    def _factory() -> Any:
        engine = create_engine("sqlite:///:memory:", future=True)
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
        return Session()

    return _factory


class _SessionFactory:
    """Returns a single tracking wrapper around a session; subsequent calls
    yield the same wrapper so the test can introspect what was added."""

    def __init__(self, inner_factory: Callable[[], Any]) -> None:
        self._inner_factory = inner_factory
        self._wrapper: _TrackingSession | None = None

    def __call__(self) -> _TrackingSession:
        if self._wrapper is None:
            self._wrapper = _TrackingSession(self._inner_factory())
        return self._wrapper

    @property
    def wrapper(self) -> _TrackingSession:
        assert self._wrapper is not None
        return self._wrapper


@pytest.fixture()
def tracking_session(memory_db: Callable[[], Any]) -> _SessionFactory:
    """A session factory that returns the same tracking wrapper on every
    call. Allows tests to seed a ``Document`` (via the wrapper) and later
    assert the generator added an ``Exercise`` to the same session."""
    return _SessionFactory(memory_db)


def _seed_document(tracking: _SessionFactory, pseudo: str, doc_id: uuid.UUID) -> None:
    session = tracking()
    session.add(
        Document(
            id=doc_id,
            student_pseudo=pseudo,
            subject=Subject.MATHS,
            filename="cours.pdf",
            s3_key=f"students/{pseudo}/{doc_id}.pdf",
            chunks_count=2,
            status=DocumentStatus.INDEXED,
        )
    )
    session.commit()


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


class TestSchema:
    def test_flashcard_schema_validates_front_back_and_topic(self) -> None:
        from app.services.exercises.flashcard_generator import FlashcardSchema

        c = FlashcardSchema(front="Q?", back="A.", topic="topic")
        assert c.front == "Q?"
        assert c.back == "A."
        assert c.topic == "topic"

    def test_flashcard_schema_rejects_empty_front(self) -> None:
        from pydantic import ValidationError

        from app.services.exercises.flashcard_generator import FlashcardSchema

        with pytest.raises(ValidationError):
            FlashcardSchema(front="", back="A.")

    def test_flashcard_schema_rejects_empty_back(self) -> None:
        from pydantic import ValidationError

        from app.services.exercises.flashcard_generator import FlashcardSchema

        with pytest.raises(ValidationError):
            FlashcardSchema(front="Q?", back="")

    def test_flashcard_schema_coerces_empty_topic_to_none(self) -> None:
        """D6 — the LLM may produce ``topic=""``, which the validator coerces to None."""
        from app.services.exercises.flashcard_generator import FlashcardSchema

        c = FlashcardSchema(front="Q?", back="A.", topic="")
        assert c.topic is None

    def test_flashcard_schema_topic_default_is_none(self) -> None:
        """D6 — ``topic`` is optional, defaults to None."""
        from app.services.exercises.flashcard_generator import FlashcardSchema

        c = FlashcardSchema(front="Q?", back="A.")
        assert c.topic is None

    def test_flashcard_schema_rejects_front_over_200_chars(self) -> None:
        """Piège 4 — the schema enforces 200 chars on the question."""
        from pydantic import ValidationError

        from app.services.exercises.flashcard_generator import FlashcardSchema

        with pytest.raises(ValidationError):
            FlashcardSchema(front="x" * 201, back="A.")

    def test_flashcard_schema_rejects_back_over_200_chars(self) -> None:
        """Piège 4 — the schema enforces 200 chars on the answer."""
        from pydantic import ValidationError

        from app.services.exercises.flashcard_generator import FlashcardSchema

        with pytest.raises(ValidationError):
            FlashcardSchema(front="Q?", back="x" * 201)


# ---------------------------------------------------------------------------
# AC1 + AC6 — happy path
# ---------------------------------------------------------------------------


class TestGenerateHappyPath:
    def test_flashcards_returns_validated_pydantic_deck(
        self,
        retriever: Retriever,
        seeded_chroma: tuple[ChromaStore, str, uuid.UUID],
        tracking_session: _SessionFactory,
    ) -> None:
        from app.services.exercises.flashcard_generator import (
            FlashcardDeck,
            FlashcardGenerator,
        )

        _chroma, pseudo, doc_id = seeded_chroma
        _seed_document(tracking_session, pseudo, doc_id)
        llm = _ScriptedLlm([_good_flashcards_json(10)])
        gen = FlashcardGenerator(
            llm=llm,  # type: ignore[arg-type]
            retriever=retriever,
            session_factory=tracking_session,
        )
        result = gen.generate(pseudo, "maths", str(doc_id), n=10)
        assert isinstance(result.deck, FlashcardDeck)
        assert len(result.deck.cards) == 10
        for card in result.deck.cards:
            assert card.front
            assert card.back

    def test_flashcards_json_output_is_parseable(
        self,
        retriever: Retriever,
        seeded_chroma: tuple[ChromaStore, str, uuid.UUID],
        tracking_session: _SessionFactory,
    ) -> None:
        """AC2 — the LLM output round-trips through ``json.loads``."""
        from app.services.exercises.flashcard_generator import FlashcardGenerator

        _chroma, pseudo, doc_id = seeded_chroma
        _seed_document(tracking_session, pseudo, doc_id)
        llm = _ScriptedLlm([_good_flashcards_json(5)])
        gen = FlashcardGenerator(
            llm=llm,  # type: ignore[arg-type]
            retriever=retriever,
            session_factory=tracking_session,
        )
        result = gen.generate(pseudo, "maths", str(doc_id), n=5)
        parsed = json.loads(result.raw)
        assert "cards" in parsed
        assert len(parsed["cards"]) == 5


# ---------------------------------------------------------------------------
# AC3 — chunk filter by document_id
# ---------------------------------------------------------------------------


class TestDocumentFilter:
    def test_flashcards_filter_chunks_by_document_id(
        self,
        chroma_store: ChromaStore,
        retriever: Retriever,
        unique_pseudo: str,
        tracking_session: _SessionFactory,
    ) -> None:
        """AC3 — only chunks belonging to the requested document reach the LLM.

        We seed two documents for the same pseudo. The scripted LLM
        receives the chunks in the user prompt; we assert that the prompt
        references the target document's content and not the other one.
        """
        from app.services.exercises.flashcard_generator import FlashcardGenerator

        target_id = uuid.uuid4()
        other_id = uuid.uuid4()
        coll = chroma_store.get_collection("maths", unique_pseudo)
        chroma_store.add_chunks(
            coll,
            [
                {
                    "id": "target-0",
                    "content": "TARGET_CONTENT: derivees de polynomes",
                    "metadata": {
                        "chunk_index": 0,
                        "filename": "target.pdf",
                        "document_id": str(target_id),
                    },
                }
            ],
            [[0.1, 0.2, 0.3]],
        )
        chroma_store.add_chunks(
            coll,
            [
                {
                    "id": "other-0",
                    "content": "OTHER_CONTENT: trigonometrie avancee",
                    "metadata": {
                        "chunk_index": 0,
                        "filename": "other.pdf",
                        "document_id": str(other_id),
                    },
                }
            ],
            [[0.1, 0.2, 0.3]],
        )

        _seed_document(tracking_session, unique_pseudo, target_id)

        llm = _ScriptedLlm([_good_flashcards_json(2)])
        gen = FlashcardGenerator(
            llm=llm,  # type: ignore[arg-type]
            retriever=retriever,
            session_factory=tracking_session,
        )
        gen.generate(unique_pseudo, "maths", str(target_id), n=2)
        # The LLM was called exactly once; the user prompt must mention the
        # target's content and never the other document's content.
        assert len(llm.calls) == 1
        prompt = llm.calls[0][1].content  # type: ignore[index]
        assert "TARGET_CONTENT" in prompt
        assert "OTHER_CONTENT" not in prompt

    def test_flashcards_no_chunks_raises(
        self,
        retriever: Retriever,
        chroma_store: ChromaStore,
        unique_pseudo: str,
        tracking_session: _SessionFactory,
    ) -> None:
        from app.services.exercises.flashcard_generator import (
            FlashcardGenerationError,
            FlashcardGenerator,
        )

        doc_id = uuid.uuid4()
        _seed_document(tracking_session, unique_pseudo, doc_id)
        llm = _ScriptedLlm([])
        gen = FlashcardGenerator(
            llm=llm,  # type: ignore[arg-type]
            retriever=retriever,
            session_factory=tracking_session,
        )
        with pytest.raises(FlashcardGenerationError) as exc_info:
            gen.generate(unique_pseudo, "maths", str(doc_id), n=3)
        assert exc_info.value.kind == "no_chunks"


# ---------------------------------------------------------------------------
# AC4 — back is concise (200 chars) and self-contained
# ---------------------------------------------------------------------------


class TestBackConciseAndSelfContained:
    def test_flashcards_back_must_not_exceed_200_chars(
        self,
        retriever: Retriever,
        seeded_chroma: tuple[ChromaStore, str, uuid.UUID],
        tracking_session: _SessionFactory,
    ) -> None:
        """Piège 4 — the LLM producing a 250-char back triggers a Pydantic
        rejection; the generator retries; if the retry is still > 200 chars,
        it raises ``malformed_output``.
        """
        from app.services.exercises.flashcard_generator import (
            FlashcardGenerationError,
            FlashcardGenerator,
        )

        _chroma, pseudo, doc_id = seeded_chroma
        _seed_document(tracking_session, pseudo, doc_id)
        long_back = "x" * 250
        too_long_payload = json.dumps(
            {
                "cards": [
                    {"front": "Q1 ?", "back": long_back, "topic": None},
                ]
            }
        )
        llm = _ScriptedLlm([too_long_payload, too_long_payload])
        gen = FlashcardGenerator(
            llm=llm,  # type: ignore[arg-type]
            retriever=retriever,
            session_factory=tracking_session,
            max_retries=1,
        )
        with pytest.raises(FlashcardGenerationError) as exc_info:
            gen.generate(pseudo, "maths", str(doc_id), n=1)
        assert exc_info.value.kind == "malformed_output"
        # LLM was called 1 + 1 retry = 2 times.
        assert len(llm.calls) == 2

    def test_flashcards_back_must_not_reference_external_section(
        self,
        retriever: Retriever,
        seeded_chroma: tuple[ChromaStore, str, uuid.UUID],
        tracking_session: _SessionFactory,
    ) -> None:
        """Piège 9 — the post-Pydantic check rejects backs that contain
        "voir", "page", "section", or "chapitre" (case-insensitive).
        """
        from app.services.exercises.flashcard_generator import (
            FlashcardGenerator,
        )

        _chroma, pseudo, doc_id = seeded_chroma
        _seed_document(tracking_session, pseudo, doc_id)
        bad_back_payload = json.dumps(
            {
                "cards": [
                    {"front": "Q1 ?", "back": "Voir section 2.1", "topic": None},
                ]
            }
        )
        good_payload = _good_flashcards_json(1)
        llm = _ScriptedLlm([bad_back_payload, good_payload])
        gen = FlashcardGenerator(
            llm=llm,  # type: ignore[arg-type]
            retriever=retriever,
            session_factory=tracking_session,
            max_retries=1,
        )
        result = gen.generate(pseudo, "maths", str(doc_id), n=1)
        # Retry succeeded with a clean deck.
        assert len(result.deck.cards) == 1
        # LLM was called twice (bad then good).
        assert len(llm.calls) == 2

    def test_flashcards_external_reference_after_retry_yields_malformed_output(
        self,
        retriever: Retriever,
        seeded_chroma: tuple[ChromaStore, str, uuid.UUID],
        tracking_session: _SessionFactory,
    ) -> None:
        """If BOTH attempts contain an external reference, the final error
        is ``malformed_output``."""
        from app.services.exercises.flashcard_generator import (
            FlashcardGenerationError,
            FlashcardGenerator,
        )

        _chroma, pseudo, doc_id = seeded_chroma
        _seed_document(tracking_session, pseudo, doc_id)
        bad_payload = json.dumps(
            {
                "cards": [
                    {"front": "Q1 ?", "back": "voir page 12", "topic": None},
                ]
            }
        )
        llm = _ScriptedLlm([bad_payload, bad_payload])
        gen = FlashcardGenerator(
            llm=llm,  # type: ignore[arg-type]
            retriever=retriever,
            session_factory=tracking_session,
            max_retries=1,
        )
        with pytest.raises(FlashcardGenerationError) as exc_info:
            gen.generate(pseudo, "maths", str(doc_id), n=1)
        assert exc_info.value.kind == "malformed_output"
        assert len(llm.calls) == 2


# ---------------------------------------------------------------------------
# Piège 5 — duplicate fronts
# ---------------------------------------------------------------------------


class TestDuplicateFronts:
    def test_flashcards_reject_duplicate_fronts(
        self,
        retriever: Retriever,
        seeded_chroma: tuple[ChromaStore, str, uuid.UUID],
        tracking_session: _SessionFactory,
    ) -> None:
        """The post-Pydantic check rejects decks with duplicate fronts
        (lower-cased and stripped)."""
        from app.services.exercises.flashcard_generator import (
            FlashcardGenerator,
        )

        _chroma, pseudo, doc_id = seeded_chroma
        _seed_document(tracking_session, pseudo, doc_id)
        duplicates_payload = json.dumps(
            {
                "cards": [
                    {"front": "Quelle est la derivee ?", "back": "2x", "topic": None},
                    {"front": "  QUELLE EST LA DERIVEE ?  ", "back": "different", "topic": None},
                ]
            }
        )
        good_payload = _good_flashcards_json(2)
        llm = _ScriptedLlm([duplicates_payload, good_payload])
        gen = FlashcardGenerator(
            llm=llm,  # type: ignore[arg-type]
            retriever=retriever,
            session_factory=tracking_session,
            max_retries=1,
        )
        result = gen.generate(pseudo, "maths", str(doc_id), n=2)
        # Retry succeeded with a clean deck.
        assert len(result.deck.cards) == 2
        assert len(llm.calls) == 2

    def test_flashcards_duplicate_fronts_after_retry_yields_malformed_output(
        self,
        retriever: Retriever,
        seeded_chroma: tuple[ChromaStore, str, uuid.UUID],
        tracking_session: _SessionFactory,
    ) -> None:
        """If BOTH attempts contain duplicate fronts, the final error is
        ``malformed_output``."""
        from app.services.exercises.flashcard_generator import (
            FlashcardGenerationError,
            FlashcardGenerator,
        )

        _chroma, pseudo, doc_id = seeded_chroma
        _seed_document(tracking_session, pseudo, doc_id)
        dup_payload = json.dumps(
            {
                "cards": [
                    {"front": "Identique ?", "back": "A", "topic": None},
                    {"front": "identique ?", "back": "B", "topic": None},
                ]
            }
        )
        llm = _ScriptedLlm([dup_payload, dup_payload])
        gen = FlashcardGenerator(
            llm=llm,  # type: ignore[arg-type]
            retriever=retriever,
            session_factory=tracking_session,
            max_retries=1,
        )
        with pytest.raises(FlashcardGenerationError) as exc_info:
            gen.generate(pseudo, "maths", str(doc_id), n=2)
        assert exc_info.value.kind == "malformed_output"
        assert len(llm.calls) == 2


# ---------------------------------------------------------------------------
# AC5 + AC7 — persistence and multi-tenant
# ---------------------------------------------------------------------------


class TestPersistenceAndMultiTenant:
    def test_flashcards_persists_with_flashcards_type_and_cards_json(
        self,
        retriever: Retriever,
        seeded_chroma: tuple[ChromaStore, str, uuid.UUID],
        tracking_session: _SessionFactory,
    ) -> None:
        from app.services.exercises.flashcard_generator import FlashcardGenerator

        _chroma, pseudo, doc_id = seeded_chroma
        _seed_document(tracking_session, pseudo, doc_id)
        llm = _ScriptedLlm([_good_flashcards_json(3)])
        gen = FlashcardGenerator(
            llm=llm,  # type: ignore[arg-type]
            retriever=retriever,
            session_factory=tracking_session,
        )
        gen.generate(pseudo, "maths", str(doc_id), n=3)

        exercises = [obj for obj in tracking_session.wrapper.added if isinstance(obj, Exercise)]
        assert len(exercises) == 1
        ex = exercises[0]
        assert ex.type is ExerciseType.FLASHCARDS
        assert ex.student_pseudo == pseudo
        assert ex.document_id == doc_id
        assert ex.cards is not None
        assert len(ex.cards) == 3
        # All other polymorphic columns stay None.
        assert ex.questions is None
        assert ex.statement is None
        assert ex.expected_answer is None
        assert ex.grading_criteria is None

    def test_flashcards_topic_optional_but_non_empty_when_present(
        self,
        retriever: Retriever,
        seeded_chroma: tuple[ChromaStore, str, uuid.UUID],
        tracking_session: _SessionFactory,
    ) -> None:
        """AC6 + D6 — ``topic=None`` is accepted and ``topic="algebre"`` is
        accepted. ``topic=""`` is coerced to None.
        """
        from app.services.exercises.flashcard_generator import FlashcardGenerator

        _chroma, pseudo, doc_id = seeded_chroma
        _seed_document(tracking_session, pseudo, doc_id)
        payload = json.dumps(
            {
                "cards": [
                    {"front": "Q1 ?", "back": "A1.", "topic": None},
                    {"front": "Q2 ?", "back": "A2.", "topic": "algebre"},
                    {"front": "Q3 ?", "back": "A3.", "topic": ""},
                ]
            }
        )
        llm = _ScriptedLlm([payload])
        gen = FlashcardGenerator(
            llm=llm,  # type: ignore[arg-type]
            retriever=retriever,
            session_factory=tracking_session,
        )
        result = gen.generate(pseudo, "maths", str(doc_id), n=3)
        assert result.deck.cards[0].topic is None
        assert result.deck.cards[1].topic == "algebre"
        assert result.deck.cards[2].topic is None

    def test_flashcards_cross_tenant_raises_document_not_found(
        self,
        retriever: Retriever,
        tracking_session: _SessionFactory,
    ) -> None:
        """AC7 — the multi-tenant invariant bite.

        Alice's document exists in the DB but Bob asks for a deck on it.
        The generator must refuse with ``document_not_found`` (no leak:
        same message whether the doc is absent or belongs to someone else)
        and the LLM MUST NEVER have been called.
        """
        from app.services.exercises.flashcard_generator import (
            FlashcardGenerationError,
            FlashcardGenerator,
        )

        session = tracking_session()
        alice_doc = uuid.uuid4()
        session.add(
            Document(
                id=alice_doc,
                student_pseudo="alice",
                subject=Subject.MATHS,
                filename="alice.pdf",
                s3_key="students/alice/x.pdf",
                chunks_count=2,
                status=DocumentStatus.INDEXED,
            )
        )
        session.commit()

        llm = _ScriptedLlm([])
        gen = FlashcardGenerator(
            llm=llm,  # type: ignore[arg-type]
            retriever=retriever,
            session_factory=tracking_session,
        )
        with pytest.raises(FlashcardGenerationError) as exc_info:
            gen.generate("bob", "maths", str(alice_doc), n=3)
        assert exc_info.value.kind == "document_not_found"
        # LLM must NEVER have been called on a cross-tenant request.
        assert llm.calls == []

    def test_flashcards_document_not_found(
        self,
        retriever: Retriever,
        tracking_session: _SessionFactory,
    ) -> None:
        from app.services.exercises.flashcard_generator import (
            FlashcardGenerationError,
            FlashcardGenerator,
        )

        llm = _ScriptedLlm([])
        gen = FlashcardGenerator(
            llm=llm,  # type: ignore[arg-type]
            retriever=retriever,
            session_factory=tracking_session,
        )
        with pytest.raises(FlashcardGenerationError) as exc_info:
            gen.generate("alice", "maths", str(uuid.uuid4()), n=3)
        assert exc_info.value.kind == "document_not_found"

    def test_flashcards_invalid_uuid_raises_document_not_found(
        self,
        retriever: Retriever,
        tracking_session: _SessionFactory,
    ) -> None:
        from app.services.exercises.flashcard_generator import (
            FlashcardGenerationError,
            FlashcardGenerator,
        )

        gen = FlashcardGenerator(
            llm=_ScriptedLlm([]),  # type: ignore[arg-type]
            retriever=retriever,
            session_factory=tracking_session,
        )
        with pytest.raises(FlashcardGenerationError) as exc_info:
            gen.generate("alice", "maths", "not-a-uuid", n=3)
        assert exc_info.value.kind == "document_not_found"


# ---------------------------------------------------------------------------
# Argument validation
# ---------------------------------------------------------------------------


class TestArgumentValidation:
    def test_flashcards_invalid_n_too_large(
        self,
        retriever: Retriever,
        tracking_session: _SessionFactory,
    ) -> None:
        """D5 — n=50 is rejected when max_n=30."""
        from app.services.exercises.flashcard_generator import (
            FlashcardGenerationError,
            FlashcardGenerator,
        )

        gen = FlashcardGenerator(
            llm=_ScriptedLlm([]),  # type: ignore[arg-type]
            retriever=retriever,
            session_factory=tracking_session,
            max_n=30,
        )
        with pytest.raises(FlashcardGenerationError) as exc_info:
            gen.generate("alice", "maths", str(uuid.uuid4()), n=50)
        assert exc_info.value.kind == "invalid_input"

    def test_flashcards_invalid_n_zero(
        self,
        retriever: Retriever,
        tracking_session: _SessionFactory,
    ) -> None:
        from app.services.exercises.flashcard_generator import (
            FlashcardGenerationError,
            FlashcardGenerator,
        )

        gen = FlashcardGenerator(
            llm=_ScriptedLlm([]),  # type: ignore[arg-type]
            retriever=retriever,
            session_factory=tracking_session,
        )
        with pytest.raises(FlashcardGenerationError) as exc_info:
            gen.generate("alice", "maths", str(uuid.uuid4()), n=0)
        assert exc_info.value.kind == "invalid_input"


# ---------------------------------------------------------------------------
# AC4 — retry / malformed output
# ---------------------------------------------------------------------------


class TestRetry:
    def test_flashcards_retries_once_on_malformed_output(
        self,
        retriever: Retriever,
        seeded_chroma: tuple[ChromaStore, str, uuid.UUID],
        tracking_session: _SessionFactory,
    ) -> None:
        from app.services.exercises.flashcard_generator import FlashcardGenerator

        _chroma, pseudo, doc_id = seeded_chroma
        _seed_document(tracking_session, pseudo, doc_id)
        llm = _ScriptedLlm(
            [
                "not valid json at all",
                _good_flashcards_json(4),
            ]
        )
        gen = FlashcardGenerator(
            llm=llm,  # type: ignore[arg-type]
            retriever=retriever,
            session_factory=tracking_session,
            max_retries=1,
        )
        result = gen.generate(pseudo, "maths", str(doc_id), n=4)
        assert len(result.deck.cards) == 4
        # LLM was called twice: first attempt + 1 retry.
        assert len(llm.calls) == 2

    def test_flashcards_fails_after_max_retries(
        self,
        retriever: Retriever,
        seeded_chroma: tuple[ChromaStore, str, uuid.UUID],
        tracking_session: _SessionFactory,
    ) -> None:
        from app.services.exercises.flashcard_generator import (
            FlashcardGenerationError,
            FlashcardGenerator,
        )

        _chroma, pseudo, doc_id = seeded_chroma
        _seed_document(tracking_session, pseudo, doc_id)
        llm = _ScriptedLlm(["not json", "still not json"])
        gen = FlashcardGenerator(
            llm=llm,  # type: ignore[arg-type]
            retriever=retriever,
            session_factory=tracking_session,
            max_retries=1,
        )
        with pytest.raises(FlashcardGenerationError) as exc_info:
            gen.generate(pseudo, "maths", str(doc_id), n=3)
        assert exc_info.value.kind == "malformed_output"
        # 1 first attempt + 1 retry = 2 total calls.
        assert len(llm.calls) == 2


# ---------------------------------------------------------------------------
# No-session mode
# ---------------------------------------------------------------------------


class TestNoSessionMode:
    def test_flashcards_without_session_factory_skips_persistence(
        self,
        retriever: Retriever,
        seeded_chroma: tuple[ChromaStore, str, uuid.UUID],
    ) -> None:
        from app.services.exercises.flashcard_generator import FlashcardGenerator

        _chroma, pseudo, doc_id = seeded_chroma
        llm = _ScriptedLlm([_good_flashcards_json(2)])
        gen = FlashcardGenerator(
            llm=llm,  # type: ignore[arg-type]
            retriever=retriever,
            session_factory=None,
        )
        result = gen.generate(pseudo, "maths", str(doc_id), n=2)
        assert len(result.deck.cards) == 2
