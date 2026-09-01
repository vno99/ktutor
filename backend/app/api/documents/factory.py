"""Factory for the upload service used by the documents API (s10).

Mirrors :func:`app.cli._build_service` (the CLI's wire-up) so the
HTTP path and the CLI path invoke the **same** :class:`UploadService`
contract (AC4). The differences are intentional and minimal:

* No ``s3_client.ensure_bucket()`` — the bucket is an operational
  concern that the CLI handles on its first command, not something an
  HTTP request should silently trigger per call.
* No ``db_session.init_db()`` — the FastAPI ``lifespan`` in
  ``app/main.py`` initializes the schema once at boot.
* ``Settings`` is a function parameter so the FastAPI dependency
  ``get_settings`` can inject it (and tests can override).

Tests inject :class:`app.services.rag.upload_service.UploadService`
stubs directly via FastAPI ``dependency_overrides`` on
:func:`get_upload_service_dep`, bypassing the factory altogether.
"""

from __future__ import annotations

from app.core.config import Settings
from app.core.database import session as db_session
from app.services.rag.chroma_store import ChromaStore
from app.services.rag.embeddings import build_embedding_provider
from app.services.rag.ingestion import DocumentIngestor
from app.services.rag.ocr import MultimodalOcr
from app.services.rag.upload_service import UploadService
from app.services.storage.minio_client import MinioClient


def build_upload_service(settings: Settings) -> UploadService:
    """Build the :class:`UploadService` from the live :class:`Settings`.

    Returns an instance wired against the real S3 / ChromaDB / OCR
    backends. Used by the FastAPI dependency in the router; tests
    override the dependency to inject fakes.
    """
    s3_client = MinioClient(
        endpoint=settings.s3_endpoint,
        access_key=settings.s3_access_key,
        secret_key=settings.s3_secret_key,
        bucket=settings.s3_bucket,
    )
    chroma = ChromaStore(persist_directory=settings.chroma_persist_directory)
    embeddings = build_embedding_provider(
        llm_provider=settings.llm_provider,
        openai_api_key=settings.openai_api_key,
    )
    ocr = MultimodalOcr(
        base_url=settings.deepseek_ocr_url,
        timeout=float(settings.deepseek_ocr_timeout),
    )
    return UploadService(
        s3_client=s3_client,
        chroma_store=chroma,
        embeddings=embeddings,
        ingestor=DocumentIngestor(),
        ocr=ocr,
        session_factory=db_session.get_session_factory(),
        max_upload_size_mb=settings.max_upload_size_mb,
    )


def get_upload_service_dep() -> UploadService:
    """FastAPI dependency that returns a fresh :class:`UploadService`.

    Returns a new instance per request (mirrors ``_build_supervisor_dep``
    in the chat router). Pooling is YAGNI at this scale.
    """
    return build_upload_service(Settings())


__all__ = ["build_upload_service", "get_upload_service_dep"]
