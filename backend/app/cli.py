"""``ktutor`` CLI — user-facing entry point.

Run via ``python -m ktutor.cli <command> ...``.

Commands
--------

* ``upload`` — index a document into a student's per-pseudo RAG.
* ``chat``  — ask a question against the indexed documents (s02).
* ``generate-qcm`` — generate a QCM from a specific document (s03).

Exit codes (see ``docs/designs/s01-uploader-document.md`` § Conventions):

  0 — success (or ``manual_review_needed``: the command executed correctly)
  1 — generic error
  2 — invalid file (missing, too large, unsupported extension)
  3 — OCR failure (LLM vision unavailable or unparseable)
  4 — ChromaDB or PostgreSQL write failure (or LLM malformed output)
  5 — invalid pseudo (or document not found / cross-tenant)
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from app.core.config import get_settings
from app.core.database import session as db_session
from app.services.agents.maths_agent import MathsAgent
from app.services.exercises.qcm_generator import (
    QcmGenerationError,
    QcmGenerator,
)
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


def _build_chat_service() -> MathsAgent:
    """Wire the maths agent with its dependencies (ChromaDB, embeddings, LLM).

    No S3, no PostgreSQL, no OCR — chat is read-only and reads only the
    ChromaDB collections populated by the upload command.
    """
    settings = get_settings()
    chroma = ChromaStore(persist_directory=settings.chroma_persist_directory)
    embeddings = build_embedding_provider(
        llm_provider=settings.llm_provider,
        openai_api_key=settings.openai_api_key,
    )
    llm = build_llm_client(settings)
    retriever = Retriever(chroma_store=chroma, embeddings=embeddings)
    return MathsAgent(
        llm=llm,
        retriever=retriever,
        top_k=settings.chat_top_k,
        no_document_message=settings.chat_no_document_message,
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
    subject: str = typer.Option(..., "--subject", help="Matière (maths|francais)"),
    question: str = typer.Option(..., "--question", help="Question posée à l'agent"),
    json_output: bool = typer.Option(False, "--json", help="Sortie JSON pour scripts"),
) -> None:
    """Pose une question à l'agent sur les documents indexés de l'élève."""
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


if __name__ == "__main__":  # pragma: no cover
    app()
