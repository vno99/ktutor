"""``ktutor`` CLI — the user-facing entry point for s01 (upload).

Run via ``python -m ktutor.cli upload <file> --pseudo <p> --subject maths``.
Exit codes (see ``docs/designs/s01-uploader-document.md`` § Conventions):

  0 — success (or ``manual_review_needed``: the command executed correctly)
  1 — generic error
  2 — invalid file (missing, too large, unsupported extension)
  3 — OCR failure (LLM vision unavailable or unparseable)
  4 — ChromaDB or PostgreSQL write failure
  5 — invalid pseudo
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from app.core.config import get_settings
from app.core.database import session as db_session
from app.services.rag.chroma_store import ChromaStore
from app.services.rag.embeddings import build_embedding_provider
from app.services.rag.ingestion import DocumentIngestor
from app.services.rag.ocr import MultimodalOcr
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


if __name__ == "__main__":  # pragma: no cover
    app()
