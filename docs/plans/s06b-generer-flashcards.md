---
validated: yes
---
# Plan — Story s06b-generer-flashcards

Branch: `feature/s06b-generer-flashcards`
Research: `docs/research/s06b-generer-flashcards.md` — read it first; this plan does not repeat it.
Design: `docs/designs/s06b-generer-flashcards.md` — story purement backend, aucun écran à produire. Le design doc fige le contrat de sortie JSON du générateur et les comportements UI attendus des futures stories (s11, s16, s19, story UI de révision dédiée). Ce plan n'invente rien côté UI.

## Target story

**Story** : s06b-generer-flashcards — Générer des flashcards (recto : question, verso : réponse) à partir d'un de mes documents.

**Complexity** : 3 (LLM generation + structured output + persistence). Confirmé à la recherche § 1, aucune divergence.

### Acceptance criteria (7 ACs)

1. CLI `python -m ktutor.cli generate-flashcards --pseudo <p> --document-id <id> --n 10` retourne un JSON avec 10 cartes, chacune avec `front` (question), `back` (réponse), `topic` (optionnel).
2. Sortie JSON valide, parseable sans nettoyage manuel.
3. Flashcards générées **UNIQUEMENT** à partir du document spécifié (chunks filtrés par `document_id`).
4. Chaque `front` est une question autonome (pas un fragment dépendant du contexte) ; `back` est une réponse concise.
5. Deck persisté en PostgreSQL avec `pseudo`, `document_id`, `generation_date`, cards JSON.
6. Test : schéma JSON valide (`front`/`back`/`topic` présents et non vides).
7. Test : isolation multi-tenant — `pseudo_a` ne peut pas lire le deck de `pseudo_b`.

## Decisions tranchées au planning

Issues de la recherche § 6, **toutes adoptées telles quelles** (D1-D6) :

- **D1** — **Option A** : nouvelle colonne `cards: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)` sur `Exercise`. Sémantiquement correct (1 colonne = 1 type d'exercice), accepte `{front, back, topic}`. Option B (réutiliser `questions`) est sémantiquement fausse ; option C (réutiliser `grading_criteria`) bloque s07.
- **D2** — **Ordre imposé par l'historique** : s06 a déjà été squash-merge sur `main` (f928d65, PR #7) avant le début de s06b. L'enum `ExerciseType` contient déjà `QCM`, `PROBLEME`, `REDACTION`. s06b ajoute `FLASHCARDS` au résultat (union triviale de 4 valeurs). Le rebase en étape 0 suffit ; D2 est obsolète par l'évolution.
- **D3** — **Option A** (rejet + retry) si le LLM produit des `front` dupliqués. Conforme au pattern s03 (retry on `malformed_output`), préserve l'intention pédagogique (« 10 cartes DIFFÉRENTES »).
- **D4** — **Option A** : `Field(max_length=200)` sur `front` ET `back`. La story le fixe explicitement ; 200 chars suffisent largement pour une réponse concise.
- **D5** — **Option A** : `default_n=10` (cohérent AC1), `max_n=30` (cohérent stories.md:253). Ne pas aligner sur QCM (5/20 inadapté au rappel actif).
- **D6** — `topic: str | None` (None ou string non-vide). Le test AC6 couvre les 2 cas. Si le LLM produit `topic=""`, le validateur post-Pydantic le coerce à `None` (Pydantic `field_validator` ou coercion explicite).

### Décision complémentaire D7 — Réutilisation de `_parsing.py` créé par s06

s06 a extrait `extract_json_block` vers `backend/app/services/exercises/_parsing.py` (mutualisé entre `qcm_generator.py` et `free_generator.py`). **s06b importe depuis `_parsing.py`**, ne redéfinit pas `_extract_json_block` dans `flashcard_generator.py`. Cela évite la divergence et aligne s06b sur la convention s06.

### Décision complémentaire D8 — `cards` schema et validation post-Pydantic

Le schéma Pydantic `FlashcardSchema(front, back, topic)` est validé carte par carte. Après validation du deck complet, une **validation post-Pydantic** détecte :
- `front` dupliqué (lower-cased et stripé) → `FlashcardGenerationError("duplicate_fronts")` → retry.
- `back` contenant un renvoi externe (regex `\b(voir|page|section|chapitre)\b` case-insensitive) → `FlashcardGenerationError("external_reference")` → retry. Le LLM peut produire « voir section 2.1 » comme back (Piège #9), ce qui viole AC4.

Ces deux validations sont dans le service (pas le schéma Pydantic), conformément au pattern s03.

## Tasks (ordered)

### Étape 0 — Préparation du worktree

0. [x] **Rebase sur main pour intégrer s05 et s06** : `git fetch origin && git rebase origin/main`. Le main est à `f928d65` (= s05 c8c9617 + s06 squash f928d65). Conflits attendus : `models.py` (ajout `FLASHCARDS` après `PROBLEME`/`REDACTION`) et `cli.py` (ajout `generate_flashcards` après `generate_exercise`). Tous triviaux (union). **Vérification** : `git log --oneline -3` montre les commits s05 et s06 squashés en `main`.

### Étape 1 — Outillage (config + modèle)

1. [x] **Étendre `backend/app/core/database/models.py`** : ajouter `FLASHCARDS = "flashcards"` à `ExerciseType` (qui contient déjà QCM/PROBLEME/REDACTION après rebase). Ajouter la colonne `cards: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)` au modèle `Exercise` (après `questions` ligne 132 du fichier rebasé). **Vérification** : test dans `tests/core/test_models.py` :
   - `TestExercise::test_exercise_creation_with_flashcards_cards` (cards populé avec liste de dicts, type=FLASHCARDS, statement/expected_answer/grading_criteria null).
2. [x] **Étendre `backend/app/core/config.py`** : bloc `FLASHCARDS_*` après le bloc `FREE_*` (créé par s06), avec :
   - `flashcards_default_n: int = 10` (env `FLASHCARDS_DEFAULT_N`)
   - `flashcards_max_n: int = 30` (env `FLASHCARDS_MAX_N`)
   - `flashcards_max_retries: int = 1` (env `FLASHCARDS_MAX_RETRIES`)
   - `flashcards_temperature: float = 0.0` (env `FLASHCARDS_TEMPERATURE`)
   - `flashcards_max_front_chars: int = 200` (env `FLASHCARDS_MAX_FRONT_CHARS`)
   - `flashcards_max_back_chars: int = 200` (env `FLASHCARDS_MAX_BACK_CHARS`)
   - **Vérification** : test dans `tests/core/test_config.py` (ajouter `TestFlashcardSettings::test_default_flashcard_settings` qui assert les 6 valeurs par défaut).
3. [x] **Étendre `backend/.env.example`** : 6 variables `FLASHCARDS_*` commentées après le bloc `FREE_*` (lignes ajoutées par s06).

### Étape 2 — Générateur de flashcards (Pydantic + LLM + persistence)

4. [x] **Créer `backend/app/services/exercises/flashcard_generator.py`** avec :
   - **Schémas Pydantic** :
     - `FlashcardSchema(front: str = Field(min_length=1, max_length=200), back: str = Field(min_length=1, max_length=200), topic: str | None = None)` avec `field_validator("topic")` qui coerce `""` → `None`.
     - `FlashcardDeck(type: Literal["flashcards"], cards: list[FlashcardSchema] = Field(min_length=1, max_length=30))`.
     - `FlashcardGenerationResult(exercise_id: uuid.UUID, deck: FlashcardDeck, raw: str)`.
   - **Exceptions** : `FlashcardGenerationError(Exception)` avec `kind: str` ∈ `{"document_not_found", "invalid_input", "no_chunks", "malformed_output", "storage_failure", "duplicate_fronts", "external_reference"}` (cf. recherche § 5 Pièges 3, 4, 5, 9).
   - **Helpers** : importer `extract_json_block` depuis `app.services.exercises._parsing` (créé par s06 — D7). **Ne pas redéfinir** `_extract_json_block` localement.
   - **Prompts** :
     - `_FLASHCARDS_SYSTEM_PROMPT` : explique les invariants (recto = question autonome, verso = réponse concise SANS renvoi externe, pas de doublons, fondé UNIQUEMENT sur les chunks).
     - `_FLASHCARDS_USER_PROMPT_TEMPLATE` : injecte `n`, chunks, consigne « chaque carte doit être answerable from the chunks below ONLY ».
     - `_STRICT_FLASHCARDS_USER_PROMPT_TEMPLATE` : pour le retry, exige UNIQUEMENT le JSON.
   - **`FlashcardGenerator` classe** : constructeur `__init__(self, *, llm: LlmClient, retriever: Retriever, session_factory: Callable[[], _SessionLike] | None = None, default_n: int = 10, max_n: int = 30, max_retries: int = 1, temperature: float = 0.0, max_front_chars: int = 200, max_back_chars: int = 200)`. Méthode publique :
     - `generate(pseudo: str, subject: str, document_id: str, n: int | None = None) -> FlashcardGenerationResult` :
       1. Valide `n` (1 ≤ n ≤ `max_n`) → sinon `FlashcardGenerationError("invalid_input", ...)`.
       2. Valide `uuid.UUID(document_id)`. Si `session_factory` non None : récupère le document, vérifie `document.student_pseudo == pseudo`. Échec ou mauvais pseudo : `FlashcardGenerationError("document_not_found", ...)` (même message, pas de leak cross-tenant). **Bite test critique** : le LLM n'est PAS appelé sur requête cross-tenant.
       3. `chunks = self._retriever.get_chunks_for_document(subject, pseudo, document_id, k=20)`. Si vide : `FlashcardGenerationError("no_chunks", ...)`.
       4. Construit le user prompt avec les chunks et `n`.
       5. Appelle `self._llm.invoke([SystemMessage, HumanMessage])`. Boucle retry 1 fois avec prompt strict en cas d'échec Pydantic. Si retry échoue : `FlashcardGenerationError("malformed_output", ...)`.
       6. **Validation post-Pydantic** : détecte `front` dupliqués (lower-cased et stripés) → `FlashcardGenerationError("duplicate_fronts", ...)` → retry. Si retry produit encore des doublons : `malformed_output` final.
       7. **Validation post-Pydantic** : détecte `back` avec renvoi externe (regex `\b(voir|page|section|chapitre)\b` case-insensitive) → `FlashcardGenerationError("external_reference", ...)` → retry. Si retry produit encore un renvoi : `malformed_output` final.
       8. Si `session_factory` non None : `session.add(Exercise(student_pseudo=pseudo, subject=Subject(subject), type=ExerciseType.FLASHCARDS, document_id=doc_uuid, cards=deck.model_dump()))` + `session.commit()`.
       9. Retourne `FlashcardGenerationResult(exercise_id=..., deck=deck, raw=deck.model_dump_json())`.
   - **Vérification** : tests dans `tests/services/exercises/test_flashcard_generator.py` (cf. § Tests).

### Étape 3 — CLI

5. [x] **Étendre `backend/app/cli.py`** :
   - Ajouter `_build_flashcard_service() -> FlashcardGenerator` à côté de `_build_free_service()` (ajouté par s06). Wire-up : `ChromaStore`, `build_embedding_provider`, `build_llm_client`, `Retriever`, `FlashcardGenerator` (avec `default_n=settings.flashcards_default_n`, `max_n=settings.flashcards_max_n`, `max_retries=settings.flashcards_max_retries`, `temperature=settings.flashcards_temperature`, `max_front_chars=settings.flashcards_max_front_chars`, `max_back_chars=settings.flashcards_max_back_chars`).
   - Ajouter la commande typer `generate_flashcards(...)` à côté de `generate_exercise` (ajouté par s06). Options :
     - `--pseudo` (required)
     - `--subject` (required, `maths|francais`)
     - `--document-id` (required, UUID)
     - `--n` (default = `flashcards_default_n` du settings, 1-30)
   - Mapping d'exceptions vers exit codes (réutilise les constantes existantes `EXIT_QCM_DOCUMENT_NOT_FOUND=5` et `EXIT_QCM_LLM_FAILURE=4` — pas de duplication, le commentaire CLI ligne 336-337 confirme) :
     - `document_not_found`, `invalid_input` → exit 5.
     - `malformed_output`, `no_chunks`, `storage_failure`, `duplicate_fronts`, `external_reference` → exit 4.
   - Helpers d'affichage `_print_flashcard_result(result)` et `_print_flashcard_error(error: FlashcardGenerationError)` à côté de `_print_free_result` et `_print_free_error`.
   - **Vérification** : tests dans `tests/cli/test_cli.py::TestGenerateFlashcards` (cf. § Tests).

### Étape 4 — Tests

6. [x] **Créer `backend/tests/services/exercises/test_flashcard_generator.py`** avec ~12 tests :
   - Pattern réutilisé : `_ScriptedLlm`, `_TrackingSession`, fixtures `memory_db`, `_SessionFactory` (depuis `test_qcm_generator.py:47-211`).
   - Tests unitaires :
     - `test_flashcards_returns_validated_pydantic_deck` (AC1, AC6) : assert `isinstance(result.deck, FlashcardDeck)` et `len(result.deck.cards) == 10`.
     - `test_flashcards_json_output_is_parseable` (AC2) : `json.loads(result.raw)` ne lève pas.
     - `test_flashcards_filter_chunks_by_document_id` (AC3) : assert `retriever.get_chunks_for_document` appelé avec `(subject, pseudo, document_id)`.
     - `test_flashcards_back_is_concise_max_200_chars` (AC4, Piège 4) : bite — script LLM retourne `back = "x" * 250` → Pydantic rejette (max_length=200) → retry.
     - `test_flashcards_back_must_not_reference_external_section` (AC4, Piège 9) : bite — script LLM retourne `back = "voir section 2.1"` → rejet post-Pydantic → retry.
     - `test_flashcards_reject_duplicate_fronts` (Piège 5) : bite — script LLM retourne 2 cartes avec le même `front` → `duplicate_fronts` → retry.
     - `test_flashcards_persists_with_flashcards_type_and_cards_json` (AC5) : assert `session.add(Exercise(...))` appelé avec `type=ExerciseType.FLASHCARDS` et `cards=[...]` (statement/expected_answer/grading_criteria null).
     - `test_flashcards_topic_optional_but_non_empty_when_present` (AC6, D6) : assert `topic=None` accepté ET `topic="algèbre"` accepté. `topic=""` doit être rejeté ou coercé à `None`.
     - `test_flashcards_cross_tenant_raises_document_not_found` (AC7, obligatoire) : Alice possède le document, Bob demande, `FlashcardGenerationError("document_not_found")` levée, `assert llm.calls == []`. **Bite critique** : si on retire la vérification d'ownership, le test mord (le LLM est appelé → appel visible dans `llm.calls`).
     - `test_flashcards_document_not_found` : `session.get(Document, ...)` retourne None → `FlashcardGenerationError("document_not_found")`.
     - `test_flashcards_no_chunks_raises` : retriever retourne liste vide → `FlashcardGenerationError("no_chunks")`.
     - `test_flashcards_invalid_n_too_large` (D5) : `n=50` > `max_n=30` → `FlashcardGenerationError("invalid_input")`.
     - `test_flashcards_invalid_uuid_raises_document_not_found` : `document_id="not-a-uuid"` → `FlashcardGenerationError("document_not_found")`.
     - `test_flashcards_retries_once_on_malformed_output` (D5) : script LLM retourne d'abord du JSON malformé, puis valide au retry. Assert `len(llm.calls) == 2`.
     - `test_flashcards_fails_after_max_retries` : script LLM retourne toujours du malformé → `FlashcardGenerationError("malformed_output")` après 2 tentatives.
7. [x] **Étendre `backend/tests/cli/test_cli.py`** avec une nouvelle classe `TestGenerateFlashcards` (~5 tests) :
   - `_StubFlashcardGenerator` (drop-in pour `FlashcardGenerator`) + `stubbed_flashcard_service` (monkeypatch de `_build_flashcard_service`).
   - `test_generate_flashcards_returns_deck_with_front_back_topic` (AC1, AC6).
   - `test_generate_flashcards_json_output_is_valid` (AC2).
   - `test_generate_flashcards_document_not_found_returns_5` (AC7, multi-tenant).
   - `test_generate_flashcards_malformed_output_returns_4` (AC1, retry).
   - `test_generate_flashcards_invalid_n_returns_5` (D5).
   - `test_help_lists_generate_flashcards_command` : sanity check que la commande apparaît dans `--help`.

### Étape 5 — Vérification finale

8. [x] **Lancer la suite de tests complète** : `cd backend && python -m pytest -x -m "not integration"`. Tous les tests existants (≥ 255 après s06) + ~17 nouveaux doivent passer.
9. [x] **Vérifier la couverture** : `pytest --cov=app --cov-fail-under=80`. Le nouveau module `flashcard_generator.py` doit être couvert ≥ 80%.
10. [x] **Lint** : `ruff check app tests` clean.
11. [x] **Smoke test CLI manuel** (sanity, hors pytest) : créer un document factice, indexer 2-3 chunks, lancer `python -m ktutor.cli generate-flashcards --pseudo <p> --subject maths --document-id <id> --n 10` et vérifier que la sortie JSON contient `cards` avec 10 entrées `{front, back, topic}`.

### Étape 6 — Commit unique

12. [ ] **Un seul commit sur `feature/s06b-generer-flashcards`** (cf. convention s05, s06) : `feat(exercises): add flashcard deck generator (s06b)`. Le commit inclut :
   - Tous les changements de code (étapes 1-5).
   - Le commit isolé de l'étape 1.1 (extension `ExerciseType` + colonne `cards`) peut soit (a) fusionner dans ce commit unique, soit (b) être isolé. **Recommandation** : (a) un commit unique, plus simple à reviewer. La collision avec s06 a déjà été résolue par le squash-merge de s06, donc l'enum contient déjà 3 valeurs et s06b ajoute la 4e (union triviale).

## Run interdicts

- **Ne pas modifier `qcm_generator.py` ou `free_generator.py`** sauf si leur import de `_parsing` est cassé par le rebase (auquel cas, juste mettre à jour l'import, pas de logique). Tout autre changement est hors-scope.
- **Ne pas dupliquer `extract_json_block`** : importer depuis `app.services.exercises._parsing` (D7). Si l'import échoue après rebase, c'est un signal que le rebase n'a pas été complet.
- **Ne pas réutiliser `questions` ou `grading_criteria` pour stocker les cartes** (D1, option A retenue) : la nouvelle colonne `cards` est obligatoire.
- **Ne pas étendre `Exercise` avec d'autres colonnes** que `cards`. Les champs `statement`/`expected_answer`/`grading_criteria` sont nullables et restent tels quels.
- **Ne pas ajouter de dépendance** (`requirements.txt`). Tout le code utilise la stack existante.
- **Ne pas toucher au design system** : la story est purement backend.
- **Ne pas implémenter la correction progressive (s08)**. s06b produit l'exercice, s08 le notera plus tard.
- **Ne pas ajouter de commande `generate-redaction` ou `generate-probleme`** : c'est s06. s06b ajoute `generate-flashcards` à côté de `generate-exercise` (s06).
- **Ne pas merger dans `main`** : c'est le job de `/ks-ship`. Un commit sur la branche suffit.
- **Ne pas valider `n` côté CLI** (typer) : la validation est côté service, comme pour `n` QCM (s03) et `difficulty` free (s06).
- **Ne pas merger en premier** : c'est trop tard, s06 a déjà mergé. Le rebase suffit.

## The point everything turns on

**Le point central** est la **séparation propre entre la colonne `cards` et la structure polymorphique d'`Exercise`** (D1 — option A). Trois endroits où cela peut casser :

1. **Le discriminant `type=FLASHCARDS`** : si on omet d'ajouter `FLASHCARDS` à l'enum (ou si le rebase oublie les valeurs de s06), Pydantic/SQLAlchemy lève `LookupError` à la première insertion. Le test `test_flashcards_persists_with_flashcards_type_and_cards_json` mord. **Comparaison** : `git diff backend/app/core/database/models.py` doit montrer **les 4 valeurs** enum (`QCM`, `PROBLEME`, `REDACTION`, `FLASHCARDS`).

2. **La validation post-Pydantic des doublons** : si on retire le check `duplicate_fronts`, le test `test_flashcards_reject_duplicate_fronts` passe au vert alors qu'il devrait lever `duplicate_fronts`. **Comparaison** : le diff de `flashcard_generator.py` doit montrer le bloc de détection de doublons **après** la validation Pydantic, **avant** la persistance.

3. **Le bite test cross-tenant** : si la vérification d'ownership est déplacée **après** l'appel LLM (au lieu d'avant), le test `test_flashcards_cross_tenant_raises_document_not_found` devient rouge sur `assert llm.calls == []`. **Comparaison** : le diff de `flashcard_generator.py` doit montrer la vérification d'ownership dans `generate(...)` **avant** tout appel à `self._llm`.

## Files touched

| Fichier | Action | Rôle |
|---|---|---|
| `backend/app/core/database/models.py` | Étendre (3 lignes) | `FLASHCARDS` à `ExerciseType` + colonne `cards` sur `Exercise`. |
| `backend/app/core/config.py` | Étendre (6 lignes) | Bloc `FLASHCARDS_*` après `FREE_*`. |
| `backend/.env.example` | Étendre (6 lignes) | 6 variables `FLASHCARDS_*` commentées. |
| `backend/app/services/exercises/flashcard_generator.py` | Créer (~250 lignes) | `FlashcardGenerator` + Pydantic + prompts + exception typée. |
| `backend/app/cli.py` | Étendre (~80 lignes) | `_build_flashcard_service`, `generate_flashcards`, helpers d'affichage. |
| `backend/tests/services/exercises/test_flashcard_generator.py` | Créer (~400 lignes) | ~15 tests (cf. étape 4). |
| `backend/tests/cli/test_cli.py` | Étendre (~150 lignes) | `TestGenerateFlashcards` + `_StubFlashcardGenerator` + `stubbed_flashcard_service`. |
| `backend/tests/core/test_config.py` | Étendre (~30 lignes) | `TestFlashcardSettings::test_default_flashcard_settings`. |
| `backend/tests/core/test_models.py` | Étendre (~20 lignes) | `TestExercise::test_exercise_creation_with_flashcards_cards`. |

**Aucun changement** dans `docs/architecture.md`, `docs/design-system.md`, `docs/roadmap.md`, `docs/prd.md`, `_parsing.py`, ou les autres stories.

## Test strategy

**Niveau unitaire** (couche service) : `test_flashcard_generator.py` — 15 tests couvrent toutes les ACs, tous les pièges, et les 6 décisions D1-D6 + D7-D8. Le bite test cross-tenant (`test_flashcards_cross_tenant_raises_document_not_found`) est obligatoire. Les bites anti-régression sont explicites : retirer la regex `external_reference` mord `test_flashcards_back_must_not_reference_external_section` ; retirer le check de doublons mord `test_flashcards_reject_duplicate_fronts`.

**Niveau CLI** (couche présentation) : `test_cli.py::TestGenerateFlashcards` — 6 tests vérifient que le mapping d'exceptions → exit codes fonctionne (réutilise `EXIT_QCM_DOCUMENT_NOT_FOUND=5` et `EXIT_QCM_LLM_FAILURE=4`), et que la sortie JSON contient `cards` (AC1, AC6). Pas de duplication des invariants déjà testés en unitaire.

**Niveau settings** : `test_config.py::TestFlashcardSettings` — 1 test assert les 6 valeurs par défaut. Évite qu'un changement de settings casse silencieusement la CLI.

**Niveau modèle** : `test_models.py` — 1 test vérifie que `Exercise` accepte le type `FLASHCARDS` et stocke `cards` (les 3 autres champs polymorphiques restent null). Évite qu'une régression sur l'enum casse la persistance.

**Pas de tests a11y/Lighthouse** (story backend pur).

**Smoke test manuel** (étape 5.4) : sanity check de bout en bout, hors pytest. Documenté dans le commit message.

## Definition of Done

- Toutes les tâches du plan cochées (12/12).
- `pytest -m "not integration"` passe (≥ 272 tests attendus après ajout de ~17 nouveaux).
- `pytest --cov=app --cov-fail-under=80` passe.
- `ruff check app tests` clean.
- AC1-AC7 tous couverts par des tests unitaires ET des tests CLI.
- **Multi-tenancy** : `test_flashcards_cross_tenant_raises_document_not_found` passe, bite vérifié.
- **Tests bites anti-régression** : au moins 4 bites documentés (longueur 200, external_reference, duplicate_fronts, no_chunks) qui morderaient si la garde est retirée.
- Smoke test CLI manuel OK (sortie JSON avec `cards`).
- Commit unique sur `feature/s06b-generer-flashcards`, message conventional commit.
- Note de complétion dans le message de commit : « Cette PR complète la famille d'exercices (QCM + probleme + redaction + flashcards). L'enum `ExerciseType` contient désormais 4 valeurs ; le polymorphisme d'`Exercise` est validé par colonne (`questions` pour QCM, `statement`/`expected_answer`/`grading_criteria` pour probleme/redaction, `cards` pour flashcards). »
- Review passée (gate `Ship allowed: yes`).
