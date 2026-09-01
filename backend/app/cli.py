"""``ktutor`` CLI — user-facing entry point.

Run via ``python -m ktutor.cli <command> ...``.

Commands
--------

* ``upload`` — index a document into a student's per-pseudo RAG.
* ``chat``  — ask a question against the indexed documents (s02).
* ``generate-qcm`` — generate a QCM from a specific document (s03).
* ``submit-qcm`` — submit answers to a previously generated QCM (s04).
* ``generate-exercise`` — generate a free-style exercise (s06).
* ``generate-flashcards`` — generate a flashcard deck (s06b).
* ``submit-text`` — submit a free-form text answer (s07, LLM-as-judge).

Exit codes (see ``docs/designs/s01-uploader-document.md`` § Conventions):

  0 — success (or ``manual_review_needed``: the command executed correctly)
  1 — generic error
  2 — invalid file (missing, too large, unsupported extension)
  3 — OCR failure (LLM vision unavailable or unparseable)
  4 — ChromaDB or PostgreSQL write failure (or LLM malformed output)
  5 — invalid pseudo (or document not found / cross-tenant)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# Reconfigure stdout/stderr to UTF-8 so the rich console can write Unicode
# characters (the "X" / "OK" markers, French accents) on Windows
# consoles that default to cp1252. Without this, ``UnicodeEncodeError``
# is raised on the first non-ASCII character at exit. See s04 review.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        # Python < 3.7 or already closed — best-effort only.
        pass

from app.core.config import get_settings
from app.core.database import session as db_session
from app.core.database.models import Subject
from app.services.agents import FrancaisAgent, MathsAgent, SubjectSupervisor
from app.services.exercises.flashcard_generator import (
    FlashcardGenerationError,
    FlashcardGenerator,
)
from app.services.exercises.free_generator import (
    FreeGenerationError,
    FreeGenerator,
)
from app.services.exercises.qcm_generator import (
    QcmGenerationError,
    QcmGenerator,
)
from app.services.exercises.qcm_grader import QcmGrader, QcmGradingError
from app.services.exercises.text_grader import TextGrader, TextGradingError
from app.services.llm.client import build_llm_client
from app.services.rag.chroma_store import ChromaStore, InvalidPseudoError
from app.services.rag.embeddings import build_embedding_provider
from app.services.rag.ingestion import DocumentIngestor
from app.services.rag.ocr import MultimodalOcr
from app.services.rag.retriever import Retriever
from app.services.rag.upload_service import (
    EXIT_GENERIC_ERROR,
    EXIT_INVALID_FILE,
    EXIT_INVALID_PSEUDO,
    EXIT_OCR_FAILURE,
    EXIT_OK,
    EXIT_STORAGE_FAILURE,
    UploadError,
    UploadErrorKind,
    UploadService,
)
from app.services.storage.minio_client import MinioClient

app = typer.Typer(add_completion=False, help="ktutor — AI homework assistant CLI.")


@app.callback()
def _root() -> None:
    """ktutor — AI homework assistant CLI."""


console = Console()


def _build_service() -> UploadService:
    settings = get_settings()
    s3_client = MinioClient(
        endpoint=settings.s3_endpoint,
        access_key=settings.s3_access_key,
        secret_key=settings.s3_secret_key,
        bucket=settings.s3_bucket,
    )
    s3_client.ensure_bucket()
    chroma = ChromaStore(persist_directory=settings.chroma_persist_directory)
    embeddings = build_embedding_provider(
        llm_provider=settings.llm_provider,
        openai_api_key=settings.openai_api_key,
    )
    ocr = MultimodalOcr(
        base_url=settings.deepseek_ocr_url,
        timeout=float(settings.deepseek_ocr_timeout),
    )
    db_session.init_db()
    return UploadService(
        s3_client=s3_client,
        chroma_store=chroma,
        embeddings=embeddings,
        ingestor=DocumentIngestor(),
        ocr=ocr,
        session_factory=db_session.get_session_factory(),
        max_upload_size_mb=settings.max_upload_size_mb,
    )


def _build_chat_service() -> SubjectSupervisor:
    """Wire the subject supervisor with all subject agents (s05).

    The supervisor dispatches to the right agent based on the
    ``--subject`` flag. No S3, no PostgreSQL, no OCR — chat is read-only
    and reads only the ChromaDB collections populated by the upload
    command.

    Both agents share the same LLM, retriever and ``no_document_message``
    so the multi-tenant invariant and the no-hallucination fallback are
    uniform across subjects.
    """
    settings = get_settings()
    chroma = ChromaStore(persist_directory=settings.chroma_persist_directory)
    embeddings = build_embedding_provider(
        llm_provider=settings.llm_provider,
        openai_api_key=settings.openai_api_key,
    )
    llm = build_llm_client(settings)
    retriever = Retriever(chroma_store=chroma, embeddings=embeddings)
    maths = MathsAgent(
        llm=llm,
        retriever=retriever,
        top_k=settings.chat_top_k,
        no_document_message=settings.chat_no_document_message,
    )
    francais = FrancaisAgent(
        llm=llm,
        retriever=retriever,
        top_k=settings.chat_top_k,
        no_document_message=settings.chat_no_document_message,
    )
    return SubjectSupervisor(
        {Subject.MATHS.value: maths, Subject.FRANCAIS.value: francais}
    )


def _build_qcm_service() -> QcmGenerator:
    """Wire the QCM generator (s03).

    No S3, no OCR. ChromaDB and the LLM are required; the session factory
    is wired so generated QCMs are persisted. ``init_db()`` is called so
    the ``exercises`` table exists in dev/CI (s15 will consolidate the
    Alembic migration).
    """
    settings = get_settings()
    chroma = ChromaStore(persist_directory=settings.chroma_persist_directory)
    embeddings = build_embedding_provider(
        llm_provider=settings.llm_provider,
        openai_api_key=settings.openai_api_key,
    )
    llm = build_llm_client(settings)
    retriever = Retriever(chroma_store=chroma, embeddings=embeddings)
    db_session.init_db()
    return QcmGenerator(
        llm=llm,
        retriever=retriever,
        session_factory=db_session.get_session_factory(),
        default_questions=settings.qcm_default_questions,
        max_questions=settings.qcm_max_questions,
        max_retries=settings.qcm_max_retries,
        temperature=settings.qcm_temperature,
    )


def _build_free_service() -> FreeGenerator:
    """Wire the free-style exercise generator (s06 — probleme, redaction).

    Same plumbing as :func:`_build_qcm_service`: ChromaDB + LLM, no S3/OCR.
    The session factory is wired so the ``Exercise`` row is persisted.
    ``free_difficulty_options`` is a comma-separated string parsed into a
    tuple here (s03 convention for ``qcm_max_questions``).
    """
    settings = get_settings()
    chroma = ChromaStore(persist_directory=settings.chroma_persist_directory)
    embeddings = build_embedding_provider(
        llm_provider=settings.llm_provider,
        openai_api_key=settings.openai_api_key,
    )
    llm = build_llm_client(settings)
    retriever = Retriever(chroma_store=chroma, embeddings=embeddings)
    db_session.init_db()
    return FreeGenerator(
        llm=llm,
        retriever=retriever,
        session_factory=db_session.get_session_factory(),
        default_difficulty=settings.free_default_difficulty,
        difficulty_options=tuple(
            value.strip()
            for value in settings.free_difficulty_options.split(",")
            if value.strip()
        ),
        max_retries=settings.free_max_retries,
        temperature=settings.free_temperature,
        max_statement_chars=settings.free_max_statement_chars,
    )


def _build_flashcard_service() -> FlashcardGenerator:
    """Wire the flashcard deck generator (s06b).

    Same plumbing as :func:`_build_qcm_service` and
    :func:`_build_free_service`: ChromaDB + LLM, no S3/OCR. The session
    factory is wired so the ``Exercise`` row is persisted with the
    polymorphic ``cards`` JSON column. All six ``FLASHCARDS_*`` settings
    are read from the typed ``Settings`` instance.
    """
    settings = get_settings()
    chroma = ChromaStore(persist_directory=settings.chroma_persist_directory)
    embeddings = build_embedding_provider(
        llm_provider=settings.llm_provider,
        openai_api_key=settings.openai_api_key,
    )
    llm = build_llm_client(settings)
    retriever = Retriever(chroma_store=chroma, embeddings=embeddings)
    db_session.init_db()
    return FlashcardGenerator(
        llm=llm,
        retriever=retriever,
        session_factory=db_session.get_session_factory(),
        default_n=settings.flashcards_default_n,
        max_n=settings.flashcards_max_n,
        max_retries=settings.flashcards_max_retries,
        temperature=settings.flashcards_temperature,
        max_front_chars=settings.flashcards_max_front_chars,
        max_back_chars=settings.flashcards_max_back_chars,
    )


def _print_summary(result, *, quiet: bool, json_output: bool) -> None:
    if json_output:
        console.print_json(
            data={
                "status": result.status.value,
                "document_id": str(result.document_id),
                "chunks_count": result.chunks_count,
                "duration_ms": result.duration_ms,
                "collection": result.collection,
                "s3_key": result.s3_key,
                "ocr_confidence": result.ocr_confidence,
            }
        )
        return
    if quiet:
        return
    title = (
        "[bold green]Document indexé avec succès[/bold green]"
        if result.chunks_count
        else "[bold yellow]Indexation partielle — révision manuelle requise[/bold yellow]"
    )
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column(style="dim")
    table.add_column()
    table.add_row("Fichier", "")
    table.add_row("Document ID", str(result.document_id))
    table.add_row("Chunks", str(result.chunks_count))
    table.add_row("Collection", result.collection or "—")
    table.add_row("Durée", f"{result.duration_ms / 1000:.2f} s")
    if result.ocr_confidence is not None:
        table.add_row("Confiance OCR", f"{result.ocr_confidence:.2f}")
    console.print(Panel(table, title=title, border_style="green" if result.chunks_count else "yellow"))


def _print_error(
    kind: UploadErrorKind, message: str, *, json_output: bool
) -> None:
    if json_output:
        console.print_json(data={"status": "error", "kind": kind.value, "message": message})
    else:
        console.print(f"[bold red]✗ Échec de l'upload[/bold red] — {message}")


@app.command()
def upload(
    file: Path = typer.Argument(..., exists=False, help="Fichier à indexer (.pdf/.png/.jpg/.jpeg/.txt)"),
    pseudo: str = typer.Option(..., "--pseudo", help="Pseudo de l'élève (regex ^[a-zA-Z0-9_]{3,32}$)"),
    subject: str = typer.Option(..., "--subject", help="Matière (maths|francais)"),
    quiet: bool = typer.Option(False, "--quiet", help="N'affiche que la ligne finale ✓/✗/⚠"),
    json_output: bool = typer.Option(False, "--json", help="Sortie JSON pour scripts"),
) -> None:
    """Indexe un fichier dans le RAG personnel de l'élève."""
    from rich.console import Console as _C

    show_steps = not quiet and not json_output
    with_status = _C(force_terminal=not json_output, no_color=False)

    # Early existence check (no spinner, immediate feedback).
    if not file.exists():
        _print_error(
            UploadErrorKind.INVALID_FILE,
            f"Fichier introuvable: {file}",
            json_output=json_output,
        )
        raise typer.Exit(code=EXIT_INVALID_FILE)

    def _run() -> object:
        try:
            service = _build_service()
        except UploadError:
            raise
        except Exception as exc:
            # Service initialization failed (S3 / Postgres / Chroma unreachable).
            # Surface as a storage failure so the user sees exit code 4.
            raise UploadError(
                UploadErrorKind.STORAGE_FAILURE,
                f"Initialisation des services impossible: {exc}",
            ) from exc
        return service.upload(str(file), pseudo, subject)

    try:
        if show_steps:
            with with_status.status("[bold blue]Initialisation…[/bold blue]", spinner="dots"):
                pass  # nothing to do, just signal progress
            with with_status.status(
                "[bold blue]Push S3 + indexation ChromaDB…[/bold blue]", spinner="dots"
            ):
                result = _run()
        else:
            result = _run()
    except UploadError as exc:
        _print_error(exc.kind, str(exc), json_output=json_output)
        mapping = {
            UploadErrorKind.INVALID_PSEUDO: EXIT_INVALID_PSEUDO,
            UploadErrorKind.INVALID_FILE: EXIT_INVALID_FILE,
            UploadErrorKind.OCR_FAILURE: EXIT_OCR_FAILURE,
            UploadErrorKind.STORAGE_FAILURE: EXIT_STORAGE_FAILURE,
        }
        raise typer.Exit(code=mapping.get(exc.kind, EXIT_GENERIC_ERROR)) from exc
    except SystemExit:
        raise
    except Exception as exc:
        _print_error(UploadErrorKind.STORAGE_FAILURE, f"Erreur inattendue: {exc}", json_output=json_output)
        raise typer.Exit(code=EXIT_GENERIC_ERROR) from exc

    _print_summary(result, quiet=quiet, json_output=json_output)
    raise typer.Exit(code=EXIT_OK)


# ---------------------------------------------------------------------------
# Chat command (s02)
# ---------------------------------------------------------------------------


def _print_chat_result(result, *, json_output: bool) -> None:
    if json_output:
        console.print_json(
            data={
                "answer": result.answer,
                "sources": [
                    {"filename": s.filename, "chunk_index": s.chunk_index}
                    for s in result.sources
                ],
            }
        )
        return
    body_lines = [result.answer, ""]
    if result.sources:
        body_lines.append("Sources :")
        for s in result.sources:
            body_lines.append(f"  - {s.filename} (chunk {s.chunk_index})")
    console.print(Panel("\n".join(body_lines), title="[bold blue]Réponse[/bold blue]", border_style="blue"))


@app.command()
def chat(
    pseudo: str = typer.Option(..., "--pseudo", help="Pseudo de l'élève (regex ^[a-zA-Z0-9_]{3,32}$)"),
    subject: str = typer.Option(
        ...,
        "--subject",
        help="Matière (maths|francais)",
        case_sensitive=False,
    ),
    question: str = typer.Option(..., "--question", help="Question posée à l'agent"),
    json_output: bool = typer.Option(False, "--json", help="Sortie JSON pour scripts"),
) -> None:
    """Pose une question à l'agent sur les documents indexés de l'élève."""
    # Defense in depth (D3): validate the subject BEFORE building any
    # service. Unknown subjects are a user error, not a runtime failure.
    valid_subjects = {s.value for s in Subject}
    if subject.lower() not in valid_subjects:
        console.print(
            f"[bold red]✗ Matière inconnue[/bold red] — {subject!r}. "
            f"Valeurs acceptées : {sorted(valid_subjects)}."
        )
        raise typer.Exit(code=EXIT_INVALID_PSEUDO)
    # Normalise to the canonical lowercase form the supervisor and the
    # ChromaDB collection-name convention both expect.
    subject = subject.lower()

    try:
        try:
            agent = _build_chat_service()
        except Exception as exc:
            console.print(f"[bold red]✗ Initialisation impossible[/bold red] — {exc}")
            raise typer.Exit(code=EXIT_GENERIC_ERROR) from exc

        result = agent.ask(subject, pseudo, question)
    except InvalidPseudoError as exc:
        console.print(f"[bold red]✗ Pseudo invalide[/bold red] — {exc}")
        raise typer.Exit(code=EXIT_INVALID_PSEUDO) from exc
    except ValueError as exc:
        # SubjectSupervisor (or an agent) refused the subject — same
        # bucket as an invalid pseudo per the D3 recommendation.
        console.print(f"[bold red]✗ Matière invalide[/bold red] — {exc}")
        raise typer.Exit(code=EXIT_INVALID_PSEUDO) from exc
    except SystemExit:
        raise
    except Exception as exc:
        console.print(f"[bold red]✗ Échec[/bold red] — {exc}")
        raise typer.Exit(code=EXIT_GENERIC_ERROR) from exc

    _print_chat_result(result, json_output=json_output)
    raise typer.Exit(code=EXIT_OK)


# ---------------------------------------------------------------------------
# generate-qcm command (s03)
# ---------------------------------------------------------------------------


# s03 adds two more exit codes on top of the upload/chat convention:
#   5 — document not found / no chunks (treated like "invalid pseudo": the
#       user gave a wrong document_id, including the cross-tenant case)
#   4 — malformed LLM output (treated like a storage failure: the LLM
#       pipeline could not deliver a parseable result)
EXIT_QCM_DOCUMENT_NOT_FOUND = 5
EXIT_QCM_LLM_FAILURE = EXIT_STORAGE_FAILURE  # 4


def _print_qcm_result(result, *, json_output: bool) -> None:
    if json_output:
        console.print_json(
            data={
                "exercise_id": str(result.exercise_id),
                "questions": [q.model_dump() for q in result.questions],
            }
        )
        return
    body_lines = [f"Exercise ID : {result.exercise_id}", "", "Questions :"]
    for i, q in enumerate(result.questions, 1):
        body_lines.append(f"  {i}. {q.question}")
        for j, opt in enumerate(q.options):
            marker = " ✓" if j == q.correct_index else "  "
            body_lines.append(f"     {marker} {chr(ord('A') + j)}. {opt}")
    console.print(
        Panel("\n".join(body_lines), title="[bold blue]QCM généré[/bold blue]", border_style="blue")
    )


def _print_qcm_error(kind: str, message: str, *, json_output: bool) -> None:
    if json_output:
        console.print_json(data={"status": "error", "kind": kind, "message": message})
    else:
        console.print(f"[bold red]✗ Échec de la génération du QCM[/bold red] — {message}")


@app.command()
def generate_qcm(
    pseudo: str = typer.Option(..., "--pseudo", help="Pseudo de l'élève (regex ^[a-zA-Z0-9_]{3,32}$)"),
    document_id: str = typer.Option(..., "--document-id", help="Identifiant UUID du document source"),
    n: int = typer.Option(None, "--n", help="Nombre de questions (défaut: qcm_default_questions)"),
    subject: str = typer.Option("maths", "--subject", help="Matière (maths|francais)"),
    quiet: bool = typer.Option(False, "--quiet", help="N'affiche que la ligne finale ✓/✗"),
    json_output: bool = typer.Option(False, "--json", help="Sortie JSON pour scripts"),
) -> None:
    """Génère un QCM à partir d'un document indexé de l'élève."""
    try:
        try:
            service = _build_qcm_service()
        except Exception as exc:
            console.print(f"[bold red]✗ Initialisation impossible[/bold red] — {exc}")
            raise typer.Exit(code=EXIT_GENERIC_ERROR) from exc

        result = service.generate(pseudo, subject, document_id, n=n)
    except QcmGenerationError as exc:
        kind = exc.kind
        if kind == "document_not_found" or kind == "no_chunks" or kind == "invalid_input":
            _print_qcm_error(kind, str(exc), json_output=json_output)
            raise typer.Exit(code=EXIT_QCM_DOCUMENT_NOT_FOUND) from exc
        # malformed_output / storage_failure map to a storage-style failure.
        _print_qcm_error(kind, str(exc), json_output=json_output)
        raise typer.Exit(code=EXIT_QCM_LLM_FAILURE) from exc
    except InvalidPseudoError as exc:
        console.print(f"[bold red]✗ Pseudo invalide[/bold red] — {exc}")
        raise typer.Exit(code=EXIT_INVALID_PSEUDO) from exc
    except SystemExit:
        raise
    except Exception as exc:
        console.print(f"[bold red]✗ Échec inattendu[/bold red] — {exc}")
        raise typer.Exit(code=EXIT_GENERIC_ERROR) from exc

    _print_qcm_result(result, json_output=json_output)
    if not quiet and not json_output:
        console.print("[bold green]✓ QCM généré[/bold green]")
    raise typer.Exit(code=EXIT_OK)


# ---------------------------------------------------------------------------
# submit-qcm command (s04)
# ---------------------------------------------------------------------------


# s04 maps QcmGradingError kinds to exit codes consistent with the existing
# convention:
#   5 — exercise_not_found / cross_tenant (same as upload/chat: the user
#       pointed at a wrong or foreign exercise_id; no leak)
#   4 — invalid_answers / invalid_exercise (bad input that cannot be
#       persisted, treated like a storage failure: the pipeline cannot
#       deliver a parseable result)
EXIT_QCM_GRADER_NOT_FOUND = 5
EXIT_QCM_GRADER_BAD_INPUT = EXIT_STORAGE_FAILURE  # 4


def _build_grader_service() -> QcmGrader:
    """Wire the QCM grader (s04).

    No S3, no OCR, no ChromaDB, no LLM. The session factory is the only
    dependency; ``init_db()`` creates the ``attempts`` table in dev/CI
    (s15 will consolidate the Alembic migration).
    """
    db_session.init_db()
    return QcmGrader(session_factory=db_session.get_session_factory())


def _print_grading_result(result, *, json_output: bool) -> None:
    if json_output:
        console.print_json(
            data={
                "is_success": result.is_success,
                "correct_count": result.correct_count,
                "total": result.total,
                "feedback": result.feedback,
                "attempt_id": str(result.attempt_id),
                "attempt_number": result.attempt_number,
            }
        )
        return
    title = (
        "[bold green]✓ QCM réussi[/bold green]"
        if result.is_success
        else "[bold red]✗ QCM échoué[/bold red]"
    )
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column(style="dim")
    table.add_column()
    table.add_row("Score", f"{result.correct_count}/{result.total}")
    table.add_row("Verdict", "Toutes les réponses sont correctes." if result.is_success else f"{result.correct_count}/{result.total} réponses correctes.")
    table.add_row("Attempt ID", str(result.attempt_id))
    table.add_row("Numéro de tentative", str(result.attempt_number))
    console.print(Panel(table, title=title, border_style="green" if result.is_success else "red"))


def _print_grading_error(kind: str, message: str, *, json_output: bool) -> None:
    if json_output:
        console.print_json(data={"status": "error", "kind": kind, "message": message})
    else:
        console.print(f"[bold red]✗ Échec du grading QCM[/bold red] — {message}")


@app.command()
def submit_qcm(
    pseudo: str = typer.Option(..., "--pseudo", help="Pseudo de l'élève (regex ^[a-zA-Z0-9_]{3,32}$)"),
    exercise_id: str = typer.Option(..., "--exercise-id", help="Identifiant UUID de l'exercice QCM"),
    answers: str = typer.Option(..., "--answers", help="Réponses en JSON, ex: '[0,2,1,3,0]'"),
    quiet: bool = typer.Option(False, "--quiet", help="N'affiche que la ligne finale ✓/✗"),
    json_output: bool = typer.Option(False, "--json", help="Sortie JSON pour scripts"),
) -> None:
    """Soumet les réponses à un QCM et affiche le verdict binaire."""
    # Parse the answers as JSON up front: a malformed payload is a
    # user error, not a service error, but it lands in the "bad input"
    # exit bucket (4) for consistency with ``invalid_answers``.
    try:
        raw_answers = json.loads(answers)
    except (ValueError, TypeError) as exc:
        _print_grading_error("invalid_answers", f"--answers JSON invalide: {exc}", json_output=json_output)
        raise typer.Exit(code=EXIT_QCM_GRADER_BAD_INPUT) from exc
    if not isinstance(raw_answers, list) or not all(isinstance(x, int) and not isinstance(x, bool) for x in raw_answers):
        _print_grading_error(
            "invalid_answers",
            "--answers doit être une liste d'entiers (ex: '[0,2,1,3,0]').",
            json_output=json_output,
        )
        raise typer.Exit(code=EXIT_QCM_GRADER_BAD_INPUT)

    try:
        try:
            service = _build_grader_service()
        except Exception as exc:
            console.print(f"[bold red]✗ Initialisation impossible[/bold red] — {exc}")
            raise typer.Exit(code=EXIT_GENERIC_ERROR) from exc

        result = service.grade(pseudo, exercise_id, raw_answers)
    except QcmGradingError as exc:
        kind = exc.kind
        if kind in ("exercise_not_found", "cross_tenant"):
            _print_grading_error(kind, str(exc), json_output=json_output)
            raise typer.Exit(code=EXIT_QCM_GRADER_NOT_FOUND) from exc
        # invalid_answers / invalid_exercise / storage_failure land in 4.
        _print_grading_error(kind, str(exc), json_output=json_output)
        raise typer.Exit(code=EXIT_QCM_GRADER_BAD_INPUT) from exc
    except InvalidPseudoError as exc:
        console.print(f"[bold red]✗ Pseudo invalide[/bold red] — {exc}")
        raise typer.Exit(code=EXIT_INVALID_PSEUDO) from exc
    except SystemExit:
        raise
    except Exception as exc:
        console.print(f"[bold red]✗ Échec inattendu[/bold red] — {exc}")
        raise typer.Exit(code=EXIT_GENERIC_ERROR) from exc

    _print_grading_result(result, json_output=json_output)
    if not quiet and not json_output:
        console.print(
            "[bold green]✓[/bold green]" if result.is_success else "[bold red]✗[/bold red]"
        )
    raise typer.Exit(code=EXIT_OK)


# ---------------------------------------------------------------------------
# generate-exercise command (s06 — probleme, redaction)
# ---------------------------------------------------------------------------


# s06 follows the s03 exit code convention:
#   5 — document_not_found / no_chunks / invalid_type / invalid_difficulty
#   4 — malformed_output / thin_expected_answer / statement_too_long
#       (LLM-side inconsistencies, treated as a storage-style failure)
EXIT_FREE_NOT_FOUND = 5
EXIT_FREE_LLM_FAILURE = EXIT_STORAGE_FAILURE  # 4


def _print_free_result(result, *, json_output: bool) -> None:
    if json_output:
        # ``result.exercise`` is a discriminated Union — use ``model_dump``
        # to produce the JSON-friendly shape.
        console.print_json(
            data={
                "exercise_id": str(result.exercise_id),
                "exercise": result.exercise.model_dump(by_alias=True),
            }
        )
        return
    dump = result.exercise.model_dump(by_alias=True)
    body_lines = [
        f"Exercise ID : {result.exercise_id}",
        "",
        f"Type : {dump.get('type')}",
        f"Sujet / thème : {dump.get('statement', '')[:120]}{'...' if len(dump.get('statement', '')) > 120 else ''}",
        "",
        "Critères d'évaluation :",
    ]
    for c in dump.get("grading_criteria", []):
        body_lines.append(f"  - {c}")
    console.print(
        Panel(
            "\n".join(body_lines),
            title="[bold blue]Exercice généré[/bold blue]",
            border_style="blue",
        )
    )


def _print_free_error(kind: str, message: str, *, json_output: bool) -> None:
    if json_output:
        console.print_json(data={"status": "error", "kind": kind, "message": message})
    else:
        console.print(f"[bold red]✗ Échec de la génération de l'exercice[/bold red] — {message}")


@app.command()
def generate_exercise(
    pseudo: str = typer.Option(..., "--pseudo", help="Pseudo de l'élève (regex ^[a-zA-Z0-9_]{3,32}$)"),
    subject: str = typer.Option(..., "--subject", help="Matière (maths|francais)"),
    type: str = typer.Option(..., "--type", help="Type d'exercice (probleme|redaction)"),
    document_id: str = typer.Option(..., "--document-id", help="Identifiant UUID du document source"),
    topic: str = typer.Option(..., "--topic", help="Sujet ou thème de l'exercice"),
    difficulty: str = typer.Option(None, "--difficulty", help="Difficulté (facile|moyen|difficile)"),
    quiet: bool = typer.Option(False, "--quiet", help="N'affiche que la ligne finale ✓/✗"),
    json_output: bool = typer.Option(False, "--json", help="Sortie JSON pour scripts"),
) -> None:
    """Génère un exercice libre (problème de maths ou rédaction de français)."""
    settings = get_settings()
    chosen_difficulty = difficulty or settings.free_default_difficulty
    try:
        try:
            service = _build_free_service()
        except Exception as exc:
            console.print(f"[bold red]✗ Initialisation impossible[/bold red] — {exc}")
            raise typer.Exit(code=EXIT_GENERIC_ERROR) from exc

        result = service.generate(
            pseudo, subject, type, document_id, topic, difficulty=chosen_difficulty
        )
    except FreeGenerationError as exc:
        kind = exc.kind
        if kind in (
            "document_not_found",
            "no_chunks",
            "invalid_type",
            "invalid_difficulty",
        ):
            _print_free_error(kind, str(exc), json_output=json_output)
            raise typer.Exit(code=EXIT_FREE_NOT_FOUND) from exc
        # malformed_output / thin_expected_answer / statement_too_long / storage_failure
        # all land in 4 (LLM-side inconsistencies).
        _print_free_error(kind, str(exc), json_output=json_output)
        raise typer.Exit(code=EXIT_FREE_LLM_FAILURE) from exc
    except InvalidPseudoError as exc:
        console.print(f"[bold red]✗ Pseudo invalide[/bold red] — {exc}")
        raise typer.Exit(code=EXIT_INVALID_PSEUDO) from exc
    except SystemExit:
        raise
    except Exception as exc:
        console.print(f"[bold red]✗ Échec inattendu[/bold red] — {exc}")
        raise typer.Exit(code=EXIT_GENERIC_ERROR) from exc

    _print_free_result(result, json_output=json_output)
    if not quiet and not json_output:
        console.print("[bold green]✓ Exercice généré[/bold green]")
    raise typer.Exit(code=EXIT_OK)


# ---------------------------------------------------------------------------
# generate-flashcards command (s06b)
# ---------------------------------------------------------------------------


# s06b follows the s03 / s06 exit code convention:
#   5 — document_not_found / no_chunks / invalid_input (treated as a
#       user-error bucket: the user gave a wrong document_id, including
#       the cross-tenant case, or an out-of-range n)
#   4 — malformed_output (LLM pipeline could not deliver a parseable
#       result after retry, including the duplicate_fronts /
#       external_reference post-Pydantic checks that exhausted retries)
EXIT_FLASHCARDS_NOT_FOUND = 5
EXIT_FLASHCARDS_LLM_FAILURE = EXIT_STORAGE_FAILURE  # 4


def _print_flashcard_result(result, *, json_output: bool) -> None:
    if json_output:
        console.print_json(
            data={
                "exercise_id": str(result.exercise_id),
                "deck": result.deck.model_dump(),
            }
        )
        return
    body_lines = [
        f"Exercise ID : {result.exercise_id}",
        "",
        f"Cartes : {len(result.deck.cards)}",
        "",
    ]
    for i, card in enumerate(result.deck.cards, 1):
        topic_label = f" [{card.topic}]" if card.topic else ""
        body_lines.append(f"  {i}. Q : {card.front}{topic_label}")
        body_lines.append(f"     R : {card.back}")
    console.print(
        Panel(
            "\n".join(body_lines),
            title="[bold blue]Deck de flashcards généré[/bold blue]",
            border_style="blue",
        )
    )


def _print_flashcard_error(kind: str, message: str, *, json_output: bool) -> None:
    if json_output:
        console.print_json(data={"status": "error", "kind": kind, "message": message})
    else:
        console.print(f"[bold red]✗ Échec de la génération des flashcards[/bold red] — {message}")


@app.command()
def generate_flashcards(
    pseudo: str = typer.Option(..., "--pseudo", help="Pseudo de l'élève (regex ^[a-zA-Z0-9_]{3,32}$)"),
    document_id: str = typer.Option(..., "--document-id", help="Identifiant UUID du document source"),
    n: int = typer.Option(None, "--n", help="Nombre de cartes (défaut: flashcards_default_n)"),
    subject: str = typer.Option("maths", "--subject", help="Matière (maths|francais)"),
    quiet: bool = typer.Option(False, "--quiet", help="N'affiche que la ligne finale ✓/✗"),
    json_output: bool = typer.Option(False, "--json", help="Sortie JSON pour scripts"),
) -> None:
    """Génère un deck de flashcards (recto: question, verso: réponse) à partir d'un document indexé de l'élève."""
    settings = get_settings()
    chosen_n = n if n is not None else settings.flashcards_default_n
    try:
        try:
            service = _build_flashcard_service()
        except Exception as exc:
            console.print(f"[bold red]✗ Initialisation impossible[/bold red] — {exc}")
            raise typer.Exit(code=EXIT_GENERIC_ERROR) from exc

        result = service.generate(pseudo, subject, document_id, n=chosen_n)
    except FlashcardGenerationError as exc:
        kind = exc.kind
        if kind in ("document_not_found", "no_chunks", "invalid_input"):
            _print_flashcard_error(kind, str(exc), json_output=json_output)
            raise typer.Exit(code=EXIT_FLASHCARDS_NOT_FOUND) from exc
        # malformed_output (also reports duplicate_fronts / external_reference
        # exhausted) maps to the LLM-failure bucket (4).
        _print_flashcard_error(kind, str(exc), json_output=json_output)
        raise typer.Exit(code=EXIT_FLASHCARDS_LLM_FAILURE) from exc
    except InvalidPseudoError as exc:
        console.print(f"[bold red]✗ Pseudo invalide[/bold red] — {exc}")
        raise typer.Exit(code=EXIT_INVALID_PSEUDO) from exc
    except SystemExit:
        raise
    except Exception as exc:
        console.print(f"[bold red]✗ Échec inattendu[/bold red] — {exc}")
        raise typer.Exit(code=EXIT_GENERIC_ERROR) from exc

    _print_flashcard_result(result, json_output=json_output)
    if not quiet and not json_output:
        console.print("[bold green]✓ Deck de flashcards généré[/bold green]")
    raise typer.Exit(code=EXIT_OK)


# ---------------------------------------------------------------------------
# submit-text command (s07 — LLM-as-judge text grading)
# ---------------------------------------------------------------------------


# s07 follows the s04 / s06 / s06b exit code convention:
#   5 — exercise_not_found / cross_tenant (same as submit-qcm: the user
#       pointed at a wrong or foreign exercise_id; no leak)
#   4 — invalid_exercise_type / verdict_missing / llm_failure /
#       storage_failure (bad input or LLM-side inconsistency, treated as
#       a pipeline failure)
#   2 — answer_too_long (user error: the response exceeded the configured
#       ``text_grader_max_answer_chars`` safety net)
EXIT_TEXT_NOT_FOUND = 5
EXIT_TEXT_BAD_INPUT = EXIT_STORAGE_FAILURE  # 4
EXIT_TEXT_TOO_LONG = 2


def _build_text_grader_service() -> TextGrader:
    """Wire the free-form text grader (s07).

    Mirrors :func:`_build_grader_service`: no S3, no OCR, no ChromaDB.
    The LLM is required (LLM-as-judge); the session factory is wired so
    the ``Attempt`` row is persisted with ``answer_text`` populated and
    ``raw_answers=[]``. ``init_db()`` creates the ``attempts`` table in
    dev/CI (s15 will consolidate the Alembic migration).
    """
    settings = get_settings()
    llm = build_llm_client(settings)
    db_session.init_db()
    return TextGrader(
        llm=llm,
        session_factory=db_session.get_session_factory(),
        max_retries=settings.text_grader_max_retries,
        temperature=settings.text_grader_temperature,
        max_answer_chars=settings.text_grader_max_answer_chars,
    )


def _print_text_result(result, *, json_output: bool) -> None:
    if json_output:
        console.print_json(
            data={
                "is_success": result.is_success,
                "feedback": result.feedback,
                "attempt_id": str(result.attempt_id),
                "attempt_number": result.attempt_number,
            }
        )
        return
    title = (
        "[bold green]✓ Exercice réussi[/bold green]"
        if result.is_success
        else "[bold red]✗ Exercice échoué[/bold red]"
    )
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column(style="dim")
    table.add_column()
    table.add_row("Verdict", "Réussite" if result.is_success else "Échec")
    table.add_row("Appréciation", result.feedback)
    table.add_row("Attempt ID", str(result.attempt_id))
    table.add_row("Numéro de tentative", str(result.attempt_number))
    console.print(Panel(table, title=title, border_style="green" if result.is_success else "red"))


def _print_text_error(kind: str, message: str, *, json_output: bool) -> None:
    if json_output:
        console.print_json(data={"status": "error", "kind": kind, "message": message})
    else:
        console.print(f"[bold red]✗ Échec du grading texte[/bold red] — {message}")


@app.command()
def submit_text(
    pseudo: str = typer.Option(..., "--pseudo", help="Pseudo de l'élève (regex ^[a-zA-Z0-9_]{3,32}$)"),
    exercise_id: str = typer.Option(..., "--exercise-id", help="Identifiant UUID de l'exercice (probleme|redaction)"),
    answer: str = typer.Option(..., "--answer", help="Réponse texte de l'élève"),
    quiet: bool = typer.Option(False, "--quiet", help="N'affiche que la ligne finale ✓/✗"),
    json_output: bool = typer.Option(False, "--json", help="Sortie JSON pour scripts"),
) -> None:
    """Soumet une réponse texte à un exercice libre (probleme / redaction) et affiche le verdict binaire du LLM."""
    try:
        try:
            service = _build_text_grader_service()
        except Exception as exc:
            console.print(f"[bold red]✗ Initialisation impossible[/bold red] — {exc}")
            raise typer.Exit(code=EXIT_GENERIC_ERROR) from exc

        result = service.grade(pseudo, exercise_id, answer)
    except TextGradingError as exc:
        kind = exc.kind
        if kind in ("exercise_not_found", "cross_tenant"):
            _print_text_error(kind, str(exc), json_output=json_output)
            raise typer.Exit(code=EXIT_TEXT_NOT_FOUND) from exc
        if kind == "answer_too_long":
            _print_text_error(kind, str(exc), json_output=json_output)
            raise typer.Exit(code=EXIT_TEXT_TOO_LONG) from exc
        # invalid_exercise_type / verdict_missing / llm_failure /
        # storage_failure / invalid_answers all land in 4.
        _print_text_error(kind, str(exc), json_output=json_output)
        raise typer.Exit(code=EXIT_TEXT_BAD_INPUT) from exc
    except InvalidPseudoError as exc:
        console.print(f"[bold red]✗ Pseudo invalide[/bold red] — {exc}")
        raise typer.Exit(code=EXIT_INVALID_PSEUDO) from exc
    except SystemExit:
        raise
    except Exception as exc:
        console.print(f"[bold red]✗ Échec inattendu[/bold red] — {exc}")
        raise typer.Exit(code=EXIT_GENERIC_ERROR) from exc

    _print_text_result(result, json_output=json_output)
    if not quiet and not json_output:
        console.print(
            "[bold green]✓[/bold green]" if result.is_success else "[bold red]✗[/bold red]"
        )
    raise typer.Exit(code=EXIT_OK)


if __name__ == "__main__":  # pragma: no cover
    app()
