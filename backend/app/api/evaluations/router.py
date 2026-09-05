"""``POST /api/evaluations/upload`` — multipart upload endpoint (s18).

Bridges FastAPI ``UploadFile`` streams to
:meth:`app.services.ocr.evaluation_extractor.EvaluationService.upload`.
The router's responsibilities mirror ``app/api/documents/router.py``:

* Multipart parsing (FastAPI + ``python-multipart``).
* Two-level size guard (Content-Length header, then post-read body)
  — the service does a third check on the materialized file.
* Materialize the ``UploadFile`` stream to a
  ``tempfile.NamedTemporaryFile`` with the original suffix (the OCR
  transport does not care, but the file-type discrimination is
  clearer when the suffix is preserved).
* Clean up the tempfile in a ``finally`` block so neither a
  successful upload nor a 4xx/5xx error leaks a file.
* Map :class:`EvaluationError` to stable HTTP status codes:

  * ``INVALID_FILE`` (extension) → 415
  * ``INVALID_FILE`` (size) → 413
  * ``EXTRACTION_FAILURE`` → 422
  * ``STORAGE_FAILURE`` → 500

The size vs extension discrimination is done by substring-matching
the service's error message (it includes the literal ``"extension"``
or ``"Taille"`` in each branch). Same trick as
``documents/router.py:78-90``.

**Identity (s15)**: the tenant identity comes from the JWT
(``Depends(get_current_user)``); the multipart body MUST NOT
carry a ``pseudo`` form field (research Drift 1). The AC1 wording
in ``docs/stories.md`` is overridden here — the body accepts
``subject`` and ``file`` only, anything else triggers a 422.
``docs/stories.md`` is not edited in this story; the drift is
recorded in the research report.

**RBAC**: no ``require_role`` filter — the documents upload is
open to ``eleve`` + ``parent`` + ``admin`` (CLAUDE.md § Permissions
RBAC). s18 only lets the **JWT user** upload, with
``student_pseudo = user.pseudo``. Parents uploading on behalf of
their children are out of scope (s17 already pulls children's
data; s18b can add a "submit on behalf of" mode if requested).

s18b — two additional endpoints (manual score entry and reprocess)
attach to this router. See ``score_manual`` and ``reprocess``
below. They live in this same file by convention (one router per
sub-domain, cf. ``documents/router.py`` and ``users/router.py``).
"""

from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from loguru import logger
from sqlalchemy.orm import Session

from app.api.evaluations.factory import get_evaluation_service_dep
from app.api.evaluations.schemas import (
    EvaluationStateErrorResponse,
    ReprocessResponse,
    ScoreManualRequest,
    ScoreManualResponse,
    UploadErrorResponse,
    UploadResponse,
)
from app.core.auth.middleware import (
    assert_jwt_pseudo_matches_or_403,
    assert_parent_linked_to_child_or_403,
    get_current_user,
    require_role,
)
from app.core.config import Settings, get_settings
from app.core.database.models import Evaluation, User, UserRole
from app.core.database.session import get_db
from app.services.ocr.evaluation_extractor import (
    EvaluationError,
    EvaluationErrorKind,
    EvaluationService,
    EvaluationStateError,
)

router = APIRouter(prefix="/api/evaluations", tags=["evaluations"])


def _error_payload(*, message: str, code: str) -> dict:
    """Build the canonical error body for HTTPException details."""
    return UploadErrorResponse(error=message, code=code).model_dump()


def _map_invalid_file_to_status(message: str) -> int:
    """Discriminate size vs extension from the service error message.

    The service emits one of two literal phrases (see
    ``evaluation_extractor.py:300-309``):

    * ``"extension ... non supportée"`` → 415
    * ``"Taille ... supérieure à la limite"`` → 413
    """
    lower = message.lower()
    if "extension" in lower:
        return status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    return status.HTTP_413_CONTENT_TOO_LARGE


@router.post(
    "/upload",
    status_code=status.HTTP_201_CREATED,
    response_model=UploadResponse,
    responses={
        413: {"model": UploadErrorResponse, "description": "Fichier trop volumineux ou extension invalide."},
        415: {"model": UploadErrorResponse, "description": "Extension non supportée."},
        422: {"model": UploadErrorResponse, "description": "Validation ou extraction échouée (OCR injoignable)."},
        500: {"model": UploadErrorResponse, "description": "Panne de stockage (S3/DB)."},
    },
)
async def upload(
    request: Request,
    user: User = Depends(get_current_user),
    subject: Literal["maths", "francais"] = Form(...),
    file: UploadFile = File(...),
    settings: Settings = Depends(get_settings),
    service: EvaluationService = Depends(get_evaluation_service_dep),
) -> UploadResponse:
    """Run the full evaluation upload pipeline.

    The body is validated by FastAPI BEFORE this handler runs (422
    on missing field, unknown subject, etc.). The handler then
    resolves the JWT via :func:`get_current_user` (401
    ``invalid_token`` on failure) and calls the cross-tenant guard
    with ``claimed=None`` — a defensive no-op (no body ``pseudo``
    field, the AC1 drift is overridden).

    The service's :class:`EvaluationError` is mapped to the HTTP
    layer with stable status codes (see module docstring).
    ``MANUAL_REVIEW_NEEDED`` is a successful HTTP outcome — the
    evaluation IS persisted, just with ``status=manual_review_needed``
    and ``score=None``.
    """
    assert_jwt_pseudo_matches_or_403(user, None, route="/api/evaluations/upload")

    # s15 hard cut: the body MUST NOT carry a ``pseudo`` form field
    # (research Piège 1). FastAPI's ``Form()`` / ``File()``
    # parameter parsers do not natively reject unknown fields, so
    # we read the raw form and explicitly reject any field outside
    # the declared schema.
    form = await request.form()
    allowed_fields = {"subject", "file"}
    unknown = set(form.keys()) - allowed_fields
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=[
                {
                    "loc": ("body", min(unknown)),
                    "msg": (
                        "Champ de formulaire inattendu : "
                        + ", ".join(sorted(unknown))
                        + ". Le champ 'pseudo' n'est plus accepté (s15)."
                    ),
                    "type": "value_error.extra",
                }
            ],
        )

    max_bytes = settings.max_upload_size_mb * 1024 * 1024

    # Level 1 — best-effort header check.
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            if int(content_length) > max_bytes:
                raise HTTPException(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    detail=_error_payload(
                        message="Fichier trop volumineux.",
                        code=EvaluationErrorKind.INVALID_FILE.value,
                    ),
                )
        except ValueError:
            # Malformed header — ignore and let the post-read check handle it.
            pass

    # Level 2 — materialize the upload and re-check.
    data = await file.read()
    if len(data) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=_error_payload(
                message="Fichier trop volumineux.",
                code=EvaluationErrorKind.INVALID_FILE.value,
            ),
        )

    # Materialize to a tempfile with the original suffix. ``delete=False``
    # is intentional: the ``EvaluationService`` reads the file from disk
    # AFTER this block closes, so the path must survive the ``with``.
    # The ``finally`` block at the bottom does the actual ``os.unlink``.
    filename = file.filename or f"upload-{uuid.uuid4().hex}"
    suffix = Path(filename).suffix
    tmp = tempfile.NamedTemporaryFile(  # noqa: SIM115 - see comment above
        prefix="ktutor-eval-upload-",
        suffix=suffix,
        delete=False,
    )
    tmp_path: str | None = None
    try:
        tmp.write(data)
        tmp.close()
        tmp_path = tmp.name

        # Level 3 — service check (third defense line).
        try:
            result = service.upload(
                file_path=tmp_path, pseudo=user.pseudo, subject=subject
            )
        except EvaluationError as exc:
            message = str(exc)
            http_status = _status_for_evaluation_error(exc, message)
            logger.warning(
                "Eval upload refused: kind={} pseudo={} message={}",
                exc.kind.value,
                user.pseudo,
                message,
            )
            raise HTTPException(
                status_code=http_status,
                detail=_error_payload(message=message, code=exc.kind.value),
            )

        # MANUAL_REVIEW_NEEDED is a successful HTTP outcome — the
        # file is persisted, just with status=manual_review_needed
        # and score=None.
        return UploadResponse(
            evaluation_id=result.evaluation_id,
            status=result.status.value,
            score=result.score,
            max_score=result.max_score,
            annotations=result.annotations or [],
            teacher_comments=result.teacher_comments,
            ocr_confidence=result.ocr_confidence,
        )
    finally:
        if tmp_path is not None:
            try:
                os.unlink(tmp_path)
            except OSError:
                logger.warning(
                    "Could not remove tempfile {}; ignored.",
                    tmp_path,
                )


def _status_for_evaluation_error(exc: EvaluationError, message: str) -> int:
    """Map an :class:`EvaluationError` to its HTTP status code."""
    if exc.kind is EvaluationErrorKind.INVALID_FILE:
        return _map_invalid_file_to_status(message)
    if exc.kind is EvaluationErrorKind.EXTRACTION_FAILURE:
        return status.HTTP_422_UNPROCESSABLE_CONTENT
    if exc.kind is EvaluationErrorKind.STORAGE_FAILURE:
        return status.HTTP_500_INTERNAL_SERVER_ERROR
    # Defensive fallback — should never trigger.
    return status.HTTP_500_INTERNAL_SERVER_ERROR


# ---------------------------------------------------------------------------
# s18b — POST /api/evaluations/{id}/score-manual
#   and POST /api/evaluations/{id}/reprocess
# ---------------------------------------------------------------------------


def _state_error_to_status(exc: EvaluationStateError) -> int:
    """Map an :class:`EvaluationStateError` to its HTTP status code.

    The convention is: the message substring ``"not_found"`` is the
    only 404 trigger; anything else is a 409 ``state_conflict`` (the
    row is in a state that does not allow the requested transition).
    """
    if "not_found" in str(exc):
        return status.HTTP_404_NOT_FOUND
    return status.HTTP_409_CONFLICT


def _state_error_code(exc: EvaluationStateError) -> str:
    if "not_found" in str(exc):
        return "not_found"
    return "state_conflict"


def _state_error_payload(exc: EvaluationStateError) -> dict:
    """Build the canonical 404/409 body for an EvaluationStateError."""
    return EvaluationStateErrorResponse(
        error=str(exc), code=_state_error_code(exc)
    ).model_dump()


def _require_score_manual_authorized(
    user: User,
    evaluation_id: uuid.UUID,
    *,
    db: Session,
) -> Evaluation:
    """RBAC gate for ``score-manual``.

    The contract is admin-OR-linked-parent (ADR 014). The row is
    loaded FIRST so the helper can read ``row.student_pseudo`` (the
    row's tenant) and not the URL path. A 404 ``not_found`` is
    raised before the RBAC check so a non-authorised caller cannot
    distinguish "missing row" from "row exists but you can't see
    it" — the same anti-leak pattern as the documents router.

    Returns the loaded :class:`Evaluation` (the handler re-uses the
    row from the service response; loading here is just for the
    RBAC check).
    """
    row = db.get(Evaluation, evaluation_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=EvaluationStateErrorResponse(
                error="not_found", code="not_found"
            ).model_dump(),
        )
    if user.role is UserRole.ADMIN:
        return row
    if user.role is UserRole.PARENT:
        # The helper short-circuits on admin, raises 403 ``forbidden``
        # on a parent who is not linked to the row's student.
        assert_parent_linked_to_child_or_403(
            user,
            row.student_pseudo,
            route=f"/api/evaluations/{evaluation_id}/score-manual",
            db=db,
        )
        return row
    # eleve (and any other role) → 403.
    logger.info(
        "auth.middleware.forbidden pseudo={} role={} required=['admin','parent']",
        user.pseudo,
        user.role.value,
    )
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={"error": "Accès refusé.", "code": "forbidden"},
    )


@router.post(
    "/{evaluation_id}/score-manual",
    response_model=ScoreManualResponse,
    responses={
        403: {"model": UploadErrorResponse, "description": "Cible non autorisée."},
        404: {
            "model": EvaluationStateErrorResponse,
            "description": "Évaluation introuvable.",
        },
        409: {
            "model": EvaluationStateErrorResponse,
            "description": "Évaluation déjà scorée.",
        },
        422: {
            "model": UploadErrorResponse,
            "description": "Payload invalide (Pydantic).",
        },
    },
)
async def score_manual(
    evaluation_id: uuid.UUID,
    body: ScoreManualRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    service: EvaluationService = Depends(get_evaluation_service_dep),
) -> ScoreManualResponse:
    """Persist a manually-entered score on a MANUAL_REVIEW_NEEDED row.

    **RBAC** : admin-OR-linked-parent. The row is loaded first so the
    parent-link check reads ``row.student_pseudo`` (the row's tenant)
    rather than anything from the URL or body. An eleve caller is
    rejected with 403 (Piège 5 — no ``row.student_pseudo ==
    user.pseudo`` shortcut).

    **State** : 404 if the row is missing, 409 ``state_conflict`` if
    the row is not in ``MANUAL_REVIEW_NEEDED``. 422 is reserved for
    Pydantic body validation (Piège 1).
    """
    # RBAC + row load.
    _require_score_manual_authorized(user, evaluation_id, db=db)
    try:
        updated = service.score_manual(
            evaluation_id=evaluation_id,
            score=body.score,
            max_score=body.max_score,
            teacher_comments=body.teacher_comments,
        )
    except EvaluationStateError as exc:
        http_status = _state_error_to_status(exc)
        logger.warning(
            "Eval score-manual refused: evaluation_id={} caller={} reason={}",
            evaluation_id,
            user.pseudo,
            str(exc),
        )
        raise HTTPException(
            status_code=http_status,
            detail=_state_error_payload(exc),
        )
    # T5 — audit log on success. ``caller`` is the JWT pseudo (not
    # the row's student_pseudo — that would be the **target**, not
    # the operator). The teacher_comments value is intentionally
    # absent (PII / AGENTS.md § Backend logging).
    logger.info(
        "security.evaluation_manual_score caller={} evaluation_id={} "
        "new_score={} new_max_score={} student_pseudo={}",
        user.pseudo,
        evaluation_id,
        body.score,
        body.max_score,
        updated.student_pseudo,
    )
    return ScoreManualResponse(
        evaluation_id=updated.id,
        status=updated.status.value,
        score=updated.score,
        max_score=updated.max_score,
        teacher_comments=updated.teacher_comments,
        created_at=updated.created_at,
    )


@router.post(
    "/{evaluation_id}/reprocess",
    response_model=ReprocessResponse,
    responses={
        403: {"model": UploadErrorResponse, "description": "Cible non autorisée."},
        404: {
            "model": EvaluationStateErrorResponse,
            "description": "Évaluation introuvable.",
        },
        409: {
            "model": EvaluationStateErrorResponse,
            "description": "Évaluation déjà scorée.",
        },
        500: {
            "model": UploadErrorResponse,
            "description": "OCR ou stockage indisponible.",
        },
    },
)
async def reprocess(
    evaluation_id: uuid.UUID,
    user: User = Depends(require_role(UserRole.ADMIN)),
    db: Session = Depends(get_db),
    service: EvaluationService = Depends(get_evaluation_service_dep),
) -> ReprocessResponse:
    """Re-run the LLM vision extractor on the original image.

    **RBAC** : admin only (AC4). Parents and eleves are rejected
    with 403 by ``require_role(UserRole.ADMIN)``.

    **State** : 404 if the row is missing, 409 ``state_conflict`` if
    the row is already SCORED (Piège 4 — re-scorer une copie déjà
    scorée n'a pas de sens en s18b).
    """
    # The ``require_role`` dependency already enforced admin. The
    # row is loaded here so the 404 anti-leak is consistent with
    # ``score-manual`` (and the service can short-circuit on
    # state-conflict before the S3 download).
    row = db.get(Evaluation, evaluation_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=EvaluationStateErrorResponse(
                error="not_found", code="not_found"
            ).model_dump(),
        )
    try:
        outcome = service.reprocess(evaluation_id=evaluation_id)
    except EvaluationStateError as exc:
        http_status = _state_error_to_status(exc)
        logger.warning(
            "Eval reprocess refused: evaluation_id={} caller={} reason={}",
            evaluation_id,
            user.pseudo,
            str(exc),
        )
        raise HTTPException(
            status_code=http_status,
            detail=_state_error_payload(exc),
        )
    # T5 — audit log on success. No OCR text, no image bytes, no
    # teacher_comments in the log line (AGENTS.md § Backend logging).
    logger.info(
        "evaluation.reprocess_attempted caller={} evaluation_id={} "
        "previous_status={} new_status={} new_score={} student_pseudo={}",
        user.pseudo,
        evaluation_id,
        outcome.previous_status.value,
        outcome.evaluation.status.value,
        outcome.extraction.score,
        outcome.evaluation.student_pseudo,
    )
    return ReprocessResponse(
        evaluation_id=outcome.evaluation.id,
        status=outcome.evaluation.status.value,
        score=outcome.evaluation.score,
        max_score=outcome.evaluation.max_score,
        teacher_comments=outcome.evaluation.teacher_comments,
        created_at=outcome.evaluation.created_at,
        ocr_confidence=outcome.extraction.ocr_confidence,
        source=outcome.extraction.source,
    )


__all__ = ["router"]
