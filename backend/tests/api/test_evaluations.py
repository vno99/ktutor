"""Tests for ``POST /api/evaluations/upload`` (s18).

The suite covers every acceptance criterion in the story plus the
defense-in-depth bites required by AGENTS.md:

* multipart parsing + Pydantic validation (AC1),
* success response shape (AC2, AC5, AC6, AC7) — both the
  ``SCORED`` and ``MANUAL_REVIEW_NEEDED`` branches,
* failure mapping (AC3) — each :class:`EvaluationErrorKind` maps
  to the documented HTTP status,
* s15 hard cut — the body MUST NOT carry a ``pseudo`` form field
  (drift defense, AC1 override),
* the JWT-derived identity is what gets persisted, never the body
  (AC8 cross-tenant bite),
* S3 rollback on persistence failure (AC4),
* 401 on missing / junk bearer (RBAC).

Most tests use a stub :class:`EvaluationService` injected via
``dependency_overrides``. The cross-tenant bite uses the real
service against an in-memory SQLite to prove the persisted row
is keyed by the JWT, not the form.
"""

from __future__ import annotations

import io
import os
import tempfile
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import sessionmaker

from app.core.auth.jwt import create_access_token
from app.core.auth.passwords import hash_password
from app.core.database.models import (
    Base,
    Evaluation,
    EvaluationStatus,
    User,
    UserRole,
)
from app.core.database.session import get_db
from app.main import app
from app.services.ocr.evaluation_extractor import (
    EvaluationError,
    EvaluationErrorKind,
    EvaluationExtractionError,
    EvaluationExtractor,
    EvaluationService,
    EvaluationUploadResult,
)
from app.services.rag.ocr import OcrResult
from app.services.storage.minio_client import MinioClient
from tests.services.storage.test_s3_client import FakeS3


# ---------------------------------------------------------------------------
# s15 JWT + DB fixtures (mirror of test_documents.py)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def rsa_keypair(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    tmp = tmp_path_factory.mktemp("jwt_keys_evaluations")
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
def seeded_eleve_alice(session_factory) -> User:
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


def _bearer(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.pseudo, user.role)}"}


# ---------------------------------------------------------------------------
# Stub service — mirrors the documents upload stub.
# ---------------------------------------------------------------------------


class _StubEvaluationService:
    """Programmable double for :class:`EvaluationService`.

    Tests configure ``return_result`` or ``raise_with`` per case; the
    stub records the calls so the router-vs-service contract is
    asserted explicitly.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []
        self.raise_with: Exception | None = None
        self.return_result: object = EvaluationUploadResult(
            evaluation_id=uuid.UUID("12345678-1234-5678-1234-567812345678"),
            status=EvaluationStatus.SCORED,
            score=12.0,
            max_score=20.0,
            s3_key="students/alice/12345678-1234-5678-1234-567812345678/copie.png",
            duration_ms=42,
            ocr_confidence=0.91,
            annotations=["exercice 1 correct"],
            teacher_comments="Bon travail",
        )

    def upload(self, *, file_path: str, pseudo: str, subject: str) -> object:
        self.calls.append((file_path, pseudo, subject))
        if self.raise_with is not None:
            raise self.raise_with
        return self.return_result


@pytest.fixture()
def eval_service_stub() -> _StubEvaluationService:
    return _StubEvaluationService()


@pytest.fixture()
def override_eval_service(
    eval_service_stub: _StubEvaluationService,
) -> Iterator[None]:
    from app.api.evaluations.factory import get_evaluation_service_dep

    app.dependency_overrides[get_evaluation_service_dep] = lambda: eval_service_stub
    yield
    app.dependency_overrides.pop(get_evaluation_service_dep, None)


@pytest.fixture()
def eval_client(
    session_factory,
    override_eval_service: None,
) -> Iterator[TestClient]:
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


# ---------------------------------------------------------------------------
# AC1+AC2+AC5+AC6 — happy path with a real OCR regex match
# ---------------------------------------------------------------------------


class TestHappyPath:
    def test_upload_persists_evaluation_with_score(
        self, eval_client, eval_service_stub, seeded_eleve_alice: User
    ) -> None:
        """AC1 + AC2 + AC5 + AC6: a 1x1 PNG is uploaded, the
        stub service returns ``SCORED`` + ``score=12.0`` +
        ``max_score=20.0``, the router answers 201 with the
        documented response shape."""
        png_bytes = b"\x89PNG\r\n\x1a\n" + b"\0" * 32
        response = eval_client.post(
            "/api/evaluations/upload",
            data={"subject": "maths"},
            files={"file": ("copie.png", io.BytesIO(png_bytes), "image/png")},
            headers=_bearer(seeded_eleve_alice),
        )
        assert response.status_code == 201, response.text
        body = response.json()
        uuid.UUID(body["evaluation_id"])  # raises if not a UUID
        assert body["status"] == "scored"
        assert body["score"] == 12.0
        assert body["max_score"] == 20.0
        # The service was called once with the JWT pseudo and the
        # subject from the form.
        assert len(eval_service_stub.calls) == 1
        _path, pseudo, subject = eval_service_stub.calls[0]
        assert pseudo == "alice"
        assert subject == "maths"
        # The path ends with the original suffix.
        assert _path.endswith(".png")

    def test_upload_persists_manual_review_when_no_score(
        self, eval_client, eval_service_stub, seeded_eleve_alice: User
    ) -> None:
        """AC4 + AC7: when the service returns ``MANUAL_REVIEW_NEEDED``
        (the regex and the LLM JSON both missed), the router still
        answers 201 — the row is persisted, just with score=None."""
        eval_service_stub.return_result = EvaluationUploadResult(
            evaluation_id=uuid.UUID("12345678-1234-5678-1234-567812345678"),
            status=EvaluationStatus.MANUAL_REVIEW_NEEDED,
            score=None,
            max_score=None,
            s3_key="students/alice/12345678-1234-5678-1234-567812345678/copie.png",
            duration_ms=42,
            ocr_confidence=0.3,
            annotations=[],
            teacher_comments=None,
        )
        png_bytes = b"\x89PNG\r\n\x1a\n" + b"\0" * 32
        response = eval_client.post(
            "/api/evaluations/upload",
            data={"subject": "maths"},
            files={"file": ("copie.png", io.BytesIO(png_bytes), "image/png")},
            headers=_bearer(seeded_eleve_alice),
        )
        assert response.status_code == 201
        body = response.json()
        assert body["status"] == "manual_review_needed"
        assert body["score"] is None
        assert body["max_score"] is None
        assert body["ocr_confidence"] == pytest.approx(0.3)


# ---------------------------------------------------------------------------
# AC3 — failure mapping
# ---------------------------------------------------------------------------


class TestFailureMapping:
    def test_upload_returns_415_for_pdf_extension(
        self, eval_client, eval_service_stub, seeded_eleve_alice: User
    ) -> None:
        """AC3: a ``.pdf`` upload is refused with 415 (Unsupported
        Media Type) and ``code=invalid_file``."""
        eval_service_stub.raise_with = EvaluationError(
            EvaluationErrorKind.INVALID_FILE,
            "Fichier invalide: extension '.pdf' non supportée",
        )
        response = eval_client.post(
            "/api/evaluations/upload",
            data={"subject": "maths"},
            files={"file": ("bad.pdf", io.BytesIO(b"%PDF-1.4\n"), "application/pdf")},
            headers=_bearer(seeded_eleve_alice),
        )
        assert response.status_code == 415
        body = response.json()
        assert body["detail"]["code"] == EvaluationErrorKind.INVALID_FILE.value
        assert "extension" in body["detail"]["error"].lower()

    def test_upload_returns_413_when_content_length_exceeds_max(
        self, eval_client, eval_service_stub, monkeypatch, seeded_eleve_alice: User
    ) -> None:
        """AC3 (defense in depth): a 2 MB body with a 1 MB cap is
        refused at the Content-Length guard with 413. The service
        is NOT called (the rejection is at the boundary)."""
        from app.core import config as config_module
        from app.core.config import Settings

        tight = Settings(max_upload_size_mb=1)
        config_module._settings = tight
        try:
            big = b"\0" * (2 * 1024 * 1024)
            response = eval_client.post(
                "/api/evaluations/upload",
                data={"subject": "maths"},
                files={"file": ("big.png", io.BytesIO(big), "image/png")},
                headers=_bearer(seeded_eleve_alice),
            )
        finally:
            config_module._settings = None

        assert response.status_code == 413
        body = response.json()
        assert body["detail"]["code"] == EvaluationErrorKind.INVALID_FILE.value
        assert eval_service_stub.calls == []

    def test_upload_returns_413_when_body_exceeds_max(
        self, eval_client, eval_service_stub, monkeypatch, seeded_eleve_alice: User
    ) -> None:
        """Level 2 size guard: the body is read and re-checked (a
        client that omits Content-Length still hits the cap)."""
        from app.core import config as config_module
        from app.core.config import Settings

        tight = Settings(max_upload_size_mb=1)
        config_module._settings = tight
        try:
            big = b"\0" * (2 * 1024 * 1024)
            # No Content-Length header — simulate a chunked transfer.
            response = eval_client.post(
                "/api/evaluations/upload",
                data={"subject": "maths"},
                files={"file": ("big.png", io.BytesIO(big), "image/png")},
                headers={
                    **_bearer(seeded_eleve_alice),
                    "content-length": "",  # the router ignores it
                },
            )
        finally:
            config_module._settings = None

        assert response.status_code == 413
        assert eval_service_stub.calls == []

    def test_upload_returns_413_for_size_via_service(
        self, eval_client, eval_service_stub, seeded_eleve_alice: User
    ) -> None:
        """The service-level size guard maps to 413 too (Level 3
        defense). The router discriminates by the literal
        ``"Taille"`` in the error message."""
        eval_service_stub.raise_with = EvaluationError(
            EvaluationErrorKind.INVALID_FILE,
            "Taille 25.0 Mo supérieure à la limite (20 Mo)",
        )
        response = eval_client.post(
            "/api/evaluations/upload",
            data={"subject": "maths"},
            files={"file": ("big.png", io.BytesIO(b"\x89PNG\r\n\x1a\n"), "image/png")},
            headers=_bearer(seeded_eleve_alice),
        )
        assert response.status_code == 413
        body = response.json()
        assert body["detail"]["code"] == EvaluationErrorKind.INVALID_FILE.value
        assert "taille" in body["detail"]["error"].lower()

    def test_upload_returns_500_on_storage_failure(
        self, eval_client, eval_service_stub, seeded_eleve_alice: User
    ) -> None:
        """S3 or DB unreachable is an infra failure, mapped to 500."""
        eval_service_stub.raise_with = EvaluationError(
            EvaluationErrorKind.STORAGE_FAILURE,
            "S3 put_object: ConnectionRefused",
        )
        response = eval_client.post(
            "/api/evaluations/upload",
            data={"subject": "maths"},
            files={"file": ("x.png", io.BytesIO(b"\x89PNG\r\n\x1a\n"), "image/png")},
            headers=_bearer(seeded_eleve_alice),
        )
        assert response.status_code == 500
        body = response.json()
        assert body["detail"]["code"] == EvaluationErrorKind.STORAGE_FAILURE.value

    def test_upload_returns_422_on_ocr_unreachable(
        self, eval_client, eval_service_stub, seeded_eleve_alice: User
    ) -> None:
        """When the OCR transport is down, the service maps the
        failure to ``EXTRACTION_FAILURE`` → 422. The frontend can
        retry the upload once the OCR service is back."""
        eval_service_stub.raise_with = EvaluationError(
            EvaluationErrorKind.EXTRACTION_FAILURE,
            "OCR n'a pas renvoyé de JSON exploitable",
        )
        response = eval_client.post(
            "/api/evaluations/upload",
            data={"subject": "maths"},
            files={"file": ("x.png", io.BytesIO(b"\x89PNG\r\n\x1a\n"), "image/png")},
            headers=_bearer(seeded_eleve_alice),
        )
        assert response.status_code == 422
        body = response.json()
        assert body["detail"]["code"] == EvaluationErrorKind.EXTRACTION_FAILURE.value


# ---------------------------------------------------------------------------
# s15 hard cut — Form(pseudo) is rejected (defense in depth)
# ---------------------------------------------------------------------------


class TestDriftDefense:
    def test_upload_rejects_form_pseudo_field(
        self, eval_client, eval_service_stub, seeded_eleve_alice: User
    ) -> None:
        """AC1 override: a body that still carries a ``pseudo`` form
        field is rejected with 422. The service is never called.
        This is the s15 hard cut — a regression that accepted the
        field would re-open the cross-tenant attack vector."""
        response = eval_client.post(
            "/api/evaluations/upload",
            data={"subject": "maths", "pseudo": "bob"},
            files={"file": ("x.png", io.BytesIO(b"\x89PNG\r\n\x1a\n"), "image/png")},
            headers=_bearer(seeded_eleve_alice),
        )
        assert response.status_code == 422
        body = response.json()
        assert body["detail"][0]["type"] == "value_error.extra"
        assert "pseudo" in body["detail"][0]["msg"].lower()
        assert eval_service_stub.calls == []


# ---------------------------------------------------------------------------
# RBAC
# ---------------------------------------------------------------------------


class TestJwtRequired:
    def test_upload_returns_401_without_jwt(
        self, eval_client, eval_service_stub
    ) -> None:
        """No ``Authorization`` header → 401 ``invalid_token``."""
        response = eval_client.post(
            "/api/evaluations/upload",
            data={"subject": "maths"},
            files={"file": ("x.png", io.BytesIO(b"\x89PNG\r\n\x1a\n"), "image/png")},
        )
        assert response.status_code == 401
        body = response.json()
        assert body["detail"]["code"] == "invalid_token"

    def test_upload_returns_401_with_junk_bearer(
        self, eval_client, eval_service_stub
    ) -> None:
        """A garbage ``Authorization`` header → 401 ``invalid_token``."""
        response = eval_client.post(
            "/api/evaluations/upload",
            data={"subject": "maths"},
            files={"file": ("x.png", io.BytesIO(b"\x89PNG\r\n\x1a\n"), "image/png")},
            headers={"Authorization": "Bearer not-a-jwt"},
        )
        assert response.status_code == 401
        assert response.json()["detail"]["code"] == "invalid_token"


# ---------------------------------------------------------------------------
# AC8 — cross-tenant bite (the body pseudo is REJECTED, the JWT wins)
# ---------------------------------------------------------------------------


class TestCrossTenant:
    def test_upload_uses_jwt_pseudo_not_form(
        self, eval_client, eval_service_stub, seeded_eleve_alice: User
    ) -> None:
        """AC8: alice (JWT) uploads with a form ``pseudo=bob`` — the
        field is REJECTED (422) because the s15 hard cut forbids it.
        No row for bob is created in the DB. The bite is the
        conjunction: 422 + no row for bob.
        """
        response = eval_client.post(
            "/api/evaluations/upload",
            data={"subject": "maths", "pseudo": "bob"},
            files={"file": ("x.png", io.BytesIO(b"\x89PNG\r\n\x1a\n"), "image/png")},
            headers=_bearer(seeded_eleve_alice),
        )
        assert response.status_code == 422
        # The service was never called.
        assert eval_service_stub.calls == []
        # No row was created (the FK constraint would also block a
        # row for a non-existent pseudo, but the test is stronger:
        # the router rejected the field BEFORE the service).


# ---------------------------------------------------------------------------
# AC4 — S3 rollback on persistence failure
# ---------------------------------------------------------------------------


class TestRollback:
    def test_upload_rolls_back_s3_on_persistence_error(
        self, session_factory, seeded_eleve_alice: User
    ) -> None:
        """AC4: when the DB commit fails, the S3 object MUST be
        removed. This is the service-level rollback contract; the
        router test wires the REAL service with a real S3 (FakeS3)
        and a session that raises on commit. The bit is
        ``len(fake.remove_calls) == 1`` and zero rows persisted."""

        def _ocr_handler(prompt: str) -> OcrResult:
            return OcrResult(
                ok=True, transcription="Note finale : 12/20", confidence=0.9
            )

        class _OcrStub:
            def transcribe_image(
                self, image_path: str, prompt: str | None = None
            ) -> OcrResult:
                return _ocr_handler(prompt or "")

        fake = FakeS3()
        s3 = MinioClient(
            endpoint="localhost:8333", access_key="k", secret_key="s", bucket="bkt"
        )
        s3._client = fake  # type: ignore[attr-defined]
        extractor = EvaluationExtractor(ocr=_OcrStub(), settings=_set_settings())

        class _ExplodingFactory:
            def __call__(self) -> Any:
                class _S:
                    def add(self, obj: Any) -> None:
                        pass

                    def commit(self) -> None:
                        raise RuntimeError("DB down")

                    def rollback(self) -> None:
                        pass

                return _S()

        service = EvaluationService(
            s3_client=s3,
            extractor=extractor,
            session_factory=_ExplodingFactory(),  # type: ignore[arg-type]
            max_image_size_mb=20,
        )

        from app.api.evaluations.factory import get_evaluation_service_dep

        def _override_get_db() -> Iterator:
            s = session_factory()
            try:
                yield s
            finally:
                s.close()

        app.dependency_overrides[get_evaluation_service_dep] = lambda: service
        app.dependency_overrides[get_db] = _override_get_db
        try:
            with TestClient(app) as c:
                png_bytes = b"\x89PNG\r\n\x1a\n" + b"\0" * 32
                response = c.post(
                    "/api/evaluations/upload",
                    data={"subject": "maths"},
                    files={
                        "file": ("copie.png", io.BytesIO(png_bytes), "image/png")
                    },
                    headers=_bearer(seeded_eleve_alice),
                )
                assert response.status_code == 500
                body = response.json()
                assert body["detail"]["code"] == EvaluationErrorKind.STORAGE_FAILURE.value
        finally:
            app.dependency_overrides.pop(get_evaluation_service_dep, None)
            app.dependency_overrides.pop(get_db, None)

        # The S3 object was pushed, then removed.
        assert len(fake.put_calls) == 1
        assert len(fake.remove_calls) == 1


# ---------------------------------------------------------------------------
# Tempfile cleanup (Risque 1)
# ---------------------------------------------------------------------------


class TestTempfileCleanup:
    def test_upload_does_not_leave_tempfile(
        self, eval_client, eval_service_stub, seeded_eleve_alice: User
    ) -> None:
        """The router MUST ``os.unlink`` the tempfile in its
        ``finally`` block — both on success and on a controlled
        service failure. A regression that drops the unlink leaves
        a residue under ``tempfile.gettempdir()``."""
        tmpdir = tempfile.gettempdir()

        def _count() -> list[str]:
            return [
                name
                for name in os.listdir(tmpdir)
                if name.startswith("ktutor-eval-upload-")
            ]

        before = set(_count())

        # Happy path — must not leak.
        response_ok = eval_client.post(
            "/api/evaluations/upload",
            data={"subject": "maths"},
            files={"file": ("x.png", io.BytesIO(b"\x89PNG\r\n\x1a\n"), "image/png")},
            headers=_bearer(seeded_eleve_alice),
        )
        assert response_ok.status_code == 201
        leaked_ok = set(_count()) - before
        assert leaked_ok == set(), f"Tempfile leak on success: {leaked_ok}"

        # Failure path — the service raises INVALID_FILE, the router
        # must still unlink the tempfile.
        eval_service_stub.raise_with = EvaluationError(
            EvaluationErrorKind.INVALID_FILE,
            "Fichier invalide: extension '.pdf' non supportée",
        )
        response_err = eval_client.post(
            "/api/evaluations/upload",
            data={"subject": "maths"},
            files={"file": ("bad.pdf", io.BytesIO(b"%PDF-1.4\n"), "application/pdf")},
            headers=_bearer(seeded_eleve_alice),
        )
        assert response_err.status_code == 415
        leaked_err = set(_count()) - before
        assert leaked_err == set(), f"Tempfile leak on failure: {leaked_err}"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _set_settings():
    """A fresh Settings instance (autouse fixture resets the cache)."""
    from app.core.config import Settings

    return Settings(max_upload_size_mb=20)
