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

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

# Form field bounds (router enforces these via Pydantic ``Form``).
MAX_FILENAME_CHARS = 255

# s18b — bounds for the manual score entry. Pydantic enforces them
# at the request layer; the router maps violations to 422.
TEACHER_COMMENTS_MAX_CHARS = 8192


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


# ---------------------------------------------------------------------------
# s18b — manual score entry and reprocess responses.
# ---------------------------------------------------------------------------


class ScoreManualRequest(BaseModel):
    """Body of ``POST /api/evaluations/{id}/score-manual``.

    The bounds are Pydantic-enforced; violations surface as 422 (never
    409 — the 409 is reserved for the *state* conflict, see Piège 1
    of the s18b research).
    """

    score: float = Field(..., ge=0, description="Score saisi (>= 0).")
    max_score: float = Field(..., ge=0, description="Barème (>= 0).")
    teacher_comments: str | None = Field(
        default=None,
        max_length=TEACHER_COMMENTS_MAX_CHARS,
        description="Commentaire global de l'enseignant (optionnel).",
    )

    @model_validator(mode="after")
    def _score_le_max_score(self) -> ScoreManualRequest:
        if self.score > self.max_score:
            raise ValueError("score doit être <= max_score")
        return self


class EvaluationResponse(BaseModel):
    """Common shape for both ``ScoreManualResponse`` and ``ReprocessResponse``.

    Carries the persisted row's user-visible fields. The
    ``ReprocessResponse`` extends this with the OCR confidence and
    the source discriminator (``"regex" / "llm" / "none"``) read off
    the :class:`ExtractionResult`.
    """

    evaluation_id: UUID = Field(
        ...,
        description="UUID de l'évaluation mise à jour.",
    )
    status: Literal["scored", "manual_review_needed"] = Field(
        ...,
        description="Statut après l'opération.",
    )
    score: float | None = Field(default=None, description="Score final.")
    max_score: float | None = Field(default=None, description="Barème du score.")
    teacher_comments: str | None = Field(
        default=None,
        description="Commentaire global de l'enseignant.",
    )
    created_at: datetime = Field(
        ...,
        description="Horodatage de la ligne (UTC). S18b n'ajoute pas "
        "de colonne d'historique : ``created_at`` est l'horodatage de "
        "dernière mise à jour effective.",
    )


class ScoreManualResponse(EvaluationResponse):
    """Successful response of ``POST /api/evaluations/{id}/score-manual``."""


class ReprocessResponse(EvaluationResponse):
    """Successful response of ``POST /api/evaluations/{id}/reprocess``.

    Carries the OCR source discriminator and confidence so the caller
    can audit which extraction path produced the score (regex / LLM /
    none).
    """

    ocr_confidence: float | None = Field(
        default=None,
        description="Confiance OCR du dernier passage (None si ok=False).",
    )
    source: Literal["regex", "llm", "none"] = Field(
        ...,
        description="Source du score (regex / llm / none).",
    )


class EvaluationStateErrorResponse(BaseModel):
    """Body for 404 (not_found) and 409 (state_conflict) responses.

    The two cases share the same wire shape — the discriminator is
    the ``code`` field. The router maps an :class:`EvaluationStateError`
    to 404 when the message is ``"not_found"`` and to 409 otherwise.
    """

    error: str = Field(..., description="Message d'erreur lisible.")
    code: Literal["state_conflict", "not_found"] = Field(
        ...,
        description="Code machine de l'erreur.",
    )
