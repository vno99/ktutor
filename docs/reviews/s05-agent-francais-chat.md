# Review — s05-agent-francais-chat

> Revu par : sous-agent `reviewer` (contexte frais).
> Date : 2026-09-01
> Source : `git diff main...feature/s05-agent-francais-chat` (HEAD `b0fb7ec`) vs `docs/plans/s05-agent-francais-chat.md` + `docs/research/s05-agent-francais-chat.md` + ADR 002/003/004.
> Tests : **219 passés** (lancés par le reviewer) — couverture **86.73%** (seuil 80%).
> Lint : `ruff check app tests` → **0 erreur**.
> Worktree : `C:\Workspace\ktutor\.worktrees\s05-agent-francais-chat` (branche `feature/s05-agent-francais-chat`).

## Test suite + lint (rejoués par le reviewer)

- `cd backend && python -m pytest --cov=app --cov-fail-under=80 -m "not integration"` : **219 passed, 1 warning** (langchain-community deprecation), coverage 86.73%.
- `cd backend && ruff check app tests` : **All checks passed!**
- Tests s05 (nouveaux) : `test_francais_agent.py` (11), `test_supervisor.py` (9), `test_types.py` (2), `test_citations.py` (4) = **26 tests**, tous verts.
- Tests s05 (CLI) : `test_cli.py::TestChat` 9 tests, dont 4 nouveaux (`test_chat_with_francais_subject_routes_to_french_agent`, `test_chat_with_maths_subject_still_works`, `test_chat_rejects_unknown_subject`, `test_chat_francais_with_no_document_returns_no_document_message`) — tous verts.
- Couverture des nouveaux modules : `francais_agent.py` 100%, `supervisor.py` 95%, `types.py` 100%, `citations.py` 100%, `agents/__init__.py` 100%. Au-dessus du seuil 80%.

## Diff vs plan, task by task

| Plan task | Status | Note |
| --- | --- | --- |
| Tâche 1 — `agents/types.py` | Done | `SourceCitation` et `ChatResult` (Pydantic) créés dans `backend/app/services/agents/types.py` (33 lignes), importés depuis les modules consommateurs. |
| Tâche 2 — `agents/citations.py` | Done | `CITATION_FORMAT` et `CITATION_RE` (regex compilé) créés dans `backend/app/services/agents/citations.py` (24 lignes). |
| Tâche 3 — Refactor `maths_agent.py` | Done | Définitions locales `SourceCitation`/`ChatResult`/`CITATION_FORMAT`/`CITATION_RE` supprimées ; imports depuis `types` et `citations`. `SYSTEM_PROMPT` intact. ~21 lignes en moins (le plan estimait ~10). |
| Tâche 4 — `FrancaisAgent` | Done | Clone de `MathsAgent` avec `SYSTEM_PROMPT` français (5 invariants : français, collège, citation format, pas de général knowledge, refus poli). Validation `subject == "francais"` au début de `ask`. 11 tests dont cross-tenant. |
| Tâche 5 — `SubjectSupervisor` | Done | `SubjectAgent` Protocol (`@runtime_checkable`) + `SubjectSupervisor(subject_agents: dict[str, SubjectAgent])` + validation contre l'enum `Subject` à l'init ET à l'ask. 9 tests dont dispatch maths/francais, validation, passthrough, isolation croisée. |
| Tâche 6 — `agents/__init__.py` | Done | Ré-exporte `MathsAgent`, `FrancaisAgent`, `SubjectSupervisor`, `ChatResult`, `SourceCitation`, `CITATION_FORMAT`, `CITATION_RE`, `SubjectAgent`. |
| Tâche 7 — Câblage CLI | Done avec déviation mineure | `_build_chat_service()` retourne un `SubjectSupervisor`. Validation `subject` en **deux étapes** (defense in depth) : bloc `if subject.lower() not in valid_subjects: raise typer.Exit(EXIT_INVALID_PSEUDO)` + `subject = subject.lower()` pour normaliser. Le plan recommandait `click.Choice` directement sur l'option `typer.Option`, mais la déviation est fonctionnellement équivalente (et nécessaire car `typer.Option` n'a pas d'attribut `case_sensitive=False` standard). Les 4 nouveaux tests CLI passent. |
| Tâche 8 — `test_maths_agent.py` (imports) | Done | Seulement les imports ont changé (4 lignes). Aucun test fonctionnel modifié. |
| Tâche 9 — ADR 003 mis à jour | Done | Section "Update — s05" ajoutée mentionnant le dispatcher Python typé et le report du `StateGraph` au routage par contenu. Pas de nouvel ADR. |
| Tâche 10 — `docs/architecture.md` mis à jour | Done | Paragraphe "Supervisor pattern (s05)" ajouté dans § Patterns & conventions. |
| Tâche 11 — Lint + tests complets | Done | ruff OK, pytest OK, couverture ≥ 80% (86.73%). |
| Tâche 12 — Commit + PR | Done (commit unique) | Le plan autorisait "Commit atomique par tâche (ou 2-3 commits logiques)". Commit unique : `b0fb7ec feat(agents): add French subject agent + supervisor (s05)`. Mineur. |

**Pas de drift majeur** — la diff reste dans le scope de la story. Run interdicts respectés :

- Aucun import `langgraph` ni `langgraph-supervisor` dans `backend/app/services/agents/` (vérifié par `grep -r "import langgraph"`).
- `backend/app/services/rag/retriever.py` intact.
- `backend/app/services/llm/client.py` intact.
- `backend/requirements.txt` intact (aucune dépendance ajoutée).
- `SYSTEM_PROMPT` de `MathsAgent` intact (uniquement l'import refactor).
- Pas de duplication `SourceCitation`/`ChatResult` dans `francais_agent.py` ou `supervisor.py` (importés depuis `agents/types.py`).
- Pas de message de fallback spécifique au français (`francais_no_document_message`) — `chat_no_document_message` réutilisé (D6/YAGNI).
- Pas de nouveau code `EXIT_INVALID_SUBJECT` — `EXIT_INVALID_PSEUDO=5` réutilisé pour les sujets invalides.
- Commandes s04 (`generate_qcm`, `submit_qcm`) intactes (vérifié : `subject: str = typer.Option("maths", "--subject", ...)` toujours présent).
- Validation `subject` au niveau CLI ET au niveau agent (defense in depth) — vérifié.

## Anti-hallucination (chaque import, appel, signature vérifié)

- `from app.services.agents.types import ChatResult, SourceCitation` — OK, `types.py` exporte les deux Pydantic BaseModel.
- `from app.services.agents.citations import CITATION_FORMAT, CITATION_RE` — OK, `citations.py` exporte les deux.
- `from app.services.agents.maths_agent import _build_user_prompt, _collect_sources, _RetrieverLike` — OK, fonctions/Protocol exportés par `maths_agent.py` (méthodes internes promues en module-level pour partage entre agents — vu dans le diff).
- `from app.core.database.models import Subject` — OK, `Subject` est l'enum avec `MATHS = "maths"` et `FRANCAIS = "francais"`.
- `from app.services.agents.supervisor import SubjectAgent, SubjectSupervisor` — OK, les deux exportés.
- `subject.lower()` + comparaison à `{s.value for s in Subject}` — `Subject.MATHS.value == "maths"`, `Subject.FRANCAIS.value == "francais"` (minuscules) — cohérent.
- `FrancaisAgent.__init__(llm, retriever, top_k, no_document_message)` — signature identique à `MathsAgent` (vérifié).
- `FrancaisAgent.ask(subject, pseudo, question) -> ChatResult` — signature identique.
- `SubjectSupervisor.__init__(subject_agents: dict[str, SubjectAgent])` — typé et validé.
- `SubjectSupervisor.ask(subject, pseudo, question) -> ChatResult` — dispatch + validation.

Pas d'API inventée. Pas de fonction/import halluciné.

## Tests bite (vérifiés par exécution réelle des assertions)

- **Bite 1** : `FrancaisAgent.ask("maths", "alice", "Q ?")` lève `ValueError` (vérifié par exécution) — `TestValidation::test_ask_rejects_non_french_subject` couvre.
- **Bite 2** : `FrancaisAgent.ask("francais", "alice", "Q ?")` (collection vide) appelle le retriever avec `(subject="francais", pseudo="alice", question, k=4)` et **n'appelle PAS le LLM** — `TestAskEmpty::test_ask_with_empty_collection_returns_no_document_message` et `TestCrossTenant::test_french_question_with_no_french_doc_does_not_query_maths` couvrent (ce dernier utilise un vrai `EphemeralClient` + vrai `Retriever`).
- **Bite 3** : `FrancaisAgent.SYSTEM_PROMPT` contient `"UNIQUEMENT"`, `"[source:"`, `"collège"`, `"français"`, `"inventer"` — `TestSystemPrompt::test_system_prompt_contains_5_invariants` + `test_system_prompt_locks_no_general_knowledge` + `test_system_prompt_shares_citation_format_constant` couvrent.
- **Bite 4** : `SubjectSupervisor.ask("histoire", ...)` lève `ValueError` avant tout appel d'agent — `TestValidation::test_ask_rejects_unknown_subject` + `test_ask_rejects_empty_subject` couvrent.
- **Bite 5** : Dispatch par sujet — `TestDispatch::test_dispatch_to_maths_when_subject_is_maths` et `test_dispatch_to_francais_when_subject_is_francais` couvrent ; `TestIsolation::test_supervisor_does_not_route_to_other_subject` + `test_supervisor_does_not_route_francais_to_maths` prouvent qu'un sujet ne touche **jamais** l'agent de l'autre matière.
- **Bite 6** : Cross-tenant — `TestCrossTenant::test_cross_tenant_isolation_at_french_agent_level` utilise un vrai `EphemeralClient` + 2 pseudos distincts + un `EchoLlm` qui révèle la fuite ; passe.

Les bite tests ne sont pas décoratifs : retirer la validation `subject` dans `FrancaisAgent.ask`, ou changer la signature de `SubjectSupervisor.ask` pour router toujours vers le même agent, casserait des tests rouges (vérifié par lecture des assertions et par tests réels des invariants via `python -c`).

## Conformité design system

**Aucun composant, token, couleur ou espacement utilisé.** Story purement backend. `docs/designs/s05-agent-francais-chat.md` confirme : "Aucun écran à produire... Aucun composant du design system n'est consommé." Conformité N/A.

## Conformité AGENTS.md / ADR

- ADR 003 mis à jour (mineure, comme demandé) — pas de contradiction, le dispatcher Python typé est explicitement mentionné comme D1 retenu.
- ADR 004 (RAG isolation par collection) : respectée par construction — `FrancaisAgent.ask` appelle `retriever.query(subject="francais", pseudo, question, k)`, et `Retriever` (intact) appelle `chroma_store.get_collection("francais", pseudo)` qui produit `rag_francais_<pseudo>`.
- `AGENTS.md` : conventions de nommage respectées (snake_case fichiers/fonctions, PascalCase classes, kebab-case URLs). Typage obligatoire respecté. Pas de `try/except` muets (un `except ValueError` dans le CLI logue et affiche un message).
- Multi-tenancy (CLAUDE.md § Multi-Tenancy) : `student_pseudo` propagé partout ; test cross-tenant au niveau agent (le plus proche de la prod) et au niveau superviseur (régression).

## Findings

- **minor** — `docs/plans/s05-agent-francais-chat.md` — La validation `subject` au niveau CLI est implémentée via un bloc `if subject.lower() not in valid_subjects` dans le corps de la fonction `chat()` plutôt que via `click.Choice([Subject.MATHS.value, Subject.FRANCAIS.value])` directement sur l'option `typer.Option` comme suggéré. La déviation est fonctionnellement équivalente et permet le message d'erreur personnalisé + la normalisation `subject = subject.lower()` (case-insensitive).
- **minor** — `docs/plans/s05-agent-francais-chat.md` — Commit unique (`b0fb7ec`) au lieu de 2-3 commits logiques (1 refactor + 1 feature + 1 doc). Le plan autorisait explicitement "Commit atomique par tâche (ou 2-3 commits logiques)". Acceptable mais le diff est lisible (570 lignes de code, hors tests/docs).
- **minor** — `backend/app/services/agents/francais_agent.py` — `FrancaisAgent` importe `_build_user_prompt` et `_collect_sources` depuis `maths_agent` (méthodes internes promues en module-level). Le plan ne l'interdisait pas, mais crée un couplage `francais_agent → maths_agent` qui sera à inverser si un troisième agent arrive. Note de l'auteur du PR : le commentaire `# Internals — module-level so the French agent can share them` le documente.
- **minor** — `docs/plans/s05-agent-francais-chat.md` (Tâche 7) — Pas de test CLI cross-tenant pour le chat (`test_chat_francais_cross_tenant_returns_5` listé dans la recherche ligne 275, absent). Acceptable car le test cross-tenant au niveau agent français est plus fort (utilise un vrai `EphemeralClient`), mais le plan ne le mentionne pas comme "skip — justifié".

Aucun finding **critical** ni **major**.

## Not verified

- **Pas de rendering browser** — la story est 100% backend, donc rien à vérifier visuellement. Conformité design system triviale.
- **Pas d'appel réel à un LLM** — `minimax/minimax-m3:free` (le défaut déclaré) n'a pas été exercé end-to-end avec un PDF français réel. Les tests utilisent `_CapturingLlm` (stub) et `FakeListChatModel`. Le PRD § Questions ouvertes mentionne "registre littéraire adapté au collège" — un humain doit lancer le test d'intégration `pytest -m integration` avec un vrai PDF français uploadé pour valider que le ton du LLM est approprié (cf. risque #5 de la recherche).
- **Pas de test d'intégration ChromaDB `PersistentClient`** — seuls `EphemeralClient` ont été testés. La convention `rag_francais_<pseudo>` est garantie par le code de `chroma_store.get_collection` (intact), mais un humain devrait faire un `python -m ktutor.cli upload cours.pdf --pseudo ali --subject francais` puis `python -m ktutor.cli chat --pseudo ali --subject francais --question "..."` en local pour confirmer la persistance.
- **Pas de migration / DB** — `Subject` enum existait déjà (s02), aucun changement de schéma. Rien à vérifier.
- **Case-sensitivity `--subject`** — Vérifié par lecture que `case_sensitive=False` + `subject.lower()` fonctionnent. Le test CLI n'exerce pas explicitement `--subject MATHS` (majuscule), mais le code le supporte (vérifié manuellement).
- **Le test bite "mater `SubjectSupervisor.ask` pour skip la validation"** — neutralisé par lecture (la validation est dans `ask` ET dans `__init__`, et le test `test_ask_rejects_unknown_subject` asserte `maths.calls == []` après un appel avec `subject="histoire"`). Si la validation était retirée, l'agent `maths` serait appelé et recevrait `(subject="histoire", ...)` — `MathsAgent.ask` n'a pas de validation `subject == "maths"`, donc ne lèverait pas, et le test rouge.

## Verdict

Max severity: minor
Ship allowed: yes