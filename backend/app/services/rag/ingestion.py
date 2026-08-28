"""PDF / image-to-text ingestion and chunking.

The pipeline:

1. PDF: load with ``PyMuPDFLoader``; if the extracted text is shorter than
   ``SCANNED_PDF_MIN_CHARS`` characters, treat as a scanned PDF and fall back
   to OCR (caller-provided).
2. Plain text: split with ``RecursiveCharacterTextSplitter`` using the values
   mandated by the PRD (chunk_size=1000, overlap=200).
3. Each chunk is wrapped in a ``Chunk`` Pydantic model with deterministic
   metadata so ChromaDB ``id`` collisions are avoided on re-ingestion.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Protocol

from langchain_community.document_loaders import PyMuPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pydantic import BaseModel, Field

SCANNED_PDF_MIN_CHARS = 50
"""If a PDF yields fewer characters than this after PyMuPDFLoader, it is treated
as a scanned document and routed to the OCR pipeline."""


class Chunk(BaseModel):
    """A single chunk produced by the ingestion pipeline."""

    id: str
    content: str
    metadata: dict = Field(default_factory=dict)


class _OcrLike(Protocol):
    def transcribe_image(self, image_path: str) -> OcrResult: ...


class OcrResult(BaseModel):  # forward declaration; concrete class lives in ocr.py
    """Mirrors the structure produced by ``MultimodalOcr``; redefined here to
    avoid a circular import (ingestion is consumed by ocr.py's test path)."""

    ok: bool
    transcription: str = ""
    confidence: float = 0.0
    reason: str | None = None


class DocumentIngestor:
    """Open a file, produce ``Chunk`` objects ready for embedding."""

    def __init__(
        self,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        separators: list[str] | None = None,
    ) -> None:
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=separators or ["\n\n", "\n", " ", ""],
        )

    def ingest(
        self,
        file_path: str,
        document_id: uuid.UUID | None = None,
        ocr: _OcrLike | None = None,
    ) -> list[Chunk]:
        """Ingest a file and return its chunks.

        * ``file_path``: path to a PDF (text-extracted) or a plain text file.
          The OCR fallback is only triggered when the file is a PDF that
          ``PyMuPDFLoader`` cannot extract enough text from, **and** an
          ``ocr`` callable is provided.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Fichier introuvable: {file_path}")
        document_id = document_id or uuid.uuid4()
        suffix = path.suffix.lower()

        if suffix == ".pdf":
            text = self._extract_pdf_text(path)
            if len(text.strip()) < SCANNED_PDF_MIN_CHARS and ocr is not None:
                # PDF scanné : on tente l'OCR sur la première page.
                text = self._ocr_first_page(path, ocr)
            return self._split(text, document_id)
        # .txt or anything else with text content.
        return self._split(path.read_text(encoding="utf-8", errors="ignore"), document_id)

    @staticmethod
    def _extract_pdf_text(path: Path) -> str:
        loader = PyMuPDFLoader(str(path))
        documents = loader.load()
        return "\n\n".join(doc.page_content for doc in documents)

    @staticmethod
    def _ocr_first_page(path: Path, ocr: _OcrLike) -> str:
        # We send the PDF itself to the OCR service which extracts the first page.
        # (DeepSeek-OCR-2 accepts PDFs natively.)
        result = ocr.transcribe_image(str(path))
        return result.transcription if result.ok else ""

    def _split(self, text: str, document_id: uuid.UUID) -> list[Chunk]:
        if not text.strip():
            return []
        docs = self._splitter.create_documents([text])
        return [
            Chunk(
                id=f"{document_id}-{i}",
                content=doc.page_content,
                metadata={
                    "chunk_index": i,
                    "document_id": str(document_id),
                },
            )
            for i, doc in enumerate(docs)
        ]
