"""Tests for :class:`EvaluationExtractor` and :class:`EvaluationService`.

The extractor is the unit under test for the **regex + LLM dual-source
extraction contract** (plan T2): a ``<n>/<m>`` pattern in the OCR
transcript wins over the structured JSON returned by the vision LLM,
but the LLM is the fallback when the regex misses. The service
wraps the extractor with the S3 push + DB row + rollback
contract (T3).

Both layers are exercised with cheap in-memory doubles — the real
OCR transport, S3 backend, and PostgreSQL engine are never touched.
The tests assert on the **observable contract** (returned objects,
S3 calls, DB rows), not on which internal method got invoked.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.core.database.models import (
    Base,
    Evaluation,
    EvaluationStatus,
    Subject,
    User,
)
from app.core.auth.passwords import hash_password
from app.services.ocr.evaluation_extractor import (
    EvaluationError,
    EvaluationErrorKind,
    EvaluationExtractionError,
    EvaluationExtractor,
    EvaluationService,
)
from app.services.rag.ocr import OcrError, OcrResult
from app.services.storage.minio_client import MinioClient
from tests.services.storage.test_s3_client import FakeS3


# ---------------------------------------------------------------------------
# OCR transport double — replaces the real DeepSeek-OCR-2 service.
# ---------------------------------------------------------------------------


class _OcrStub:
    """In-memory double for :class:`MultimodalOcr`.

    The stub captures every call so the test can assert on the prompt
    the extractor sent. ``result_factory`` produces the
    :class:`OcrResult` the stub will return for each call.
    """

    def __init__(self, result_factory: Any) -> None:
        self._result_factory = result_factory
        self.calls: list[tuple[str, str | None]] = []

    def transcribe_image(self, image_path: str, prompt: str | None = None) -> OcrResult:
        self.calls.append((image_path, prompt))
        return self._result_factory(prompt or "")


# ---------------------------------------------------------------------------
# Service-level doubles
# ---------------------------------------------------------------------------


class _FakeSession:
    """Session double that records ``add``/``commit``/``rollback`` calls."""

    def __init__(self) -> None:
        self.added: list[Any] = []
        self.committed = False
        self.rolled_back = False
        self.commit_should_raise: bool | None = None

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    def commit(self) -> None:
        if self.commit_should_raise is not None:
            raise self.commit_should_raise
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True


def _make_s3_with_fake() -> tuple[MinioClient, FakeS3]:
    fake = FakeS3()
    s3 = MinioClient(
        endpoint="localhost:8333", access_key="k", secret_key="s", bucket="bkt"
    )
    s3._client = fake  # type: ignore[attr-defined]
    return s3, fake


def _settings(max_size_mb: int = 20) -> Settings:
    return Settings(max_upload_size_mb=max_size_mb)


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def fake_image(tmp_path: Path) -> Path:
    """A 1x1 PNG — the extractor never inspects the bytes."""
    from PIL import Image

    p = tmp_path / "copie.png"
    Image.new("RGB", (1, 1), color="white").save(p)
    return p


@pytest.fixture()
def session_factory():
    """In-memory SQLite session factory, with all tables created."""
    engine = create_engine("sqlite://", future=True)
    Base.metadata.create_all(engine)
    sf = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with sf() as s:
        s.add(
            User(pseudo="alice", password_hash=hash_password("passwordone1"))
        )
        s.commit()
    yield sf
    engine.dispose()


# ---------------------------------------------------------------------------
# Task 2 — EvaluationExtractor unit tests
# ---------------------------------------------------------------------------


class TestRegexFastPath:
    def test_regex_picks_explicit_12_over_20(self) -> None:
        """AC6: a clear ``<n>/<m>`` in the OCR transcript is captured
        by the regex (source=``regex``). The regex anchors on ``/``
        so a stray ``12`` in the text would not be picked up — this
        test exercises the canonical pattern ``Note finale : 12/20``."""

        def _factory(prompt: str) -> OcrResult:
            return OcrResult(
                ok=True,
                transcription="Note finale : 12/20. Très bien !",
                confidence=0.9,
            )

        extractor = EvaluationExtractor(ocr=_OcrStub(_factory), settings=_settings())
        result = extractor.extract("ignored.png")

        assert result.source == "regex"
        assert result.score == 12.0
        assert result.max_score == 20.0
        assert result.ocr_text == "Note finale : 12/20. Très bien !"
        assert result.ocr_confidence == 0.9
        assert result.annotations == []
        assert result.teacher_comments is None

    def test_regex_picks_first_match_when_multiple(self) -> None:
        """When two ``<n>/<m>`` patterns coexist (e.g. ``exercice
        noté 12/15`` and ``Note finale : 8/20``), the regex picks the
        first one — the agentic note flagged this as a potential
        false-positive trap. The LLM JSON is the safety net (s18b)."""

        def _factory(prompt: str) -> OcrResult:
            return OcrResult(
                ok=True,
                transcription="exercice noté 12/15. Note finale : 8/20.",
                confidence=0.9,
            )

        extractor = EvaluationExtractor(ocr=_OcrStub(_factory), settings=_settings())
        result = extractor.extract("ignored.png")

        assert result.source == "regex"
        # The first match wins — ``12/15`` here.
        assert result.score == 12.0
        assert result.max_score == 15.0


class TestLlmFallback:
    def test_llm_fallback_when_regex_misses(self) -> None:
        """AC7: when the OCR text carries no ``<n>/<m>`` pattern, the
        extractor falls back to the LLM JSON payload returned alongside
        the transcription (source=``llm``). The LLM's structured
        fields are exposed via :attr:`OcrResult.raw`."""

        def _factory(prompt: str) -> OcrResult:
            return OcrResult(
                ok=True,
                transcription="très bien",
                confidence=0.85,
                raw={
                    "score": 8,
                    "max_score": 20,
                    "annotations": ["exercice 1 correct"],
                    "teacher_comments": "Bon travail",
                    "ocr_text": "très bien",
                    "ocr_confidence": 0.85,
                },
            )

        extractor = EvaluationExtractor(ocr=_OcrStub(_factory), settings=_settings())
        result = extractor.extract("ignored.png")

        assert result.source == "llm"
        assert result.score == 8.0
        assert result.max_score == 20.0
        assert result.annotations == ["exercice 1 correct"]
        assert result.teacher_comments == "Bon travail"


class TestNoScoreFound:
    def test_manual_review_when_neither_finds_score(self) -> None:
        """AC4: when neither the regex nor the LLM JSON carry a score,
        the extractor returns ``source='none'`` — the caller maps this
        to :class:`EvaluationStatus.MANUAL_REVIEW_NEEDED`."""

        def _factory(prompt: str) -> OcrResult:
            return OcrResult(
                ok=True,
                transcription="copie illisible",
                confidence=0.8,
                raw={
                    "score": None,
                    "max_score": None,
                    "annotations": [],
                    "teacher_comments": None,
                    "ocr_text": "copie illisible",
                    "ocr_confidence": 0.8,
                },
            )

        extractor = EvaluationExtractor(ocr=_OcrStub(_factory), settings=_settings())
        result = extractor.extract("ignored.png")

        assert result.source == "none"
        assert result.score is None
        assert result.max_score is None

    def test_ocr_low_confidence_short_circuits_to_none(self) -> None:
        """Piège 5: a low-confidence OCR result is rejected BEFORE the
        regex is attempted (no point matching on garbage). A
        regression that still ran the regex would not be a functional
        bug (the result is the same), but the test pins the
        short-circuit contract so a future refactor that re-enables
        the regex on ``ok=False`` would be caught here."""

        stub = _OcrStub(
            lambda p: OcrResult(ok=False, reason="low_confidence", confidence=0.1)
        )
        extractor = EvaluationExtractor(ocr=stub, settings=_settings())
        result = extractor.extract("ignored.png")

        assert result.source == "none"
        assert result.score is None
        assert result.max_score is None


class TestOcrError:
    def test_ocr_error_raises_evaluation_extraction_error(self) -> None:
        """When the OCR transport raises :class:`OcrError`, the
        extractor re-raises as :class:`EvaluationExtractionError` so
        the router can map it to 500."""

        class _RaisingStub:
            def transcribe_image(self, *args, **kwargs) -> OcrResult:
                raise OcrError("service down")

        extractor = EvaluationExtractor(ocr=_RaisingStub(), settings=_settings())
        with pytest.raises(EvaluationExtractionError):
            extractor.extract("ignored.png")


class TestPromptIsCustom:
    """The extractor must pass a custom prompt so the vision LLM
    returns a structured JSON. The default ``MultimodalOcr`` prompt
    is a generic transcription prompt (s10) and would not carry the
    score / max_score fields. A regression that dropped the custom
    prompt would make every evaluation land on ``source='none'`` —
    the manual-review branch would be over-triggered.
    """

    def test_custom_prompt_is_sent(self) -> None:
        captured: list[str] = []

        def _factory(prompt: str) -> OcrResult:
            captured.append(prompt)
            return OcrResult(ok=True, transcription="x", confidence=0.9)

        extractor = EvaluationExtractor(ocr=_OcrStub(_factory), settings=_settings())
        extractor.extract("ignored.png")

        assert len(captured) == 1
        # The prompt must request the JSON fields — a regression
        # to the default prompt would not mention ``score``.
        assert "score" in captured[0]
        assert "max_score" in captured[0]


# ---------------------------------------------------------------------------
# Task 3 — EvaluationService tests
# ---------------------------------------------------------------------------


class TestEvaluationService:
    def test_upload_persists_evaluation_row_with_score(
        self, fake_image: Path, session_factory
    ) -> None:
        """Happy path: the regex finds ``12/20`` and the row is
        persisted with ``status=SCORED`` and the score filled in."""

        def _factory(prompt: str) -> OcrResult:
            return OcrResult(
                ok=True,
                transcription="Note finale : 12/20",
                confidence=0.9,
            )

        s3, fake = _make_s3_with_fake()
        extractor = EvaluationExtractor(ocr=_OcrStub(_factory), settings=_settings())
        service = EvaluationService(
            s3_client=s3,
            extractor=extractor,
            session_factory=session_factory,
            max_image_size_mb=20,
        )

        result = service.upload(file_path=str(fake_image), pseudo="alice", subject="maths")

        assert result.status is EvaluationStatus.SCORED
        assert result.score == 12.0
        assert result.max_score == 20.0
        # The S3 object was pushed.
        assert len(fake.put_calls) == 1
        # The DB row exists.
        with session_factory() as s:
            rows = s.query(Evaluation).all()
            assert len(rows) == 1
            assert rows[0].score == 12.0
            assert rows[0].status is EvaluationStatus.SCORED
            assert rows[0].student_pseudo == "alice"

    def test_upload_persists_manual_review_when_no_score(
        self, fake_image: Path, session_factory
    ) -> None:
        """AC4: when the extractor returns ``source='none'``, the
        service persists a row with ``status=MANUAL_REVIEW_NEEDED``
        and ``score=None``. The HTTP layer maps this to 201 (not an
        error)."""

        def _factory(prompt: str) -> OcrResult:
            return OcrResult(
                ok=True,
                transcription="illisible",
                confidence=0.8,
                raw={
                    "score": None,
                    "max_score": None,
                    "annotations": [],
                    "teacher_comments": None,
                    "ocr_text": "illisible",
                    "ocr_confidence": 0.8,
                },
            )

        extractor = EvaluationExtractor(ocr=_OcrStub(_factory), settings=_settings())
        s3, _ = _make_s3_with_fake()
        service = EvaluationService(
            s3_client=s3,
            extractor=extractor,
            session_factory=session_factory,
            max_image_size_mb=20,
        )

        result = service.upload(
            file_path=str(fake_image),
            pseudo="alice",
            subject="maths",
        )

        assert result.status is EvaluationStatus.MANUAL_REVIEW_NEEDED
        assert result.score is None
        assert result.max_score is None
        with session_factory() as s:
            rows = s.query(Evaluation).all()
            assert len(rows) == 1
            assert rows[0].status is EvaluationStatus.MANUAL_REVIEW_NEEDED
            assert rows[0].score is None

    def test_upload_rolls_back_s3_on_evaluation_persistence_error(
        self, fake_image: Path, session_factory
    ) -> None:
        """AC4 — the service MUST roll back the S3 object if the DB
        insert fails. Otherwise an orphan object lingers in the
        bucket and a re-upload of the same content would produce a
        second S3 key — a multi-tenant leak risk."""

        s3, fake = _make_s3_with_fake()
        extractor = EvaluationExtractor(
            ocr=_OcrStub(
                lambda p: OcrResult(
                    ok=True, transcription="Note : 12/20", confidence=0.9
                )
            ),
            settings=_settings(),
        )

        class _ExplodingFactory:
            def __call__(self) -> _FakeSession:
                fake_session = _FakeSession()
                fake_session.commit_should_raise = RuntimeError("DB down")
                return fake_session

        service = EvaluationService(
            s3_client=s3,
            extractor=extractor,
            session_factory=_ExplodingFactory(),  # type: ignore[arg-type]
            max_image_size_mb=20,
        )

        # The service catches the DB failure and raises
        # ``EvaluationError(STORAGE_FAILURE)`` — the router maps
        # this to 500. The S3 object must have been rolled back.
        with pytest.raises(EvaluationError) as exc_info:
            service.upload(
                file_path=str(fake_image),
                pseudo="alice",
                subject="maths",
            )
        assert exc_info.value.kind is EvaluationErrorKind.STORAGE_FAILURE
        # The S3 object was pushed, then removed.
        assert len(fake.put_calls) == 1
        assert len(fake.remove_calls) == 1

    def test_upload_rejects_pdf_extension(
        self, tmp_path: Path, session_factory
    ) -> None:
        """AC1 — only image extensions are accepted. A ``.pdf`` upload
        is refused with :class:`EvaluationError` and ``kind=
        INVALID_FILE``. The router maps this to 415."""

        s3, _ = _make_s3_with_fake()
        extractor = EvaluationExtractor(
            ocr=_OcrStub(lambda p: OcrResult(ok=True, transcription="x", confidence=0.9)),
            settings=_settings(),
        )
        service = EvaluationService(
            s3_client=s3,
            extractor=extractor,
            session_factory=session_factory,
            max_image_size_mb=20,
        )

        pdf = tmp_path / "doc.pdf"
        pdf.write_bytes(b"%PDF-1.4\n%fake\n")
        with pytest.raises(EvaluationError) as exc_info:
            service.upload(file_path=str(pdf), pseudo="alice", subject="maths")
        assert exc_info.value.kind is EvaluationErrorKind.INVALID_FILE
        # The error message includes the word "extension" so the
        # router can map to 415 (vs "taille" → 413).
        assert "extension" in str(exc_info.value).lower()

    def test_upload_rejects_oversized_image(
        self, tmp_path: Path, session_factory
    ) -> None:
        """The size guard fires before the S3 push — a 5 MB image
        with a 1 MB cap is refused without any S3 call."""

        s3, fake = _make_s3_with_fake()
        extractor = EvaluationExtractor(
            ocr=_OcrStub(lambda p: OcrResult(ok=True, transcription="x", confidence=0.9)),
            settings=_settings(),
        )
        service = EvaluationService(
            s3_client=s3,
            extractor=extractor,
            session_factory=session_factory,
            max_image_size_mb=1,
        )

        big = tmp_path / "big.png"
        big.write_bytes(b"\0" * (2 * 1024 * 1024))  # 2 MB
        with pytest.raises(EvaluationError) as exc_info:
            service.upload(file_path=str(big), pseudo="alice", subject="maths")
        assert exc_info.value.kind is EvaluationErrorKind.INVALID_FILE
        assert "taille" in str(exc_info.value).lower()
        # No S3 push.
        assert fake.put_calls == []
