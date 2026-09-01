"""Free-style exercise generator (s06 — probleme / redaction).

Generates one of two exercise flavours on top of the same RAG pipeline as
``QcmGenerator``:

* ``probleme`` — a multi-step maths problem with explicit numeric data
  and a step-by-step ``expected_answer`` solution;
* ``redaction`` — a French writing prompt with a target word count and a
  closed-set ``register``, plus a detailed grading rubric.

The pipeline mirrors s03 (validate inputs, validate document ownership,
fetch chunks, prompt the LLM with a soft template, retry with a strict
template on parse failure, persist the validated ``Exercise`` row). The
multi-tenant invariant is enforced at the same point as in s03 — the LLM
is NEVER called on a cross-tenant request.
"""

from __future__ import annotations

import enum
import json
import uuid
from collections.abc import Callable
from typing import Annotated, Any, Literal, Protocol

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, Field, ValidationError, model_validator

from app.core.database.models import (
    Document,
    Exercise,
    ExerciseType,
    Subject,
)
from app.services.exercises._parsing import extract_json_block
from app.services.llm.client import LlmClient

# ---------------------------------------------------------------------------
# Difficulty enum (closed set)
# ---------------------------------------------------------------------------


class Difficulty(str, enum.Enum):
    """Closed enumeration of accepted difficulty levels."""

    FACILE = "facile"
    MOYEN = "moyen"
    DIFFICILE = "difficile"


# ---------------------------------------------------------------------------
# Pydantic schemas (per the plan: D3 list[str], D4 min_words/max_words)
# ---------------------------------------------------------------------------


# Closed set of accepted registers for ``redaction`` exercises.
_REDACTION_REGISTERS = (
    "courant",
    "soutenu",
    "familier",
    "argumentatif",
    "narratif",
)


class ProblemeStatement(BaseModel):
    """A maths problem (multi-step, with explicit numeric data)."""

    type: Literal["probleme"]
    statement: str = Field(min_length=20, max_length=8000)
    # The solution must be substantial — s07 (free-form grading) reads it
    # to compare against the student's answer. Piège 2.
    expected_answer: str = Field(min_length=50, max_length=8000)
    grading_criteria: list[str] = Field(min_length=1, max_length=10)


class RedactionStatement(BaseModel):
    """A French writing prompt (with target word count and register)."""

    model_config = {"populate_by_name": True}

    type: Literal["redaction"]
    statement: str = Field(min_length=20, max_length=8000)
    expected_answer: str = Field(min_length=200, max_length=8000)
    grading_criteria: list[str] = Field(min_length=1, max_length=10)
    min_words: int = Field(ge=50, le=2000)
    max_words: int = Field(ge=50, le=2000)
    # The Pydantic ``register`` validator method on BaseModel would shadow
    # the field; we keep the wire name as ``register`` via the alias and
    # expose the value through ``target_register``.
    target_register: str = Field(alias="register")

    @model_validator(mode="after")
    def _check_range_and_register(self) -> RedactionStatement:
        if self.min_words > self.max_words:
            raise ValueError(
                f"min_words ({self.min_words}) doit être <= max_words ({self.max_words})."
            )
        if self.target_register not in _REDACTION_REGISTERS:
            raise ValueError(
                f"register {self.target_register!r} inconnu. Valeurs acceptées : "
                f"{', '.join(_REDACTION_REGISTERS)}."
            )
        return self


# Discriminated Union — Pydantic 2 picks the right schema by the ``type`` field.
FreeStatement = Annotated[
    ProblemeStatement | RedactionStatement,
    Field(discriminator="type"),
]


class FreeGenerationResult(BaseModel):
    """The successful outcome of :meth:`FreeGenerator.generate`."""

    exercise_id: uuid.UUID
    exercise: FreeStatement  # type: ignore[valid-type]
    raw: str


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class FreeGenerationError(Exception):
    """Controlled failure raised by :meth:`FreeGenerator.generate`.

    ``kind`` is a stable string the CLI / API can map to an exit code or
    HTTP status without parsing the message.
    """

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------


_FREE_SYSTEM_PROMPT = """Tu es un générateur d'exercices pour un élève de collège (11-15 ans).

Règles strictes :
1. Tu produis UNIQUEMENT des énoncés fondés sur les extraits de documents
   (chunks) fournis dans le message de l'utilisateur. Tu n'utilises aucune
   connaissance générale, aucune source externe.
2. Tu renvoies un objet JSON valide. La forme exacte dépend du champ
   ``type`` (voir ci-dessous).
3. ``statement`` est UNIQUEMENT l'énoncé, sans la solution. ``expected_answer``
   est UNIQUEMENT la solution complète avec la démarche étape par étape.
4. Tu n'inclus aucun texte autour du JSON. Pas de markdown, pas de prose.
5. Le sujet doit être adapté à un élève de collège (11-15 ans). Pas de sujet
   violent, politique, religieux ou sexuel.
"""


_PROBLEME_USER_PROMPT_TEMPLATE = """Génère un problème de maths de difficulté {difficulty}.

Extraits de documents (utilise UNIQUEMENT ces extraits) :
{chunks}

Sujet / thème : {topic}

Difficulté : {difficulty}
- facile : 1-2 étapes, nombres entiers, contexte simple (courses, voyage), pas de distracteur.
- moyen : 2-3 étapes, mélange d'entiers et décimaux, contexte réaliste, 1 distracteur.
- difficile : 3-4 étapes, fractions ou pourcentages, mise en équation possible, 1-2 distracteurs.

Règles :
- ``statement`` est UNIQUEMENT l'énoncé, sans la solution. L'énoncé DOIT
  contenir des données numériques explicites (nombres entiers, décimaux,
  fractions ou pourcentages selon la difficulté).
- ``expected_answer`` est UNIQUEMENT la solution complète avec la
  démarche étape par étape (au moins 4 lignes de démarche).
- ``grading_criteria`` est une liste de 3 à 5 critères vérifiables.

Réponds UNIQUEMENT avec l'objet JSON demandé, sans markdown ni prose autour.
La forme exacte est :
{{"type": "probleme", "statement": "...", "expected_answer": "...", "grading_criteria": ["...", "..."]}}
"""


_PROBLEME_STRICT_USER_PROMPT_TEMPLATE = """Génère un problème de maths de difficulté {difficulty}.

Extraits de documents (utilise UNIQUEMENT ces extraits) :
{chunks}

Sujet / thème : {topic}

Difficulté : {difficulty}

Règles strictes :
- ``statement`` : UNIQUEMENT l'énoncé, sans la solution. L'énoncé DOIT contenir
  des données numériques explicites (entiers, décimaux, fractions, pourcentages).
- ``expected_answer`` : UNIQUEMENT la solution complète avec démarche
  étape par étape (>= 4 lignes).
- ``grading_criteria`` : 3 à 5 critères vérifiables.

Réponds STRICTEMENT avec un objet JSON valide, sans markdown, sans ```json.
La forme exacte est :
{{"type": "probleme", "statement": "...", "expected_answer": "...", "grading_criteria": ["...", "..."]}}
"""


_REDACTION_USER_PROMPT_TEMPLATE = """Génère un sujet de rédaction de français de difficulté {difficulty}.

Extraits de documents (utilise UNIQUEMENT ces extraits) :
{chunks}

Sujet / thème : {topic}

Difficulté : {difficulty}
- facile : 100-200 mots, sujet concret, plan suggéré.
- moyen : 200-400 mots, sujet argumentatif ou narratif, plan suggéré.
- difficile : 400-700 mots, sujet nuancé, plan suggéré, contraintes stylistiques.

Règles :
- Le sujet doit être adapté à un élève de collège (11-15 ans). Pas de sujet
  violent, politique, religieux ou sexuel.
- ``min_words`` et ``max_words`` : entiers cohérents avec la difficulté.
- ``register`` : l'un de : courant, soutenu, familier, argumentatif, narratif.
- ``statement`` est UNIQUEMENT la consigne, sans corrigé type.
- ``expected_answer`` est UNIQUEMENT le corrigé type (plan détaillé + éléments
  attendus). Minimum 200 caractères.
- ``grading_criteria`` est une liste de 3 à 5 critères vérifiables.

Réponds UNIQUEMENT avec l'objet JSON demandé, sans markdown ni prose autour.
La forme exacte est :
{{"type": "redaction", "statement": "...", "expected_answer": "...", "grading_criteria": ["..."], "min_words": N, "max_words": N, "register": "..."}}
"""


_REDACTION_STRICT_USER_PROMPT_TEMPLATE = """Génère un sujet de rédaction de français de difficulté {difficulty}.

Extraits de documents (utilise UNIQUEMENT ces extraits) :
{chunks}

Sujet / thème : {topic}

Difficulté : {difficulty}

Règles strictes :
- Sujet adapté à un élève de collège. Pas de sujet violent, politique, religieux
  ou sexuel.
- ``min_words`` <= ``max_words``. Les deux entre 50 et 2000.
- ``register`` : l'un de : courant, soutenu, familier, argumentatif, narratif.
- ``statement`` : UNIQUEMENT la consigne, sans corrigé.
- ``expected_answer`` : corrigé type (>= 200 caractères).
- ``grading_criteria`` : 3 à 5 critères.

Réponds STRICTEMENT avec un objet JSON valide, sans markdown, sans ```json.
La forme exacte est :
{{"type": "redaction", "statement": "...", "expected_answer": "...", "grading_criteria": ["..."], "min_words": N, "max_words": N, "register": "..."}}
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


class FreeGenerator:
    """Generate a free-style exercise (probleme or redaction).

    Follows the same injection and persistence conventions as
    :class:`QcmGenerator`. The closed ``Difficulty`` enum and the closed
    ``type`` set are validated inside :meth:`generate`; a bad value raises
    :class:`FreeGenerationError` with ``kind="invalid_difficulty"`` or
    ``kind="invalid_type"``. The multi-tenant invariant is enforced by the
    document ownership check **before** any LLM call.
    """

    _ALLOWED_TYPES = ("probleme", "redaction")

    def __init__(
        self,
        *,
        llm: LlmClient,
        retriever: _RetrieverLike,
        session_factory: Callable[[], _SessionLike] | None = None,
        default_difficulty: str = "moyen",
        difficulty_options: tuple[str, ...] = ("facile", "moyen", "difficile"),
        max_retries: int = 1,
        temperature: float = 0.0,
        max_statement_chars: int = 8000,
    ) -> None:
        self._llm = llm
        self._retriever = retriever
        self._session_factory = session_factory
        self._default_difficulty = default_difficulty
        self._difficulty_options = difficulty_options
        self._max_retries = max_retries
        self._temperature = temperature
        self._max_statement_chars = max_statement_chars

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(
        self,
        pseudo: str,
        subject: str,
        type: str,
        document_id: str,
        topic: str,
        difficulty: str | None = None,
    ) -> FreeGenerationResult:
        """Generate a free-style exercise for ``(pseudo, document_id)``.

        Raises :class:`FreeGenerationError` on every controlled failure.
        """
        # 1. Validate the type discriminator.
        if type not in self._ALLOWED_TYPES:
            raise FreeGenerationError(
                "invalid_type",
                f"type={type!r} non supporté. Valeurs acceptées : "
                f"{', '.join(self._ALLOWED_TYPES)}.",
            )

        # 2. Validate the difficulty (closed set, like s03 for ``n``).
        chosen = difficulty or self._default_difficulty
        try:
            Difficulty(chosen)
        except ValueError as exc:
            raise FreeGenerationError(
                "invalid_difficulty",
                f"difficulty={chosen!r} non supportée. Valeurs acceptées : "
                f"{', '.join(self._difficulty_options)}.",
            ) from exc

        # 3. Validate the UUID format up front.
        try:
            doc_uuid = uuid.UUID(document_id)
        except (ValueError, TypeError) as exc:
            raise FreeGenerationError(
                "document_not_found", f"document_id invalide: {document_id}"
            ) from exc

        # 4. Multi-tenant invariant: the document MUST exist and belong to
        # ``pseudo``. Removing this check would let one tenant generate an
        # exercise on another tenant's chunks. The LLM is NEVER called on
        # a cross-tenant request.
        if self._session_factory is not None:
            session = self._session_factory()
            doc = session.get(Document, doc_uuid)
            if doc is None or doc.student_pseudo != pseudo:
                raise FreeGenerationError(
                    "document_not_found",
                    f"Document {doc_uuid} introuvable pour le pseudo {pseudo!r}.",
                )

        # 5. Fetch the chunks (multi-tenant collection + per-document filter).
        chunks = self._retriever.get_chunks_for_document(
            subject, pseudo, document_id, k=20
        )
        if not chunks:
            raise FreeGenerationError(
                "no_chunks",
                f"Aucun extrait indexé pour le document {document_id}.",
            )

        # 6. Route to the type-specific sub-routine.
        if type == "probleme":
            return self._generate_probleme(
                pseudo, subject, doc_uuid, topic, chosen, chunks
            )
        return self._generate_redaction(
            pseudo, subject, doc_uuid, topic, chosen, chunks
        )

    # ------------------------------------------------------------------
    # Internal: type-specific routines
    # ------------------------------------------------------------------

    def _generate_probleme(
        self,
        pseudo: str,
        subject: str,
        doc_uuid: uuid.UUID,
        topic: str,
        difficulty: str,
        chunks: list[Any],
    ) -> FreeGenerationResult:
        chunks_block = _format_chunks(chunks)
        soft_prompt = _PROBLEME_USER_PROMPT_TEMPLATE.format(
            difficulty=difficulty, chunks=chunks_block, topic=topic
        )
        strict_prompt = _PROBLEME_STRICT_USER_PROMPT_TEMPLATE.format(
            difficulty=difficulty, chunks=chunks_block, topic=topic
        )
        stmt = self._call_llm_for_statement(
            pseudo, subject, doc_uuid, soft_prompt, strict_prompt, "probleme"
        )
        # After Pydantic validation, enforce the runtime safety net.
        self._enforce_statement_length(stmt)
        return self._persist(pseudo, subject, doc_uuid, stmt, "probleme")

    def _generate_redaction(
        self,
        pseudo: str,
        subject: str,
        doc_uuid: uuid.UUID,
        topic: str,
        difficulty: str,
        chunks: list[Any],
    ) -> FreeGenerationResult:
        chunks_block = _format_chunks(chunks)
        soft_prompt = _REDACTION_USER_PROMPT_TEMPLATE.format(
            difficulty=difficulty, chunks=chunks_block, topic=topic
        )
        strict_prompt = _REDACTION_STRICT_USER_PROMPT_TEMPLATE.format(
            difficulty=difficulty, chunks=chunks_block, topic=topic
        )
        stmt = self._call_llm_for_statement(
            pseudo, subject, doc_uuid, soft_prompt, strict_prompt, "redaction"
        )
        self._enforce_statement_length(stmt)
        return self._persist(pseudo, subject, doc_uuid, stmt, "redaction")

    # ------------------------------------------------------------------
    # Internal: shared LLM/retry/persist plumbing
    # ------------------------------------------------------------------

    def _call_llm_for_statement(
        self,
        pseudo: str,
        subject: str,
        doc_uuid: uuid.UUID,
        soft_prompt: str,
        strict_prompt: str,
        type_label: str,
    ) -> FreeStatement:  # type: ignore[valid-type]
        """Call the LLM, retry with the strict prompt on parse failure.

        Returns the validated Pydantic instance. Raises
        :class:`FreeGenerationError` with ``kind="malformed_output"`` after
        the configured number of retries has been exhausted.
        """
        last_text = ""
        stmt: ProblemeStatement | RedactionStatement | None = None
        attempts = self._max_retries + 1
        for i in range(attempts):
            prompt = soft_prompt if i == 0 else strict_prompt
            messages = [
                SystemMessage(content=_FREE_SYSTEM_PROMPT),
                HumanMessage(content=prompt),
            ]
            response: AIMessage = self._llm.invoke(messages)
            last_text = response.content
            block = extract_json_block(last_text)
            if block is None:
                continue
            # Use the discriminated Union to let Pydantic pick the right
            # schema by the ``type`` field. A payload missing ``type``
            # raises ValidationError, which is caught and triggers the
            # retry. ``TypeAdapter`` is the right entry point for
            # ``Annotated[Union[...], Field(discriminator=...)]`` because
            # ``model_validate_json`` on the BaseModel itself would not
            # resolve the discriminator.
            from pydantic import TypeAdapter

            adapter = TypeAdapter(FreeStatement)
            try:
                parsed = adapter.validate_json(block)
            except ValidationError:
                continue
            if isinstance(parsed, (ProblemeStatement, RedactionStatement)):
                stmt = parsed
                break
        if stmt is None:
            raise FreeGenerationError(
                "malformed_output",
                "Le LLM n'a pas renvoyé un JSON valide après retry.",
            )
        return stmt

    def _enforce_statement_length(self, stmt: BaseModel) -> None:
        if len(stmt.statement) > self._max_statement_chars:
            raise FreeGenerationError(
                "statement_too_long",
                f"statement dépasse {self._max_statement_chars} caractères "
                f"(longueur observée : {len(stmt.statement)}).",
            )

    def _persist(
        self,
        pseudo: str,
        subject: str,
        doc_uuid: uuid.UUID,
        stmt: BaseModel,
        type_label: str,
    ) -> FreeGenerationResult:
        exercise_id = uuid.uuid4()
        if self._session_factory is not None:
            session = self._session_factory()
            try:
                session.add(
                    Exercise(
                        id=exercise_id,
                        student_pseudo=pseudo,
                        subject=Subject(subject),
                        type=ExerciseType(type_label),
                        document_id=doc_uuid,
                        statement=stmt.statement,
                        expected_answer=stmt.expected_answer,
                        grading_criteria=list(stmt.grading_criteria),
                        questions=None,
                    )
                )
                session.commit()
            except Exception:
                session.rollback()
                raise
        # Build the raw JSON payload for the result (used by the CLI for
        # --json output and by tests for shape assertions).
        if isinstance(stmt, ProblemeStatement):
            raw_payload = json.dumps(stmt.model_dump())
        else:
            raw_payload = json.dumps(stmt.model_dump())
        return FreeGenerationResult(
            exercise_id=exercise_id,
            exercise=stmt,  # type: ignore[arg-type]
            raw=raw_payload,
        )
