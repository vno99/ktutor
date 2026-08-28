"""MinIO / S3 client for storing uploaded source files.

Implements the multi-tenant key prefix ``students/<pseudo>/<document_id>``
(see ``docs/architecture.md`` § Multi-tenancy and ADR 007).
"""

from __future__ import annotations

import uuid
from io import BytesIO
from typing import Optional

from minio import Minio
from minio.error import S3Error


class MinioClient:
    """Thin wrapper around ``minio.Minio`` enforcing our key convention."""

    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        secure: bool = False,
    ) -> None:
        self._bucket = bucket
        self._client = Minio(
            endpoint=endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure,
        )

    def ensure_bucket(self) -> None:
        """Create the bucket if it does not exist; idempotent."""
        if not self._client.bucket_exists(self._bucket):
            self._client.make_bucket(self._bucket)

    def put_object(
        self,
        pseudo: str,
        document_id: uuid.UUID,
        filename: str,
        data: bytes,
    ) -> str:
        """Upload ``data`` under the per-student prefix and return the key.

        The returned key has the form ``students/<pseudo>/<document_id>`` and
        is the value persisted in the ``documents.minio_key`` column.
        """
        key = self._build_key(pseudo, document_id)
        self._client.put_object(
            bucket_name=self._bucket,
            object_name=key,
            data=BytesIO(data),
            length=len(data),
            content_type=_guess_content_type(filename),
        )
        return key

    def get_object(self, minio_key: str) -> bytes:
        """Read back the bytes stored at ``minio_key``."""
        response = None
        try:
            response = self._client.get_object(self._bucket, minio_key)
            return response.read()
        finally:
            if response is not None:
                response.close()
                response.release_conn()

    def remove_object(self, minio_key: str) -> None:
        """Delete an object. Silently ignores missing keys for idempotent rollback."""
        try:
            self._client.remove_object(self._bucket, minio_key)
        except S3Error as exc:
            if exc.code in {"NoSuchKey", "NoSuchObject"}:
                return
            raise

    @staticmethod
    def _build_key(pseudo: str, document_id: uuid.UUID) -> str:
        return f"students/{pseudo}/{document_id}"


def _guess_content_type(filename: str) -> str:
    """Best-effort MIME guess from the file extension (MinIO needs one)."""
    lower = filename.lower()
    if lower.endswith(".pdf"):
        return "application/pdf"
    if lower.endswith(".png"):
        return "image/png"
    if lower.endswith((".jpg", ".jpeg")):
        return "image/jpeg"
    if lower.endswith(".txt"):
        return "text/plain"
    return "application/octet-stream"
