"""QCM generator (s03).

Generates a QCM grounded on the chunks of a single document owned by a
student. The pipeline:

  1. validate inputs (n in [1, max_questions], document_id is a UUID)
  2. validate ownership: the document row exists *and* belongs to ``pseudo``
     (the multi-tenant invariant; see :meth:`QcmGenerator.generate`)
  3. fetch the document's chunks (multi-tenant collection + ``document_id`` filter)
  4. prompt the LLM with a soft template, then retry with a strict template
     if the response is not parseable
  5. persist the validated ``Exercise`` row (PostgreSQL) — only after the
     Pydantic model validates, never on a half-parsed structure

The generator is intentionally narrow — it does one thing, the QCM
generation — and inherits the same dependency-injection convention as
``UploadService`` and ``MathsAgent`` (LLM and retriever injected, cheap
test doubles possible).
"""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import Callable
from typing import Any, Protocol

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, Field, ValidationError

from app.core.database.models import (
    Document,
    Exercise,
    ExerciseType,
    Subject,
)
from app.services.llm.client import LlmClient

# ---------------------------------------------------------------------------
# Schemas (Pydantic)
# ---------------------------------------------------------------------------


class QcmQuestion(BaseModel):
    """A single QCM question. Locked by AC6: 4 options, ``correct_index`` in [0, 3]."""

    question: str
    options: list[str] = Field(min_length=4, max_length=4)
    correct_index: int = Field(ge=0, le=3)


class QcmExercise(BaseModel):
    """A complete QCM, parsed from the LLM's JSON output."""

    questions: list[QcmQuestion] = Field(min_length=1)


class QcmGenerationResult(BaseModel):
    """The successful outcome of :meth:`QcmGenerator.generate`."""

    exercise_id: uuid.UUID
    questions: list[QcmQuestion]
    raw: str


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class QcmGenerationError(Exception):
    """Controlled failure raised by :meth:`QcmGenerator.generate`.

    ``kind`` is a stable string the CLI / API can map to an exit code or
    HTTP status without parsing the message.
    """

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


def _extract_json_block(text: str) -> str | None:
    """Best-effort JSON object extraction.

    LLM outputs often wrap JSON in markdown fences (``\\`\\`\\`json``) or
    add a short preamble. We try (a) stripping fences and parsing, (b) a
    regex search for the first ``{...}`` block and parsing that. Returns
    the raw JSON string on success, ``None`` on failure.
    """
    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = re.sub(r"^```(?:json)?\s*", "", candidate)
        candidate = re.sub(r"\s*```$", "", candidate)
    try:
        json.loads(candidate)
        return candidate
    except (ValueError, TypeError):
        pass
    match = _JSON_OBJECT_RE.search(text)
    if match is None:
        return None
    block = match.group(0)
    try:
        json.loads(block)
    except (ValueError, TypeError):
        return None
    return block


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """Tu es un générateur d'exercices de type QCM pour un élève de collège.

Règles strictes :
1. Tu produis UNIQUEMENT des questions de QCM fondées sur les extraits de
   documents (chunks) fournis par le système dans le message de l'utilisateur.
   Tu n'utilises aucune connaissance générale, aucune source externe.
2. Tu renvoies un objet JSON valide avec la forme exacte :
   {
     "questions": [
       {
         "question": "string",
         "options": ["string", "string", "string", "string"],
         "correct_index": 0
       },
       ...
     ]
   }
3. Chaque question a EXACTEMENT 4 options. Une seule est correcte.
   ``correct_index`` est l'index (0-3) de la bonne réponse.
4. La question ne doit JAMAIS révéler la bonne réponse (pas d'indice dans
   l'énoncé comme "la réponse est..."). L'indice correct_index est la
   seule indication de la bonne réponse.
5. Tu ne mets aucun texte autour du JSON. Pas de markdown, pas de prose.
"""

_USER_PROMPT_TEMPLATE = """Génère un QCM de {n} questions à partir des extraits de documents ci-dessous.

Extraits de documents (utilise UNIQUEMENT ces extraits) :
{chunks}

Réponds UNIQUEMENT avec l'objet JSON demandé, sans markdown ni prose autour.
"""

_STRICT_USER_PROMPT_TEMPLATE = """Génère un QCM de {n} questions à partir des extraits de documents ci-dessous.

Extraits de documents (utilise UNIQUEMENT ces extraits) :
{chunks}

Réponds STRICTEMENT avec un objet JSON valide, sans aucun texte autour, sans markdown, sans ```json.
La forme exacte est :
{{"questions": [{{"question": "...", "options": ["a", "b", "c", "d"], "correct_index": 0}}, ...]}}
"""


def _format_chunks(chunks: list[Any]) -> str:
    """Render the retrieved chunks into the user prompt body."""
    if not chunks:
        return "(aucun extrait)"
    lines: list[str] = []
    for i, c in enumerate(chunks):
        filename = c.metadata.get("filename", "unknown")
        chunk_index = c.metadata.get("chunk_index", i)
        lines.append(f"[chunk {i} | source: {filename}, chunk {chunk_index}] {c.content}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class _SessionLike(Protocol):
    """The slice of a SQLAlchemy session the generator uses."""

    def add(self, obj: Any) -> None: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...


class _RetrieverLike(Protocol):
    def get_chunks_for_document(
        self, subject: str, pseudo: str, document_id: str, k: int = 20
    ) -> list[Any]: ...


class QcmGenerator:
    """Generate a QCM from a single document's chunks.

    The class follows the project's injection convention: the LLM client and
    retriever are passed at construction time. ``session_factory`` is
    optional — when ``None``, no ``Exercise`` row is persisted (used by
    tests and ad-hoc CLI invocations). Persistence requires the document
    to exist *and* belong to ``pseudo`` (multi-tenant invariant).
    """

    def __init__(
        self,
        *,
        llm: LlmClient,
        retriever: _RetrieverLike,
        session_factory: Callable[[], _SessionLike] | None = None,
        default_questions: int = 5,
        max_questions: int = 20,
        max_retries: int = 1,
        temperature: float = 0.0,
    ) -> None:
        self._llm = llm
        self._retriever = retriever
        self._session_factory = session_factory
        self._default_questions = default_questions
        self._max_questions = max_questions
        self._max_retries = max_retries
        self._temperature = temperature

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(
        self,
        pseudo: str,
        subject: str,
        document_id: str,
        n: int | None = None,
    ) -> QcmGenerationResult:
        """Generate a QCM of ``n`` questions for ``(pseudo, document_id)``.

        Raises :class:`QcmGenerationError` on every controlled failure.
        """
        requested = n if n is not None else self._default_questions
        if requested < 1 or requested > self._max_questions:
            raise QcmGenerationError(
                "invalid_input",
                f"n={requested} hors bornes [1, {self._max_questions}]",
            )

        # Validate the UUID format up front (CLI passes a string).
        try:
            doc_uuid = uuid.UUID(document_id)
        except (ValueError, TypeError) as exc:
            raise QcmGenerationError(
                "document_not_found", f"document_id invalide: {document_id}"
            ) from exc

        # Multi-tenant invariant: the document MUST exist and belong to
        # ``pseudo``. This is the lock — removing this check would let
        # one tenant generate a QCM on another tenant's chunks.
        if self._session_factory is not None:
            session = self._session_factory()
            doc = session.get(Document, doc_uuid)
            if doc is None or doc.student_pseudo != pseudo:
                # Same message for both cases: do not leak whether the
                # document exists under another pseudo.
                raise QcmGenerationError(
                    "document_not_found",
                    f"Document {doc_uuid} introuvable pour le pseudo {pseudo!r}.",
                )

        # Retrieve the chunks. Empty -> the LLM has nothing to ground on.
        chunks = self._retriever.get_chunks_for_document(
            subject, pseudo, document_id, k=20
        )
        if not chunks:
            raise QcmGenerationError(
                "no_chunks",
                f"Aucun extrait indexé pour le document {document_id}.",
            )

        # Build the prompt once, then call the LLM up to max_retries + 1
        # times (1 first attempt + max_retries retries). The retry uses
        # the strict template to push the LLM away from markdown.
        chunks_block = _format_chunks(chunks)
        soft_prompt = _USER_PROMPT_TEMPLATE.format(n=requested, chunks=chunks_block)
        strict_prompt = _STRICT_USER_PROMPT_TEMPLATE.format(
            n=requested, chunks=chunks_block
        )

        last_text = ""
        qcm: QcmExercise | None = None
        attempts = self._max_retries + 1
        for i in range(attempts):
            prompt = soft_prompt if i == 0 else strict_prompt
            messages = [
                SystemMessage(content=_SYSTEM_PROMPT),
                HumanMessage(content=prompt),
            ]
            response: AIMessage = self._llm.invoke(messages)
            last_text = response.content
            block = _extract_json_block(last_text)
            if block is None:
                continue
            try:
                qcm = QcmExercise.model_validate_json(block)
                break
            except ValidationError:
                continue

        if qcm is None:
            raise QcmGenerationError(
                "malformed_output",
                "Le LLM n'a pas renvoyé un JSON valide après retry.",
            )

        # Persist the validated exercise. We do NOT persist on a failed
        # parse — that would leak half-baked rows in the database.
        exercise_id = uuid.uuid4()
        if self._session_factory is not None:
            session = self._session_factory()
            try:
                session.add(
                    Exercise(
                        id=exercise_id,
                        student_pseudo=pseudo,
                        subject=Subject(subject),
                        type=ExerciseType.QCM,
                        document_id=doc_uuid,
                        questions=[q.model_dump() for q in qcm.questions],
                    )
                )
                session.commit()
            except Exception:
                session.rollback()
                raise

        return QcmGenerationResult(
            exercise_id=exercise_id,
            questions=qcm.questions,
            raw=json.dumps({"questions": [q.model_dump() for q in qcm.questions]}),
        )
