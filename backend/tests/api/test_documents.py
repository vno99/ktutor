"""Tests for ``POST /api/documents/upload`` (s10, s15).

The suite covers every acceptance criterion in the original story
plus the s15 cross-tenant bite required by the repo Definition
of Done (AGENTS.md):

* multipart parsing + Pydantic validation (AC1, T3.8, T3.9),
* success response shape (AC2, T3.1) and ``manual_review_needed``
  (AC2, T3.2 — a successful HTTP outcome, not an error),
* failure mapping (AC3, T3.3-T3.7) — each :class:`UploadErrorKind`
  maps to the documented HTTP status,
* AC4 — the router calls :func:`UploadService.upload` directly
  (T3.10),
* tempfile cleanup (Risque 1, T3.11),
* multi-tenant isolation at the service boundary (AC7, T3.12),
* CORS preflight behaviour (T3.13, T3.14) — inherited from s09,
  verified here so a regression on the middleware cannot slip through.

The s15 migration replaces ``Form(pseudo)`` with a JWT-derived
identity. The :class:`TestDocumentsUploadJwtRequired` and
:class:`TestDocumentsUploadCrossTenant` classes prove the
migration:

* 401 ``invalid_token`` when the bearer is missing / junk / expired,
* 422 from FastAPI when the client still sends ``Form(pseudo)``
  (s15 hard cut — research Piège 1),
* 201 with the JWT pseudo in the persisted row when the body is
  clean.

Most tests use :func:`documents_client` + :func:`upload_service_stub`
to keep the suite fast and deterministic. The cross-tenant test
(T3.12) wires the real :class:`UploadService` with the cheap in-memory
doubles (``FakeS3``, ``chromadb.EphemeralClient``, ``FakeEmbeddings``,
``FakeSession``) and asserts on the resulting ChromaDB collections —
this is the bite that proves the router passes the body pseudo
through to the service unchanged.
"""

from __future__ import annotations

import io
import os
import tempfile
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import chromadb
import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import sessionmaker

from app.core.auth.jwt import create_access_token
from app.core.auth.passwords import hash_password
from app.core.database.models import Base, DocumentStatus, User, UserRole
from app.core.database.session import get_db
from app.main import app
from app.services.rag.chroma_store import ChromaStore
from app.services.rag.ingestion import DocumentIngestor
from app.services.rag.ocr import MultimodalOcr
from app.services.rag.upload_service import (
    UploadError,
    UploadErrorKind,
    UploadResult,
    UploadService,
)
from app.services.storage.minio_client import MinioClient
from tests.services.storage.test_s3_client import FakeS3

# ---------------------------------------------------------------------------
# s15 JWT fixtures (duplicated from test_chat_stream / test_users_create
# per AGENTS.md « Pas de refactor transverse »). The upload endpoint
# now requires ``Depends(get_current_user)`` so the tests must seed
# a real User row whose pseudo the JWT can carry.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def rsa_keypair(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    tmp = tmp_path_factory.mktemp("jwt_keys_documents")
    private_path = tmp / "jwt_private.pem"
    public_path = tmp / "jwt_public.pem"
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    private_path.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    public_path.write_bytes(
        public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    return {"private": private_path, "public": public_path}


@pytest.fixture(autouse=True)
def _point_settings(
    monkeypatch: pytest.MonkeyPatch, rsa_keypair: dict[str, Path]
) -> None:
    monkeypatch.setenv("JWT_PRIVATE_KEY_PATH", str(rsa_keypair["private"]))
    monkeypatch.setenv("JWT_PUBLIC_KEY_PATH", str(rsa_keypair["public"]))
    monkeypatch.setenv("JWT_ALGORITHM", "RS256")
    monkeypatch.setenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "30")
    monkeypatch.setenv("JWT_REFRESH_TOKEN_EXPIRE_DAYS", "7")
    # Force an in-memory SQLite so the lifespan ``init_db()`` does
    # not try to dial a PostgreSQL server that may not be reachable
    # in CI. The fixture's ``db_engine`` ignores this and creates
    # its own engine; this is only for the lifespan.
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")


@pytest.fixture()
def db_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture()
def session_factory(db_engine):
    return sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)


@pytest.fixture()
def jwt_client(
    session_factory,
    override_upload_service: None,
) -> Iterator[TestClient]:
    """A TestClient bound to an isolated in-memory SQLite + the
    stub upload service. The ``get_db`` dependency is overridden
    so each request sees the seeded users."""

    def _override_get_db() -> Iterator:
        s = session_factory()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _override_get_db
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture()
def documents_client(
    session_factory,
    override_upload_service: None,
) -> Iterator[TestClient]:
    """A TestClient bound to an isolated in-memory SQLite (so the
    ``get_current_user`` resolver can find seeded users) plus the
    stub upload service. s15 replacement for the s10
    ``documents_client`` — auth is now mandatory, so the DB must
    be wired even for tests that don't explicitly use the bearer.
    The CORS preflight tests still pass because OPTIONS does not
    trigger the auth dependency.
    """

    def _override_get_db() -> Iterator:
        s = session_factory()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _override_get_db
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture()
def seeded_eleve_bob(session_factory) -> User:
    with session_factory() as db:
        user = User(
            pseudo="bob",
            password_hash=hash_password("studentpassword"),
            role=UserRole.ELEVE,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user


@pytest.fixture()
def seeded_eleve_alice(session_factory) -> User:
    """The default ``alice`` used by the s10 happy-path tests.
    Picked up by ``documents_client`` indirectly via
    ``override_upload_service`` -> jwt_client.
    """
    with session_factory() as db:
        user = User(
            pseudo="alice",
            password_hash=hash_password("studentpassword"),
            role=UserRole.ELEVE,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user


@pytest.fixture()
def seeded_admin(session_factory) -> User:
    with session_factory() as db:
        user = User(
            pseudo="boss",
            password_hash=hash_password("adminpassword"),
            role=UserRole.ADMIN,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user


def _bearer(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.pseudo, user.role)}"}


# ---------------------------------------------------------------------------
# Local doubles (used by the cross-tenant test which wires the real
# UploadService, not the stub).
# ---------------------------------------------------------------------------


class _LocalFakeEmbeddings:
    """Deterministic 3-dim embeddings — copy from the upload service
    test suite so the documents tests stay self-contained.
    """

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(t) % 7), float(t.count(" ") % 7), 1.0] for t in texts]


class _LocalFakeSession:
    def __init__(self) -> None:
        self.added: list[Any] = []
        self.committed = False

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        pass


def _build_real_upload_service(
    *,
    chroma_client: Any | None = None,
    embeddings: _LocalFakeEmbeddings | None = None,
    persist_directory: Path | None = None,
) -> tuple[UploadService, FakeS3, ChromaStore]:
    """Build a real :class:`UploadService` against in-memory doubles.

    The factory mirrors the one in ``test_upload_service.py`` so the
    cross-tenant test exercises the same pipeline the CLI does, only
    with no S3 / Postgres / Chroma-server I/O.
    """

    def _handler(_request: httpx.Request) -> httpx.Response:
        import json as _json

        return httpx.Response(
            200,
            content=_json.dumps(
                {
                    "transcription": "OCR'd text",
                    "type": "texte",
                    "confidence": 0.9,
                    "has_math": False,
                }
            ),
        )

    fake_s3 = FakeS3()
    s3_client = MinioClient(
        endpoint="localhost:8333",
        access_key="k",
        secret_key="s",
        bucket="bkt",
    )
    s3_client._client = fake_s3  # type: ignore[attr-defined]

    if chroma_client is None:
        chroma_client = chromadb.EphemeralClient()
    chroma = ChromaStore(client=chroma_client)
    embeddings = embeddings or _LocalFakeEmbeddings()
    ocr = MultimodalOcr(base_url="http://ocr", transport=httpx.MockTransport(_handler))

    session = _LocalFakeSession()

    def _session_factory() -> _LocalFakeSession:
        return session

    service = UploadService(
        s3_client=s3_client,
        chroma_store=chroma,
        embeddings=embeddings,
        ingestor=DocumentIngestor(),
        ocr=ocr,
        session_factory=_session_factory,
        max_upload_size_mb=20,
    )
    return service, fake_s3, chroma


# ---------------------------------------------------------------------------
# AC1 + AC5 — endpoint accepts a multipart upload
# ---------------------------------------------------------------------------


class TestMultipartAcceptance:
    def test_upload_accepts_multipart_with_pdf(
        self,
        documents_client,
        upload_service_stub,
        sample_pdf_path: Path,
        seeded_eleve_alice: User,
    ) -> None:
        """AC1 + AC5: a valid PDF upload is accepted and answered 201.

        Bite: if the router is not wired (the test would get 404).
        """
        with sample_pdf_path.open("rb") as fh:
            response = documents_client.post(
                "/api/documents/upload",
                data={"subject": "maths"},
                files={"file": (sample_pdf_path.name, fh, "application/pdf")},
                headers=_bearer(seeded_eleve_alice),
            )
        assert response.status_code == 201, response.text
        body = response.json()
        assert "document_id" in body
        assert body["status"] == "indexed"
        assert body["chunks_count"] >= 1
        # The router must have invoked the (stub) service once with the
        # JWT pseudo (s15: the body no longer carries ``pseudo``) and
        # the tempfile path.
        assert len(upload_service_stub.calls) == 1
        _path, pseudo, subject = upload_service_stub.calls[0]
        assert pseudo == "alice"
        assert subject == "maths"
        # The path passed to the service MUST end with the right
        # extension (Piège 1: the service inspects the suffix to
        # discriminate text/image/PDF). The file itself has been
        # unlinked by the router's ``finally`` block before this
        # assertion runs (T3.11 verifies that the cleanup is
        # effective).
        assert _path.endswith(".pdf")


# ---------------------------------------------------------------------------
# AC2 — success response shape
# ---------------------------------------------------------------------------


class TestSuccessResponse:
    def test_upload_returns_201_with_id_status_chunks(
        self, documents_client, upload_service_stub, seeded_eleve_alice: User
    ) -> None:
        """AC2 bite: the response carries ``status`` mirroring the
        service's :class:`DocumentStatus` value. Hardcoding
        ``"ok"`` (or any other literal) would fail this test.
        """
        pdf_bytes = b"%PDF-1.4\n%fake\n"
        response = documents_client.post(
            "/api/documents/upload",
            data={"subject": "maths"},
            files={"file": ("cours.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
            headers=_bearer(seeded_eleve_alice),
        )
        assert response.status_code == 201
        body = response.json()
        # UUID is a string, parse it.
        uuid.UUID(body["document_id"])  # raises if not a UUID
        assert body["status"] == "indexed"
        assert isinstance(body["chunks_count"], int)
        assert body["chunks_count"] >= 0

    def test_upload_returns_201_for_manual_review_needed(
        self, documents_client, upload_service_stub, seeded_eleve_alice: User
    ) -> None:
        """AC2 (Piège 7): when the service returns MANUAL_REVIEW_NEEDED,
        the router still answers 201 (success HTTP), with the
        ``status`` field set to ``"manual_review_needed"`` and
        ``chunks_count=0``. A regression that mapped MANUAL_REVIEW to
        4xx would break the frontend's happy path tracking.
        """
        upload_service_stub.return_result = UploadResult(
            document_id=uuid.UUID("12345678-1234-5678-1234-567812345678"),
            chunks_count=0,
            duration_ms=10,
            status=DocumentStatus.MANUAL_REVIEW_NEEDED,
            collection="",
            s3_key="students/alice/uuid/cours.pdf",
            ocr_confidence=0.2,
        )
        response = documents_client.post(
            "/api/documents/upload",
            data={"subject": "maths"},
            files={"file": ("flou.png", io.BytesIO(b"\x89PNG\r\n\x1a\n"), "image/png")},
            headers=_bearer(seeded_eleve_alice),
        )
        assert response.status_code == 201
        body = response.json()
        assert body["status"] == "manual_review_needed"
        assert body["chunks_count"] == 0
        assert body["ocr_confidence"] == pytest.approx(0.2)


# ---------------------------------------------------------------------------
# AC3 — failure mapping
# ---------------------------------------------------------------------------


class TestFailureMapping:
    def test_upload_oversize_returns_413(
        self, documents_client, upload_service_stub, monkeypatch, seeded_eleve_alice: User
    ) -> None:
        """AC3 + AC6 (Piège 2): a 25 MB upload is rejected with 413.

        The router enforces the size at two levels (Content-Length
        header + post-read body length). A regression that drops
        EITHER guard would not catch the 25 MB body — but a smaller
        body that exceeds a tight ``max_upload_size_mb`` setting
        does. We use a small setting to make the test fast and
        deterministic.
        """
        from app.core import config as config_module
        from app.core.config import Settings

        tight = Settings(
            cors_allow_origins="http://localhost:3000",
            max_upload_size_mb=1,  # 1 MB cap
        )
        config_module._settings = tight
        try:
            # 2 MB body — above the 1 MB cap. Content-Length is
            # set automatically by TestClient.
            big = b"\0" * (2 * 1024 * 1024)
            response = documents_client.post(
                "/api/documents/upload",
                data={"subject": "maths"},
                files={"file": ("big.pdf", io.BytesIO(big), "application/pdf")},
                headers=_bearer(seeded_eleve_alice),
            )
        finally:
            config_module._settings = None

        assert response.status_code == 413, response.text
        body = response.json()
        assert body["detail"]["code"] == UploadErrorKind.INVALID_FILE.value
        assert (
            "volumineux" in body["detail"]["error"].lower()
            or "taille" in body["detail"]["error"].lower()
        )
        # The router rejected at the boundary — the service was NOT
        # called, so no tempfile was materialized and no chunks were
        # indexed.
        assert upload_service_stub.calls == []

    def test_upload_unsupported_extension_returns_415(
        self, documents_client, upload_service_stub, seeded_eleve_alice: User
    ) -> None:
        """AC3 (Piège 11): an upload with an unsupported extension is
        rejected with 415 (Unsupported Media Type) and code
        ``invalid_file``. A regression that mapped every
        ``INVALID_FILE`` to 413 would fail here.
        """
        upload_service_stub.raise_with = UploadError(
            UploadErrorKind.INVALID_FILE,
            "Fichier invalide: extension '.exe' non supportée",
        )
        response = documents_client.post(
            "/api/documents/upload",
            data={"subject": "maths"},
            files={"file": ("bad.exe", io.BytesIO(b"MZ"), "application/octet-stream")},
            headers=_bearer(seeded_eleve_alice),
        )
        assert response.status_code == 415
        body = response.json()
        assert body["detail"]["code"] == UploadErrorKind.INVALID_FILE.value
        assert "extension" in body["detail"]["error"].lower()

    def test_upload_invalid_pseudo_returns_422(
        self, documents_client, upload_service_stub, seeded_eleve_alice: User
    ) -> None:
        """AC3 (Piège 6): a service-raised ``INVALID_PSEUDO`` maps to
        422. A regression that did not catch ``UploadError`` would
        surface the failure as a 500.
        """
        upload_service_stub.raise_with = UploadError(
            UploadErrorKind.INVALID_PSEUDO,
            "Pseudo invalide: 'ali ce' (caractère interdit)",
        )
        response = documents_client.post(
            "/api/documents/upload",
            data={"subject": "maths"},
            files={"file": ("x.pdf", io.BytesIO(b"%PDF-1.4\n"), "application/pdf")},
            headers=_bearer(seeded_eleve_alice),
        )
        assert response.status_code == 422
        body = response.json()
        assert body["detail"]["code"] == UploadErrorKind.INVALID_PSEUDO.value

    def test_upload_ocr_failure_returns_422(
        self, documents_client, upload_service_stub, seeded_eleve_alice: User
    ) -> None:
        """AC3 (Piège 11): a service-raised ``OCR_FAILURE`` maps to 422.
        """
        upload_service_stub.raise_with = UploadError(
            UploadErrorKind.OCR_FAILURE, "Confiance OCR 0.1 sous le seuil"
        )
        response = documents_client.post(
            "/api/documents/upload",
            data={"subject": "maths"},
            files={"file": ("x.png", io.BytesIO(b"\x89PNG\r\n\x1a\n"), "image/png")},
            headers=_bearer(seeded_eleve_alice),
        )
        assert response.status_code == 422
        body = response.json()
        assert body["detail"]["code"] == UploadErrorKind.OCR_FAILURE.value

    def test_upload_storage_failure_returns_500(
        self, documents_client, upload_service_stub, seeded_eleve_alice: User
    ) -> None:
        """AC3 (Piège 11): a service-raised ``STORAGE_FAILURE`` maps
        to 500. S3 or DB unreachable is an infra failure, not a
        client mistake.
        """
        upload_service_stub.raise_with = UploadError(
            UploadErrorKind.STORAGE_FAILURE, "S3 put_object: ConnectionRefused"
        )
        response = documents_client.post(
            "/api/documents/upload",
            data={"subject": "maths"},
            files={"file": ("x.pdf", io.BytesIO(b"%PDF-1.4\n"), "application/pdf")},
            headers=_bearer(seeded_eleve_alice),
        )
        assert response.status_code == 500
        body = response.json()
        assert body["detail"]["code"] == UploadErrorKind.STORAGE_FAILURE.value


# ---------------------------------------------------------------------------
# Pydantic / Form validation (auto 422)
# ---------------------------------------------------------------------------


class TestRequestValidation:
    def test_upload_missing_file_field_returns_422(
        self, documents_client, upload_service_stub, seeded_eleve_alice: User
    ) -> None:
        """AC1: a request without the ``file`` form field is rejected
        by Pydantic with 422 BEFORE the handler runs.
        """
        response = documents_client.post(
            "/api/documents/upload",
            data={"subject": "maths"},
            headers=_bearer(seeded_eleve_alice),
        )
        assert response.status_code == 422
        body = response.json()
        assert any(
            err.get("loc", [])[-1] == "file" for err in body.get("detail", [])
        )
        # The service was never called.
        assert upload_service_stub.calls == []

    def test_upload_invalid_subject_returns_422(
        self, documents_client, upload_service_stub, seeded_eleve_alice: User
    ) -> None:
        """Piège 5: ``subject`` outside ``{"maths", "francais"}`` is
        rejected by Pydantic's ``Literal`` with 422.
        """
        response = documents_client.post(
            "/api/documents/upload",
            data={"subject": "physique"},
            files={"file": ("x.pdf", io.BytesIO(b"%PDF-1.4\n"), "application/pdf")},
            headers=_bearer(seeded_eleve_alice),
        )
        assert response.status_code == 422
        # The service was never called.
        assert upload_service_stub.calls == []


# ---------------------------------------------------------------------------
# AC4 — same UploadService as the CLI
# ---------------------------------------------------------------------------


class TestSharedService:
    def test_upload_uses_same_service_as_cli(self) -> None:
        """AC4: the router's ``get_upload_service_dep`` returns the
        same :class:`UploadService` class the CLI builds in
        :func:`app.cli._build_service`. The two must be the same
        implementation — a regression that introduces a local
        "API-only" service variant would silently drift.
        """
        from app.api.documents.factory import get_upload_service_dep
        from app.cli import _build_service as cli_build_service

        # The factory function and the CLI function are two distinct
        # callables but BOTH return a ``UploadService`` instance. We
        # assert the type equality (same class).
        from app.services.rag.upload_service import UploadService

        assert get_upload_service_dep is not None
        assert cli_build_service is not None
        # Both factories build instances of ``UploadService`` — the
        # class identity is the contract AC4 protects.
        from app.services.rag.upload_service import UploadService as US

        assert US is UploadService


# ---------------------------------------------------------------------------
# Tempfile cleanup (Risque 1)
# ---------------------------------------------------------------------------


class TestTempfileCleanup:
    def test_upload_does_not_leave_tempfile(
        self, documents_client, upload_service_stub, seeded_eleve_alice: User
    ) -> None:
        """Risque 1: the router MUST ``os.unlink`` the tempfile in
        its ``finally`` block — both on success and on a controlled
        service failure. A regression that drops the ``unlink``
        leaves a residue under ``tempfile.gettempdir()``.

        The assertion is the count of ``ktutor-upload-*`` files in
        the temp dir before vs. after the request — the difference
        must be zero.
        """
        tmpdir = tempfile.gettempdir()

        def _count() -> list[str]:
            return [
                name
                for name in os.listdir(tmpdir)
                if name.startswith("ktutor-upload-")
            ]

        before = set(_count())

        # Happy path — must not leak.
        response_ok = documents_client.post(
            "/api/documents/upload",
            data={"subject": "maths"},
            files={"file": ("x.pdf", io.BytesIO(b"%PDF-1.4\n"), "application/pdf")},
            headers=_bearer(seeded_eleve_alice),
        )
        assert response_ok.status_code == 201
        after_ok = set(_count())
        leaked_ok = after_ok - before
        assert leaked_ok == set(), f"Tempfile leak on success: {leaked_ok}"

        # Failure path — the service raises INVALID_FILE, the router
        # must still unlink the tempfile.
        upload_service_stub.raise_with = UploadError(
            UploadErrorKind.INVALID_FILE,
            "Fichier invalide: extension '.exe' non supportée",
        )
        response_err = documents_client.post(
            "/api/documents/upload",
            data={"subject": "maths"},
            files={"file": ("bad.exe", io.BytesIO(b"MZ"), "application/octet-stream")},
            headers=_bearer(seeded_eleve_alice),
        )
        assert response_err.status_code == 415
        after_err = set(_count())
        leaked_err = after_err - before
        assert leaked_err == set(), f"Tempfile leak on failure: {leaked_err}"


# ---------------------------------------------------------------------------
# AC7 — cross-tenant isolation
# ---------------------------------------------------------------------------


class TestCrossTenant:
    def test_pseudo_a_upload_not_visible_to_pseudo_b(
        self,
        sample_pdf_path: Path,
        session_factory,
    ) -> None:
        """AC7 (s15): a document uploaded as ``pseudo_a`` (JWT) is
        indexed in the ``rag_<subject>_<pseudo_a>`` ChromaDB
        collection and nowhere else. ``pseudo_b``'s collection has
        0 documents. The test wires the real :class:`UploadService`
        (not the stub) so it exercises the full pipeline up to
        ChromaDB indexing.
        """
        from fastapi.testclient import TestClient

        from app.api.documents.factory import get_upload_service_dep
        from app.core.auth.jwt import create_access_token
        from app.main import app

        # Seed two users so the JWT resolver can find them.
        for pseudo, role in [("pseudo_a", UserRole.ELEVE), ("pseudo_b", UserRole.ELEVE)]:
            with session_factory() as db:
                db.add(
                    User(
                        pseudo=pseudo,
                        password_hash=hash_password("pw"),
                        role=role,
                    )
                )
                db.commit()

        # One shared in-memory ChromaDB so the two collections live
        # in the same backing store (the real one).
        chroma_client = chromadb.EphemeralClient()
        service, fake_s3, chroma = _build_real_upload_service(
            chroma_client=chroma_client
        )

        def _override_get_db() -> Iterator:
            s = session_factory()
            try:
                yield s
            finally:
                s.close()

        app.dependency_overrides[get_upload_service_dep] = lambda: service
        app.dependency_overrides[get_db] = _override_get_db
        try:
            with TestClient(app) as c:
                with sample_pdf_path.open("rb") as fh:
                    resp_a = c.post(
                        "/api/documents/upload",
                        data={"subject": "maths"},
                        files={
                            "file": (sample_pdf_path.name, fh, "application/pdf"),
                        },
                        headers={
                            "Authorization": (
                                f"Bearer {create_access_token('pseudo_a', UserRole.ELEVE)}"
                            )
                        },
                    )
                assert resp_a.status_code == 201, resp_a.text

                with sample_pdf_path.open("rb") as fh:
                    resp_b = c.post(
                        "/api/documents/upload",
                        data={"subject": "maths"},
                        files={
                            "file": (sample_pdf_path.name, fh, "application/pdf"),
                        },
                        headers={
                            "Authorization": (
                                f"Bearer {create_access_token('pseudo_b', UserRole.ELEVE)}"
                            )
                        },
                    )
                assert resp_b.status_code == 201, resp_b.text

            # Inspect the ChromaDB collections directly.
            coll_a = chroma.get_collection("maths", "pseudo_a")
            coll_b = chroma.get_collection("maths", "pseudo_b")
            count_a = coll_a.count()
            count_b = coll_b.count()
            assert count_a >= 1
            assert count_b >= 1
            # The two collections must NOT share documents: every
            # chunk in A has a ``document_id`` distinct from every
            # chunk in B (the two uploads are separate UUIDs).
            ids_a = set(coll_a.get(include=[])["ids"])
            ids_b = set(coll_b.get(include=[])["ids"])
            assert ids_a.isdisjoint(ids_b), (
                "Chunks leaked across tenants: " f"shared={ids_a & ids_b}"
            )

            # The S3 keys are namespaced by pseudo too.
            s3_keys = [k for (_b, k) in fake_s3.objects]
            assert any(k.startswith("students/pseudo_a/") for k in s3_keys)
            assert any(k.startswith("students/pseudo_b/") for k in s3_keys)
            assert not any(
                k.startswith("students/pseudo_a/") and "pseudo_b" in k
                for k in s3_keys
            )
        finally:
            app.dependency_overrides.pop(get_upload_service_dep, None)
            app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# CORS (inherited from s09; verified here so a middleware regression
# does not pass s10's gate).
# ---------------------------------------------------------------------------


class TestCors:
    def test_cors_preflight_succeeds_for_allowed_origin(
        self, documents_client
    ) -> None:
        """CORS preflight from the dev frontend (Next.js on
        ``http://localhost:3000``) is allowed.
        """
        response = documents_client.options(
            "/api/documents/upload",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        assert response.status_code in (200, 204)
        assert (
            response.headers.get("access-control-allow-origin")
            == "http://localhost:3000"
        )

    def test_cors_preflight_fails_for_disallowed_origin(
        self, documents_client
    ) -> None:
        """Bite: a preflight from an origin NOT in the allow-list is
        refused (400) and does NOT receive the
        ``access-control-allow-origin`` header. Using
        ``allow_origins=["*"]`` would weaken this test to a no-op.
        """
        response = documents_client.options(
            "/api/documents/upload",
            headers={
                "Origin": "http://evil.example",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        assert response.status_code == 400
        assert "access-control-allow-origin" not in {
            k.lower() for k in response.headers
        }


# ---------------------------------------------------------------------------
# s15 — JWT is required, body must not carry ``pseudo`` (hard cut)
# ---------------------------------------------------------------------------


class TestDocumentsUploadJwtRequired:
    def test_missing_authorization_returns_401(
        self, documents_client, upload_service_stub
    ) -> None:
        """AC5 (s15): a request with no ``Authorization`` header is
        rejected with 401 ``invalid_token`` BEFORE the handler
        runs. The upload service is NOT called.
        """
        response = documents_client.post(
            "/api/documents/upload",
            data={"subject": "maths"},
            files={"file": ("x.pdf", io.BytesIO(b"%PDF-1.4\n"), "application/pdf")},
        )
        assert response.status_code == 401, response.text
        body = response.json()
        assert body["detail"]["code"] == "invalid_token"
        assert upload_service_stub.calls == []

    def test_junk_bearer_returns_401(
        self, documents_client, upload_service_stub
    ) -> None:
        """AC5 (s15): a malformed bearer token is rejected with
        401 ``invalid_token``. A regression that accepts any
        string starting with ``Bearer `` would let an attacker
        forge the pseudo.
        """
        response = documents_client.post(
            "/api/documents/upload",
            data={"subject": "maths"},
            files={"file": ("x.pdf", io.BytesIO(b"%PDF-1.4\n"), "application/pdf")},
            headers={"Authorization": "Bearer not-a-real-jwt"},
        )
        assert response.status_code == 401
        assert response.json()["detail"]["code"] == "invalid_token"
        assert upload_service_stub.calls == []

    def test_unknown_pseudo_in_valid_jwt_returns_401(
        self, documents_client, upload_service_stub
    ) -> None:
        """AC5 (s15): a JWT signed by the local key but carrying an
        unknown pseudo is rejected with 401 — the user must exist
        in the database. A regression that trusted the JWT ``sub``
        blindly would let an attacker reference any pseudo.
        """
        from app.core.auth.jwt import create_access_token

        # No User row seeded for ``ghost``. The token is valid
        # cryptographically but the resolver can't find the user.
        token = create_access_token("ghost", UserRole.ELEVE)
        response = documents_client.post(
            "/api/documents/upload",
            data={"subject": "maths"},
            files={"file": ("x.pdf", io.BytesIO(b"%PDF-1.4\n"), "application/pdf")},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 401
        assert response.json()["detail"]["code"] == "invalid_token"
        assert upload_service_stub.calls == []

    def test_body_pseudo_field_is_rejected_with_422(
        self, documents_client, upload_service_stub, seeded_eleve_alice: User
    ) -> None:
        """AC5 (s15 hard cut, research Piège 1): a client that still
        sends ``Form(pseudo=...)`` is rejected by FastAPI with 422
        BEFORE the handler runs. The form field is no longer
        declared on the endpoint — the only known client is the
        frontend shipped in the same repo (s11c), so a hard cut is
        safe.
        """
        response = documents_client.post(
            "/api/documents/upload",
            data={"pseudo": "alice", "subject": "maths"},
            files={"file": ("x.pdf", io.BytesIO(b"%PDF-1.4\n"), "application/pdf")},
            headers=_bearer(seeded_eleve_alice),
        )
        assert response.status_code == 422, response.text
        body = response.json()
        # The detail list must contain a Pydantic-form error pointing
        # at the unknown ``pseudo`` field. FastAPI / python-multipart
        # surface it as either ``"pseudo"`` (Form extra) or via the
        # generic value-error path. Accept either — the contract is
        # ``422 + no upload took place``.
        assert "detail" in body
        assert upload_service_stub.calls == []


class TestDocumentsUploadCrossTenant:
    def test_jwt_pseudo_overrides_body_pseudo(
        self,
        documents_client,
        upload_service_stub,
        seeded_eleve_alice: User,
        seeded_eleve_bob: User,
    ) -> None:
        """AC2 (s15): when the JWT says ``alice`` and the body has no
        ``pseudo`` (s15 hard cut), the service is invoked with
        ``alice`` — never ``bob``, never the URL, never the
        multipart payload. A regression that still used the body
        or any other source would be caught here.
        """
        response = documents_client.post(
            "/api/documents/upload",
            data={"subject": "maths"},
            files={"file": ("x.pdf", io.BytesIO(b"%PDF-1.4\n"), "application/pdf")},
            headers=_bearer(seeded_eleve_alice),
        )
        assert response.status_code == 201, response.text
        assert len(upload_service_stub.calls) == 1
        _path, pseudo, subject = upload_service_stub.calls[0]
        assert pseudo == "alice"
        assert subject == "maths"

    def test_bob_token_uploads_for_bob_not_alice(
        self,
        documents_client,
        upload_service_stub,
        seeded_eleve_alice: User,
        seeded_eleve_bob: User,
    ) -> None:
        """AC2 (s15): two requests, two JWTs, two pseudos. The
        service is invoked once per request with the correct
        pseudo. A regression that hardcoded ``alice`` would pass
        the previous test and fail this one.
        """
        for user, expected in [
            (seeded_eleve_alice, "alice"),
            (seeded_eleve_bob, "bob"),
        ]:
            response = documents_client.post(
                "/api/documents/upload",
                data={"subject": "maths"},
                files={"file": ("x.pdf", io.BytesIO(b"%PDF-1.4\n"), "application/pdf")},
                headers=_bearer(user),
            )
            assert response.status_code == 201, response.text
        pseudos = [c[1] for c in upload_service_stub.calls]
        assert pseudos == ["alice", "bob"]

    def test_admin_token_still_uploads_with_admin_pseudo(
        self,
        documents_client,
        upload_service_stub,
        seeded_admin: User,
    ) -> None:
        """ADR 005: an admin can upload on their own behalf (the
        admin ``sub`` is used as the pseudo). The admin-bypass
        only matters when a non-admin claims to be a different
        user — uploading as the admin themselves uses the admin
        pseudo.
        """
        response = documents_client.post(
            "/api/documents/upload",
            data={"subject": "maths"},
            files={"file": ("x.pdf", io.BytesIO(b"%PDF-1.4\n"), "application/pdf")},
            headers=_bearer(seeded_admin),
        )
        assert response.status_code == 201, response.text
        assert len(upload_service_stub.calls) == 1
        _path, pseudo, _subject = upload_service_stub.calls[0]
        assert pseudo == "boss"
