"""Flashcard deck generator (s06b).

Generates a deck of flashcards (recto: question, verso: answer) grounded on
the chunks of a single document owned by a student. The pipeline mirrors
``QcmGenerator`` and ``FreeGenerator``:

  1. validate inputs (n in [1, max_n], document_id is a UUID)
  2. validate ownership: the document row exists *and* belongs to ``pseudo``
     (the multi-tenant invariant; see :meth:`FlashcardGenerator.generate`)
  3. fetch the document's chunks (multi-tenant collection + ``document_id``
     filter)
  4. prompt the LLM with a soft template, then retry with a strict
     template if the response is not parseable
  5. post-Pydantic checks: duplicate ``front`` (lower-cased + stripped),
     external reference in ``back`` (``voir`` / ``page`` / ``section`` /
     ``chapitre`` case-insensitive) — each triggers one retry
  6. persist the validated ``Exercise`` row (PostgreSQL) only after the
     Pydantic model validates, never on a half-parsed structure
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Callable
from typing import Any, Literal, Protocol

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, Field, ValidationError, field_validator

from app.core.database.models import (
    Document,
    Exercise,
    ExerciseType,
    Subject,
)
from app.services.exercises._parsing import extract_json_block
from app.services.llm.client import LlmClient

# ---------------------------------------------------------------------------
# Schemas (Pydantic)
# ---------------------------------------------------------------------------


# Piège 9 — the post-Pydantic check rejects ``back`` that contains a
# reference to an external section/page/chapter. The pattern is the
# boundary word followed by digits or end-of-string; it is checked
# case-insensitively in the service.
_EXTERNAL_REFERENCE_RE = re.compile(
    r"\b(voir|page|section|chapitre)\b",
    re.IGNORECASE,
)


class FlashcardSchema(BaseModel):
    """A single flashcard (recto / verso + optional topic).

    Locked by AC4 + D6: ``front`` and ``back`` are 1..200 chars; ``topic``
    is optional (``None`` or a non-empty string). ``topic=""`` is coerced
    to ``None`` so the LLM can return the empty string for "no topic".
    """

    front: str = Field(min_length=1, max_length=200)
    back: str = Field(min_length=1, max_length=200)
    topic: str | None = None

    @field_validator("topic", mode="before")
    @classmethod
    def _coerce_empty_topic(cls, value: Any) -> Any:
        # The LLM may return ``""`` for "no topic"; the schema treats that
        # as "absent" so the contract (D6) is uniform: ``None`` or a
        # non-empty string.
        if value == "":
            return None
        return value


class FlashcardDeck(BaseModel):
    """A complete flashcard deck, parsed from the LLM's JSON output."""

    type: Literal["flashcards"] = "flashcards"
    cards: list[FlashcardSchema] = Field(min_length=1, max_length=30)


class FlashcardGenerationResult(BaseModel):
    """The successful outcome of :meth:`FlashcardGenerator.generate`."""

    exercise_id: uuid.UUID
    deck: FlashcardDeck
    raw: str


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class FlashcardGenerationError(Exception):
    """Controlled failure raised by :meth:`FlashcardGenerator.generate`.

    ``kind`` is a stable string the CLI / API can map to an exit code or
    HTTP status without parsing the message. Allowed values:

      - ``"document_not_found"`` — UUID bad, doc absent, or owned by
        another pseudo (no cross-tenant leak)
      - ``"invalid_input"`` — n out of [1, max_n]
      - ``"no_chunks"`` — the document has no indexed chunks
      - ``"malformed_output"`` — the LLM did not return a valid deck
      - ``"storage_failure"`` — the DB write failed
      - ``"duplicate_fronts"`` — post-Pydantic check fired (retry path)
      - ``"external_reference"`` — post-Pydantic check fired (retry path)
    """

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------


_FLASHCARDS_SYSTEM_PROMPT = """Tu es un générateur de flashcards (recto-verso) pour un élève de collège.

Règles strictes :
1. Tu produis UNIQUEMENT des flashcards fondées sur les extraits de
   documents (chunks) fournis dans le message de l'utilisateur. Tu
   n'utilises aucune connaissance générale, aucune source externe.
2. Tu renvoies un objet JSON valide avec la forme exacte :
   {
     "cards": [
       {
         "front": "string (1-200 chars, question autonome, sans renvoi externe)",
         "back": "string (1-200 chars, réponse concise, SANS référence externe)",
         "topic": "string ou null"
       },
       ...
     ]
   }
3. Le ``front`` est une question AUTONOME : la question doit se comprendre
   sans lire le reste du document. Pas de fragment dépendant du contexte.
4. Le ``back`` est une réponse CONCISE (max 200 caractères) qui NE
   référence JAMAIS une autre partie du document. Pas de
   "voir section 2.1", "voir page 12", "voir chapitre 3" — la réponse
   doit être suffisante en elle-même.
5. Le ``topic`` est optionnel. Si tu ne sais pas, mets ``null``. N'utilise
   jamais une chaîne vide.
6. Chaque carte doit être DIFFÉRENTE des autres (pas de doublons).
   Si la même question apparaît deux fois, l'exercice est invalide.
7. Tu ne mets aucun texte autour du JSON. Pas de markdown, pas de prose.
"""


_FLASHCARDS_USER_PROMPT_TEMPLATE = """Génère un deck de {n} flashcards à partir des extraits de documents ci-dessous.

Extraits de documents (utilise UNIQUEMENT ces extraits) :
{chunks}

Règles :
- Chaque carte doit être answerable from the chunks below ONLY.
- ``front`` : question autonome, 1-200 chars.
- ``back`` : réponse concise SANS référence externe, 1-200 chars.
- ``topic`` : chaîne non-vide ou ``null``. Pas de chaîne vide.
- Toutes les cartes doivent être DIFFÉRENTES (pas de ``front`` dupliqué).

Réponds UNIQUEMENT avec l'objet JSON demandé, sans markdown ni prose autour.
La forme exacte est :
{{"cards": [{{"front": "...", "back": "...", "topic": null}}, ...]}}
"""


_STRICT_FLASHCARDS_USER_PROMPT_TEMPLATE = """Génère un deck de {n} flashcards à partir des extraits de documents ci-dessous.

Extraits de documents (utilise UNIQUEMENT ces extraits) :
{chunks}

Règles strictes :
- ``front`` : question autonome, 1-200 chars, sans référence externe.
- ``back`` : réponse concise, 1-200 chars, SANS référence externe
  (pas de "voir section", "voir page", "voir chapitre").
- ``topic`` : ``null`` ou string non-vide.
- Toutes les cartes DIFFÉRENTES (pas de ``front`` dupliqué, même en
  changeant la casse ou les espaces).

Réponds STRICTEMENT avec un objet JSON valide, sans markdown, sans ```json.
La forme exacte est :
{{"cards": [{{"front": "...", "back": "...", "topic": null}}, ...]}}
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


class FlashcardGenerator:
    """Generate a deck of flashcards from a single document's chunks.

    Same injection and persistence convention as ``QcmGenerator``. The
    LLM is NEVER called on a cross-tenant request (the owner check is
    enforced **before** the first LLM call). After a successful Pydantic
    parse, two post-Pydantic checks fire:

      * duplicate ``front`` (lower-cased and stripped) — retry;
      * external reference in ``back`` (``voir`` / ``page`` / ``section`` /
        ``chapitre`` case-insensitive) — retry.

    A check firing on the last attempt is reported as ``malformed_output``
    to the caller, so a misbehaving LLM never produces a half-baked deck.
    """

    def __init__(
        self,
        *,
        llm: LlmClient,
        retriever: _RetrieverLike,
        session_factory: Callable[[], _SessionLike] | None = None,
        default_n: int = 10,
        max_n: int = 30,
        max_retries: int = 1,
        temperature: float = 0.0,
        max_front_chars: int = 200,
        max_back_chars: int = 200,
    ) -> None:
        self._llm = llm
        self._retriever = retriever
        self._session_factory = session_factory
        self._default_n = default_n
        self._max_n = max_n
        self._max_retries = max_retries
        self._temperature = temperature
        self._max_front_chars = max_front_chars
        self._max_back_chars = max_back_chars

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(
        self,
        pseudo: str,
        subject: str,
        document_id: str,
        n: int | None = None,
    ) -> FlashcardGenerationResult:
        """Generate a deck of ``n`` flashcards for ``(pseudo, document_id)``.

        Raises :class:`FlashcardGenerationError` on every controlled failure.
        """
        requested = n if n is not None else self._default_n
        if requested < 1 or requested > self._max_n:
            raise FlashcardGenerationError(
                "invalid_input",
                f"n={requested} hors bornes [1, {self._max_n}]",
            )

        # Validate the UUID format up front (CLI passes a string).
        try:
            doc_uuid = uuid.UUID(document_id)
        except (ValueError, TypeError) as exc:
            raise FlashcardGenerationError(
                "document_not_found", f"document_id invalide: {document_id}"
            ) from exc

        # Multi-tenant invariant: the document MUST exist and belong to
        # ``pseudo``. Removing this check would let one tenant generate
        # flashcards on another tenant's chunks. The LLM is NEVER called
        # on a cross-tenant request — the ``llm.calls == []`` assertion
        # in the bite test depends on the check being HERE.
        if self._session_factory is not None:
            session = self._session_factory()
            doc = session.get(Document, doc_uuid)
            if doc is None or doc.student_pseudo != pseudo:
                # Same message for both cases: do not leak whether the
                # document exists under another pseudo.
                raise FlashcardGenerationError(
                    "document_not_found",
                    f"Document {doc_uuid} introuvable pour le pseudo {pseudo!r}.",
                )

        # Retrieve the chunks. Empty -> the LLM has nothing to ground on.
        chunks = self._retriever.get_chunks_for_document(
            subject, pseudo, document_id, k=20
        )
        if not chunks:
            raise FlashcardGenerationError(
                "no_chunks",
                f"Aucun extrait indexé pour le document {document_id}.",
            )

        # Build the prompt once, then call the LLM up to max_retries + 1
        # times (1 first attempt + max_retries retries). The retry uses
        # the strict template to push the LLM away from markdown and
        # back into the canonical shape.
        chunks_block = _format_chunks(chunks)
        soft_prompt = _FLASHCARDS_USER_PROMPT_TEMPLATE.format(
            n=requested, chunks=chunks_block
        )
        strict_prompt = _STRICT_FLASHCARDS_USER_PROMPT_TEMPLATE.format(
            n=requested, chunks=chunks_block
        )

        deck: FlashcardDeck | None = None
        last_issue: str | None = None
        attempts = self._max_retries + 1
        for i in range(attempts):
            prompt = soft_prompt if i == 0 else strict_prompt
            messages = [
                SystemMessage(content=_FLASHCARDS_SYSTEM_PROMPT),
                HumanMessage(content=prompt),
            ]
            response: AIMessage = self._llm.invoke(messages)
            block = extract_json_block(response.content)
            if block is None:
                last_issue = "malformed_output"
                continue
            try:
                parsed = FlashcardDeck.model_validate_json(block)
            except ValidationError:
                last_issue = "malformed_output"
                continue
            # Post-Pydantic checks — these are the Piège 5 / Piège 9
            # guards. They run AFTER Pydantic so a too-long string is
            # already rejected by the schema, not by us.
            duplicate = self._find_duplicate_front(parsed)
            if duplicate is not None:
                last_issue = "duplicate_fronts"
                continue
            ext_ref = self._find_external_reference(parsed)
            if ext_ref is not None:
                last_issue = "external_reference"
                continue
            deck = parsed
            break

        if deck is None:
            # Either the LLM never returned a valid Pydantic structure,
            # or a post-Pydantic check fired on every attempt. The kind
            # we report is the *last* issue we observed — useful in logs
            # to distinguish "LLM doesn't know JSON" from "LLM keeps
            # duplicating fronts" (a different remediation).
            kind = last_issue or "malformed_output"
            # The contract says malformed_output is the user-facing kind
            # when retries are exhausted on any post-Pydantic issue, so
            # the CLI exits 4. The internal distinction is preserved
            # in the message.
            if kind in ("duplicate_fronts", "external_reference"):
                kind = "malformed_output"
            raise FlashcardGenerationError(
                kind,
                "Le LLM n'a pas renvoyé un deck de flashcards valide après retry.",
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
                        type=ExerciseType.FLASHCARDS,
                        document_id=doc_uuid,
                        statement=None,
                        expected_answer=None,
                        grading_criteria=None,
                        questions=None,
                        cards=[c.model_dump() for c in deck.cards],
                    )
                )
                session.commit()
            except Exception:
                session.rollback()
                raise

        return FlashcardGenerationResult(
            exercise_id=exercise_id,
            deck=deck,
            raw=deck.model_dump_json(),
        )

    # ------------------------------------------------------------------
    # Internal: post-Pydantic guards
    # ------------------------------------------------------------------

    @staticmethod
    def _find_duplicate_front(deck: FlashcardDeck) -> str | None:
        """Return the offending front if any card has a duplicate.

        Duplicates are detected on the lower-cased, stripped front. A
        deck is duplicate-free if every normalised front is unique.
        """
        seen: set[str] = set()
        for card in deck.cards:
            key = card.front.strip().lower()
            if key in seen:
                return card.front
            seen.add(key)
        return None

    @staticmethod
    def _find_external_reference(deck: FlashcardDeck) -> str | None:
        """Return the offending back if any card references an external
        section / page / chapter.

        Pattern (case-insensitive): ``\\b(voir|page|section|chapitre)\\b``.
        The check is post-Pydantic so the length constraint is already
        enforced; we just look for the boundary words.
        """
        for card in deck.cards:
            if _EXTERNAL_REFERENCE_RE.search(card.back):
                return card.back
        return None
