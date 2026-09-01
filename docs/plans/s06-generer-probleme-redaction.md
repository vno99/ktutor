---
validated: yes
---
# Plan — Story s06-generer-probleme-redaction

Branch: `feature/s06-generer-probleme-redaction`
Research: `docs/research/s06-generer-probleme-redaction.md` — read it first; this plan does not repeat it.
Design: `docs/designs/s06-generer-probleme-redaction.md` — story purement backend, aucun écran à produire. Le design doc fige le contrat de sortie JSON du générateur et les comportements UI attendus des futures stories (s11, s16, s19). Ce plan n'invente rien côté UI.

## Target story

**Story** : s06-generer-probleme-redaction — Générer un problème de maths ou une rédaction de français.

**Complexity** : 3 (LLM generation + structured output + persistence). Confirmé à la recherche § 1, aucune divergence.

### Acceptance criteria (5 ACs)

1. CLI `python -m ktutor.cli generate-exercise --pseudo <p> --subject <s> --type probleme|redaction --topic "..." --difficulty facile|moyen|difficile` retourne un JSON avec `statement`, `expected_answer` (solution complète, pour grading ultérieur), et `grading_criteria` (liste de chaînes pour le grading LLM).
2. Pour `probleme` (maths), l'énoncé est un problème multi-étapes avec données numériques explicites.
3. Pour `redaction` (français), l'énoncé est un sujet de rédaction avec longueur et registre imposés.
4. L'exercice est persisté avec les mêmes métadonnées que le QCM (`pseudo`, `subject`, `type`, `generation_date`, `statement`, `expected_answer`, `grading_criteria`).
5. Un test vérifie que le schéma JSON est valide pour les deux types.

## Decisions tranchées au planning

Issues de la recherche § 6, **toutes adoptées telles quelles** (D1-D6) :

- **D1** — **Option C** : un service public `FreeGenerator.generate(...)` route vers deux sous-fonctions privées `_generate_probleme(...)` et `_generate_redaction(...)`. Deux schémas Pydantic distincts (`ProblemeStatement` et `RedactionStatement`) unifiés via `Union` discriminé par `Literal` dans `FreeExercise`. Pro : prompts isolés, API publique unifiée, deux schémas séparés.
- **D2** — **Option D2.c** (mixte, difficulté module le détail) :
  - `facile` : 1-2 étapes, nombres entiers < 100, contexte simple, pas de distracteur.
  - `moyen` : 2-3 étapes, mélange entiers/décimaux, contexte réaliste, 1 distracteur.
  - `difficile` : 3-4 étapes, fractions ou pourcentages, mise en équation possible, 1-2 distracteurs.
- **D3** — **Option D3.a** : `grading_criteria: list[str]`, Pydantic `Field(min_length=1, max_length=10)`. Simple, sérialisable JSON, conforme à l'AC1. La pondération est un faux besoin à ce stade.
- **D4** — **Option D4.b** : `RedactionStatement` expose `min_words: int = Field(ge=50, le=2000)` et `max_words: int` (validation croisée `min_words <= max_words`). Plus naturel pour l'élève qu'une cible ± tolérance.
- **D5** — **Option D5.a** (s03-like) : 1 retry strict, puis `FreeGenerationError("malformed_output")`. Cohérence avec le pattern validé en s03. D5.b augmente la latence sans gain clair. D5.c (`response_format=json_object`) est une optimisation prématurée.
- **D6** — **Validation côté service** : `FreeGenerator` accepte n'importe quel string pour `difficulty`, valide via un enum interne `Difficulty` (`FACILE`, `MOYEN`, `DIFFICILE`), lève `FreeGenerationError("invalid_difficulty")` sinon. Cohérent avec la validation `n` côté service de s03.

### Décision complémentaire D7 — Type field sur les schémas Pydantic

`ProblemeStatement` et `RedactionStatement` exposent chacun un champ `type: Literal["probleme"]` (resp. `"redaction"`) pour que la `Union` discriminée fonctionne proprement avec Pydantic 2. Le test bite § 8 mord si on retire ce discriminant.

## Tasks (ordered)

### Étape 0 — Préparation du worktree

0. [x] **Rebase sur main pour intégrer s05** : `git fetch origin && git rebase origin/main`. s05 a déjà été mergé (squash c8c9617) ; s05 est purement additif (nouveaux fichiers `agents/{types,citations,francais_agent,supervisor}.py`) et ne touche pas le code référencé par s06. Si conflit sur l'enum `ExerciseType` (s06b l'aurait touché mais s06b n'est pas mergé) : résoudre trivialement. **Vérification** : `git log --oneline -1` montre le commit s05 dans l'historique.

### Étape 1 — Outillage (config + modèle + settings)

1. [x] **Étendre `backend/app/core/database/models.py`** : ajouter `PROBLEME = "probleme"` et `REDACTION = "redaction"` à `ExerciseType` (l. 33-40). Les colonnes `statement`, `expected_answer`, `grading_criteria` existent déjà (l. 129-131) et restent nullables. **Action de merge** : committer cet ajout en un commit isolé au début de la branche (cf. recherche § 7.1) pour minimiser la surface de conflit avec s06b. **Vérification** : test dans `tests/core/test_models.py` :
   - `TestExercise::test_exercise_creation_with_probleme_fields` (statement + expected_answer + grading_criteria populés, type=PROBLEME).
   - `TestExercise::test_exercise_creation_with_redaction_fields` (idem pour REDACTION).
2. [x] **Étendre `backend/app/core/config.py`** : bloc `FREE_*` après le bloc QCM (l. 67-70), avec :
   - `free_default_difficulty: str = "moyen"` (env `FREE_DEFAULT_DIFFICULTY`)
   - `free_difficulty_options: str = "facile,moyen,difficile"` (env `FREE_DIFFICULTY_OPTIONS`, parsée en tuple au get_settings — convention s03 `qcm_max_questions`)
   - `free_max_retries: int = 1` (env `FREE_MAX_RETRIES`)
   - `free_temperature: float = 0.0` (env `FREE_TEMPERATURE`)
   - `free_max_statement_chars: int = 8000` (env `FREE_MAX_STATEMENT_CHARS`, filet de sécurité avant la limite 8192 de la colonne, cf. recherche § 4.1)
   - **Vérification** : test dans `tests/core/test_config.py` (ajouter `TestFreeSettings::test_default_free_settings` qui assert les 5 valeurs par défaut).
3. [x] **Étendre `backend/.env.example`** : 5 variables `FREE_*` commentées après le bloc QCM (l. 65-72), avec un commentaire expliquant le rôle de `free_max_statement_chars` (garde-fou avant la limite de la colonne).

### Étape 2 — Générateur libre (Pydantic + LLM + persistence)

4. [x] **Créer `backend/app/services/exercises/free_generator.py`** avec :
   - **Énumération interne** : `class Difficulty(str, enum.Enum): FACILE = "facile"; MOYEN = "moyen"; DIFFICILE = "difficile"`.
   - **Schémas Pydantic** :
     - `ProblemeStatement(type: Literal["probleme"], statement: str = Field(min_length=20, max_length=8000), expected_answer: str = Field(min_length=50, max_length=8000), grading_criteria: list[str] = Field(min_length=1, max_length=10))`.
     - `RedactionStatement(type: Literal["redaction"], statement: str = Field(min_length=20, max_length=8000), expected_answer: str = Field(min_length=200, max_length=8000), grading_criteria: list[str] = Field(min_length=1, max_length=10), min_words: int = Field(ge=50, le=2000), max_words: int = Field(ge=50, le=2000), register: str)` avec validator croisé `min_words <= max_words`. Le `register` est validé contre une énumération fermée (`courant`, `soutenu`, `familier`, `argumentatif`, `narratif`) via `Field(..., json_schema_extra={"enum": [...]})` ou validator custom.
     - `FreeExercise = Annotated[Union[ProblemeStatement, RedactionStatement], Field(discriminator="type")]`.
     - `FreeGenerationResult` (sortie) : `exercise_id: uuid.UUID`, `exercise: FreeExercise` (l'instance Pydantic validée), `raw: str`.
   - **Exceptions** : `FreeGenerationError(Exception)` avec `kind: str` ∈ `{"document_not_found", "invalid_difficulty", "malformed_output", "no_chunks", "storage_failure", "thin_expected_answer", "statement_too_long"}` (cf. recherche § 5 pièges 2 et 7).
   - **Helpers de parsing** : reprendre `_extract_json_block` depuis `qcm_generator.py` (l. 88-116). **Action concrète** : importer la fonction via `from app.services.exercises.qcm_generator import _extract_json_block` (privé mais dans le même package, OK) OU la copier avec un commentaire `# Extrait de qcm_generator.py:88-116, partagé pour éviter la divergence`. **Recommandation** : déplacer `_extract_json_block` vers `backend/app/services/exercises/_parsing.py` (nouveau module privé) et l'importer depuis `qcm_generator.py` ET `free_generator.py`. Cela évite la duplication et le piège « le helper diverge entre QCM et free ». **Vérification bite** : si on retire le helper, le test `test_retries_once_on_malformed_output` de QCM ET de free deviennent rouges en même temps.
   - **Prompts** :
     - `_FREE_SYSTEM_PROMPT` (commun, explique les invariants : énoncé sans solution, pas de sujet inapproprié, format JSON strict, niveau collège).
     - `_PROBLEME_USER_PROMPT_TEMPLATE` : injecte `topic`, `difficulty` (consignes D2.c), chunks. Clauses explicites : « `statement` est UNIQUEMENT l'énoncé, sans la solution. `expected_answer` est UNIQUEMENT la solution complète avec démarche étape par étape. ».
     - `_REDACTION_USER_PROMPT_TEMPLATE` : injecte `topic`, `difficulty` (consignes D4.b), chunks, registre. Clauses explicites : « Pas de sujet violent, politique, religieux. Sujet adapté à un élève de collège (11-15 ans). Le `register` doit être l'un de : courant, soutenu, familier, argumentatif, narratif. ».
     - `_STRICT_*_TEMPLATE` (deux variantes, pour le retry).
   - **`FreeGenerator` classe** : constructeur `__init__(self, *, llm: LlmClient, retriever: Retriever, session_factory: Callable[[], _SessionLike] | None = None, default_difficulty: str = "moyen", difficulty_options: tuple[str, ...] = ("facile", "moyen", "difficile"), max_retries: int = 1, temperature: float = 0.0, max_statement_chars: int = 8000)`. Méthode publique :
     - `generate(pseudo: str, subject: str, type: str, document_id: str, topic: str, difficulty: str | None = None) -> FreeGenerationResult` :
       1. Valide `type ∈ {"probleme", "redaction"}` → sinon `FreeGenerationError("invalid_type", ...)`.
       2. Valide `Difficulty(difficulty or default_difficulty)` → sinon `FreeGenerationError("invalid_difficulty", ...)`. Cohérent avec s03 (validation côté service).
       3. Valide `uuid.UUID(document_id)`. Si `session_factory` non None : récupère le document, vérifie `document.student_pseudo == pseudo`. Échec ou mauvais pseudo : `FreeGenerationError("document_not_found", ...)` (même message, pas de leak cross-tenant). **Bite test critique** : le LLM n'est PAS appelé sur requête cross-tenant.
       4. `chunks = self._retriever.get_chunks_for_document(subject, pseudo, document_id, k=20)`. Si vide : `FreeGenerationError("no_chunks", ...)`.
       5. Route vers `self._generate_probleme(pseudo, subject, document_id, topic, difficulty, chunks)` ou `self._generate_redaction(...)` selon `type`. Les deux internes suivent le même squelette : construit le user prompt, appelle le LLM (boucle retry 1 fois avec prompt strict en cas d'échec Pydantic), persiste l'`Exercise` en base (type=PROBLEME/REDACTION, statement/expected_answer/grading_criteria populés), retourne `FreeGenerationResult`.
       6. Avant persistance, valide `len(result.statement) <= max_statement_chars` (filet de sécurité). Si trop long : `FreeGenerationError("statement_too_long", ...)` (pas de troncature silencieuse).
   - **Vérification** : tests dans `tests/services/exercises/test_free_generator.py` (cf. § Tests).

### Étape 3 — CLI

5. [x] **Étendre `backend/app/cli.py`** :
   - Ajouter `_build_free_service() -> FreeGenerator` à côté de `_build_qcm_service()` (l. 135). Wire-up : `ChromaStore`, `build_embedding_provider`, `build_llm_client`, `Retriever`, `FreeGenerator` (avec `default_difficulty=settings.free_default_difficulty`, `difficulty_options=tuple(settings.free_difficulty_options.split(","))`, `max_retries=settings.free_max_retries`, `temperature=settings.free_temperature`, `max_statement_chars=settings.free_max_statement_chars`).
   - Ajouter la commande typer `generate_exercise(...)` à côté de `generate_qcm` (l. 368). Options :
     - `--pseudo` (required)
     - `--subject` (required, `maths|francais`)
     - `--type` (required, `probleme|redaction`)
     - `--document-id` (required, UUID)
     - `--topic` (required, string)
     - `--difficulty` (default = `free_default_difficulty` du settings, `facile|moyen|difficile`)
   - Mapping d'exceptions vers exit codes (cohérent avec conventions `docs/designs/s01-uploader-document.md` citées en `cli.py:13-20`) :
     - `document_not_found`, `invalid_difficulty`, `invalid_type` → exit 5.
     - `malformed_output`, `no_chunks`, `storage_failure` → exit 4.
     - `thin_expected_answer`, `statement_too_long` → exit 4 (incohérences LLM).
   - Helpers d'affichage `_print_free_result(result)` et `_print_free_error(error: FreeGenerationError)` à côté de `_print_qcm_result` et `_print_qcm_error`.
   - **Vérification** : tests dans `tests/cli/test_cli.py::TestGenerateExercise` (cf. § Tests).

### Étape 4 — Tests

6. [x] **Créer `backend/tests/services/exercises/test_free_generator.py`** avec ~12 tests :
   - Pattern réutilisé : `_ScriptedLlm`, `_TrackingSession`, fixtures `memory_db`, `_SessionFactory` (depuis `test_qcm_generator.py:47-211`).
   - Tests unitaires :
     - `test_probleme_returns_validated_pydantic_model` (AC1, AC5) : assert `isinstance(result.exercise, ProblemeStatement)`.
     - `test_redaction_returns_validated_pydantic_model` (AC1, AC5) : assert `isinstance(result.exercise, RedactionStatement)`.
     - `test_probleme_statement_has_numeric_data` (AC2, Piège 1) : bite — script LLM qui retourne un énoncé sans nombre → assert que le prompt exige des données numériques et que le test bite mord si on retire la clause.
     - `test_probleme_expected_answer_is_substantial` (AC1, Piège 2) : bite — `expected_answer="42"` → Pydantic rejette (min_length=50).
     - `test_redaction_has_target_length_and_register` (AC3, Piège 3) : assert `result.exercise.min_words <= result.exercise.max_words` et `result.exercise.register` ∈ énumération fermée.
     - `test_redaction_expected_answer_is_substantial` (AC1, Piège 2) : bite — `expected_answer="..."` < 200 chars → Pydantic rejette.
     - `test_difficulty_changes_prompt` (AC1, Piège 4) : bite — mocker `_ScriptedLlm`, générer avec `difficulty="facile"` et `difficulty="difficile"`. Assert que les deux prompts contiennent des marqueurs distincts (« facile » → « nombres entiers » ; « difficile » → « fractions »).
     - `test_persists_exercise_with_probleme_type` (AC4) : assert `session.add(Exercise(...))` appelé avec `type=ExerciseType.PROBLEME` et les 3 champs populés.
     - `test_persists_exercise_with_redaction_type` (AC4) : idem pour REDACTION.
     - `test_filters_chunks_by_document_id` (AC4) : assert `retriever.get_chunks_for_document` appelé avec les bons arguments.
     - `test_raises_document_not_found_for_cross_tenant` (multi-tenant, obligatoire) : Alice possède le document, Bob demande, `FreeGenerationError("document_not_found")` levée, `assert llm.calls == []`. **Bite critique** : si on retire la vérification d'ownership, le test mord (le LLM est appelé → appel visible dans `llm.calls`).
     - `test_raises_invalid_difficulty` (D6) : `difficulty="expert"` → `FreeGenerationError("invalid_difficulty")`.
     - `test_raises_invalid_type` (D7) : `type="qcm"` (réservé à s03) → `FreeGenerationError("invalid_type")`.
     - `test_retries_once_on_malformed_output` (D5) : script LLM retourne d'abord du JSON malformé, puis du JSON valide au retry. Assert `len(llm.calls) == 2`.
     - `test_fails_after_max_retries` (D5) : script LLM retourne toujours du malformé. Assert `FreeGenerationError("malformed_output")` après 2 tentatives.
     - `test_statement_too_long_raises` (Piège 7) : LLM retourne un énoncé > `max_statement_chars` → `FreeGenerationError("statement_too_long")`.
     - `test_redaction_avoids_inappropriate_topics` (Piège 6, best-effort) : bite — script LLM retourne un sujet violent → test vérifie qu'une liste noire de mots-clés (`guerre`, `mort`, `religion`, etc.) **n'apparaît pas** dans le `statement` une fois passé à travers le validateur Pydantic (qui ne valide PAS le sujet lui-même, c'est juste un contrôle best-effort sur la sortie). Note : ce test est mou par construction (regex), mais il documente la garde.
7. [x] **Étendre `backend/tests/cli/test_cli.py`** avec une nouvelle classe `TestGenerateExercise` (~6 tests) :
   - `_StubFreeGenerator` (drop-in pour `FreeGenerator`) + `stubbed_free_service` (monkeypatch de `_build_free_service`).
   - `test_generate_exercise_probleme_returns_statement_expected_answer_grading_criteria` (AC1, AC2, AC5).
   - `test_generate_exercise_redaction_returns_statement_expected_answer_grading_criteria` (AC1, AC3, AC5).
   - `test_generate_exercise_json_output_is_valid_for_both_types` (AC5).
   - `test_generate_exercise_document_not_found_returns_5` (AC4, multi-tenant).
   - `test_generate_exercise_malformed_output_returns_4` (AC1, retry).
   - `test_generate_exercise_invalid_difficulty_returns_5` (D6).
   - `test_help_lists_generate_exercise_command` : sanity check que la commande apparaît dans `--help`.

### Étape 5 — Vérification finale

8. [x] **Lancer la suite de tests complète** : `cd backend && python -m pytest -x -m "not integration"`. Tous les tests existants + ~20 nouveaux doivent passer.
9. [x] **Vérifier la couverture** : `pytest --cov=app --cov-fail-under=80` (le seuil défini en s03). Le nouveau module `free_generator.py` doit être couvert ≥ 80%.
10. [x] **Lint** : `ruff check app tests` clean.
11. [x] **Smoke test CLI manuel** (sanity, hors pytest) : créer un document factice, indexer 2-3 chunks, lancer `python -m ktutor.cli generate-exercise --pseudo <p> --subject maths --type probleme --topic "vitesse" --difficulty moyen --document-id <id>` et vérifier que la sortie JSON contient `statement`, `expected_answer`, `grading_criteria`.

### Étape 6 — Commit unique

12. [x] **Un seul commit sur `feature/s06-generer-probleme-redaction`** (cf. convention s05) : `feat(exercises): add free-style exercise generator (probleme, redaction) (s06)`. Le commit inclut :
   - Tous les changements de code (étapes 1-5).
   - Le commit isolé de l'étape 1.1 (`ExerciseType` étendu) doit **fusionner** dans ce commit unique — pas de commits séparés. Pour respecter la recherche § 7.1 (minimiser le conflit avec s06b), on peut soit (a) tout mettre dans un commit, soit (b) faire 2 commits (un pour l'enum, un pour le reste). **Recommandation** : (a) un commit unique, plus simple à reviewer. La collision avec s06b reste triviale (union de deux ajouts sur l'enum).

## Run interdicts

- **Ne pas modifier `qcm_generator.py` sauf pour importer `_extract_json_block`** (s'il est déplacé vers `_parsing.py`). Tout autre changement est hors-scope.
- **Ne pas étendre `Exercise` avec de nouvelles colonnes**. Les champs `statement`/`expected_answer`/`grading_criteria` sont déjà là et suffisent.
- **Ne pas ajouter de dépendance** (`requirements.txt`). Tout le code utilise la stack existante (Pydantic 2, SQLAlchemy 2, typer, loguru).
- **Ne pas toucher au design system** : la story est purement backend.
- **Ne pas implémenter la correction progressive (s08)**. s06 se contente de **produire** l'exercice. s08 consommera `expected_answer` et `grading_criteria` plus tard.
- **Ne pas ajouter la commande `generate-flashcards`** : c'est s06b. L'enum `ExerciseType` accepte `FLASHCARDS = "flashcards"` seulement si s06b l'a déjà ajouté (sinon attendre s06b pour la collision).
- **Ne pas merger dans `main`** : c'est le job de `/ks-ship`. Un commit sur la branche suffit.
- **Ne pas dupliquer `_extract_json_block`** : si on le déplace vers `_parsing.py`, importer depuis les deux générateurs. Si on le copie, le reviewer va crier.
- **Ne pas valider `difficulty` côté CLI** (typer) : la validation est côté service, comme `n` pour s03.

## The point everything turns on

**Le point central** est l'**isolement propre des deux prompts** (D1 — option C) avec une `Union` Pydantic discriminée par `Literal["probleme"]` / `Literal["redaction"]`. Trois endroits où cela peut casser :

1. **Le discriminant** : si on omet le champ `type` dans `ProblemeStatement`/`RedactionStatement`, Pydantic 2 lève `ValidationError` sur la résolution de l'Union. Le test `test_probleme_returns_validated_pydantic_model` mord (Pydantic ne sait pas trancher). **Comparaison** : vérifier en runtime que `result.exercise.type == "probleme"` (resp. `"redaction"`).

2. **La taille de l'enum** : si on n'ajoute que `PROBLEME` (oubli de `REDACTION`), le test `test_redaction_returns_validated_pydantic_model` ne peut pas instancier. **Comparaison** : `git diff backend/app/core/database/models.py` doit montrer **les deux** valeurs ajoutées.

3. **Le bite test cross-tenant** : si la vérification d'ownership est déplacée **après** l'appel LLM (au lieu d'avant), le test `test_raises_document_not_found_for_cross_tenant` devient rouge sur `assert llm.calls == []`. **Comparaison** : le diff de `free_generator.py` doit montrer la vérification d'ownership dans `generate(...)` **avant** tout appel à `self._llm`.

## Files touched

| Fichier | Action | Rôle |
|---|---|---|
| `backend/app/core/database/models.py` | Étendre (2 lignes) | Ajout `PROBLEME`, `REDACTION` à `ExerciseType`. |
| `backend/app/core/config.py` | Étendre (5 lignes) | Bloc `FREE_*` après QCM. |
| `backend/.env.example` | Étendre (5 lignes) | 5 variables `FREE_*` commentées. |
| `backend/app/services/exercises/_parsing.py` | Créer (30 lignes) | `_extract_json_block` extrait de `qcm_generator.py` (cf. étape 2). |
| `backend/app/services/exercises/qcm_generator.py` | Étendre (1 ligne) | Import depuis `_parsing.py` à la place de la définition locale. |
| `backend/app/services/exercises/free_generator.py` | Créer (~300 lignes) | `FreeGenerator` + Pydantic + prompts + exception typée. |
| `backend/app/cli.py` | Étendre (~80 lignes) | `_build_free_service`, `generate_exercise`, helpers d'affichage. |
| `backend/tests/services/exercises/test_free_generator.py` | Créer (~400 lignes) | ~17 tests (cf. étape 4). |
| `backend/tests/cli/test_cli.py` | Étendre (~200 lignes) | `TestGenerateExercise` + `_StubFreeGenerator` + `stubbed_free_service`. |
| `backend/tests/core/test_config.py` | Étendre (~30 lignes) | `TestFreeSettings::test_default_free_settings`. |
| `backend/tests/core/test_models.py` | Étendre (~40 lignes) | `TestExercise::test_exercise_creation_with_probleme_fields` + `test_exercise_creation_with_redaction_fields`. |

**Aucun changement** dans `docs/architecture.md`, `docs/design-system.md`, `docs/roadmap.md`, `docs/prd.md`, ou les autres stories.

## Test strategy

**Niveau unitaire** (couche service) : `test_free_generator.py` — 17 tests couvrent toutes les ACs, tous les pièges, et les 6 décisions D1-D6. Le bite test cross-tenant (`test_raises_document_not_found_for_cross_tenant`) est obligatoire. Les bites anti-régression sont explicites : retirer la clause de prompt mord `test_probleme_statement_has_numeric_data` ; retirer la validation Pydantic `min_length` mord `test_probleme_expected_answer_is_substantial`.

**Niveau CLI** (couche présentation) : `test_cli.py::TestGenerateExercise` — 6 tests vérifient que le mapping d'exceptions → exit codes fonctionne, et que la sortie JSON contient les 3 champs attendus (AC1, AC5). Pas de duplication des invariants déjà testés en unitaire.

**Niveau settings** : `test_config.py::TestFreeSettings` — 1 test assert les 5 valeurs par défaut. Évite qu'un changement de settings casse silencieusement la CLI.

**Niveau modèle** : `test_models.py` — 2 tests vérifient que `Exercise` accepte les 2 nouveaux types et stocke les 3 champs polymorphiques. Évite qu'une régression sur l'enum casse la persistance.

**Pas de tests a11y/Lighthouse** (story backend pur).

**Smoke test manuel** (étape 5.4) : sanity check de bout en bout, hors pytest. Documenté dans le commit message.

## Definition of Done

- Toutes les tâches du plan cochées (12/12).
- `pytest -m "not integration"` passe (≥ 220 tests attendus après ajout de ~20 nouveaux).
- `pytest --cov=app --cov-fail-under=80` passe.
- `ruff check app tests` clean.
- AC1-AC5 tous couverts par des tests unitaires ET des tests CLI.
- **Multi-tenancy** : `test_raises_document_not_found_for_cross_tenant` passe, bite vérifié.
- **Tests bites anti-régression** : au moins 3 bites documentés (prompt numérique, prompt difficulté, prompt longueur/registre) qui morderaient si la clause est retirée.
- Smoke test CLI manuel OK (sortie JSON avec les 3 champs).
- Commit unique sur `feature/s06-generer-probleme-redaction`, message conventional commit.
- Note de collision dans le message de commit : « Cette PR et `s06b-flashcards` ajoutent des valeurs au même enum `ExerciseType` ; conflit trivial à la résolution (union de deux ajouts). Le merge de s06b en premier ou en second ne change pas le résultat final. »
- Review passée (gate `Ship allowed: yes`).
