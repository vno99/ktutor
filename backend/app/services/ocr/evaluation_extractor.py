"""Score-extraction pipeline for evaluation copies (s18).

This module owns two layers:

* :class:`EvaluationExtractor` — takes a :class:`MultimodalOcr` and
  extracts the score from the OCR transcript using a two-step
  strategy: a fast regex on the transcription, then a fallback on
  the structured JSON returned by the vision LLM (carried via
  :attr:`OcrResult.raw`). The output carries a ``source`` field so
  the caller can audit which path fired.
* :class:`EvaluationService` — orchestrates an upload: validate the
  file, push the bytes to S3, call the extractor, persist an
  :class:`Evaluation` row. Mirrors the contract of
  :class:`app.services.rag.upload_service.UploadService` (S3
  rollback on persistence failure, ``MANUAL_REVIEW_NEEDED`` as a
  successful HTTP outcome, etc.).

The two-state design (``SCORED`` / ``MANUAL_REVIEW_NEEDED``) is
recorded in ADR 013 — a copy is **always** persisted, the status
just reflects whether the score was extracted.
"""

from __future__ import annotations

import os
import re
import tempfile
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Literal, Protocol

from loguru import logger

from app.core.config import Settings
from app.core.database.models import Evaluation, EvaluationStatus, Subject
from app.services.rag.ocr import OcrError, OcrResult

# A canonical ``<n>/<m>`` pattern in the OCR text. Anchored on the
# slash so a stray ``12`` in the prose (e.g. ``élève a 12 ans``) is
# NOT picked up. The agentic notes flagged the false-positive risk;
# the LLM JSON is the safety net when the regex is ambiguous (s18b
# will add the manual review workflow for those cases).
SCORE_RE = re.compile(r"\b(\d+)\s*/\s*(\d+)\b")

ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}
"""Image-only extensions for s18. The ``documents`` endpoint accepts
more (PDF, TXT); evaluations are photo-only per the AC1 contract."""


# ---------------------------------------------------------------------------
# Custom prompt for the multimodal LLM. s18 elicits a JSON envelope
# that carries the score AND the natural-language transcription (the
# regex needs the natural text, not the structured fields). The
# prompt is intentionally strict — we tell the LLM to return ``null``
# rather than guess a score (Piège 3 of the research).
# ---------------------------------------------------------------------------

EVALUATION_PROMPT = (
    "Analyse cette photo de copie d'évaluation corrigée par un enseignant. "
    "Renvoie UNIQUEMENT un objet JSON strict avec les clés: "
    'score (number|null — la note sur le barème, jamais inventée si absente), '
    "max_score (number|null — le barème, ex: 20 pour /20), "
    "annotations (list[string] — annotations courtes de l'enseignant, [] si aucune), "
    "teacher_comments (string|null — commentaire global, null si absent), "
    "ocr_text (string — la transcription littérale du texte de la copie), "
    "ocr_confidence (float entre 0 et 1). "
    "Si aucun score n'est lisible, NE DEVINE PAS — réponds null pour score ET max_score."
)


@dataclass(frozen=True)
class ExtractionResult:
    """Outcome of one score-extraction attempt.

    ``source`` discriminates the path that produced the score:

    * ``"regex"`` — a ``<n>/<m>`` pattern was found in the OCR
      transcript (fast path, no LLM JSON consulted).
    * ``"llm"`` — the regex missed; the LLM JSON envelope carried a
      non-null score (fallback).
    * ``"none"`` — neither source produced a score; the caller maps
      this to ``MANUAL_REVIEW_NEEDED``.
    """

    score: float | None
    max_score: float | None
    annotations: list[str]
    teacher_comments: str | None
    ocr_text: str
    ocr_confidence: float | None
    source: Literal["regex", "llm", "none"]


class EvaluationExtractionError(RuntimeError):
    """Raised when the OCR transport itself is unavailable.

    The router maps this to HTTP 500. Distinct from
    :class:`EvaluationError` (which carries a kind enum for the
    validation / storage / extraction distinction at the service
    layer).
    """


class _OcrLike(Protocol):
    """Structural type for the OCR client — kept loose so the
    service tests can plug in a :class:`MultimodalOcr` or a
    hand-rolled double without subclassing.
    """

    def transcribe_image(
        self, image_path: str, prompt: str | None = None
    ) -> OcrResult: ...


class EvaluationExtractor:
    """Run the dual-source score extraction on a single evaluation copy.

    The extractor is stateless across calls; instances are cheap to
    create and safe to share. The constructor takes a
    :class:`MultimodalOcr` (or any compatible double) and a
    :class:`Settings` reference (kept for symmetry with the
    :class:`EvaluationService` even though the extractor itself
    does not read any setting).
    """

    def __init__(self, *, ocr: _OcrLike, settings: Settings) -> None:
        self._ocr = ocr
        self._settings = settings

    def extract(self, image_path: str) -> ExtractionResult:
        """Run OCR + dual-source score extraction on one image.

        The extraction is synchronous — the upload is one HTTP
        call to DeepSeek-OCR-2 (ADR 008, ~50-200 ms locally).

        Raises:
            EvaluationExtractionError: when the OCR transport itself
                raises (network down, malformed JSON, etc.). The
                ``EvaluationService`` rolls back the S3 push and
                re-raises as :class:`EvaluationError` of kind
                ``EXTRACTION_FAILURE``.
        """
        try:
            ocr_result: OcrResult = self._ocr.transcribe_image(
                image_path, prompt=EVALUATION_PROMPT
            )
        except OcrError as exc:
            raise EvaluationExtractionError(str(exc)) from exc

        if not ocr_result.ok:
            return ExtractionResult(
                score=None,
                max_score=None,
                annotations=[],
                teacher_comments=None,
                ocr_text=ocr_result.transcription,
                ocr_confidence=ocr_result.confidence,
                source="none",
            )

        # Step 1 — regex fast path on the OCR transcript.
        match = SCORE_RE.search(ocr_result.transcription)
        if match is not None:
            score = float(match.group(1))
            max_score = float(match.group(2))
            annotations, teacher_comments = _extract_llm_extras(ocr_result)
            return ExtractionResult(
                score=score,
                max_score=max_score,
                annotations=annotations,
                teacher_comments=teacher_comments,
                ocr_text=ocr_result.transcription,
                ocr_confidence=ocr_result.confidence,
                source="regex",
            )

        # Step 2 — LLM JSON fallback. The vision LLM's structured
        # payload lives in :attr:`OcrResult.raw`; we read the
        # score / max_score from there. A null score in the JSON
        # means the LLM confirmed there is no readable score on
        # the page — we honour the verdict and return ``none``.
        llm_score, llm_max_score = _read_llm_score(ocr_result)
        if llm_score is not None:
            annotations, teacher_comments = _extract_llm_extras(ocr_result)
            return ExtractionResult(
                score=llm_score,
                max_score=llm_max_score,
                annotations=annotations,
                teacher_comments=teacher_comments,
                ocr_text=ocr_result.transcription,
                ocr_confidence=ocr_result.confidence,
                source="llm",
            )

        # No regex, no LLM JSON score — the row is persisted with
        # ``status=MANUAL_REVIEW_NEEDED``.
        annotations, teacher_comments = _extract_llm_extras(ocr_result)
        return ExtractionResult(
            score=None,
            max_score=None,
            annotations=annotations,
            teacher_comments=teacher_comments,
            ocr_text=ocr_result.transcription,
            ocr_confidence=ocr_result.confidence,
            source="none",
        )


# ---------------------------------------------------------------------------
# Service layer — orchestrates S3 push + extraction + DB row.
# ---------------------------------------------------------------------------


class EvaluationErrorKind(str, Enum):
    """Failure modes the service distinguishes.

    Mirror of :class:`app.services.rag.upload_service.UploadErrorKind`
    so the router can apply the same mapping table.
    """

    INVALID_FILE = "invalid_file"
    STORAGE_FAILURE = "storage_failure"
    EXTRACTION_FAILURE = "extraction_failure"


class EvaluationError(Exception):
    """Controlled failure raised by :class:`EvaluationService.upload`.

    The ``kind`` enum lets the router map to stable HTTP status codes
    (INVALID_FILE → 415 / 413, EXTRACTION_FAILURE → 422,
    STORAGE_FAILURE → 500) without parsing the human message.
    """

    def __init__(self, kind: EvaluationErrorKind, message: str) -> None:
        super().__init__(message)
        self.kind = kind


class EvaluationStateError(Exception):
    """State-transition failure raised by :class:`EvaluationService`.

    Distinct from :class:`EvaluationError` (which carries a ``kind``
    enum for upload failures). The router maps the message substring
    to a status code:

    * ``"not_found"`` → 404
    * otherwise → 409 ``state_conflict`` (the row is in a state that
      does not allow the requested transition — e.g. attempting to
      score-manual a SCORED row, or to reprocess a SCORED row).

    The error has no kind enum on purpose — the message IS the kind,
    the two values above are the only ones the router ever emits.
    A future ``EvaluationStateError`` subclass with a discriminator
    is preferable to extending the message vocabulary.
    """


class _S3Like(Protocol):
    def put_object(
        self,
        *,
        pseudo: str,
        document_id: uuid.UUID,
        filename: str,
        data: bytes,
    ) -> str: ...

    def get_object(self, minio_key: str) -> bytes: ...

    def remove_object(self, key: str) -> None: ...


class _SessionLike(Protocol):
    def add(self, obj: Any) -> None: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...
    def get(self, entity: type, pk: Any) -> Any: ...
    def refresh(self, obj: Any) -> None: ...


@dataclass
class EvaluationUploadResult:
    """Outcome of a successful upload (HTTP 201 target)."""

    evaluation_id: uuid.UUID
    status: EvaluationStatus
    score: float | None
    max_score: float | None
    s3_key: str
    duration_ms: int
    ocr_confidence: float | None = None
    annotations: list[str] | None = None
    teacher_comments: str | None = None


@dataclass
class EvaluationReprocessResult:
    """Outcome of a successful reprocess.

    Carries the refreshed :class:`Evaluation` row, the
    :class:`ExtractionResult` produced by the LLM vision pass, and
    the row's status *before* the reprocess (so the router can
    emit an audit log carrying the transition).
    """

    evaluation: Evaluation
    extraction: ExtractionResult
    previous_status: EvaluationStatus


class EvaluationService:
    """Orchestrate one evaluation copy upload (s18).

    The contract mirrors :class:`app.services.rag.upload_service
    .UploadService`:

    * validate the file (extension, size) up-front — fail fast
      without touching S3;
    * push the bytes to S3 (key: ``students/<pseudo>/<id>``);
    * run the score extraction;
    * persist a single :class:`Evaluation` row;
    * roll back the S3 object on any failure past the S3 push
      (AC4 — "persistance rien à moitié").
    """

    def __init__(
        self,
        *,
        s3_client: _S3Like,
        extractor: EvaluationExtractor,
        session_factory: Callable[[], _SessionLike] | None = None,
        max_image_size_mb: int = 20,
    ) -> None:
        self._s3 = s3_client
        self._extractor = extractor
        self._session_factory = session_factory
        self._max_bytes = max_image_size_mb * 1024 * 1024

    def upload(
        self,
        *,
        file_path: str,
        pseudo: str,
        subject: str,
    ) -> EvaluationUploadResult:
        """Run the full pipeline. Raises :class:`EvaluationError` on
        any controlled failure."""
        started = time.monotonic()
        path = Path(file_path)
        if not path.exists() or path.suffix.lower() not in ALLOWED_IMAGE_EXTENSIONS:
            raise EvaluationError(
                EvaluationErrorKind.INVALID_FILE,
                f"Fichier invalide: extension {path.suffix!r} non supportée",
            )
        size = path.stat().st_size
        if size > self._max_bytes:
            raise EvaluationError(
                EvaluationErrorKind.INVALID_FILE,
                f"Taille {size / (1024 * 1024):.1f} Mo supérieure à la limite "
                f"({self._max_bytes // (1024 * 1024)} Mo)",
            )

        evaluation_id = uuid.uuid4()
        # Step 1 — push to S3 first; everything past this point
        # must roll back on failure (AC4).
        try:
            s3_key = self._s3.put_object(
                pseudo=pseudo,
                document_id=evaluation_id,
                filename=path.name,
                data=path.read_bytes(),
            )
        except Exception as exc:
            raise EvaluationError(
                EvaluationErrorKind.STORAGE_FAILURE, f"S3 put_object: {exc}"
            ) from exc

        # Step 2 — extract the score (synchronous; one HTTP call).
        try:
            result = self._extractor.extract(file_path)
        except EvaluationExtractionError as exc:
            self._s3.remove_object(s3_key)
            raise EvaluationError(
                EvaluationErrorKind.EXTRACTION_FAILURE, str(exc)
            ) from exc

        # Step 3 — persist the row. A DB failure past the S3 push
        # must roll back the object (AC4) so the bucket stays
        # consistent with the DB.
        status = (
            EvaluationStatus.SCORED
            if result.score is not None
            else EvaluationStatus.MANUAL_REVIEW_NEEDED
        )
        error_reason: str | None = None
        if status is EvaluationStatus.MANUAL_REVIEW_NEEDED:
            error_reason = (
                "no_score_in_transcript" if not result.ocr_text
                else "no_score_extracted"
            )

        try:
            self._persist(
                evaluation_id=evaluation_id,
                pseudo=pseudo,
                subject=subject,
                filename=path.name,
                s3_key=s3_key,
                status=status,
                score=result.score,
                max_score=result.max_score,
                annotations=result.annotations,
                teacher_comments=result.teacher_comments,
                ocr_text=result.ocr_text,
                ocr_confidence=result.ocr_confidence,
                error_reason=error_reason,
            )
        except Exception as exc:
            self._s3.remove_object(s3_key)
            raise EvaluationError(
                EvaluationErrorKind.STORAGE_FAILURE, f"DB persist: {exc}"
            ) from exc

        return EvaluationUploadResult(
            evaluation_id=evaluation_id,
            status=status,
            score=result.score,
            max_score=result.max_score,
            s3_key=s3_key,
            duration_ms=_ms_since(started),
            ocr_confidence=result.ocr_confidence,
            annotations=result.annotations,
            teacher_comments=result.teacher_comments,
        )

    def _persist(
        self,
        *,
        evaluation_id: uuid.UUID,
        pseudo: str,
        subject: str,
        filename: str,
        s3_key: str,
        status: EvaluationStatus,
        score: float | None,
        max_score: float | None,
        annotations: list[str],
        teacher_comments: str | None,
        ocr_text: str,
        ocr_confidence: float | None,
        error_reason: str | None,
    ) -> None:
        if self._session_factory is None:
            return
        session = self._session_factory()
        session.add(
            Evaluation(
                id=evaluation_id,
                student_pseudo=pseudo,
                subject=Subject(subject),
                s3_key=s3_key,
                filename=filename,
                status=status,
                score=score,
                max_score=max_score,
                annotations=annotations,
                teacher_comments=teacher_comments,
                ocr_text=ocr_text,
                ocr_confidence=ocr_confidence,
                error_reason=error_reason,
            )
        )
        session.commit()

    # -------------------------------------------------------------------
    # s18b — manual score entry and reprocess workflows.
    # -------------------------------------------------------------------

    def score_manual(
        self,
        *,
        evaluation_id: uuid.UUID,
        score: float,
        max_score: float,
        teacher_comments: str | None = None,
    ) -> Evaluation:
        """Persist a manually-entered score on a MANUAL_REVIEW_NEEDED row.

        The router has already validated the body bounds (Pydantic, 422
        on miss). The service is responsible for the state transition
        (AC2 → 409 ``state_conflict`` if the row is not
        ``MANUAL_REVIEW_NEEDED``, AC1 → 404 ``not_found`` if the row
        is missing).

        Returns the refreshed :class:`Evaluation` row. The audit log
        (carrying the **caller** pseudo) is emitted at the router
        layer so the service stays unaware of the JWT identity.
        """
        session = self._session_factory()
        row = session.get(Evaluation, evaluation_id)
        if row is None:
            raise EvaluationStateError("not_found")
        if row.status is not EvaluationStatus.MANUAL_REVIEW_NEEDED:
            raise EvaluationStateError(
                f"evaluation already scored (status={row.status.value!r}); "
                "score-manual only accepts rows in 'manual_review_needed'"
            )
        row.score = score
        row.max_score = max_score
        row.teacher_comments = teacher_comments
        row.error_reason = None
        row.status = EvaluationStatus.SCORED
        session.commit()
        session.refresh(row)
        return row

    def reprocess(
        self, *, evaluation_id: uuid.UUID
    ) -> EvaluationReprocessResult:
        """Re-run the LLM vision extractor on the original image.

        The original S3 object is downloaded to a tempfile, the
        extractor is invoked (synchronous, ~50-200 ms), and the row
        is updated with the new :class:`ExtractionResult`. The state
        transition is the same as :meth:`upload`:

        * score present → ``SCORED`` (the new score replaces the
          previous one — same row, no history column, Piège 3
          audit lives in loguru)
        * score absent → ``MANUAL_REVIEW_NEEDED`` (preserved)
        * row already ``SCORED`` → 409 (re-scorer une copie déjà
          scorée n'a pas de sens — recherche Piège 4)
        * row missing → 404

        Returns an :class:`EvaluationReprocessResult` carrying the
        refreshed row, the :class:`ExtractionResult`, and the
        ``previous_status`` so the router can emit an audit log
        carrying the transition. The audit log itself is emitted at
        the router layer (the service does not know the caller).
        """
        session = self._session_factory()
        row = session.get(Evaluation, evaluation_id)
        if row is None:
            raise EvaluationStateError("not_found")
        if row.status is EvaluationStatus.SCORED:
            raise EvaluationStateError(
                f"evaluation already scored (status={row.status.value!r}); "
                "reprocess is reserved for 'manual_review_needed' rows"
            )

        previous_status = row.status

        # Pull the original image bytes from S3, write to a tempfile,
        # invoke the extractor, unlink in `finally`. The tempfile
        # survives the function call (delete=False) so the extractor
        # can read from disk.
        image_bytes = self._s3.get_object(row.s3_key)
        suffix = Path(row.filename).suffix or ".png"
        tmp = tempfile.NamedTemporaryFile(  # noqa: SIM115 - see comment below
            prefix="ktutor-eval-reprocess-",
            suffix=suffix,
            delete=False,
        )
        tmp.write(image_bytes)
        tmp.close()
        tmp_path: str | None = None
        try:
            tmp_path = tmp.name
            # The OCR transport is down — the row stays in
            # MANUAL_REVIEW_NEEDED (its existing state); nothing
            # was changed. The router maps this to 500.
            result = self._extractor.extract(tmp_path)
            new_status = (
                EvaluationStatus.SCORED
                if result.score is not None
                else EvaluationStatus.MANUAL_REVIEW_NEEDED
            )
            new_error_reason: str | None = None
            if new_status is EvaluationStatus.MANUAL_REVIEW_NEEDED:
                new_error_reason = (
                    "no_score_in_transcript" if not result.ocr_text
                    else "no_score_extracted"
                )
            row.score = result.score
            row.max_score = result.max_score
            row.annotations = result.annotations or None
            row.teacher_comments = result.teacher_comments
            row.ocr_text = result.ocr_text
            row.ocr_confidence = result.ocr_confidence
            row.status = new_status
            row.error_reason = new_error_reason
            session.commit()
            session.refresh(row)
            return EvaluationReprocessResult(
                evaluation=row,
                extraction=result,
                previous_status=previous_status,
            )
        finally:
            if tmp_path is not None:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    logger.warning(
                        "Could not remove reprocess tempfile {}; ignored.",
                        tmp_path,
                    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_llm_score(ocr_result: OcrResult) -> tuple[float | None, float | None]:
    """Read the score / max_score from the LLM JSON envelope.

    Returns ``(None, None)`` when the envelope is missing or the
    score field is ``None`` / absent — the caller treats this as
    "the LLM could not extract a score".
    """
    raw = ocr_result.raw or {}
    score = raw.get("score")
    max_score = raw.get("max_score")
    if score is None:
        return None, None
    try:
        score_f = float(score)
    except (TypeError, ValueError):
        return None, None
    if max_score is None:
        return score_f, None
    try:
        return score_f, float(max_score)
    except (TypeError, ValueError):
        return score_f, None


def _extract_llm_extras(ocr_result: OcrResult) -> tuple[list[str], str | None]:
    """Read the annotations / teacher_comments from the LLM envelope.

    Both fields are best-effort: missing keys yield ``([], None)``,
    malformed values are dropped (never raised — the LLM is not
    trusted for these fields).
    """
    raw = ocr_result.raw or {}
    annotations_raw = raw.get("annotations") or []
    annotations: list[str] = []
    if isinstance(annotations_raw, list):
        for item in annotations_raw:
            if isinstance(item, str) and item:
                annotations.append(item)
    teacher_comments = raw.get("teacher_comments")
    if teacher_comments is not None and not isinstance(teacher_comments, str):
        teacher_comments = None
    return annotations, teacher_comments


def _ms_since(start: float) -> int:
    return int((time.monotonic() - start) * 1000)


__all__ = [
    "ALLOWED_IMAGE_EXTENSIONS",
    "EVALUATION_PROMPT",
    "SCORE_RE",
    "EvaluationError",
    "EvaluationErrorKind",
    "EvaluationExtractionError",
    "EvaluationExtractor",
    "EvaluationReprocessResult",
    "EvaluationService",
    "EvaluationStateError",
    "EvaluationUploadResult",
    "ExtractionResult",
]
