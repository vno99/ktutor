"""Tests for the ``QcmGenerator`` service (s03).

The generator is the place where the multi-tenant invariant lives: a
``pseudo`` must only be able to generate a QCM from a ``document_id`` that
belongs to them. The cross-tenant bite (test_generate_raises_document_not_found_for_cross_tenant)
is the load-bearing assertion: removing the ``document.student_pseudo ==
pseudo`` check must turn it red.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from typing import Any

import chromadb
import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database.models import (
    Base,
    Document,
    DocumentStatus,
    Exercise,
    Subject,
)
from app.services.rag.chroma_store import ChromaStore
from app.services.rag.embeddings import EmbeddingProvider
from app.services.rag.retriever import Retriever

# ---------------------------------------------------------------------------
# Test doubles
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
    """Wraps a real SQLAlchemy session, recording every ``add`` call.

    Used to assert that the generator *did* call ``session.add(Exercise(...))``
    before committing. After a commit, ``session.new`` is empty on a real
    session, so the wrapper is the only way to assert the addition happened
    at all.
    """

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


def _good_qcm_json(n: int = 3) -> str:
    """Return a well-formed QCM JSON payload with ``n`` questions."""
    return json.dumps(
        {
            "questions": [
                {
                    "question": f"Q{i + 1} ?",
                    "options": ["a", "b", "c", "d"],
                    "correct_index": i % 4,
                }
                for i in range(n)
            ]
        }
    )


def _seed_document_for_pseudo(
    chroma: ChromaStore, pseudo: str, subject: str, document_id: uuid.UUID
) -> None:
    coll = chroma.get_collection(subject, pseudo)
    chunks = [
        {
            "id": f"{pseudo}-{document_id}-0",
            "content": "La dérivée de x^2 est 2x.",
            "metadata": {
                "chunk_index": 0,
                "filename": "cours.pdf",
                "document_id": str(document_id),
            },
        },
        {
            "id": f"{pseudo}-{document_id}-1",
            "content": "La dérivée de sin(x) est cos(x).",
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
    has the ``Base`` metadata applied. Used to seed a ``Document`` row and
    read back persisted ``Exercise`` rows."""

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


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


class TestSchema:
    def test_qcm_question_schema_validates_4_options_and_correct_index_range(self) -> None:
        from app.services.exercises.qcm_generator import QcmQuestion

        q = QcmQuestion(question="Q?", options=["a", "b", "c", "d"], correct_index=0)
        assert q.correct_index == 0
        assert len(q.options) == 4

    def test_qcm_question_rejects_wrong_options_count(self) -> None:
        from app.services.exercises.qcm_generator import QcmQuestion

        with pytest.raises(ValidationError):
            QcmQuestion(question="Q?", options=["a", "b", "c"], correct_index=0)

    def test_qcm_question_rejects_out_of_range_correct_index(self) -> None:
        from app.services.exercises.qcm_generator import QcmQuestion

        with pytest.raises(ValidationError):
            QcmQuestion(question="Q?", options=["a", "b", "c", "d"], correct_index=4)


# ---------------------------------------------------------------------------
# Happy path / AC1 + AC2
# ---------------------------------------------------------------------------


class TestGenerateHappyPath:
    def test_generate_returns_n_questions(
        self,
        retriever: Retriever,
        seeded_chroma: tuple[ChromaStore, str, uuid.UUID],
        tracking_session: _SessionFactory,
    ) -> None:
        from app.services.exercises.qcm_generator import QcmGenerator

        _chroma, pseudo, doc_id = seeded_chroma
        # Pre-seed a Document via the tracking session so the generator
        # passes its document ownership check on the same wrapper.
        session = tracking_session()
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

        llm = _ScriptedLlm([_good_qcm_json(5)])
        gen = QcmGenerator(
            llm=llm,  # type: ignore[arg-type]
            retriever=retriever,
            session_factory=tracking_session,
        )
        result = gen.generate(pseudo, "maths", str(doc_id), n=5)
        assert len(result.questions) == 5
        for q in result.questions:
            assert len(q.options) == 4
            assert 0 <= q.correct_index <= 3

    def test_generate_returns_valid_json(
        self,
        retriever: Retriever,
        seeded_chroma: tuple[ChromaStore, str, uuid.UUID],
        tracking_session: _SessionFactory,
    ) -> None:
        """AC2 — the LLM output round-trips through ``json.loads``."""
        from app.services.exercises.qcm_generator import QcmGenerator

        _chroma, pseudo, doc_id = seeded_chroma
        session = tracking_session()
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
        llm = _ScriptedLlm([_good_qcm_json(3)])
        gen = QcmGenerator(
            llm=llm,  # type: ignore[arg-type]
            retriever=retriever,
            session_factory=tracking_session,
        )
        result = gen.generate(pseudo, "maths", str(doc_id), n=3)
        parsed = json.loads(result.raw)
        assert "questions" in parsed
        assert len(parsed["questions"]) == 3


# ---------------------------------------------------------------------------
# AC3 — chunk filter by document_id
# ---------------------------------------------------------------------------


class TestDocumentFilter:
    def test_generate_filters_chunks_by_document_id(
        self,
        chroma_store: ChromaStore,
        retriever: Retriever,
        unique_pseudo: str,
        tracking_session: _SessionFactory,
    ) -> None:
        """AC3 — only chunks belonging to the requested document reach the LLM.

        We seed two documents for the same pseudo. The scripted LLM would
        notice if the wrong chunks were sent (it receives them in the user
        prompt). We assert that the prompt references the target document's
        content and not the other document's.
        """
        from app.services.exercises.qcm_generator import QcmGenerator

        target_id = uuid.uuid4()
        other_id = uuid.uuid4()
        # Seed target with distinctive content.
        coll = chroma_store.get_collection("maths", unique_pseudo)
        chroma_store.add_chunks(
            coll,
            [
                {
                    "id": "target-0",
                    "content": "TARGET_CONTENT: dérivées de polynômes",
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
                    "content": "OTHER_CONTENT: trigonométrie avancée",
                    "metadata": {
                        "chunk_index": 0,
                        "filename": "other.pdf",
                        "document_id": str(other_id),
                    },
                }
            ],
            [[0.1, 0.2, 0.3]],
        )

        session = tracking_session()
        session.add(
            Document(
                id=target_id,
                student_pseudo=unique_pseudo,
                subject=Subject.MATHS,
                filename="target.pdf",
                s3_key=f"students/{unique_pseudo}/{target_id}.pdf",
                chunks_count=1,
                status=DocumentStatus.INDEXED,
            )
        )
        session.commit()

        llm = _ScriptedLlm([_good_qcm_json(2)])
        gen = QcmGenerator(
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

    def test_generate_raises_no_chunks_when_document_empty(
        self,
        retriever: Retriever,
        chroma_store: ChromaStore,
        unique_pseudo: str,
        tracking_session: _SessionFactory,
    ) -> None:
        from app.services.exercises.qcm_generator import (
            QcmGenerationError,
            QcmGenerator,
        )

        doc_id = uuid.uuid4()
        session = tracking_session()
        session.add(
            Document(
                id=doc_id,
                student_pseudo=unique_pseudo,
                subject=Subject.MATHS,
                filename="empty.pdf",
                s3_key=f"students/{unique_pseudo}/{doc_id}.pdf",
                chunks_count=0,
                status=DocumentStatus.INDEXED,
            )
        )
        session.commit()

        llm = _ScriptedLlm([])
        gen = QcmGenerator(
            llm=llm,  # type: ignore[arg-type]
            retriever=retriever,
            session_factory=tracking_session,
        )
        with pytest.raises(QcmGenerationError) as exc_info:
            gen.generate(unique_pseudo, "maths", str(doc_id), n=3)
        assert exc_info.value.kind == "no_chunks"


# ---------------------------------------------------------------------------
# AC4 — retry on malformed output
# ---------------------------------------------------------------------------


class TestRetry:
    def test_generate_retries_once_on_malformed_output(
        self,
        retriever: Retriever,
        seeded_chroma: tuple[ChromaStore, str, uuid.UUID],
        tracking_session: _SessionFactory,
    ) -> None:
        from app.services.exercises.qcm_generator import QcmGenerator

        _chroma, pseudo, doc_id = seeded_chroma
        session = tracking_session()
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

        llm = _ScriptedLlm(
            [
                "not valid json at all",
                _good_qcm_json(4),
            ]
        )
        gen = QcmGenerator(
            llm=llm,  # type: ignore[arg-type]
            retriever=retriever,
            session_factory=tracking_session,
            max_retries=1,
        )
        result = gen.generate(pseudo, "maths", str(doc_id), n=4)
        assert len(result.questions) == 4
        # LLM was called twice: first attempt + 1 retry.
        assert len(llm.calls) == 2

    def test_generate_fails_after_max_retries(
        self,
        retriever: Retriever,
        seeded_chroma: tuple[ChromaStore, str, uuid.UUID],
        tracking_session: _SessionFactory,
    ) -> None:
        from app.services.exercises.qcm_generator import (
            QcmGenerationError,
            QcmGenerator,
        )

        _chroma, pseudo, doc_id = seeded_chroma
        session = tracking_session()
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

        llm = _ScriptedLlm(["not json", "still not json"])
        gen = QcmGenerator(
            llm=llm,  # type: ignore[arg-type]
            retriever=retriever,
            session_factory=tracking_session,
            max_retries=1,
        )
        with pytest.raises(QcmGenerationError) as exc_info:
            gen.generate(pseudo, "maths", str(doc_id), n=3)
        assert exc_info.value.kind == "malformed_output"
        # 1 first attempt + 1 retry = 2 total calls.
        assert len(llm.calls) == 2


# ---------------------------------------------------------------------------
# AC5 — persistence + multi-tenant
# ---------------------------------------------------------------------------


class TestPersistence:
    def test_generate_persists_exercise_in_session(
        self,
        retriever: Retriever,
        seeded_chroma: tuple[ChromaStore, str, uuid.UUID],
        tracking_session: _SessionFactory,
    ) -> None:
        from app.services.exercises.qcm_generator import QcmGenerator

        _chroma, pseudo, doc_id = seeded_chroma
        session = tracking_session()
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

        llm = _ScriptedLlm([_good_qcm_json(3)])
        gen = QcmGenerator(
            llm=llm,  # type: ignore[arg-type]
            retriever=retriever,
            session_factory=tracking_session,
        )
        gen.generate(pseudo, "maths", str(doc_id), n=3)

        # The tracking wrapper recorded every ``add`` call — including the
        # ``Exercise`` that was committed. After commit, ``session.new`` is
        # empty on the real session, so the wrapper is the only way to
        # assert the addition happened.
        exercises = [obj for obj in tracking_session.wrapper.added if isinstance(obj, Exercise)]
        assert len(exercises) == 1
        ex = exercises[0]
        assert ex.student_pseudo == pseudo
        assert ex.document_id == doc_id
        assert ex.questions is not None
        assert len(ex.questions) == 3

    def test_generate_raises_document_not_found_for_unknown_uuid(
        self,
        retriever: Retriever,
        tracking_session: _SessionFactory,
    ) -> None:
        from app.services.exercises.qcm_generator import (
            QcmGenerationError,
            QcmGenerator,
        )

        llm = _ScriptedLlm([])
        gen = QcmGenerator(
            llm=llm,  # type: ignore[arg-type]
            retriever=retriever,
            session_factory=tracking_session,
        )
        with pytest.raises(QcmGenerationError) as exc_info:
            gen.generate("alice", "maths", str(uuid.uuid4()), n=3)
        assert exc_info.value.kind == "document_not_found"

    def test_generate_raises_document_not_found_for_cross_tenant(
        self,
        retriever: Retriever,
        tracking_session: _SessionFactory,
    ) -> None:
        """The multi-tenant invariant bite — owner check MUST be enforced.

        Alice's document exists in the DB but Bob asks for a QCM on it.
        The generator must refuse with ``document_not_found`` (no leak:
        same message whether the doc is absent or belongs to someone else).
        """
        from app.services.exercises.qcm_generator import (
            QcmGenerationError,
            QcmGenerator,
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
        gen = QcmGenerator(
            llm=llm,  # type: ignore[arg-type]
            retriever=retriever,
            session_factory=tracking_session,
        )
        with pytest.raises(QcmGenerationError) as exc_info:
            gen.generate("bob", "maths", str(alice_doc), n=3)
        assert exc_info.value.kind == "document_not_found"
        # LLM must NEVER have been called on a cross-tenant request.
        assert llm.calls == []


# ---------------------------------------------------------------------------
# Argument validation
# ---------------------------------------------------------------------------


class TestArgumentValidation:
    def test_generate_rejects_invalid_uuid(
        self,
        retriever: Retriever,
        tracking_session: _SessionFactory,
    ) -> None:
        from app.services.exercises.qcm_generator import (
            QcmGenerationError,
            QcmGenerator,
        )

        gen = QcmGenerator(
            llm=_ScriptedLlm([]),  # type: ignore[arg-type]
            retriever=retriever,
            session_factory=tracking_session,
        )
        with pytest.raises(QcmGenerationError) as exc_info:
            gen.generate("alice", "maths", "not-a-uuid", n=3)
        assert exc_info.value.kind == "document_not_found"

    def test_generate_rejects_n_above_cap(
        self,
        retriever: Retriever,
        tracking_session: _SessionFactory,
    ) -> None:
        from app.services.exercises.qcm_generator import (
            QcmGenerationError,
            QcmGenerator,
        )

        gen = QcmGenerator(
            llm=_ScriptedLlm([]),  # type: ignore[arg-type]
            retriever=retriever,
            session_factory=tracking_session,
            max_questions=5,
        )
        with pytest.raises(QcmGenerationError) as exc_info:
            gen.generate("alice", "maths", str(uuid.uuid4()), n=20)
        assert exc_info.value.kind == "invalid_input"

    def test_generate_rejects_n_zero(
        self,
        retriever: Retriever,
        tracking_session: _SessionFactory,
    ) -> None:
        from app.services.exercises.qcm_generator import (
            QcmGenerationError,
            QcmGenerator,
        )

        gen = QcmGenerator(
            llm=_ScriptedLlm([]),  # type: ignore[arg-type]
            retriever=retriever,
            session_factory=tracking_session,
        )
        with pytest.raises(QcmGenerationError) as exc_info:
            gen.generate("alice", "maths", str(uuid.uuid4()), n=0)
        assert exc_info.value.kind == "invalid_input"


# ---------------------------------------------------------------------------
# No-session mode (CLI / scripting without DB)
# ---------------------------------------------------------------------------


class TestNoSessionMode:
    def test_generate_without_session_factory_skips_persistence(
        self,
        retriever: Retriever,
        seeded_chroma: tuple[ChromaStore, str, uuid.UUID],
    ) -> None:
        from app.services.exercises.qcm_generator import QcmGenerator

        _chroma, pseudo, doc_id = seeded_chroma
        llm = _ScriptedLlm([_good_qcm_json(2)])
        gen = QcmGenerator(
            llm=llm,  # type: ignore[arg-type]
            retriever=retriever,
            session_factory=None,
        )
        result = gen.generate(pseudo, "maths", str(doc_id), n=2)
        assert len(result.questions) == 2
