"""Pydantic schemas for the documents API (s10).

Two response shapes are exposed:

* :class:`UploadResponse` — successful upload (HTTP 201). The
  ``status`` field mirrors :class:`DocumentStatus` (``"indexed"`` or
  ``"manual_review_needed"``). ``chunks_count`` is 0 when the document
  needs manual review (OCR confidence below threshold).
* :class:`UploadErrorResponse` — 4xx/5xx body. The ``code`` field is
  machine-readable and stable so the frontend can map it to a UI state
  (toast, redirect, retry) without parsing the human message.

The request body is bound form-field by form-field in the router
(``Form(...)``), so a dedicated request Pydantic model is not used
(``File`` / ``Form`` cannot be combined with a single Pydantic body
model in FastAPI's contract).
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

# Form field bounds (router enforces these via Pydantic ``Form``).
# Pseudo is validated server-side by the service (``validate_pseudo``
# in ``chroma_store.py``); the router only bounds the length here so
# the Pydantic 422 (long-string) and service 422 (regex) have distinct
# error messages.
MAX_PSEUDO_CHARS = 32
MAX_FILENAME_CHARS = 255


class UploadResponse(BaseModel):
    """Successful upload response (HTTP 201)."""

    document_id: UUID = Field(
        ...,
        description="UUID du document persisté en base.",
    )
    status: Literal["indexed", "manual_review_needed", "error"] = Field(
        ...,
        description="Statut final du document (mirror de DocumentStatus).",
    )
    chunks_count: int = Field(
        ...,
        ge=0,
        description="Nombre de chunks indexés dans ChromaDB (0 si MANUAL_REVIEW_NEEDED).",
    )
    ocr_confidence: float | None = Field(
        default=None,
        description="Confiance OCR (images uniquement, None pour PDF texte).",
    )


class UploadErrorResponse(BaseModel):
    """Failure response body.

    The ``code`` discriminator lets the frontend branch on the cause
    without parsing the (French) human message. Values are aligned with
    :class:`app.services.rag.upload_service.UploadErrorKind` so a future
    addition in the service forces a code addition here.
    """

    error: str = Field(..., description="Message d'erreur lisible.")
    code: Literal[
        "invalid_pseudo",
        "invalid_file",
        "ocr_failure",
        "storage_failure",
    ] = Field(..., description="Code machine de l'erreur.")
