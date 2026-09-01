---
name: research-s08-correction-progressive
description: s08-correction-progressive — research output for /ks-plan
metadata:
  type: project
  story: s08-correction-progressive
---

# Research — Story s08-correction-progressive

> **Statut** : phase Research. Cible de la phase Plan (`docs/plans/s08-correction-progressive.md`).
> **Worktree** : `C:\Workspace\ktutor\.worktrees\s08-correction-progressive` (branche `feature/s08-correction-progressive`).
> **Source de vérité** : `CLAUDE.md` § Correction Progressive + `docs/stories.md` s08.

## Les cinq faits structurants

1. **L'algorithme cible est déjà spécifié dans `CLAUDE.md` (l.394-462)** — `ProgressiveCorrection.evaluate(attempt_number, is_success)` avec une seule règle : `is_success` → `full`, `attempt_number >= max_attempts` → `full_after_attempts`, sinon `partial`. La classe `ProgressiveCorrection` du CLAUDE.md est cependant **incomplète** : elle n'a qu'un seul état partiel (`partial`) et ignore le `partial_attempt_2` listé dans le tableau des états (CLAUDE.md l.307) et dans l'AC de la story (l.308 de `docs/stories.md`). **C'est le piège n°1** : l'algorithme de référence ne suffit pas — il faut l'étendre pour avoir DEUX états partiels distincts (`partial` vs `partial_attempt_2`), comme l'exige la story.
2. **L'`is_success` est binaire et externe à s08** — pour le QCM il vient de `QcmGrader.grade` (s04, `backend/app/services/exercises/qcm_grader.py:211`), pour le texte libre il viendra du `TextGrader` que s07 est en train de spécifier (story `s07-repondre-texte-libre`). **s08 ne grade pas** : il consomme un `is_success: bool` (et un `feedback: str`) déjà calculé. Le piège : s08 NE DOIT PAS réintroduire la moindre logique de scoring. Il orchestre un verdict existant et décide quoi dévoiler.
3. **L'`Attempt` est déjà persisté par s04 avec `correction_level: Mapped[str | None]`** — `backend/app/core/database/models.py:183`. Le champ est nullable, jamais écrit par s04 (le QCM grading est binaire et le verdict s'affiche sans niveau de correction). s08 doit y écrire la valeur dérivée du state machine (`"partial"` | `"partial_attempt_2"` | `"full"` | `"full_after_attempts"`). s07 fera la même chose pour ses attempts texte.
4. **`MAX_CORRECTION_ATTEMPTS=3` est documenté dans `CLAUDE.md:609` mais NON câblé** — la variable n'est ni dans `backend/app/core/config.py:10-71` (vérifié), ni dans `.env`. s08 doit l'ajouter à la `Settings` Pydantic avec `default=3`, et propager la valeur au state machine.
5. **Multi-tenancy stricte par `student_pseudo`** — toute tentative de soumission sur un `Exercise.student_pseudo != pseudo` doit lever `cross_tenant` (cohérent avec s04 `qcm_grader.py:171-175`). Le state machine opère APRÈS ce check, sur des données déjà validées comme appartenant à l'élève courant. **Piège n°2** : si la garde multi-tenant est oubliée, un élève A peut « gratter » les hints d'un exercice de l'élève B (les hints LLM-révèlent la solution).

## Cible — Story s08-correction-progressive

**Story** : s08-correction-progressive — Découvrir la correction par étapes (1 à 3 tentatives).
**Complexity** : **4** — state machine sur 4 états × 2 types d'exercice, génération d'indices LLM, couplage avec un verdict externe non-déterministe, fermeture de l'exercice après 3 échecs.

### Acceptance criteria (9 ACs)

> Recopiés depuis `docs/stories.md:305-315` (story s08). Tous les ACs sont à traiter dans le plan.

1. Après un premier échec (QCM ou texte), la réponse contient `correction_level: "partial"`, `hints: [str, str, ...]` (1-3 indices), `next_steps: str`.
2. Après un deuxième échec sur le même exercice, la réponse contient `correction_level: "partial_attempt_2"` avec des indices plus spécifiques (type d'erreur identifié).
3. Après un troisième échec, la réponse contient `correction_level: "full_after_attempts"` avec la solution complète.
4. Si la première tentative réussit, la réponse contient `correction_level: "full"` avec la solution complète + points bonus.
5. La state machine est déterministe : succès à la tentative N (1 ≤ N ≤ 3) → `full` ; échec à la tentative 1 ou 2 → `partial` ; échec à la tentative 3 → `full_after_attempts` (pas de 4e tentative).
6. Un test couvre les 4 états de correction : `partial`, `partial_attempt_2`, `full`, `full_after_attempts`, plus le cas « réussite au premier coup » (5 transitions au total).
7. Un test vérifie que les indices de la tentative 2 sont différents (ou plus riches) que ceux de la tentative 1.
8. Un test vérifie l'isolation multi-tenant.
9. Un test vérifie qu'`attempt_number > 3` sur le même exercice retourne 409 (l'exercice est fermé après `full_after_attempts`).

### Dépendances (story s08)

> Source : `docs/stories.md:318-321` + cross-références.

- **s04** (`feature/s04-repondre-qcm`, shippé) — fournit `QcmGrader` (QCM verdict binaire, `is_success`, `attempt_number`, `Attempt` row). s08 consomme `is_success` + `feedback` + `attempt_number` retournés par s04.
- **s07** (`feature/s07-repondre-texte-libre`, en parallèle) — fournira `TextGrader` (verdict LLM-as-judge pour les exercices libres). s08 consomme le même contrat (`is_success: bool, feedback: str, attempt_number: int`).
- **Pas de dépendance sur s06b** (flashcards) — la story s06b (`docs/stories.md:223-258`) marque explicitement les flashcards comme « NOT graded via the progressive correction flow (s08) — they are a study aid, not an evaluated exercise » (l.252). **s08 NE TRAITE PAS** le type `flashcards`.

### Hypothèse de coordination avec s07

> **Risque ouvert** : la story s07 est en cours de recherche. Le contrat exact de `TextGrader` (nom de classe, fichier, signature de méthode) n'est pas encore figé. s08 doit être **prêt à intégrer** s07 dès que s07 sera livrée, mais NE DOIT PAS dépendre de la signature interne de s07 — uniquement du contrat `is_success: bool, feedback: str, attempt_number: int`. **Cette interface est déjà documentée dans `docs/stories.md:272`** : `submit-text` retourne `{is_success: bool, feedback: string, attempt_number: int}`. Le plan s08 doit tabler là-dessus.

## Code existant à réutiliser

> Chaque référence est citée avec `fichier:ligne` (vérifié par lecture du worktree). Aucune n'est une hypothèse.

### 1. `QcmGrader` (s04, shippé)

- **Fichier** : `backend/app/services/exercises/qcm_grader.py:123-281`.
- **API publique** : `QcmGrader(session_factory=...)` + `grade(pseudo, exercise_id, raw_answers) -> GradingResult`.
- **`GradingResult`** (`:61-69`) : `is_success, correct_count, total, feedback, attempt_id, attempt_number`. C'est le **verdict** que s08 consomme. Le `feedback` est informatif (« Toutes les réponses sont correctes. » / « X/Y réponses correctes. ») — s08 peut le réutiliser tel quel ou l'enrichir (à trancher au plan).
- **`QcmGradingError(kind, message)`** (`:44-53`) : `kind ∈ {"exercise_not_found", "cross_tenant", "invalid_answers", "invalid_exercise", "storage_failure"}`. s08 doit réutiliser ce type d'erreur (même signature) pour les erreurs multi-tenant et exercise-not-found qui précèdent la state machine.
- **Multi-tenant guard** (`:171-175`) : `if exercise.student_pseudo != pseudo: raise QcmGradingError("cross_tenant", ...)`. Le message est identique à `exercise_not_found` pour ne pas leaker. **s08 doit appliquer le même schéma** : avant d'invoquer le state machine, vérifier `Exercise.student_pseudo == pseudo` ; sinon lever la même erreur avec le même message.
- **Re-validation Pydantic des `Exercise.questions`** (`:186-192`) : defense-in-depth via `QcmQuestion.model_validate(d)`. s08 doit **réutiliser cette logique** quand il a besoin de savoir si l'exercice est un QCM bien formé (pour orienter la génération d'indices : « QCM → pointer le concept », « texte → pointer le critère de grading non rempli »).
- **`MAX(attempt_number)`** (`:260-281`) : `SELECT MAX(attempt_number) FROM attempts WHERE exercise_id = ? AND student_pseudo = ?`. s08 doit réutiliser la même requête pour dériver le **nouveau** `attempt_number` de la tentative en cours. **Note** : la s04 a posé ce pattern, le reviewer s04 (`docs/reviews/s04-repondre-qcm.md:67-69`) l'a verrouillé par mutation testing. s08 hérite du filet de sécurité.

### 2. `Attempt` model (s04, shippé)

- **Fichier** : `backend/app/core/database/models.py:147-195`.
- **Champs utilisés par s08** :
  - `id: uuid.UUID` (PK)
  - `exercise_id: uuid.UUID`
  - `student_pseudo: str`
  - `attempt_number: int`
  - `is_success: bool`
  - `answer_text: str | None` — **vide pour QCM** (s07 le remplira pour les exercices texte)
  - `correction_level: str | None` — **s08 écrit ce champ** (cf. AC5)
  - `submitted_at: datetime`
- **`raw_answers: list[int]`** (`:181`) — peuplé par s04, **NULL n'est pas autorisé** (c'est `nullable=False`). **Piège n°3** : s08 doit passer une liste (vide `[]` pour les exercices texte, ou la liste QCM pour les QCM) sinon l'INSERT violera la contrainte NOT NULL. Cohérent avec ce que le reviewer s04 a noté dans `docs/reviews/s04-repondre-qcm.md:96` (« `submitted_at` non directement asserté dans le test de persistance » — s08 doit renforcer cette assertion sur `correction_level`).
- **Le champ `correction_level` est `String(32)`** (`:183`). Les 4 valeurs possibles (`"partial"`, `"partial_attempt_2"`, `"full"`, `"full_after_attempts"`) tiennent largement.

### 3. `Exercise` model (s03, shippé)

- **Fichier** : `backend/app/core/database/models.py:90-144`.
- **Champs utilisés par s08** :
  - `id: uuid.UUID` (PK)
  - `student_pseudo: str` (clé du multi-tenancy)
  - `type: ExerciseType` (QCM | futur : `probleme` | `redaction` | `flashcards`)
  - `statement: str | None` — pour s07/s06 (énoncé d'un problème ou d'une rédaction)
  - `expected_answer: str | None` — pour s07/s06 (solution complète, utilisée par la correction `full` et `full_after_attempts`)
  - `grading_criteria: dict | None` (JSON) — pour s07/s06 (critères de notation LLM, orientent la génération d'indices)
  - `questions: list[dict] | None` (JSON) — pour QCM (utilisé par s04, **s08 le lit** pour contextualiser les hints QCM)
- **Le `ExerciseType` enum** (`:33-38`) n'a pour l'instant que `QCM = "qcm"`. s08 doit tester `exercise.type == ExerciseType.QCM` (pour la branche hints) et supposer `else` → exercice libre (à servir par s07). **Piège n°4** : si s07 ajoute un nouveau type avant que s08 ne soit planifié, le test de la branche `else` doit être paramétrable. Aujourd'hui, le test couvrira « QCM + texte (sera `else` puisque le type n'existe pas encore) ».
- **Aucune méthode `to_solution_dict()` ou `to_hint_context()`** : s08 doit extraire la solution (`expected_answer` pour texte, reconstruction depuis `questions` pour QCM) directement. **À factoriser en helper** dans le module s08.

### 4. `LlmClient` (s02, shippé)

- **Fichier** : `backend/app/services/llm/client.py:27-79`.
- **API** : `LlmClient.invoke(messages: list[BaseMessage]) -> AIMessage` (Protocol runtime-checkable). Utilisable par s08 pour la génération d'indices.
- **Factory** : `build_llm_client(settings)` (`:51-79`). s08 peut la réutiliser pour câbler le hint generator.
- **Test pattern** : `backend/tests/services/agents/test_maths_agent.py` montre comment stubber un `LlmClient` (cf. `_ScriptedLlm` dans `test_qcm_generator.py:47`). s08 réutilisera ce pattern pour tester la génération d'indices sans appeler de vrai LLM.

### 5. Conventions de service (s01-s04)

- **Injection par constructeur** : `Service(llm=..., retriever=..., session_factory=...)`. Cohérent pour `ProgressiveCorrection` et `HintGenerator`.
- **Erreurs typées avec `kind: str`** : `UploadError`, `QcmGenerationError(kind, message)`, `QcmGradingError(kind, message)`. **s08 introduit `ProgressiveCorrectionError(kind, message)`** avec les kinds : `"exercise_not_found"`, `"cross_tenant"`, `"closed"` (tentative > 3), `"invalid_exercise"`, `"storage_failure"`, `"llm_failure"` (la génération d'indices a échoué).
- **Protocol `_SessionLike`** : `qcm_grader.py:113-120` expose le slice de session SQLAlchemy utilisé (add, commit, rollback, get, query). s08 réutilise ce Protocol (ou en étend un similaire).
- **Pattern de test** : `_TrackingSession` (`test_qcm_grader.py:40-70`) + `_SessionFactory` (`:73-89`) + `memory_db` (`:105-117`) + `_seed_exercise` (`:128-163`). Le plan s08 doit réutiliser mot pour mot ces fixtures pour la couche service.

## Dépendances amont

> Toutes les dépendances sont **techniques** (câblage) ou **story** (consommation de contrat).

### Stories

| ID | Statut | Ce que s08 en tire |
|---|---|---|
| **s04** | SHIPPÉ (commit `80c427a`, review `docs/reviews/s04-repondre-qcm.md` `Ship allowed: yes`) | `QcmGrader.grade()` (`:139-253`) — verdict QCM. `QcmGradingError` (`:44-53`). `MAX(attempt_number)` (`:260-281`). `Attempt` model (models.py:147-195). |
| **s07** | En cours de recherche (parallèle à s08) | `TextGrader` (à venir) — verdict LLM-as-judge pour problème/rédaction. Contrat supposé : `{is_success: bool, feedback: str, attempt_number: int}` (cf. `docs/stories.md:272`). s08 NE DOIT PAS attendre que s07 soit planifiée : elle s'interface sur le contrat et un stub pour les tests. |
| **s01-s03** | SHIPPÉ | `ChromaStore`, `Retriever`, `QcmGenerator` (modèle `Exercise` avec `questions` JSON, `expected_answer`/`grading_criteria` pour s06). s08 ne touche à rien de s01-s03. |

### Techniques

- **PostgreSQL / SQLAlchemy 2.0+** : déjà opérationnel, `init_db()` dans `db_session.py` (vérifié — s04 review l'a utilisé 189 tests). s08 ajoute 1 colonne (déjà existante : `correction_level`) et lit `MAX(attempt_number)` via le même pattern s04.
- **LLM provider** : `LlmClient` (s02) — s08 l'utilise pour générer les hints. Stub LLM pour les tests unitaires.
- **`MAX_CORRECTION_ATTEMPTS` env var** : documenté dans `CLAUDE.md:609` mais **NON câblé** dans `backend/app/core/config.py`. s08 doit l'ajouter (`max_correction_attempts: int = 3`) et l'exposer via `get_settings()`. C'est une **tâche d'étape 0** du plan.

## Contraintes techniques

> Issues de `docs/stories.md:305-335` + `CLAUDE.md` § Correction Progressive + conventions du projet.

### Multi-tenancy (AGENTS.md § Multi-tenancy + s04 review)

- **Clé d'isolation** : `student_pseudo` (string), extraite du `pseudo` de l'élève courant. Aucune query SQL/ORM ne doit filter sans ce champ.
- **Vérification systématique** : avant d'invoquer la state machine, `exercise.student_pseudo != pseudo` ⇒ `ProgressiveCorrectionError("cross_tenant", ...)` (même message que `exercise_not_found`, **pas de leak** — pattern s04 `qcm_grader.py:171-175`).
- **Test obligatoire** : un test « pseudo_b ne peut pas soumettre un QCM de pseudo_a » + un test « pseudo_b ne peut pas voir les hints d'un exercice de pseudo_a ». **Piège n°5** : un test séparé sur le state machine n'est pas suffisant — il faut aussi un test sur le service complet qui passe par `session.get(Exercise, ...)` puis vérifie le `student_pseudo`.

### State machine déterministe

> Source : `docs/stories.md:311` (AC5) + `CLAUDE.md:419-445` (algorithme de référence, **à étendre** pour `partial_attempt_2`).

- **4 états** : `"partial"`, `"partial_attempt_2"`, `"full"`, `"full_after_attempts"`. + 1 cas spécial « réussite du premier coup » qui produit aussi `"full"`.
- **Transitions autorisées** (table de vérité) :

  | `attempt_number` (1-based) | `is_success` | `correction_level` | Bonus points |
  |---|---|---|---|
  | 1 | true | `"full"` | 2 |
  | 1 | false | `"partial"` | 0 |
  | 2 | true | `"full"` | 2 (ou 0 ? à trancher) |
  | 2 | false | `"partial_attempt_2"` | 0 |
  | 3 | true | `"full"` | 2 (ou 0 ? à trancher) |
  | 3 | false | `"full_after_attempts"` | 0 |
  | > 3 | n'importe | **fermé (409)** | 0 |

- **Pure function** : la table de vérité doit être implémentée comme une **fonction pure** `next_correction_level(attempt_number, is_success, max_attempts) -> CorrectionLevel` **OU** une `IntEnum`/`Literal` + un mapping dict. **Recommandation** (à valider au plan) : pure function pour testabilité + référence explicite dans la story. La classe `ProgressiveCorrection` du CLAUDE.md (`:395-462`) utilise des `if/elif` — c'est plus difficile à tester exhaustivement.
- **Piège n°6** : si `is_success=True` à la tentative 1, **on ne passe JAMAIS** par un état `partial`. Le test AC6 (5 cas) DOIT inclure explicitement « `is_success=True, attempt=1` → `full` » (pas `partial`, pas `partial_attempt_2`).

### `MAX_CORRECTION_ATTEMPTS` env (default 3)

- **Source** : `CLAUDE.md:609`. Non câblé aujourd'hui dans `config.py:10-71` (vérifié par lecture complète).
- **Action** : ajouter `max_correction_attempts: int = 3` dans `Settings` (`backend/app/core/config.py`), câbler dans `get_settings()`.
- **Effet** : à `attempt_number >= max_correction_attempts` (3), l'échec mène à `"full_after_attempts"`. Une 4e tentative (attempt_number=4) doit lever `"closed"`.

### Fermeture de l'exercice (AC9)

- **Comportement** : après 3 tentatives (toutes échouées), l'exercice est **CLOSED**. Une 4e soumission retourne **409** (équivalent HTTP). En CLI, exit code 6 (nouveau) ou 4 (réutilisé pour « bad input »).
- **Où enforce** ? Deux options :
  1. **CLI uniquement** (cheap, le state machine rejette côté service et le CLI mappe en exit 6).
  2. **Service** (rejette via `ProgressiveCorrectionError("closed")` levée dans la state machine avant tout calcul de hint).
  - **Recommandation** : option 2 (service). Le state machine lève `"closed"` si `attempt_number > max_correction_attempts`. Le CLI et (plus tard) l'API mappent en conséquence. Le test de la state machine couvre cette transition (« attempt=4 + n'importe quel is_success → `closed` »).

### Génération d'indices LLM-spécifiques

> Source : `docs/stories.md:327` (« Hints are LLM-generated, not hard-coded — they must be specific to the student's actual answer and the exercise »).

- **Distinguer QCM et texte** (story traps, l.333) : pour QCM, les hints pointent vers le **concept** (la notion du cours que l'exercice teste) ; pour texte, les hints pointent vers les **critères de grading non remplis** (le `grading_criteria` du `Exercise`).
- **Distinguer tentative 1 et tentative 2** (AC7) : les hints de la tentative 2 doivent être **plus précis** (ou simplement **différents**). Proposition : prompt différent (le prompt v2 inclut l'historique des hints précédents + la nouvelle réponse, et demande au LLM d'identifier le type d'erreur).
- **Stub LLM pour les tests** : `FakeListLLM` de LangChain ou un `_ScriptedLlm` (cf. `test_qcm_generator.py:47`). s08 teste le **contrat** de `HintGenerator.generate_hints(...)` (retourne une liste de 1-3 strings) avec un LLM scripté, pas la qualité du contenu LLM.
- **Piège n°7** : que se passe-t-il si l'appel LLM pour les hints échoue (timeout, JSON mal formé) ? La story ne le dit pas. **Recommandation** : lever `ProgressiveCorrectionError("llm_failure", ...)` et **retourner un fallback** (un hint générique : « Relisez le cours sur ce sujet. ») plutôt que de crasher. **À trancher au plan**.

### Reward ledger (couplage avec s20)

- Source : `docs/stories.md:847` (s20) : « 5 base points + 2 bonus si réussite du premier coup ».
- **s08 NE TOUCHE PAS** au `RewardLedger` (s20 le fera). s08 **calcule** les `bonus_points` (2 si `is_success`, 0 sinon) et les expose dans la `CorrectionResult` (`bonus_points: int`). s20 les consommera.
- **Piège n°8** : ne pas persister de points dans s08. Le state machine et le service retournent un `bonus_points: int` dans le résultat, mais **n'écrivent PAS** dans la table `reward_ledger`. s20 s'en chargera.

### Conformité observabilité (CLAUDE.md § Observabilité)

- **Logs structurés** : `loguru` JSON avec `pseudo`, `exercise_id`, `attempt_number`, `correction_level`, `is_success`, `duration_ms`. Champ `request_id` si l'appel vient de l'API (s09+) — pour la CLI, générer un `request_id` ad hoc.
- **Métriques Prometheus** (counter) : `progressive_correction_total{correction_level="..."}` incrémenté à chaque évaluation. À ajouter dans `app/core/observability/metrics.py` (s23 consolidera).
- **Tracing LLM** : la génération d'indices passe par `LlmClient.invoke` — le wrapper LangChain ajoute déjà les callbacks de tracing. s08 n'a rien à câbler de plus.

### i18n & accessibilité

- **Pas d'impact i18n** : s08 est backend pur, ne touche pas le frontend. Les messages retournés (`hints`, `feedback`, `next_steps`) sont en français (langue de l'élève). L'AC ne mentionne pas d'i18n.
- **Pas d'impact a11y** : s08 ne touche pas l'UI.

## Pièges identifiés (≥ 4 exigés, complexité 4)

> **Piège n°1** (rappel) : l'algo de `CLAUDE.md:395-462` n'a qu'un seul état `partial`. La story exige DEUX états partiels distincts (`partial` et `partial_attempt_2`). Le plan doit étendre l'algo avec une branche `elif attempt_number == 1: "partial"` + `elif attempt_number == 2: "partial_attempt_2"`. Le tableau de l.303-310 confirme.

> **Piège n°2** (rappel) : la state machine **doit recevoir** un `is_success: bool` propre. Si l'orchestrateur calcule lui-même `is_success` (par exemple en re-inférant depuis `correct_count == total` du QCM), il y a duplication de logique et risque de drift. **Solution** : déléguer à `QcmGrader.grade()` (s04) pour le QCM, à `TextGrader.grade()` (s07) pour le texte. Le service s08 NE CONNAÎT PAS le type de grading — il consomme juste le verdict.

> **Piège n°3** (rappel) : `Attempt.raw_answers: Mapped[list[int]]` est `nullable=False` (`models.py:181`). Pour les exercices texte (s07), l'ORM va insérer une liste vide `[]` (Pydantic + `default=[]` au niveau service) ou bien le schéma doit évoluer. **À clarifier avec s07** : si s07 insère avec `raw_answers=None`, s08 doit faire `default=[]` côté service pour rester portable. **Recommandation** : faire comme s04, passer `raw_answers=[]` explicitement quand l'exercice n'est pas un QCM.

> **Piège n°4** (rappel) : le `ExerciseType` enum n'a que `QCM` aujourd'hui (`models.py:33-38`). Le test de la branche `else` (« exercice non-QCM ») doit être paramétrable pour accepter un mock ou un futur `ExerciseType.PROBLEME`. **Solution** : utiliser un mock ou un `Exercise(type=ExerciseType.QCM)` pour le test « texte » en attendant s07, avec un commentaire « sera levé en s07 ».

> **Piège n°5** (rappel) : la **garde multi-tenant** doit précéder la state machine. Le test croisé-temoin (AC8) doit passer par la couche service complète, pas seulement par la state machine. Sinon, un bug dans l'orchestrateur (par ex. oubli du check) passe inaperçu.

> **Piège n°6** (rappel) : `is_success=True` à la tentative 1 doit produire `full`, pas `partial` ni `partial_attempt_2`. C'est explicite dans l'AC5 (« success on attempt N (1 ≤ N ≤ 3) → `full` »). Le test AC6 doit l'assertir explicitement (« first-try success → `full` »), pas seulement « any success → `full` ».

> **Piège n°7** (rappel) : la **génération d'indices LLM est non-déterministe** et peut crasher (timeout, JSON invalide, modèle surchargé). Le service doit **toujours retourner** une `CorrectionResult` avec un `correction_level` (sinon, l'AC1 ne peut pas être testé). **Stratégie** : try/except autour de `llm.invoke(...)`. Si l'appel LLM échoue :
  - Option A : retry une fois avec un prompt plus strict (cohérent avec s03 `qcm_generator.py:284-314`).
  - Option B : fallback déterministe — retourner un hint générique (« Relisez le cours lié à cet exercice et réessayez. ») et logger un `warning` structuré.
  - **Recommandation** : Option A (1 retry) + Option B (fallback générique si retry échoue). Plus robuste, aligné sur les patterns s02/s03.

> **Piège n°8** (rappel) : **concurrence sur `attempt_number`**. Le `MAX(attempt_number)` du s04 (`qcm_grader.py:260-281`) n'est pas transactionnellement safe : deux soumissions parallèles sur le même `(pseudo, exercise_id)` peuvent lire le même `MAX` et insérer deux rows avec le même `attempt_number`. Le test de l'AC5 (plusieurs soumissions) n'est pas concurrent, donc le piège n'est pas visible. **Recommandation** : ajouter une `UNIQUE(exercise_id, student_pseudo, attempt_number)` constraint en Alembic (s15) pour garantir l'invariant. Pour s08, **documenter** la limite (« non thread-safe, ajouter une contrainte en s15 ») et **tester** sérialisé. C'est cohérent avec ce que s04 a fait.

> **Piège n°9** (nouveau) : le **tableau des états de `CLAUDE.md:303-310`** liste CINQ états (`partial`, `partial_attempt_2`, `partial_attempt_3`, `full`, `full_after_attempts`) mais l'AC5 de la story (`docs/stories.md:311`) n'en retient que QUATRE (`partial`, `partial_attempt_2`, `full`, `full_after_attempts`). Le `partial_attempt_3` du tableau CLAUDE.md est en trop. **Action** : ne pas implémenter `partial_attempt_3`. Le `max_attempts=3` rend l'état inutile. **À documenter comme écart de spec** dans la PR (story dit 4 états, CLAUDE.md dit 5 états — la story prime, conformément à AGENTS.md « stories sont la source de vérité du périmètre »).

> **Piège n°10** (nouveau) : `feedback` retourné par le `QcmGrader` (`"X/Y réponses correctes."`) et par le `TextGrader` (à venir) est **informatif**, pas un hint. s08 doit le **conserver tel quel** dans la `CorrectionResult` (le client peut l'afficher à côté des hints) et **ne PAS** le substituer par un hint. C'est implicite dans l'AC1 (« feedback » est listé séparément de `hints`).

> **Piège n°11** (nouveau) : la **fermeture après 3 échecs** doit être testée par les DEUX côtés : (a) la state machine refuse `attempt_number=4` (lève `closed`), (b) le `QcmGrader` (s04) ne devrait même pas être appelé si l'exercice est fermé (le service s08 court-circuite). Le test de l'AC9 vérifie (a) et (b). Sinon, un mock qui court-circuite mal laisse passer une 4e soumission.

## Décisions d'architecture à prendre

> **Statut** : ouvertes au moment de la recherche. **Le plan doit les trancher** (référence au gate `validated: yes`).

### D1. State machine : pure function vs class

- **Option A** : pure function `next_correction_level(attempt_number, is_success, max_attempts) -> CorrectionLevel` (enum ou `Literal["partial", "partial_attempt_2", "full", "full_after_attempts", "closed"]`).
- **Option B** : classe `ProgressiveCorrection` (style CLAUDE.md) avec méthode `evaluate(attempt_number, is_success) -> CorrectionLevel`.
- **Recommandation** : **Option A**. La story demande explicitement un state machine testable (AC6 : 5 tests de transition) ; une pure function se teste trivialement avec `@pytest.mark.parametrize`. La classe est plus « pédagogique » mais ajoute du boilerplate. **À trancher au plan**.

### D2. Hint generation : prompt unique vs prompts par tentative/type

- **Option A** : un seul prompt générique, le LLM s'adapte (peu fiable).
- **Option B** : un prompt par tentative (`hint_prompt_v1` pour `partial`, `hint_prompt_v2` pour `partial_attempt_2`) + un prompt par type d'exercice (QCM vs texte).
- **Recommandation** : **Option B**. Aligné sur le piège n°7 (hints plus précis en v2) et le piège n°4 (QCM vs texte). 4 prompts au total, versionnés explicitement (`HINT_PROMPT_V1_QCM`, `HINT_PROMPT_V2_QCM`, `HINT_PROMPT_V1_TEXT`, `HINT_PROMPT_V2_TEXT`). Le test AC7 vérifie que les deux prompts produisent des outputs **différents** (pas besoin de vérifier la qualité).

### D3. Politique « raté vs réussi après aide »

> Source : PRD `docs/prd.md:86` (« si un élève échoue 3 fois et obtient la correction complète, doit-on considérer l'exercice comme "raté" pour les stats de progression, ou "réussi après aide" ? »).

- **Option A** : `full_after_attempts` est marqué `is_success=False` dans l'`Attempt` (l'élève a quand même échoué 3 fois) et le dashboard l'agrège comme un échec.
- **Option B** : `full_after_attempts` est marqué `is_success=True` (l'élève a obtenu la correction, c'est une forme de réussite).
- **Recommandation** : **Option A** (conserver `is_success=False` pour l'attempt, l'`Exercise` lui-même peut être flagué `completed_via_hints` plus tard). C'est la lecture littérale de l'AC3 (« la solution complète est dévoilée » ne dit pas « l'exercice est réussi »). Le PRD dit explicitement « à trancher en phase Research de STORY-017 » — **cette recherche EST la phase Research de s08**, et la story s08 est l'implémentation directe de la correction progressive. **Le plan doit poser la question au checkpoint** et recommander l'option A par défaut.

### D4. 409 sur 4e tentative : enforcement service vs CLI

- **Option A** : `ProgressiveCorrection.evaluate()` lève `ProgressiveCorrectionError("closed", ...)` si `attempt_number > max_correction_attempts`. Le CLI mappe en exit 6.
- **Option B** : le CLI checke `len(attempts) >= max_correction_attempts` AVANT d'appeler le service.
- **Recommandation** : **Option A**. Le service est la source de vérité, le CLI est un consumer. Pattern s04 (le service lève `cross_tenant`, le CLI mappe en exit 5). Cohérent.

### D5. Stratégie retry + fallback LLM pour hints

- **Option A** : 1 retry avec prompt strict + fallback déterministe.
- **Option B** : pas de retry, fallback déterministe direct.
- **Recommandation** : **Option A**. Cohérent avec s03 (`qcm_generator.py:284-314` : 1 retry avec prompt strict). Le fallback déterministe est un hint générique de 1 phrase.

### D6. Bonus points : 2 si réussite à toute tentative, ou 2 si first-try seulement ?

- **Option A** : 2 points de bonus à toute réussite (story `s20` n'est pas explicite, mais le CLAUDE.md l.427 dit « bonus_points = 2 » sans condition).
- **Option B** : 2 points de bonus seulement au first-try (s20, `docs/stories.md:826` : « 5 base points + 2 bonus si réussite du premier coup »).
- **Recommandation** : **Option B** (lecture stricte de s20). s08 expose `bonus_points: int` dans la `CorrectionResult` (= 2 si `is_success and attempt_number == 1`, = 0 sinon). s20 consomme.

### D7. Emplacement des services

- `backend/app/services/correction/progressive.py` — la state machine + orchestration (création).
- `backend/app/services/correction/hints.py` — la génération d'indices (création).
- `backend/app/services/correction/__init__.py` — barrel (création).
- `backend/app/services/exercises/qcm_grader.py` (s04) — **étendu** pour accepter un callback de progressive correction OU **intact** et s08 wrap l'appel (recommandation : **intact**, s08 est un service distinct qui appelle s04 et applique la state machine). Cf. le piège n°2 (s08 ne grade pas).
- `backend/app/cli.py` — étendu avec une commande `submit-attempt` (unifie QCM + texte, ou garde `submit-qcm` et ajoute `submit-text`). **À trancher au plan** : nouvelle commande unifiée `submit-attempt --type qcm|probleme|redaction` ou bien `submit-qcm` (s04) et `submit-text` (s07) restent séparés et s08 s'insère via une commande `submit` générique ? **Recommandation** : **`submit-qcm` reste tel quel** (s04), **`submit-text` vient de s07**, et **s08 expose `submit-attempt` (unifié)** qui prend `--type` et route vers QCMGrader ou TextGrader. Mais c'est un refactor non-trivial. **Alternative plus simple** : `submit-qcm` et `submit-text` sont étendus chacun à appeler la state machine après grading. **À trancher au plan**.

### D8. Migration Alembic pour `Attempt.correction_level`

- **Option A** : la colonne existe déjà (`models.py:183`), pas de migration nécessaire.
- **Option B** : ajouter une `CheckConstraint` pour limiter `correction_level` aux 4 valeurs + `NULL`.
- **Recommandation** : **Option A** + **CHECK constraint optionnel** (à ajouter en s15, pas en s08). Cohérent avec s04 (pas de migration dans la story, s15 consolide).

## Fichiers anticipés

> Pour chaque fichier : **nouveau** / **étendu** / **refactor**. Les run interdicts sont dans le plan (cf. s04 plan § Run interdicts comme modèle).

### Code (création)

1. **`backend/app/services/correction/__init__.py`** (nouveau, ~10 lignes) — barrel export pour `ProgressiveCorrectionService` et `HintGenerator`.
2. **`backend/app/services/correction/progressive.py`** (nouveau, ~180 lignes) — classe `ProgressiveCorrectionService` + fonction pure `next_correction_level(...)` + dataclasses `CorrectionResult`, `ProgressiveCorrectionError`. Comporte :
   - `next_correction_level(attempt_number, is_success, max_attempts) -> Literal[...]` (D1).
   - `ProgressiveCorrectionService(session_factory, hint_generator, max_attempts)`.
   - `evaluate(pseudo, exercise_id, grade_callback)` — orchestre : fetch exercise, multi-tenant guard, délègue le grading à `grade_callback(exercise, pseudo) -> (is_success, feedback)`, applique la state machine, génère les hints si partial, persiste l'`Attempt` avec `correction_level`, retourne `CorrectionResult`.
3. **`backend/app/services/correction/hints.py`** (nouveau, ~120 lignes) — classe `HintGenerator(llm, max_retries=1)` + dataclass `HintContext` (statement, type, attempt_number, previous_hints, student_answer). Comporte :
   - `_build_prompt(context, version, exercise_type) -> tuple[SystemMessage, HumanMessage]`.
   - `generate_hints(context) -> list[str]` (1 retry + fallback déterministe).

### Code (extension)

4. **`backend/app/core/config.py`** (étendu, +1 champ) — ajouter `max_correction_attempts: int = 3` dans `Settings`.
5. **`backend/app/cli.py`** (étendu, +~50 lignes) — nouvelle commande `submit-attempt` (D7) qui prend `--pseudo`, `--exercise-id`, `--type`, `--answers` (pour QCM) ou `--answer` (pour texte), et route vers `QcmGrader` ou `TextGrader` + `ProgressiveCorrectionService`. Mapping des erreurs en exit codes (5 = cross_tenant, 6 = closed, 4 = invalid_input, 0 = success).
6. **`backend/app/core/database/models.py`** — **NON touché** (le champ `correction_level` existe déjà). Cf. s04 plan l.41-52.
7. **`backend/app/services/exercises/qcm_grader.py`** (s04) — **NON touché** (s08 appelle `grade()` sans le modifier). Run interdict.
8. **`backend/app/services/exercises/qcm_generator.py`** (s03) — **NON touché**.
9. **`backend/app/services/llm/client.py`** (s02) — **NON touché** (s08 utilise `LlmClient` injecté).

### Tests (création)

10. **`backend/tests/services/correction/__init__.py`** (vide).
11. **`backend/tests/services/correction/test_progressive.py`** (nouveau, ~10-12 tests) — couvre la state machine pure (5 transitions + 1 closed + 1 cas limite) + le service complet (multi-tenant, persistance, `correction_level` écrit).
12. **`backend/tests/services/correction/test_hints.py`** (nouveau, ~5-6 tests) — couvre la génération d'indices (stub LLM, retry, fallback, hints v1 ≠ hints v2).
13. **`backend/tests/cli/test_cli.py`** (étendu, +5-6 tests) — `submit-attempt` happy path, cross-tenant, closed (4e tentative), invalid input, JSON output.

### Tests (étendu)

14. **`backend/tests/core/test_config.py`** (étendu, +1 test) — `max_correction_attempts=3` par défaut, surcharge via env.

### Doc

15. **`docs/architecture.md:215-216`** (étendu) — compléter la ligne `correction_level` avec la liste exacte des 4 valeurs + la règle de transition. Note inline : « partial_attempt_3 listed in CLAUDE.md is NOT implemented (3 max attempts) — see story s08 AC5 ».

## Tests à prévoir

> Un par AC + tests d'intégration/combinatoires. **La state machine est load-bearing : tous les chemins DOIVENT être testés** (mutation testing cible).

### State machine — `test_progressive.py::TestNextCorrectionLevel`

Couvre D1 (pure function) avec `@pytest.mark.parametrize` :

| `attempt_number` | `is_success` | `max_attempts` | `correction_level` attendue | Test |
|---|---|---|---|---|
| 1 | True | 3 | `"full"` | AC5, AC6 (first-try success) |
| 1 | False | 3 | `"partial"` | AC1, AC6 |
| 2 | True | 3 | `"full"` | AC5 |
| 2 | False | 3 | `"partial_attempt_2"` | AC2, AC6 |
| 3 | True | 3 | `"full"` | AC5 |
| 3 | False | 3 | `"full_after_attempts"` | AC3, AC6 |
| 4 | True | 3 | `"closed"` (exception `ProgressiveCorrectionError`) | AC9 |
| 4 | False | 3 | `"closed"` (exception `ProgressiveCorrectionError`) | AC9 |

→ 8 transitions, 1 bite (neutraliser la branche `partial_attempt_2` → doit faire passer la transition en `partial`).

### Service complet — `test_progressive.py::TestProgressiveCorrectionService`

| Test | AC couvert |
|---|---|
| `test_service_evaluates_first_attempt_failure_with_partial` | AC1 |
| `test_service_evaluates_second_attempt_failure_with_partial_attempt_2` | AC2 |
| `test_service_evaluates_third_attempt_failure_with_full_after_attempts` | AC3 |
| `test_service_evaluates_first_try_success_with_full` | AC4 |
| `test_service_evaluates_late_success_with_full` (attempt 2 ou 3) | AC5 |
| `test_service_persists_attempt_with_correction_level` | AC5 |
| `test_service_raises_closed_on_attempt_4` | AC9 |
| `test_service_raises_cross_tenant_for_foreign_exercise` | AC8 |
| `test_service_does_not_call_grader_when_closed` | AC9 (Piège n°11) |

### Hint generation — `test_hints.py::TestHintGenerator`

| Test | AC couvert |
|---|---|
| `test_generate_hints_v1_qcm_returns_list_of_strings` | AC1 |
| `test_generate_hints_v2_text_includes_grading_criteria_context` | AC2 |
| `test_generate_hints_v1_differ_from_v2_for_same_input` | AC7 |
| `test_generate_hints_retries_on_malformed_output` | Piège n°7 |
| `test_generate_hints_falls_back_to_generic_when_llm_fails_twice` | Piège n°7 |
| `test_generate_hints_qcm_prompt_targets_concept_not_grading` | Piège n°1 (distinction QCM/texte) |

### CLI — `test_cli.py::TestSubmitAttempt`

| Test | AC couvert |
|---|---|
| `test_submit_attempt_qcm_first_try_success_returns_zero` | AC1, AC4 |
| `test_submit_attempt_qcm_first_try_failure_returns_partial` | AC1 |
| `test_submit_attempt_qcm_third_try_failure_returns_full_after_attempts` | AC3 |
| `test_submit_attempt_qcm_fourth_try_returns_six` (exit 6 = closed) | AC9 |
| `test_submit_attempt_cross_tenant_returns_five` (exit 5) | AC8 |
| `test_submit_attempt_json_output_is_valid` | AC1 |

### Multi-tenant — `test_progressive.py::TestCrossTenant`

| Test | AC couvert |
|---|---|
| `test_foreign_exercise_raises_cross_tenant` | AC8 |
| `test_foreign_attempt_history_does_not_influence_counter` (Piège n°5) | AC8 |

### Bites de régression (à exécuter en fin d'implémentation)

1. **AC2 (partial_attempt_2)** : neutraliser la branche `elif attempt_number == 2: "partial_attempt_2"` → test rouge sur `test_service_evaluates_second_attempt_failure_with_partial_attempt_2`.
2. **AC9 (closed)** : retirer le check `attempt_number > max_attempts` → test rouge sur `test_service_raises_closed_on_attempt_4` et `test_submit_attempt_qcm_fourth_try_returns_six`.
3. **AC8 (cross-tenant)** : retirer la garde `if exercise.student_pseudo != pseudo` → test rouge sur `test_foreign_exercise_raises_cross_tenant`.
4. **AC5 (correction_level persisté)** : retirer l'écriture de `attempt.correction_level` dans le service → test rouge sur `test_service_persists_attempt_with_correction_level`.
5. **Piège n°6 (first-try success = full)** : muter la state machine pour retourner `partial` même si `is_success=True` → test rouge sur `test_service_evaluates_first_try_success_with_full`.

## Risques

> La complexité est 4, le plus haut du lot Phase 2. Risques explicites :

### R1. State machine × 2 types d'exercice = combinatoire

- **Manifestation** : la state machine est simple (4 états), mais le contenu des hints dépend du type (QCM vs texte) et de la tentative (v1 vs v2). Soit 2 × 2 = 4 prompts à maintenir. Si on ajoute un type (s07, puis s18, puis un hypothétique « true/false » plus tard), la combinatoire explose.
- **Mitigation** :
  1. Implémenter la state machine comme **pure function** (D1) pour borner la complexité au table de vérité.
  2. Les prompts hints sont versionnés explicitement (D2) et testés par leur **contrat** (retournent une liste de strings), pas leur contenu.
  3. La distinction QCM vs texte est isolée dans `HintGenerator._build_prompt(...)` (un `if/elif`), pas éparpillée.

### R2. LLM non-déterministe pour les hints

- **Manifestation** : le contenu des hints varie d'un appel à l'autre, même avec `temperature=0`. Un test qui assert `hints == ["Relisez le cours sur les dérivées", ...]` sera fragile.
- **Mitigation** :
  1. Tests unitaires : stub LLM qui retourne un script fixe (cf. `_ScriptedLlm` `test_qcm_generator.py:47`).
  2. Tests d'intégration (best-effort, marqués `@pytest.mark.integration`) : assert que la longueur est dans [1, 3] et que les hints sont non-vides.
  3. Le contrat testé est la **forme** (liste de 1-3 strings), pas le fond.

### R3. Couplage avec s07 (texte libre)

- **Manifestation** : s08 a besoin du verdict de `TextGrader` (s07), mais s07 est en parallèle. Si s07 change son contrat, s08 doit s'adapter.
- **Mitigation** :
  1. s08 dépend d'un **contrat** (interface `GradeCallback` ou `Protocol`), pas d'une implémentation.
  2. Le test s08 mock ce contrat (`_StubTextGrader` retourne `is_success, feedback`).
  3. Quand s07 sera planifiée et implémentée, l'orchestrateur CLI (`submit-attempt`) branchera le vrai `TextGrader` sur le même contrat.

### R4. PRD open question (D3)

- **Manifestation** : « failed 3 times = raté vs réussi après aide » n'est pas tranchée. Affecte l'agrégation dans le dashboard (s16).
- **Mitigation** :
  1. Le plan **pose explicitement la question** au checkpoint et recommande l'option A (conserver `is_success=False`).
  2. L'`Exercise` lui-même peut être flagué `completed_via_hints` (extension future, hors s08).
  3. s16 (dashboard) traitera la sémantique ; s08 n'a qu'à exposer la donnée brute (`is_success`, `correction_level`).

### R5. Course condition sur `MAX(attempt_number)` (Piège n°8)

- **Manifestation** : deux soumissions parallèles peuvent obtenir le même `attempt_number`.
- **Mitigation** : hors scope de s08. Documenter la limite ; s15 ajoute la `UNIQUE(exercise_id, student_pseudo, attempt_number)`.

### R6. Écart de spec entre CLAUDE.md (5 états) et story (4 états) (Piège n°9)

- **Manifestation** : `CLAUDE.md:307` liste `partial_attempt_3`, mais l'AC5 de s08 ne le retient pas. Si un reviewer lit CLAUDE.md et exige `partial_attempt_3`, la PR est bloquée.
- **Mitigation** : **documenter l'écart dans la PR** (un commentaire dans `progressive.py` + une note dans la description de PR). L'AGENTS.md est clair : « stories sont la source de vérité du périmètre ».

## Definition of Done (spécialisée s08)

> Référence : `AGENTS.md` § Définition of Done + adaptions spécifiques à s08.

- [ ] Toutes les tâches du plan s08 cochées.
- [ ] `pytest --cov=app --cov-fail-under=80 -m "not integration"` passe (cible : ≥ 200 tests, vs 189 baseline s04).
- [ ] `ruff check app tests` clean (0 erreur).
- [ ] AC1-AC9 tous couverts par au moins un test (idéalement un par AC explicite + 1 bite de régression).
- [ ] La state machine est testée exhaustivement (5 transitions + 1 closed, parametrize).
- [ ] Cross-tenant : un test vérifie qu'un pseudo ne peut pas soumettre sur un exercice d'un autre pseudo (AC8) ET que les hints d'un exercice ne sont pas lisibles par un autre pseudo.
- [ ] Génération d'indices : tests avec stub LLM couvrent QCM (v1, v2) et texte (v1, v2), retry sur malformed, fallback déterministe.
- [ ] Le 4e tentative retourne 409 (CLI : exit 6) — testé par `test_service_raises_closed_on_attempt_4` ET `test_submit_attempt_qcm_fourth_try_returns_six`.
- [ ] `correction_level` est persisté en DB avec l'une des 4 valeurs autorisées (test `test_service_persists_attempt_with_correction_level`).
- [ ] `MAX_CORRECTION_ATTEMPTS=3` est lu depuis l'env et surchargeable (test `test_config.py`).
- [ ] Logs structurés : `loguru` JSON avec `pseudo`, `exercise_id`, `attempt_number`, `correction_level`, `is_success`, `duration_ms`.
- [ ] `is_success=True` au premier coup → `correction_level="full"` (pas `partial`), bite de régression vérifié.
- [ ] `MAX_CORRECTION_ATTEMPTS` non câblé dans `config.py` doit être ajouté (étape 0 du plan).
- [ ] `qcm_grader.py`, `qcm_generator.py`, `llm/client.py`, `models.py` non modifiés (run interdicts).
- [ ] PR unique, description structurée : résumé, AC cochées, écart documenté (`partial_attempt_3` non implémenté), décision D3 explicitée.
- [ ] `git diff main...feature/s08-correction-progressive` lisible.
- [ ] Review passée (`docs/reviews/s08-correction-progressive.md` avec `Ship allowed: yes`).

## Questions ouvertes / à trancher au plan

> Le plan doit les résoudre (référence au gate `validated: yes` du frontmatter).

1. **D1 (state machine pure function vs class)** — recommandation : pure function.
2. **D2 (4 prompts hints vs 1)** — recommandation : 4 prompts versionnés.
3. **D3 (raté vs réussi après aide)** — recommandation : `is_success=False` (à poser au checkpoint).
4. **D4 (closed enforcement)** — recommandation : service (pas CLI).
5. **D5 (retry + fallback LLM)** — recommandation : 1 retry + fallback déterministe.
6. **D6 (bonus points)** — recommandation : 2 seulement au first-try (lecture stricte s20).
7. **D7 (commande CLI unifiée vs extensions)** — recommandation : `submit-attempt` unifié (refactor s04 + s07), mais c'est non-trivial. Alternative : extensions de `submit-qcm` et `submit-text`. À trancher.
8. **D8 (CHECK constraint sur `correction_level`)** — recommandation : pas en s08, ajouter en s15.

## Sources

> Fichiers et sections lus pour cette recherche. Tous les chemins sont absolus ou relatifs au worktree (`C:\Workspace\ktutor\.worktrees\s08-correction-progressive`).

### Code (lu intégralement ou aux sections citées)

- `backend/app/services/exercises/qcm_grader.py:1-281` — `QcmGrader`, `QcmGradingError`, `GradingResult`, `SubmittedAnswers`, `_SessionLike`, `_next_attempt_number` (s04, shippé).
- `backend/app/core/database/models.py:1-195` — `Document`, `Exercise`, `Attempt`, `ExerciseType`, `Subject`, `DocumentStatus` (s01/s03/s04).
- `backend/app/services/exercises/qcm_generator.py:1-341` — `QcmGenerator`, `QcmQuestion`, prompts LLM (s03, shippé).
- `backend/app/services/llm/client.py:1-79` — `LlmClient` Protocol, `build_llm_client`, `_LangChainChatWrapper` (s02).
- `backend/app/services/agents/maths_agent.py:1-145` — pattern d'agent avec LLM, citations, injection (s02).
- `backend/app/core/config.py:1-81` — `Settings` Pydantic (s01-s04). `MAX_CORRECTION_ATTEMPTS` **NON présent**.
- `backend/app/cli.py:1-529` — `submit_qcm` (s04) et autres commandes. Patterns `_build_*_service`, `_print_*_result`, mapping d'exit codes.
- `backend/tests/services/exercises/test_qcm_grader.py:1-409` — fixtures (`_TrackingSession`, `_SessionFactory`, `memory_db`, `_seed_exercise`), classes de test (`TestSchema`, `TestGrade`, `TestPersistence`, `TestAttemptNumber`, `TestCrossTenant`, `TestInvalidExercise`, `TestExerciseNotFound`, `TestInvalidAnswers`).

### Spec / doc

- `CLAUDE.md:13` (résumé exécutif correction progressive), `CLAUDE.md:129` (arborescence cible), `CLAUDE.md:260-310` (workflow + tableau des 5 états), `CLAUDE.md:390-490` (algorithme `ProgressiveCorrection`, **incomplet pour `partial_attempt_2`**), `CLAUDE.md:609` (`MAX_CORRECTION_ATTEMPTS=3` documenté mais non câblé).
- `docs/stories.md:296-335` — story s08 complète (9 AC, dépendances, traps, open question PRD).
- `docs/prd.md:35` (périmètre : correction progressive), `docs/prd.md:86` (open question : « raté vs réussi après aide »), `docs/prd.md:9` (différenciateur produit).
- `docs/architecture.md:207-217` (schéma `attempts`), `docs/architecture.md:288-299` (integration points).
- `docs/research/s04-repondre-qcm.md:1-218` (research s04 — patterns, traps, conventions).
- `docs/plans/s04-repondre-qcm.md:1-215` (plan s04 — exemple de structure de plan à reproduire).
- `docs/reviews/s04-repondre-qcm.md:1-114` (review s04 — bite tests, multi-tenant verrouillé, ship allowed yes).

### ADRs applicables

- `docs/decisions/001-monorepo-backend-frontend.md` (monorepo, structure backend).
- `docs/decisions/002-poc-rewrite-from-scratch.md` (POC = réécriture from scratch).
- `docs/decisions/004-rag-isolation-by-collection.md` (isolation par collection ChromaDB, **n'affecte pas directement s08** mais fixe le pattern multi-tenancy).
- `docs/decisions/005-auth-rs256-rbac.md` (auth JWT — n'affecte pas directement s08, mais le champ `student_pseudo` est la clé d'isolation).

### Conventions projet (AGENTS.md + CLAUDE.md)

- **Backend** : snake_case fichiers, PascalCase classes, kebab-case URLs. `from __future__ import annotations`. Erreurs typées avec `kind: str`. `loguru` JSON. Tests `pytest` avec `_TrackingSession` + SQLite in-memory.
- **Multi-tenancy** : `student_pseudo` partout, filtre côté service (pas côté CLI), message générique pour `cross_tenant` (= `exercise_not_found`).
- **State machine** : pas de pattern existant, à créer (D1).
- **Hints LLM** : pas de pattern existant, à créer (D2). Référence la plus proche : `qcm_generator.py:284-314` (1 retry avec prompt strict).
- **LLM testing** : `FakeListLLM` ou `_ScriptedLlm` (s03). Pas d'appel LLM réel dans les tests unitaires.

## Point de bascule

> Le « point everything turns on » pour le plan.

**L'invariant de la state machine** : `next_correction_level(attempt_number, is_success, max_attempts)` est une **fonction pure, totale, et testée parametrize** sur les 8 transitions (1×success, 1×fail, 2×success, 2×fail, 3×success, 3×fail, 4×closed, 4×closed). Tant que cette table de vérité est correcte et que la garde multi-tenant est appliquée avant, le reste du service (hint generation, persistance, mapping CLI) ne peut pas casser la state machine. Les pièges 1-11 sont tous des pièges **autour** de cet invariant (états manquants, garde oubliée, persistance partielle, etc.) — pas l'invariant lui-même.

**Trois endroits où le plan peut se tromper** :

1. **L'algo `ProgressiveCorrection` du CLAUDE.md (l.395-462) n'a qu'un état `partial`** — si le plan le reproduit tel quel, l'AC2 (`partial_attempt_2`) échoue. Le plan doit **étendre** explicitement avec `elif attempt_number == 2`.
2. **La garde multi-tenant** (`if exercise.student_pseudo != pseudo`) doit précéder l'invocation de la state machine. Si le plan l'oublie ou la met après, un élève A peut gratter les hints d'un exercice de l'élève B.
3. **Le `correction_level` doit être écrit dans la même transaction que l'`Attempt`**. Si le plan fait deux `commit()` séparés, une coupure réseau au milieu laisse un attempt sans `correction_level`, et la state machine est silencieusement corrompue pour les tentatives suivantes.

## Run interdicts (à reporter dans le plan)

- **Ne PAS modifier** `backend/app/services/exercises/qcm_grader.py` (s04, intact).
- **Ne PAS modifier** `backend/app/services/exercises/qcm_generator.py` (s03, intact).
- **Ne PAS modifier** `backend/app/services/llm/client.py` (s02, intact).
- **Ne PAS modifier** `backend/app/services/agents/maths_agent.py` (s02, intact).
- **Ne PAS modifier** `backend/app/services/rag/chroma_store.py`, `retriever.py`, `ingestion.py`, `ocr.py`, `upload_service.py` (s01, intact).
- **Ne PAS modifier** `backend/app/services/storage/minio_client.py` (s01b, intact).
- **Ne PAS câbler** de LLM dans le state machine (D1 : pure function). Le LLM est dans `HintGenerator` uniquement.
- **Ne PAS créer** de migration Alembic pour `attempts` (s15 viendra). `init_db()` (déjà appelé par s04) suffit en dev/CI.
- **Ne PAS utiliser** `JSONB` (Postgres-only). Utiliser `sqlalchemy.JSON` (portable).
- **Ne PAS implémenter** `partial_attempt_3` (Piège n°9, écart avec CLAUDE.md, story prime).
- **Ne PAS toucher** au `RewardLedger` (s20 s'en chargera). s08 expose juste `bonus_points: int`.
- **Ne PAS commit** depuis la base du repo. Tout le travail se fait dans `.worktrees/s08-correction-progressive/`.
- **Ne PAS push** vers `main` directement. PR obligatoire.

## Annexe — Table de vérité complète de la state machine

| `attempt_number` | `is_success` | `correction_level` | `correction_content` | `bonus_points` |
|---|---|---|---|---|
| 1 | True | `"full"` | `{solution, detailed_correction, common_mistakes}` | 2 |
| 1 | False | `"partial"` | `{hints: [1-3], next_steps}` | 0 |
| 2 | True | `"full"` | `{solution, detailed_correction, common_mistakes}` | 0 (D6) |
| 2 | False | `"partial_attempt_2"` | `{hints: [1-3 plus précis], next_steps, identified_error_type?}` | 0 |
| 3 | True | `"full"` | `{solution, detailed_correction, common_mistakes}` | 0 (D6) |
| 3 | False | `"full_after_attempts"` | `{solution, detailed_correction, message: "Après 3 tentatives…"}` | 0 |
| > 3 | n'importe | **FERMÉ** | (n/a — l'`Attempt` n'est même pas créé) | 0 |

**Note D3** : pour `full_after_attempts`, `is_success=False` est conservé dans l'`Attempt` (l'élève a échoué 3 fois avant d'obtenir la correction).

**Note D6** : `bonus_points=2` seulement si `is_success=True` ET `attempt_number==1`. Aux tentatives 2 et 3 (succès tardif), 0 bonus. À trancher au plan.

---

<< IP Mike: ce que toute recherche doit vérifier — premise, traps, anchor points, complexity, sources citées. >>
