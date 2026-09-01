---
validated: yes
---
# Plan — Story s05-agent-francais-chat

Branch: `feature/s05-agent-francais-chat`
Research: `docs/research/s05-agent-francais-chat.md` (362 lignes) — read it first; this plan does not repeat it.
Design: `docs/designs/s05-agent-francais-chat.md` — story purement backend, aucun mockup, contrat UI figé pour les stories aval.

## Target story

**As an** élève **I want** poser une question sur un cours de français **so that** j'obtiens une réponse qui s'appuie sur mes documents de français.

**Complexity** : 3 (Second agent + supervisor + collection ChromaDB séparée).

### Acceptance criteria (résumé, 6 ACs)

1. `python -m ktutor.cli chat --subject francais ...` fonctionne (CLI flag).
2. L'agent français utilise la collection `rag_francais_<pseudo>`.
3. Un superviseur LangGraph (en fait dispatcher typé — cf. D1) route par `--subject`.
4. La réponse cite des sources des documents français.
5. Question française SANS document français → message « pas de document » (pas de fallback maths).
6. Isolation cross-tenant : `pseudo_a` dans `rag_francais_a` non lisible par `pseudo_b`.

## Tasks (ordonnées)

> **Conventions** : un test par AC, commits atomiques, Python 3.12, ruff OK, `pytest -m "not integration"` doit passer en intégralité.

### Tâche 1 — Extraire `SourceCitation` et `ChatResult` dans `agents/types.py` [x]

- **Action** : Créer `backend/app/services/agents/types.py` avec `SourceCitation` (Pydantic BaseModel, identique à `maths_agent.py:51-56`) et `ChatResult` (idem lignes 58-62).
- **Test** : `backend/tests/services/agents/test_types.py::TestTypes` (1 test : `ChatResult.model_validate({"answer": "x", "sources": [{"filename": "a", "chunk_index": 0}]})`).
- **Vérification** : `python -c "from app.services.agents.types import ChatResult, SourceCitation"` ne lève pas.
- **Run interdicts** : ne pas modifier `maths_agent.py` dans cette tâche (refactor isolé).

### Tâche 2 — Extraire `CITATION_FORMAT` et `CITATION_RE` dans `agents/citations.py` [x]

- **Action** : Créer `backend/app/services/agents/citations.py` avec les 2 constantes extraites de `maths_agent.py:26-30`.
- **Test** : `backend/tests/services/agents/test_citations.py::TestCitations` (2 tests : `CITATION_FORMAT` constant = `"[source: {filename}, chunk {chunk_index}]"`, regex matche un exemple et rejette un non-match).
- **Vérification** : `python -c "from app.services.agents.citations import CITATION_FORMAT, CITATION_RE"`.
- **Run interdicts** : ne pas modifier `maths_agent.py`.

### Tâche 3 — Refactor `maths_agent.py` pour importer les types extraits [x]

- **Action** : Dans `maths_agent.py`, remplacer les définitions locales de `SourceCitation`, `ChatResult`, `CITATION_FORMAT`, `CITATION_RE` par `from app.services.agents.types import SourceCitation, ChatResult` et `from app.services.agents.citations import CITATION_FORMAT, CITATION_RE`.
- **Test** : `pytest backend/tests/services/agents/test_maths_agent.py -v` doit passer SANS modification des tests (les imports restent compatibles).
- **Vérification** : `git diff --stat` ne montre qu'un import remplacé, ~10 lignes en moins dans `maths_agent.py`.
- **Run interdicts** : ne pas changer la signature publique de `MathsAgent.ask` ni le `SYSTEM_PROMPT`.

### Tâche 4 — Implémenter `FrancaisAgent` (clone avec prompt français) [x]

- **Action** : Créer `backend/app/services/agents/francais_agent.py` :
  - `SYSTEM_PROMPT` = prompt français (cf. recherche D4, 5 invariants verrouillés : pas de général knowledge, citations `[source: ...]`, registre neutre, longueur concise, refus hors-périmètre français).
  - `FrancaisAgent.__init__(llm, retriever, top_k, no_document_message, source_format=CITATION_FORMAT, source_re=CITATION_RE)` — même signature que `MathsAgent` (sauf `subject="francais"` imposé).
  - `FrancaisAgent.ask(subject, pseudo, question) -> ChatResult` :
    - **Validation bite** : `if subject != "francais": raise ValueError(...)`.
    - Sinon, clone du flow `MathsAgent.ask` (lignes 92-110).
- **Test** : `backend/tests/services/agents/test_francais_agent.py` avec 8-10 tests :
  - `TestSystemPrompt::test_system_prompt_contains_5_invariants` (test bite)
  - `TestAskHappyPath::test_ask_returns_answer_citing_sources` (AC4)
  - `TestAsk::test_ask_uses_retriever_with_correct_subject_pseudo` (AC2)
  - `TestAsk::test_ask_returns_no_document_message_when_no_chunks` (AC5)
  - `TestValidation::test_ask_rejects_non_french_subject` (test bite)
  - `TestCrossTenant::test_cross_tenant_isolation_at_french_agent_level` (AC6)
  - `TestCrossTenant::test_french_question_with_no_french_doc_does_not_query_maths` (AC5, avec `EphemeralClient`)
- **Run interdicts** : ne pas dupliquer `SourceCitation`/`ChatResult` localement (importer depuis `agents/types.py`).

### Tâche 5 — Implémenter `SubjectSupervisor` (dispatcher typé) [x]

- **Action** : Créer `backend/app/services/agents/supervisor.py` :
  - `class SubjectAgent(Protocol)` avec `ask(subject: str, pseudo: str, question: str) -> ChatResult`.
  - `class SubjectSupervisor` :
    - `__init__(subject_agents: dict[str, SubjectAgent])`.
    - `ask(subject, pseudo, question) -> ChatResult` :
      - Validation `subject` contre `Subject` enum (`Subject.MATHS.value` / `Subject.FRANCAIS.value`).
      - Dispatch via `self._subject_agents[subject].ask(subject, pseudo, question)`.
      - Si sujet inconnu : `raise ValueError(f"Unknown subject: {subject}")`.
- **Test** : `backend/tests/services/agents/test_supervisor.py` avec 5-7 tests :
  - `TestDispatch::test_dispatch_to_maths_when_subject_is_maths` (AC3)
  - `TestDispatch::test_dispatch_to_francais_when_subject_is_francais` (AC3)
  - `TestValidation::test_ask_rejects_unknown_subject` (test bite D3)
  - `TestPassthrough::test_chat_result_propagated_unchanged`
  - `TestPassthrough::test_agent_exception_propagated`
  - `TestIsolation::test_supervisor_does_not_route_to_other_subject` (test bite, régression cross-subject)
- **Run interdicts** : ne PAS utiliser `langgraph` ou `langgraph-supervisor` (D1 retenu : dispatcher typé). Pas de nouvelle dépendance `requirements.txt`.

### Tâche 6 — Mettre à jour `agents/__init__.py` [x]

- **Action** : Ré-exporter `MathsAgent`, `FrancaisAgent`, `SubjectSupervisor`, `ChatResult`, `SourceCitation` depuis les modules respectifs.
- **Test** : `python -c "from app.services.agents import MathsAgent, FrancaisAgent, SubjectSupervisor"` ne lève pas.
- **Run interdicts** : ne pas casser les imports existants.

### Tâche 7 — Câbler le superviseur dans le CLI [x]

- **Action** : Dans `backend/app/cli.py` :
  - `_build_chat_service()` (ligne 113) : au lieu de retourner un `MathsAgent` direct, instancie `MathsAgent` ET `FrancaisAgent`, les injecte dans un `SubjectSupervisor({Subject.MATHS.value: maths, Subject.FRANCAIS.value: francais})`, retourne le superviseur.
  - Commande `chat` (ligne 298) : ajouter `click.Choice([Subject.MATHS.value, Subject.FRANCAIS.value])` sur l'option `--subject` (typer : `case_sensitive=False` ou `case_sensitive=True` — à fixer).
  - Mise à jour du mapping exit codes : `ValueError` (sujet inconnu côté agent) → `EXIT_INVALID_PSEUDO` (5) ou nouveau `EXIT_INVALID_SUBJECT` (à créer dans `upload_service.py` — recommander `EXIT_INVALID_PSEUDO=5` par défaut, pas de nouveau code).
- **Test** : `backend/tests/cli/test_cli.py` avec 4 nouveaux tests dans `TestChat` :
  - `test_chat_with_francais_subject_routes_to_french_agent` (AC1, exit 0)
  - `test_chat_with_maths_subject_still_works` (régression s02)
  - `test_chat_rejects_unknown_subject` (AC1, exit ≠ 0)
  - `test_chat_francais_with_no_document_returns_no_document_message` (AC5, exit 0)
- **Run interdicts** : ne pas changer `--subject` default pour les autres commandes (`generate_qcm` ligne 367, `submit_qcm` ligne 472).

### Tâche 8 — Mettre à jour `test_maths_agent.py` (imports) [x]

- **Action** : Si le test importe `SourceCitation` depuis `maths_agent`, changer pour `from app.services.agents.types import SourceCitation`.
- **Test** : `pytest backend/tests/services/agents/test_maths_agent.py -v` doit passer sans modification fonctionnelle.
- **Vérification** : `git diff backend/tests/services/agents/test_maths_agent.py` ne montre que des changements d'import.
- **Run interdicts** : ne pas modifier le comportement testé.

### Tâche 9 — Mise à jour mineure ADR 003 [x]

- **Action** : Dans `docs/decisions/003-langgraph-supervisor.md`, ajouter une mention : « s05 livre un dispatcher Python typé (`SubjectSupervisor`), pas un `StateGraph`. Le `StateGraph` arrive quand le routage par contenu est implémenté (itération future). »
- **Test** : pas de test — c'est de la doc.
- **Run interdicts** : ne pas créer de nouvel ADR (la décision s'inscrit dans ADR 003).

### Tâche 10 — Mise à jour mineure `docs/architecture.md` [x]

- **Action** : Section « Patterns & conventions » (ligne 317-322) — ajouter un paragraphe sur le pattern `SubjectSupervisor` : dispatcher typé Python, protocole `SubjectAgent`, signature `ask(subject, pseudo, question) -> ChatResult`. Mentionner ADR 003 et le report du `StateGraph`.
- **Test** : `markdownlint docs/architecture.md` doit passer.
- **Run interdicts** : ne pas réécrire l'architecture, juste ajouter le paragraphe.

### Tâche 11 — Lint + tests complets [x]

- **Action** :
  - `ruff check app tests` doit passer (0 erreur).
  - `pytest --cov=app --cov-fail-under=80 -m "not integration"` doit passer.
  - Vérifier couverture ≥ 80% sur les nouveaux modules (`agents/francais_agent.py`, `agents/supervisor.py`, `agents/types.py`, `agents/citations.py`).
- **Test** : les 189 tests existants (s01-s04) doivent toujours passer.
- **Run interdicts** : ne pas baisser le seuil de couverture.

### Tâche 12 — Commit + PR

- **Action** :
  - Commit atomique par tâche (ou 2-3 commits logiques : 1 refactor, 1 feature, 1 doc).
  - Push sur `feature/s05-agent-francais-chat`.
  - PR : titre `feat(agents): add French subject agent + supervisor (s05)`, description structurée (résumé, AC cochées, points d'attention : dispatcher Python au lieu de `StateGraph`, 0 nouvelle dépendance).
- **Test** : `git log --oneline feature/s05-agent-francais-chat` doit montrer 3-4 commits max.
- **Run interdicts** : pas de commit sur `main`, pas de merge auto (mode manuel cf. AGENTS.md).

## Run interdicts

- **Pas de `langgraph` ni `langgraph-supervisor`** dans les imports. D1 retenu : dispatcher Python typé. Tout import de `langgraph` dans cette story est un signal d'alarme.
- **Pas de modification du `SYSTEM_PROMPT` de `MathsAgent`** sauf l'import refactor (tâche 3). Les 2 agents doivent diverger UNIQUEMENT sur le prompt, pas sur le flow.
- **Pas de duplication `SourceCitation` / `ChatResult`** dans `francais_agent.py` ou `supervisor.py`. Toujours importer depuis `agents/types.py` (D2).
- **Pas de modification du `Retriever`** ni du `LlmClient`. Les 2 agents utilisent les mêmes interfaces.
- **Pas de nouvelle dépendance** dans `requirements.txt` (vérifié par `diff` à la fin).
- **Pas de validation `subject` côté agent seul** — défense en profondeur : CLI valide + agent valide (D3).
- **Pas de message de fallback spécifique au français** (`francais_no_document_message`) — réutiliser `chat_no_document_message` (D6, YAGNI).
- **Pas de modification des autres CLI commands** (`upload`, `generate_qcm`, `submit_qcm`, `submit_text` n'existe pas encore) — scope strict.
- **Pas de story UI dans cette PR** — l'écran `/chat` est en s11.

## The point everything turns on

**Décision D1** : implémenter un **dispatcher Python typé** (`SubjectSupervisor` avec `dict[str, SubjectAgent]`), pas un `StateGraph` LangGraph. C'est le compromis qui évite d'ajouter une dépendance (`langgraph-supervisor` n'est pas installé) et qui reste compatible avec une future migration vers `StateGraph` quand le routage par contenu arrivera (le refactor touchera `SubjectSupervisor` uniquement, pas les agents).

**Deux endroits où cette décision pourrait être fausse** :

1. Si le pipeline Phase 2 introduit un autre cas de « routage par critère » AVANT le routage par contenu (ex : router par difficulté, par matière secondaire), le dispatcher dict devient un nid à if/elif. Mitigation : le `Protocol SubjectAgent` est compatible avec une encapsulation dans un `Pregel.invoke(...)` plus tard.

2. Si le LLM `minimax/minimax-m3:free` se révèle inadapté au français littéraire (registre trop sec, hallucinations de citations), il faut un modèle distinct. Mitigation : le `__init__` de `FrancaisAgent` accepte un `llm` séparé — il suffit d'injecter un `build_llm_client(settings_french)` au lieu de `build_llm_client(settings)` dans `_build_chat_service()`. Mais on ne le fait PAS dans s05 (D6, YAGNI).

## Files touched

### Code
- `backend/app/services/agents/types.py` (nouveau, ~30 lignes)
- `backend/app/services/agents/citations.py` (nouveau, ~15 lignes)
- `backend/app/services/agents/maths_agent.py` (modifié, ~10 lignes en moins)
- `backend/app/services/agents/francais_agent.py` (nouveau, ~100 lignes)
- `backend/app/services/agents/supervisor.py` (nouveau, ~50 lignes)
- `backend/app/services/agents/__init__.py` (modifié, ~10 lignes)
- `backend/app/cli.py` (modifié, ~15 lignes de diff)

### Tests
- `backend/tests/services/agents/test_types.py` (nouveau, ~30 lignes)
- `backend/tests/services/agents/test_citations.py` (nouveau, ~40 lignes)
- `backend/tests/services/agents/test_francais_agent.py` (nouveau, ~250 lignes)
- `backend/tests/services/agents/test_supervisor.py` (nouveau, ~150 lignes)
- `backend/tests/services/agents/test_maths_agent.py` (modifié, ~5 lignes d'imports)
- `backend/tests/cli/test_cli.py` (étendu, ~80 lignes)

### Doc
- `docs/decisions/003-langgraph-supervisor.md` (modifié, ~3 lignes)
- `docs/architecture.md` (modifié, ~10 lignes)

**Total** : 4 nouveaux fichiers Python, 2 nouveaux fichiers de test, 4 fichiers Python modifiés, 1 fichier de test étendu, 2 fichiers de doc modifiés. ~10 nouveaux tests + 4 nouveaux tests CLI = ~14 nouveaux tests, soit ~204 tests au total (189 + 14 + quelques imports de refactor).

## Test strategy

### Tests automatisés (pytest, un par AC)

| AC | Test | Couche | Stub |
|---|---|---|---|
| AC1 (`--subject francais` marche) | `test_cli.py::TestChat::test_chat_with_francais_subject_routes_to_french_agent` | CLI | `_StubSubjectSupervisor` |
| AC2 (collection `rag_francais_<pseudo>`) | `test_francais_agent.py::TestAsk::test_ask_uses_retriever_with_correct_subject_pseudo` | Agent | `_RecordingRetriever` |
| AC3 (superviseur route par `--subject`) | `test_supervisor.py::TestDispatch::test_dispatch_to_*_when_subject_is_*` (2 tests) | Superviseur | `MathsAgent`/`FrancaisAgent` instanciés |
| AC4 (réponse cite des sources) | `test_francais_agent.py::TestAskHappyPath::test_ask_returns_answer_citing_sources` | Agent | `_CapturingLlm` + chunks seeded |
| AC5 (no doc français → pas de fallback maths) | `test_francais_agent.py::TestCrossTenant::test_french_question_with_no_french_doc_does_not_query_maths` | Agent | `EphemeralClient` réel |
| AC6 (cross-tenant) | `test_francais_agent.py::TestCrossTenant::test_cross_tenant_isolation_at_french_agent_level` | Agent | `EphemeralClient` réel, 2 pseudos |

### Tests bite de régression (4)

1. **Muter `FrancaisAgent.ask` pour accepter `subject="maths"`** → `TestValidation::test_ask_rejects_non_french_subject` rouge.
2. **Muter `SubjectSupervisor.ask` pour router vers n'importe quel agent** → `TestDispatch` rouge (2 tests).
3. **Muter `FrancaisAgent.SYSTEM_PROMPT` pour retirer la consigne « uniquement tes documents »** → `TestSystemPrompt::test_system_prompt_contains_5_invariants` rouge.
4. **Muter `SubjectSupervisor` pour skip la validation `subject`** → `TestValidation::test_ask_rejects_unknown_subject` rouge.

### Tests CLI (4)

- `test_chat_with_francais_subject_routes_to_french_agent` (AC1)
- `test_chat_with_maths_subject_still_works` (régression s02)
- `test_chat_rejects_unknown_subject` (D3, exit ≠ 0)
- `test_chat_francais_with_no_document_returns_no_document_message` (AC5)

### Tests d'intégration (best-effort, non bloquants)

- `@pytest.mark.integration` : stub réel + upload PDF français + chat → assert réponse contient citation.
- Skip si `LLM_API_KEY` absent.

### Vérification visuelle

**N/A** — la story n'a pas d'écran. La vérification est 100% automatisée.

### Couverture

Cible : ≥ 80% sur les nouveaux modules. Les agents sont de petite taille (~100 lignes) et bien testés, donc couverture attendue ≥ 90%.

## Definition of Done

Repo DoD spécialisé pour s05 :

- [ ] Toutes les tâches 1-12 cochées.
- [ ] `pytest -m "not integration"` passe : ~204 tests au total.
- [ ] `ruff check app tests` passe (0 erreur).
- [ ] AC1-AC6 tous couverts par tests unitaires.
- [ ] Tests bite de régression (4) verts.
- [ ] Test cross-tenant au niveau agent français ET au niveau superviseur.
- [ ] Test « pas de fallback maths » (AC5) avec retriever réel (`EphemeralClient`).
- [ ] `SubjectSupervisor` testé avec dispatch par sujet.
- [ ] Format de citation `[source: filename, chunk N]` partagé (constante dans `agents/citations.py`).
- [ ] `SYSTEM_PROMPT` français contient les 5 invariants (test bite).
- [ ] Validation `subject` au niveau CLI ET au niveau agent (défense en profondeur).
- [ ] `chat_no_document_message` réutilisé tel quel (pas de duplication).
- [ ] **Pas de dépendance ajoutée** à `requirements.txt` (vérifié par `git diff main...feature/s05-agent-francais-chat -- requirements.txt`).
- [ ] **Pas d'import `langgraph` ni `langgraph-supervisor`** (vérifié par `grep -r "import langgraph" backend/app/services/agents/`).
- [ ] ADR 003 mis à jour (mineure).
- [ ] `docs/architecture.md` mis à jour.
- [ ] PR unique, description structurée : résumé, AC cochées, points d'attention (dispatcher Python, 0 nouvelle dépendance, 4 états vs 5 états de CLAUDE.md).
- [ ] `git diff main...feature/s05-agent-francais-chat` est lisible (≤ 800 lignes de diff, hors tests).
- [ ] Review passée (`docs/reviews/s05-agent-francais-chat.md` avec `Ship allowed: yes`).

<< IP Mike: task granularity, what a good plan contains/avoids. >>
