"""End-to-end upload orchestration.

The service is the *only* place that knows about the order of operations:

  1. validate the pseudo (multi-tenant contract, exit code 5)
  2. validate the file (size + extension, exit code 2)
  3. push the source file to S3 / SeaweedFS (rollback target on later failure)
  4. run the right ingestion path (PDF text / scanned PDF+OCR / image+OCR)
  5. embed the chunks
  6. add the chunks to the per-pseudo ChromaDB collection
  7. write a row in the ``documents`` table
  8. delete the S3 object on any failure past step 3 (AC4 — "persists nothing")
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Protocol

from app.core.database.models import DocumentStatus, Subject
from app.services.rag.chroma_store import ChromaStore, validate_pseudo
from app.services.rag.ingestion import Chunk, DocumentIngestor
from app.services.rag.ocr import MultimodalOcr, OcrError, OcrResult
from app.services.storage.minio_client import MinioClient

# Document exit codes (see docs/designs/s01-uploader-document.md § Conventions).
EXIT_OK = 0
EXIT_GENERIC_ERROR = 1
EXIT_INVALID_FILE = 2
EXIT_OCR_FAILURE = 3
EXIT_STORAGE_FAILURE = 4
EXIT_INVALID_PSEUDO = 5

ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".txt"}


class UploadErrorKind(str, Enum):
    INVALID_PSEUDO = "invalid_pseudo"
    INVALID_FILE = "invalid_file"
    OCR_FAILURE = "ocr_failure"
    STORAGE_FAILURE = "storage_failure"


class UploadError(Exception):
    """Raised by ``UploadService.upload`` to signal a controlled failure."""

    def __init__(self, kind: UploadErrorKind, message: str) -> None:
        super().__init__(message)
        self.kind = kind


@dataclass
class UploadResult:
    """Outcome of a successful upload."""

    document_id: uuid.UUID
    chunks_count: int
    duration_ms: int
    status: DocumentStatus
    collection: str
    s3_key: str
    ocr_confidence: float | None = None


class _SessionLike(Protocol):
    def add(self, obj) -> None: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...


class _EmbeddingsLike(Protocol):
    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...


class UploadService:
    """Orchestrate one upload from CLI to a fully indexed RAG document.

    The constructor takes *interfaces* for every dependency so the service can
    be unit-tested with cheap in-memory doubles.
    """

    def __init__(
        self,
        *,
        s3_client: MinioClient,
        chroma_store: ChromaStore,
        embeddings: _EmbeddingsLike,
        ingestor: DocumentIngestor,
        ocr: MultimodalOcr,
        session_factory: Callable[[], _SessionLike] | None = None,
        max_upload_size_mb: int = 20,
    ) -> None:
        self._s3 = s3_client
        self._chroma = chroma_store
        self._embeddings = embeddings
        self._ingestor = ingestor
        self._ocr = ocr
        self._session_factory = session_factory
        self._max_bytes = max_upload_size_mb * 1024 * 1024

    def upload(self, file_path: str, pseudo: str, subject: str) -> UploadResult:
        """Run the full pipeline. Raises :class:`UploadError` on any controlled failure."""
        started = time.monotonic()
        try:
            validate_pseudo(pseudo)
        except ValueError as exc:
            raise UploadError(UploadErrorKind.INVALID_PSEUDO, str(exc)) from exc

        path = Path(file_path)
        if not path.exists() or path.suffix.lower() not in ALLOWED_EXTENSIONS:
            raise UploadError(
                UploadErrorKind.INVALID_FILE,
                f"Fichier invalide: extension {path.suffix!r} non supportée",
            )
        size = path.stat().st_size
        if size > self._max_bytes:
            raise UploadError(
                UploadErrorKind.INVALID_FILE,
                f"Taille {size / (1024 * 1024):.1f} Mo supérieure à la limite "
                f"({self._max_bytes // (1024 * 1024)} Mo)",
            )

        document_id = uuid.uuid4()

        # Step 1: push to S3 first; everything past this point must roll back.
        try:
            s3_key = self._s3.put_object(
                pseudo=pseudo,
                document_id=document_id,
                filename=path.name,
                data=path.read_bytes(),
            )
        except Exception as exc:
            raise UploadError(UploadErrorKind.STORAGE_FAILURE, f"S3 put_object: {exc}") from exc

        # From here on, any failure must clean up the S3 object (AC4).
        try:
            chunks, ocr_confidence = self._extract_text(path, document_id)

            if not chunks:
                # OCR low confidence or empty text: refuse to index, but still
                # create a row with status=manual_review_needed for traceability.
                self._persist_document(
                    document_id=document_id,
                    pseudo=pseudo,
                    subject=subject,
                    filename=path.name,
                    s3_key=s3_key,
                    chunks_count=0,
                    status=DocumentStatus.MANUAL_REVIEW_NEEDED,
                    error_reason="ocr_low_confidence",
                )
                return UploadResult(
                    document_id=document_id,
                    chunks_count=0,
                    duration_ms=_ms_since(started),
                    status=DocumentStatus.MANUAL_REVIEW_NEEDED,
                    collection="",
                    s3_key=s3_key,
                    ocr_confidence=ocr_confidence,
                )

            # Step 2: embed.
            embeddings = self._embeddings.embed_documents([c.content for c in chunks])
            # Step 3: index.
            collection = self._chroma.get_collection(subject, pseudo)
            self._chroma.add_chunks(
                collection,
                [_to_chroma_dict(c, document_id) for c in chunks],
                embeddings,
            )
            # Step 4: persist row.
            self._persist_document(
                document_id=document_id,
                pseudo=pseudo,
                subject=subject,
                filename=path.name,
                s3_key=s3_key,
                chunks_count=len(chunks),
                status=DocumentStatus.INDEXED,
                error_reason=None,
            )
            return UploadResult(
                document_id=document_id,
                chunks_count=len(chunks),
                duration_ms=_ms_since(started),
                status=DocumentStatus.INDEXED,
                collection=collection.name,
                s3_key=s3_key,
                ocr_confidence=ocr_confidence,
            )
        except UploadError:
            self._s3.remove_object(s3_key)
            raise
        except Exception as exc:
            # Unknown failure: roll back S3 and surface as a storage failure
            # so the CLI can show a generic error and the user can retry.
            self._s3.remove_object(s3_key)
            raise UploadError(UploadErrorKind.STORAGE_FAILURE, f"Pipeline failure: {exc}") from exc

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _extract_text(
        self, path: Path, document_id: uuid.UUID
    ) -> tuple[list[Chunk], float | None]:
        """Run OCR first if the file is an image; else defer to the ingestor."""
        suffix = path.suffix.lower()
        if suffix in {".png", ".jpg", ".jpeg"}:
            try:
                result: OcrResult = self._ocr.transcribe_image(str(path))
            except OcrError as exc:
                raise UploadError(UploadErrorKind.OCR_FAILURE, str(exc)) from exc
            except FileNotFoundError as exc:
                raise UploadError(UploadErrorKind.INVALID_FILE, str(exc)) from exc
            if not result.ok:
                return [], result.confidence
            # Use the ingestor's splitter on the OCR'd text so we benefit from
            # the same chunking strategy.
            from langchain_text_splitters import RecursiveCharacterTextSplitter

            splitter = RecursiveCharacterTextSplitter(
                chunk_size=self._ingestor._splitter._chunk_size,  # type: ignore[attr-defined]
                chunk_overlap=self._ingestor._splitter._chunk_overlap,  # type: ignore[attr-defined]
                separators=self._ingestor._splitter._separators,  # type: ignore[attr-defined]
            )
            docs = splitter.create_documents([result.transcription])
            chunks = [
                Chunk(
                    id=f"{document_id}-{i}",
                    content=doc.page_content,
                    metadata={"chunk_index": i, "document_id": str(document_id)},
                )
                for i, doc in enumerate(docs)
            ]
            return chunks, result.confidence
        # PDF or text: let the ingestor decide (PDF scanned fallback to OCR).
        chunks = self._ingestor.ingest(str(path), document_id=document_id, ocr=self._ocr)
        return chunks, None

    def _persist_document(
        self,
        *,
        document_id: uuid.UUID,
        pseudo: str,
        subject: str,
        filename: str,
        s3_key: str,
        chunks_count: int,
        status: DocumentStatus,
        error_reason: str | None,
    ) -> None:
        """Insert the document row. No-op when no session factory is configured."""
        if self._session_factory is None:
            return
        session = self._session_factory()
        try:
            from app.core.database.models import Document

            session.add(
                Document(
                    id=document_id,
                    student_pseudo=pseudo,
                    subject=Subject(subject),
                    filename=filename,
                    s3_key=s3_key,
                    chunks_count=chunks_count,
                    status=status,
                    error_reason=error_reason,
                )
            )
            session.commit()
        except Exception:
            session.rollback()
            raise


def _ms_since(start: float) -> int:
    return int((time.monotonic() - start) * 1000)


def _to_chroma_dict(chunk: Chunk, document_id: uuid.UUID) -> dict:
    return {
        "id": chunk.id,
        "content": chunk.content,
        "metadata": {**chunk.metadata, "document_id": str(document_id)},
    }
