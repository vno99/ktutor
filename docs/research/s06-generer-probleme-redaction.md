---
name: research-s06-probleme-redaction
description: s06-generer-probleme-redaction — recherche de contexte pour /ks-plan
metadata:
  type: project
  story: s06-generer-probleme-redaction
---

# Recherche — Story s06-generer-probleme-redaction

## 1. Rappel de la story

Source : `docs/stories.md` (lignes 188-219).

**As an** élève **I want** générer un exercice de type problème (maths) ou rédaction (français) **so that** je puisse m'entraîner sur un exercice libre.

**Complexity** : 3 — LLM generation + structured output + persistence.

### Acceptance criteria (5 ACs)

1. La commande `python -m ktutor.cli generate-exercise --pseudo <p> --subject <s> --type probleme|redaction --topic "..." --difficulty facile|moyen|difficile` retourne un JSON avec `statement`, `expected_answer` (solution complète, pour grading ultérieur), et `grading_criteria` (liste de chaînes pour le grading LLM).
2. Pour `probleme` (maths), l'énoncé est un problème multi-étapes avec données numériques explicites.
3. Pour `redaction` (français), l'énoncé est un sujet de rédaction avec longueur et registre imposés.
4. L'exercice est persisté avec les mêmes métadonnées que le QCM (`pseudo`, `subject`, `type`, `generation_date`, `statement`, `expected_answer`, `grading_criteria`).
5. Un test vérifie que le schéma JSON est valide pour les deux types.

### Questions ouvertes liées (PRD § Questions ouvertes)

- `docs/prd.md:85` — **« Modèles d'exercices : pour les problèmes de maths, quel niveau de détail dans l'énoncé ? (Algo à affiner en STORY-016.) »** → la présente story est l'occurrence réelle de la STORY-016. Le niveau de détail doit être tranché **ici** (cf. § 6).
- `docs/stories.md:219` (notes s06) — confirme que la question ouverte n°2 du PRD est traitée dans cette phase Research.

## 2. Code existant à réutiliser

Le générateur de cette story doit s'appuyer presque intégralement sur les patterns et le code livrés par s01-s04. Aucun module libre n'existe aujourd'hui : tout est à créer dans `backend/app/services/exercises/free_generator.py`. Voici l'inventaire exhaustif des briques réutilisables.

### 2.1. Modèle `Exercise` (s03, livré)

- `backend/app/core/database/models.py:90-144` — table `exercises` polymorphique par `type`. Champs exploitables directement par s06 :
  - Lignes 119-122 : `type: Mapped[ExerciseType]` — enum à étendre.
  - Ligne 123-127 : `document_id: Mapped[uuid.UUID]` (FK logique, pas de constraint avant s15).
  - Lignes 129-130 : `statement: Mapped[str | None]` et `expected_answer: Mapped[str | None]` — **déjà câblés** et nullable, exactement la forme attendue par s06.
  - Ligne 131 : `grading_criteria: Mapped[dict[str, Any] | None]` — champ JSON déjà présent. Stocke une `list[str]` sérialisée.
  - Ligne 133 : `questions: Mapped[list[dict] | None]` — reste null pour les types non-QCM.
- Lignes 33-40 : `ExerciseType` enum (`QCM = "qcm"`). **À étendre** avec `PROBLEME = "probleme"` et `REDACTION = "redaction"`.
- Note importante : s06b (flashcards) a un besoin parallèle sur ce même enum (ajouter `FLASHCARDS = "flashcards"`). Les deux stories ajoutent chacune leur valeur, sans collision. Le plan s06 doit préciser l'ordre d'ajout pour éviter les conflits de merge entre worktrees (`s06-generer-probleme-redaction` et `s06b-generer-flashcards`).

### 2.2. Client LLM (s02, livré)

- `backend/app/services/llm/client.py:27-34` — `LlmClient` Protocol avec unique méthode `invoke(messages: list[BaseMessage]) -> AIMessage`. Le générateur libre s'injecte ce client, exactement comme `QcmGenerator` (s03).
- `backend/app/services/llm/client.py:51-79` — `build_llm_client(settings)`. Reprend `chat_temperature` (s03 crée `qcm_temperature` séparé — s06 créera `free_temperature`).
- Pas d'extension requise : le wrapper `_LangChainChatWrapper` est réutilisable tel quel.

### 2.3. Retriever (s03, livré)

- `backend/app/services/rag/retriever.py:104-151` — `Retriever.get_chunks_for_document(subject, pseudo, document_id, k=20)`. Filtre par `document_id` dans la collection de l'élève. **Réutilisable tel quel** : le générateur libre gronde ses énoncés sur les chunks d'un document, comme le QCM. Différences attendues :
  - Le nombre de chunks à passer au prompt doit être paramétrable (s03 force `k=20`). Pour un problème ou une rédaction, on a souvent besoin de plus de contexte (5-10 chunks substantiels). Le plan peut soit (a) réutiliser la méthode existante avec un `k` plus grand (ex. 30), soit (b) accepter un `k` injectable. **(a) suffit** — `k` est un paramètre de la méthode.
- L'invariant multi-tenant (`pseudo` validé par `validate_pseudo` à la ligne 128) est respecté. ADR 004 honoré.

### 2.4. Pattern de persistence (s03, livré)

- `backend/app/services/exercises/qcm_generator.py:198-225` — constructeur de `QcmGenerator` : `session_factory: Callable[[], _SessionLike] | None = None`. Le générateur libre adopte la **même signature**, modulo l'ajout de `default_difficulty: str = "moyen"`.
- `backend/app/services/exercises/qcm_generator.py:316-335` — pattern de persistence : `session.add(Exercise(...))` puis `session.commit()`, avec `try/except: rollback; raise`. Reprend exactement cette structure.
- L'invariant `Exercise.student_pseudo == pseudo` (vérification `document.student_pseudo == pseudo` à la ligne 263 de `qcm_generator.py`) doit être reproduit : on vérifie que le document appartient à l'élève **avant** d'invoquer le LLM (pas de leak, pas d'appel LLM sur requête cross-tenant).

### 2.5. Pattern de parsing LLM + retry (s03, livré)

- `backend/app/services/exercises/qcm_generator.py:88-116` — `_extract_json_block(text) -> str | None`. Stratégie : (a) strip les fences markdown ```json, (b) `json.loads`, (c) si échec, regex `_JSON_OBJECT_RE` cherche le premier bloc `{...}`. **Réutilisable tel quel** : la même regex s'applique au JSON de s06 (statement/expected_answer/grading_criteria).
- `backend/app/services/exercises/qcm_generator.py:290-314` — boucle de retry : 1ère tentative avec prompt « soft » autorisant markdown, retry avec prompt « strict » `=== JSON START ===`. **Pattern à dupliquer** pour s06. `max_retries` est un paramètre injectable (ligne 217, défaut 1).
- Le prompt soft/strict doit interdire explicitement la « correction » dans l'énoncé (le `system_prompt` du QCM à la ligne 123 interdit déjà « révèle la bonne réponse dans la question » — analogue pour s06).

### 2.6. CLI typer (s03, livré)

- `backend/app/cli.py:135-160` — `_build_qcm_service()` : wire `ChromaStore`, `build_embedding_provider`, `build_llm_client`, `Retriever`, `QcmGenerator`, `db_session.init_db()`. Le `_build_free_service()` de s06 reprend la même forme.
- `backend/app/cli.py:336-405` — `generate_qcm` : pattern complet (option `--pseudo`, `--document-id`, mapping d'exceptions vers exit codes, `_print_qcm_result`, `_print_qcm_error`). Le `generate_exercise` de s06 reprend la même structure avec un mapping d'exceptions propre.
- Conventions d'exit code à respecter (cf. `docs/designs/s01-uploader-document.md`, cité en `backend/app/cli.py:13-20`) :
  - 0 — succès
  - 4 — LLM malformed / storage failure
  - 5 — document not found / cross-tenant

### 2.7. Conventions de test (s03 + s04, livrés)

- `backend/tests/services/exercises/test_qcm_generator.py:47-62` — `_ScriptedLlm` : drop-in pour `LlmClient`, garde la liste des appels, pop la prochaine réponse à chaque `invoke`. **Pattern à dupliquer** pour s06.
- `backend/tests/services/exercises/test_qcm_generator.py:64-91` — `_TrackingSession` : wrappe une vraie session SQLAlchemy, observe chaque `session.add(obj)`. **Pattern à dupliquer**.
- `backend/tests/services/exercises/test_qcm_generator.py:186-211` — fixtures `memory_db` (SQLite in-memory + `Base.metadata.create_all`) et `_SessionFactory` (retourne le même wrapper sur tous les appels). **Réutilisables tels quels**.
- `backend/tests/services/exercises/test_qcm_generator.py:596-637` — bite de test cross-tenant : Alice possède le document, Bob demande, on vérifie `llm.calls == []`. Le test mord si on retire la vérification d'ownership. **Pattern à dupliquer**.
- `backend/tests/cli/test_cli.py:411-590` — `_StubQcmGenerator` + `stubbed_qcm_service` (monkeypatch de `_build_qcm_service`) + 6 tests `TestGenerateQcm`. **Pattern à dupliquer** pour `generate-exercise`.

### 2.8. Settings (s03, livré)

- `backend/app/core/config.py:67-70` — bloc `QCM_*` (4 variables : default, max, retries, temperature). **Pattern à étendre** avec un bloc `FREE_*` (4 variables analogues : default_difficulty, max_difficulty_options, retries, temperature). Une éventuelle variable `free_max_statement_chars` est à envisager pour borner l'énoncé (cf. § 6).
- `backend/.env.example` fin de fichier (lignes 65-72) — 4 vars QCM commentées. **À étendre** avec 4 vars FREE.

### 2.9. Schéma Pydantic (s03, livré)

- `backend/app/services/exercises/qcm_generator.py:45-64` — `QcmQuestion`, `QcmExercise`, `QcmGenerationResult` (modèles Pydantic 2 avec `Field(min_length=..., max_length=...)`). Le générateur libre aura `FreeStatement` (Pydantic), `FreeExercise` (Pydantic), `FreeGenerationResult` (Pydantic) — **même style, même conventions**.

### 2.10. Architecture cible

- `docs/architecture.md:188-205` — schéma `exercises` cible. Les champs `statement TEXT`, `expected_answer TEXT`, `grading_criteria JSON` sont déjà décrits comme « nullable; QCM leaves it null ». s06 n'a **rien à modifier** dans `docs/architecture.md` — il remplit simplement les colonnes déjà documentées. Le commentaire « QCM payload » à la ligne 197 reste exact.

## 3. Dépendances amont

s06 a besoin des fondations posées par s01-s04. La table suivante résume les **livrables réutilisables** et le **risque** si l'un d'eux est manquant.

| Story | Livrable attendu | Fichier / symbole | Conséquence si absent |
|---|---|---|---|
| s01 | Pipeline RAG par matière | `ChromaStore`, `Retriever.query` | Pas d'ancrage RAG pour l'exercice. |
| s01 | Modèle `Document` | `backend/app/core/database/models.py:43-87` | Pas de jointure possible pour valider l'ownership. |
| s01 | Collection par (matière × pseudo) | ADR 004 | Fuite cross-tenant si régression. |
| s02 | Client LLM avec `invoke(messages)` | `app/services/llm/client.py:51-79` | Le générateur n'a pas de LLM à appeler. |
| s02 | Settings chat | `Settings.llm_*`, `Settings.chat_*` | Pas de config centralisée. |
| s03 | Modèle `Exercise` polymorphique | `app/core/database/models.py:90-144` | Pas de table où persister. **Bloquant**. |
| s03 | `ExerciseType` enum | `app/core/database/models.py:33-40` | Pas de discriminant. **Bloquant**. |
| s03 | `Retriever.get_chunks_for_document` | `app/services/rag/retriever.py:104-151` | Pas de filtre par document. **Bloquant**. |
| s03 | `_extract_json_block` | `app/services/exercises/qcm_generator.py:88-116` | À recoder (risque de divergence). |
| s04 | `Attempt` model | `app/core/database/models.py:147-195` | Pas de table d'attempts pour s07 (rédaction grading). Mais s06 ne crée pas d'attempt — juste un exercice. Pas bloquant pour s06, mais bloque s07. |

**Toutes les stories amont sont livrées (PRs #2-#5 mergées sur `main` au moment de la recherche).** Le diff `git diff main...feature/s06-generer-probleme-redaction` est vide au démarrage.

## 4. Contraintes techniques

### 4.1. Validation Pydantic obligatoire

Comme pour s03, **toute** sortie LLM est validée par Pydantic **avant** persistance (cf. bite #4 du review s03 : `session.add` retiré → test rouge). Les pièges à anticiper :

- `statement` peut être tronqué par le LLM au-delà de 8192 caractères (limite de la colonne `String(8192)` à la ligne 129 de `models.py`). Le plan doit soit (a) augmenter la taille de la colonne (refactor transverse à coordonner avec s06b), soit (b) tronquer côté Pydantic avec un avertissement explicite. **(a) est risqué** : changement de schéma sans migration. **(b) est recommandé** : un énoncé de maths de niveau collège dépasse rarement 2000 caractères, une rédaction dépasse rarement 4000.
- `expected_answer` est la solution complète. Pour un problème de maths multi-étapes, 4000-6000 caractères sont plausibles. Pour une rédaction, l'`expected_answer` est un **corrigé type** (introduction, développement, conclusion) — facilement 2000-3000 caractères. La limite 8192 tient.
- `grading_criteria` est une `list[str]`. Le prompt LLM doit demander une liste (par exemple : « 3 à 5 critères vérifiables »). Le plan doit borner la longueur (Pydantic `Field(min_length=1, max_length=10)`).

### 4.2. Structured output LLM

Le PRD (lignes 34-35) exige 4 types d'exercices : QCM, problème, rédaction, flashcards. Le LLM doit donc accepter un **discriminant de type** dans le prompt. Trois architectures possibles (cf. § 6) :

- **Option A** : un seul prompt avec branche `if type == "probleme" ... elif type == "redaction" ...`. Pro : un seul service. Con : prompt plus long, plus risqué à débugger.
- **Option B** : deux prompts distincts, deux fonctions. Pro : prompts courts, plus faciles à itérer. Con : duplication du boilerplate (parsing, retry, persistence).
- **Option C** : une fonction `generate(pseudo, subject, type, ...)` qui route vers deux sous-fonctions privées. Pro : API publique unifiée, prompts isolés. Con : deux schémas Pydantic à maintenir.

Le plan doit trancher (cf. § 6 décision D1).

### 4.3. Multi-tenancy

L'invariant **doit** être le même que s03 :

- Le `pseudo` est validé par `validate_pseudo` avant tout (`app/services/rag/chroma_store.py:34-39`).
- Le `document_id` doit être un UUID, et le document doit appartenir à `pseudo` (cf. `qcm_generator.py:260-269`).
- Le filtre ChromaDB est `(subject, pseudo)` puis `where={"document_id": ...}`.
- Le LLM **n'est jamais appelé** sur une requête cross-tenant (test bite s03 ligne 637 : `assert llm.calls == []`).
- L'erreur retournée est `document_not_found` dans tous les cas (pas de leak).

### 4.4. Niveau collège (âge-appropriate)

Le PRD (ligne 13) cible les **collégiens 6e-3e** (~11-15 ans). Contraintes concrètes sur le contenu généré :

- **Maths** : un problème de 6e n'utilise pas les nombres négatifs pour les aires ; un problème de 3e peut. Le plan doit paramétrer la difficulté mais **ne peut pas** se reposer uniquement sur le LLM pour adapter le niveau — il faut un prompt système qui **explicite** le niveau.
- **Français** : la rédaction ne doit pas suggérer de sujet sensible (violence, politique, religion, etc.). Le prompt système doit contenir une clause « sujet adapté à un élève de collège, registre neutre, ni violent ni politique ».
- Le **registre** de la rédaction (courant, soutenu, familier) doit être imposé par le prompt et vérifiable.

Le plan doit ajouter une assertion dans le test : pour un `probleme` avec `difficulty="facile"`, le LLM reçoit un prompt contenant « niveau 6e-5e » ; pour `difficulty="difficile"`, « niveau 4e-3e ». Vérification par introspection de `llm.calls[N].messages` (pattern déjà en place dans `test_qcm_generator.py:399-401`).

### 4.5. Richesse de `expected_answer`

L'AC1 exige un `expected_answer` « full solution, for later grading ». Le piège central est un LLM qui produit un `expected_answer` pauvre (juste la réponse finale, ex. « 42 », sans la démarche). Le plan doit :

- Demander explicitement une **démarche étape par étape** dans le prompt.
- Vérifier en Pydantic que `expected_answer` est plus long qu'un seuil minimal (par exemple : `min_length=20` caractères, ou plus strict : `>= 3 * len(statement)`).
- Prévoir un test bite : si on retire la clause « démarche étape par étape » du prompt, le test « expected_answer est substantiel » devient rouge.

### 4.6. Longueur et format de la rédaction (AC3)

Le PRD AC3 demande « target length and register ». Le prompt LLM doit inclure explicitement :

- **Longueur** : « entre X et Y mots ». Proposition : 200-400 mots pour `facile`, 400-600 pour `moyen`, 600-800 pour `difficile`. Le Pydantic peut parser un nombre de mots approximatif, ou simplement demander un champ `target_word_count: int` que le plan retournera à l'élève (information pédagogique, pas une validation stricte).
- **Registre** : courant / soutenu / familier / argumentatif / narratif. Une énumération fermée dans le prompt, avec un test qui vérifie que le prompt liste les registres disponibles.

Le piège (cf. § 5) est un LLM qui omet cette information. Le test bite : retirer « registre : ... » du prompt → le test « prompt contient un registre » devient rouge.

## 5. Pièges identifiés

### Piège 1 — Le LLM produit une « correction » au lieu d'un « énoncé »

**Description** : un LLM appelée à générer un problème de maths produit « Voici un problème : un train part de Paris à 14h... Solution : le train arrive à 18h. ». Le JSON retourné contient la solution dans `statement` et `expected_answer` est vide ou redondant. Le test de l'AC1 (« énoncé vs correction ») ne mord pas parce qu'on n'a pas de discriminateur.

**Mitigation** :

- Le system prompt doit contenir une clause explicite : « `statement` est UNIQUEMENT l'énoncé, sans la solution. `expected_answer` est UNIQUEMENT la solution complète. »
- Le test bite : pour un LLM scripted qui retourne `{"statement": "Énoncé + Solution...", "expected_answer": ""}`, le test rouge.
- Pattern s03 : le system prompt du QCM (`qcm_generator.py:142-144`) interdit déjà le leak de la réponse dans la question. On s'en inspire.

### Piège 2 — `expected_answer` trop mince pour le grading de s07

**Description** : s07 (soumettre une réponse libre) s'appuiera sur `expected_answer` pour comparer avec la réponse de l'élève. Si `expected_answer` est juste « 42 », s07 ne peut pas distinguer « 42 par chance » de « 42 par compréhension ». Le test de l'AC1 est satisfait (le JSON est valide), mais s07 sera inutilisable.

**Mitigation** :

- Le prompt LLM exige une démarche étape par étape (cf. § 4.5).
- Le plan ajoute une validation Pydantic : `expected_answer` doit être substantiel. Proposition de bite : `len(expected_answer) >= 50` (caractères) pour `probleme`, `>= 200` pour `redaction` (le corrigé type d'une rédaction est plus long).
- Test bite : mocker un LLM qui retourne `expected_answer="42"` → la validation lève `FreeGenerationError("thin_expected_answer")`.

### Piège 3 — Rédaction sans longueur ni registre spécifiés

**Description** : AC3 demande « target length and register ». Un LLM sans consigne explicite produit « Écris une rédaction sur le thème de l'amitié. » — conforme au type, mais inutilisable comme consigne d'exercice (l'élève ne sait pas combien de mots, quel ton).

**Mitigation** :

- Le system prompt de `redaction` doit imposer `target_word_count` (entier) et `register` (parmi une liste fermée).
- Le Pydantic `RedactionStatement` doit valider `target_word_count: int = Field(ge=50, le=2000)` et `register: str` ∈ énumération fermée.
- Test bite : mocker un LLM qui omet `target_word_count` → Pydantic rejette.

### Piège 4 — Difficulté non prise en compte

**Description** : AC1 mentionne `--difficulty facile|moyen|difficile`. Un LLM qui ignore la difficulté produit toujours le même niveau. Le piège n'est pas un crash, c'est un用户体验 dégradé.

**Mitigation** :

- Le prompt injecte la difficulté et la traduit en **consignes concrètes** (« facile » → nombres entiers < 100, une seule opération ; « difficile » → plusieurs étapes, fractions, etc.).
- Test bite : mocker un LLM scripted pour répondre à `difficulty="facile"` et `difficulty="difficile"`. Vérifier que les prompts diffèrent et contiennent des marqueurs (« nombres simples » vs « fractions »).
- Note : on n'évalue **pas** la difficulté de la sortie (trop subjectif), on vérifie que le **prompt** est différencié.

### Piège 5 — Compatibilité avec le worktree s06b

**Description** : `s06b-generer-flashcards` (worktree voisin, déjà créé) ajoute `FLASHCARDS = "flashcards"` à `ExerciseType`. Si s06 ajoute `PROBLEME` et `REDACTION` au même enum, les deux PRs entrent en conflit.

**Mitigation** :

- Le plan s06 doit **committer en premier** la modification de l'enum (ajout des deux valeurs) sur sa branche. Si s06b a déjà committé sur sa branche, le merge de s06 vers `main` créera un conflit trivial (deux ajouts sur le même enum). C'est un conflit acceptable, à résoudre par union.
- Le plan s06 doit ajouter les deux valeurs (`PROBLEME`, `REDACTION`) en un seul commit, **avant** tout autre changement, pour minimiser la surface de conflit.
- **Action concrète** : Étape 0 du plan commence par « Étendre `ExerciseType` avec `PROBLEME = "probleme"` et `REDACTION = "redaction"` ».

### Piège 6 — Sujet de rédaction inapproprié (âge, registre)

**Description** : sans garde-fou explicite, le LLM peut proposer un sujet trop mature (« Rédige une dissertation sur la mort dans Camus ») ou un sujet vide (« Écris sur un sujet libre »). Le PRD (ligne 13) cible les collégiens.

**Mitigation** :

- Le system prompt contient une clause : « Le sujet doit être adapté à un élève de collège (11-15 ans). Pas de sujet violent, politique, religieux, sexuel. Propose un sujet en lien avec un thème classique de collège (amitié, nature, école, voyage, imaginaire, etc.). »
- Test bite : mocker un LLM scripted qui retourne un sujet explicitement interdit (« Rédige sur la guerre en Irak »). Le plan inclut un test qui vérifie qu'une **liste noire** de mots-clés n'apparaît jamais dans `statement` pour `redaction` (et pour `probleme` côté maths : pas de contexte violent). Note : cette liste est **best-effort** (regex), pas une garantie.

### Piège 7 — Troncature par la limite 8192 caractères de `String`

**Description** : la colonne `statement` est `String(8192)` (ligne 129 de `models.py`). Si le LLM produit un énoncé plus long (très plausible pour un problème de maths qui inclut un long tableau de données, ou pour une rédaction de 800 mots ≈ 5500 caractères + balises JSON ≈ 7000), MySQL/Postgres tronque silencieusement ou lève une erreur.

**Mitigation** :

- Le plan doit vérifier que la sortie LLM tient dans 8192 caractères **avant** d'écrire en base. Le Pydantic peut borner (`max_length=8000` par sécurité) ou le code peut lever `FreeGenerationError("statement_too_long")` et demander un retry.
- Si la limite est jugée trop basse, le plan peut proposer un agrandissement à `String(16384)` dans une migration. **Recommandation** : commencer par borner côté Pydantic, n'agrandir que si des cas légitimes saturent.

## 6. Décisions d'architecture à prendre

Les décisions **D1-D5** ci-dessous doivent être tranchées par le plan. Pour chacune, l'option recommandée est marquée **(R)**.

### D1 — Un ou deux prompts ? Une ou deux fonctions ? (R : Option C)

**Question** : comment discriminer `probleme` vs `redaction` dans le code ?

**Option A** — Un seul prompt avec branche :

```python
def generate(pseudo, subject, type, ...):
    system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(type=type, ...)
    ...
```

- Pro : un seul service, simple à tester.
- Con : le prompt fait 1500+ tokens, mélange des consignes contradictoires (« utiliser des données numériques » pour `probleme`, « pas de données numériques » pour `redaction`).

**Option B** — Deux fonctions distinctes (`generate_probleme`, `generate_redaction`) :

- Pro : prompts courts, dédiés.
- Con : duplication de parsing/retry/persistence, deux CLI commands au lieu d'une.

**Option C** (R) — Une fonction publique `generate(pseudo, subject, type, ...)` qui route vers deux sous-fonctions privées `_generate_probleme(...)` et `_generate_redaction(...)`. Schéma Pydantic unifié `FreeExercise` avec un sous-type discriminé par `type`.

- Pro : API publique unifiée (un seul `generate(...)` pour le CLI), prompts isolés, schémas Pydantic séparés.
- Con : deux schémas à maintenir. Acceptable (les deux types sont sémantiquement très différents).

**Recommandation détaillée pour le plan** :

- `FreeStatement` (Pydantic) — discriminant : `probleme_statement: str | None`, `redaction_meta: dict | None` (longueur, registre). OU deux classes Pydantic distinctes (`ProblemeStatement`, `RedactionStatement`) et un `Union` dans `FreeExercise`.
- La seconde option est plus propre. Pydantic 2 supporte bien les unions discriminées par `Literal`.

### D2 — Niveau de détail de l'énoncé maths (PRD Q2)

**Question** : pour un problème de maths, à quel point expliciter les données ?

**Options** :

- **D2.a (Concis)** : l'énoncé tient en 2-3 phrases, avec 2-3 données numériques. Style « un train part de Paris à 14h... ». L'élève doit comprendre la situation, identifier l'opération, calculer.
- **D2.b (Détaillé)** : l'énoncé décompose les étapes (« 1. Calcule la vitesse moyenne. 2. Sachant que... calcule la distance. »). L'élève a moins d'initiative.
- **D2.c (Mixte avec difficulté)** : `facile` → concis, `moyen` → semi-détaillé, `difficile` → détaillé avec distracteurs.

**Recommandation (R : D2.c)** : la difficulté module naturellement le niveau de détail. Le prompt injecte des consignes différentes par difficulté :

- `facile` : « 1-2 étapes, nombres entiers, contexte simple (courses, voyage), pas de distracteur ».
- `moyen` : « 2-3 étapes, mélange d'entiers et décimaux, contexte réaliste, 1 distracteur ».
- `difficile` : « 3-4 étapes, fractions ou pourcentages, mise en équation possible, 1-2 distracteurs ».

**Action pour le plan** : un tableau dans le plan qui mappe difficulté → consignes injectées. Test bite : mocker le LLM et vérifier que les prompts contiennent les bons marqueurs.

### D3 — Format du `grading_criteria`

**Question** : AC1 dit « list of strings for LLM grading ». Comment la formater ?

**Options** :

- **D3.a** : `list[str]` simple, ex. `["L'élève identifie la vitesse", "L'élève calcule correctement la distance", "L'élève convertit les unités"]`.
- **D3.b** : `list[dict]` structuré, ex. `[{"criterion": "...", "weight": 1.0}, ...]`.
- **D3.c** : `dict[str, str]` clé-valeur, ex. `{"criterion_1": "L'élève identifie...", ...}`.

**Recommandation (R : D3.a)** :

- L'AC dit explicitement « list of strings ». Le Pydantic `Field(min_length=1, max_length=10)` borne.
- La `weight` est un faux besoin à ce stade : s07 (grading LLM) lit les critères comme du texte brut, pas comme un barème pondéré.
- Pydantic `list[str]` est trivialement sérialisable en JSON.

### D4 — Choix de la longueur cible de la rédaction

**Question** : AC3 demande « target length ». Quelles bornes ?

**Options** :

- **D4.a** : `target_word_count: int` simple (l'élève vise N mots).
- **D4.b** : `min_words: int`, `max_words: int` (fourchette).
- **D4.c** : `target_word_count: int` + `tolerance: int` (cible ± tolérance).

**Recommandation (R : D4.b)** : un élève de collège a besoin d'une fourchette (la consigne « entre 300 et 400 mots » est plus naturelle que « 350 mots ± 20 »). Le Pydantic valide `min_words <= max_words`, `min_words >= 50`, `max_words <= 2000`.

### D5 — Comportement si le LLM ne produit pas un JSON valide

**Question** : pattern s03 = « pre-extract + Pydantic + 1 retry strict ». Faut-il faire mieux pour s06 ?

**Options** :

- **D5.a (R : s03-like)** : 1 retry strict, puis `FreeGenerationError("malformed_output")`. Cohérence avec s03.
- **D5.b** : 2 retries (un strict, un ultra-strict qui exige le schéma complet).
- **D5.c** : structured output JSON mode (si le provider le supporte, ex. `response_format={"type": "json_object"}` sur OpenAI).

**Recommandation (R : D5.a)** : s03 a fait ses preuves, la review s03 a validé ce pattern. D5.b augmente la latence sans gain clair. D5.c est une optimisation prématurée — à considérer en suivi si le taux d'échec `malformed_output` est élevé en prod. Le LLM par défaut (Minimax-M3 via OpenRouter) n'expose pas forcément `response_format`.

### Décision D6 — Validation `difficulty`

**Question** : `--difficulty facile|moyen|difficile` est une énumération fermée. Le CLI doit-il valider en amont ou laisser le service le faire ?

**Recommandation (R : validation côté service)** : le service `FreeGenerator` accepte n'importe quel string, le valide via un enum interne `Difficulty` (`FACILE = "facile"`, `MOYEN = "moyen"`, `DIFFICILE = "difficile"`), lève `FreeGenerationError("invalid_difficulty")` sinon. Le CLI mappe vers exit code 5. Cohérent avec la validation `difficulty` côté service (et non côté CLI), comme s03 pour `n`.

## 7. Fichiers anticipés

| Fichier | Action | Rôle | Bloquant pour ship ? |
|---|---|---|---|
| `backend/app/services/exercises/free_generator.py` | **Créer** | `FreeGenerator` class + Pydantic + prompts. | Oui |
| `backend/app/services/exercises/__init__.py` | Existant (vide) | — | — |
| `backend/app/core/database/models.py` | **Étendre** | Ajouter `PROBLEME` et `REDACTION` à `ExerciseType` (lignes 33-40). | Oui |
| `backend/app/core/config.py` | **Étendre** | Bloc `FREE_*` (4-5 settings) après le bloc `QCM_*` (ligne 70). | Oui |
| `backend/.env.example` | **Étendre** | 4-5 variables `FREE_*` après le bloc QCM (ligne 72). | Oui |
| `backend/app/cli.py` | **Étendre** | `_build_free_service()` + commande `generate_exercise` + helpers d'affichage. | Oui |
| `backend/tests/services/exercises/test_free_generator.py` | **Créer** | 9-12 tests (cf. § 8). | Oui |
| `backend/tests/cli/test_cli.py` | **Étendre** | Classe `TestGenerateExercise` (5-6 tests) + `_StubFreeGenerator` + `stubbed_free_service`. | Oui |
| `backend/tests/core/test_config.py` | **Étendre** | `TestFreeSettings::test_default_free_settings`. | Oui |
| `backend/tests/core/test_models.py` | **Étendre** | `TestExercise::test_exercise_creation_with_probleme_fields` + `test_exercise_creation_with_redaction_fields`. | Oui |
| `docs/architecture.md` | Pas de modif | Le schéma `exercises` est déjà correct (lignes 188-205). | — |
| `docs/research/s06-generer-probleme-redaction.md` | **Créer** (présent doc) | Ce document. | — |
| `docs/plans/s06-generer-probleme-redaction.md` | À créer en phase Plan | — | — |
| `docs/reviews/s06-generer-probleme-redaction.md` | À créer en phase Review | — | — |

### 7.1. Risques de merge avec s06b

`feature/s06b-generer-flashcards` modifie les mêmes fichiers que s06 (principalement `models.py` pour `ExerciseType`, `config.py` pour les settings, `cli.py` pour la commande). Le plan doit :

- Committer l'extension `ExerciseType` en un commit isolé au début de la branche (atomique, sans autre changement).
- Documenter dans le PR que cette PR et `s06b-flashcards` ajoutent des valeurs au même enum — le merge vers `main` créera un conflit trivial (union de deux ajouts).

## 8. Tests à prévoir

Un test par AC + bites d'anti-régression. Tous les tests utilisent `_ScriptedLlm` et `_TrackingSession` (cf. § 2.7). Les fixtures ChromaDB et SQLite sont réutilisées telles quelles.

### Tests `tests/services/exercises/test_free_generator.py`

| Test | AC couvert | Piège couvert |
|---|---|---|
| `test_probleme_statement_has_numeric_data` | AC2 | Piège 1 (LLM produit correction au lieu d'énoncé) — bite : le script LLM retourne une string sans nombre. |
| `test_probleme_expected_answer_is_substantial` | AC1, AC5 | Piège 2 (expected_answer trop mince) — bite : `expected_answer="42"`. |
| `test_probleme_grading_criteria_is_list_of_strings` | AC1, AC5 | — |
| `test_probleme_difficulty_changes_prompt` | AC1 (implicite) | Piège 4 (difficulté ignorée) — bite : assert `llm.calls[0].messages[0].content` contient « facile » pour `difficulty="facile"`. |
| `test_redaction_has_target_length_and_register` | AC3 | Piège 3 (redaction sans longueur/registre). |
| `test_redaction_expected_answer_is_substantial` | AC1, AC5 | Piège 2. |
| `test_redaction_statement_avoids_inappropriate_topics` | AC1 | Piège 6 — bite : mocker un LLM scripted qui retourne un sujet violent. |
| `test_persists_exercise_with_probleme_type` | AC4 | — |
| `test_persists_exercise_with_redaction_type` | AC4 | — |
| `test_filters_chunks_by_document_id` | AC4 (implicite) | Multi-tenancy chunks. |
| `test_raises_document_not_found_for_cross_tenant` | AC4 (implicite) | Multi-tenancy — bite identique à s03 (`llm.calls == []`). |
| `test_raises_invalid_difficulty` | — | Décision D6. |
| `test_retries_once_on_malformed_output` | AC1 (implicite) | Retry pattern. |
| `test_fails_after_max_retries` | AC1 (implicite) | Retry pattern. |

### Tests `tests/cli/test_cli.py::TestGenerateExercise`

| Test | AC couvert |
|---|---|
| `test_generate_exercise_probleme_returns_statement_expected_answer_grading_criteria` | AC1, AC2, AC5 |
| `test_generate_exercise_redaction_returns_statement_expected_answer_grading_criteria` | AC1, AC3, AC5 |
| `test_generate_exercise_json_output_is_valid_for_both_types` | AC5 |
| `test_generate_exercise_document_not_found_returns_5` | AC4 (multi-tenant) |
| `test_generate_exercise_malformed_output_returns_4` | AC1 (retry) |
| `test_generate_exercise_help_works` | — |
| `test_help_lists_generate_exercise_command` | — |

### Test cross-tenant obligatoire

Le test `test_raises_document_not_found_for_cross_tenant` (équivalent de `test_qcm_generator.py:596-637`) est **obligatoire** : il est le seul qui mord si la vérification d'ownership est retirée.

### Tests a11y / Lighthouse

Hors-scope pour s06 (story backend pur).

## 9. Risques

### Risque 1 — Complexité 3 assumée

L'AC1 (un seul CLI pour deux types d'exercices) augmente la surface par rapport à s03 (un seul type). La review s03 (ligne « diff vs plan, task by task ») a validé le pattern pour un type ; le doublement est modéré mais réel. Mitigation : option C de la décision D1 (un service public, deux internes), deux schémas Pydantic, deux prompts séparés.

### Risque 2 — Richesse du `expected_answer`

L'AC1 demande « full solution, for later grading ». La qualité perçue par l'utilisateur dépend de ce champ. Si le prompt ne cadre pas la profondeur, le LLM produit un one-liner. Mitigation : bite explicite + validation Pydantic de longueur minimale (cf. § 4.5, piège 2).

### Risque 3 — Conflit de merge avec s06b (flashcards)

Les deux worktrees touchent `models.py` (`ExerciseType`), `config.py`, `cli.py`. Si s06 et s06b sont mergées en parallèle vers `main`, conflit attendu mais résoluble trivialement. Le plan doit committer l'extension `ExerciseType` tôt et isolément (cf. § 7.1).

### Risque 4 — Sujet de rédaction inapproprié

Le LLM peut produire un sujet trop mature malgré les garde-fous. Le test bite (§ 5 piège 6) couvre les cas les plus flagrants mais n'est pas une garantie absolue. Acceptable : un professeur pourrait aussi produire un sujet borderline ; le PRD n'exige pas une modération parfaite à ce stade.

### Risque 5 — Latence (non bloquant pour le ship)

Un exercice libre prend 2x plus de tokens LLM qu'un QCM (énoncé + solution + critères vs 5 questions courtes). Latence P95 estimée à 5-10 secondes. Acceptable pour un MVP. L'observabilité (s23) pourra mesurer.

## 10. Definition of Done (spécialisé pour s06)

- Toutes les tâches du plan cochées.
- `pytest -m "not integration"` passe (≥ 200 tests attendus, après ajout de ~16 nouveaux).
- `pytest --cov=app --cov-fail-under=80` passe.
- `ruff check app tests` clean.
- AC1-AC5 tous couverts par des tests unitaires ET des tests CLI.
- **Multi-tenancy** : un test vérifie qu'un `pseudo_b` ne peut pas générer un exercice sur un document de `pseudo_a` (le LLM n'est pas appelé).
- **Test bite sur le type d'exercice** : un test vérifie que le schéma JSON diffère entre `probleme` et `redaction` (assertion sur la présence des champs spécifiques).
- **Test bite sur la richesse de `expected_answer`** : un test vérifie qu'un `expected_answer` trop court est rejeté.
- **Test bite sur la difficulté** : un test vérifie que la difficulté est reflétée dans le prompt.
- PR unique, description structurée : résumé, AC cochées, points d'attention (notamment l'extension de `ExerciseType` et le conflit potentiel avec s06b).
- Review passée (gate `Ship allowed: yes`).

## 11. Sources

### Fichiers lus (chemins absolus)

- `C:\Workspace\ktutor\.worktrees\s06-generer-probleme-redaction\docs\stories.md` (l. 188-219 pour s06 ; l. 1083 pour la référence à STORY-016 ; l. 1066 pour le split s06/s06b).
- `C:\Workspace\ktutor\.worktrees\s06-generer-probleme-redaction\docs\prd.md` (l. 34 pour les 4 types d'exercices ; l. 85 pour la Q2 sur le niveau de détail ; l. 13 pour la cible collège).
- `C:\Workspace\ktutor\.worktrees\s06-generer-probleme-redaction\docs\architecture.md` (l. 188-205 pour le schéma `exercises` cible ; l. 70-71 pour la convention `sqlalchemy.JSON` portable).
- `C:\Workspace\ktutor\.worktrees\s06-generer-probleme-redaction\docs\research\s03-generer-qcm.md` (pattern de recherche réutilisé).
- `C:\Workspace\ktutor\.worktrees\s06-generer-probleme-redaction\docs\plans\s03-generer-qcm.md` (structure de plan à dupliquer).
- `C:\Workspace\ktutor\.worktrees\s06-generer-probleme-redaction\docs\reviews\s03-generer-qcm.md` (validations, bites, lacunes à éviter).
- `C:\Workspace\ktutor\.worktrees\s06-generer-probleme-redaction\backend\app\core\database\models.py` (l. 33-40 enum ; l. 90-144 modèle `Exercise`).
- `C:\Workspace\ktutor\.worktrees\s06-generer-probleme-redaction\backend\app\services\exercises\qcm_generator.py` (pattern complet).
- `C:\Workspace\ktutor\.worktrees\s06-generer-probleme-redaction\backend\app\services\exercises\qcm_grader.py` (pattern `Attempt` — non utilisé par s06 mais utile pour s07).
- `C:\Workspace\ktutor\.worktrees\s06-generer-probleme-redaction\backend\app\services\llm\client.py` (client LLM).
- `C:\Workspace\ktutor\.worktrees\s06-generer-probleme-redaction\backend\app\services\rag\retriever.py` (l. 104-151 `get_chunks_for_document`).
- `C:\Workspace\ktutor\.worktrees\s06-generer-probleme-redaction\backend\app\services\rag\chroma_store.py` (l. 34-39 `validate_pseudo`).
- `C:\Workspace\ktutor\.worktrees\s06-generer-probleme-redaction\backend\app\cli.py` (structure CLI complète).
- `C:\Workspace\ktutor\.worktrees\s06-generer-probleme-redaction\backend\app\core\config.py` (settings QCM à étendre).
- `C:\Workspace\ktutor\.worktrees\s06-generer-probleme-redaction\backend\tests\services\exercises\test_qcm_generator.py` (test patterns).
- `C:\Workspace\ktutor\.worktrees\s06-generer-probleme-redaction\backend\tests\cli\test_cli.py` (l. 411-590 pour les stubs QCM).
- `C:\Workspace\ktutor\.worktrees\s06-generer-probleme-redaction\backend\tests\conftest.py` (fixtures PDF, image, DB).
- `C:\Workspace\ktutor\.worktrees\s06-generer-probleme-redaction\backend\.env.example` (l. 65-72 pour le bloc QCM à étendre).

### ADRs consultés

- `docs/decisions/001-monorepo-backend-frontend.md` — monorepo, deux racines.
- `docs/decisions/002-poc-rewrite-from-scratch.md` — POC Python from scratch.
- `docs/decisions/003-langgraph-supervisor.md` — superviseur LangGraph (non utilisé par s06 backend, mais contexte global).
- `docs/decisions/004-rag-isolation-by-collection.md` — convention `rag_<subject>_<pseudo>` (multi-tenant invariant).
- `docs/decisions/005-auth-rs256-rbac.md` — JWT RS256 (hors-scope pour s06).
- `docs/decisions/006-frontend-nextjs-app-router.md` — frontend (hors-scope pour s06).
- `docs/decisions/007-minio-from-s01.md` — stockage S3 (hors-scope pour s06).
- `docs/decisions/008-deepseek-ocr-2-for-vision.md` — OCR (hors-scope pour s06).
- `docs/decisions/009-seaweedfs-replaces-minio.md` — SeaweedFS (hors-scope pour s06).

### CLAUDE.md (extraits pertinents)

- § Stack Technologique — FastAPI + SQLAlchemy + ChromaDB + LLM (Minimax-M3 par défaut).
- § Multi-Tenancy — `student_pseudo` partout, ChromaDB collection naming, JWT.
- § Correction Progressive — détaillée dans CLAUDE.md, mais l'**algorithme de correction** est en s08, pas en s06. s06 ne fait que **produire** l'exercice.
- § Identité & Données Personnelles — pseudo uniquement, pas de PII.
- § Conventions de Code — snake_case fichiers, PascalCase classes, kebab-case URLs, typage obligatoire.

### Pas d'ADR nouveau requis

Les décisions s'inscrivent dans l'architecture cible existante. Si le plan tranche l'option D2.c (difficulté module le niveau de détail), aucune consigne formelle dans `docs/architecture.md` n'est contredite. Si le plan augmente la taille de `String(8192)` (cf. piège 7), un nouvel ADR « décision de schema » est nécessaire — recommandation : **ne pas** agrandir, borner côté Pydantic pour cette story.

### Questions ouvertes levées par cette recherche

- **PRD Q2 (« niveau de détail des problèmes de maths »)** : tranchée en **D2.c** (difficulté module le détail via des consignes concrètes dans le prompt). À valider au planning par l'utilisateur.

---

## 12. Re-vérification après merge de s05 (2026-08-31)

Cette recherche a été livrée par l'agent parallèle de la vague massive (s05-s08) avant que la story **s05-agent-francais-chat** ne soit mergée (squash c8c9617 sur `main`). Le pipeline me demande de **vérifier l'état actuel du code** avant d'écrire le plan, pas de me fier aux docs.

**Vérification effectuée (chemins absolus, worktree `s06-generer-probleme-redaction`, branche `feature/s06-generer-probleme-redaction`, HEAD `a593fc8`)** :

| Élément cité dans la recherche | Localisation | État | Conclusion |
|---|---|---|---|
| `ExerciseType` enum (l. 33-40) | `backend/app/core/database/models.py:33-40` | `QCM = "qcm"` seul ; commentaire mentionne « reserved for s06/s06b » | ✓ Prémisse valide — extension triviale |
| Modèle `Exercise` polymorphique (l. 90-144) | `backend/app/core/database/models.py:90-144` | `statement`, `expected_answer` (String 8192), `grading_criteria` (JSON) tous câblés nullables | ✓ Prémisse valide |
| `_extract_json_block` (l. 88-116) | `backend/app/services/exercises/qcm_generator.py:91-116` | Présent, signature stable | ✓ Pattern réutilisable |
| `_SYSTEM_PROMPT` (l. 123-146) | `backend/app/services/exercises/qcm_generator.py:123-146` | Prompt QCM présent, interdit le leak de réponse (analogue pour s06) | ✓ Inspiration valide |
| `Retriever.get_chunks_for_document` (l. 104-151) | `backend/app/services/rag/retriever.py:104-151` | `k=20` paramétrable, multi-tenant invariant respecté | ✓ Réutilisable tel quel |
| `validate_pseudo` (l. 34-39 chroma_store) | `backend/app/services/rag/chroma_store.py:27-65` | Présent, appelé à 3 endroits (l. 65, 96, 128) | ✓ Réutilisable |
| `QcmGenerator.__init__` (l. 198-225) | `backend/app/services/exercises/qcm_generator.py:198-225` | `session_factory: Callable[[], _SessionLike] | None = None` | ✓ Signature à dupliquer |
| Settings QCM (l. 67-70) | `backend/app/core/config.py:67-70` | Bloc `qcm_*` présent (4 vars) | ✓ Pattern `free_*` à dupliquer |
| `_build_qcm_service` (l. 135-160) | `backend/app/cli.py:135` | Wire-up présent | ✓ Pattern à dupliquer pour `free_service` |
| `generate_qcm` (l. 336-405) | `backend/app/cli.py:368` | Commande typer présente avec options et mapping d'exceptions | ✓ Pattern à dupliquer |
| `_ScriptedLlm`, `_TrackingSession`, `memory_db` | `backend/tests/services/exercises/test_qcm_generator.py:47-211` | Tous présents | ✓ Patterns de test réutilisables |
| Test cross-tenant `bob/alice` (l. 596-637) | `backend/tests/services/exercises/test_qcm_generator.py:613-634` | Bite test fonctionnel | ✓ Pattern obligatoire pour s06 |
| `docs/reviews/stories.md` (verdict global) | l. 89 | **`Stories ready: yes`** | ✓ s06 confirmé dans le périmètre |
| `.env.example` bloc QCM (l. 65-72) | `backend/.env.example` | 4 vars QCM commentées | ✓ Bloc `FREE_*` à ajouter |

**Impact de s05 sur s06** : **aucune régression**. Le merge de s05 (c8c9617) est purement additif — il a créé `backend/app/services/agents/{types,citations,francais_agent,supervisor}.py` et leurs tests. **Aucun de ces modules** n'est référencé par le chemin critique de s06 (modèle Exercise, retriever, QcmGenerator, LlmClient, CLI, settings, tests). Quand s06 sera rebase sur main après merge de s05, le diff restera minimal et le conflit attendu est **uniquement l'enum `ExerciseType`** (s05 ne le touche pas, mais s06b oui — déjà identifié dans la recherche, piège 5).

**Conclusion** : la recherche est **à jour** et le plan peut être écrit sans modification des prémisses. **Pas de faux premise trouvé** (aucune assertion invalidée par l'état du code).

### Note pour le plan

Le plan s06 doit ajouter une consigne en début de branche : **« Si s05 a été mergée sur main après création du worktree, rebase sur main avant de commencer (les modules s05 sont additifs, pas de conflit attendu sur le code de s06). »** Cela facilitera la review en minimisant le diff visualisé.
