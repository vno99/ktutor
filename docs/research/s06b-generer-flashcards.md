---
name: research-s06b-generer-flashcards
description: s06b-generer-flashcards — recherche de contexte pour /ks-plan
metadata:
  type: project
  story: s06b-generer-flashcards
---

# Recherche — Story s06b-generer-flashcards

> Recherche en français. Code identifiers (snake_case, PascalCase) dans leur forme d'origine. Diacritiques : « recto », « verso », « flashcards », « rappel actif », « élève ».

## 1. Rappel de la story

Source : `docs/stories.md:223-258`.

**As an** élève **I want** générer des flashcards (recto : question, verso : réponse) à partir d'un de mes documents **so that** je puisse réviser par rappel actif.

**Complexity** : **3** (LLM generation + structured output + persistence). Story splittée de l'ancien s06 pour respecter le périmètre PRD : les flashcards sont un type d'exercice à part entière, pas une option de `probleme|redaction`.

### Acceptance criteria (7 ACs)

1. CLI : `python -m ktutor.cli generate-flashcards --pseudo <p> --document-id <id> --n 10` retourne un JSON avec 10 cartes, chacune avec `front` (question), `back` (réponse), `topic` (optionnel).
2. Sortie JSON valide, parseable sans nettoyage manuel.
3. Flashcards générées **UNIQUEMENT** à partir du document spécifié (chunks filtrés par `document_id`).
4. Chaque `front` est une question autonome (pas un fragment dépendant du contexte) ; `back` est une réponse concise.
5. Deck persisté en PostgreSQL avec `pseudo`, `document_id`, `generation_date`, cards JSON.
6. Test : schéma JSON valide (`front`/`back`/`topic` présents et non vides).
7. Test : isolation multi-tenant — `pseudo_a` ne peut pas lire le deck de `pseudo_b`.

### Questions ouvertes liées (PRD)

- **Aucune** question ouverte n'est attachée à s06b dans le PRD (`docs/prd.md`). Le périmètre est verrouillé par les 7 ACs ci-dessus et la convention de nommage s03.

## 2. Code existant à réutiliser (vérifié sur le HEAD `a593fc8`)

### 2.1. `QcmGenerator` — pattern à dupliquer tel quel

`backend/app/services/exercises/qcm_generator.py` (342 lignes) implémente exactement la même forme que s06b doit implémenter. Tous les patterns structurels sont réutilisables.

- **Injection de dépendances** (lignes 208-225) : `__init__(*, llm, retriever, session_factory=None, default_questions, max_questions, max_retries, temperature)`. s06b adopte la même signature en remplaçant `default_questions`/`max_questions` par `default_cards`/`max_cards`.
- **Validation UUID + multi-tenant** (lignes 250-269) : `uuid.UUID(document_id)` puis `session.get(Document, doc_uuid)` + check `doc.student_pseudo != pseudo`. **Même message** pour not-found et cross-tenant (ligne 264-265 : « do not leak whether the document exists under another pseudo »). s06b reproduit ce pattern ligne pour ligne.
- **Récupération des chunks** (lignes 272-279) : `self._retriever.get_chunks_for_document(subject, pseudo, document_id, k=20)`. **AC3 est satisfaite par cette méthode existante** (cf. § 2.4).
- **Boucle de retry soft → strict** (lignes 290-314) : 1ère tentative avec prompt « soft » autorisant la prose, retry avec prompt « strict » qui exige UNIQUEMENT le JSON. `max_retries=1` par défaut. s06b duplique.
- **Extraction JSON robuste** (lignes 88-116, `_extract_json_block`) : helper pur, prend en charge les fences markdown ` ```json ` et un fallback regex `{...}`. Réutilisable tel quel.
- **Persistance après validation Pydantic** (lignes 318-335) : `exercise_id = uuid.uuid4()`, puis `session.add(Exercise(...))` + `commit()` dans un try/except. **Aucune persistance en cas de validation échouée** (commentaire ligne 317 : « would leak half-baked rows »).
- **Format des chunks dans le prompt** (lignes 167-176, `_format_chunks`) : `[chunk i | source: filename, chunk j] content`. Réutilisable tel quel.

### 2.2. Modèle `Exercise` polymorphique — extension requise

`backend/app/core/database/models.py:90-144` — `Exercise` est déjà conçu comme polymorphe par `type` (commentaire ligne 92-95 : « QCMs carry their full structure in `questions` (JSON); future types (probleme, redaction, flashcards) will use `statement` / `expected_answer` / `grading_criteria` »).

**MAIS** : ce commentaire ne correspond pas au besoin s06b. Les flashcards n'ont ni `statement` ni `expected_answer` (un seul coup d'œil : elles ont des **cartes**). Trois options architecturales (cf. § 6 décision D1) :

- **Option A** : ajouter une colonne `cards: JSON | None` au modèle. Propre, extensible, **collision** avec s06 sur le même fichier.
- **Option B** : réutiliser `questions` (JSON) en stockant des `{front, back, topic}`. **Sémantiquement faux** (le nom « questions » est trompeur) mais zéro migration.
- **Option C** : réutiliser `grading_criteria` (JSON) en y stockant `{"cards": [...]}`. **Tortueux** et bloque s07 qui lira `grading_criteria` pour le grading LLM.

**Recommandation** : Option A (cf. § 6 D1).

### 2.3. Enum `ExerciseType` — extension triviale requise

`backend/app/core/database/models.py:33-40` :

```python
class ExerciseType(str, enum.Enum):
    QCM = "qcm"
```

Pour s06b, **une seule ligne à ajouter** :

```python
FLASHCARDS = "flashcards"
```

**Collision confirmée** : s06 recherche indique qu'elle ajoute `PROBLEME` / `REDACTION` au même enum. Les deux PRs (s06 et s06b) modifieront ce fichier en parallèle — cf. § 5 Piège #1.

### 2.4. `Retriever.get_chunks_for_document` — déjà conforme à l'AC3

`backend/app/services/rag/retriever.py:104-151` :

- Validation UUID (ligne 124).
- `validate_pseudo(pseudo)` (ligne 128) — c'est la même règle qu'à l'upload (`ChromaStore.validate_pseudo`).
- `get_collection(subject, pseudo)` (ligne 132) — la seule façon d'accéder à un tenant.
- `collection.get(where={"document_id": document_id}, include=["documents", "metadatas"], limit=k)` (lignes 133-137) — filtre exact par document.

**AC3 est déjà implémentée.** s06b n'a rien à ajouter au retriever. Le seul branchement est d'injecter le `Retriever` dans le `FlashcardGenerator` exactement comme le `QcmGenerator`.

### 2.5. `LlmClient` — réutilisable tel quel

`backend/app/services/llm/client.py:27-34` — Protocol `LlmClient` avec unique méthode `invoke(messages: list[BaseMessage]) -> AIMessage`. Le wrapper LangChain (`build_llm_client(settings)` ligne 51) est l'implémentation prod. Le stub `_ScriptedLlm` (test_qcm_generator.py:47) est l'implémentation test.

s06b utilise exactement la même signature.

### 2.6. CLI typer — pattern à dupliquer

`backend/app/cli.py:367-405` — commande `generate_qcm` (39 lignes) est le **template exact** pour `generate_flashcards`. Différences notées :

- **Argument name** : `n` reste (`--n 10`).
- **Option subject** : `subject` reste (`--subject maths`).
- **Mapping exit codes** (lignes 382-400) : `EXIT_GENERIC_ERROR` (1), `EXIT_INVALID_PSEUDO` (5), `EXIT_QCM_DOCUMENT_NOT_FOUND` (5), `EXIT_QCM_LLM_FAILURE` (4). s06b a besoin de `EXIT_FLASHCARDS_DOCUMENT_NOT_FOUND` et `EXIT_FLASHCARDS_LLM_FAILURE` (ou réutilise ceux du QCM s'ils sont définis au niveau module — vérifier dans `upload_service.py`).
- **Sortie** : `rich.panel.Panel` (lignes 378-379) — reproduire.

Les exit codes sont définis dans `backend/app/services/rag/upload_service.py` (cf. imports `cli.py:60-65`). s06b doit vérifier que les constantes nécessaires existent ou les ajouter.

### 2.7. Conventions de test (s03, livré) — pattern à dupliquer

`backend/tests/services/exercises/test_qcm_generator.py` (727 lignes) :

- **`_ScriptedLlm`** (lignes 47-62) : pop la prochaine réponse, sinon `AIMessage(content="")`. Réutilisable tel quel.
- **`memory_db`** fixture (lignes 173-185) : SQLite in-memory + `Base.metadata.create_all`. Réutilisable tel quel.
- **`_TrackingSession`** / **`_SessionFactory`** (lignes 64-89, 187-209) : enveloppe SQLAlchemy qui observe `session.add` et `commit`. Réutilisable tel quel.
- **9 tests d'instance** (`TestQcmGenerator`, lignes 234-707) : happy path, retry sur JSON malformé, validation `n` hors bornes, multi-tenant cross-tenant, document introuvable, no session mode, etc. s06b doit couvrir les mêmes cas.

## 3. Dépendances amont

- **s01** ✅ shippé — RAG pipeline (ingestion, chunks, ChromaDB, `get_chunks_for_document`).
- **s02** ✅ shippé — `LlmClient` Protocol + `build_llm_client(settings)`.
- **s03** ✅ shippé — `Exercise` model polymorphique + `QcmGenerator` pattern.

**Pas de dépendance bloquante.** Toutes les briques sont en place.

**Dépendance transversale** : s06 (probleme/redaction) modifie le même fichier `models.py` (ajout à `ExerciseType` et possiblement `Exercise`). Le merge des deux stories doit être planifié (cf. § 5 Piège #1 et § 6 D2).

## 4. Contraintes techniques (depuis CLAUDE.md et ADR)

- **Multi-tenancy** (CLAUDE.md § Multi-Tenancy) : `student_pseudo` sur toutes les tables métier, filtrage par ce champ à chaque query. La collection ChromaDB est `rag_<subject>_<pseudo>` (ADR 004). s06b reproduit le check `doc.student_pseudo == pseudo` (qcm_generator.py:263).
- **Pydantic validation discipline** (s03 review) : la sortie LLM **DOIT** être validée par un schéma Pydantic **AVANT** la persistance. Pas d'exception : aucun `Exercise` row persisté avec un JSON non-validé.
- **Pas de général knowledge** (CLAUDE.md § LLM et agents) : les agents répondent UNIQUEMENT à partir des chunks RAG. Le system prompt s06b doit l'exiger explicitement (pattern : ligne 127-128 de qcm_generator.py : « Tu produis UNIQUEMENT des questions de QCM fondées sur les extraits de documents »).
- **Temperature** : 0 pour les tests, 0.3 par défaut en prod (CLAUDE.md). s03 utilise 0.0 par défaut dans le constructeur — s06b fait pareil (configurable via `Settings`).
- **Observabilité** (CLAUDE.md) : logs structurés JSON, LLM call logging avec prompt/completion/durée/tokens. s03 NE log PAS les appels LLM dans le `QcmGenerator` (le logging est au niveau du wrapper LangChain). s06b hérite de ce pattern.
- **i18n** (CLAUDE.md) : pas applicable au générateur (la sortie est dans la langue de l'élève, pas une string UI).
- **Accessibilité** : N/A (CLI).
- **Pas de streaming** : comme s03, s06b est un appel LLM ponctuel.

## 5. Pièges identifiés

### Piège #1 — Collision de merge avec s06 sur `ExerciseType` et `Exercise`

**Constat** : la recherche s06 (déjà livrée dans le worktree voisin `feature/s06-generer-probleme-redaction/docs/research/s06-generer-probleme-redaction.md`, 499 lignes) indique que s06 modifie le même `models.py` pour ajouter `PROBLEME` / `REDACTION` à `ExerciseType` ET étend le `Exercise` model. Si s06 et s06b sont shippées en parallèle, le merge va conflict-er sur le même bloc.

**Mitigation** : l'une des deux stories doit merger en premier, l'autre rebase. Ordre recommandé : **s06b d'abord** (modification minimale d'`ExerciseType` : 1 ligne), puis s06 rebase et ajoute ses 2 valeurs. Alternative : merger s06 d'abord (ajoute 2 valeurs + colonnes `statement`/`expected_answer`), puis s06b rebase (ajoute 1 valeur + colonne `cards`). **Le checkpoint `/ks-plan` tranche.**

### Piège #2 — Le commentaire `models.py:94` induit en erreur

Le commentaire ligne 94 dit « future types (probleme, redaction, flashcards) will use `statement` / `expected_answer` / `grading_criteria` ». **C'est faux pour les flashcards** : une flashcard n'a pas de « statement/expected_answer », elle a un recto et un verso. Le plan s06b doit ignorer ce commentaire et soit :

- ajouter une nouvelle colonne `cards: JSON | None` (propre), soit
- réutiliser `questions` (sale mais compatible avec le schéma actuel).

### Piège #3 — Le LLM peut produire `back == front` (répétition)

Le trap s06b (notes `docs/stories.md:255`) : « LLM may produce a `back` that simply repeats the `front` ». Le prompt système doit explicitement exiger que `back` **soit la réponse**, pas une reformulation. Le test d'AC6 doit inclure un cas « back == front » qui détecte cette régression.

### Piège #4 — Longueur des cartes (AC4 « concise answer »)

L'AC4 exige `back` concis. Sans borne, le LLM peut écrire 3 phrases. La story propose 200 chars max (notes `docs/stories.md:256`). Le schéma Pydantic doit imposer `Field(max_length=200)` sur `front` ET `back`. Le test AC4 inclut un cas « back de 500 chars » qui doit lever une `ValidationError` et déclencher le retry.

### Piège #5 — Doublons de cartes dans un même deck

L'AC6 exige « front, back, topic fields present and non-empty ». Elle ne vérifie pas l'unicité de `front`. Le LLM peut produire 2 cartes quasi-identiques. Le plan s06b doit ajouter une validation post-Pydantic (dans le service, pas le schéma) qui détecte les `front` dupliqués et lève une erreur de retry.

### Piège #6 — Le LLM peut générer des cartes non-ancrées dans le document (violation AC3)

Le prompt doit être plus strict que pour le QCM : « each card MUST be answerable from the chunks below ONLY ». Le test AC3 doit injecter des chunks vides et vérifier que le service refuse (erreur `no_chunks` — déjà implémentée par le pattern s03 ligne 275-279). Le test doit aussi injecter des chunks non-vides et vérifier que la sortie est bornée (impossible de tester l'ancrage factuel sans un LLM réel, mais on peut vérifier que le système prompt est bien envoyé via un mock LLM qui enregistre les messages).

### Piège #7 — Le `default_questions=5` est le défaut ; s06b doit introduire `default_cards=10`

L'AC1 fixe `--n 10` (10 cartes) comme exemple. Le défaut de s03 est 5 questions. Pour s06b, le défaut doit être 10 cartes (cohérent avec l'AC1). Le plan s06b doit ajouter une variable d'env `FLASHCARDS_DEFAULT_N=10` et `FLASHCARDS_MAX_N=30` (le max de 30 vient de `docs/stories.md:253`).

### Piège #8 — Le system prompt QCM force un JSON `{"questions": [...]}`. Le s06b doit forcer `{"cards": [...]}`

C'est trivial mais le diff est facile à oublier. Le plan doit inclure un system prompt dédié avec :

```json
{"cards": [{"front": "...", "back": "...", "topic": "..."}, ...]}
```

Et le strict prompt du retry doit être encore plus explicite sur la forme.

### Piège #9 — Le `Back` peut contenir un renvoi au document (« voir page 3 »)

Le LLM peut produire « voir section 2.1 du document » comme back, ce qui viole l'AC4 (« self-contained question »). Le prompt doit exiger un back **autonome** (sans référence externe). Test : injecter un mock LLM qui produit `{front: "Quelle est la dérivée de x² ?", back: "Voir section 2.3", topic: ""}` et vérifier que la validation post-Pydantic rejette.

### Piège #10 — Le `topic` est optionnel dans l'AC1 mais obligatoire-non-vide dans l'AC6

L'AC1 dit « `topic` (string, optional) ». L'AC6 dit « `front`, `back`, `topic` fields present and non-empty ». **Contradiction** : si `topic` est optionnel, il peut être `None` ; l'AC6 exige non-empty. Le plan s06b tranche : **`topic: str | None` accepté** (None ou string non-vide), test AC6 vérifie les 2 cas (`topic=None` et `topic="algèbre"`).

## 6. Décisions d'architecture à prendre

### D1 — Schéma de persistance : nouvelle colonne `cards` ou réutilisation

**Question** : où stocker le deck de flashcards dans `Exercise` ?

- **Option A** (recommandée) : ajouter `cards: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)`. Propre, sémantique correcte, accepte `{front, back, topic}`. Inconvénient : migration légère + collision avec s06.
- **Option B** : réutiliser `questions` (JSON) en stockant des `{front, back, topic}`. Zéro migration. Inconvénient : sémantiquement faux (les « questions » QCM ont `options`/`correct_index`).
- **Option C** : réutiliser `grading_criteria` en y stockant `{"cards": [...]}`. Tordu, bloque s07.

**Recommandation** : **Option A**. Justification : (1) `Exercise` est déjà polymorphe par `type`, le schéma doit suivre la même logique (1 colonne = 1 type d'exercice) ; (2) Pydantic `FlashcardDeck` valide la structure, le code applicatif lit `exercise.cards` (clair) ; (3) le coût de la migration est nul en dev (`Base.metadata.create_all` ré-applique tout).

### D2 — Ordre de merge s06 vs s06b

**Question** : quelle story merge en premier ?

- **Option A** : s06b d'abord. Modifications minimales (`ExerciseType += FLASHCARDS`, `Exercise += cards`). s06 rebase.
- **Option B** : s06 d'abord. Modifications plus lourdes (3 valeurs enum, 3 colonnes statement/expected_answer/grading_criteria). s06b rebase.
- **Option C** : fusionner dans une PR commune. Interdit par le pipeline (1 story = 1 PR).

**Recommandation** : **Option A**. Justification : s06b est plus simple, plus rapide à shipper, et découple le risque (si s06b review fail, s06 n'est pas bloqué).

### D3 — Validation post-Pydantic : déduplication des fronts

**Question** : que faire si le LLM produit 2 cartes avec un `front` quasi-identique ?

- **Option A** : rejeter + retry (le LLM tente à nouveau avec un prompt qui insiste sur la diversité).
- **Option B** : dédupliquer silencieusement (garder la première).
- **Option C** : rejeter définitivement (le deck est invalide).

**Recommandation** : **Option A**. Justification : conforme au pattern s03 (retry on malformed_output), préserve l'intention pédagogique (« 10 cartes DIFFÉRENTES »).

### D4 — Longueur max des faces (200 chars)

**Question** : borner à 200 chars (notes `docs/stories.md:256`) ou plus ?

- **Option A** : 200 chars (notes stories).
- **Option B** : 280 chars (limite tweet, plus permissive).

**Recommandation** : **Option A** (200). Justification : la story le fixe explicitement ; 200 chars est largement suffisant pour une réponse concise. Le Pydantic `Field(max_length=200)` rejette à la validation.

### D5 — Default `n` et `max n`

**Question** : quels defaults ?

- **Option A** : `default_n=10` (cohérent AC1), `max_n=30` (cohérent stories.md:253).
- **Option B** : aligner sur QCM (default=5, max=20).

**Recommandation** : **Option A**. Justification : la story fixe explicitement 10/30 ; ne pas réutiliser les valeurs QCM qui sont inadaptées (un deck de 5 flashcards est trop court pour du rappel actif).

### D6 — Le `topic` : vraiment optionnel ?

**Question** : `topic` est-il `str | None` ou toujours présent ?

**Recommandation** : **`str | None`**. Justification : l'AC1 dit « (string, optional) » et l'AC6 dit « present and non-empty » — la lecture cohérente est « si présent, non-vide ». Le test AC6 couvre les 2 cas. Si le LLM produit `topic=""`, le validateur post-Pydantic le coerce à `None`.

## 7. Fichiers anticipés

| Fichier | Action | Justification |
| --- | --- | --- |
| `backend/app/services/exercises/flashcard_generator.py` | **new** | Le service lui-même (pattern s03). ~200 lignes attendues (QcmGenerator = 342). |
| `backend/app/core/database/models.py` | **extend** | Ajouter `FLASHCARDS` à `ExerciseType` (1 ligne) + colonne `cards` (D1). |
| `backend/app/core/config.py` | **extend** | Ajouter bloc `FLASHCARDS_*` (3-4 vars) — pattern lignes 66-70. |
| `backend/.env.example` | **extend** | Ajouter les vars `FLASHCARDS_*` commentées. |
| `backend/app/cli.py` | **extend** | Ajouter `generate_flashcards` (~40 lignes, pattern `generate_qcm` lignes 367-405). |
| `backend/app/services/rag/upload_service.py` | **extend** (mineur) | Vérifier que `EXIT_OK`/`EXIT_GENERIC_ERROR`/`EXIT_INVALID_PSEUDO`/`EXIT_STORAGE_FAILURE` couvrent les besoins ; sinon ajouter `EXIT_FLASHCARDS_DOCUMENT_NOT_FOUND` (5) et `EXIT_FLASHCARDS_LLM_FAILURE` (4). |
| `backend/tests/services/exercises/test_flashcard_generator.py` | **new** | 9+ tests d'instance (pattern s03). |
| `backend/tests/cli/test_cli.py` | **extend** | Tests pour `generate_flashcards` (5-6 tests, pattern `TestSubmitQcm` lignes 598-811). |
| `backend/tests/core/test_models.py` | **extend** (mineur) | Test que `Exercise.cards` est nullable par défaut (pattern `TestAttemptModel.answer_text`). |

**Aucun nouveau service transversal** (pas d'agent, pas de supervisor, pas d'API). C'est purement un nouveau générateur + une nouvelle commande CLI.

## 8. Tests à prévoir (un par AC, plus l'isolation)

| AC | Test | Fixture |
| --- | --- | --- |
| AC1 | Happy path : 10 cartes générées | `_ScriptedLlm([_good_flashcards_json(10)])` + `memory_db` + `Retriever` stub |
| AC2 | Le retour est un JSON valide parseable | Idem + `json.loads(result.raw)` ne lève pas |
| AC3 | Chunks filtrés par `document_id` | Stub `Retriever.get_chunks_for_document` qui vérifie les args (`subject`, `pseudo`, `document_id`) et retourne les chunks du fixture |
| AC4 | `back` concise (≤ 200 chars) | `_ScriptedLlm` qui produit `{back: "x"*250}` → `ValidationError` → retry |
| AC4 bis | `front` self-contained (pas de « voir p. 3 ») | `_ScriptedLlm` qui produit `{back: "voir section 2"}` → rejet post-Pydantic |
| AC5 | Deck persisté en PostgreSQL | `memory_db` + vérification `session.add(Exercise(...))` a été appelé avec `type=ExerciseType.FLASHCARDS` et `cards=[...]` |
| AC6 | Schéma JSON valide (front, back, topic non-vides) | Multi-cas : `topic=None` accepté, `topic=""` rejeté, `front=""` rejeté |
| AC6 bis | Pas de doublons de `front` | `_ScriptedLlm` qui produit 2 cartes avec le même `front` → retry |
| AC7 | Isolation multi-tenant | Stub `Retriever` qui retourne [] quand `pseudo != doc.student_pseudo` → `FlashcardGenerationError(kind="document_not_found")` |
| AC7 bis | Document introuvable | `session.get(Document, ...)` retourne None → `FlashcardGenerationError(kind="document_not_found")` |
| **Bonus** | No session mode (génération sans persistance) | Constructeur avec `session_factory=None` |
| **Bonus** | Retry sur JSON malformé | `_ScriptedLlm(["not json", "still not json"])` → `FlashcardGenerationError(kind="malformed_output")` |
| **Bonus** | `n` hors bornes | `generate(pseudo, subject, doc_id, n=50)` → `FlashcardGenerationError(kind="invalid_input")` |
| **Bonus** | UUID invalide | `generate(pseudo, subject, "not-a-uuid", n=10)` → `FlashcardGenerationError(kind="document_not_found")` |

**Couverture totale** : 12+ tests, soit plus que s03 (9). Justifié par : 1 AC de plus (AC4 « self-contained » vs la simple longueur QCM), 1 piège de plus (Piège #5 doublons), 1 schéma différent (cards vs questions).

## 9. Risques

- **R1 — Complexité 3** (LLM generation + structured output + persistence). Cohérent avec s03. Risque connu, mitigation par le pattern s03. **Probabilité faible, impact modéré**.
- **R2 — Collision de merge avec s06** (Piège #1). **Probabilité forte** (les deux stories étendent `models.py` et `cli.py`). Mitigation : D2 — s06b merge en premier. **Probabilité forte, impact modéré** (rebase de s06).
- **R3 — Le LLM ignore la consigne « back autonome »** (Piège #9). Probabilité moyenne, impact modéré (la carte est inutilisable). Mitigation : validation post-Pydantic + retry explicite.
- **R4 — Le LLM produit des cartes hors sujet** (Piège #6). Probabilité moyenne (mitigation par le prompt strict). Impact : pollution du deck. Mitigation : `no_chunks` + retry avec prompt renforcé.
- **R5 — Le LLM produit des cartes plus longues que 200 chars** (Piège #4). Probabilité forte. Impact : la validation Pydantic rejette → retry. Si le LLM produit toujours > 200 chars après retry, c'est `malformed_output` (échec total). **Mitigation acceptable** : c'est exactement le comportement souhaité (un deck avec des cartes de 500 chars n'est pas une flashcard).
- **R6 — Le commentaire trompeur de `models.py:94`** (Piège #2). Probabilité forte si le plan suit aveuglément le commentaire. Mitigation : le plan doit ignorer le commentaire et appliquer D1 (nouvelle colonne `cards`).
- **R7 — Conflit sémantique AC1 « topic optional » vs AC6 « topic non-empty »** (Piège #10). Probabilité forte, impact test (un test naïve échoue). Mitigation : D6 — `topic: str | None` + le test couvre les 2 cas.

## 10. Definition of Done (spécialisé s06b)

- Une PR unique, description structurée (résumé, AC cochées, points d'attention sur la collision s06).
- Tests passants : `pytest --cov=app --cov-fail-under=80 -m "not integration"` ≥ 12 nouveaux tests passants.
- Pas de régression sur les 189 tests existants (s01-s04 + phase 1 E2E).
- **Multi-tenancy vérifié** : 1 test cross-tenant explicite (AC7) + 1 test document-not-found (Piège AC7 bis).
- **L'extension `ExerciseType` est rétro-compatible** : QCM continue de fonctionner sans modification.
- **L'extension `Exercise.cards` est rétro-compatible** : les anciens QCM ont `cards=None` (non-nullable seulement pour `type=FLASHCARDS`).
- **Le diff est minimal** : 1 nouveau service, 1 nouvelle commande CLI, 2 lignes de modèle (1 enum + 1 colonne), 4 lignes de config, 1 fichier de test.
- Review passée : `docs/reviews/s06b-generer-flashcards.md` termine par `Max severity: <...>` et `Ship allowed: yes`.
- **Pas de modification de `retriever.py`** (la méthode `get_chunks_for_document` est déjà conforme).
- **Pas de modification du LLM client**.
- **Pas de migration Alembic** (le `Base.metadata.create_all` ré-applique tout en dev/CI, comme s04 l'a documenté).

## 11. Sources (vérifiées sur le HEAD `a593fc8`)

### Code lu

- `backend/app/services/exercises/qcm_generator.py` (342 lignes) — pattern principal, ligne par ligne.
- `backend/app/services/exercises/qcm_grader.py` (281 lignes) — conventions error/result.
- `backend/app/core/database/models.py` (195 lignes) — `Exercise` polymorphique, `ExerciseType`, `Document`.
- `backend/app/services/rag/retriever.py` (151 lignes) — `get_chunks_for_document` (AC3).
- `backend/app/services/llm/client.py` (80 lignes) — `LlmClient` Protocol, `build_llm_client`.
- `backend/app/services/rag/upload_service.py` — exit codes, conventions UploadError/UploadErrorKind.
- `backend/app/cli.py` (529 lignes) — commande `generate_qcm` (lignes 367-405), imports, exit codes.
- `backend/app/core/config.py` — bloc `QCM_*` (lignes 66-70), pattern à étendre.
- `backend/tests/services/exercises/test_qcm_generator.py` (727 lignes) — fixtures, tests, pattern à dupliquer.

### Spécification lue

- `docs/stories.md:223-258` — story s06b complète (AC, dépendances, agentic notes).
- `docs/reviews/stories.md` — split de l'ancien s06 pour respecter le périmètre PRD.
- `docs/prd.md` — périmètre flashcards (vérification : bien listé comme type d'exercice).
- `docs/architecture.md` — schéma `exercises` polymorphe.
- `CLAUDE.md` § Multi-Tenancy, § LLM et agents, § Tests.

### Recherche voisine (collision)

- `.worktrees/s06-generer-probleme-redaction/docs/research/s06-generer-probleme-redaction.md` (499 lignes) — confirme que s06 modifie `models.py` (ajout à `ExerciseType` + colonnes `statement`/`expected_answer`/`grading_criteria`). Source du Piège #1.

### ADR consultés

- `docs/decisions/004-rag-isolation-by-collection.md` — convention `rag_<subject>_<pseudo>` (réutilisée, pas modifiée).
- `docs/decisions/003-langgraph-supervisor.md` — non applicable à s06b (pas d'agent, pas de supervisor).
- `docs/decisions/002-poc-rewrite-from-scratch.md` — confirme la portée du POC.

### Aucun ADR nouveau requis

- Pas de nouvelle décision architecturale (le polymorphisme d'`Exercise` est déjà documenté dans `models.py:92-95`).
- Pas de nouvelle dépendance.
- Pas de nouveau service transversal.

## 12. Pré-requis pour passer à `/ks-plan`

Toutes les questions ouvertes de § 5 ont une recommandation (§ 6). Les blocages éventuels sont :

- **D2 (ordre de merge s06 vs s06b)** : trancher au checkpoint `/ks-plan`. Recommandation = s06b d'abord.
- **D1 (nouvelle colonne `cards` vs réutilisation)** : trancher au checkpoint. Recommandation = nouvelle colonne.

Une fois ces 2 décisions tranchées, le plan s06b est faisable en moins de 10 tâches (conformément à la skill `agentic-stories` § « implementable in one cycle »).

---

## 13. Re-vérification après merges s05 et s06 (2026-09-01)

Cette recherche a été livrée par l'agent parallèle de la vague massive (s05-s08) avant que les stories **s05-agent-francais-chat** (squash c8c9617, PR #6) et **s06-generer-probleme-redaction** (squash f928d65, PR #7) ne soient mergées sur `main`. Le pipeline me demande de **vérifier l'état actuel du code** avant d'écrire le plan, pas de me fier aux docs.

**État au moment de cette re-vérification** :

- Branche `feature/s06b-generer-flashcards` : HEAD = `a593fc8` (= main **avant** s05 et s06). Le worktree local n'a pas le code de s05/s06.
- `main` (remote) : `f928d65` (= `a593fc8` + s05 + s06 squashés).
- Le plan s06b doit donc commencer par un **rebase sur `origin/main`** (étape 0 du plan).

**Vérification des éléments cités par la recherche, sur le code LOCAL de la branche s06b (HEAD `a593fc8`)** :

| Élément cité | Localisation | État local | Conformité à la recherche |
|---|---|---|---|
| `ExerciseType` (l. 33-40) | `backend/app/core/database/models.py:33-40` | `QCM = "qcm"` seul | ✓ Prémisse valide localement. **Invalide après rebase** : s06 a déjà ajouté `PROBLEME` et `REDACTION`. |
| `Exercise` polymorphique (l. 90-144) | `backend/app/core/database/models.py:90-144` | `statement`, `expected_answer`, `grading_criteria` nullables | ✓ Valide localement. **Changement après rebase** : s06 a utilisé ces colonnes, aucune nouvelle colonne. |
| `_extract_json_block` (l. 88-116) | `backend/app/services/exercises/qcm_generator.py:91-116` | Privé dans qcm_generator.py | ✓ Valide localement. **Changement après rebase** : s06 l'a extrait vers `_parsing.py` (mutualisé). Le plan s06b doit importer depuis `_parsing.py`, pas redéfinir. |
| `QcmGenerator` (l. 198-225) | `backend/app/services/exercises/qcm_generator.py:198-225` | Pattern constructeur stable | ✓ Valide. Réutilisable tel quel. |
| `Retriever.get_chunks_for_document` (l. 104-151) | `backend/app/services/rag/retriever.py:104-151` | `k=20` paramétrable, multi-tenant invariant | ✓ Valide. AC3 déjà implémentée. |
| `LlmClient` Protocol (l. 27-34) | `backend/app/services/llm/client.py:27-34` | `invoke(messages)` stable | ✓ Valide. |
| `cli.py` exit codes (l. 336-337) | `backend/app/cli.py:336-337` | `EXIT_QCM_DOCUMENT_NOT_FOUND=5`, `EXIT_QCM_LLM_FAILURE=4` | ✓ Valide. **Reutilisables** pour s06b (le commentaire note l'option de dupliquer, mais on peut mutualiser : la recherche dit « vérifier que les constantes couvrent les besoins »). |
| `cli.py` `generate_qcm` (l. 367-405) | `backend/app/cli.py:367-405` | Pattern typer complet | ✓ Valide. À dupliquer pour `generate_flashcards`. |
| Tests s03 patterns (727 lignes) | `backend/tests/services/exercises/test_qcm_generator.py` | `_ScriptedLlm`, `memory_db`, `_TrackingSession`, `_SessionFactory` | ✓ Valide. Réutilisables tels quels. |
| `docs/reviews/stories.md` verdict | l. 89 | `Stories ready: yes` | ✓ s06b confirmé dans le périmètre. |

**Impact des merges récents sur s06b** :

1. **s05 (c8c9617)** : purement additif (nouveaux fichiers `agents/{types,citations,francais_agent,supervisor}.py`). **Aucun impact** sur le code référencé par s06b. Conflit de rebase : aucun attendu.

2. **s06 (f928d65)** : modifications significatives à intégrer :
   - `ExerciseType` étendu avec `PROBLEME` et `REDACTION`. **s06b doit ajouter `FLASHCARDS` au résultat** (union de 3 valeurs). Conflit trivial.
   - `free_generator.py` créé (nouveau service). **Aucun impact** sur s06b (s06b crée son propre service `flashcard_generator.py`).
   - `_parsing.py` créé (nouveau module privé). **s06b doit importer `extract_json_block` depuis `_parsing.py`**, pas redéfinir ni dupliquer. Évite la divergence.
   - `cli.py` étendu avec `_build_free_service`, `generate_exercise`, helpers, et nouveau mapping d'exceptions. **s06b doit juste ajouter `generate_flashcards`** à côté — pas de conflit.
   - `tests/services/exercises/test_free_generator.py` créé. **Aucun impact** sur s06b (s06b crée son propre `test_flashcard_generator.py`).
   - `tests/cli/test_cli.py` étendu avec `TestGenerateExercise`. **Aucun impact** sur s06b (s06b ajoute `TestGenerateFlashcards`).
   - `tests/core/test_models.py` étendu avec 2 tests `PROBLEME`/`REDACTION`. **s06b ajoute 1 test `FLASHCARDS`**.
   - `tests/core/test_config.py` étendu avec `TestFreeSettings`. **s06b ajoute `TestFlashcardSettings`**.

**Recommandations pour le plan s06b** :

- **Étape 0 obligatoire** : `git fetch origin && git rebase origin/main`. s05 + s06 mergés, le code local n'est plus à jour. Conflits attendus : `models.py` (ajout `FLASHCARDS` après `PROBLEME`/`REDACTION`), `cli.py` (ajout `generate_flashcards` après `generate_exercise`). Tous triviaux.
- **Réutiliser `_parsing.py`** créé par s06 (import `from app.services.exercises._parsing import extract_json_block`), pas dupliquer. Cela aligne s06b sur la convention s06.
- **L'ordre de merge** est désormais **imposé** : s06 a déjà mergé. s06b ne peut pas merger en premier (c'est trop tard). La collision `ExerciseType` reste triviale (s06 a ajouté 2 valeurs, s06b ajoute 1 valeur). **D2 devient obsolète** : « s06b d'abord » n'est plus possible. Le rebase suffit.
- **Constatation importante** : le commentaire `models.py:94` cité en Piège #2 (« future types will use `statement`/`expected_answer`/`grading_criteria` ») est désormais **encore plus faux** : s06 utilise effectivement `statement`/`expected_answer`/`grading_criteria`, mais s06b ne le fera pas (cartes ≠ énoncé). s06b a besoin d'une **nouvelle colonne `cards`**. La décision **D1 = Option A** (nouvelle colonne) est confirmée par l'évolution du code.

**Conclusion** : la recherche est **solide** et le plan s06b peut être écrit sans modification des prémisses. **Aucun faux premise trouvé**. Le rebase en étape 0 est la seule action nouvelle par rapport à la recherche initiale (qui supposait merger en premier).
