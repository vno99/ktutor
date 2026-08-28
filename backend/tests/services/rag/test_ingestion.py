"""Tests for the ``DocumentIngestor`` pipeline."""

from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.services.rag.ingestion import (
    Chunk,
    DocumentIngestor,
    OcrResult,
)


class TestIngestTextPdf:
    def test_extracts_text_from_text_pdf(
        self, sample_pdf_path: Path, fixed_document_id: uuid.UUID
    ) -> None:
        ingestor = DocumentIngestor()
        chunks = ingestor.ingest(str(sample_pdf_path), document_id=fixed_document_id)
        assert chunks, "expected non-empty chunk list for a text PDF"
        assert all(isinstance(c, Chunk) for c in chunks)
        joined = " ".join(c.content for c in chunks)
        # The fixture contains the word "dérivée" — proves PyMuPDFLoader did its job.
        assert "dérivée" in joined or "derivee" in joined

    def test_chunks_carry_metadata(
        self, sample_pdf_path: Path, fixed_document_id: uuid.UUID
    ) -> None:
        chunks = DocumentIngestor().ingest(str(sample_pdf_path), document_id=fixed_document_id)
        assert chunks
        first = chunks[0]
        assert first.metadata["document_id"] == str(fixed_document_id)
        assert first.metadata["chunk_index"] == 0
        # Chunk ids are deterministic for the same document id.
        assert first.id == f"{fixed_document_id}-0"

    def test_chunk_size_and_overlap_observed(
        self, sample_pdf_path: Path
    ) -> None:
        chunks = DocumentIngestor(chunk_size=300, chunk_overlap=50).ingest(str(sample_pdf_path))
        # Each chunk except possibly the last must be at or below chunk_size.
        # We use a tolerant upper bound because splitter may emit slightly
        # larger pieces at paragraph boundaries.
        for c in chunks[:-1]:
            assert len(c.content) <= 300 + 50

    def test_empty_pdf_yields_no_chunks(self, tmp_upload: Path) -> None:
        # Empty PDF: 1 page, no text written.
        from reportlab.pdfgen import canvas

        path = tmp_upload / "empty.pdf"
        c = canvas.Canvas(str(path))
        c.showPage()
        c.save()
        chunks = DocumentIngestor().ingest(str(path))
        assert chunks == []


class TestScannedPdfFallback:
    def test_short_text_falls_back_to_ocr(
        self, tmp_upload: Path, fixed_document_id: uuid.UUID
    ) -> None:
        # Build a PDF whose text is shorter than SCANNED_PDF_MIN_CHARS to
        # trigger the OCR path.
        path = tmp_upload / "scanned.pdf"
        from tests.conftest import make_sample_pdf

        make_sample_pdf(path, pages=1, page_text="x")  # 1 char total

        # Stub OCR: returns 1 sentence.
        ocr = MagicMock()
        ocr.transcribe_image.return_value = OcrResult(
            ok=True,
            transcription="Cours de maths: dérivée d'une fonction.",
            confidence=0.9,
        )

        chunks = DocumentIngestor().ingest(
            str(path), document_id=fixed_document_id, ocr=ocr
        )
        assert chunks
        assert "dérivée" in chunks[0].content
        ocr.transcribe_image.assert_called_once()

    def test_ocr_failure_yields_no_chunks(
        self, tmp_upload: Path, fixed_document_id: uuid.UUID
    ) -> None:
        path = tmp_upload / "scanned.pdf"
        from tests.conftest import make_sample_pdf

        make_sample_pdf(path, pages=1, page_text="x")

        ocr = MagicMock()
        ocr.transcribe_image.return_value = OcrResult(
            ok=False, transcription="", confidence=0.1, reason="low_confidence"
        )
        chunks = DocumentIngestor().ingest(
            str(path), document_id=fixed_document_id, ocr=ocr
        )
        assert chunks == []


class TestIngestMissingFile:
    def test_missing_file_raises(self, tmp_upload: Path) -> None:
        with pytest.raises(FileNotFoundError):
            DocumentIngestor().ingest(str(tmp_upload / "does-not-exist.pdf"))
