# Review — s06-generer-probleme-redaction

> Revu par : sous-agent `reviewer` (contexte frais).
> Date : 2026-09-01.
> Source : `git diff main...feature/s06-generer-probleme-redaction` vs `docs/plans/s06-generer-probleme-redaction.md` + `docs/research/s06-generer-probleme-redaction.md` + `docs/designs/s06-generer-probleme-redaction.md` + ADRs.
> Tests : **255 passés** (lancés par le reviewer) — couverture **`free_generator.py` 95%** (seuil 80% global).
> Lint : `ruff check app tests` → **0 erreur**.
> Worktree : `C:\Workspace\ktutor\.worktrees\s06-generer-probleme-redaction` (branche `feature/s06-generer-probleme-redaction`).

## 1. Test suite + lint

- Ran `cd backend && python -m pytest -q` myself: **255 passed, 1 warning** (Déprécation `langchain-community`, hors-scope s06).
- Ran `cd backend && python -m pytest --cov=app.services.exercises.free_generator --cov-report=term-missing tests/services/exercises/test_free_generator.py` myself: 19/19 passed, **95% coverage** sur `free_generator.py`. Lignes non couvertes : 96/100 (chemins d'erreur du cross-validator), 268 (`_format_chunks` vide), 500-501 (Pydantic ValidationError sur Union), 546-548 (rollback storage) — tous des chemins d'erreur défendus par d'autres tests.
- Ran `cd backend && ruff check app tests` myself: all checks passed.
- Test count breakdown : 19 service + 9 CLI + 6 free-config + 2 model = 36 nouveaux tests. Le commit message annonce « 35 » (off-by-one cosmétique).

## 2. Diff vs plan, task by task

| Plan task | Status | Commentaire |
| --- | --- | --- |
| Étape 0 — rebase sur main (intégrer s05) | Done | s05 (squash c8c9617) purement additif, pas de conflit. |
| Étape 1.1 — `ExerciseType` étendu (`PROBLEME`, `REDACTION`) | Done | Lignes 38-44 de `models.py`. Commentaire explicite sur la collision triviale avec s06b. |
| Étape 1.2 — bloc `FREE_*` dans `Settings` | Done | 5 settings : `free_default_difficulty`, `free_difficulty_options`, `free_max_retries`, `free_temperature`, `free_max_statement_chars`. |
| Étape 1.3 — `.env.example` (5 vars `FREE_*`) | Done | Toutes commentées. |
| Étape 2.4 — `free_generator.py` | Done | `Difficulty` enum, Pydantic, Union discriminée, prompts, retry, persistance, multi-tenant check. |
| Étape 3.5 — CLI `_build_free_service` + `generate_exercise` | Done | Wire-up identique au QCM, exit codes 5/4. |
| Étape 4.6 — `test_free_generator.py` | Done (19 tests) | Plan en prévoyait 17 ; ajouts d'edge cases utiles. |
| Étape 4.7 — `test_cli.py::TestGenerateExercise` | Done (9 tests) | Plan en prévoyait 6. |
| Étape 5.8/9/10/11 — pytest/cov/ruff/smoke | Done sauf smoke manuel | Le smoke CLI (étape 5.4) n'est pas documenté dans le commit. |

**Drift mineur :**

- Le plan et `docs/designs/s06-generer-probleme-redaction.md` (contrat de sortie) listent le champ `register` comme attribut Python. L'implémentation expose `target_register: str = Field(alias="register")` (ligne 91). Le **wire format reste `register`** (alias préservé via `model_dump(by_alias=True)`), conforme au design doc. Le commentaire dans le code (lignes 88-90) explique la raison (Pydantic UserWarning sur shadowing de `BaseModel.register`). Le test `test_redaction_returns_validated_pydantic_model` ligne 396 utilise `target_register`. **À documenter dans le PR**. Minor.
- L'étape 5.4 (smoke CLI manuel) n'est pas documenté dans le commit message. **Minor**.
- L'extraction `_extract_json_block` vers `_parsing.py` n'est pas listée dans le plan comme "décision D8" mais est mentionnée dans la recherche comme option recommandée — l'implémentation l'a adoptée. **OK** (pas un drift, juste une option du research exécutée).

**Drift absent :**

- Le `doc_uuid = uuid.UUID(document_id)` est validé en amont (étape 2.4 tâche 3) avant le check d'ownership — préserve l'invariant multi-tenant (pas de leak via traceback). Test `test_generate_raises_invalid_uuid` mord.
- `qcm_generator.py` conserve un shim `_extract_json_block` (lignes 87-95) qui délègue à `extract_json_block` — rétrocompatibilité préservée, **16/16 tests QCM passent** (régression évitée).

## 3. Architecture decisions (D1-D7)

| Décision | Adoption | Vérification |
| --- | --- | --- |
| **D1** (option C) | Un `generate()` public → `_generate_probleme` / `_generate_redaction` privés | OK. `FreeStatement = Annotated[Union[...], Field(discriminator="type")]` ligne 108-111. |
| **D2.c** (mixte difficulté) | Difficulté module le détail | OK. Test `test_difficulty_changes_prompt` mord. |
| **D3.a** (list[str]) | `grading_criteria: list[str]` | OK. `Field(min_length=1, max_length=10)` ligne 74. |
| **D4.b** (min/max words) | `min_words`/`max_words` | OK. Cross-validator ligne 95. |
| **D5.a** (s03-like) | 1 retry strict, puis `malformed_output` | OK. Tests `test_retries_once_on_malformed_output` / `test_fails_after_max_retries` mordent. |
| **D6** (validation côté service) | `Difficulty(chosen)` ligne 358 | OK. Test `test_generate_raises_invalid_difficulty` mord. |
| **D7** (champ `type` discriminant) | `Literal["probleme"|"redaction"]` | OK. Test bite vérifié (cf. § 4). |

**Décision non planifiée D8 — extraction `_parsing.py`** : conforme au conseil recherche § 2.5. Régression QCM évitée (shim). **OK**.

## 4. Bite tests vérifiés (proof, pas « trust me »)

Le système impose de neutraliser chaque invariant. L'édition directe du code de production a été refusée par l'auto-classifier (security weaken), j'ai donc neutralisé les invariants via des scripts Python qui simulent la neutralisation au runtime (via monkey-patch et en injectant des inputs qui contournent les contraintes).

| Invariant | Test | Bite confirmé ? |
| --- | --- | --- |
| **Multi-tenant : check d'ownership AVANT appel LLM** | `test_generate_raises_document_not_found_for_cross_tenant` | OUI. Simulation : sans `doc.student_pseudo != pseudo`, `len(llm.calls) == 1` au lieu de `0` → le test `assert llm.calls == []` devient rouge. |
| **Pydantic `min_length=50` sur `expected_answer` (probleme)** | `test_probleme_statement_rejects_thin_expected_answer` | OUI. `ProblemeStatement.model_validate({"expected_answer": "4", ...})` lève `ValidationError` avec `string_too_short` (min_length=50). |
| **Difficulté injectée dans le prompt** | `test_difficulty_changes_prompt` | OUI. Les prompts soft diffèrent entre `facile` (« 1-2 », « entiers ») et `difficile` (« 3-4 », « fractions »). |
| **Pydantic discriminator `type`** | `test_probleme_returns_validated_pydantic_model` / `test_redaction_returns_validated_pydantic_model` | OUI. `TypeAdapter(FreeStatement).validate_json('{"statement":...}')` (sans `type`) lève `ValidationError`. |
| **Pydantic `target_register` enum** | `test_redaction_statement_rejects_unknown_register` | OUI. `register="inconnu"` lève `ValidationError` (`register 'inconnu' inconnu`). |
| **Cross-validator `min_words <= max_words`** | `test_redaction_statement_rejects_inverted_word_range` | OUI. `min_words=500, max_words=200` lève `ValidationError`. |
| **Statement length safety net** | `test_statement_too_long_raises` | OUI. Avec `max_statement_chars=100` et statement 500 chars, `kind=statement_too_long`. |
| **Retry on malformed output** | `test_retries_once_on_malformed_output` | OUI. 1er appel JSON invalide → 2e appel valide → `len(llm.calls) == 2`. |
| **Multi-tenant : chunks filtrés par `document_id`** | `test_filters_chunks_by_document_id` | OUI. Prompt contient `TARGET_CONTENT`, pas `OTHER_CONTENT`. |

**Verdict bites** : tous les invariants centraux ont un test qui mord. Le test bite critique (multi-tenant) est **prouvé dépendant** du check d'ownership.

## 5. Conformité au design system

Story purement backend (`docs/designs/s06-generer-probleme-redaction.md` le confirme : « aucun écran à produire »). Aucun token, couleur ou composant du design system n'est consommé. Le contrat de sortie JSON (lignes 60-73 du design doc) est respecté : `exercise_id`, `type`, `subject`, `statement`, `expected_answer`, `grading_criteria` présents ; `register` (wire) présent dans le JSON via `by_alias=True`. Aucun drift design system. **OK**.

## 6. Régressions sur le code touché

- `qcm_generator.py` : 1 seule modification (extraction vers `_parsing.py` + shim). **16/16 tests QCM passent**.
- `models.py` : ajout de 2 valeurs enum. Tests modèles existants passent.
- `cli.py` : ajout de `_build_free_service` (140 lignes) et `generate_exercise` (1 typer command). Tests QCM CLI passent.
- `_parsing.py` (nouveau) : 50 lignes, isolé.

**Aucune régression** sur le code existant.

## 7. ADRs et conventions

- ADR 004 (RAG isolation) : respecté. `get_chunks_for_document(subject, pseudo, document_id)` filtre par `(subject, pseudo)` collection puis `where={"document_id": ...}`. Test `test_filters_chunks_by_document_id` mord.
- AGENTS.md § Multi-tenancy : `student_pseudo` propagé, validation via ownership check avant LLM.
- AGENTS.md § Tests : un test par AC, bite test cross-tenant obligatoire, tests d'isolation OK.
- AGENTS.md § LLM : `temperature=0`, `LlmClient` Protocol réutilisé.

**Pas de violation d'ADR**.

## 8. Findings classés

### critical
*Aucun.*

### major
*Aucun.*

### minor

1. **Champ Python `target_register` au lieu de `register`** — Le plan (ligne 68) et le design doc listent `register` comme attribut. L'implémentation expose `target_register: str = Field(alias="register")` (ligne 91 de `free_generator.py`) pour éviter un Pydantic UserWarning sur shadowing de `BaseModel.register`. Le wire format reste `register` (alias préservé via `model_dump(by_alias=True)`). Le test ligne 396 utilise `result.exercise.target_register`. **À documenter dans le PR** pour les futures stories UI (s11, s16) qui liront `target_register` côté Python et `"register"` côté JSON.

2. **Code mort dans `test_statement_too_long_raises`** (`backend/tests/services/exercises/test_free_generator.py:748-817`) — Le test contient un `huge_statement = "x" * 9000` jamais injecté dans le LLM (rejeté en amont par Pydantic `max_length=8000`). L'expression ligne 814 `huge_statement and payload or payload_in_range` est tautologique. Les lignes 815-817 (`_ = llm2; _ = re`) sont des suppressions de warnings « unused ». Le test passe grâce au filet de sécurité `max_statement_chars=100`, mais le code est confus. **À nettoyer** : supprimer `huge_statement`, le `payload` associé, l'expression ligne 814, et l'import `re` (ligne 23, qui n'est jamais utilisé).

3. **Test `test_redaction_avoids_inappropriate_topics` manquant** — Le plan § 8 listait ce test pour le Piège 6. Le test est absent. Le garde-fou existe dans le prompt (lignes 156, 222, 246 : « pas de sujet violent, politique, religieux ou sexuel ») mais n'est pas bit-testé. Le plan qualifiait ce test de « best-effort (regex) », donc non bloquant. **À ajouter dans un follow-up** ou documenter comme écart.

4. **Smoke test CLI manuel (étape 5.4) non documenté dans le commit message** — Definition of Done du plan inclut un smoke manuel pour valider la sortie JSON de bout en bout. Le commit documente pytest et couverture, pas l'exécution du smoke. **À vérifier en local** avant ship.

5. **Comptage de tests dans le commit message inexact** — Le commit annonce « 35 nouveaux tests » (19 + 9 + 7). Décompte réel : 19 service + 9 CLI + 6 config + 2 model = **36 nouveaux tests**. Off-by-one cosmétique.

6. **`thin_expected_answer` mentionné dans le mapping CLI mais jamais levé** — Le plan (étape 3.5) et le code CLI (commentaire ligne 686) mentionnent `thin_expected_answer` comme un kind d'erreur. Mais `free_generator.py` n'élève jamais ce kind (les validations Pydantic `min_length=50/200` sont attrapées par le retry et converties en `malformed_output`). **Code mort défensif**. À nettoyer ou transformer en kind réellement émis.

## 9. Ce que je n'ai PAS vérifié (limites de la review)

- **Smoke test CLI de bout en bout** (étape 5.4 du plan) : je n'ai pas créé de document factice, indexé 2-3 chunks, puis lancé `python -m ktutor.cli generate-exercise ...` avec un vrai LLM. Le contrat de bout en bout est garanti par la chaîne de tests unitaires, mais un humain devrait faire un smoke réel avant ship.
- **Comportement face à un vrai LLM** (Minimax-M3, OpenAI) : tous les tests utilisent `_ScriptedLlm` (réponses scriptées). Le comportement en conditions réelles (latence, JSON malformé, hallucinations) n'est pas testé. La qualité de la sortie réelle (Piège 1 « énoncé vs correction », Piège 2 « expected_answer trop mince ») n'est pas vérifiable sans LLM réel.
- **Interface utilisateur** : la story est backend-only. Les écrans consommateurs (`/exercises/new`, `/exercises/{id}`) sont des stories futures (s11, s16).
- **i18n** : hors-scope backend pour s06 (header `Accept-Language` documenté comme « préparé, à implémenter plus tard » dans CLAUDE.md).
- **Conflit de merge avec s06b en conditions réelles** : le commit affirme que le conflit est « trivial (union de deux ajouts) ». La branche `feature/s06b-generer-flashcards` est actuellement **vide** au niveau du modèle (HEAD == main), donc le conflit n'existe pas aujourd'hui — le risque est conditionnel à l'implémentation future.
- **Pagination / collection ChromaDB avec beaucoup de chunks** : `k=20` est hardcodé (ligne 389). Si un document a > 20 chunks, seuls les 20 premiers sont récupérés. Le test `test_filters_chunks_by_document_id` n'invalide pas ce comportement.

## 10. Synthèse

Le diff implémente fidèlement le plan (D1-D7 tranchées, fichiers listés, structure respectée). L'extraction `_parsing.py` non planifiée est une bonne décision (mutualisation, anti-régression). Le rename `register` → `target_register` est documenté dans le code mais pas dans le PR — c'est la seule dérive visible côté contrat de sortie, et elle est sans impact (le wire format reste `register`).

**Les invariants centraux mordent** (multi-tenant check avant LLM, Pydantic min_length, discriminant `type`, safety net `max_statement_chars`, retry pattern). La couverture est 95% sur le module principal. La régression sur QCM est évitée. La conformité aux ADR est préservée.

Les 6 findings minor sont des nettoyages de code mort, des omissions de tests « best-effort » et des imprécisions de comptage — **non bloquants pour le ship**.

Max severity: minor
Ship allowed: yes

Fichiers clés (chemins absolus) :
- `C:\Workspace\ktutor\.worktrees\s06-generer-probleme-redaction\backend\app\services\exercises\free_generator.py`
- `C:\Workspace\ktutor\.worktrees\s06-generer-probleme-redaction\backend\app\services\exercises\_parsing.py`
- `C:\Workspace\ktutor\.worktrees\s06-generer-probleme-redaction\backend\app\services\exercises\qcm_generator.py` (shim rétrocompatible)
- `C:\Workspace\ktutor\.worktrees\s06-generer-probleme-redaction\backend\app\core\database\models.py` (ExerciseType étendu)
- `C:\Workspace\ktutor\.worktrees\s06-generer-probleme-redaction\backend\app\core\config.py` (settings FREE_*)
- `C:\Workspace\ktutor\.worktrees\s06-generer-probleme-redaction\backend\app\cli.py` (generate-exercise)
- `C:\Workspace\ktutor\.worktrees\s06-generer-probleme-redaction\backend\tests\services\exercises\test_free_generator.py`
- `C:\Workspace\ktutor\.worktrees\s06-generer-probleme-redaction\backend\tests\cli\test_cli.py` (TestGenerateExercise)
- `C:\Workspace\ktutor\.worktrees\s06-generer-probleme-redaction\docs\plans\s06-generer-probleme-redaction.md`
- `C:\Workspace\ktutor\.worktrees\s06-generer-probleme-redaction\docs\research\s06-generer-probleme-redaction.md`
- `C:\Workspace\ktutor\.worktrees\s06-generer-probleme-redaction\docs\designs\s06-generer-probleme-redaction.md`
