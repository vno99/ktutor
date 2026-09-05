"""Factory for the evaluation service used by the evaluations API (s18).

Mirrors :mod:`app.api.documents.factory` — the FastAPI dependency
returns a fresh :class:`EvaluationService` per request, wired
against the live :class:`Settings`. Tests inject a stub via
``dependency_overrides`` so the real S3 / OCR / DB backends are
never touched in the suite.
"""

from __future__ import annotations

from app.core.config import Settings
from app.core.database import session as db_session
from app.services.ocr.evaluation_extractor import EvaluationExtractor, EvaluationService
from app.services.rag.ocr import MultimodalOcr
from app.services.storage.minio_client import MinioClient


def build_evaluation_service(settings: Settings) -> EvaluationService:
    """Build the :class:`EvaluationService` from the live :class:`Settings`."""
    s3_client = MinioClient(
        endpoint=settings.s3_endpoint,
        access_key=settings.s3_access_key,
        secret_key=settings.s3_secret_key,
        bucket=settings.s3_bucket,
    )
    ocr = MultimodalOcr(
        base_url=settings.deepseek_ocr_url,
        timeout=float(settings.deepseek_ocr_timeout),
    )
    extractor = EvaluationExtractor(ocr=ocr, settings=settings)
    return EvaluationService(
        s3_client=s3_client,
        extractor=extractor,
        session_factory=db_session.get_session_factory(),
        max_image_size_mb=settings.max_upload_size_mb,
    )


def get_evaluation_service_dep() -> EvaluationService:
    """FastAPI dependency that returns a fresh :class:`EvaluationService`."""
    return build_evaluation_service(Settings())


__all__ = ["build_evaluation_service", "get_evaluation_service_dep"]
