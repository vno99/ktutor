---
story: s09-api-chat-streaming
reviewer: reviewer (anti-hallucination, fresh context)
date: 2026-09-01
worktree: C:/Workspace/ktutor/.worktrees/s09-api-chat-streaming
branch: feature/s09-api-chat-streaming
commit: 0172c28 feat(api): add /api/chat/stream SSE endpoint (s09)
default_branch_at_review: f255046 (s08 merged)
---

# Review — s09-api-chat-streaming

**Verdict**: ship allowed.

## Test & lint verification (re-run by reviewer)

- `cd backend && python -m pytest` → **397 passed, 2 warnings** (StarletteDeprecationWarning sur httpx/testclient, langchain-community deprecation — pré-existants, hors-scope s09).
- `cd backend && python -m ruff check app tests` → **All checks passed**.
- Worktree : `C:/Workspace/ktutor/.worktrees/s09-api-chat-streaming` (branche `feature/s09-api-chat-streaming`).
- Story diff scope : commit `0172c28` (s09). Le `f255046` (s08) est déjà sur `origin/main` et reproduit localement sur la branche feature — traité comme background, hors-diff s09.

## What was verified

- Chaque nouveau fichier du commit s09 existe sur disque et est câblé exactement comme le plan et l'ADR 010 le décrivent.
- Tous les imports résolvent : `fastapi`, `fastapi.responses.StreamingResponse`, `fastapi.middleware.cors.CORSMiddleware`, `langchain_core.messages.{AIMessage, AIMessageChunk, BaseMessage}`, `pydantic_settings.BaseSettings`. Aucune référence inventée.
- `subjects` dans le superviseur (`Subject.MATHS.value` / `Subject.FRANCAIS.value`) match l'enum canonique.
- `LlmClient.astream` est un passe-plat vers `BaseChatModel.astream` — vérifié via une sous-classe custom `BaseChatModel` dans le test qui exerce le chemin directement.
- L'app FastAPI utilise `StreamingResponse` natif ; `sse-starlette` n'est pas dans `requirements.txt` (D2 honoré).
- `cors_allow_origins: str` est parsé par `cors_allow_origins_list` (property) avant d'être passé à `CORSMiddleware`. CORS rejette les origines non-listées.
- Le router passe `body.pseudo` à `supervisor.astream(subject, body.pseudo, question)` inchangé — cf. `router.py:84-86`.
- Les 7 ACs de la story + le test cross-tenant DoD sont tous présents et nommés.

## Neutralization — what bites

Cinq mutations appliquées, chacune prouvée clean après restore (`git diff --exit-code` sur le fichier, exit 0). Red count par mutation :

| # | Mutated invariant | File | Test(s) qui sont passés rouges | Restored ? |
|---|---|---|---|---|
| 1 | `body.pseudo` passé à `supervisor.astream` | `app/api/chat/router.py:85` | `test_cross_tenant_via_body_swap` — 1 red | oui, `git diff --exit-code` clean |
| 2 | SSE trailing `\n\n` | `app/api/chat/sse.py:30` | `test_each_event_ends_with_double_newline` — 1 red | oui, clean |
| 3 | CORS allow-list non-empty | `app/main.py:53` | `test_cors_preflight_allowed_for_allowlisted_origin` + `test_actual_post_includes_allow_origin_header` — 2 reds | oui, clean |
| 4 | `LlmClient.astream` passe-plat chunks | `app/services/llm/client.py:64-72` | `test_wrapper_astream_yields_aimessage_chunks` — 1 red | oui, clean |
| 5 | `FrancaisAgent.astream` garde sur `subject` | `app/services/agents/francais_agent.py:112-115` | `test_astream_rejects_other_subject` — 1 red | oui, clean |

La mutation "agent pseudo hardcode" (remplacer `pseudo` par `"alice"` dans `MathsAgent.astream`) a été tentée mais **n'a pas mordu** le test existant — `test_astream_uses_retriever_with_correct_pseudo` utilise `expected_pseudo="alice"` ET appelle avec `pseudo="alice"`, donc un hardcode à "alice" produit la même signature d'appel et le test passe. Vérifié manuellement que le hardcode serait attrapé si l'un des deux côtés utilisait un pseudo différent. Le test cross-tenant au niveau router (`test_cross_tenant_via_body_swap`) attrape le hardcode au niveau intégration, donc l'invariant multi-tenant reste protégé — mais le test unitaire au niveau agent a un angle mort connu. Voir **minor 3** ci-dessous.

## Findings

### Critical
Aucun.

### Major
Aucun. Les 7 ACs sont couvertes. L'invariant cross-tenant est protégé par le test router. L'invariant cross-tenant central (router qui passe `body.pseudo` inchangé) mord correctement. Le format stream et les invariants CORS mordent correctement. Le passe-plat `LlmClient.astream` mord correctement.

### Minor

1. **`StreamChunk.event` Literal inclut `"sources"` mais aucun code ne l'émet** (`backend/app/services/agents/types.py:64`). Le plan T2.2 réservait l'event `"sources"` pour une story future ; l'implémentation garde l'union de types mais ni `maths_agent.astream` ni `francais_agent.astream` ne yield jamais un event `event="sources"`. Le router a un commentaire explicite "event == 'sources' is reserved for a future story" et le drop silencieusement. Code mort dans l'union. Fix facile : retirer le literal `"sources"` jusqu'à ce qu'il serve, ou documenter pourquoi il reste.

2. **`chat_stream_heartbeat_ms` setting est déclaré mais jamais lu** (`backend/app/core/config.py:36`). Le plan D6 dit "paramétrable via `chat_stream_heartbeat_ms=0`" mais le router ne lit que `chat_stream_max_chunks`. La variable heartbeat est de la config morte. YAGNI respecté dans l'esprit, mais le champ mort devrait être retiré ou wiré avant la prochaine story qui le lira.

3. **Le test cross-tenant au niveau agent a un angle mort** (`backend/tests/services/agents/test_streaming.py:164-181`). `test_astream_uses_retriever_with_correct_pseudo` utilise `expected_pseudo="alice"` et appelle avec `pseudo="alice"` — donc un hardcode d'un autre pseudo ("bob", "default", etc.) passerait encore le check retriever, et un hardcode à `"alice"` passerait aussi. Une régression future qui hardcode `"alice"` dans l'agent (par ex. "par commodité") passerait ce test unitaire. Le test d'intégration `test_cross_tenant_via_body_swap` (niveau router) attrape la même régression en pratique, mais le test unitaire devrait utiliser des pseudos distincts expected/request pour réellement exercer l'invariant qu'il prétend imposer.

4. **`fresh_settings` fixture est du code mort avec un bug latent** (`backend/tests/api/conftest.py:117-125`). Défini mais jamais référencé par aucun test. Pire, il appelle `get_settings.cache_clear()` ligne 120, mais `get_settings` est une fonction module-level plain (pas `lru_cache`-decorée) — la ligne lèverait `AttributeError` si la fixture était invoquée. Soit retirer la fixture, soit fixer l'appel `cache_clear` (utiliser `config._config_module._settings = None`).

5. **`test_max_chunks_safety_net_stops_runaway_stream` touche aux internals du module** (`backend/tests/api/test_chat_stream.py:336-354`). Le test mute `config_module._settings` directement, réassigne `config_module.get_settings` et le restore, et le restore ne marche que parce que `get_settings` est un attribut module. Il passe aujourd'hui, mais le test est fragile face à un refactor futur qui transformerait `get_settings` en `lru_cache` (le plan l'a déjà considéré dans la recherche). Le chemin propre est l'override FastAPI dependency sur `get_settings` (déjà utilisé par d'autres tests) au lieu de monkeyer le module.

6. **`docs/architecture.md` la liste ADR a ramassé 007/008/009 dans s09** (`docs/architecture.md:351-353`). Le commit s09 ajoute les bullets pour ADRs 007 (MinIO, s01b), 008 (DeepSeek-OCR-2), 009 (SeaweedFS) en plus de l'ADR 010 s09. Ils appartiennent à leurs stories respectives, pas à s09. Défendable comme un petit drive-by fix (architecture.md était en retard sur le repo) mais techniquement drift ; pas un défaut, juste un nit d'hygiène.

7. **Aucun test pour les nouveaux champs `Settings`** (`backend/tests/core/test_config.py`). Le pattern s02-s08 est un test par nouveau setting (default + override-via-env). `cors_allow_origins`, `chat_stream_max_chunks`, `chat_stream_heartbeat_ms` n'ont pas de couverture. Le plan T3.2 ne les imposait pas, mais la convention s02-s08 le fait.

8. **Le test `test_cors_middleware_registered` du plan T3.11 est manquant**. CORS est exercé par `test_cors_preflight_allowed_for_allowlisted_origin` et `test_cors_preflight_rejected_for_other_origin`, donc l'invariant est couvert — mais le test nommé dans le plan n'est pas dans le fichier. Pas un défaut, juste de la conformité plan.

9. **La branche contient s08 + s09 au lieu de s09 rebasé sur `origin/main`**. Le plan T0.1 demande explicitement `git fetch origin && git rebase origin/main` pour intégrer s08. La branche porte s08 comme commit séparé (même contenu, mais le rebase n'a pas eu lieu). Le commit s08 est byte-identique à `origin/main`, donc le merge sera fast-forward, mais le diff de PR porte du bruit s08 (6064 lignes de diff total, dont seulement ~2477 sont s09). Selon AGENTS.md "one single commit at the end of the story" et le plan "Commit unique en fin de story" — la PR a deux commits (`f255046` s08 + `0172c28` s09). Le plan dit aussi "Pas de commit de merge (rebase --no-ff interdit ici)" — mais c'est un rebase qui était voulu, et il n'a pas eu lieu.

## Conformity check

- **AGENTS.md § Backend conventions** : typing, schémas Pydantic, split async/sync, loguru — tous conformes. Logs : pas de `try/except` muets ; le `except ValueError` du router re-raise via `return` après l'event d'erreur, ce qui est acceptable pour SSE (le stream se ferme proprement). Tests : 1 test par AC + cross-tenant — conforme.
- **ADR 010** : D1, D2, D4, D5 documentés. L'ADR omet D3 (que la recherche disait "Option A" aussi — `list[SourceCitation]` chunks-RAG). Petit gap de doc.
- **Design system** : non applicable — s09 est backend-only, pas de changement UI.
- **docs/designs/s09-*.md** : n'existe pas ; pas requis pour backend-only.

## What I could not verify

- **Smoke test `uvicorn` live (T5.4)** — nécessiterait un vrai serveur sur port 8000 et un vrai LLM joignable ; l'exercice `cURL` contre un serveur qui tourne n'a pas été fait. La suite TestClient exerce le même chemin `StreamingResponse`, mais la description de PR claim un smoke test end-to-end. Je fais confiance à ce claim mais ne l'ai pas reproduit.
- **L'ordre réel des tokens LLM avec le modèle upstream `minimax`** — les tests utilisent des doubles stubbés `_ScriptedStreamingLlm` / `BaseChatModel` ; savoir si le vrai adapter `ChatOpenAI` contre OpenRouter yield des chunks dans l'ordre est un claim runtime, pas un invariant testé. Si un modèle futur buffer et émet un gros chunk, le router marche encore (il ne tokenize juste pas).
- **Migration JWT (s15)** — `body.pseudo` du router est l'auth stub, comme documenté dans l'ADR 010. La ligne de migration s15 n'est pas encore écrite.

## Relevant file paths

- `C:/Workspace/ktutor/.worktrees/s09-api-chat-streaming/backend/app/main.py`
- `C:/Workspace/ktutor/.worktrees/s09-api-chat-streaming/backend/app/api/chat/router.py`
- `C:/Workspace/ktutor/.worktrees/s09-api-chat-streaming/backend/app/api/chat/schemas.py`
- `C:/Workspace/ktutor/.worktrees/s09-api-chat-streaming/backend/app/api/chat/sse.py`
- `C:/Workspace/ktutor/.worktrees/s09-api-chat-streaming/backend/app/services/agents/factory.py`
- `C:/Workspace/ktutor/.worktrees/s09-api-chat-streaming/backend/app/services/agents/maths_agent.py`
- `C:/Workspace/ktutor/.worktrees/s09-api-chat-streaming/backend/app/services/agents/francais_agent.py`
- `C:/Workspace/ktutor/.worktrees/s09-api-chat-streaming/backend/app/services/agents/supervisor.py`
- `C:/Workspace/ktutor/.worktrees/s09-api-chat-streaming/backend/app/services/agents/types.py`
- `C:/Workspace/ktutor/.worktrees/s09-api-chat-streaming/backend/app/services/llm/client.py`
- `C:/Workspace/ktutor/.worktrees/s09-api-chat-streaming/backend/app/core/config.py`
- `C:/Workspace/ktutor/.worktrees/s09-api-chat-streaming/backend/tests/api/test_chat_stream.py`
- `C:/Workspace/ktutor/.worktrees/s09-api-chat-streaming/backend/tests/api/conftest.py`
- `C:/Workspace/ktutor/.worktrees/s09-api-chat-streaming/backend/tests/services/agents/test_streaming.py`
- `C:/Workspace/ktutor/.worktrees/s09-api-chat-streaming/backend/tests/services/agents/test_supervisor.py`
- `C:/Workspace/ktutor/.worktrees/s09-api-chat-streaming/backend/tests/services/llm/test_client.py`
- `C:/Workspace/ktutor/.worktrees/s09-api-chat-streaming/docs/decisions/010-fastapi-streaming.md`
- `C:/Workspace/ktutor/.worktrees/s09-api-chat-streaming/docs/plans/s09-api-chat-streaming.md`
- `C:/Workspace/ktutor/.worktrees/s09-api-chat-streaming/docs/research/s09-api-chat-streaming.md`
- `C:/Workspace/ktutor/.worktrees/s09-api-chat-streaming/docs/architecture.md`

## Summary for the gate

- Tous les ACs sont couverts par des tests nommés.
- 397 tests verts, ruff clean.
- 5 mutations red→green sur les invariants centraux (cross-tenant, SSE format, CORS allow-list, `LlmClient.astream` passe-plat, garde `subject` français).
- 0 critical, 0 major, 9 minor (config morte, code mort dans Literal, angle mort test unitaire, fixture morte, fragilité test, doc lag ADR list, couverture config, test manquant, rebase non fait).
- Le ship n'est pas bloqué. Les minors sont documentés pour backlog.

Max severity: minor
Ship allowed: yes
