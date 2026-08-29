"""Tests for ``UploadService``.

Every external dependency is replaced with a controllable double: we want
to assert *what* the service does, not how the storage / embeddings / Chroma
internals behave. Those are tested in their own files.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import chromadb
import pytest

from app.core.database.models import Document, DocumentStatus
from app.services.rag.chroma_store import ChromaStore
from app.services.rag.ingestion import DocumentIngestor
from app.services.rag.ocr import MultimodalOcr
from app.services.rag.upload_service import (
    ALLOWED_EXTENSIONS,
    UploadError,
    UploadErrorKind,
    UploadService,
)
from app.services.storage.minio_client import MinioClient
from tests.services.storage.test_s3_client import FakeS3

# ---------------------------------------------------------------------------
# Shared doubles
# ---------------------------------------------------------------------------


class FakeEmbeddings:
    """Deterministic embeddings: each text becomes a 3-dim vector derived from its hash."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        return [[float(len(t) % 7), float(t.count(" ") % 7), 1.0] for t in texts]


class FakeSession:
    """In-memory session that records added Documents."""

    def __init__(self) -> None:
        self.added: list[Document] = []
        self.committed = False
        self.rolled_back = False

    def add(self, obj) -> None:
        self.added.append(obj)

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True


def _build_service(
    *,
    embeddings: FakeEmbeddings | None = None,
    session: FakeSession | None = None,
    ocr_transport: object = None,
    persist_directory: Path | None = None,
    max_upload_size_mb: int = 20,
) -> tuple[UploadService, FakeS3, ChromaStore, FakeEmbeddings, list[FakeSession]]:
    """Build a wired service plus its dependencies (for assertions)."""
    fake_s3 = FakeS3()
    s3_client = MinioClient(
        endpoint="localhost:8333", access_key="k", secret_key="s", bucket="bkt"
    )
    s3_client._client = fake_s3  # type: ignore[attr-defined]

    chroma = ChromaStore(client=chromadb.EphemeralClient())
    embeddings = embeddings or FakeEmbeddings()

    if ocr_transport is None:
        # Default OCR returns ok=True with a deterministic transcription.
        def handler(request):
            import json as _json

            import httpx

            return httpx.Response(
                200,
                content=_json.dumps(
                    {
                        "transcription": "OCR'd text",
                        "type": "texte",
                        "confidence": 0.9,
                        "has_math": False,
                    }
                ),
            )

        import httpx

        ocr_transport = httpx.MockTransport(handler)
    ocr = MultimodalOcr(base_url="http://ocr", transport=ocr_transport)

    sessions: list[FakeSession] = []

    def session_factory():
        s = session or FakeSession()
        sessions.append(s)
        return s

    service = UploadService(
        s3_client=s3_client,
        chroma_store=chroma,
        embeddings=embeddings,
        ingestor=DocumentIngestor(),
        ocr=ocr,
        session_factory=session_factory,
        max_upload_size_mb=max_upload_size_mb,
    )
    return service, fake_s3, chroma, embeddings, sessions


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestValidation:
    def test_invalid_pseudo_raises_with_code_5(self, tmp_path: Path) -> None:
        service, *_ = _build_service()
        with pytest.raises(UploadError) as exc_info:
            service.upload(str(tmp_path / "x.pdf"), "bad-pseudo", "maths")
        assert exc_info.value.kind is UploadErrorKind.INVALID_PSEUDO

    def test_missing_file_raises_invalid_file(self, tmp_path: Path) -> None:
        service, *_ = _build_service()
        with pytest.raises(UploadError) as exc_info:
            service.upload(str(tmp_path / "missing.pdf"), "ali", "maths")
        assert exc_info.value.kind is UploadErrorKind.INVALID_FILE

    def test_unsupported_extension_raises_invalid_file(self, tmp_upload: Path) -> None:
        bad = tmp_upload / "bad.exe"
        bad.write_bytes(b"fake")
        service, *_ = _build_service()
        with pytest.raises(UploadError) as exc_info:
            service.upload(str(bad), "ali", "maths")
        assert exc_info.value.kind is UploadErrorKind.INVALID_FILE

    def test_oversized_file_raises_invalid_file(self, tmp_upload: Path) -> None:
        # Use a smaller max for the test to keep it fast.
        service, *_ = _build_service(max_upload_size_mb=1)
        big = tmp_upload / "big.pdf"
        big.write_bytes(b"x" * (2 * 1024 * 1024))  # 2MB > 1MB
        with pytest.raises(UploadError) as exc_info:
            service.upload(str(big), "ali", "maths")
        assert exc_info.value.kind is UploadErrorKind.INVALID_FILE


class TestHappyPath:
    def test_text_pdf_indexed_and_persisted(self, sample_pdf_path: Path) -> None:
        pseudo = f"u_{uuid.uuid4().hex[:10]}"
        service, fake_s3, chroma, embeddings, sessions = _build_service()
        result = service.upload(str(sample_pdf_path), pseudo, "maths")

        assert result.status is DocumentStatus.INDEXED
        assert result.chunks_count > 0
        assert result.collection == f"rag_maths_{pseudo}"
        # S3 got the file.
        keys = [k for (_bucket, k) in fake_s3.objects]
        assert any(k.startswith(f"students/{pseudo}/") for k in keys)
        # Chroma collection has the chunks.
        coll = chroma.get_collection("maths", pseudo)
        assert coll.count() == result.chunks_count
        # Embeddings called once with all chunk contents.
        assert embeddings.calls and len(embeddings.calls[0]) == result.chunks_count
        # Persisted a row in the documents table.
        assert sessions and sessions[0].added and sessions[0].committed
        row = sessions[0].added[0]
        assert isinstance(row, Document)
        assert row.student_pseudo == pseudo
        assert row.status is DocumentStatus.INDEXED

    def test_typed_image_uses_ocr_then_persists(self, typed_image_path: Path) -> None:
        pseudo = f"u_{uuid.uuid4().hex[:10]}"
        service, _, _, _, sessions = _build_service()
        result = service.upload(str(typed_image_path), pseudo, "maths")
        assert result.status is DocumentStatus.INDEXED
        assert result.ocr_confidence == pytest.approx(0.9)
        assert sessions and sessions[0].added


class TestManualReviewNeeded:
    def test_low_confidence_ocr_yields_no_chunks_but_persists_row(
        self, typed_image_path: Path
    ) -> None:
        import json as _json

        import httpx

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                content=_json.dumps(
                    {
                        "transcription": "flou",
                        "type": "texte",
                        "confidence": 0.2,
                        "has_math": False,
                    }
                ),
            )

        pseudo = f"u_{uuid.uuid4().hex[:10]}"
        service, _fake_s3, _, _, sessions = _build_service(ocr_transport=httpx.MockTransport(handler))
        result = service.upload(str(typed_image_path), pseudo, "maths")

        assert result.status is DocumentStatus.MANUAL_REVIEW_NEEDED
        assert result.chunks_count == 0
        assert result.ocr_confidence == pytest.approx(0.2)
        # Row was still created so the user can find their upload later.
        assert sessions and sessions[0].added
        row = sessions[0].added[0]
        assert row.status is DocumentStatus.MANUAL_REVIEW_NEEDED
        assert row.error_reason == "ocr_low_confidence"
        # No chunks were indexed — the Chroma collection may exist but is empty.
        chroma = service._chroma  # type: ignore[attr-defined]
        coll = chroma.get_collection("maths", pseudo)
        assert coll.count() == 0

    def test_ocr_http_error_raises_ocr_failure(self, typed_image_path: Path) -> None:
        import httpx

        transport = httpx.MockTransport(lambda req: httpx.Response(500, content="boom"))
        pseudo = f"u_{uuid.uuid4().hex[:10]}"
        service, fake_s3, _, _, _ = _build_service(ocr_transport=transport)
        with pytest.raises(UploadError) as exc_info:
            service.upload(str(typed_image_path), pseudo, "maths")
        assert exc_info.value.kind is UploadErrorKind.OCR_FAILURE
        # AC4: the S3 object must have been rolled back.
        keys = [k for (_bucket, k) in fake_s3.objects]
        assert not any(k.startswith(f"students/{pseudo}/") for k in keys)


class TestRollback:
    def test_s3_object_removed_on_chromadb_failure(self, sample_pdf_path: Path) -> None:
        pseudo = f"u_{uuid.uuid4().hex[:10]}"
        service, fake_s3, _, _, _ = _build_service()

        # Sabotage Chroma so that add_chunks raises.
        from app.services.rag.chroma_store import ChromaStore

        original_add = ChromaStore.add_chunks

        def boom(self, collection, chunks, embeddings):
            raise RuntimeError("chroma down")

        ChromaStore.add_chunks = boom  # type: ignore[assignment]
        try:
            with pytest.raises(UploadError) as exc_info:
                service.upload(str(sample_pdf_path), pseudo, "maths")
        finally:
            ChromaStore.add_chunks = original_add  # type: ignore[assignment]

        assert exc_info.value.kind is UploadErrorKind.STORAGE_FAILURE
        # The S3 key for this pseudo must have been removed (rollback).
        keys = [k for (_bucket, k) in fake_s3.objects]
        assert not any(k.startswith(f"students/{pseudo}/") for k in keys)


class TestSessionFailure:
    def test_postgres_failure_rolls_back_s3(self, sample_pdf_path: Path) -> None:
        class FailingSession(FakeSession):
            def commit(self) -> None:
                raise RuntimeError("postgres down")

        pseudo = f"u_{uuid.uuid4().hex[:10]}"
        service, fake_s3, _, _, _ = _build_service(session=FailingSession())
        with pytest.raises(UploadError) as exc_info:
            service.upload(str(sample_pdf_path), pseudo, "maths")
        assert exc_info.value.kind is UploadErrorKind.STORAGE_FAILURE
        # S3 must have been rolled back.
        keys = [k for (_bucket, k) in fake_s3.objects]
        assert not any(k.startswith(f"students/{pseudo}/") for k in keys)


class TestAllowedExtensions:
    def test_extensions_include_pdf_png_jpg_txt(self) -> None:
        assert {".pdf", ".png", ".jpg", ".jpeg", ".txt"} == ALLOWED_EXTENSIONS


class TestMetadata:
    """Chroma metadata must include the filename so the chat agent can cite sources (s02)."""

    def test_filename_included_in_chroma_metadata(self, sample_pdf_path: Path) -> None:
        pseudo = f"u_{uuid.uuid4().hex[:10]}"
        service, _, chroma, _, _ = _build_service()
        service.upload(str(sample_pdf_path), pseudo, "maths")

        coll = chroma.get_collection("maths", pseudo)
        results = coll.get(include=["metadatas"])
        assert results["metadatas"], "expected at least one indexed chunk"
        for meta in results["metadatas"]:
            assert meta.get("filename") == sample_pdf_path.name
            assert meta.get("document_id")
