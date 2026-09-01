# Review — s06b-generer-flashcards

> Revu par : sous-agent `reviewer` (contexte frais).
> Date : 2026-09-01.
> Source : `git diff main...feature/s06b-generer-flashcards` vs `docs/plans/s06b-generer-flashcards.md` + `docs/research/s06b-generer-flashcards.md` + `docs/designs/s06b-generer-flashcards.md` + ADRs.
> Tests : **292 passés** (lancés par le reviewer) — couverture **`flashcard_generator.py` 97%** (seuil 80% global).
> Lint : `ruff check app tests` → **0 erreur**.
> Worktree : `C:\Workspace\ktutor\.worktrees\s06b-generer-flashcards` (branche `feature/s06b-generer-flashcards`).

## 1. Test suite + lint

- Ran `cd backend && python -m pytest -m "not integration" -q` myself: **292 passed, 1 warning** (Déprécation `langchain-community`, hors-scope s06b).
- Ran `cd backend && python -m pytest --cov=app.services.exercises.flashcard_generator --cov-report=term-missing tests/services/exercises/test_flashcard_generator.py` myself: 26/26 passed, **97% coverage** sur `flashcard_generator.py`. Lignes non couvertes : 195 (`_format_chunks` cas vide, déjà défendu), 402-404 (rollback storage, exception path).
- Ran `cd backend && ruff check app tests` myself: all checks passed.
- Test count breakdown : 26 service + 8 CLI + 2 flashcard-config + 1 flashcard-model = **37 nouveaux tests**. Le plan en prévoyait ~17. Le delta (+20) est du **son couverture** : TestSchema couvre 7 cas Pydantic (chacun mord), TestBackConciseAndSelfContained/TestDuplicateFronts/TestRetry doublent chaque bite « marche » et « échoue après retry ». Pas de duplication décorative.

## 2. Diff vs plan, task by task

| Plan task | Status | Commentaire |
| --- | --- | --- |
| Étape 0 — rebase sur main (s05 + s06) | Done | Conflit trivial union d'`ExerciseType` + colonne `cards`. |
| Étape 1.1 — `ExerciseType += FLASHCARDS` + colonne `cards` | Done | `models.py:50`, `models.py:145`. |
| Étape 1.2 — bloc `FLASHCARDS_*` dans `Settings` | Done | 6 settings, tous testés. |
| Étape 1.3 — `.env.example` (6 vars) | Done | Toutes commentées. |
| Étape 2.4 — `flashcard_generator.py` | Done | Schémas Pydantic, post-Pydantic checks (D8), prompts soft + strict, retry 1 fois, persistance, multi-tenant check AVANT LLM. |
| Étape 3.5 — CLI `_build_flashcard_service` + `generate_flashcards` | Done | Wire-up identique au QCM, exit codes 5/4. |
| Étape 4.6 — `test_flashcard_generator.py` | Done (26 tests) | Plan en prévoyait ~12. |
| Étape 4.7 — `test_cli.py::TestGenerateFlashcards` | Done (8 tests) | Plan en prévoyait 5-6. |
| Étape 5.8/9/10 — pytest/cov/ruff | Done | 292/292, 97%, ruff clean. |
| Étape 5.11 — smoke test CLI manuel | Non documenté | Le commit message ne mentionne pas l'exécution d'un smoke manuel. |
| Étape 6.12 — commit unique | Done | `053d211` est le commit principal, `78ea15a` est un tick trivial. |

**Drift mineur :**

- **Mapping `no_chunks` → exit 5 vs plan exit 4.** Le plan étape 3.5 dit `no_chunks` → exit 4. L'implémentation mappe à exit 5 (comme `document_not_found` et `invalid_input`). Mais le **comportement QCM existant** (`cli.py:498-501`) mappe déjà `no_chunks` à exit 5. La cohérence avec le QCM est meilleure que la lettre du plan. Le test CLI `test_generate_flashcards_no_chunks_returns_5` est cohérent avec l'implémentation. **Pas un defect, mais divergence plan/implementation** — à clarifier dans le PR.
- **Le compteur de tests dans le commit message est absent.** Le DoD du plan demandait une note de complétion. **À ajouter dans la PR description**.

**Drift absent :**

- **D7 — `extract_json_block` importé depuis `_parsing.py`**, pas redéfini. Ligne 37 du `flashcard_generator.py` : `from app.services.exercises._parsing import extract_json_block`. Vérifié : `_parsing.py` contient bien la fonction (signature `def extract_json_block(text: str) -> str | None`).
- **D8 — post-Pydantic checks présents et bite-testés.** `duplicate_fronts` (lignes 352-355) et `external_reference` (lignes 356-359) sont dans le service, conformément au plan.
- **D1, D2, D3, D4, D5, D6 — adoptées** : nouvelle colonne `cards`, enum à 4 valeurs, reject+retry sur doublons, `Field(max_length=200)`, `default_n=10`/`max_n=30`, `topic: str | None` avec coercion `""` → `None` via Pydantic `field_validator`.
- **`doc_uuid = uuid.UUID(document_id)` validé en amont** (ligne 281) avant le check d'ownership (ligne 297) — pas de leak via traceback.
- **`_parsing.py`, `qcm_generator.py`, `free_generator.py` non modifiés** — pas de régression induite.

## 3. Architecture decisions (D1-D8)

| Décision | Adoption | Vérification |
| --- | --- | --- |
| **D1** (option A) | Colonne `cards: JSON | None` | OK. `models.py:145`. |
| **D2** | Triviale (s06 a déjà mergé) | OK. 4 valeurs dans l'enum. |
| **D3** (option A) | Reject + retry sur doublons | OK. |
| **D4** (option A) | `Field(max_length=200)` | OK. |
| **D5** (option A) | `default_n=10`/`max_n=30` | OK. |
| **D6** | `topic: str | None` + coerce `""`→`None` | OK. |
| **D7** | Import depuis `_parsing.py` | OK. |
| **D8** | `duplicate_fronts` + `external_reference` dans le service | OK. |

## 4. Bite tests vérifiés (proof, pas « trust me »)

J'ai neutralisé chaque invariant central **en éditant temporairement** `flashcard_generator.py`, puis **restauré** et confirmé `git diff --exit-code` clean.

| Invariant neutralisé | Test affecté | Bite confirmé ? | Restauration propre ? |
| --- | --- | --- | --- |
| **Multi-tenant : check d'ownership AVANT appel LLM** (ligne 300) | `test_flashcards_cross_tenant_raises_document_not_found` | **OUI**. Sans `doc.student_pseudo != pseudo`, le test lève `no_chunks` au lieu de `document_not_found` → rouge. | Oui (`git diff` vide). |
| **Post-Pydantic `duplicate_fronts`** (ligne 352) | `test_flashcards_reject_duplicate_fronts` | **OUI**. Sans le check, `len(llm.calls) == 1` au lieu de `2` → rouge. | Oui. |
| **Post-Pydantic `external_reference`** (ligne 356) | `test_flashcards_back_must_not_reference_external_section` | **OUI**. Sans le check, `len(llm.calls) == 1` au lieu de `2` → rouge. | Oui. |

**Verdict bites** : les 3 invariants centraux mordent réellement. Le test bite critique (multi-tenant) est **prouvé dépendant** du check d'ownership. L'invariant « longueur 200 chars » est délégué à Pydantic (`Field(max_length=200)`) — le test `test_flashcard_schema_rejects_back_over_200_chars` mord au niveau Pydantic.

## 5. Conformité au design system

Story purement backend (`docs/designs/s06b-generer-flashcards.md` le confirme : « Aucun écran à produire »). Aucun token, couleur ou composant du design system consommé. Le contrat de sortie JSON (lignes 67-82 du design doc) est respecté : `exercise_id`, `type="flashcards"`, `cards: [{front, back, topic}]`, `topic: str | null` avec coercion `""`→`None`. **Aucun drift design system**.

## 6. Régressions sur le code touché

- `qcm_generator.py` : **non modifié** (diff vide). Tests QCM 16/16 passent.
- `free_generator.py` : **non modifié** (diff vide). Tests Free 19/19 passent.
- `_parsing.py` : **non modifié** (diff vide). Helper mutualisé préservé.
- `models.py`, `cli.py`, `config.py` : extensions additives uniquement.
- Tests QCM et Free : **non modifiés**, passent.

**Pas de régression.** Total 292/292 tests passent (255 pré-s06b + 37 nouveaux).

## 7. Conformité AGENTS.md + ADR

- AGENTS.md § Multi-tenancy : ownership check **avant** LLM (ligne 297-306). Bite cross-tenant vérifié.
- AGENTS.md § Tests : un test par AC, bite test cross-tenant présent et bite-vérifié.
- AGENTS.md § LLM : `temperature=0` par défaut, `LlmClient` Protocol réutilisé, pas de général knowledge dans le prompt.
- AGENTS.md § Pipeline : commit unique sur `feature/s06b-generer-flashcards`. Convention `feat(exercises):` respectée.
- ADR 004 (rag-isolation-by-collection) : convention `rag_<subject>_<pseudo>` réutilisée.
- ADR 003 (langgraph-supervisor) : non applicable.

**Pas de violation d'ADR**.

## 8. Findings classés

### critical
*Aucun.*

### major
*Aucun.*

### minor

1. **Drift `no_chunks` → exit code 5 vs plan exit 4.** Le plan dit exit 4, l'implémentation dit exit 5. Le comportement est **cohérent avec le QCM existant** dans le même fichier `cli.py` (ligne 498-501), donc pas une invention. Pas un defect bloquant — à clarifier dans le PR.

2. **Note de complétion « famille complète » absente du commit message.** Le plan DoD demande « Cette PR complète la famille d'exercices (QCM + probleme + redaction + flashcards) ». Le commit body ne le mentionne pas explicitement. **À ajouter dans la PR description**.

3. **Smoke test CLI manuel (étape 5.11) non documenté.** Le DoD inclut un smoke manuel. Le contrat est garanti par les tests unitaires (97% de couverture) mais un humain devrait faire un smoke réel avant ship.

4. **Sur-test de +20 tests par rapport au plan.** 26 + 8 = 34 (+ 2 config + 1 model = 37) vs ~17 prévus. Le delta est justifié par TestSchema (7 cas Pydantic) et les paires « happy + fail après retry » pour chaque bite. **Son couverture, pas décoratif**. Cosmétique.

5. **`last_issue → malformed_output` simplification** (lignes 369-378 du generator). Les kinds internes `duplicate_fronts`/`external_reference` sont perdus côté CLI (mappés à exit 4 = LLM failure). Choix défendable de contrat. **Cosmétique**.

## 9. Ce que je n'ai PAS vérifié (limites de la review)

- **Smoke test CLI de bout en bout** : pas créé de document factice, pas lancé le CLI avec un vrai LLM.
- **Comportement face à un vrai LLM** : tous les tests utilisent `_ScriptedLlm`. La qualité de la sortie réelle (Piège 4 « longueur », Piège 5 « doublons », Piège 9 « renvoi externe ») n'est vérifiable qu'à travers les bites Pydantic/service.
- **Conflit de merge avec une autre story concurrente** : pas testé (HEAD actuel contient 4 valeurs, conflit trivial en cas d'ajout d'une 5e).
- **`k=20` hardcodé** dans le retriever : si > 20 chunks, seuls les 20 premiers sont récupérés. Pas de régression, c'est la limite documentée (s01).
- **i18n** : hors-scope backend.
- **A11y** : N/A (CLI uniquement).
- **Interface utilisateur** : backend-only ; les écrans consommateurs sont des stories futures (s11, story UI dédiée).

## 10. Synthèse

Le diff implémente fidèlement le plan (D1-D8 tranchées, fichiers listés, structure respectée). Le service `flashcard_generator.py` est solidement testé (97% de couverture, 26 tests), avec 3 bites centraux vérifiés par neutralisation (multi-tenant, duplicate_fronts, external_reference). L'import depuis `_parsing.py` est correct (D7), la colonne `cards` est propre (D1), les 6 settings `FLASHCARDS_*` sont wirés. La régression sur QCM/Free est évitée (diff vide sur ces fichiers). La conformité aux ADR est préservée.

Le seul drift notable est le mapping `no_chunks` → exit 5 (au lieu de exit 4), qui est en réalité une **cohérence avec le QCM existant**. Le décompte de tests (37 vs ~17) est du sur-test justifié.

Les 5 findings minor sont des non-bloquants : drift de mapping (cohérent QCM), note de complétion manquante, smoke manuel non documenté, sur-test, simplification de `last_issue`.

Max severity: minor
Ship allowed: yes

Fichiers clés (chemins absolus) :
- `C:\Workspace\ktutor\.worktrees\s06b-generer-flashcards\backend\app\services\exercises\flashcard_generator.py`
- `C:\Workspace\ktutor\.worktrees\s06b-generer-flashcards\backend\app\services\exercises\_parsing.py` (helper mutualisé réutilisé, non modifié)
- `C:\Workspace\ktutor\.worktrees\s06b-generer-flashcards\backend\app\services\exercises\qcm_generator.py` (non modifié, régression évitée)
- `C:\Workspace\ktutor\.worktrees\s06b-generer-flashcards\backend\app\services\exercises\free_generator.py` (non modifié, régression évitée)
- `C:\Workspace\ktutor\.worktrees\s06b-generer-flashcards\backend\app\core\database\models.py` (ExerciseType étendu + colonne `cards`)
- `C:\Workspace\ktutor\.worktrees\s06b-generer-flashcards\backend\app\core\config.py` (settings FLASHCARDS_*)
- `C:\Workspace\ktutor\.worktrees\s06b-generer-flashcards\backend\.env.example` (6 vars FLASHCARDS_*)
- `C:\Workspace\ktutor\.worktrees\s06b-generer-flashcards\backend\app\cli.py` (generate-flashcards + _build_flashcard_service)
- `C:\Workspace\ktutor\.worktrees\s06b-generer-flashcards\backend\tests\services\exercises\test_flashcard_generator.py` (26 tests)
- `C:\Workspace\ktutor\.worktrees\s06b-generer-flashcards\backend\tests\cli\test_cli.py` (TestGenerateFlashcards, 8 tests)
- `C:\Workspace\ktutor\.worktrees\s06b-generer-flashcards\docs\plans\s06b-generer-flashcards.md`
- `C:\Workspace\ktutor\.worktrees\s06b-generer-flashcards\docs\research\s06b-generer-flashcards.md`
- `C:\Workspace\ktutor\.worktrees\s06b-generer-flashcards\docs\designs\s06b-generer-flashcards.md`
