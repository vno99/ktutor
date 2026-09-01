"""``POST /api/documents/upload`` — multipart upload endpoint (s10).

Bridges FastAPI ``UploadFile`` streams to
:class:`app.services.rag.upload_service.UploadService.upload`. The
service is the **same** one the CLI invokes, so the upload pipeline
(validation, S3 push, OCR, embedding, ChromaDB index, Document row,
S3 rollback on failure) is shared (AC4 — ``app/cli.py:333``).

The router's only responsibilities:

* Multipart parsing (handled by FastAPI + ``python-multipart``).
* Two-level size guard (Content-Length header, then post-read) — the
  service does a third check on the materialized file (Piège 2 —
  defense in depth).
* Materialize the ``UploadFile`` stream to a ``tempfile.NamedTemporaryFile``
  so :func:`UploadService.upload` can read it from disk (Piège 1).
* Clean up the tempfile in a ``finally`` block so neither a successful
  upload nor a 4xx/5xx error leaks a file (Risque 1).
* Map :class:`UploadError` to stable HTTP status codes:

  * ``INVALID_PSEUDO`` → 422 (validation)
  * ``INVALID_FILE`` (taille) → 413 (Payload Too Large)
  * ``INVALID_FILE`` (extension) → 415 (Unsupported Media Type)
  * ``OCR_FAILURE`` → 422
  * ``STORAGE_FAILURE`` → 500

The size vs extension discrimination is done by substring-matching the
service's error message (it includes the literal ``"extension"`` or
``"Taille"`` in each branch — see ``upload_service.py:115-126``). This
keeps the router decoupled from the service's internals while staying
deterministic.
"""

from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from loguru import logger

from app.api.documents.factory import get_upload_service_dep
from app.api.documents.schemas import (
    MAX_PSEUDO_CHARS,
    UploadErrorResponse,
    UploadResponse,
)
from app.core.config import Settings, get_settings
from app.services.rag.upload_service import (
    UploadError,
    UploadErrorKind,
    UploadService,
)

router = APIRouter(prefix="/api/documents", tags=["documents"])


def _error_payload(*, message: str, code: str) -> dict:
    """Build the canonical error body for HTTPException details."""
    return UploadErrorResponse(error=message, code=code).model_dump()


def _map_invalid_file_to_status(message: str) -> int:
    """Discriminate size vs extension from the service error message.

    The service emits one of two literal phrases (see
    ``upload_service.py:115-126``):

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
        422: {"model": UploadErrorResponse, "description": "Validation ou OCR échoué."},
        500: {"model": UploadErrorResponse, "description": "Panne de stockage (S3/DB)."},
    },
)
async def upload(
    request: Request,
    pseudo: str = Form(..., min_length=1, max_length=MAX_PSEUDO_CHARS),
    subject: Literal["maths", "francais"] = Form(...),
    file: UploadFile = File(...),
    settings: Settings = Depends(get_settings),
    service: UploadService = Depends(get_upload_service_dep),
) -> UploadResponse:
    """Run the full upload pipeline via :class:`UploadService`.

    The body is validated by FastAPI BEFORE this handler runs (422
    on missing field, unknown subject, oversize pseudo, etc.). The
    handler then performs a defensive size check at two levels
    (``Content-Length`` header, then post-read body length) before
    materializing the file to a tempfile and calling the service.

    The service's :class:`UploadError` is mapped to the HTTP layer
    with stable status codes (see module docstring).
    """
    max_bytes = settings.max_upload_size_mb * 1024 * 1024

    # Level 1 — best-effort header check (clients may omit Content-Length).
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            if int(content_length) > max_bytes:
                raise HTTPException(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    detail=_error_payload(
                        message="Fichier trop volumineux.",
                        code=UploadErrorKind.INVALID_FILE.value,
                    ),
                )
        except ValueError:
            # Malformed header — ignore and let the post-read check handle it.
            pass

    # Level 2 — materialize the upload and re-check (Piège 2).
    data = await file.read()
    if len(data) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=_error_payload(
                message="Fichier trop volumineux.",
                code=UploadErrorKind.INVALID_FILE.value,
            ),
        )

    # Tempfile with the same extension as the upload (the service
    # inspects the suffix to discriminate text/image/PDF). Cleanup is
    # mandatory — the test bite ``test_upload_does_not_leave_tempfile``
    # will catch any leak. ``delete=False`` is intentional: the
    # ``UploadService`` reads the file from disk AFTER this block
    # closes, so the path must survive the ``with``. The ``finally``
    # block at the bottom does the actual ``os.unlink``.
    filename = file.filename or f"upload-{uuid.uuid4().hex}"
    suffix = Path(filename).suffix
    tmp = tempfile.NamedTemporaryFile(  # noqa: SIM115 - see comment above
        prefix="ktutor-upload-",
        suffix=suffix,
        delete=False,
    )
    tmp_path: str | None = None
    try:
        tmp.write(data)
        tmp.close()
        tmp_path = tmp.name

        # Level 3 — service check (third defense line, Piège 2).
        try:
            result = service.upload(tmp_path, pseudo, subject)
        except UploadError as exc:
            message = str(exc)
            http_status = _status_for_upload_error(exc, message)
            logger.warning(
                "Upload refused: kind={} pseudo={} message={}",
                exc.kind.value,
                pseudo,
                message,
            )
            raise HTTPException(
                status_code=http_status,
                detail=_error_payload(message=message, code=exc.kind.value),
            )
        # MANUAL_REVIEW_NEEDED is a successful HTTP outcome — the file
        # is persisted, just with status=manual_review_needed and 0
        # chunks (Piège 7). The frontend decides what to show.
        return UploadResponse(
            document_id=result.document_id,
            status=result.status.value,
            chunks_count=result.chunks_count,
            ocr_confidence=result.ocr_confidence,
        )
    finally:
        if tmp_path is not None:
            try:
                os.unlink(tmp_path)
            except OSError:
                # If unlink fails (file already gone, permission, ...),
                # log and move on — the file is in a temp directory and
                # the OS will reap it eventually.
                logger.warning(
                    "Could not remove tempfile {}; ignored.",
                    tmp_path,
                )


def _status_for_upload_error(exc: UploadError, message: str) -> int:
    """Map an :class:`UploadError` to its HTTP status code."""
    if exc.kind is UploadErrorKind.INVALID_PSEUDO:
        return status.HTTP_422_UNPROCESSABLE_CONTENT
    if exc.kind is UploadErrorKind.INVALID_FILE:
        return _map_invalid_file_to_status(message)
    if exc.kind is UploadErrorKind.OCR_FAILURE:
        return status.HTTP_422_UNPROCESSABLE_CONTENT
    if exc.kind is UploadErrorKind.STORAGE_FAILURE:
        return status.HTTP_500_INTERNAL_SERVER_ERROR
    # Defensive fallback — should never trigger.
    return status.HTTP_500_INTERNAL_SERVER_ERROR


__all__ = ["router"]
