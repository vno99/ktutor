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
