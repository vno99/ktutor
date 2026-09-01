"""Tests for the ``ktutor`` CLI.

We use ``typer.testing.CliRunner`` and monkey-patch the CLI's
``_build_service`` to inject a fully-wired fake service. The CLI itself
is exercised for argument parsing, output formatting and exit codes.
"""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

import pytest
from typer.testing import CliRunner

from app.cli import app
from app.core.database.models import DocumentStatus
from app.services.rag.upload_service import (
    EXIT_GENERIC_ERROR,
    EXIT_INVALID_FILE,
    EXIT_INVALID_PSEUDO,
    EXIT_OCR_FAILURE,
    EXIT_OK,
    EXIT_STORAGE_FAILURE,
    UploadError,
    UploadErrorKind,
)

runner = CliRunner()


class _StubService:
    """Acts as ``UploadService`` for the CLI without touching real services."""

    def __init__(self, *, behavior: str = "ok", **kwargs) -> None:
        self.behavior = behavior
        self.kwargs = kwargs
        self.calls: list[tuple[str, str, str]] = []

    def upload(self, file_path: str, pseudo: str, subject: str):
        from app.services.rag.upload_service import UploadResult

        self.calls.append((file_path, pseudo, subject))
        if self.behavior == "ok":
            return UploadResult(
                document_id=uuid.uuid4(),
                chunks_count=42,
                duration_ms=1234,
                status=DocumentStatus.INDEXED,
                collection=f"rag_{subject}_{pseudo}",
                s3_key=f"students/{pseudo}/stub",
            )
        if self.behavior == "manual_review":
            return UploadResult(
                document_id=uuid.uuid4(),
                chunks_count=0,
                duration_ms=500,
                status=DocumentStatus.MANUAL_REVIEW_NEEDED,
                collection="",
                s3_key="students/ali/stub",
                ocr_confidence=0.2,
            )
        if self.behavior == "invalid_pseudo":
            raise UploadError(UploadErrorKind.INVALID_PSEUDO, "Pseudo 'bad' invalide.")
        if self.behavior == "invalid_file":
            raise UploadError(UploadErrorKind.INVALID_FILE, "Extension '.exe' non supportée.")
        if self.behavior == "ocr_failure":
            raise UploadError(UploadErrorKind.OCR_FAILURE, "OCR 503")
        if self.behavior == "storage":
            raise UploadError(UploadErrorKind.STORAGE_FAILURE, "ChromaDB down")
        if self.behavior == "generic":
            raise RuntimeError("kaboom")
        raise RuntimeError(f"unknown behavior: {self.behavior}")


@pytest.fixture()
def stubbed_service(monkeypatch: pytest.MonkeyPatch):
    """Patch ``_build_service`` so the CLI uses our stub."""
    holder: dict[str, _StubService] = {}

    def _factory(behavior: str = "ok"):
        stub = _StubService(behavior=behavior)
        holder["svc"] = stub
        monkeypatch.setattr("app.cli._build_service", lambda: stub)
        return stub

    return _factory, holder


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestHappyPath:
    def test_upload_returns_zero(self, sample_pdf_path: Path, stubbed_service) -> None:
        factory, holder = stubbed_service
        factory("ok")
        result = runner.invoke(
            app,
            ["upload", str(sample_pdf_path), "--pseudo", "ali", "--subject", "maths"],
        )
        assert result.exit_code == EXIT_OK, result.stdout
        # Service was called with the right args.
        assert holder["svc"].calls == [(str(sample_pdf_path), "ali", "maths")]

    def test_json_output_is_valid(self, sample_pdf_path: Path, stubbed_service) -> None:
        factory, _ = stubbed_service
        factory("ok")
        result = runner.invoke(
            app,
            [
                "upload",
                str(sample_pdf_path),
                "--pseudo",
                "ali",
                "--subject",
                "maths",
                "--json",
            ],
        )
        assert result.exit_code == EXIT_OK
        # ``rich.console.print_json`` pretty-prints multi-line JSON.
        # Find the first ``{`` and the matching closing ``}`` and parse.
        text = result.stdout
        start = text.find("{")
        assert start != -1, text
        # Walk forward to the matching close, handling nesting.
        depth = 0
        end = -1
        for i in range(start, len(text)):
            ch = text[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        assert end != -1, text
        payload = json.loads(text[start:end])
        assert payload["status"] == "indexed"
        assert payload["chunks_count"] == 42
        assert payload["collection"] == "rag_maths_ali"

    def test_manual_review_still_returns_zero(self, sample_pdf_path: Path, stubbed_service) -> None:
        factory, _ = stubbed_service
        factory("manual_review")
        result = runner.invoke(
            app,
            ["upload", str(sample_pdf_path), "--pseudo", "ali", "--subject", "maths"],
        )
        assert result.exit_code == EXIT_OK


class TestExitCodes:
    def test_invalid_pseudo_returns_5(self, sample_pdf_path: Path, stubbed_service) -> None:
        factory, _ = stubbed_service
        factory("invalid_pseudo")
        result = runner.invoke(
            app,
            ["upload", str(sample_pdf_path), "--pseudo", "bad-pseudo", "--subject", "maths"],
        )
        assert result.exit_code == EXIT_INVALID_PSEUDO

    def test_invalid_file_returns_2(self, sample_pdf_path: Path, stubbed_service) -> None:
        factory, _ = stubbed_service
        factory("invalid_file")
        result = runner.invoke(
            app,
            ["upload", str(sample_pdf_path), "--pseudo", "ali", "--subject", "maths"],
        )
        assert result.exit_code == EXIT_INVALID_FILE

    def test_ocr_failure_returns_3(self, sample_pdf_path: Path, stubbed_service) -> None:
        factory, _ = stubbed_service
        factory("ocr_failure")
        result = runner.invoke(
            app,
            ["upload", str(sample_pdf_path), "--pseudo", "ali", "--subject", "maths"],
        )
        assert result.exit_code == EXIT_OCR_FAILURE

    def test_storage_failure_returns_4(self, sample_pdf_path: Path, stubbed_service) -> None:
        factory, _ = stubbed_service
        factory("storage")
        result = runner.invoke(
            app,
            ["upload", str(sample_pdf_path), "--pseudo", "ali", "--subject", "maths"],
        )
        assert result.exit_code == EXIT_STORAGE_FAILURE

    def test_generic_exception_returns_1(self, sample_pdf_path: Path, stubbed_service) -> None:
        factory, _ = stubbed_service
        factory("generic")
        result = runner.invoke(
            app,
            ["upload", str(sample_pdf_path), "--pseudo", "ali", "--subject", "maths"],
        )
        assert result.exit_code == EXIT_GENERIC_ERROR


class TestInitFailure:
    def test_build_service_failure_returns_4(
        self, sample_pdf_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # _build_service raises before the service is constructed; e.g. S3 down.
        def _boom():
            raise ConnectionError("S3 unreachable")

        monkeypatch.setattr("app.cli._build_service", _boom)
        result = runner.invoke(
            app,
            ["upload", str(sample_pdf_path), "--pseudo", "ali", "--subject", "maths"],
        )
        assert result.exit_code == EXIT_STORAGE_FAILURE


class TestCliSurface:
    def test_help_screen_works(self) -> None:
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "upload" in result.stdout

    def test_upload_help_works(self) -> None:
        result = runner.invoke(app, ["upload", "--help"])
        assert result.exit_code == 0
        # Use result.output (stdout+stderr combined) rather than result.stdout:
        # in CI environments with no TTY, typer may route help to stderr,
        # and rich emits ANSI escape codes that pollute the substring search.
        # Strip ANSI before asserting.
        text = re.sub(r"\x1b\[[0-9;]*m", "", result.output)
        assert "--pseudo" in text
        assert "--subject" in text

    def test_help_lists_chat_command(self) -> None:
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "chat" in result.stdout

    def test_chat_help_works(self) -> None:
        result = runner.invoke(app, ["chat", "--help"])
        assert result.exit_code == 0
        text = re.sub(r"\x1b\[[0-9;]*m", "", result.output)
        assert "--pseudo" in text
        assert "--subject" in text
        assert "--question" in text


# ---------------------------------------------------------------------------
# Chat command tests (s02)
# ---------------------------------------------------------------------------


class _StubChatService:
    """Acts as ``MathsAgent`` for the CLI without touching real services."""

    def __init__(self, *, behavior: str = "ok") -> None:
        self.behavior = behavior
        self.calls: list[tuple[str, str, str]] = []

    def ask(self, subject: str, pseudo: str, question: str):
        from app.services.agents.maths_agent import ChatResult, SourceCitation

        self.calls.append((subject, pseudo, question))
        if self.behavior == "ok":
            return ChatResult(
                answer="Une dérivée mesure la pente. [source: cours.pdf, chunk 0]",
                sources=[SourceCitation(filename="cours.pdf", chunk_index=0)],
            )
        if self.behavior == "no_document":
            return ChatResult(answer="Je n'ai rien trouvé.", sources=[])
        if self.behavior == "invalid_pseudo":
            from app.services.rag.chroma_store import InvalidPseudoError

            raise InvalidPseudoError("Pseudo 'bad' invalide.")
        if self.behavior == "generic":
            raise RuntimeError("kaboom")
        raise RuntimeError(f"unknown behavior: {self.behavior}")


@pytest.fixture()
def stubbed_chat_service(monkeypatch: pytest.MonkeyPatch):
    """Patch ``_build_chat_service`` so the CLI uses our chat stub."""
    holder: dict[str, _StubChatService] = {}

    def _factory(behavior: str = "ok"):
        stub = _StubChatService(behavior=behavior)
        holder["svc"] = stub
        monkeypatch.setattr("app.cli._build_chat_service", lambda: stub)
        return stub

    return _factory, holder


class TestChat:
    def test_chat_returns_zero_with_answer(self, stubbed_chat_service) -> None:
        factory, holder = stubbed_chat_service
        factory("ok")
        result = runner.invoke(
            app,
            [
                "chat",
                "--pseudo",
                "ali",
                "--subject",
                "maths",
                "--question",
                "Qu'est-ce qu'une dérivée ?",
            ],
        )
        assert result.exit_code == EXIT_OK, result.stdout
        assert holder["svc"].calls == [("maths", "ali", "Qu'est-ce qu'une dérivée ?")]

    def test_chat_returns_zero_with_no_document(self, stubbed_chat_service) -> None:
        factory, _ = stubbed_chat_service
        factory("no_document")
        result = runner.invoke(
            app,
            [
                "chat",
                "--pseudo",
                "ali",
                "--subject",
                "maths",
                "--question",
                "Quoi ?",
            ],
        )
        assert result.exit_code == EXIT_OK
        # The fallback message must be present in the output.
        text = re.sub(r"\x1b\[[0-9;]*m", "", result.output)
        assert "Je n'ai rien trouvé" in text

    def test_chat_json_output_is_valid(self, stubbed_chat_service) -> None:
        factory, _ = stubbed_chat_service
        factory("ok")
        result = runner.invoke(
            app,
            [
                "chat",
                "--pseudo",
                "ali",
                "--subject",
                "maths",
                "--question",
                "Q?",
                "--json",
            ],
        )
        assert result.exit_code == EXIT_OK
        text = result.stdout
        start = text.find("{")
        assert start != -1, text
        depth = 0
        end = -1
        for i in range(start, len(text)):
            ch = text[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        assert end != -1, text
        payload = json.loads(text[start:end])
        assert "answer" in payload
        assert "sources" in payload
        assert payload["sources"][0]["filename"] == "cours.pdf"
        assert payload["sources"][0]["chunk_index"] == 0

    def test_chat_invalid_pseudo_returns_5(self, stubbed_chat_service) -> None:
        factory, _ = stubbed_chat_service
        factory("invalid_pseudo")
        result = runner.invoke(
            app,
            [
                "chat",
                "--pseudo",
                "bad-pseudo",
                "--subject",
                "maths",
                "--question",
                "Q?",
            ],
        )
        assert result.exit_code == EXIT_INVALID_PSEUDO

    def test_chat_generic_exception_returns_1(self, stubbed_chat_service) -> None:
        factory, _ = stubbed_chat_service
        factory("generic")
        result = runner.invoke(
            app,
            [
                "chat",
                "--pseudo",
                "ali",
                "--subject",
                "maths",
                "--question",
                "Q?",
            ],
        )
        assert result.exit_code == EXIT_GENERIC_ERROR

    # --- s05: French subject + supervisor wiring ----------------------------

    def test_chat_with_francais_subject_routes_to_french_agent(
        self, stubbed_chat_service
    ) -> None:
        """AC1 — ``--subject francais`` is wired to the supervisor/agent."""
        factory, holder = stubbed_chat_service
        factory("ok")
        result = runner.invoke(
            app,
            [
                "chat",
                "--pseudo",
                "ali",
                "--subject",
                "francais",
                "--question",
                "C'est quoi un métaplasme ?",
            ],
        )
        assert result.exit_code == EXIT_OK, result.stdout
        # The supervisor must have forwarded the call with subject=francais.
        assert holder["svc"].calls == [
            ("francais", "ali", "C'est quoi un métaplasme ?")
        ]

    def test_chat_with_maths_subject_still_works(self, stubbed_chat_service) -> None:
        """Regression — the s02 maths path must keep working unchanged."""
        factory, holder = stubbed_chat_service
        factory("ok")
        result = runner.invoke(
            app,
            [
                "chat",
                "--pseudo",
                "ali",
                "--subject",
                "maths",
                "--question",
                "Qu'est-ce qu'une dérivée ?",
            ],
        )
        assert result.exit_code == EXIT_OK, result.stdout
        assert holder["svc"].calls == [
            ("maths", "ali", "Qu'est-ce qu'une dérivée ?")
        ]

    def test_chat_rejects_unknown_subject(self, stubbed_chat_service) -> None:
        """D3 — ``--subject histoire`` must be refused at the CLI."""
        factory, holder = stubbed_chat_service
        factory("ok")
        result = runner.invoke(
            app,
            [
                "chat",
                "--pseudo",
                "ali",
                "--subject",
                "histoire",
                "--question",
                "Q?",
            ],
        )
        # Defense in depth: the CLI rejects BEFORE the service is built,
        # so the stub's ask() must never have been called.
        assert result.exit_code == EXIT_INVALID_PSEUDO
        assert holder["svc"].calls == []

    def test_chat_francais_with_no_document_returns_no_document_message(
        self, stubbed_chat_service
    ) -> None:
        """AC5 — a French question on an empty French collection returns the
        no-document message (NOT a maths fallback).
        """
        factory, holder = stubbed_chat_service
        factory("no_document")
        result = runner.invoke(
            app,
            [
                "chat",
                "--pseudo",
                "ali",
                "--subject",
                "francais",
                "--question",
                "Q?",
            ],
        )
        assert result.exit_code == EXIT_OK
        assert holder["svc"].calls == [("francais", "ali", "Q?")]
        text = re.sub(r"\x1b\[[0-9;]*m", "", result.output)
        assert "Je n'ai rien trouvé" in text


# ---------------------------------------------------------------------------
# generate-qcm command tests (s03)
# ---------------------------------------------------------------------------


class _StubQcmGenerator:
    """Acts as ``QcmGenerator`` for the CLI without touching real services."""

    def __init__(self, *, behavior: str = "ok") -> None:
        self.behavior = behavior
        self.calls: list[tuple[str, str, str, int | None]] = []

    def generate(self, pseudo: str, subject: str, document_id: str, n: int | None = None):
        from app.services.exercises.qcm_generator import (
            QcmGenerationError,
            QcmGenerationResult,
            QcmQuestion,
        )

        self.calls.append((pseudo, subject, document_id, n))
        if self.behavior == "ok":
            return QcmGenerationResult(
                exercise_id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
                questions=[
                    QcmQuestion(question=f"Q{i + 1} ?", options=["a", "b", "c", "d"], correct_index=0)
                    for i in range(3)
                ],
                raw='{"questions":[]}',
            )
        if self.behavior == "document_not_found":
            raise QcmGenerationError(
                "document_not_found",
                "Document 00000000-0000-0000-0000-000000000000 introuvable pour le pseudo 'ali'.",
            )
        if self.behavior == "no_chunks":
            raise QcmGenerationError("no_chunks", "Aucun extrait indexé.")
        if self.behavior == "malformed_output":
            raise QcmGenerationError("malformed_output", "Le LLM n'a pas renvoyé un JSON valide.")
        raise RuntimeError(f"unknown behavior: {self.behavior}")


@pytest.fixture()
def stubbed_qcm_service(monkeypatch: pytest.MonkeyPatch):
    """Patch ``_build_qcm_service`` so the CLI uses our QCM stub."""
    holder: dict[str, _StubQcmGenerator] = {}

    def _factory(behavior: str = "ok"):
        stub = _StubQcmGenerator(behavior=behavior)
        holder["svc"] = stub
        monkeypatch.setattr("app.cli._build_qcm_service", lambda: stub)
        return stub

    return _factory, holder


class TestGenerateQcm:
    def test_generate_qcm_returns_zero_with_n_questions(
        self, stubbed_qcm_service
    ) -> None:
        factory, holder = stubbed_qcm_service
        factory("ok")
        result = runner.invoke(
            app,
            [
                "generate-qcm",
                "--pseudo",
                "ali",
                "--document-id",
                "11111111-1111-1111-1111-111111111111",
                "--n",
                "3",
                "--subject",
                "maths",
            ],
        )
        assert result.exit_code == EXIT_OK, result.stdout
        assert holder["svc"].calls == [
            ("ali", "maths", "11111111-1111-1111-1111-111111111111", 3)
        ]

    def test_generate_qcm_json_output_is_valid(self, stubbed_qcm_service) -> None:
        factory, _ = stubbed_qcm_service
        factory("ok")
        result = runner.invoke(
            app,
            [
                "generate-qcm",
                "--pseudo",
                "ali",
                "--document-id",
                "11111111-1111-1111-1111-111111111111",
                "--n",
                "3",
                "--json",
            ],
        )
        assert result.exit_code == EXIT_OK
        text = result.stdout
        start = text.find("{")
        assert start != -1, text
        depth = 0
        end = -1
        for i in range(start, len(text)):
            ch = text[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        assert end != -1, text
        payload = json.loads(text[start:end])
        assert payload["exercise_id"] == "22222222-2222-2222-2222-222222222222"
        assert len(payload["questions"]) == 3
        assert all(len(q["options"]) == 4 for q in payload["questions"])
        assert all(0 <= q["correct_index"] <= 3 for q in payload["questions"])

    def test_generate_qcm_document_not_found_returns_5(self, stubbed_qcm_service) -> None:
        factory, _ = stubbed_qcm_service
        factory("document_not_found")
        result = runner.invoke(
            app,
            [
                "generate-qcm",
                "--pseudo",
                "ali",
                "--document-id",
                "00000000-0000-0000-0000-000000000000",
                "--n",
                "3",
            ],
        )
        assert result.exit_code == 5

    def test_generate_qcm_no_chunks_returns_5(self, stubbed_qcm_service) -> None:
        factory, _ = stubbed_qcm_service
        factory("no_chunks")
        result = runner.invoke(
            app,
            [
                "generate-qcm",
                "--pseudo",
                "ali",
                "--document-id",
                "11111111-1111-1111-1111-111111111111",
                "--n",
                "3",
            ],
        )
        assert result.exit_code == 5

    def test_generate_qcm_malformed_output_returns_4(self, stubbed_qcm_service) -> None:
        factory, _ = stubbed_qcm_service
        factory("malformed_output")
        result = runner.invoke(
            app,
            [
                "generate-qcm",
                "--pseudo",
                "ali",
                "--document-id",
                "11111111-1111-1111-1111-111111111111",
                "--n",
                "3",
            ],
        )
        assert result.exit_code == 4

    def test_generate_qcm_help_works(self) -> None:
        result = runner.invoke(app, ["generate-qcm", "--help"])
        assert result.exit_code == 0
        text = re.sub(r"\x1b\[[0-9;]*m", "", result.output)
        assert "--pseudo" in text
        assert "--document-id" in text
        assert "--n" in text

    def test_help_lists_generate_qcm_command(self) -> None:
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "generate-qcm" in result.stdout


# ---------------------------------------------------------------------------
# submit-qcm command tests (s04)
# ---------------------------------------------------------------------------


class _StubQcmGrader:
    """Acts as ``QcmGrader`` for the CLI without touching real services."""

    def __init__(self, *, behavior: str = "ok") -> None:
        self.behavior = behavior
        self.calls: list[tuple[str, str, list[int]]] = []

    def grade(self, pseudo: str, exercise_id: str, raw_answers: list[int]):
        from app.services.exercises.qcm_grader import GradingResult, QcmGradingError

        self.calls.append((pseudo, exercise_id, list(raw_answers)))
        if self.behavior == "ok":
            return GradingResult(
                is_success=True,
                correct_count=3,
                total=3,
                feedback="Toutes les réponses sont correctes.",
                attempt_id=uuid.UUID("33333333-3333-3333-3333-333333333333"),
                attempt_number=1,
            )
        if self.behavior == "wrong":
            return GradingResult(
                is_success=False,
                correct_count=2,
                total=3,
                feedback="2/3 réponses correctes.",
                attempt_id=uuid.UUID("44444444-4444-4444-4444-444444444444"),
                attempt_number=1,
            )
        if self.behavior == "invalid_answers":
            raise QcmGradingError("invalid_answers", "Reponses invalides.")
        if self.behavior == "cross_tenant":
            raise QcmGradingError("cross_tenant", "Exercise introuvable pour 'bob'.")
        if self.behavior == "exercise_not_found":
            raise QcmGradingError("exercise_not_found", "Exercise introuvable.")
        if self.behavior == "invalid_exercise":
            raise QcmGradingError("invalid_exercise", "Exercise mal forme.")
        raise RuntimeError(f"unknown behavior: {self.behavior}")


@pytest.fixture()
def stubbed_qcm_grader(monkeypatch: pytest.MonkeyPatch):
    """Patch ``_build_grader_service`` so the CLI uses our QCM grader stub."""
    holder: dict[str, _StubQcmGrader] = {}

    def _factory(behavior: str = "ok"):
        stub = _StubQcmGrader(behavior=behavior)
        holder["svc"] = stub
        monkeypatch.setattr("app.cli._build_grader_service", lambda: stub)
        return stub

    return _factory, holder


class TestSubmitQcm:
    def test_submit_qcm_returns_zero_with_success(self, stubbed_qcm_grader) -> None:
        factory, holder = stubbed_qcm_grader
        factory("ok")
        result = runner.invoke(
            app,
            [
                "submit-qcm",
                "--pseudo",
                "ali",
                "--exercise-id",
                "11111111-1111-1111-1111-111111111111",
                "--answers",
                "[0,0,0]",
            ],
        )
        assert result.exit_code == EXIT_OK, result.stdout
        assert holder["svc"].calls == [
            ("ali", "11111111-1111-1111-1111-111111111111", [0, 0, 0])
        ]

    def test_submit_qcm_json_output_is_valid(self, stubbed_qcm_grader) -> None:
        factory, _ = stubbed_qcm_grader
        factory("ok")
        result = runner.invoke(
            app,
            [
                "submit-qcm",
                "--pseudo",
                "ali",
                "--exercise-id",
                "11111111-1111-1111-1111-111111111111",
                "--answers",
                "[0,0,0]",
                "--json",
            ],
        )
        assert result.exit_code == EXIT_OK
        text = result.stdout
        start = text.find("{")
        assert start != -1, text
        depth = 0
        end = -1
        for i in range(start, len(text)):
            ch = text[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        assert end != -1, text
        payload = json.loads(text[start:end])
        assert payload["is_success"] is True
        assert payload["correct_count"] == 3
        assert payload["total"] == 3
        assert payload["attempt_id"] == "33333333-3333-3333-3333-333333333333"

    def test_submit_qcm_invalid_answers_returns_4(self, stubbed_qcm_grader) -> None:
        factory, _ = stubbed_qcm_grader
        factory("invalid_answers")
        result = runner.invoke(
            app,
            [
                "submit-qcm",
                "--pseudo",
                "ali",
                "--exercise-id",
                "11111111-1111-1111-1111-111111111111",
                "--answers",
                "[0,0,0]",
            ],
        )
        assert result.exit_code == 4

    def test_submit_qcm_invalid_exercise_returns_4(self, stubbed_qcm_grader) -> None:
        factory, _ = stubbed_qcm_grader
        factory("invalid_exercise")
        result = runner.invoke(
            app,
            [
                "submit-qcm",
                "--pseudo",
                "ali",
                "--exercise-id",
                "11111111-1111-1111-1111-111111111111",
                "--answers",
                "[0,0,0]",
            ],
        )
        assert result.exit_code == 4

    def test_submit_qcm_cross_tenant_returns_5(self, stubbed_qcm_grader) -> None:
        factory, _ = stubbed_qcm_grader
        factory("cross_tenant")
        result = runner.invoke(
            app,
            [
                "submit-qcm",
                "--pseudo",
                "bob",
                "--exercise-id",
                "11111111-1111-1111-1111-111111111111",
                "--answers",
                "[0,0,0]",
            ],
        )
        assert result.exit_code == 5

    def test_submit_qcm_exercise_not_found_returns_5(self, stubbed_qcm_grader) -> None:
        factory, _ = stubbed_qcm_grader
        factory("exercise_not_found")
        result = runner.invoke(
            app,
            [
                "submit-qcm",
                "--pseudo",
                "ali",
                "--exercise-id",
                "00000000-0000-0000-0000-000000000000",
                "--answers",
                "[0,0,0]",
            ],
        )
        assert result.exit_code == 5

    def test_submit_qcm_malformed_json_answers_returns_4(self, stubbed_qcm_grader) -> None:
        # Answers must be JSON — passing a non-JSON string yields exit 4
        # before we even reach the grader.
        factory, holder = stubbed_qcm_grader
        factory("ok")
        result = runner.invoke(
            app,
            [
                "submit-qcm",
                "--pseudo",
                "ali",
                "--exercise-id",
                "11111111-1111-1111-1111-111111111111",
                "--answers",
                "not-json",
            ],
        )
        assert result.exit_code == 4
        # The grader must NOT have been called.
        assert holder["svc"].calls == []

    def test_submit_qcm_help_works(self) -> None:
        result = runner.invoke(app, ["submit-qcm", "--help"])
        assert result.exit_code == 0
        text = re.sub(r"\x1b\[[0-9;]*m", "", result.output)
        assert "--pseudo" in text
        assert "--exercise-id" in text
        assert "--answers" in text

    def test_help_lists_submit_qcm_command(self) -> None:
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "submit-qcm" in result.stdout


# ---------------------------------------------------------------------------
# generate-exercise command tests (s06 — probleme, redaction)
# ---------------------------------------------------------------------------


class _StubFreeGenerator:
    """Acts as ``FreeGenerator`` for the CLI without touching real services."""

    def __init__(self, *, behavior: str = "ok_probleme") -> None:
        self.behavior = behavior
        # (pseudo, subject, type, document_id, topic, difficulty)
        self.calls: list[tuple[str, str, str, str, str, str | None]] = []

    def generate(
        self,
        pseudo: str,
        subject: str,
        type: str,
        document_id: str,
        topic: str,
        difficulty: str | None = None,
    ):
        from app.services.exercises.free_generator import (
            FreeGenerationError,
            FreeGenerationResult,
            ProblemeStatement,
            RedactionStatement,
        )

        self.calls.append((pseudo, subject, type, document_id, topic, difficulty))
        if self.behavior == "ok_probleme":
            return FreeGenerationResult(
                exercise_id=uuid.UUID("55555555-5555-5555-5555-555555555555"),
                exercise=ProblemeStatement(
                    type="probleme",
                    statement=(
                        "Un jardinier plante 24 fleurs en 3 rangées égales. "
                        "Combien de fleurs par rangée ?"
                    ),
                    expected_answer=(
                        "Étape 1 : identifier la donnée (24 fleurs, 3 rangées).\n"
                        "Étape 2 : effectuer la division 24 / 3.\n"
                        "Étape 3 : conclure. Réponse : 8 fleurs par rangée."
                    ),
                    grading_criteria=[
                        "L'élève identifie la division",
                        "L'élève effectue le calcul",
                        "L'élève énonce la réponse",
                    ],
                ),
                raw="{}",
            )
        if self.behavior == "ok_redaction":
            return FreeGenerationResult(
                exercise_id=uuid.UUID("66666666-6666-6666-6666-666666666666"),
                exercise=RedactionStatement(
                    type="redaction",
                    statement=(
                        "Rédige un texte argumentatif de 200 à 300 mots sur le thème "
                        "de l'amitié."
                    ),
                    expected_answer=(
                        "Plan détaillé : introduction (présentation du sujet, thèse), "
                        "développement (deux arguments principaux avec exemples), "
                        "conclusion (bilan et ouverture). Le corrigé type attend un "
                        "texte structuré, cohérent et bien orthographié, illustrant "
                        "chaque argument par un exemple concret tiré de la vie quotidienne."
                    ),
                    grading_criteria=[
                        "L'élève respecte la fourchette 200-300 mots",
                        "L'élève utilise un registre argumentatif",
                    ],
                    min_words=200,
                    max_words=300,
                    target_register="argumentatif",
                ),
                raw="{}",
            )
        if self.behavior == "document_not_found":
            raise FreeGenerationError(
                "document_not_found",
                "Document 00000000-0000-0000-0000-000000000000 introuvable pour 'ali'.",
            )
        if self.behavior == "no_chunks":
            raise FreeGenerationError("no_chunks", "Aucun extrait indexé.")
        if self.behavior == "malformed_output":
            raise FreeGenerationError("malformed_output", "Le LLM n'a pas renvoyé un JSON valide.")
        if self.behavior == "invalid_difficulty":
            raise FreeGenerationError("invalid_difficulty", "Difficulté 'expert' inconnue.")
        if self.behavior == "invalid_type":
            raise FreeGenerationError("invalid_type", "Type 'qcm' non supporté.")
        raise RuntimeError(f"unknown behavior: {self.behavior}")


@pytest.fixture()
def stubbed_free_service(monkeypatch: pytest.MonkeyPatch):
    """Patch ``_build_free_service`` so the CLI uses our free-style stub."""
    holder: dict[str, _StubFreeGenerator] = {}

    def _factory(behavior: str = "ok_probleme"):
        stub = _StubFreeGenerator(behavior=behavior)
        holder["svc"] = stub
        monkeypatch.setattr("app.cli._build_free_service", lambda: stub)
        return stub

    return _factory, holder


class TestGenerateExercise:
    def test_generate_exercise_probleme_returns_statement_expected_answer_grading_criteria(
        self, stubbed_free_service
    ) -> None:
        factory, holder = stubbed_free_service
        factory("ok_probleme")
        result = runner.invoke(
            app,
            [
                "generate-exercise",
                "--pseudo",
                "ali",
                "--subject",
                "maths",
                "--type",
                "probleme",
                "--document-id",
                "11111111-1111-1111-1111-111111111111",
                "--topic",
                "fractions",
                "--difficulty",
                "facile",
            ],
        )
        assert result.exit_code == EXIT_OK, result.stdout
        # Service was called with the right args (CLI defaults difficulty to
        # the configured value, here we passed it explicitly).
        assert holder["svc"].calls == [
            ("ali", "maths", "probleme", "11111111-1111-1111-1111-111111111111", "fractions", "facile")
        ]

    def test_generate_exercise_redaction_returns_statement_expected_answer_grading_criteria(
        self, stubbed_free_service
    ) -> None:
        factory, holder = stubbed_free_service
        factory("ok_redaction")
        result = runner.invoke(
            app,
            [
                "generate-exercise",
                "--pseudo",
                "ali",
                "--subject",
                "francais",
                "--type",
                "redaction",
                "--document-id",
                "11111111-1111-1111-1111-111111111111",
                "--topic",
                "amitié",
            ],
        )
        assert result.exit_code == EXIT_OK, result.stdout
        # Default difficulty (moyen) is filled in by the CLI.
        assert holder["svc"].calls == [
            ("ali", "francais", "redaction", "11111111-1111-1111-1111-111111111111", "amitié", "moyen")
        ]

    def test_generate_exercise_json_output_is_valid_for_both_types(
        self, stubbed_free_service
    ) -> None:
        factory, _ = stubbed_free_service
        factory("ok_probleme")
        result = runner.invoke(
            app,
            [
                "generate-exercise",
                "--pseudo",
                "ali",
                "--subject",
                "maths",
                "--type",
                "probleme",
                "--document-id",
                "11111111-1111-1111-1111-111111111111",
                "--topic",
                "fractions",
                "--json",
            ],
        )
        assert result.exit_code == EXIT_OK
        text = result.stdout
        start = text.find("{")
        assert start != -1, text
        depth = 0
        end = -1
        for i in range(start, len(text)):
            ch = text[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        assert end != -1, text
        payload = json.loads(text[start:end])
        assert payload["exercise_id"] == "55555555-5555-5555-5555-555555555555"
        ex = payload["exercise"]
        assert ex["type"] == "probleme"
        assert "statement" in ex and len(ex["statement"]) > 0
        assert "expected_answer" in ex and len(ex["expected_answer"]) > 0
        assert isinstance(ex["grading_criteria"], list) and len(ex["grading_criteria"]) >= 1

    def test_generate_exercise_document_not_found_returns_5(self, stubbed_free_service) -> None:
        factory, _ = stubbed_free_service
        factory("document_not_found")
        result = runner.invoke(
            app,
            [
                "generate-exercise",
                "--pseudo",
                "ali",
                "--subject",
                "maths",
                "--type",
                "probleme",
                "--document-id",
                "00000000-0000-0000-0000-000000000000",
                "--topic",
                "x",
            ],
        )
        assert result.exit_code == 5

    def test_generate_exercise_malformed_output_returns_4(self, stubbed_free_service) -> None:
        factory, _ = stubbed_free_service
        factory("malformed_output")
        result = runner.invoke(
            app,
            [
                "generate-exercise",
                "--pseudo",
                "ali",
                "--subject",
                "maths",
                "--type",
                "probleme",
                "--document-id",
                "11111111-1111-1111-1111-111111111111",
                "--topic",
                "x",
            ],
        )
        assert result.exit_code == 4

    def test_generate_exercise_invalid_difficulty_returns_5(self, stubbed_free_service) -> None:
        factory, _ = stubbed_free_service
        factory("invalid_difficulty")
        result = runner.invoke(
            app,
            [
                "generate-exercise",
                "--pseudo",
                "ali",
                "--subject",
                "maths",
                "--type",
                "probleme",
                "--document-id",
                "11111111-1111-1111-1111-111111111111",
                "--topic",
                "x",
                "--difficulty",
                "expert",
            ],
        )
        assert result.exit_code == 5

    def test_generate_exercise_invalid_type_returns_5(self, stubbed_free_service) -> None:
        factory, _ = stubbed_free_service
        factory("invalid_type")
        result = runner.invoke(
            app,
            [
                "generate-exercise",
                "--pseudo",
                "ali",
                "--subject",
                "maths",
                "--type",
                "qcm",
                "--document-id",
                "11111111-1111-1111-1111-111111111111",
                "--topic",
                "x",
            ],
        )
        assert result.exit_code == 5

    def test_generate_exercise_help_works(self) -> None:
        result = runner.invoke(app, ["generate-exercise", "--help"])
        assert result.exit_code == 0
        text = re.sub(r"\x1b\[[0-9;]*m", "", result.output)
        assert "--pseudo" in text
        assert "--type" in text
        assert "--document-id" in text
        assert "--topic" in text

    def test_help_lists_generate_exercise_command(self) -> None:
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "generate-exercise" in result.stdout


# ---------------------------------------------------------------------------
# generate-flashcards command tests (s06b)
# ---------------------------------------------------------------------------


class _StubFlashcardGenerator:
    """Acts as ``FlashcardGenerator`` for the CLI without touching real services."""

    def __init__(self, *, behavior: str = "ok") -> None:
        self.behavior = behavior
        # (pseudo, subject, document_id, n)
        self.calls: list[tuple[str, str, str, int | None]] = []

    def generate(
        self,
        pseudo: str,
        subject: str,
        document_id: str,
        n: int | None = None,
    ):
        from app.services.exercises.flashcard_generator import (
            FlashcardDeck,
            FlashcardGenerationError,
            FlashcardGenerationResult,
            FlashcardSchema,
        )

        self.calls.append((pseudo, subject, document_id, n))
        if self.behavior == "ok":
            cards = [
                FlashcardSchema(front=f"Q{i + 1} ?", back=f"R{i + 1}.", topic="algebre")
                for i in range(3)
            ]
            return FlashcardGenerationResult(
                exercise_id=uuid.UUID("77777777-7777-7777-7777-777777777777"),
                deck=FlashcardDeck(type="flashcards", cards=cards),
                raw=json.dumps(
                    {
                        "type": "flashcards",
                        "cards": [c.model_dump() for c in cards],
                    }
                ),
            )
        if self.behavior == "document_not_found":
            raise FlashcardGenerationError(
                "document_not_found",
                "Document 00000000-0000-0000-0000-000000000000 introuvable pour 'ali'.",
            )
        if self.behavior == "no_chunks":
            raise FlashcardGenerationError("no_chunks", "Aucun extrait indexé.")
        if self.behavior == "malformed_output":
            raise FlashcardGenerationError(
                "malformed_output",
                "Le LLM n'a pas renvoyé un deck valide après retry.",
            )
        if self.behavior == "invalid_input":
            raise FlashcardGenerationError("invalid_input", "n=50 hors bornes [1, 30].")
        raise RuntimeError(f"unknown behavior: {self.behavior}")


@pytest.fixture()
def stubbed_flashcard_service(monkeypatch: pytest.MonkeyPatch):
    """Patch ``_build_flashcard_service`` so the CLI uses our flashcard stub."""
    holder: dict[str, _StubFlashcardGenerator] = {}

    def _factory(behavior: str = "ok"):
        stub = _StubFlashcardGenerator(behavior=behavior)
        holder["svc"] = stub
        monkeypatch.setattr("app.cli._build_flashcard_service", lambda: stub)
        return stub

    return _factory, holder


class TestGenerateFlashcards:
    def test_generate_flashcards_returns_deck_with_front_back_topic(
        self, stubbed_flashcard_service
    ) -> None:
        factory, holder = stubbed_flashcard_service
        factory("ok")
        result = runner.invoke(
            app,
            [
                "generate-flashcards",
                "--pseudo",
                "ali",
                "--subject",
                "maths",
                "--document-id",
                "11111111-1111-1111-1111-111111111111",
                "--n",
                "3",
            ],
        )
        assert result.exit_code == EXIT_OK, result.stdout
        assert holder["svc"].calls == [
            ("ali", "maths", "11111111-1111-1111-1111-111111111111", 3)
        ]

    def test_generate_flashcards_json_output_is_valid(
        self, stubbed_flashcard_service
    ) -> None:
        factory, _ = stubbed_flashcard_service
        factory("ok")
        result = runner.invoke(
            app,
            [
                "generate-flashcards",
                "--pseudo",
                "ali",
                "--subject",
                "maths",
                "--document-id",
                "11111111-1111-1111-1111-111111111111",
                "--n",
                "3",
                "--json",
            ],
        )
        assert result.exit_code == EXIT_OK
        text = result.stdout
        start = text.find("{")
        assert start != -1, text
        depth = 0
        end = -1
        for i in range(start, len(text)):
            ch = text[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        assert end != -1, text
        payload = json.loads(text[start:end])
        assert payload["exercise_id"] == "77777777-7777-7777-7777-777777777777"
        assert "deck" in payload
        assert len(payload["deck"]["cards"]) == 3
        for c in payload["deck"]["cards"]:
            assert "front" in c and len(c["front"]) > 0
            assert "back" in c and len(c["back"]) > 0

    def test_generate_flashcards_document_not_found_returns_5(
        self, stubbed_flashcard_service
    ) -> None:
        factory, _ = stubbed_flashcard_service
        factory("document_not_found")
        result = runner.invoke(
            app,
            [
                "generate-flashcards",
                "--pseudo",
                "ali",
                "--subject",
                "maths",
                "--document-id",
                "00000000-0000-0000-0000-000000000000",
                "--n",
                "3",
            ],
        )
        assert result.exit_code == 5

    def test_generate_flashcards_no_chunks_returns_5(
        self, stubbed_flashcard_service
    ) -> None:
        factory, _ = stubbed_flashcard_service
        factory("no_chunks")
        result = runner.invoke(
            app,
            [
                "generate-flashcards",
                "--pseudo",
                "ali",
                "--subject",
                "maths",
                "--document-id",
                "11111111-1111-1111-1111-111111111111",
                "--n",
                "3",
            ],
        )
        assert result.exit_code == 5

    def test_generate_flashcards_malformed_output_returns_4(
        self, stubbed_flashcard_service
    ) -> None:
        factory, _ = stubbed_flashcard_service
        factory("malformed_output")
        result = runner.invoke(
            app,
            [
                "generate-flashcards",
                "--pseudo",
                "ali",
                "--subject",
                "maths",
                "--document-id",
                "11111111-1111-1111-1111-111111111111",
                "--n",
                "3",
            ],
        )
        assert result.exit_code == 4

    def test_generate_flashcards_invalid_n_returns_5(
        self, stubbed_flashcard_service
    ) -> None:
        factory, _ = stubbed_flashcard_service
        factory("invalid_input")
        result = runner.invoke(
            app,
            [
                "generate-flashcards",
                "--pseudo",
                "ali",
                "--subject",
                "maths",
                "--document-id",
                "11111111-1111-1111-1111-111111111111",
                "--n",
                "50",
            ],
        )
        assert result.exit_code == 5

    def test_generate_flashcards_help_works(self) -> None:
        result = runner.invoke(app, ["generate-flashcards", "--help"])
        assert result.exit_code == 0
        text = re.sub(r"\x1b\[[0-9;]*m", "", result.output)
        assert "--pseudo" in text
        assert "--subject" in text
        assert "--document-id" in text
        assert "--n" in text

    def test_help_lists_generate_flashcards_command(self) -> None:
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "generate-flashcards" in result.stdout


# ---------------------------------------------------------------------------
# submit-text command tests (s07 — free-form text grading)
# ---------------------------------------------------------------------------


class _StubTextGrader:
    """Acts as ``TextGrader`` for the CLI without touching real services."""

    def __init__(self, *, behavior: str = "ok") -> None:
        self.behavior = behavior
        self.calls: list[tuple[str, str, str]] = []

    def grade(self, pseudo: str, exercise_id: str, answer: str):
        from app.services.exercises.text_grader import (
            TextGradingError,
            TextGradingResult,
        )

        self.calls.append((pseudo, exercise_id, answer))
        if self.behavior == "ok":
            return TextGradingResult(
                is_success=True,
                feedback="Bonne réponse.",
                attempt_id=uuid.UUID("77777777-7777-7777-7777-777777777777"),
                attempt_number=1,
            )
        if self.behavior == "echec":
            return TextGradingResult(
                is_success=False,
                feedback="Réponse incomplète.",
                attempt_id=uuid.UUID("88888888-8888-8888-8888-888888888888"),
                attempt_number=1,
            )
        if self.behavior == "cross_tenant":
            raise TextGradingError(
                "cross_tenant", "Exercise introuvable pour 'bob'."
            )
        if self.behavior == "exercise_not_found":
            raise TextGradingError("exercise_not_found", "Exercise introuvable.")
        if self.behavior == "invalid_exercise_type":
            raise TextGradingError(
                "invalid_exercise_type", "Exercise de type 'qcm' refuse."
            )
        if self.behavior == "verdict_missing":
            raise TextGradingError(
                "verdict_missing", "Le service n'a pas pu analyser ta réponse."
            )
        if self.behavior == "answer_too_long":
            raise TextGradingError(
                "answer_too_long", "Réponse trop longue : 9000 caractères."
            )
        raise RuntimeError(f"unknown behavior: {self.behavior}")


@pytest.fixture()
def stubbed_text_grader(monkeypatch: pytest.MonkeyPatch):
    """Patch ``_build_text_grader_service`` so the CLI uses our stub."""
    holder: dict[str, _StubTextGrader] = {}

    def _factory(behavior: str = "ok"):
        stub = _StubTextGrader(behavior=behavior)
        holder["svc"] = stub
        monkeypatch.setattr(
            "app.cli._build_text_grader_service", lambda: stub
        )
        return stub

    return _factory, holder


class TestSubmitText:
    def test_submit_text_returns_zero_with_success(
        self, stubbed_text_grader
    ) -> None:
        factory, holder = stubbed_text_grader
        factory("ok")
        result = runner.invoke(
            app,
            [
                "submit-text",
                "--pseudo",
                "ali",
                "--exercise-id",
                "11111111-1111-1111-1111-111111111111",
                "--answer",
                "ma réponse",
            ],
        )
        assert result.exit_code == EXIT_OK, result.stdout
        assert holder["svc"].calls == [
            ("ali", "11111111-1111-1111-1111-111111111111", "ma réponse")
        ]

    def test_submit_text_json_output_is_valid(
        self, stubbed_text_grader
    ) -> None:
        factory, _ = stubbed_text_grader
        factory("ok")
        result = runner.invoke(
            app,
            [
                "submit-text",
                "--pseudo",
                "ali",
                "--exercise-id",
                "11111111-1111-1111-1111-111111111111",
                "--answer",
                "ma réponse",
                "--json",
            ],
        )
        assert result.exit_code == EXIT_OK
        text = result.stdout
        start = text.find("{")
        assert start != -1, text
        depth = 0
        end = -1
        for i in range(start, len(text)):
            ch = text[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        assert end != -1, text
        payload = json.loads(text[start:end])
        assert payload["is_success"] is True
        assert payload["feedback"] == "Bonne réponse."
        assert payload["attempt_id"] == "77777777-7777-7777-7777-777777777777"
        assert payload["attempt_number"] == 1

    def test_submit_text_echec_returns_zero_with_is_success_false(
        self, stubbed_text_grader
    ) -> None:
        factory, _ = stubbed_text_grader
        factory("echec")
        result = runner.invoke(
            app,
            [
                "submit-text",
                "--pseudo",
                "ali",
                "--exercise-id",
                "11111111-1111-1111-1111-111111111111",
                "--answer",
                "ma réponse",
            ],
        )
        assert result.exit_code == EXIT_OK, result.stdout

    def test_submit_text_cross_tenant_returns_5(
        self, stubbed_text_grader
    ) -> None:
        factory, _ = stubbed_text_grader
        factory("cross_tenant")
        result = runner.invoke(
            app,
            [
                "submit-text",
                "--pseudo",
                "bob",
                "--exercise-id",
                "11111111-1111-1111-1111-111111111111",
                "--answer",
                "ma réponse",
            ],
        )
        assert result.exit_code == 5

    def test_submit_text_exercise_not_found_returns_5(
        self, stubbed_text_grader
    ) -> None:
        factory, _ = stubbed_text_grader
        factory("exercise_not_found")
        result = runner.invoke(
            app,
            [
                "submit-text",
                "--pseudo",
                "ali",
                "--exercise-id",
                "00000000-0000-0000-0000-000000000000",
                "--answer",
                "ma réponse",
            ],
        )
        assert result.exit_code == 5

    def test_submit_text_invalid_exercise_type_returns_4(
        self, stubbed_text_grader
    ) -> None:
        factory, _ = stubbed_text_grader
        factory("invalid_exercise_type")
        result = runner.invoke(
            app,
            [
                "submit-text",
                "--pseudo",
                "ali",
                "--exercise-id",
                "11111111-1111-1111-1111-111111111111",
                "--answer",
                "ma réponse",
            ],
        )
        assert result.exit_code == 4

    def test_submit_text_verdict_missing_returns_4(
        self, stubbed_text_grader
    ) -> None:
        factory, _ = stubbed_text_grader
        factory("verdict_missing")
        result = runner.invoke(
            app,
            [
                "submit-text",
                "--pseudo",
                "ali",
                "--exercise-id",
                "11111111-1111-1111-1111-111111111111",
                "--answer",
                "ma réponse",
            ],
        )
        assert result.exit_code == 4

    def test_submit_text_answer_too_long_returns_2(
        self, stubbed_text_grader
    ) -> None:
        factory, _ = stubbed_text_grader
        factory("answer_too_long")
        result = runner.invoke(
            app,
            [
                "submit-text",
                "--pseudo",
                "ali",
                "--exercise-id",
                "11111111-1111-1111-1111-111111111111",
                "--answer",
                "x" * 9000,
            ],
        )
        assert result.exit_code == 2

    def test_submit_text_help_works(self) -> None:
        result = runner.invoke(app, ["submit-text", "--help"])
        assert result.exit_code == 0
        text = re.sub(r"\x1b\[[0-9;]*m", "", result.output)
        assert "--pseudo" in text
        assert "--exercise-id" in text
        assert "--answer" in text

    def test_help_lists_submit_text_command(self) -> None:
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "submit-text" in result.stdout
