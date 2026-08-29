"""Tests for the S3 client wrapper (SeaweedFS in local dev / CI).

We never connect to a real S3 here: the ``minio.Minio`` instance held by
``MinioClient`` is replaced with a ``FakeS3`` double. The contract we lock
in is the *key* (multi-tenant prefix) and the *calls* (idempotent bucket
create, exact put_object args, error-swallowing remove).
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest

from app.services.storage.minio_client import MinioClient


class FakeS3:
    """In-memory stand-in for ``minio.Minio`` covering the operations we use."""

    def __init__(self) -> None:
        self.buckets: set[str] = set()
        self.objects: dict[tuple[str, str], bytes] = {}
        self.put_calls: list[dict] = []
        self.remove_calls: list[tuple[str, str]] = []

    def bucket_exists(self, bucket: str) -> bool:
        return bucket in self.buckets

    def make_bucket(self, bucket: str) -> None:
        self.buckets.add(bucket)

    def put_object(self, bucket_name: str, object_name: str, data, length: int, content_type: str) -> None:
        payload = data.read() if hasattr(data, "read") else data
        self.objects[(bucket_name, object_name)] = payload
        self.put_calls.append(
            {
                "bucket": bucket_name,
                "key": object_name,
                "length": length,
                "content_type": content_type,
            }
        )

    def get_object(self, bucket: str, key: str):
        data = self.objects.get((bucket, key))
        if data is None:
            from minio.error import S3Error

            raise S3Error(None, "NoSuchKey", "no such key", bucket, key, "rid", "hid")
        resp = MagicMock()
        resp.read.return_value = data
        resp.close = MagicMock()
        resp.release_conn = MagicMock()
        return resp

    def remove_object(self, bucket: str, key: str) -> None:
        if (bucket, key) not in self.objects:
            from minio.error import S3Error

            raise S3Error(None, "NoSuchKey", "no such key", bucket, key, "rid", "hid")
        del self.objects[(bucket, key)]
        self.remove_calls.append((bucket, key))


@pytest.fixture()
def fake_s3() -> FakeS3:
    fake = FakeS3()
    MinioClient.__init__.__globals__["__builtins__"]  # sanity
    return fake


def _make_client(fake: FakeS3, bucket: str = "assistant-documents") -> MinioClient:
    client = MinioClient(
        endpoint="localhost:8333",
        access_key="k",
        secret_key="s",
        bucket=bucket,
    )
    # Swap the internal client (the constructor built a real one).
    client._client = fake  # type: ignore[attr-defined]
    return client


class TestEnsureBucket:
    def test_creates_bucket_if_missing(self, fake_s3: FakeS3) -> None:
        client = _make_client(fake_s3, bucket="bkt")
        assert "bkt" not in fake_s3.buckets
        client.ensure_bucket()
        assert "bkt" in fake_s3.buckets

    def test_is_idempotent(self, fake_s3: FakeS3) -> None:
        client = _make_client(fake_s3, bucket="bkt")
        client.ensure_bucket()
        # Second call should not raise even though the bucket already exists.
        client.ensure_bucket()
        assert "bkt" in fake_s3.buckets


class TestPutObject:
    def test_key_follows_students_pseudo_document_id_convention(self, fake_s3: FakeS3) -> None:
        client = _make_client(fake_s3)
        document_id = uuid.uuid4()
        key = client.put_object("ali", document_id, "cours.pdf", b"%PDF-1.4 fake")
        assert key == f"students/ali/{document_id}"
        assert fake_s3.objects[("assistant-documents", key)] == b"%PDF-1.4 fake"

    def test_content_type_inferred_from_extension(self, fake_s3: FakeS3) -> None:
        client = _make_client(fake_s3)
        document_id = uuid.uuid4()
        client.put_object("ali", document_id, "scan.png", b"\x89PNG fake")
        assert fake_s3.put_calls[-1]["content_type"] == "image/png"

        document_id_2 = uuid.uuid4()
        client.put_object("ali", document_id_2, "scan.jpg", b"\xff\xd8 fake")
        assert fake_s3.put_calls[-1]["content_type"] == "image/jpeg"

        document_id_3 = uuid.uuid4()
        client.put_object("ali", document_id_3, "doc.pdf", b"%PDF-1.4 fake")
        assert fake_s3.put_calls[-1]["content_type"] == "application/pdf"


class TestGetObject:
    def test_returns_bytes_for_existing_key(self, fake_s3: FakeS3) -> None:
        client = _make_client(fake_s3)
        document_id = uuid.uuid4()
        client.put_object("ali", document_id, "x.pdf", b"hello")
        assert client.get_object(f"students/ali/{document_id}") == b"hello"


class TestRemoveObject:
    def test_deletes_existing_key(self, fake_s3: FakeS3) -> None:
        client = _make_client(fake_s3)
        document_id = uuid.uuid4()
        client.put_object("ali", document_id, "x.pdf", b"hello")
        client.remove_object(f"students/ali/{document_id}")
        assert ("assistant-documents", f"students/ali/{document_id}") not in fake_s3.objects

    def test_missing_key_does_not_raise(self, fake_s3: FakeS3) -> None:
        client = _make_client(fake_s3)
        # Must not raise: allows idempotent rollback in UploadService.
        client.remove_object("students/ali/does-not-exist")
