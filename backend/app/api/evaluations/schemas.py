"""Pydantic schemas for the evaluations API (s18).

Two response shapes are exposed:

* :class:`UploadResponse` — successful upload (HTTP 201). The
  ``status`` field is one of ``"scored"`` or
  ``"manual_review_needed"`` (mirror of
  :class:`app.core.database.models.EvaluationStatus`). When the
  status is ``"manual_review_needed"``, ``score`` and ``max_score``
  are ``None`` — the frontend will display a banner (out of scope
  for s18).
* :class:`UploadErrorResponse` — 4xx/5xx body. The ``code`` field is
  machine-readable and stable so the frontend can map it to a UI
  state without parsing the human message.

The request body is bound form-field by form-field in the router
(``Form()`` / ``File()``); no Pydantic request model is needed
(FastAPI cannot combine ``File`` / ``Form`` with a single
Pydantic body model).
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

# Form field bounds (router enforces these via Pydantic ``Form``).
MAX_FILENAME_CHARS = 255


class UploadResponse(BaseModel):
    """Successful upload response (HTTP 201)."""

    evaluation_id: UUID = Field(
        ...,
        description="UUID de l'évaluation persistée en base.",
    )
    status: Literal["scored", "manual_review_needed"] = Field(
        ...,
        description="Statut final de l'évaluation (mirror de EvaluationStatus).",
    )
    score: float | None = Field(
        default=None,
        description="Score extrait (None quand status=manual_review_needed).",
    )
    max_score: float | None = Field(
        default=None,
        description="Barème du score (None quand status=manual_review_needed).",
    )
    annotations: list[str] = Field(
        default_factory=list,
        description="Annotations courtes extraites par la vision LLM.",
    )
    teacher_comments: str | None = Field(
        default=None,
        description="Commentaire global de l'enseignant, ou null si absent.",
    )
    ocr_confidence: float | None = Field(
        default=None,
        description="Confiance OCR (None quand l'OCR a retourné ok=False).",
    )


class UploadErrorResponse(BaseModel):
    """Failure response body.

    The ``code`` discriminator lets the frontend branch on the cause
    without parsing the (French) human message. Values are aligned
    with :class:`app.services.ocr.evaluation_extractor.EvaluationErrorKind`
    so a future addition in the service forces a code addition here.
    """

    error: str = Field(..., description="Message d'erreur lisible.")
    code: Literal[
        "invalid_file",
        "extraction_failure",
        "storage_failure",
    ] = Field(..., description="Code machine de l'erreur.")
