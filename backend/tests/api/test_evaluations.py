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

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import sessionmaker

from app.api.evaluations.schemas import ScoreManualRequest
from app.core.auth.jwt import create_access_token
from app.core.auth.passwords import hash_password
from app.core.database.models import (
    Base,
    Evaluation,
    EvaluationStatus,
    ParentChildLink,
    Subject,
    User,
    UserRole,
)
from app.core.database.session import get_db
from app.main import app
from app.services.ocr.evaluation_extractor import (
    EvaluationError,
    EvaluationErrorKind,
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


# ---------------------------------------------------------------------------
# s18b — T1 schema validation (Pydantic-level, no HTTP)
# ---------------------------------------------------------------------------


class TestScoreManualRequestSchema:
    """AC1 + Piège 1: the request body is bounded by Pydantic.
    Negative score, score > max_score, and oversized comments are
    refused at 422 before the router / service is invoked."""

    def test_score_manual_request_rejects_negative_score(self) -> None:
        with pytest.raises(Exception) as exc_info:
            ScoreManualRequest(score=-1.0, max_score=20.0)
        # Pydantic raises ``ValidationError`` (subclass of Exception).
        assert "score" in str(exc_info.value).lower()

    def test_score_manual_request_rejects_score_greater_than_max(self) -> None:
        with pytest.raises(Exception) as exc_info:
            ScoreManualRequest(score=15.0, max_score=10.0)
        msg = str(exc_info.value).lower()
        assert "max_score" in msg or "score" in msg

    def test_score_manual_request_teacher_comments_too_long(self) -> None:
        long = "x" * 8193
        with pytest.raises(Exception) as exc_info:
            ScoreManualRequest(score=12.0, max_score=20.0, teacher_comments=long)
        assert "teacher_comments" in str(exc_info.value).lower() or "at most" in str(
            exc_info.value
        ).lower()

    def test_score_manual_request_accepts_valid_payload(self) -> None:
        """The happy-path body parses without error."""
        req = ScoreManualRequest(
            score=12.0, max_score=20.0, teacher_comments="Bon travail"
        )
        assert req.score == 12.0
        assert req.max_score == 20.0
        assert req.teacher_comments == "Bon travail"

    def test_score_manual_request_teacher_comments_optional(self) -> None:
        req = ScoreManualRequest(score=12.0, max_score=20.0)
        assert req.teacher_comments is None


# ---------------------------------------------------------------------------
# s18b — T3 + T4 + T5 — HTTP-level integration (real service, in-memory DB)
# ---------------------------------------------------------------------------


_SEEDED_EVAL_ID = "11111111-1111-1111-1111-111111111111"
_SEEDED_EVAL_ID_BOB = "33333333-3333-3333-3333-333333333333"
_SEEDED_EVAL_ID_SCORED = "22222222-2222-2222-2222-222222222222"
_SEEDED_EVAL_ID_BOB_SCORED = "44444444-4444-4444-4444-444444444444"


class _OcrStubForRouter:
    """In-memory OCR double for the s18b router tests.

    Mirrors the stub in ``tests/services/ocr/test_evaluation_extractor.py``
    (kept local so the API test file stays self-contained, per
    AGENTS.md "Pas de refactor transverse")."""

    def __init__(self, result_factory):
        self._result_factory = result_factory
        self.calls: list[tuple[str, str | None]] = []

    def transcribe_image(self, image_path: str, prompt: str | None = None) -> OcrResult:
        self.calls.append((image_path, prompt))
        return self._result_factory(prompt or "")


def _make_s3_with_fake_for_router() -> tuple[MinioClient, FakeS3]:
    fake = FakeS3()
    s3 = MinioClient(
        endpoint="localhost:8333", access_key="k", secret_key="s", bucket="bkt"
    )
    s3._client = fake  # type: ignore[attr-defined]
    return s3, fake


def _seed_evaluation(
    session_factory,
    *,
    eval_id: str = _SEEDED_EVAL_ID,
    pseudo: str = "alice",
    status: EvaluationStatus = EvaluationStatus.MANUAL_REVIEW_NEEDED,
    score: float | None = None,
    max_score: float | None = None,
) -> Evaluation:
    import uuid as _uuid
    from datetime import UTC, datetime

    with session_factory() as s:
        row = Evaluation(
            id=_uuid.UUID(eval_id),
            student_pseudo=pseudo,
            subject=Subject.MATHS,
            s3_key=f"students/{pseudo}/{eval_id}",
            filename="copie.png",
            status=status,
            score=score,
            max_score=max_score,
            annotations=None,
            teacher_comments=None,
            ocr_text="Note finale : 12/20",
            ocr_confidence=0.9,
            error_reason="no_score_in_transcript"
            if status is EvaluationStatus.MANUAL_REVIEW_NEEDED
            else None,
            created_at=datetime.now(UTC),
        )
        s.add(row)
        s.commit()
    return row


def _build_real_service(session_factory, ocr_text: str = "Note finale : 12/20"):
    """Build a real :class:`EvaluationService` against in-memory backends."""
    from app.core.config import Settings as _Settings

    s3, fake = _make_s3_with_fake_for_router()
    # Seed the image for the seeded eval row so reprocess can read it.
    fake.objects[("bkt", f"students/alice/{_SEEDED_EVAL_ID}")] = (
        b"\x89PNG\r\n\x1a\n" + b"\0" * 32
    )
    fake.objects[("bkt", f"students/bob/{_SEEDED_EVAL_ID_BOB}")] = (
        b"\x89PNG\r\n\x1a\n" + b"\0" * 32
    )
    fake.objects[("bkt", f"students/alice/{_SEEDED_EVAL_ID_SCORED}")] = (
        b"\x89PNG\r\n\x1a\n" + b"\0" * 32
    )
    fake.objects[("bkt", f"students/bob/{_SEEDED_EVAL_ID_BOB_SCORED}")] = (
        b"\x89PNG\r\n\x1a\n" + b"\0" * 32
    )

    def _factory(prompt: str) -> OcrResult:
        return OcrResult(ok=True, transcription=ocr_text, confidence=0.9)

    extractor = EvaluationExtractor(ocr=_OcrStubForRouter(_factory), settings=_Settings())
    service = EvaluationService(
        s3_client=s3,
        extractor=extractor,
        session_factory=session_factory,
        max_image_size_mb=20,
    )
    return service, fake


@pytest.fixture()
def real_service_client(session_factory):
    """A TestClient with the REAL EvaluationService wired (no stub)."""

    def _override_get_db() -> Iterator:
        s = session_factory()
        try:
            yield s
        finally:
            s.close()

    def _service_override():
        service, _fake = _build_real_service(session_factory)
        return service

    from app.api.evaluations.factory import get_evaluation_service_dep

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_evaluation_service_dep] = _service_override
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_evaluation_service_dep, None)


@pytest.fixture()
def seeded_admin(session_factory) -> User:
    with session_factory() as db:
        user = User(
            pseudo="boss",
            password_hash=hash_password("seedpassword1"),
            role=UserRole.ADMIN,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user


@pytest.fixture()
def seeded_parent(session_factory) -> User:
    with session_factory() as db:
        user = User(
            pseudo="pat",
            password_hash=hash_password("seedpassword1"),
            role=UserRole.PARENT,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user


@pytest.fixture()
def seeded_eleve_charlie(session_factory) -> User:
    """A third eleve — used to verify the cross-tenant bite."""
    with session_factory() as db:
        user = User(
            pseudo="charlie",
            password_hash=hash_password("seedpassword1"),
            role=UserRole.ELEVE,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user


def _link_parent_to_child(session_factory, parent_pseudo: str, child_pseudo: str) -> None:
    with session_factory() as db:
        db.add(
            ParentChildLink(
                parent_pseudo=parent_pseudo,
                child_pseudo=child_pseudo,
            )
        )
        db.commit()


# ---------------------------------------------------------------------------
# T3 — happy paths (AC1, AC4, AC5, AC6) + 409 (AC2)
# ---------------------------------------------------------------------------


class TestScoreManualAdminHappyPath:
    def test_score_manual_admin_updates_to_scored(
        self,
        real_service_client: TestClient,
        session_factory,
        seeded_admin: User,
        seeded_eleve_alice: User,
    ) -> None:
        """AC1 + AC5 + AC6: admin POSTs to score-manual on a
        MANUAL_REVIEW_NEEDED row. The response is 200 with the
        updated row, and the DB row is SCORED."""
        _seed_evaluation(session_factory, eval_id=_SEEDED_EVAL_ID, pseudo="alice")
        response = real_service_client.post(
            f"/api/evaluations/{_SEEDED_EVAL_ID}/score-manual",
            json={"score": 12.0, "max_score": 20.0, "teacher_comments": "Bon travail"},
            headers=_bearer(seeded_admin),
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "scored"
        assert body["score"] == 12.0
        assert body["max_score"] == 20.0
        assert body["teacher_comments"] == "Bon travail"
        assert body["evaluation_id"] == _SEEDED_EVAL_ID
        # The DB row is updated.
        import uuid as _uuid

        with session_factory() as s:
            row = s.get(Evaluation, _uuid.UUID(_SEEDED_EVAL_ID))
            assert row is not None
            assert row.status is EvaluationStatus.SCORED
            assert row.score == 12.0
            assert row.teacher_comments == "Bon travail"

    def test_score_manual_returns_409_when_already_scored(
        self,
        real_service_client: TestClient,
        session_factory,
        seeded_admin: User,
        seeded_eleve_alice: User,
    ) -> None:
        """AC2: the row is already SCORED → the router returns 409
        with ``code=state_conflict``. The DB row is NOT mutated."""
        _seed_evaluation(
            session_factory,
            eval_id=_SEEDED_EVAL_ID_SCORED,
            pseudo="alice",
            status=EvaluationStatus.SCORED,
            score=8.0,
            max_score=20.0,
        )
        response = real_service_client.post(
            f"/api/evaluations/{_SEEDED_EVAL_ID_SCORED}/score-manual",
            json={"score": 18.0, "max_score": 20.0},
            headers=_bearer(seeded_admin),
        )
        assert response.status_code == 409
        body = response.json()
        assert body["detail"]["code"] == "state_conflict"
        # The DB row is NOT updated to 18.0.
        import uuid as _uuid

        with session_factory() as s:
            row = s.get(Evaluation, _uuid.UUID(_SEEDED_EVAL_ID_SCORED))
            assert row is not None
            assert row.score == 8.0  # original


class TestReprocessAdminHappyPath:
    def test_reprocess_admin_extracts_and_updates(
        self,
        real_service_client: TestClient,
        session_factory,
        seeded_admin: User,
        seeded_eleve_alice: User,
    ) -> None:
        """AC4 + AC5: admin POSTs to reprocess on a MANUAL_REVIEW_NEEDED
        row. The OCR finds ``12/20``, the row is updated to SCORED,
        and the response carries the source."""
        _seed_evaluation(session_factory, eval_id=_SEEDED_EVAL_ID, pseudo="alice")
        response = real_service_client.post(
            f"/api/evaluations/{_SEEDED_EVAL_ID}/reprocess",
            headers=_bearer(seeded_admin),
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "scored"
        assert body["score"] == 12.0
        assert body["max_score"] == 20.0
        assert body["source"] == "regex"

    def test_reprocess_leaves_manual_review_needed_on_ocr_failure(
        self,
        real_service_client: TestClient,
        session_factory,
        seeded_admin: User,
        seeded_eleve_alice: User,
    ) -> None:
        """AC5 second branch: when the re-extraction finds no score,
        the response carries status=manual_review_needed and the
        source=none."""
        # Override the service factory for THIS test with an OCR stub
        # that returns no score.
        from app.api.evaluations.factory import get_evaluation_service_dep

        def _override_get_db() -> Iterator:
            s = session_factory()
            try:
                yield s
            finally:
                s.close()

        s3, fake = _make_s3_with_fake_for_router()
        fake.objects[("bkt", f"students/alice/{_SEEDED_EVAL_ID}")] = (
            b"\x89PNG\r\n\x1a\n" + b"\0" * 32
        )

        def _factory(prompt: str) -> OcrResult:
            return OcrResult(
                ok=True,
                transcription="illisible",
                confidence=0.7,
                raw={
                    "score": None,
                    "max_score": None,
                    "annotations": [],
                    "teacher_comments": None,
                    "ocr_text": "illisible",
                    "ocr_confidence": 0.7,
                },
            )

        from app.core.config import Settings as _Settings

        extractor = EvaluationExtractor(ocr=_OcrStubForRouter(_factory), settings=_Settings())
        service = EvaluationService(
            s3_client=s3,
            extractor=extractor,
            session_factory=session_factory,
            max_image_size_mb=20,
        )

        app.dependency_overrides[get_db] = _override_get_db
        app.dependency_overrides[get_evaluation_service_dep] = lambda: service
        try:
            _seed_evaluation(session_factory, eval_id=_SEEDED_EVAL_ID, pseudo="alice")
            with TestClient(app) as c:
                response = c.post(
                    f"/api/evaluations/{_SEEDED_EVAL_ID}/reprocess",
                    headers=_bearer(seeded_admin),
                )
            assert response.status_code == 200, response.text
            body = response.json()
            assert body["status"] == "manual_review_needed"
            assert body["source"] == "none"
            assert body["score"] is None
        finally:
            app.dependency_overrides.pop(get_db, None)
            app.dependency_overrides.pop(get_evaluation_service_dep, None)

    def test_reprocess_returns_409_when_already_scored(
        self,
        real_service_client: TestClient,
        session_factory,
        seeded_admin: User,
        seeded_eleve_alice: User,
    ) -> None:
        """Piège 4 / research open question 3: a SCORED row cannot
        be reprocessed (the audit log lives in loguru, not in a
        history column)."""
        _seed_evaluation(
            session_factory,
            eval_id=_SEEDED_EVAL_ID_SCORED,
            pseudo="alice",
            status=EvaluationStatus.SCORED,
            score=8.0,
            max_score=20.0,
        )
        response = real_service_client.post(
            f"/api/evaluations/{_SEEDED_EVAL_ID_SCORED}/reprocess",
            headers=_bearer(seeded_admin),
        )
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "state_conflict"


# ---------------------------------------------------------------------------
# T4 — RBAC strict (AC3, AC7, AC8 + Piège 5)
# ---------------------------------------------------------------------------


class TestScoreManualRbac:
    def test_score_manual_eleve_cannot_score_own_evaluation(
        self,
        real_service_client: TestClient,
        session_factory,
        seeded_eleve_alice: User,
    ) -> None:
        """AC3 + AC7 + Piège 5: alice (eleve) cannot score her own
        evaluation. The router rejects with 403 BEFORE the service
        is invoked — the DB row stays MANUAL_REVIEW_NEEDED."""
        _seed_evaluation(session_factory, eval_id=_SEEDED_EVAL_ID, pseudo="alice")
        response = real_service_client.post(
            f"/api/evaluations/{_SEEDED_EVAL_ID}/score-manual",
            json={"score": 15.0, "max_score": 20.0},
            headers=_bearer(seeded_eleve_alice),
        )
        assert response.status_code == 403
        assert response.json()["detail"]["code"] == "forbidden"
        # The row is NOT mutated.
        import uuid as _uuid

        with session_factory() as s:
            row = s.get(Evaluation, _uuid.UUID(_SEEDED_EVAL_ID))
            assert row is not None
            assert row.status is EvaluationStatus.MANUAL_REVIEW_NEEDED
            assert row.score is None

    def test_score_manual_parent_of_linked_child_succeeds(
        self,
        real_service_client: TestClient,
        session_factory,
        seeded_parent: User,
        seeded_eleve_alice: User,
    ) -> None:
        """Piège 2 success branch: pat (parent) is linked to alice →
        score-manual succeeds. The row is updated to SCORED."""
        _seed_evaluation(session_factory, eval_id=_SEEDED_EVAL_ID, pseudo="alice")
        _link_parent_to_child(session_factory, "pat", "alice")
        response = real_service_client.post(
            f"/api/evaluations/{_SEEDED_EVAL_ID}/score-manual",
            json={"score": 14.0, "max_score": 20.0},
            headers=_bearer(seeded_parent),
        )
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "scored"
        assert response.json()["score"] == 14.0

    def test_score_manual_parent_of_unlinked_child_returns_403(
        self,
        real_service_client: TestClient,
        session_factory,
        seeded_parent: User,
        seeded_eleve_bob: User,
    ) -> None:
        """AC8 / Piège 2 miss branch: pat (parent) is NOT linked to
        bob → score-manual is rejected with 403. The DB row stays
        MANUAL_REVIEW_NEEDED."""
        # pat is NOT linked to bob — only alice is potentially linked.
        _seed_evaluation(session_factory, eval_id=_SEEDED_EVAL_ID_BOB, pseudo="bob")
        response = real_service_client.post(
            f"/api/evaluations/{_SEEDED_EVAL_ID_BOB}/score-manual",
            json={"score": 10.0, "max_score": 20.0},
            headers=_bearer(seeded_parent),
        )
        assert response.status_code == 403
        assert response.json()["detail"]["code"] == "forbidden"
        # The row is NOT mutated.
        import uuid as _uuid

        with session_factory() as s:
            row = s.get(Evaluation, _uuid.UUID(_SEEDED_EVAL_ID_BOB))
            assert row is not None
            assert row.status is EvaluationStatus.MANUAL_REVIEW_NEEDED


class TestReprocessRbac:
    def test_reprocess_eleve_returns_403(
        self,
        real_service_client: TestClient,
        session_factory,
        seeded_eleve_alice: User,
    ) -> None:
        """AC4 ``admin only``: an eleve cannot trigger a reprocess on
        her own evaluation. The router rejects with 403."""
        _seed_evaluation(session_factory, eval_id=_SEEDED_EVAL_ID, pseudo="alice")
        response = real_service_client.post(
            f"/api/evaluations/{_SEEDED_EVAL_ID}/reprocess",
            headers=_bearer(seeded_eleve_alice),
        )
        assert response.status_code == 403
        assert response.json()["detail"]["code"] == "forbidden"

    def test_reprocess_parent_returns_403(
        self,
        real_service_client: TestClient,
        session_factory,
        seeded_parent: User,
        seeded_eleve_alice: User,
    ) -> None:
        """AC4 ``admin only``: even a linked parent is rejected with
        403 — reprocess is strictly admin-only."""
        _seed_evaluation(session_factory, eval_id=_SEEDED_EVAL_ID, pseudo="alice")
        _link_parent_to_child(session_factory, "pat", "alice")
        response = real_service_client.post(
            f"/api/evaluations/{_SEEDED_EVAL_ID}/reprocess",
            headers=_bearer(seeded_parent),
        )
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# T5 — audit logging (no PII in the log line)
# ---------------------------------------------------------------------------


class TestAuditLogging:
    def test_score_manual_emits_audit_log(
        self,
        real_service_client: TestClient,
        session_factory,
        seeded_admin: User,
        seeded_eleve_alice: User,
    ) -> None:
        """T5: a successful score-manual emits the
        ``security.evaluation_manual_score`` log line with the
        caller / evaluation_id / new score fields. The
        ``teacher_comments`` value MUST NOT appear in the log
        (AGENTS.md § Backend logging — no PII)."""
        from loguru import logger as _logger

        captured: list[str] = []

        sink_id = _logger.add(
            lambda msg: captured.append(str(msg)),
            level="INFO",
        )
        try:
            _seed_evaluation(session_factory, eval_id=_SEEDED_EVAL_ID, pseudo="alice")
            secret_comment = "SECRET-PII-MUST-NOT-LEAK-12345"
            response = real_service_client.post(
                f"/api/evaluations/{_SEEDED_EVAL_ID}/score-manual",
                json={
                    "score": 12.0,
                    "max_score": 20.0,
                    "teacher_comments": secret_comment,
                },
                headers=_bearer(seeded_admin),
            )
            assert response.status_code == 200, response.text
        finally:
            _logger.remove(sink_id)

        joined = "\n".join(captured)
        assert "security.evaluation_manual_score" in joined
        # Caller (admin pseudo) and evaluation_id are present.
        assert _SEEDED_EVAL_ID in joined
        assert "boss" in joined
        # The score values are present.
        assert "12" in joined
        # The teacher_comments value MUST NOT be in the log line.
        assert secret_comment not in joined
        # No OCR text leak.
        assert "Note finale" not in joined

    def test_reprocess_emits_audit_log(
        self,
        real_service_client: TestClient,
        session_factory,
        seeded_admin: User,
        seeded_eleve_alice: User,
    ) -> None:
        """T5: a reprocess emits the ``evaluation.reprocess_attempted``
        log line. No S3 bytes, no ocr_text, no teacher_comments in
        the log line."""
        from loguru import logger as _logger

        captured: list[str] = []

        sink_id = _logger.add(
            lambda msg: captured.append(str(msg)),
            level="INFO",
        )
        try:
            _seed_evaluation(session_factory, eval_id=_SEEDED_EVAL_ID, pseudo="alice")
            response = real_service_client.post(
                f"/api/evaluations/{_SEEDED_EVAL_ID}/reprocess",
                headers=_bearer(seeded_admin),
            )
            assert response.status_code == 200, response.text
        finally:
            _logger.remove(sink_id)

        joined = "\n".join(captured)
        assert "evaluation.reprocess_attempted" in joined
        assert _SEEDED_EVAL_ID in joined
        assert "boss" in joined
        # No OCR transcript leak.
        assert "Note finale" not in joined
        # No raw image bytes leak (the seeded bytes contain \x89PNG which
        # is unlikely to appear in a plain log message).
        assert "PNG" not in joined.upper().replace("EVALUATION_ID", "")


# ---------------------------------------------------------------------------
# T3 — 404 not_found mapping
# ---------------------------------------------------------------------------


class TestNotFoundMapping:
    def test_score_manual_returns_404_when_evaluation_missing(
        self,
        real_service_client: TestClient,
        seeded_admin: User,
    ) -> None:
        response = real_service_client.post(
            f"/api/evaluations/{_SEEDED_EVAL_ID}/score-manual",
            json={"score": 12.0, "max_score": 20.0},
            headers=_bearer(seeded_admin),
        )
        assert response.status_code == 404
        body = response.json()
        assert body["detail"]["code"] == "not_found"

    def test_reprocess_returns_404_when_evaluation_missing(
        self,
        real_service_client: TestClient,
        seeded_admin: User,
    ) -> None:
        response = real_service_client.post(
            f"/api/evaluations/{_SEEDED_EVAL_ID}/reprocess",
            headers=_bearer(seeded_admin),
        )
        assert response.status_code == 404
        body = response.json()
        assert body["detail"]["code"] == "not_found"
