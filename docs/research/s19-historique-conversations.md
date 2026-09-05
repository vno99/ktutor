---
validated: no
---
# Research — Story s19-historique-conversations

## The five structuring facts

1. **`Conversation` et `Message` n'existent pas dans le code actuel.** `docs/architecture.md:271-287` les décrit dans le schéma cible mais `backend/app/core/database/models.py:1-416` ne les contient pas — il n'y a que `Document`, `Exercise`, `Attempt`, `Evaluation`, `User`, `ParentChildLink`. `init_db()` les créerait à la première migration, mais aucun fichier Alembic ne les pose. **Faux premise du doc à confirmer en planning :** s19 doit ajouter les modèles, pas « simplement » exposer la lecture d'une table qui n'existe pas.
2. **Le stream `/api/chat/stream` (s09) ne persiste rien.** `backend/app/api/chat/router.py:97-138` consomme `supervisor.astream(...)` et forwarde les `StreamChunk` au client SSE sans toucher la base. ADR 010 § « Consequences » ligne 159 le confirme explicitement : « s19 (chat history) will add a second endpoint under the same `/api/chat` prefix (`GET /api/chat/history`). » s09 est la phase « pas d'historique côté backend » ; s19 ferme ce trou.
3. **Le contrat frontend est déjà en place pour le streaming ; pas pour l'historique.** `frontend/lib/api/chat.ts` exporte `parseSSEChunk` et les types `SSEEvent` / `SourceCitation`. Aucun module `lib/api/history.ts` ni page `app/(dashboard)/[locale]/history/page.tsx` n'existe. Le chat reste sous `(public)/[locale]/chat` (pré-JWT, `pseudo` en body) ; s15 le migrera sous `(dashboard)/[locale]/chat` avec JWT — donc la page `/history` doit être côté `(dashboard)/` dès le départ pour éviter une re-migration.
4. **JWT auth + helpers cross-tenant sont déjà câblés depuis s15.** `get_current_user`, `assert_jwt_pseudo_matches_or_403`, et `assert_parent_linked_to_child_or_403` existent (`backend/app/core/auth/middleware.py`). L'AC7 « un élève ne voit que ses conversations » se branche sur le `student_pseudo` extrait du JWT, pas du path. Le contrat RBAC du `CLAUDE.md` dit : `/chat/history` doit suivre la même matrice que `/chat/stream` (parent = lecture seule sur ses enfants, admin = impersonation, élève = soi).
5. **`StreamChunk` expose le nécessaire pour la persistance.** `backend/app/services/agents/types.py:44-65` : trois `event` (`token`, `sources`, `done`), `content` pour les tokens, `sources` sur le `done`. Le router s09 collecte `event.content` pour les `token` et `event.sources` pour le `done`. La persistance côté s19 peut réutiliser ces mêmes hooks sans modifier les agents : il suffit de *consommer* le flux une fois de plus dans le handler pour récupérer (réponse complète concaténée, sources, latence).

## Target story

`docs/stories.md:945-974` — **s19-historique-conversations — Consulter l'historique de mes conversations**.

> As an élève I want consulter l'historique de mes conversations passées so that je retrouve une explication que j'ai eue.

### Acceptance criteria (verbatim)

- AC1. `GET /api/chat/history?limit=20&offset=0` (JWT auth) returns the user's past conversations, newest first.
- AC2. Each conversation includes: `id`, `subject`, `first_question`, `last_activity_at`, `message_count`.
- AC3. `GET /api/chat/history/{conversation_id}` returns the full message thread.
- AC4. The `/history` page lists the conversations and clicking one opens the detail.
- AC5. Pagination uses `limit` + `offset` (no cursor for the POC).
- AC6. A test verifies a student sees only their own conversations.
- AC7. A test verifies pagination works (limit=2 returns 2, offset=2 returns the next 2).

### Dependencies

- s15 (auth). Livré.

## Current state of the code

**Backend — fichiers impliqués ou à créer :**

- `backend/app/core/database/models.py` — pas de `Conversation` / `Message` (à ajouter).
- `backend/app/api/chat/router.py` — `/api/chat/stream` (s09), pas de `/history`. **Note** : le router actuel consomme `supervisor.astream(...)` ligne 100 sans hook de persistance.
- `backend/app/api/chat/schemas.py` — uniquement `ChatStreamRequest`. À étendre avec `ConversationListItem`, `ConversationDetail`, `MessageItem`, etc.
- `backend/app/api/chat/history.py` — **n'existe pas**. Le `docs/architecture.md:57` annonce `chat/` comme « stream, history » mais seul `stream` est codé.
- `backend/app/main.py` — pas encore d'`include_router` pour `/history` puisque le router n'existe pas.
- `backend/app/services/` — pas de service `chat_history` ; à créer ou à intégrer au router.

**Tests :**

- `backend/tests/api/test_chat_stream.py` — uniquement le stream.
- `backend/tests/api/test_chat_history.py` — **n'existe pas**.

**Frontend — fichiers impliqués ou à créer :**

- `frontend/lib/api/chat.ts` — parseur SSE OK. Pas de `lib/api/history.ts`.
- `frontend/lib/stores/chatStore.ts` — pas de cache d'historique.
- `frontend/app/(public)/[locale]/chat/page.tsx` — page chat pré-JWT.
- `frontend/app/(dashboard)/[locale]/history/page.tsx` — **n'existe pas**. À créer. Doit être sous `(dashboard)/` dès le départ (JWT guard côté s15).

**Schéma DB cible (depuis `architecture.md:271-287`) :**

```sql
conversations (
  id UUID PK,
  student_pseudo FK,
  subject,
  first_question TEXT,
  message_count INT,
  last_activity_at
)
messages (
  id PK,
  conversation_id FK,
  role ("user" | "assistant"),
  content TEXT,
  sources JSONB,
  created_at
)
```

⚠️ **Trois écarts à arbitrer en planning** par rapport à ce schéma cible :
- `id` de `messages` est typé `PK` sans précision — UUID recommandé (cohérence avec `Conversation.id`, `Document.id`, `Exercise.id`, `Evaluation.id`).
- `messages.content` est `TEXT` dans le doc mais le `backend` utilise `String(8192)` partout (`Document.filename` = 512, `Evaluation.teacher_comments` = 8192). Un message LLM peut faire plusieurs ko — `String(N)` au-delà de 8192 n'est pas portable SQLite pour la suite de tests. À trancher.
- `messages.sources` est `JSONB` dans le doc mais la codebase utilise `JSON` (portable SQLite) — `architecture.md:230-233` le dit explicitement. Même contrainte ici.

## Anchor points

**Où la feature se branche :**

- **Persistance** : dans le handler `stream_chat` de `backend/app/api/chat/router.py:76-149`. Le `event_generator()` boucle sur `supervisor.astream(...)` ; c'est ici qu'on doit (a) accumuler la réponse, (b) créer/réutiliser la conversation, (c) persister deux lignes `messages` (user + assistant) et (d) mettre à jour la conversation denormalisée. **Stratégie « sans casser le streaming »** : faire la persistance APRÈS que le flux est terminé, dans un `try/finally` autour du `async for`, en collectant la réponse en mémoire pendant le yield.
- **Lecture** : nouveau fichier `backend/app/api/chat/history.py` avec deux endpoints sous `/api/chat/history`. Le `backend/app/main.py` doit l'inclure via `include_router`.
- **Schéma** : `backend/app/core/database/models.py` — ajouter `class Conversation` et `class Message` après `class Evaluation` (logique de regroupement par story).
- **Tests** : `backend/tests/api/test_chat_history.py` (nouveau) + `backend/tests/api/test_chat_stream.py` (étendu pour vérifier que la persistance n'altère pas le stream).
- **Frontend** : `frontend/app/(dashboard)/[locale]/history/page.tsx` (liste) + `frontend/app/(dashboard)/[locale]/history/[conversation_id]/page.tsx` (détail). Module `frontend/lib/api/history.ts` pour les fetch.

**Fonctions / modèles existants à réutiliser :**

- `Depends(get_current_user)` (s15) — extraction JWT.
- `Depends(get_db)` (s15) — session SQLAlchemy.
- `assert_jwt_pseudo_matches_or_403(user, claimed, route)` — garde cross-tenant no-op défensif.
- `Subject` enum — pour typer `subject` (maths / francais).
- `User` model — pour la FK `student_pseudo`.
- `func.now()` et `DateTime(timezone=True)` — pattern d'horodatage.

## Verified APIs / functions

| Symbole | Emplacement | Signature / forme vérifiée |
| --- | --- | --- |
| `SubjectSupervisor.astream` | `app/services/agents/supervisor.py:89-106` | `astream(subject: str, pseudo: str, question: str) -> AsyncIterator[StreamChunk]`. Yields `StreamChunk(event="token"|"done")`. |
| `StreamChunk` | `app/services/agents/types.py:44-65` | `content: str`, `event: Literal["token","sources","done"]`, `sources: list[SourceCitation]`. |
| `SourceCitation` | `app/services/agents/types.py:30-33` | `{filename: str, chunk_index: int}`. |
| `format_sse` | `app/api/chat/sse.py:21-30` | `data: <json>\n\n`, `ensure_ascii=False`. |
| `get_current_user` | `app/core/auth/middleware.py` | FastAPI dependency → `User` ou 401. |
| `assert_jwt_pseudo_matches_or_403` | `app/core/auth/middleware.py` | Garde cross-tenant (no-op si pas de `claimed`). |
| `get_db` | `app/core/database/session.py` | Session SQLAlchemy par requête. |
| `init_db` | `app/core/database/session.py:56` | `Base.metadata.create_all` — applique les nouveaux modèles. |

## Traps & constraints

- **Pas de migration Alembic** : `init_db()` (`session.py:56`) recrée tout le schéma via `Base.metadata.create_all` en dev/CI. Comme pour `Evaluation` en s18, on ajoute les modèles et on laisse `init_db` poser la table. (cf. docstring d'`Attempt` lignes 175-184 — le pattern est explicite : « no Alembic migration is needed because ``init_db()`` applies the full ``Base`` metadata in dev/CI ».)
- **Pas de régression du streaming** : `test_chat_stream.py` (s09) doit continuer à passer tel quel. La persistance doit être opt-in ou ne pas modifier le comportement visible du stream (même chunks, même ordre, même timing). Stratégie : insérer les `messages` et la mise à jour de `Conversation` APRÈS que `done` a été yield (en dehors de la boucle `async for`).
- **Stratégie de regroupement des conversations** : l'AC2 dit `first_question` (singulier) et `message_count`. Options :
  - **(A) Une conversation = (eleve, subject) sans limite de temps** : simple, déterministe, mais une seule conversation par matière par élève. La `first_question` est la toute première question jamais posée.
  - **(B) Une conversation = (eleve, subject, jour calendaire UTC)** : permet plusieurs conversations par matière. Plus naturel côté UX (« mes conversations de mardi »). Risque : un élève qui pose 2 questions à 23:59 et 00:01 finit en 2 conversations.
  - **(C) Une conversation = (eleve, subject, session_id côté client)** : contrôlable par l'UI. Mais l'AC4 dit « the `/history` page lists the conversations and clicking one opens the detail » sans imposer une session_id.
  - **Recommandation recherche (à confirmer en planning)** : (A). Le plus simple, le moins de surface pour un POC, et l'AC1 « past conversations, newest first » fonctionne naturellement. Si on veut (B) plus tard, c'est un ADR.
- **Dénormalisation `first_question` / `message_count`** : `architecture.md:970` le dit explicitement (« denormalize first_question and message_count to avoid scanning all messages on the list endpoint »). Garder la cohérence à chaque `INSERT` message :
  - Sur le **premier** message d'une conversation, `first_question = <question>` et `message_count = 1`.
  - Sur les messages suivants, `message_count += 2` (1 user + 1 assistant) et `last_activity_at = now()`.
  - **Ou** : `message_count` = nombre de *paires* user/assistant. À documenter.
- **Cross-tenant bite (AC6)** : un élève A ne doit pas voir les conversations d'un élève B. La query de liste doit filtrer par `student_pseudo = user.pseudo` (extrait du JWT, jamais du path). Le détail (`GET /chat/history/{id}`) doit vérifier `conversation.student_pseudo == user.pseudo` (ou admin impersonation, ou parent lié via `assert_parent_linked_to_child_or_403`). **Note** : l'AC6 dit « student sees only their own conversations » — pas d'AC explicite sur parent/admin. Le contrat RBAC du `CLAUDE.md` impose l'extension : parent = lecture seule sur enfant lié, admin = tout. Les tests doivent couvrir les 4 edges (eleve own, eleve other, parent linked, parent unlinked, admin) — comme pour s18b.
- **Pagination AC5 + AC7** : `limit` (default 20) + `offset` (default 0), `ORDER BY last_activity_at DESC, id DESC` (le `id DESC` casse les ties pour un tri stable). L'AC7 vérifie `limit=2` puis `offset=2`.
- **Limite de taille des messages** : `String(8192)` côté SQLAlchemy est portable SQLite/PostgreSQL. Au-delà, il faut `Text`. Recommandation recherche : `String(8192)` suffit pour un POC ; on accepte la troncature silencieuse côté Pydantic si on est plus strict (ou on rejette avec 422). À trancher en planning.
- **Pas de Celery, pas de streaming sortant sur `/history`** : lecture simple, JSON. Pas de SSE, pas de file.
- **i18n frontend** : toutes les chaînes via `useTranslations()`. Pas de string en dur.
- **A11y** : la page `/history` est une liste — `<ul>` avec `<li>`, `<Link>` enveloppant chaque conversation, `<h1>` pour le titre, contraste AA.

## Open questions

1. **Stratégie de regroupement (A vs B vs C ci-dessus)** — le planning doit trancher, et la décision se reflète dans un ADR court si elle est non triviale.
2. **`messages.content` : `String(8192)` ou `Text` ?** Le doc cible `TEXT` ; la codebase utilise `String(8192)`. Trancher.
3. **Réutiliser le `supervisor.astream` ou créer un wrapper `supervisor.ask` réutilisable ?** L'option « wrapper dédié `service.record_conversation(stream) -> RecordedConversation` » est plus testable et plus propre. À valider en planning.
4. **Que faire si l'élève pose 2 questions en parallèle (deux onglets) ?** Les deux inserts vont créer deux `Conversation` (option A) — un `UNIQUE` ou un lock applicatif serait nécessaire pour les fusionner. Pour le POC on accepte la collision (warning log + regroupement arbitraire). À documenter dans le plan.
5. **Le `pseudo` du JWT est-il déjà garanti non-vide et conforme regex à ce stade ?** OUI depuis s12 (validation à l'enregistrement) + s15 (claims JWT). Pas de piège.
6. **Y a-t-il un cas d'usage pour purger l'historique ?** Pas dans cette story. Note pour un follow-up.
7. **Le détail (`GET /chat/history/{id}`) renvoie-t-il les sources des messages ?** L'AC3 dit « full message thread » sans préciser. Recommandation : oui, `messages.sources` pour la transparence des citations, conforme au pattern s11b où les sources apparaissent déjà côté stream.

## Real complexity

Le score `docs/stories.md:951` est **2** (« List endpoint + paginated query + frontend history view »). Après lecture du code :

- **Backend** : 2 modèles SQLAlchemy + 1 service de persistance (wrapper du stream) + 1 router avec 2 endpoints + tests. ~5 fichiers touchés.
- **Frontend** : 1 module API + 1 store + 2 pages (liste + détail). ~3-4 fichiers touchés.
- **Intégration** : brancher la persistance sur le flux existant **sans régression** du stream (c'est la partie la plus subtile — la boucle `async for` doit rester telle quelle pour les tests de s09).
- **Tests** : 1 test par AC (7 ACs) + cross-tenant bite (4 edges) + non-régression s09 (re-run `test_chat_stream.py`).

**Verdict recherche : 3** (pas 2). La complexité 2 sous-estime :
- l'absence des modèles (faux premise du doc, à corriger en T1 du plan) ;
- le couplage avec le stream existant (il faut persister sans régresser le streaming, ce qui ajoute une vraie contrainte d'ordonnancement) ;
- la matrice RBAC à 4 edges comme s18b (pas couverte par les ACs, qui ne parlent que d'« élève »).

Un score 3 reste dans le périmètre d'une seule story (≤ 10 tâches en plan). **Pas de split** requis.

## Split proposal

N/A — score 3 ne déclenche pas de split obligatoire. La story tient en un cycle.

---

**Fichiers inventoriés et lus** :
- `docs/stories.md:945-974` (story)
- `docs/architecture.md:1-430` (schéma cible et patterns)
- `docs/decisions/010-fastapi-streaming.md` (ADR streaming)
- `docs/reviews/stories.md` (Stories ready: yes, Max severity: minor)
- `backend/app/api/chat/router.py` (router stream s09, sans persistance)
- `backend/app/api/chat/sse.py` (helper SSE)
- `backend/app/services/agents/types.py` (StreamChunk)
- `backend/app/services/agents/supervisor.py` (SubjectSupervisor.astream)
- `backend/app/services/agents/maths_agent.py` (impl astream)
- `backend/app/core/database/models.py` (modèles existants, **Conversation et Message absents**)
- `frontend/lib/api/chat.ts` (parseur SSE, types)
- `frontend/app/(public)/[locale]/chat/page.tsx` (page chat)
- `frontend/app/(dashboard)/[locale]/` (structure dashboard, **pas de /history**)
