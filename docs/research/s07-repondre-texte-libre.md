---
name: research-s07-repondre-texte-libre
description: s07-repondre-texte-libre — recherche de contexte pour /ks-plan
metadata:
  type: project
  story: s07-repondre-texte-libre
---

# Recherche — Story s07-repondre-texte-libre

> Recherche en français. Code identifiers (snake_case, PascalCase, etc.) dans leur forme d'origine. Diacritiques respectés : « réussite », « échec », « verdict », « évaluation », « élève ».

## 1. Rappel de la story

Source : `docs/stories.md` (lignes 262-294).

**As an** élève **I want** soumettre ma réponse (texte) à un exercice de type problème ou rédaction **so that** je reçoive une appréciation qualitative (positive ou échec) du LLM.

**Complexity** : 3 — LLM-as-judge + prompt engineering + parsing + persistence.

### Acceptance criteria (6 ACs, verbatim depuis `docs/stories.md:271-278`)

1. La commande `python -m ktutor.cli submit-text --exercise-id <id> --answer "..."` retourne `{is_success: bool, feedback: string, attempt_number: int}`.
2. Le grading utilise un prompt LLM qui compare la réponse de l'élève à `expected_answer` et produit un verdict (`REUSSITE` ou `ECHEC`) plus un feedback d'une phrase.
3. Le parsing du verdict est strict (regex sur la ligne `VERDICT:`) ; si absente, le système retente une fois avec un prompt plus strict, puis échoue avec une erreur claire.
4. L'attempt est persisté (même modèle `Attempt` que s04, avec `answer_text` au lieu de `answers`).
5. Un test avec un LLM stub qui retourne `VERDICT: REUSSITE` vérifie que `is_success` est `true`.
6. Un test avec un LLM stub qui ne retourne aucune ligne `VERDICT:` vérifie que le système retente puis échoue.
7. Un test vérifie l'isolation multi-tenant (pseudo_a ne peut pas soumettre à un exercise de pseudo_b).

> Note : `docs/stories.md` numérote les ACs de 1 à 7 alors que la section « Acceptance criteria » n'en contient visuellement que 6 cases cochées. Les 6 cases couvrent les 7 points (AC1 = CLI, AC2 = prompt, AC3 = retry, AC4 = persistence, AC5 = happy path stub, AC6 = no-verdict stub, AC7 = cross-tenant). On traite les 6 ACs canoniques.

### Questions ouvertes liées (PRD § Questions ouvertes)

- Aucune question ouverte n'est attachée à s07 par le PRD. Le périmètre est verrouillé par s06 (modèle `Exercise` avec `statement`/`expected_answer`/`grading_criteria`).

## 2. Code existant à réutiliser

s07 s'appuie sur les fondations livrées par s01-s04. Inventaire exhaustif.

### 2.1. Modèle `Attempt` (s04, livré — aucun ajout modèle requis)

- `backend/app/core/database/models.py:147-195` — `Attempt` complet avec `id` (UUID PK), `exercise_id` (UUID FK logique deferred s15), `student_pseudo` (String(64) indexé), `attempt_number` (int), `is_success` (bool), `raw_answers` (JSON), **`answer_text: Mapped[str | None]`** (String(8192) nullable, **pré-créé pour s07**, cf. ligne 182), **`correction_level: Mapped[str | None]`** (String(32) nullable, pré-créé pour s08), `submitted_at` (DateTime).
- **Aucun ajout de colonne n'est nécessaire** : `answer_text` est déjà en place depuis s04 (commentaire ligne 152-155 : « stay NULL until s07 »). Le grader s07 écrit dans ce champ, sans migration.
- Le `_next_attempt_number` du QCM grader (`qcm_grader.py:259-281`) — pattern `SELECT MAX(attempt_number) FROM attempts WHERE exercise_id = ? AND student_pseudo = ?` — est **réutilisable tel quel** pour le text grader (même table, même invariant).
- Le schéma `attempts` cible est documenté en `docs/architecture.md:207-217`.

### 2.2. Modèle `Exercise` polymorphique (s03 + s06, livré partiellement)

- `backend/app/core/database/models.py:90-144` — `Exercise` avec `type: Mapped[ExerciseType]` (enum ligne 33-40, à étendre par s06 avec `PROBLEME` / `REDACTION`), `statement: Mapped[str | None]` (String(8192)), `expected_answer: Mapped[str | None]` (String(8192)), `grading_criteria: Mapped[dict[str, Any] | None]` (JSON, stocke une `list[str]`).
- **s07 ne touche pas ce modèle** : il lit `statement` / `expected_answer` / `grading_criteria` depuis l'`Exercise` persisté par s06.
- **Risque de merge avec s06** : s07 suppose que `ExerciseType` contient `PROBLEME` et `REDACTION` au moment où s06 merge. Cf. décision D7 (gate bloquant).

### 2.3. Client LLM (s02, livré)

- `backend/app/services/llm/client.py:27-34` — `LlmClient` Protocol avec unique méthode `invoke(messages: list[BaseMessage]) -> AIMessage`. **s07 l'injecte** dans le constructeur de `TextGrader`.
- `backend/app/services/llm/client.py:51-79` — `build_llm_client(settings)` retourne un wrapper LangChain. Reprend `chat_temperature` (s07 créera `text_grader_temperature`).
- `_LangChainChatWrapper.invoke` (ligne 38-48) — adaptateur fin, **suffisant pour s07**. Pas de streaming nécessaire (s07 est un appel LLM ponctuel).
- LLM par défaut `minimax/minimax-m3:free` (via OpenRouter) ; pas de structured output JSON mode garanti.

### 2.4. Grader QCM comme contrepartie déterministe (s04, livré)

- `backend/app/services/exercises/qcm_grader.py:123-281` — `QcmGrader` :
  - Constructeur `QcmGrader(*, session_factory=...)` (ligne 132). **s07 adopte la même signature**, plus `llm=...`.
  - `QcmGradingError(kind, message)` (lignes 44-52) — `kind` ∈ `{exercise_not_found, cross_tenant, invalid_answers, invalid_exercise, storage_failure}`. **s07 ajoute des kinds** : `verdict_missing`, `llm_failure`, `answer_too_long`, `invalid_exercise_type`.
  - `GradingResult` (lignes 61-69) — `is_success, correct_count, total, feedback, attempt_id, attempt_number`. **s07 simplifie** : pas de `correct_count`/`total` (appréciation binaire, qualitative), on garde `is_success, feedback, attempt_id, attempt_number`. Cf. § 6 décision D3.
  - Multi-tenant check ligne 171 : `if exercise.student_pseudo != pseudo` → `cross_tenant` (même message que `not_found`, pas de leak). **s07 reproduit le même pattern**.
  - `_next_attempt_number` (lignes 259-281) : `SELECT MAX(attempt_number) ... WHERE exercise_id = ? AND student_pseudo = ?`. **Réutilisable tel quel**.
  - `_SessionLike` Protocol (lignes 113-120) : `get, add, commit, rollback, query`. **Réutilisé tel quel**.
  - Pydantic re-validation des questions (lignes 186-192) : `QcmQuestion.model_validate(d)` pour chaque dict. **Adaptable à s07** : re-valider `statement`/`expected_answer`/`grading_criteria` via les schémas s06.

### 2.5. Convention de retry (s03, livré)

- `backend/app/services/exercises/qcm_generator.py:290-314` — boucle `for i in range(max_retries + 1)` : 1ère tentative prompt « soft », retry prompt « strict ». **Pattern à dupliquer** pour s07, adapté : la 1ère tentative autorise la prose autour du verdict, le retry exige **uniquement** la ligne `VERDICT: REUSSITE|ECHEC`.
- `max_retries: int = 1` paramétrable (s07 adopte `text_grader_max_retries`).

### 2.6. CLI typer (s04, livré)

- `backend/app/cli.py:420-432` — `_build_grader_service() -> QcmGrader` : `db_session.init_db()` puis `QcmGrader(session_factory=...)`. **s07 étend** : `_build_text_grader_service() -> TextGrader` ajoute `llm=build_llm_client(settings)`.
- `backend/app/cli.py:469-525` — commande `submit_qcm` complète (parsing JSON, exit codes 0/1/4/5). **s07 duplique la structure** pour `submit_text`. Différences : `--answers` (str JSON) devient `--answer` (str brut, pas de JSON car un seul champ texte).
- Mapping d'exceptions à exit codes documenté `cli.py:13-20` (0/1/2/3/4/5) + `cli.py:331-338`. **s07 étend** : `verdict_missing` après retry → 4, `llm_failure` → 4, `answer_too_long` → 2, `invalid_exercise_type` → 4.
- Lignes 36-43 : réconfiguration UTF-8 de stdout/stderr (depuis s04). **Préservée**.

### 2.7. Conventions de test (s03 + s04, livrés)

- `backend/tests/services/exercises/test_qcm_generator.py:47-91` — `_ScriptedLlm` (drop-in `LlmClient`, pop la prochaine réponse) et `_TrackingSession` (wrappe SQLAlchemy, observe `session.add`). **Pattern à dupliquer** pour s07. Alternative simple : `FakeListChatModel` de LangChain (cf. `test_client.py:66-74`).
- `backend/tests/services/exercises/test_qcm_generator.py:172-211` — fixtures `memory_db` (SQLite in-memory + `Base.metadata.create_all`) et `_SessionFactory`. **Réutilisables tels quels**.
- `backend/tests/services/exercises/test_qcm_grader.py:40-90` — `_TrackingSession` et `_SessionFactory` spécifiques au grader. **Pattern à dupliquer**.
- `backend/tests/cli/test_cli.py:598-811` — `_StubQcmGrader` + `stubbed_qcm_grader` (monkeypatch de `_build_grader_service`) + 9 tests `TestSubmitQcm`. **Pattern à dupliquer** pour `submit_text` : `_StubTextGrader` + `stubbed_text_grader_service` + `TestSubmitText` (6-7 tests).
- `backend/tests/core/test_models.py:175-276` — `TestAttemptModel` (3 tests). **Pas d'extension nécessaire** : `answer_text` est déjà testé comme nullable (ligne 208).

### 2.8. Settings (s03, livré)

- `backend/app/core/config.py:66-70` — bloc `QCM_*` (4 variables). **Pattern à étendre** avec un bloc `TEXT_GRADER_*` (3-4 variables : `text_grader_max_retries`, `text_grader_temperature`, `text_grader_max_answer_chars`).
- `backend/.env.example` fin de fichier (lignes 65-72) — 4 vars QCM commentées. **À étendre** avec les vars `TEXT_GRADER_*`.

### 2.9. Architecture cible

- `docs/architecture.md:188-205` — schéma `exercises` : `statement TEXT`, `expected_answer TEXT`, `grading_criteria JSON`. s06 doit confirmer que ces champs sont remplis pour `probleme`/`redaction`. **Sans cette confirmation, s07 ne peut pas grader** (cf. § 3).
- `docs/architecture.md:207-217` — schéma `attempts` : `answer_text TEXT` (nullable, s07 le remplit), `correction_level` (nullable, s08 le remplira). Cohérent.

### 2.10. Pièges d'anti-régression connus (s04 review)

- **s04 review** (`docs/reviews/s04-repondre-qcm.md:67-69`) : trois bites testées (all-or-nothing, MAX counter, cross-tenant). s07 fait l'équivalent pour ses invariants.
- **s04 review finding minor #1** (ligne 95) : `from sqlalchemy import func` en lazy import. **Convention suggérée** : importer en haut de fichier. s07 doit éviter le piège.
- **s04 review finding minor #3** (ligne 98) : `except Exception` large dans le CLI. **Pas nouveau**, accepté par s04. s07 reproduit le pattern par cohérence.

## 3. Dépendances amont

s07 dépend de la livraison de s06. Voici l'état connu et les **gaps** que s07 doit anticiper.

| Story | Livrable | Statut | Risque pour s07 |
|---|---|---|---|
| s01 | `ChromaStore`, `Retriever`, `Document` model, ADR 004 | Livré (PRs mergées) | OK |
| s02 | `LlmClient` Protocol, `build_llm_client` | Livré | OK |
| s03 | `Exercise` model polymorphique, `ExerciseType` enum, `QcmGenerator` pattern de retry/persistence | Livré | OK |
| s04 | `QcmGrader`, `Attempt` model (avec `answer_text` et `correction_level` nullable), pattern multi-tenant, exit codes CLI | Livré | OK — `answer_text` est en place |
| s06 | `FreeGenerator` qui persiste `Exercise` avec `type=probleme|redaction`, `statement`, `expected_answer`, `grading_criteria` non-NULL | **Recherche en parallèle, non livré** | **Bloquant** (cf. détail ci-dessous) |
| s08 | `ProgressiveCorrection` | À venir (s07 + s08 = progressif) | Hors-scope pour s07 (s07 grade binaire, s08 orchestre la progressivité) |

### Détail du blocage s06

s07 lit `Exercise.statement`, `Exercise.expected_answer`, `Exercise.grading_criteria` pour construire le prompt de grading. **Si s06 n'est pas livré et mergé** :

- L'`Exercise` row n'existe pas en base (pas de `probleme` ou `redaction`).
- Le grader ne peut pas être testé end-to-end.
- Le CLI `submit-text --exercise-id <id>` ne peut pas invoquer un exercise réel.

**Mitigation dans la recherche s07** : le plan s07 doit documenter cette dépendance en tête de fichier, lister les **champs s07 suppose exister** (cf. ci-dessous), et prévoir une **dépendance de merge** : s07 ne peut être reviewé sérieusement qu'après merge de s06. **Le plan s07 doit inclure une vérification pré-merge** : `git log main --grep s06-generer-probleme-redaction` doit retourner un commit. Si absent, le plan s07 ne peut pas être validé.

### Champs s07 suppose exister (et qui sont dans la zone s06)

D'après la recherche s06 (`docs/research/s06-generer-probleme-redaction.md`) :

- `Exercise.type` ∈ `{ExerciseType.PROBLEME, ExerciseType.REDACTION}` (s06 étend l'enum).
- `Exercise.statement: str` non-NULL.
- `Exercise.expected_answer: str` non-NULL, substantiel (>= 50 chars pour `probleme`, >= 200 pour `redaction`, d'après s06 § 4.5).
- `Exercise.grading_criteria: list[str]` non-NULL (1-10 critères).

**Si s06 livre un `expected_answer` trop mince** (« 42 »), le prompt s07 est inutile : la comparaison LLM n'a pas d'ancrage. Le plan s07 doit documenter ce risque.

### Champs **non** supposés par s07 (et livrés plus tard)

- `Exercise.correction_level` : reste NULL (s08).
- `Attempt.correction_level` : reste NULL (s08).
- `RewardLedger`, `UserPoints` : hors-scope (s20).

## 4. Contraintes techniques

### 4.1. LLM-as-judge est **NON-DÉTERMINISTE**

C'est l'invariant central de la story. **La story le dit explicitement** (`docs/stories.md:288` : « LLM-as-judge is NON-DETERMINISTIC. Tests use a stub. The integration test with the real LLM is best-effort »). Conséquences :

- Tous les tests unitaires utilisent un LLM stub (`FakeListChatModel` ou `_ScriptedLlm`).
- Un test d'intégration avec un vrai LLM est best-effort, **non bloquant** pour le ship.
- La sortie du LLM doit être **parsée strict** (regex `VERDICT:\s*(REUSSITE|ECHEC)`) — toute réponse sans cette ligne est un échec, jamais une réussite.

### 4.2. Parsing strict du verdict (regex `VERDICT:`)

- Regex canonique : `re.compile(r"VERDICT:\s*(REUSSITE|ECHEC)", re.IGNORECASE)` (la story autorise casse mixte).
- Le parsing est appliqué sur **toute la sortie** du LLM, pas seulement la dernière ligne. Tolère la prose autour (1ère tentative) ou l'exige absente (retry strict).
- Si le regex matche, le verdict est extrait et le **reste de la sortie** (texte avant la ligne `VERDICT:`, nettoyé) est le feedback.
- Si le regex ne matche pas, l'attempt passe en retry, puis en échec dur (`TextGradingError("verdict_missing", ...)`).

### 4.3. Retry : « once with a stricter prompt, then fail »

- Pattern s03 (lignes 290-314) : `for i in range(max_retries + 1)`. 1ère itération = prompt « soft » (autorise prose autour du verdict). 2ème itération = prompt « strict » (exige **uniquement** la ligne `VERDICT: ...`).
- Le retry **doit changer le prompt**, pas seulement relancer. Sinon 0 chance d'obtenir un format différent.
- `max_retries=1` par défaut (cohérent avec `qcm_max_retries`, `config.py:69`). Configurable via `TEXT_GRADER_MAX_RETRIES`.

### 4.4. Multi-tenancy

- L'invariant `Exercise.student_pseudo == pseudo` est vérifié **après** `session.get(Exercise, ...)`, **avant** toute logique de grading. **Identique à s04** (`qcm_grader.py:171-175`).
- L'`Attempt` row persistée a `student_pseudo == pseudo` (filtré par le grader, jamais issu du body).
- `attempt_number` est par `(pseudo, exercise_id)` via `MAX(attempt_number)`. **Réutilisation directe** de `qcm_grader.py:259-281`.
- Erreur : `TextGradingError("cross_tenant", ...)` avec le **même message** que `exercise_not_found` (pas de leak).

### 4.5. Extension du modèle `Attempt`

- **Aucune migration nécessaire** : `answer_text: Mapped[str | None]` est déjà en place (`models.py:182`).
- Le grader s07 écrit `Attempt.answer_text = <réponse de l'élève>`. Pour les QCM, ce champ reste NULL.
- `raw_answers: list[int]` reste `[]` pour les attempts texte (`Mapped[list[int]]` non-NULL → on stocke `[]`).
- `is_success: bool` calculé par le LLM (verdict → bool).

### 4.6. Troncature de la réponse de l'élève

- Limite : `String(8192)` (modèle) et `TEXT_GRADER_MAX_ANSWER_CHARS` (config, défaut 8000 caractères). Au-delà, `TextGradingError("answer_too_long", ...)` **avant** tout appel LLM.
- **Ne pas tronquer silencieusement** : la story le dit explicitement (`docs/stories.md:293` : « truncate with a warning if it does, but do not silently lose content »). On refuse et on explique. Cf. § 6 décision D4.
- L'option « warn but truncate » (log + continuer avec réponse tronquée) est documentée comme option B. **L'option A (refuse + erreur)** est la plus sûre pour le POC.

### 4.7. Prompt LLM

Le prompt doit contenir **uniquement** : (1) le `statement`, (2) l'`expected_answer`, (3) les `grading_criteria`, (4) la réponse de l'élève. Et se terminer par l'instruction explicite :

```text
Termine ta réponse par EXACTEMENT une ligne au format :
  VERDICT: REUSSITE
ou
  VERDICT: ECHEC
```

**Le prompt doit explicitement** :

- Interdire la prose autour du verdict (le retry strict le ré-impératif).
- Demander un feedback d'**une phrase** avant la ligne `VERDICT:`.
- Demander une **comparaison stricte** : « ne dis pas REUSSITE si la réponse est manifestement fausse ou hors sujet ».
- Imposer le français (le LLM peut traduire en anglais par mimétisme, cf. § 5 piège 5).

### 4.8. Feedback retourné

- Le feedback est **le texte avant la ligne `VERDICT:`** (nettoyé des espaces et de la ponctuation finale).
- En cas de retry strict, le LLM produit moins de prose, le feedback peut être plus court (acceptable).
- En cas d'échec dur (`verdict_missing` après retry), le feedback retourné à l'élève est un message générique : « L'appréciation automatique n'a pas pu être produite. Veuillez réessayer. »

## 5. Pièges identifiés

### Piège 1 — Le LLM produit de la prose sans ligne `VERDICT:`

**Description** : un LLM de mauvaise volonté retourne un paragraphe entier d'appréciation qualitative mais oublie la ligne `VERDICT: ...`. Le grader ne peut pas trancher.

**Mitigation** :

- Le prompt soft **impose** la ligne `VERDICT: ...` (cf. § 4.7).
- Le retry strict la ré-impose en majuscules.
- Le regex est appliqué sur **toute la sortie** (pas seulement la dernière ligne) pour tolérer la prose qui précède.
- Le test bite AC6 (no verdict → retry → fail) couvre exactement ce cas.

### Piège 2 — Le LLM « hallucine » une réussite pour une réponse manifestement fausse

**Description** : le LLM est par défaut « gentil » et a tendance à valider des réponses incomplètes. Si la réponse de l'élève est hors sujet, le LLM peut quand même sortir `VERDICT: REUSSITE`.

**Mitigation** :

- Le prompt doit contenir une **clause explicite** : « Sois STRICT : ne donne REUSSITE que si la réponse couvre les critères principaux. Si la réponse est hors sujet, incomplète, ou ne démontre pas la compréhension attendue, donne ECHEC. »
- Les `grading_criteria` (issus de s06) servent d'**ancrage objectif** : le LLM doit évaluer chaque critère.
- Le **bite test** : mocker un LLM scripted qui répond `VERDICT: REUSSITE` à une mauvaise réponse, et vérifier que le grader **accepte** ce verdict (le LLM-as-judge est non-déterministe, on ne peut pas tester « l'hallucination » directement). Le test vérifie au moins que le grader n'a pas de logique de veto post-LLM.
- **Action pour le plan** : ajouter un test qui passe un LLM scripted « politiquement incorrect » (qui valide tout) et vérifie que le grader suit le LLM (pas de double-check arbitraire). C'est un test **d'anti-régression** : si quelqu'un ajoute un post-traitement qui rejette les verdicts LLM, le test rouge.

### Piège 3 — Réponse trop longue qui dépasse le contexte LLM

**Description** : un élève qui colle un roman comme réponse sature le contexte. Le LLM peut crasher (token limit exceeded) ou produire une sortie tronquée et vide.

**Mitigation** :

- Validation côté grader : `len(answer_text) > TEXT_GRADER_MAX_ANSWER_CHARS` (défaut 8000) → `TextGradingError("answer_too_long")` **avant** tout appel LLM.
- Le LLM lui-même reçoit un prompt déjà borné (statement + expected_answer + grading_criteria + answer tronquée = raisonnable pour `minimax-m3` qui accepte 8K-32K tokens selon le provider).
- **Le test bite** : passer une réponse de 9000 caractères → `TextGradingError("answer_too_long")` **et** le LLM n'est pas appelé (`llm.calls == []`).

### Piège 4 — Le retry relance le même prompt

**Description** : un bug classique est de réinvoquer le LLM avec le même prompt en cas d'échec de parsing. Si le LLM vient de prouver qu'il ne produit pas le format, le relancer avec le même prompt a 0 chance de succès.

**Mitigation** :

- Le prompt **doit** être différent entre la 1ère tentative et le retry.
- Le test bite AC6 vérifie exactement ça : le 2ème appel LLM a un prompt différent du 1er (par introspection sur `_ScriptedLlm.calls[N].messages`).
- **Action pour le plan** : coder deux templates : `_USER_PROMPT_TEMPLATE` (soft) et `_STRICT_USER_PROMPT_TEMPLATE` (strict). Le retry utilise le strict.

### Piège 5 — Le verdict est en anglais (`VERDICT: SUCCESS`)

**Description** : un LLM peut traduire le verdict en anglais par mimétisme avec ses données d'entraînement. Le regex `(REUSSITE|ECHEC)` ne matche pas.

**Mitigation** :

- Le prompt **impose explicitement** la sortie en français : « Réponds en français, avec VERDICT: REUSSITE ou VERDICT: ECHEC. Pas de traduction en anglais. »
- Le retry strict ré-impératif.
- Le regex est insensible à la casse (`re.IGNORECASE`) mais strict sur les tokens `REUSSITE`/`ECHEC`. Une traduction anglaise (`SUCCESS`/`FAIL`) ne matche pas et tombe en retry. Si le LLM persiste en anglais, c'est un échec dur.

### Piège 6 — Cross-tenant non détecté parce que le grader est « gentil »

**Description** : un élève devine un UUID d'exercise de pseudo_b. Le grader charge l'`Exercise`, voit que `student_pseudo != pseudo`, lève `cross_tenant`. **Mais** : si l'`Attempt` est persistée avec `student_pseudo=pseudo` (l'élève), le compteur `MAX(attempt_number)` ne capture que les attempts de `pseudo_a`, pas celles de `pseudo_b`. C'est OK. **Le piège** est ailleurs : si quelqu'un retire le check `student_pseudo != pseudo`, l'élève peut soumettre à un exercise d'un autre, et le test bite cross-tenant ne mord plus.

**Mitigation** :

- Réutiliser **mot pour mot** le check `qcm_grader.py:171-175`.
- Le test bite AC7 vérifie : (a) `TextGradingError("cross_tenant")`, (b) **aucun `Attempt` ajouté** à la session (`assert added == []`).

### Piège 7 — Le LLM renvoie un JSON au lieu d'une ligne `VERDICT:`

**Description** : un LLM qui a vu des exemples JSON-mode peut produire `{"verdict": "REUSSITE", "feedback": "..."}`. Le regex ne matche pas.

**Mitigation** :

- Le prompt **interdit** explicitement le JSON : « Réponds en texte libre, PAS en JSON. Termine par une ligne VERDICT: REUSSITE ou VERDICT: ECHEC. »
- Le retry strict ré-impératif.
- **Note** : la story n'exige PAS de JSON (contrairement à s03 QCM). On reste sur parsing regex pour rester cohérent avec le profil « LLM-as-judge » (le LLM est un évaluateur, pas un générateur de données structurées).

## 6. Décisions d'architecture à prendre

Les décisions **D1-D6** doivent être tranchées au planning. L'option recommandée est marquée **(R)**.

### D1 — Modèle Pydantic de l'`Attempt` (R : étendre le `Attempt` existant)

**Question** : faut-il un nouveau modèle `TextAttempt` ou réutiliser `Attempt` avec `answer_text` rempli ?

**Options** :

- **D1.a (R)** : `Attempt` partagé. QCM laisse `answer_text=NULL` et `raw_answers=[...]`. Texte laisse `raw_answers=[]` et `answer_text="..."`. Cohérent avec le design s04 (commentaire `models.py:152-155`).
- **D1.b** : nouveau modèle `TextAttempt` séparé. Plus pur conceptuellement, mais duplique `attempt_number`/`is_success`/`submitted_at` et complique les jointures futures (s08 doit lire les deux).

**Recommandation D1.a** : déjà câblé par s04, aucune migration, le commentaire est explicite.

### D2 — Validation du type d'`Exercise` (R : `type ∈ {PROBLEME, REDACTION}`)

**Question** : faut-il refuser un `submit-text` sur un `Exercise` de type QCM ?

**Options** :

- **D2.a (R)** : `if exercise.type not in {ExerciseType.PROBLEME, ExerciseType.REDACTION}: raise TextGradingError("invalid_exercise_type")`. Le message est clair.
- **D2.b** : accepter n'importe quel type et grader quand même. Le LLM se débrouille (peut produire des absurdités sur un QCM).

**Recommandation D2.a** : cohérence avec la séparation QCM/text. Le CLI `submit-qcm` et `submit-text` sont des frontières sémantiques.

### D3 — Forme du `TextGradingResult` (R : `{is_success, feedback, attempt_number, attempt_id}`)

**Question** : que retourne le grader ?

**Options** :

- **D3.a (R)** : `is_success: bool, feedback: str, attempt_id: UUID, attempt_number: int`. Aligné sur l'AC1 (`{is_success, feedback, attempt_number}`) + `attempt_id` pour traçabilité.
- **D3.b** : `is_success, feedback, raw_verdict, attempt_id, attempt_number`. Inclut la sortie brute du LLM pour debug.

**Recommandation D3.a** : minimal, aligné sur l'AC1. Le `raw_verdict` est loggué (loguru) mais pas retourné à l'élève (réduction du bruit).

### D4 — Politique de troncature (R : refuser)

**Question** : que faire si la réponse dépasse `TEXT_GRADER_MAX_ANSWER_CHARS` ?

**Options** :

- **D4.a (R)** : `TextGradingError("answer_too_long", ...)` retournée au CLI, exit 2. Pas d'appel LLM.
- **D4.b** : tronquer silencieusement + log `warning.answer_truncated` + continuer.
- **D4.c** : tronquer + ajouter un suffixe `... [tronqué]` visible dans le prompt LLM.

**Recommandation D4.a** : la story le dit (« truncate with a warning if it does, but do not silently lose content »). D4.a est l'interprétation stricte : on **ne perd pas** le contenu (on dit à l'élève que c'est trop long), et on n'appelle pas le LLM. D4.b est risqué (l'élève ne sait pas que sa fin a été coupée). D4.c est un compromis, mais ajoute de la complexité sans gain clair.

### D5 — Format du feedback retourné à l'élève (R : phrase unique extraite avant `VERDICT:`)

**Question** : comment extraire le feedback de la sortie LLM ?

**Options** :

- **D5.a (R)** : prendre tout le texte **avant** la ligne `VERDICT:`, nettoyer les espaces, retourner comme feedback. Tolère plusieurs phrases si le LLM bavarde.
- **D5.b** : forcer le LLM à produire un JSON `{"feedback": "...", "verdict": "..."}` et parser. Plus structuré, mais plus de risque d'échec de parsing (cf. piège 7).
- **D5.c** : prendre uniquement la dernière phrase avant `VERDICT:` (regex findall des phrases terminées par `.`/`!`/`?`).

**Recommandation D5.a** : simple, tolérant, aligné sur l'AC2 (« one-sentence feedback » mais l'AC tolère la prose autour tant que le verdict est identifiable).

### D6 — Comportement si le LLM produit un verdict incohérent avec son feedback (R : accepter)

**Question** : si le LLM dit « Bonne réponse mais VERDICT: ECHEC » (incohérence), que faire ?

**Options** :

- **D6.a (R)** : faire confiance au verdict structuré (regex). C'est ce que le LLM a explicitement tranché.
- **D6.b** : ajouter un second passage LLM pour vérifier la cohérence. Coûteux, lent, et le LLM peut être encore plus incohérent.
- **D6.c** : post-traiter le feedback pour le rendre cohérent (ex. préfixer « [échec] »). Cosmetic, ajoute de la complexité.

**Recommandation D6.a** : la sortie LLM est ce qu'elle est. Le feedback est informatif, le verdict est décisionnel. Le LLM-as-judge est un oracle, pas un comité de lecture.

### D7 — Vérification pré-merge de s06 (R : gate du plan)

**Question** : comment garantir que s06 est mergé avant que s07 ne soit review sérieusement ?

**Recommandation (R : gate bloquant)** : le plan s07 doit inclure une **étape 0** : `git fetch origin && git log origin/main --oneline | grep -i s06-generer-probleme-redaction`. Si le commit n'est pas trouvé, le plan s07 est **invalidé** et doit attendre. Le reviewer doit vérifier ce gate.

## 7. Fichiers anticipés

| Fichier | Action | Rôle | Bloquant pour ship ? |
|---|---|---|---|
| `backend/app/services/exercises/text_grader.py` | **Créer** | `TextGrader` class + Pydantic + prompts + regex parsing. | Oui |
| `backend/app/core/config.py` | **Étendre** | Bloc `TEXT_GRADER_*` (3-4 settings) après le bloc `QCM_*` (ligne 70). | Oui |
| `backend/.env.example` | **Étendre** | 3-4 vars `TEXT_GRADER_*` après le bloc QCM. | Oui |
| `backend/app/cli.py` | **Étendre** | `_build_text_grader_service()` + commande `submit_text` + helpers d'affichage. | Oui |
| `backend/app/core/database/models.py` | **Pas de modif** | `Attempt.answer_text` déjà en place. | Non |
| `backend/tests/services/exercises/test_text_grader.py` | **Créer** | 8-10 tests (cf. § 8). | Oui |
| `backend/tests/cli/test_cli.py` | **Étendre** | `_StubTextGrader` + `stubbed_text_grader_service` + `TestSubmitText` (5-6 tests). | Oui |
| `backend/tests/core/test_config.py` | **Étendre** | `TestTextGraderSettings::test_default_text_grader_settings`. | Oui |
| `docs/architecture.md` | **Pas de modif** | Le schéma `attempts` est déjà documenté. | Non |
| `docs/research/s07-repondre-texte-libre.md` | **Créer** (présent doc) | Ce document. | Non |

### 7.1. Risques de merge avec s06 et s08

- **Avec s06** : s07 lit `Exercise.statement`/`expected_answer`/`grading_criteria` et `ExerciseType.PROBLEME`/`REDACTION`. **Si s06 merge en premier**, s07 fonctionne. **Si s07 merge en premier**, l'enum `ExerciseType` ne contient pas encore `PROBLEME`/`REDACTION` → `D2.a` lève `invalid_exercise_type` sur tout. **Gating** : s07 ne peut pas être mergé avant s06 (cf. D7).
- **Avec s08** : s08 (correction progressive) lit `Attempt.answer_text` et écrit `Attempt.correction_level`. **Pas de conflit de merge** sur les modèles : les colonnes sont déjà là. s08 peut être développé en parallèle, mais ne doit pas être mergé avant s07 (sinon le test d'intégration `s08 → s07` n'a pas de données).

## 8. Tests à prévoir

Un test par AC + bites d'anti-régression. Tous les tests utilisent `_ScriptedLlm` (ou `FakeListChatModel`) et `_TrackingSession`.

### 8.1. Tests `tests/services/exercises/test_text_grader.py`

| Test | AC couvert | Piège couvert |
|---|---|---|
| `TestSchema::test_text_submission_rejects_empty_answer` | AC1 | — |
| `TestSchema::test_text_submission_rejects_too_long_answer` | AC1 | Piège 3 |
| `TestGrade::test_verdict_reussite_returns_is_success_true` | AC1, AC2, AC5 | — |
| `TestGrade::test_verdict_echec_returns_is_success_false` | AC1, AC2 | — |
| `TestGrade::test_feedback_extracted_before_verdict_line` | AC1, AC2 | — |
| `TestGrade::test_no_verdict_retries_then_fails` | AC3, AC6 | Piège 1, Piège 4 |
| `TestGrade::test_strict_prompt_used_on_retry` | AC3, AC6 | Piège 4 (bite) |
| `TestGrade::test_llm_anglais_verdict_does_not_match` | AC3 | Piège 5 |
| `TestGrade::test_attempt_persisted_with_answer_text` | AC4 | — |
| `TestGrade::test_attempt_raw_answers_is_empty_list` | AC4 | — |
| `TestAttemptNumber::test_attempt_number_increments_across_submissions` | AC4 | — |
| `TestAttemptNumber::test_attempt_number_is_per_pseudo` | AC4 | — |
| `TestCrossTenant::test_cross_tenant_raises_text_grading_error` | AC7 | Piège 6 (bite) |
| `TestCrossTenant::test_cross_tenant_does_not_persist_attempt` | AC7 | Piège 6 (bite) |
| `TestInvalidExercise::test_qcm_exercise_raises_invalid_exercise_type` | — | Décision D2.a |
| `TestInvalidExercise::test_missing_statement_raises_grading_error` | — | Defense-in-depth (réutilise le pattern s04) |

### 8.2. Tests `tests/cli/test_cli.py::TestSubmitText`

| Test | AC couvert |
|---|---|
| `test_submit_text_returns_zero_with_success` | AC1, AC5 |
| `test_submit_text_json_output_is_valid` | AC1 |
| `test_submit_text_echec_returns_zero_with_is_success_false` | AC1, AC2 |
| `test_submit_text_cross_tenant_returns_5` | AC7 |
| `test_submit_text_verdict_missing_returns_4` | AC3, AC6 |
| `test_submit_text_answer_too_long_returns_2` | Décision D4.a |
| `test_submit_text_exercise_not_found_returns_5` | — |
| `test_submit_text_help_works` | — |
| `test_help_lists_submit_text_command` | — |

### 8.3. Test cross-tenant obligatoire (AC7)

Le test `TestCrossTenant::test_cross_tenant_raises_text_grading_error` + `test_cross_tenant_does_not_persist_attempt` (équivalent de `test_qcm_grader.py:313-330`) est **obligatoire** : il est le seul qui mord si la vérification d'ownership est retirée. La version `does_not_persist_attempt` est plus stricte que la version QCM (qui ne vérifie que l'exception) : elle vérifie aussi qu'aucun `Attempt` n'a été `session.add()`.

### 8.4. Bites d'anti-régression

1. **AC2 (verdict parsing)** : muter le grader pour toujours retourner `is_success=True` → test `test_verdict_echec_returns_is_success_false` rouge.
2. **AC3 (retry pattern)** : muter le grader pour **ne pas** changer de prompt au retry → test `test_strict_prompt_used_on_retry` rouge.
3. **AC4 (multi-tenant)** : retirer `if exercise.student_pseudo != pseudo` → test `test_cross_tenant_raises_text_grading_error` rouge.
4. **AC4 (persistence)** : retirer `session.add(Attempt(...))` → test `test_attempt_persisted_with_answer_text` rouge.
5. **D2.a (type check)** : retirer la validation `type ∈ {PROBLEME, REDACTION}` → test `test_qcm_exercise_raises_invalid_exercise_type` rouge.

### 8.5. Tests d'intégration (non bloquants)

- Un test `@pytest.mark.integration` qui appelle un vrai LLM (configurable via `LLM_PROVIDER=openai` + `OPENAI_API_KEY`) sur un cas évident : `expected_answer="Paris"`, `answer_text="Paris"`, vérifie que `is_success` est `True` la plupart du temps (tolérance flaky).
- Marqué `@pytest.mark.integration` et exclu par `-m "not integration"` (cf. `pytest.ini` / `conftest.py`).
- **Non bloquant** pour le ship, comme indiqué dans la story.

### 8.6. Tests a11y / Lighthouse

Hors-scope pour s07 (story backend pur).

## 9. Risques

### Risque 1 — Complexité 3 assumée

L'AC1 (un seul CLI `submit-text`), l'AC3 (retry pattern), l'AC4 (persistance), l'AC7 (multi-tenant) sont **4 invariants** à protéger en plus du parsing non-déterministe. La surface de test est large (16 tests estimés). Mitigation : bites explicites + 1 test par invariant.

### Risque 2 — Dépendance dure de s06

s07 ne peut pas être mergé avant s06. **C'est un risque de planning**, pas un risque technique. Le plan s07 doit inclure le gate D7 (vérification de merge de s06).

### Risque 3 — Richesse de l'`expected_answer` de s06

s07 suppose qu'`expected_answer` est substantiel (cf. § 4.7 du research s06). Si s06 livre un `expected_answer="42"`, le prompt s07 contient « Compare la réponse à "42" » et le LLM n'a aucun ancrage pour évaluer. Mitigation : le plan s07 doit documenter ce risque dans la PR description. Si s06 livre un `expected_answer` trop mince, s07 ne peut pas être corrigé localement — c'est un défaut de s06.

### Risque 4 — Conflit de merge avec s08

s08 (correction progressive) lit `Attempt.answer_text` et écrit `Attempt.correction_level`. **Pas de conflit de schéma** (colonnes déjà là). **Pas de conflit de code** (s08 a son propre module `services/correction/progressive.py`). Mais s08 dépend de s07 : si s08 merge en premier, ses tests d'intégration n'ont pas de données. Mitigation : ordre de merge `s06 → s07 → s08` (cohérent avec le pipeline).

### Risque 5 — LLM-as-judge non-déterministe en production

En production, le même élève soumettant deux fois la même réponse peut obtenir deux verdicts différents. C'est **inhérent au LLM-as-judge** et **accepté** par la story (« Tests use a stub. The integration test with the real LLM is best-effort »). Pas de mitigation. À documenter dans la PR description.

### Risque 6 — Latence (non bloquant)

Un grading LLM prend 2-5 secondes. Pour un MVP acceptable. L'observabilité (s23) pourra mesurer.

## 10. Definition of Done (spécialisé pour s07)

- [ ] **Gate D7** : `git log origin/main --oneline | grep -i s06-generer-probleme-redaction` retourne au moins un commit. Le plan s07 ne peut pas être validé avant ce gate.
- [ ] Toutes les tâches du plan cochées.
- [ ] `pytest --cov=app --cov-fail-under=80 -m "not integration"` passe (≥ 80% de couverture, cible 200+ tests après ajout d'~16).
- [ ] `ruff check app tests` passe (0 erreur).
- [ ] AC1-AC7 tous couverts par des tests unitaires ET des tests CLI.
- [ ] **Multi-tenancy** : un test vérifie qu'un `pseudo_b` ne peut pas soumettre à un exercise de `pseudo_a` (test `test_cross_tenant_does_not_persist_attempt`).
- [ ] **Test bite sur le verdict** : un test vérifie qu'un verdict `REUSSITE` retourne `is_success=True` et un verdict `ECHEC` retourne `is_success=False`.
- [ ] **Test bite sur le retry** : un test vérifie que le 2ème appel LLM utilise un prompt différent du 1er.
- [ ] **Test bite sur la troncature** : un test vérifie qu'une réponse > 8000 chars lève `TextGradingError("answer_too_long")` **avant** tout appel LLM (`llm.calls == []`).
- [ ] **Test bite sur le type d'exercise** : un test vérifie qu'un `Exercise.type=QCM` est rejeté avec `invalid_exercise_type` (décision D2.a).
- [ ] **Tests stub LLM** : 5+ tests avec un LLM scripted (verdict REUSSITE, verdict ECHEC, no verdict, anglais, JSON).
- [ ] **Le text grader appelle le LLM uniquement après validation ownership** : un test vérifie que le LLM n'est pas appelé sur une requête cross-tenant.
- [ ] CLI : exit 0 sur succès, exit 2 sur `answer_too_long`, exit 4 sur `verdict_missing` après retry, exit 5 sur `cross_tenant`/`exercise_not_found`, exit 1 sur autre.
- [ ] **Tentative d'intégration LLM réelle** : un test `@pytest.mark.integration` existe, est lancé manuellement, et documente son taux de réussite (non bloquant).
- [ ] PR unique, description structurée : résumé, AC cochées, points d'attention (notamment la dépendance à s06, la non-déterminisme du LLM-as-judge, l'extension de `Answer` model).
- [ ] `git diff main...feature/s07-repondre-texte-libre` est lisible.
- [ ] Review passée (`docs/reviews/s07-repondre-texte-libre.md` avec `Ship allowed: yes`).

## 11. Sources

### Fichiers lus (chemins absolus)

- `C:\Workspace\ktutor\.worktrees\s07-repondre-texte-libre\docs\stories.md` (l. 262-294 pour s07 ; l. 188-219 pour s06 et ses dépendances).
- `C:\Workspace\ktutor\.worktrees\s07-repondre-texte-libre\docs\architecture.md` (l. 188-205 pour `exercises` ; l. 207-217 pour `attempts` ; l. 152-157 pour multi-tenancy).
- `C:\Workspace\ktutor\.worktrees\s07-repondre-texte-libre\docs\prd.md` (référencé indirectement ; pas de Q ouverte pour s07).
- `C:\Workspace\ktutor\.worktrees\s06-generer-probleme-redaction\docs\research\s06-generer-probleme-redaction.md` (l. 1-500 : pour comprendre le contrat que s06 livre à s07).
- `C:\Workspace\ktutor\.worktrees\s07-repondre-texte-libre\docs\research\s04-repondre-qcm.md` (pattern de recherche réutilisé).
- `C:\Workspace\ktutor\.worktrees\s07-repondre-texte-libre\docs\plans\s04-repondre-qcm.md` (structure de plan à dupliquer).
- `C:\Workspace\ktutor\.worktrees\s07-repondre-texte-libre\docs\reviews\s04-repondre-qcm.md` (l. 67-69 : bites testées ; l. 95-98 : findings minor).
- `C:\Workspace\ktutor\.worktrees\s07-repondre-texte-libre\backend\app\core\database\models.py` (l. 33-40 enum `ExerciseType` ; l. 90-144 modèle `Exercise` ; l. 147-195 modèle `Attempt` avec `answer_text` ligne 182).
- `C:\Workspace\ktutor\.worktrees\s07-repondre-texte-libre\backend\app\services\exercises\qcm_grader.py` (l. 44-105 erreurs/schémas ; l. 123-281 service ; l. 259-281 `MAX(attempt_number)`).
- `C:\Workspace\ktutor\.worktrees\s07-repondre-texte-libre\backend\app\services\exercises\qcm_generator.py` (l. 88-116 `_extract_json_block` non utilisé par s07 ; l. 123-164 prompts soft/strict pattern ; l. 290-314 retry pattern).
- `C:\Workspace\ktutor\.worktrees\s07-repondre-texte-libre\backend\app\services\llm\client.py` (l. 27-34 `LlmClient` Protocol ; l. 51-79 factory).
- `C:\Workspace\ktutor\.worktrees\s07-repondre-texte-libre\backend\app\cli.py` (l. 13-20 exit codes ; l. 36-43 UTF-8 ; l. 420-525 `submit_qcm` complet).
- `C:\Workspace\ktutor\.worktrees\s07-repondre-texte-libre\backend\app\core\config.py` (l. 66-70 bloc `QCM_*` à étendre).
- `C:\Workspace\ktutor\.worktrees\s07-repondre-texte-libre\backend\tests\conftest.py` (fixtures PDF, image, DB).
- `C:\Workspace\ktutor\.worktrees\s07-repondre-texte-libre\backend\tests\services\exercises\test_qcm_generator.py` (l. 47-91 `_ScriptedLlm`/`_TrackingSession` ; l. 172-211 fixtures).
- `C:\Workspace\ktutor\.worktrees\s07-repondre-texte-libre\backend\tests\services\exercises\test_qcm_grader.py` (l. 40-90 doubles ; l. 175-330 tests grade/persistence/attempt/cross-tenant).
- `C:\Workspace\ktutor\.worktrees\s07-repondre-texte-libre\backend\tests\cli\test_cli.py` (l. 598-811 `submit-qcm` tests).
- `C:\Workspace\ktutor\.worktrees\s07-repondre-texte-libre\backend\tests\core\test_models.py` (l. 175-276 `TestAttemptModel`, l. 208 : `answer_text` nullable déjà testé).
- `C:\Workspace\ktutor\.worktrees\s07-repondre-texte-libre\backend\tests\services\llm\test_client.py` (l. 66-74 `FakeListChatModel` pattern pour stub).

### ADRs consultés

- `docs/decisions/001-monorepo-backend-frontend.md` — monorepo (contexte).
- `docs/decisions/003-langgraph-supervisor.md` — superviseur (hors-scope pour s07 backend).
- `docs/decisions/004-rag-isolation-by-collection.md` — multi-tenancy RAG (s07 ne touche pas ChromaDB, mais l'invariant `student_pseudo` est central).
- `docs/decisions/005-auth-rs256-rbac.md` — auth (hors-scope pour s07).
- `docs/decisions/009-seaweedfs-replaces-minio.md` — stockage (hors-scope pour s07).

### CLAUDE.md (extraits pertinents)

- § Stack Technologique — FastAPI + SQLAlchemy + LLM (Minimax-M3 par défaut).
- § Multi-Tenancy — `student_pseudo` partout, multi-tenant invariant central.
- § Correction Progressive — l'algorithme de correction est en s08, **pas en s07**. s07 grade binaire, s08 orchestre la progressivité.
- § Conventions de Code — snake_case fichiers, PascalCase classes, kebab-case URLs, typage obligatoire, Pydantic pour les schémas.
- § Workflows Clés § 2 (Génération et correction progressive d'exercice) — la décision de « réussite = appréciation positive du LLM » est dans la story, pas dans CLAUDE.md.

### Pas d'ADR nouveau requis

Les décisions s'inscrivent dans l'architecture cible existante. Si le plan augmente `TEXT_GRADER_MAX_ANSWER_CHARS` au-delà de 8192 (cf. § 4.6, piège 3), un nouvel ADR « décision de schema » est nécessaire — **recommandation : ne pas agrandir `String(8192)` côté `Attempt.answer_text`**, garder la limite Python à 8000 chars.

### Questions ouvertes levées par cette recherche

Aucune question ouverte attachée à s07. Toutes les décisions sont tranchées par les research/plan ou escaladées au planning utilisateur via D1-D7.

---

## 12. Re-vérification après merges s05, s06 et s06b (2026-09-01)

Cette recherche a été livrée par l'agent parallèle de la vague massive (s05-s08) avant que les stories **s05-agent-francais-chat** (squash c8c9617, PR #6), **s06-generer-probleme-redaction** (squash f928d65, PR #7) et **s06b-generer-flashcards** (squash 394d4d4, PR #8) ne soient mergées sur `main`. Le pipeline me demande de **vérifier l'état actuel du code** avant d'écrire le plan, pas de me fier aux docs.

**État au moment de cette re-vérification** :

- Branche `feature/s07-repondre-texte-libre` : HEAD = `a593fc8` (= main **avant** s05, s06, s06b). Le worktree local n'a pas le code de s05/s06/s06b.
- `main` (remote) : `394d4d4` (= `a593fc8` + s05 + s06 + s06b squashés).
- Le plan s07 doit donc commencer par un **rebase sur `origin/main`** (étape 0 du plan).

**Vérification des éléments cités par la recherche, sur le code LOCAL de la branche s07 (HEAD `a593fc8`)** :

| Élément cité | Localisation | État local | Conformité à la recherche |
|---|---|---|---|
| `ExerciseType` (l. 33-40) | `backend/app/core/database/models.py:33-40` | `QCM = "qcm"` seul | ✓ Valide localement. **Invalide après rebase** : s06 a ajouté `PROBLEME`/`REDACTION`, s06b a ajouté `FLASHCARDS`. 4 valeurs au final. |
| `Attempt.answer_text` (l. 182) | `backend/app/core/database/models.py:182` | `String(8192)` nullable | ✓ Valide localement. **Préservé** après rebase (s06 et s06b n'ont pas touché `Attempt`). |
| `QcmGrader` (l. 123) et `_next_attempt_number` (l. 260) | `backend/app/services/exercises/qcm_grader.py:123, 260` | Pattern stable | ✓ Valide. **Réutilisable tel quel** par s07. |
| `_build_grader_service` (l. 424) | `backend/app/cli.py:424` | Wire-up présent | ✓ Valide. **Pattern à dupliquer** pour `_build_text_grader_service`. |
| `submit_qcm` (l. 471) | `backend/app/cli.py:471` | Commande typer complète | ✓ Valide. **Pattern à dupliquer** pour `submit_text`. |
| `_extract_json_block` (qcm_generator.py:88-116) | `backend/app/services/exercises/qcm_generator.py:91-116` | Privé dans qcm_generator.py | ✓ Valide. **Changement après rebase** : s06 a extrait vers `_parsing.py` (mutualisé). **s07 n'utilise pas ce helper** (parsing regex direct, cf. recherche ligne 507). Pas d'impact. |
| Tests s03 + s04 patterns (727 + lignes) | `backend/tests/...` | `_ScriptedLlm`, `memory_db`, `_TrackingSession` | ✓ Valide. **Réutilisables tels quels**. |
| `docs/reviews/stories.md` verdict | l. 89 | `Stories ready: yes` | ✓ s07 confirmé dans le périmètre. |

**Impact des merges récents sur s07** :

1. **s05 (c8c9617)** : purement additif (nouveaux fichiers `agents/{types,citations,francais_agent,supervisor}.py`). **Aucun impact** sur le code référencé par s07. Conflit de rebase : aucun attendu.

2. **s06 (f928d65)** : modifications significatives à intégrer :
   - `ExerciseType` étendu avec `PROBLEME` et `REDACTION`. **s07 doit adapter D2.a** : la liste des types acceptés est désormais `{PROBLEME, REDACTION}` (les deux types pour lesquels s07 grade), et la liste des types rejetés inclut aussi `FLASHCARDS` (s06b) et `QCM`. **D2.a est confirmée**.
   - `free_generator.py` créé (nouveau service). **Aucun impact** sur s07.
   - `_parsing.py` créé. **s07 n'en a pas besoin** (parsing regex direct, non-structuré).
   - `cli.py` étendu avec `_build_free_service` et `generate_exercise`. **s07 doit juste ajouter `submit_text` à côté de `submit_qcm`**.
   - Tests s04 inchangés. **s07 ajoute ses propres tests à côté**.

3. **s06b (394d4d4)** : extensions supplémentaires à intégrer :
   - `ExerciseType += FLASHCARDS`. **s07 doit adapter D2.a** : `FLASHCARDS` est dans la liste des types rejetés (`invalid_exercise_type`).
   - `flashcard_generator.py` créé. **Aucun impact** sur s07 (s07 grade les exercices `probleme`/`redaction`, pas les flashcards — qui sont des outils d'étude, pas des exercices notés).
   - `cli.py` étendu avec `_build_flashcard_service` et `generate_flashcards`. **Aucun conflit** avec s07.
   - Tests s06b inchangés. **s07 ajoute ses propres tests à côté**.

**D7 (gate bloquant s06) — devenue obsolète** :

La décision D7 recommandait un gate bloquant : « le plan s07 ne peut pas être validé avant que s06 ne soit mergé sur main ». **Ce gate est désormais passé** : s06 a mergé (squash f928d65, PR #7) le 2026-09-01. **D7 est obsolète**, le rebase en étape 0 du plan suffit pour intégrer le code de s06.

**Constatation importante pour D2.a** :

La recherche D2.a dit « type ∈ {PROBLEME, REDACTION} → accepter ; sinon → `invalid_exercise_type` ». **Après merges s06 et s06b**, l'enum contient `QCM`, `PROBLEME`, `REDACTION`, `FLASHCARDS`. La validation devient :

```python
if exercise.type not in {ExerciseType.PROBLEME, ExerciseType.REDACTION}:
    raise TextGradingError("invalid_exercise_type", ...)
```

C'est exactement la même logique que la recherche, mais le bite test doit être étendu pour couvrir **les 4 valeurs** : `QCM` rejeté, `PROBLEME` accepté, `REDACTION` accepté, `FLASHCARDS` rejeté. **Recommandation pour le plan** : le test bite `test_qcm_exercise_raises_invalid_exercise_type` reste (QCM rejeté), et ajouter un test symétrique `test_flashcards_exercise_raises_invalid_exercise_type` (flashcards rejetées, cohérent avec la note du design s06b : « study aid, not an evaluated exercise »).

**Conclusion** : la recherche est **solide** et le plan s07 peut être écrit sans modification des prémisses. **Aucun faux premise trouvé**. Le rebase en étape 0 est la seule action nouvelle par rapport à la recherche initiale (qui supposait un gate D7 séparé).
