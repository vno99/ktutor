---
name: research-s05-francais
description: s05-agent-francais-chat — research output for /ks-plan
metadata:
  type: project
  story: s05-agent-francais-chat
---

# Research — Story s05-agent-francais-chat

## Rappel de la story

Source : `docs/stories.md` (Phase 2 — MVP), extrait des lignes 155-186.

**As an** élève **I want** poser une question sur un cours de français **so that** j'obtiens une réponse qui s'appuie sur mes documents de français.

**Complexity** : 3 (Second agent + supervisor + collection ChromaDB séparée).

### Acceptance criteria (6 ACs)

1. Une matière français est sélectionnable : `--subject francais` fonctionne dans la commande CLI `chat`.
2. L'agent français utilise une collection ChromaDB dédiée `rag_francais_<pseudo>`.
3. Un superviseur LangGraph route la question vers l'agent maths ou français selon le drapeau `--subject` (ou, dans une itération future, selon le contenu de la question).
4. La réponse cite des sources issues des documents français.
5. Un test vérifie qu'une question française SANS document français uploadé renvoie le message « pas de document » (pas de fallback vers les maths).
6. Un test vérifie que les documents de `pseudo_a` dans `rag_francais_a` ne sont PAS récupérables depuis `rag_francais_b`.

## Code existant à réutiliser

Toute la mécanique de l'agent maths (s02) est réutilisable telle quelle pour l'agent français. L'invariant multi-tenant (ADR 004) est déjà verrouillé au niveau `Retriever` et `ChromaStore`. Aucun changement aux modules transverses n'est requis.

### Modules à réutiliser sans modification

| Fichier | Rôle pour s05 | Référence |
|---|---|---|
| `backend/app/services/rag/retriever.py` | `Retriever.query(subject, pseudo, question, k)` déjà multi-tenant. Appel à `validate_pseudo` + `chroma_store.get_collection(subject, pseudo)`. Aucune modif requise — passer `subject="francais"` fonctionne par construction. | `retriever.py:43-102` |
| `backend/app/services/rag/chroma_store.py` | `collection_name(subject, pseudo)` (l.35) retourne `f"rag_{subject}_{pseudo}"` — passe `"francais"` directement. `get_collection` valide le pseudo et appelle `get_or_create_collection`. | `chroma_store.py:35-67` |
| `backend/app/services/rag/embeddings.py` | `FastEmbedProvider` (défaut) et `OpenAIEmbeddingProvider` partagent le même protocole `EmbeddingProvider.embed_documents`. Le retriever embedde la question via cette interface, donc le passage au français n'implique pas de reconfiguration. | `embeddings.py:17-71` |
| `backend/app/services/llm/client.py` | `LlmClient` Protocol + `build_llm_client(settings)` (factory). Le client est agnostique au sujet. | `client.py:26-79` |
| `backend/app/core/config.py` | `Settings.chat_top_k`, `chat_temperature`, `chat_no_document_message`, `llm_provider`, `llm_model`, `llm_base_url` couvrent déjà tout ce dont l'agent français a besoin. | `config.py:49-64` |
| `backend/app/services/rag/upload_service.py` | L'indexation d'un PDF français écrit dans `rag_francais_<pseudo>` automatiquement (le pipeline prend `subject` en argument et le passe à `_to_chroma_dict` via `get_collection(subject, pseudo)` à la ligne 171). Aucun changement. | `upload_service.py:171,288-293` |
| `backend/app/services/storage/minio_client.py` | S3 — sujet-agnostique. | intact |
| `backend/app/core/database/models.py` | `Subject` enum (`MATHS`, `FRANCAIS`) déjà défini (l.26-30) et utilisé par `Document.subject` (l.63). | `models.py:26-30,63` |

### Modules à dupliquer (clone avec un prompt système différent)

| Fichier | Devient | Justification |
|---|---|---|
| `backend/app/services/agents/maths_agent.py` | `backend/app/services/agents/francais_agent.py` | Mêmes dépendances injectées (`llm`, `retriever`, `top_k`, `no_document_message`), même signature `ask(subject, pseudo, question) -> ChatResult`. Seuls changent : `SYSTEM_PROMPT` (registre littéraire vs technique) et `_build_user_prompt` (optionnel — la structure peut être identique). Le module `ChatResult` et `SourceCitation` sont partagés (à promouvoir). |

### Modules à extraire (factorisation pendant s05)

| Source | Cible | Justification |
|---|---|---|
| `SourceCitation`, `ChatResult` (définis dans `maths_agent.py:51-62`) | `backend/app/services/agents/types.py` (nouveau) | Les deux agents partagent le même format de sortie. Évite l'import circulaire `francais_agent` → `maths_agent` pour les types. |
| `CITATION_FORMAT`, `CITATION_RE` (`maths_agent.py:26-30`) | `backend/app/services/agents/citations.py` (nouveau) | Le format de citation est transversal aux agents (et sera réutilisé par les générateurs d'exercices en s06/s06b pour leurs propres sources RAG). |
| `SYSTEM_PROMPT` (chaîne française) | Constante dans `francais_agent.py` (ne pas factoriser en core) | Le prompt est spécifique à la matière — la factorisation au niveau core ajouterait du couplage sans bénéfice. |

### Modules à créer pour le superviseur

| Fichier | Rôle | Justification |
|---|---|---|
| `backend/app/services/agents/supervisor.py` | `SubjectAgent` Protocol + `MathsSubjectAgent` (wrapping `MathsAgent`) + `FrenchSubjectAgent` (wrapping `FrancaisAgent`) + `SubjectSupervisor.ask(subject, pseudo, question) -> ChatResult` | L'AC3 demande explicitement un superviseur. Pour le scope de s05 (routage par `--subject`), c'est un **dispatcher typé** — pas un graphe LangGraph. Voir § Décisions d'architecture. |
| `backend/app/services/agents/__init__.py` | Étendu pour exposer `SubjectSupervisor` et le `Subject` literal (déjà couvert par `core.database.models.Subject`, mais à ré-exporter au niveau agent pour les imports des consommateurs). | `agents/__init__.py:1-6` (vide actuellement) |
| `backend/app/cli.py` | Extension : la commande `chat` route via `SubjectSupervisor` au lieu d'instancier `MathsAgent` directement. | `cli.py:113-132,297-323` |
| `backend/app/core/config.py` | Ajout d'un mapping optionnel `subject_prompts` (à trancher — voir § Décisions). Pour l'instant, aucune variable d'env nouvelle n'est nécessaire. | — |

### Patterns et conventions à respecter (déjà appliqués en s02)

- **Injection par constructeur** : `_build_chat_service()` dans `cli.py:113-132` passe `llm`, `retriever`, `top_k`, `no_document_message`. Le superviseur prend les mêmes dépendances et dispatche.
- **`_XxxLike` Protocol** : `_RetrieverLike` (maths_agent.py:65-69) — à dupliquer pour l'agent français ou à promouvoir dans `agents/types.py`.
- **Sortie `ChatResult` Pydantic** : `answer: str`, `sources: list[SourceCitation]`. Stable depuis s02. Le superviseur retourne ce même type.
- **Stub pattern pour tests CLI** : `_StubChatService` dans `test_cli.py:257-281` — le superviseur aura droit au même pattern (`_StubSubjectSupervisor`).
- **`FakeListChatModel` + `_CapturingLlm`** : pour stubber le LLM et inspecter les messages. Pattern s02 (`test_maths_agent.py:59-68`).
- **EphemeralClient ChromaDB** : `chromadb.EphemeralClient()` pour les tests (cf. `test_maths_agent.py:81-99`, `_chroma()` helper).
- **Test cross-tenant au niveau agent ET au niveau retriever** : la redondance est volontaire (cf. review s02 « the central invariants are real, not decorative »).

## Dépendances amont

### Ce que s01-s04 fournissent et que s05 consomme

- **s01** : pipeline d'upload sujet-agnostique qui écrit dans `rag_<subject>_<pseudo>`. Le `subject="francais"` est déjà valide (enum `Subject.FRANCAIS` à `models.py:30` et accepté par le `typer.Option` du CLI upload à `cli.py:210`).
- **s02** : `MathsAgent`, `Retriever`, `LlmClient`, commande CLI `chat` (sert de template exact pour le câblage de l'agent français et du superviseur).
- **s03** : preuve que `Retriever.get_chunks_for_document(subject, pseudo, document_id, k)` (l.104-151) marche — pas nécessaire pour s05 mais confirme que la couche retrieval est stable.
- **s04** : preuve que les commandes CLI peuvent étendre la matrice d'exit codes sans casse (`EXIT_*_NOT_FOUND = 5` pour cross-tenant, `EXIT_*_BAD_INPUT = 4` pour input malformé).

### Ce qui N'est PAS encore construit et qui ne bloque PAS s05

- **`langgraph` state graphs réels** : la story AC3 dit « superviseur LangGraph » mais l'AC précise « routes the question based on the `--subject` flag (or, in a follow-up, by question content) ». L'ADR 003 mandate LangGraph pour le superviseur multi-agents au long cours. **Pour s05, le routage est déterministe par flag** (un `dict` ou un `if/elif` typé) — pas besoin d'instancier un `StateGraph` ou un `Pregel`. Voir § Décisions.
- **Historique des conversations** : `Conversation` / `Message` arrivent en s09 (API) et s19 (endpoint). Le chat reste one-shot en s05.
- **Streaming SSE** : arrive en s09. Le chat s05 reste one-shot (`Panel` rich + exit 0).
- **JWT et middleware RBAC** : arrivent en s12-s15. Le CLI s05 reste sur `--pseudo` trusted (même contrat que s02-s04).
- **Validation de `subject` côté CLI** : la story AC1 dit « `--subject francais` works » mais `cli.py:300` accepte déjà n'importe quel `str` (le `typer.Option` n'a pas de `click.Choice`). **Comportement actuel** : si l'utilisateur passe `--subject histoire`, le code va tenter `get_collection("histoire", pseudo)` → création d'une collection `rag_histoire_<pseudo>` (silencieusement, par `get_or_create_collection`). **Décision à prendre** : faut-il rejeter en amont les sujets hors `{maths, francais}` ? Réponse dans § Décisions (recommandation : **oui**, à `CLI` niveau, lever `typer.BadParameter`).

## Contraintes techniques

### Multi-tenancy (ADR 004 — verrouillé)

- Convention `rag_<subject>_<pseudo>` (lettres minuscules). L'agent français utilise `subject="francais"` et hérite automatiquement de la convention.
- `validate_pseudo` (regex `^[a-zA-Z0-9_]{3,32}$`) est appelé au début de `Retriever.query` (l.74) et `get_collection` (l.65) — l'agent français n'a rien à vérifier de plus.
- Le test d'isolation cross-tenant français est **identique au test maths** mais avec `subject="francais"`. Le pattern `_seed` (`test_maths_agent.py:85-99`) est directement réutilisable.
- **Invariant clé** (à verrouiller dans le test du superviseur) : un agent français ne doit JAMAIS appeler `retriever.query("maths", ...)`, et vice versa. Le test bite à injecter un retriever qui enregistre ses appels et à vérifier que `subject` dans `calls` est `"francais"` (ou `"maths"`).

### ChromaDB persistence

- `chromadb.PersistentClient` avec `path=settings.chroma_persist_directory` (`cli.py:92`). Aucun changement.
- Le mode `EphemeralClient` est utilisé dans les tests (`test_maths_agent.py:82`). Le superviseur et l'agent français l'utilisent également.

### LangGraph supervisor pattern (ADR 003)

- **ADR 003** acte `LangGraph + langgraph-supervisor` pour orchestrer plusieurs agents. Il acte aussi : « Pour le POC, le routage est explicite par matière (le client envoie `--subject maths` ou `/subject=francais`). Le routage par contenu est une itération future (s05 trap). » (l.23-25).
- **Constat runtime** : `langgraph` 1.x est installé (`langgraph.pregel.Pregel` importable), mais `langgraph-supervisor` n'est PAS installé (`pip show langgraph-supervisor` → `ModuleNotFoundError`). Pour s05 (routage déterministe par flag), on n'a pas besoin de `langgraph-supervisor`. Pour une itération future (routage par contenu), il faudra l'ajouter à `requirements.txt` (cf. § Décisions).
- **Implication concrète** : le « superviseur » en s05 est un **dispatcher Python typé**, pas un `StateGraph` langgraph. C'est cohérent avec l'ADR 003 (qui reporte le superviseur LangGraph à un future où le routage par contenu le justifie).

### LLM provider

- `LLM_PROVIDER=minimax` (défaut, routé via OpenRouter) ou `openai` (direct). Les deux sont instanciés par `build_llm_client(settings)` (cf. `client.py:51-79`). L'agent français utilise le même client.
- `chat_temperature=0.0` (reproductibilité des tests, aligné s02). Le superviseur passe `settings.chat_temperature` à la construction.
- `llm_model="minimax/minimax-m3:free"` — **point de vigilance** : un modèle différent pourrait être préférable pour le français (registre littéraire vs technique). Le PRD § Questions ouvertes dit « specifics of the French agent's prompt (level: collège, register: neutre, length: concis) ». Voir § Décisions.

### Structured output

- Pour le chat, le seul structured output est `ChatResult(answer, sources)` construit post-LLM par parsing regex des citations (`maths_agent.py:30` : `CITATION_RE`). Pas de JSON-mode.
- Pour le superviseur, pas de structured output : le `subject` est passé en argument par le caller.

### Pas de général knowledge (RAG-only)

- `MathsAgent.SYSTEM_PROMPT` (l.33-48) exige explicitement « Tu réponds UNIQUEMENT à partir des extraits de documents ». L'AC5 (« pas de fallback vers les maths ») est une extension naturelle de cette règle : si la collection `rag_francais_<pseudo>` est vide, l'agent français ne doit PAS aller chercher dans `rag_maths_<pseudo>`.
- **Le test bite** : l'AC5 dit « retourne le message no-document (pas de fallback aux maths) ». Le test doit vérifier que, pour un pseudo qui a uploadé un PDF de maths mais PAS de français, une question avec `--subject francais` produit la chaîne `no_document_message` et que le retriever n'a été appelé qu'avec `subject="francais"`.

## Pièges identifiés

1. **Subject pas validé côté CLI (silencieusement accepté).** `cli.py:300` (`subject: str = typer.Option(...)`) n'a pas de `click.Choice(["maths", "francais"])`. Si l'utilisateur passe `--subject histoire`, le code va créer `rag_histoire_<pseudo>` sans broncher. **Action** : ajouter une validation à 4 endroits (CLI + `MathsAgent` + `FrancaisAgent` + superviseur) qui lève `typer.BadParameter` ou `ValueError` pour les sujets non supportés. **Bite de régression** : un test mute le superviseur pour accepter n'importe quel `subject` → le test d'isolation rouge.
2. **Le superviseur est tenté de faire du routage par contenu via LLM.** C'est l'ADR 003 § Future work, mais le piège du story AC3 (« or, in a follow-up, by question content ») est qu'un implementer ambitieux peut câbler un `ChatPromptTemplate` qui classifie la question. **Action** : verrouiller dans le plan que la signature du superviseur est `ask(subject, pseudo, question)` et que le `subject` est obligatoire. Pas de classification. Le test bite à monkey-patcher le LLM pour vérifier qu'il n'est PAS appelé pour le routage.
3. **Factorisation `ChatResult` / `SourceCitation` casse l'import circulaire.** Si on les laisse dans `maths_agent.py` et que `francais_agent.py` les importe, puis que `supervisor.py` importe les deux agents, on a un cycle. **Action** : pendant s05, promouvoir ces types dans `backend/app/services/agents/types.py` (nouveau) et importer depuis là dans les deux agents et le superviseur. Le test bite à vérifier qu'il n'y a pas d'import circulaire (`pytest --collect-only` + `importlib`).
4. **L'open question du PRD (« level: collège, register: neutre, length: concis ») est vague.** Sans décision explicite au planning, deux implementers peuvent diverger sur le ton (poétique vs factuel), la longueur (3 phrases vs 5), le niveau de langue (tutoiement vs vouvoiement). **Action** : la section § Décisions fige le prompt de l'agent français en 5 invariants : (1) tutoiement cohérent avec `MathsAgent`, (2) réponse en français, (3) citation obligatoire au format `[source: filename, chunk N]`, (4) refus poli si pas de chunks (même message que maths), (5) registre neutre adapté au collège (ni littéraire soutenu, ni familier).
5. **Le `subject` n'est PAS propagé par le `FakeListChatModel` ni par `_CapturingLlm`.** Les stubs LLM de s02 capturent les messages, pas le `subject`. Le test cross-tenant « l'agent français ne va jamais chercher dans les maths » doit donc passer par un **retriever stubbé** (comme `_RecordingRetriever` à `test_maths_agent.py:47-56`) qui enregistre les `(subject, pseudo, question, k)` et asserte que tous les `subject` valent `"francais"`. **Action** : test à ajouter dans `test_francais_agent.py::TestCrossTenant::test_does_not_query_maths_collection` — seed `rag_maths_<pseudo>` avec un chunk au contenu distinctif, seed `rag_francais_<pseudo>` vide, query, assert que le retriever a été appelé une fois avec `subject="francais"` et zéro fois avec `subject="maths"`.
6. **Le format `CITATION_FORMAT` est dans `maths_agent.py` mais doit s'appliquer aussi à l'agent français.** Si on duplique le format dans `francais_agent.py` sans constante partagée, on a deux endroits à modifier. **Action** : promouvoir la constante dans `agents/citations.py` (nouveau, ou ré-exporter depuis `agents/__init__.py` pour limiter le nombre de fichiers). Le test bite à vérifier que la chaîne retournée par l'agent français matche la regex `\[source: [^,]+, chunk \d+\]`.

## Décisions d'architecture à prendre

### D1 — Forme du superviseur : StateGraph LangGraph ou dispatcher typé ?

**Contexte** : ADR 003 mandate LangGraph + `langgraph-supervisor`. La story AC3 mentionne « superviseur LangGraph routes the question based on the `--subject` flag (or, in a follow-up, by question content) ». `langgraph` 1.x est installé, `langgraph-supervisor` ne l'est pas.

**Options** :

- **Option A — StateGraph LangGraph dès s05** (`langgraph.StateGraph` + `add_conditional_edges` keyed on `subject`). Pro : conforme à l'esprit d'ADR 003. Con : ajoute une dépendance (`langgraph-supervisor` à installer pour le wrapping des agents), complexifie les tests (le state est un `TypedDict` qui doit être mocké), et n'apporte rien pour le scope (routage par flag = un `if` typé). Risque de sur-ingénierie pour un slice qui doit rester shippable en 1 PR.
- **Option B — Dispatcher Python typé** (`SubjectSupervisor.ask(subject, pseudo, question)` qui fait `if subject == "maths": self._maths.ask(...) elif subject == "francais": self._francais.ask(...)`). Pro : testable trivialement, pas de nouvelle dépendance, signature claire. Con : « ne suit pas l'ADR 003 à la lettre ».
- **Option C — Dispatcher Python + interface `langgraph`-compatible** (le superviseur expose `invoke(input: dict) -> dict` avec la même shape qu'un `Pregel`). Pro : pose les fondations pour le `StateGraph` futur sans le câbler maintenant. Con : design spéculatif, YAGNI.

**Recommandation** : **Option B**. Justifications :

1. L'ADR 003 lui-même reporte le superviseur LangGraph à « quand le routage par contenu le justifie » (l.23-25). Le scope de s05 est explicitement par flag.
2. La review s02 a noté comme **run interdict** : « No LangGraph supervisor (no `supervisor.py`, no `langgraph` imports in `app/`) » (`reviews/s02-chatter-avec-mon-cours.md:46`). L'introduire dans la story suivante est légitime, mais pas comme un `StateGraph` complet.
3. Si on doit migrer vers `StateGraph` plus tard (routage par contenu), le refactor est mécanique : remplacer le `if/elif` par `add_conditional_edges` keyed on `state["subject"]`. La migration est encapsulée dans `SubjectSupervisor`.
4. Le test bite : injecter un `_RecordingSupervisor` qui vérifie que **seul** l'agent de la matière demandée est invoqué, jamais les deux.

**Note de cohérence ADR** : si l'option B est retenue, ajouter une mention dans l'ADR 003 (« le superviseur sera introduit comme `StateGraph` à partir de l'itération « routage par contenu », pas dès s05 ») pour ne pas laisser l'ADR en désaccord avec le code. Pas un nouvel ADR — une mise à jour de l'existant.

### D2 — Emplacement du superviseur et des types partagés

**Options** :

- **Option A** — `supervisor.py` dans `services/agents/`, types partagés dans `services/agents/types.py` (ou `citations.py`).
- **Option B** — `supervisor.py` dans `services/agents/`, types dans `services/agents/__init__.py` (ré-exportés). Plus économe en fichiers, mais `__init__.py` devient un fourre-tout.

**Recommandation** : **Option A**. Le projet a déjà une séparation `agents/{maths_agent,francais_agent}.py` (un fichier par classe). `types.py` et `citations.py` suivent le même grain. `__init__.py` reste un index d'API publique.

### D3 — Validation de `subject` côté CLI

**Options** :

- **Option A — Aucune validation** (comportement actuel). Accepte n'importe quel `str` ; le code va silencieusement créer `rag_<unknown>_<pseudo>`.
- **Option B — `typer.Option(..., click.Choice(["maths", "francais"]))`** au niveau CLI. Refuse `--subject histoire` avec un message clair.
- **Option C — Validation au niveau de l'agent** (`FrancaisAgent.ask` lève `ValueError` si `subject != "francais"` ; idem pour maths). CLI en aval mappe vers exit code 5.

**Recommandation** : **Option B + Option C combinées**. La validation CLI donne un message clair à l'utilisateur (`typer.BadParameter`). La validation au niveau agent est une **défense en profondeur** : si un autre caller (un futur endpoint FastAPI) appelle `FrancaisAgent.ask("maths", ...)`, l'agent refuse au lieu de query silencieusement la mauvaise collection. C'est aussi un test bite au niveau agent (l'AC1 et l'AC5 dépendent de cette discipline).

### D4 — Prompt de l'agent français (open question du PRD)

**Contraintes documentées** (PRD § Questions ouvertes, ligne 186) : « level: collège, register: neutre, length: concis ».

**Invariants à verrouiller dans `FrancaisAgent.SYSTEM_PROMPT`** :

1. **Tu toiement l'élève** (cohérent avec `MathsAgent.SYSTEM_PROMPT:47` — « Tu réponds en français »).
2. **Réponse en français**, niveau collège (6e-3e).
3. **Citation obligatoire** au format `[source: <filename>, chunk <n>]` (identique à `MathsAgent.CITATION_FORMAT`).
4. **Refus poli** si pas de chunks (utiliser la même chaîne que `MathsAgent.no_document_message`, configurable par `Settings.chat_no_document_message`).
5. **Ancrage strict aux chunks fournis** (interdiction explicite d'inventer, extrapoler, compléter avec des connaissances générales).

**Différenciation vs `MathsAgent.SYSTEM_PROMPT`** :

- Maths : « un élève de collège » → Français : « un élève de collège en cours de français » (clarifier le contexte disciplinaire).
- Maths : « mathématiques » → Français : « français » (le LLM doit comprendre qu'on parle de grammaire, conjugaison, littérature, analyse de texte, etc.).
- Maths : « Tu réponds de manière claire et concise » → Français : « Tu réponds de manière claire, concise, et adaptée à un élève de collège » (redondant mais explicite — c'est le piège de l'imprécision du PRD).

**Recommandation** : le prompt doit faire 5-8 lignes max, avec les 5 invariants numérotés. Le test bite à asserter que la constante contient les 5 mots-clés (« collège », « français », « source », « pas d'information » / « inventé », etc.).

### D5 — Stratégie pour le test « pas de fallback vers les maths » (AC5)

**Options** :

- **Option A** — `EphemeralClient` ChromaDB, seed `rag_maths_<pseudo>` avec un chunk au contenu distinctif, query `subject="francais"` → assert que l'agent retourne `no_document_message` et que la réponse ne contient pas le mot distinctif du chunk maths.
- **Option B** — Retriever stubbé qui retourne `[]` quand appelé avec `subject="francais"` ; assert que le retriever n'est PAS appelé avec `subject="maths"`.

**Recommandation** : **les deux**. Option A teste le comportement end-to-end (le plus proche de la prod). Option B teste l'invariant architectural (le sujet n'est jamais re-routé). Les deux tests sont dans `test_francais_agent.py::TestCrossTenant`.

### D6 — Réutilisation de `chat_no_document_message` (env `CHAT_NO_DOCUMENT_MESSAGE`)

Le message de fallback est global à la config (`Settings.chat_no_document_message`, `config.py:62-64`). L'agent français l'utilise tel quel. **Pas de duplication** : pas de `francais_no_document_message` séparé. Si le produit veut un message spécifique au français plus tard, c'est une variable d'env distincte (`FRENCH_NO_DOCUMENT_MESSAGE`) — mais c'est du YAGNI en s05.

## Fichiers anticipés

### Code

| Fichier | Action | Contenu prévu |
|---|---|---|
| `backend/app/services/agents/citations.py` | **nouveau** | `CITATION_FORMAT`, `CITATION_RE` (extraites de `maths_agent.py:26-30`). Ré-exportées. |
| `backend/app/services/agents/types.py` | **nouveau** | `SourceCitation`, `ChatResult` (extraites de `maths_agent.py:51-62`). Ré-exportées. |
| `backend/app/services/agents/maths_agent.py` | **modifié** | Imports des types/citations depuis `agents/types.py` et `agents/citations.py`. `SYSTEM_PROMPT`, `MathsAgent`, `_RetrieverLike` restent. ~10 lignes en moins. |
| `backend/app/services/agents/francais_agent.py` | **nouveau** | Clone de `maths_agent.py` avec `SYSTEM_PROMPT` spécifique (cf. D4). Validation `subject == "francais"` au début de `ask`. ~100 lignes. |
| `backend/app/services/agents/supervisor.py` | **nouveau** | `SubjectAgent` Protocol + `SubjectSupervisor(subject_agents: dict[str, SubjectAgent])` + `ask(subject, pseudo, question) -> ChatResult`. Validation `subject` contre l'enum `Subject`. ~50 lignes. |
| `backend/app/services/agents/__init__.py` | **modifié** | Ré-exporte `MathsAgent`, `FrancaisAgent`, `SubjectSupervisor`, `ChatResult`, `SourceCitation`. |
| `backend/app/cli.py` | **modifié** | `_build_chat_service()` retourne un `SubjectSupervisor` au lieu d'un `MathsAgent`. Validation `click.Choice` sur `--subject` dans la commande `chat`. ~10 lignes de diff. |
| `backend/app/core/config.py` | **modifié (optionnel)** | Possible ajout de `francais_llm_model: str = ""` (vide = utilise `llm_model` global). **À trancher au planning** : si l'équipe veut un modèle distinct pour le français (registre littéraire), c'est ici. Sinon, skip. |
| `backend/.env.example` | **modifié (optionnel)** | Idem config — ajout de `FRENCH_LLM_MODEL=` (commenté) si D6-tranchée-oui. |

### Tests

| Fichier | Action | Tests |
|---|---|---|
| `backend/tests/services/agents/test_maths_agent.py` | **modifié** | Mise à jour des imports (`SourceCitation` vient de `agents.types`). Pas de nouveau test. |
| `backend/tests/services/agents/test_francais_agent.py` | **nouveau** | 8-10 tests : citation format, system prompt, ask happy path, no document, cross-tenant, prompt injecte les chunks, validation `subject="maths"` levée, `_RetrieverLike` Protocol respecté. |
| `backend/tests/services/agents/test_supervisor.py` | **nouveau** | 5-7 tests : dispatch à `MathsAgent` quand `subject="maths"`, dispatch à `FrancaisAgent` quand `subject="francais"`, exception si sujet inconnu, `ChatResult` propagé tel quel, exception propagée depuis l'agent, cross-tenant (un agent ne peut pas demander l'autre). |
| `backend/tests/services/agents/test_citations.py` | **nouveau** | 2-3 tests : `CITATION_FORMAT` constant, regex matches/rejets, position du module stable. |
| `backend/tests/services/agents/test_types.py` | **nouveau** | 1-2 tests : `ChatResult` sérialise, `SourceCitation` sérialise, import circulaire absent. |
| `backend/tests/cli/test_cli.py` | **étendu** | 3-4 nouveaux tests `chat` : `--subject francais` exit 0 avec stub `FrancaisAgent` ; `--subject histoire` (hors `Choice`) exit 2 (ou code typer) ; `--subject francais` avec `no_document` exit 0 et message ; cross-tenant au niveau CLI. |

### Doc

| Fichier | Action | Contenu |
|---|---|---|
| `docs/architecture.md` | **modifié (mineure)** | Ligne 69 (`agents/ supervisor, maths_agent, francais_agent`) est exacte après s05. Section « Patterns & conventions » : ajouter un paragraphe sur le pattern `SubjectSupervisor` (dispatcher typé, ADR 003 reporte le `StateGraph` à l'itération routage par contenu). |
| `docs/decisions/003-langgraph-supervisor.md` | **modifié (mineure)** | Ajouter une mention : « s05 livre un dispatcher Python typé, pas un `StateGraph`. Le `StateGraph` arrive quand le routage par contenu est implémenté. » Pas un nouvel ADR. |
| `docs/decisions/004-rag-isolation-by-collection.md` | **intact** | L'ADR couvre déjà le cas français (la convention `rag_<subject>_<pseudo>` est sujet-agnostique). |
| Pas d'ADR nouveau | — | Toutes les décisions s'inscrivent dans ADR 003 (mise à jour mineure) et ADR 004 (intact). |

## Tests à prévoir

### Tests unitaires (un par AC)

| AC | Test | Couche | Stub utilisé |
|---|---|---|---|
| AC1 (`--subject francais` marche) | `test_cli.py::TestChat::test_chat_with_francais_subject_uses_french_agent` | CLI | `_StubSubjectSupervisor` qui retourne un `ChatResult` si `subject="francais"`. |
| AC2 (collection `rag_francais_<pseudo>`) | `test_francais_agent.py::TestAsk::test_ask_uses_retriever_with_correct_subject_pseudo` | Agent | `_RecordingRetriever` (hérité de `test_maths_agent.py`). |
| AC3 (superviseur route par `--subject`) | `test_supervisor.py::TestDispatch::test_dispatch_to_maths_when_subject_is_maths` + `test_dispatch_to_francais_when_subject_is_francais` | Superviseur | `MathsAgent` et `FrancaisAgent` instanciés avec un retriever stubbé qui enregistre les appels. |
| AC4 (réponse cite des sources français) | `test_francais_agent.py::TestAskHappyPath::test_ask_returns_answer_citing_sources` | Agent | `_CapturingLlm` + chunks seeded avec `filename="cours_fr.pdf"`. |
| AC5 (no doc français → pas de fallback maths) | `test_francais_agent.py::TestCrossTenant::test_french_question_with_no_french_doc_does_not_query_maths` + `test_french_question_with_no_french_doc_returns_no_document_message` | Agent | Retriever réel (EphemeralClient) avec `rag_maths_<pseudo>` seedée et `rag_francais_<pseudo>` vide. |
| AC6 (isolation cross-tenant français) | `test_francais_agent.py::TestCrossTenant::test_cross_tenant_isolation_at_french_agent_level` | Agent | Deux pseudos, seeds différents, retriever réel. |

### Tests bite de régression

1. **Muter `FrancaisAgent.ask` pour ne pas valider `subject` (accepter `"maths"`)** → `test_francais_agent.py::TestValidation::test_ask_rejects_non_french_subject` rouge.
2. **Muter `SubjectSupervisor.ask` pour router vers n'importe quel agent** (retirer le `if subject == ...`) → `test_supervisor.py::TestDispatch` rouge (2 tests).
3. **Muter `FrancaisAgent.SYSTEM_PROMPT` pour retirer la consigne « uniquement tes documents »** → `test_francais_agent.py::TestSystemPrompt::test_system_prompt_forbids_general_knowledge` rouge.
4. **Muter `citations.py` pour changer `CITATION_FORMAT`** → `test_citations.py::TestFormat` rouge.

### Tests CLI (un par AC)

| AC | Test |
|---|---|
| AC1 | `test_cli.py::TestChat::test_chat_with_francais_subject_routes_to_french_agent` |
| AC5 | `test_cli.py::TestChat::test_chat_francais_with_no_document_returns_no_document` |
| AC6 (cross-tenant) | `test_cli.py::TestChat::test_chat_francais_cross_tenant_returns_5` (ou autre code — voir D3) |
| D3 (validation sujet) | `test_cli.py::TestChat::test_chat_rejects_unknown_subject` |

### Tests d'intégration (best-effort, non bloquants)

- `@pytest.mark.integration` : stub réel du superviseur + upload d'un PDF français + chat → assert la réponse contient `[source: ..., chunk ...]`.
- Non listés en AC ; marqués `pytest.skip` si `LLM_API_KEY` absent.

## Risques

**Score de complexité** : 3. Risques réels, par ordre décroissant :

1. **Sur-ingénierie du superviseur.** Tentation naturelle de câbler un `StateGraph` LangGraph complet avec `langgraph-supervisor` (pour « respecter l'ADR 003 »). Risque : ajoute une dépendance, complexifie les tests, n'apporte rien pour le scope (routage par flag). **Mitigation** : décision D1 retenue (dispatcher typé), revue explicite en checkpoint planning.

2. **Divergence de prompt entre les deux agents.** Si l'agent maths et l'agent français ont des formulations très différentes pour la même règle (« pas d'invention »), le produit devient incohérent. **Mitigation** : les 5 invariants de D4 sont verrouillés par tests bite sur les deux prompts. Les `system_prompt_*` tests sont jumelés.

3. **Fuite de citations cross-subject.** Si le superviseur est mal câblé, l'agent français pourrait accidentellement query `rag_maths_<pseudo>`. Le test AC5 bite (option B de D5 : retriever stubbé qui vérifie le `subject` dans `calls`).

4. **Import circulaire `maths_agent` ↔ `francais_agent` ↔ `supervisor`.** Si `francais_agent.py` importe `SourceCitation` depuis `maths_agent.py` et que `supervisor.py` importe les deux, on a un cycle. **Mitigation** : D2 — extraction dans `agents/types.py` (et `citations.py`).

5. **Modèle LLM inadapté au français.** `minimax/minimax-m3:free` (OpenRouter) est optimisé pour le code et les maths. Pour le français littéraire, le ton peut être trop sec ou halluciner des citations. **Mitigation** : les tests bite verrouillent les invariants du prompt, mais le test d'intégration best-effort doit être lancé manuellement par un humain (cf. review s02 § « No real LLM call »). Si le modèle est insuffisant, c'est une décision à porter en s11 (frontend) avec un fallback de modèle.

6. **Validation `subject` côté CLI change le comportement de s02-s04.** L'ajout de `click.Choice` sur `--subject` peut casser des tests existants qui passent `--subject maths` (mais c'est attendu) ou `--subject foo` (rare). **Mitigation** : grep `typer.Option(.*--subject` dans les tests existants avant d'ajouter la validation ; mettre à jour les tests foo si besoin.

7. **Compatibilité `langgraph` 1.x.** `langgraph` 1.x a changé plusieurs APIs depuis 0.x. Si l'équipe importe un jour un pattern 0.x par erreur, ça casse au runtime. **Mitigation** : pas d'imports `langgraph` en s05 (cf. D1 — dispatcher Python). Documentation explicite.

8. **Migration vers `StateGraph` future.** Si on opte pour D1-B (dispatcher Python) et qu'on doit migrer vers `StateGraph` au routage par contenu, le refactor touche `SubjectSupervisor` uniquement — les agents restent intacts. **Mitigation** : D1-C est rejeté (YAGNI), mais la signature de `SubjectSupervisor.ask` est compatible avec une encapsulation dans un `Pregel.invoke({"subject": ..., "pseudo": ..., "question": ...})`.

## Definition of Done

(Reprend la DoD du repo, spécialisée pour s05)

- [ ] Toutes les tâches cochées.
- [ ] `pytest -m "not integration"` passe (cible : +15 à 20 tests par rapport à s04, soit ~145+ tests).
- [ ] `ruff check app tests` passe (0 erreur).
- [ ] AC1-AC6 tous couverts par des tests unitaires.
- [ ] Test cross-tenant au niveau agent français ET au niveau superviseur.
- [ ] Test « pas de fallback vers les maths » (AC5) avec retriever réel (EphemeralClient).
- [ ] `SubjectSupervisor` testé avec 2 agents stubbés — dispatch vérifié.
- [ ] Format de citation `[source: filename, chunk N]` partagé entre les deux agents (constante dans `agents/citations.py`).
- [ ] `SYSTEM_PROMPT` de l'agent français contient les 5 invariants (test bite).
- [ ] Validation `subject` au niveau CLI (`click.Choice`) ET au niveau agent (défense en profondeur).
- [ ] Pas de dépendance ajoutée à `requirements.txt` (sauf décision explicite au planning pour `langgraph-supervisor`, qui est actuellement NON retenu pour s05).
- [ ] `chat_no_document_message` réutilisé tel quel (pas de duplication).
- [ ] ADR 003 mis à jour (mineure) pour acter le dispatcher Python.
- [ ] PR unique, description structurée : résumé, AC cochées, points d'attention (notamment la non-utilisation de `langgraph-supervisor` en s05 et le report du `StateGraph` à l'itération routage par contenu).
- [ ] `git diff main...feature/s05-agent-francais-chat` est lisible.
- [ ] Review passée (`docs/reviews/s05-agent-francais-chat.md` avec `Ship allowed: yes`).

## Sources

Fichiers lus et cités dans ce document (tous relatifs à `C:\Workspace\ktutor\.worktrees\s05-agent-francais-chat\`) :

- `docs/stories.md` (l.155-186 : story s05)
- `docs/prd.md` (l.83-86 : questions ouvertes, l.16 : personas, l.30-37 : périmètre in)
- `docs/architecture.md` (l.69 : tree cible, l.150-156 : multi-tenancy, l.317-322 : observabilité)
- `docs/decisions/002-poc-rewrite-from-scratch.md` (l.32-33 : convention `rag_<subject>_<pseudo>` héritée du POC)
- `docs/decisions/003-langgraph-supervisor.md` (l.23-25 : routing par flag, l.23-25 : report au contenu)
- `docs/decisions/004-rag-isolation-by-collection.md` (l.20-30 : factory + convention)
- `docs/designs/s01-uploader-document.md` (l.137-165 : conventions CLI, codes de sortie, validation sujet)
- `docs/research/s02-chatter-avec-mon-cours.md` (template de structure pour ce document)
- `docs/research/s03-generer-qcm.md` (conventions d'injection et de persistence)
- `docs/plans/s02-chatter-avec-mon-cours.md` (template de plan + run interdicts)
- `docs/reviews/s02-chatter-avec-mon-cours.md` (l.42-50 : run interdicts, l.65-88 : findings mineurs)
- `backend/app/services/agents/__init__.py`
- `backend/app/services/agents/maths_agent.py` (intégralité — 146 lignes)
- `backend/app/services/rag/retriever.py` (intégralité — 152 lignes)
- `backend/app/services/rag/chroma_store.py` (intégralité — 99 lignes)
- `backend/app/services/rag/embeddings.py` (intégralité — 72 lignes)
- `backend/app/services/rag/upload_service.py` (l.171, l.288-293 : `get_collection` + `_to_chroma_dict`)
- `backend/app/services/llm/client.py` (intégralité — 80 lignes)
- `backend/app/core/config.py` (intégralité — 88 lignes)
- `backend/app/core/database/models.py` (l.26-30 : enum `Subject`)
- `backend/app/cli.py` (intégralité — 530 lignes)
- `backend/.env.example` (intégralité)
- `backend/requirements.txt` (intégralité — confirmation : `langgraph` n'est PAS listé explicitement, mais est tiré par `langchain-community` ; `langgraph-supervisor` absent)
- `backend/pyproject.toml`
- `backend/tests/conftest.py` (helpers `make_sample_pdf`, `make_typed_image`, fixtures)
- `backend/tests/services/agents/test_maths_agent.py` (intégralité — 316 lignes)
- `backend/tests/services/rag/test_retriever.py` (intégralité — 274 lignes)
- `backend/tests/services/llm/test_client.py` (intégralité — 80 lignes)
- `backend/tests/cli/test_cli.py` (intégralité — 812 lignes)

Vérification runtime : `python -c "import langgraph.pregel"` → OK (langgraph 1.x installé). `python -c "import langgraph_supervisor"` → `ModuleNotFoundError` (`langgraph-supervisor` NON installé).

ADR applicables : 002 (POC rewrite), 003 (LangGraph supervisor), 004 (RAG isolation par collection), 005 (auth RS256+RBAC — non touchée par s05 mais applicable), 008 (vision LLM — non touchée par s05), 009 (SeaweedFS — non touchée par s05).

Documentation externe consultée implicitement via les ADR : LangGraph 1.x pregel API (référencée dans ADR 003), langchain-openai 0.2+ ChatOpenAI (utilisée en s02), ChromaDB 1.5+ PersistentClient / EphemeralClient (utilisée en s01).
