# Review — s19-historique-conversations

Reviewer: anti-hallucination (fresh context)
Worktree: `C:\Workspace\ktutor\.worktrees\s19-historique-conversations\`
Branch: `feature/s19-historique-conversations`
Diff: `git diff main...feature/s19-historique-conversations` (single commit `d763f2c feat: add chat history (s19)`)

## Verdict

Max severity: minor
Ship allowed: yes

## Summary

L'implémentation suit le plan `docs/plans/s19-historique-conversations.md` (validé yes), respecte la recherche, l'ADR 015 et les conventions du `CLAUDE.md` / `AGENTS.md`. Les 9 tâches T1-T9 sont livrées dans un commit unique, le test suite est vert (728 backend + 72 frontend), le lint et le typecheck sont propres, l'i18n check passe. Les décisions load-bearing du plan sont toutes respectées : `Conversation` + `Message` ajoutés sans Alembic, `UNIQUE(student_pseudo, subject)`, `String(8192)` pour `content`, persistance stream en `try/finally` APRÈS la boucle `async for` et gatée par `CHAT_PERSIST_HISTORY`, RBAC 4 edges (eleve own/other, parent linked/unlinked, admin) avec 404 (pas 403) sur cross-tenant detail, pas de surface parent sur l'endpoint list, helper `formatRelativeTime` au lieu d'un composant `<RelativeTime>`, pas de Skeleton loader, toutes les chaînes via `useTranslations('history')`.

## Plan compliance

| Tâche | Statut | Notes |
| --- | --- | --- |
| T1 — Modèles `Conversation` et `Message` | ✓ | `backend/app/core/database/models.py:430-565`. `UNIQUE(student_pseudo, subject)` lignes 460-466, `CheckConstraint(role IN ('user','assistant'))` lignes 530-535, `String(8192)` content ligne 551, `String(16)` role ligne 546. Pas d'Alembic. |
| T2 — `ChatHistoryService` read-side | ✓ | `backend/app/services/chat_history/service.py`. Filtre `student_pseudo` en SQL (list l.89-98, detail l.124-127), pas en Python. |
| T3 — Router `history.py` + schemas | ✓ | `backend/app/api/chat/history.py` + `history_schemas.py`. `prefix="/api/chat"`, pas de nouvel `include_router` top-level. |
| T4 — RBAC 4 edges | ✓ | Tests eleve own/other, parent linked/unlinked, admin. Cross-tenant detail → 404 (helper `_check_tenant_access` catch 403 → re-raise 404). Parent utilise `assert_parent_linked_to_child_or_403` (pas `assert_jwt_pseudo_matches_or_403`). |
| T5 — Persistance stream | ✓ | `try/finally` APRÈS `async for` dans `event_generator`. Gated par `chat_persist_history` setting. Erreur agent → `full_response` vide → skip. |
| T6 — Mounting | ✓ | `backend/app/main.py:76-77`. |
| T7 — Frontend | ✓ | 6 fichiers créés (lib/api/history.ts, lib/intl/relativeTime.ts, 2 pages, 2 clients). |
| T8 — i18n + Playwright + a11y | ✓ | `fr.json` + `en.json` namespace `history` + `header.navHistory`. `e2e/history.spec.ts` 7/7 passés. axe-core fr + en verts (corrections `text-text-primary` sur pill français > 4.5:1, `text-text-secondary` sur role label > 4.5:1). |
| T9 — ADR 015 + commit | ✓ | `docs/decisions/015-...`. Commit unique `d763f2c`. |

## Run interdicts

Tous les 13 interdits du plan sont respectés (no Alembic, UNIQUE only, SQL-side filter, 404-not-403 sur cross-tenant detail, no `GET /api/chat/history/{id}/messages` sub-endpoint, subject None=all / invalid=422, no `<RelativeTime>`, no parent list bypass, no JWT/bearer/body/message logging, no `docs/stories.md` edit, `Enum(Subject, native_enum=False)`, no Skeleton).

## Anti-hallucination checks

- Tous les imports vérifiés : `Callable` depuis `collections.abc`, `select` depuis `sqlalchemy`, `Session` depuis `sqlalchemy.orm`, `SourceCitation` depuis `agents.types`, `format_sse` depuis `chat.sse`, helpers auth depuis `core.auth.middleware`, `get_settings` depuis `core.config`, `get_session_factory` depuis `database.session`.
- Signatures conformes au plan : `ChatHistoryService(session_factory)`, `list_conversations(*, student_pseudo, subject, limit, offset)`, `get_conversation_with_messages(*, student_pseudo, conversation_id)`.
- `stream_chat` utilise `user.pseudo` (pas `body.pseudo`) pour la persistance.
- La persistance ouvre une seconde session via `get_session_factory()` (différente de la `get_db` dependency de l'endpoint), conformément à l'interdit « pas de session partagée ».
- Le ruff auto-fix sur `test_service.py` (set-comprehension `{r.id for r in page1}.isdisjoint({r.id for r in page2})`) préserve l'invariant AC7.

## Rules compliance

- Conventions backend (snake_case, Pydantic, loguru JSON, type hints, async I/O) respectées.
- Aucun ADR existant contredit : ADR 005 (RBAC bypass admin) honoré, ADR 011 (Zustand hydrate client-side only) respecté, ADR 015 créé pour cette story.
- Design system : tokens utilisés (bg-primary, bg-accent-warm, text-text-primary/secondary, etc.), aucun nouveau token introduit.
- L'écran respecte l'intent du design : liste + détail, pills matière, pagination, source pills, loading state avec aria-busy, not-found avec bouton retour.

## Tests

| Suite | Résultat |
| --- | --- |
| `pytest backend/tests` | 728 passés (full suite, aucune régression s09/s15/s17/s18/s18b). |
| `ruff check backend/` | Propre. |
| `tsc --noEmit` (frontend) | Propre (1 warning pré-existant dans DashboardClient, hors scope s19). |
| `bash frontend/scripts/check-i18n.sh` | `OK (no hardcoded UI strings detected)`. |
| `pnpm exec playwright test e2e/history.spec.ts` | 7/7 passés (responsive 360/768 + axe-core fr/en). |
| Vitest (history + relativeTime) | 19/19 passés. |

**Bite prouvé par neutralisation** : le reviewer a patché le service pour retirer `WHERE student_pseudo = :pseudo`, le test `test_list_history_other_eleve_sees_only_own` a cassé avec « Cross-tenant LEAK : bob should see 1 row but sees 2 » — fichier restauré ensuite. Le filtre SQL sur `student_pseudo` est mordered par les tests.

## Findings

### Minor

1. **Documentation accuracy** — `backend/app/api/chat/router.py:277-280` : le commentaire dit « the `finally` is skipped » quand la branche `ValueError` appelle `return`. En Python, `return` exécute bien le `finally` ; la garde `if persist and full_response:` à la ligne 281 empêche correctement la persistance quand `full_response` est vide (cas du `ValueError` avant tout token). Le comportement est correct, le commentaire est trompeusement négatif. À reformuler en « the `full_response` guard prevents any DB write on the error path ».
2. **Plan deviation on aria-busy** — Le plan dit « aria-busy="true" sur le `<ul>` ». L'implémentation pose `aria-busy` sur le `<div>` parent (`HistoryListClient.tsx:144`). Le `<ul>` n'existe qu'en état succès (rendu conditionnel), donc le placer sur le `<ul>` n'aurait aucun signal ; sur le `<div>` parent c'est fonctionnellement équivalent et sémantiquement plus correct. Acceptable, pas un fix.
3. **Docstring inaccuracy** — `backend/tests/api/test_chat_history.py:462` : le docstring dit « the second page has 1 row » mais le seed est 5 rows, donc la page 2 (`offset=2`) a 2 rows et la page 3 (`offset=4`) a 1 row. Les assertions ligne 479 (`len(page2["items"]) == 2`) sont correctes ; seul le docstring est faux. À corriger.
4. **Bottom tab bar missing on mobile** — Le design appelle un bottom tab bar mobile (5 entrées : chat / upload / history / dashboard). L'implémentation ajoute history au top nav (Header) mais il n'y a pas de bottom tab bar component. Le plan a explicitement prévu le cas « if it is hardcoded to 4, the implementation adds the entry inline with a one-line change » — fait. Le composant bottom tab bar n'existe pas dans le boilerplate actuel, c'est un pré-existing gap (s11a l'a peut-être figé à 4, le plan le signale). À documenter en design system gap (déjà fait dans `docs/designs/s19-historique-conversations.md` § Design system gaps #3). Pas un fix s19, à traiter en s22 (UX/a11y pass).

### Not verified by this review

- **e2e Playwright contre un vrai dev server** : le reviewer a exécuté `pnpm exec playwright test e2e/history.spec.ts` (qui passe 7/7), mais un humain doit aussi ouvrir `http://localhost:3000/fr/history` en viewport 360px pour valider le rendu réel et l'absence de scroll horizontal.
- **Rendu navigateur réel** : à valider visuellement (smartphone 360px + tablette 768px), switch de langue via `LanguageSwitcher`, et un coup de screen reader (NVDA / VoiceOver) sur l'aria-live loading et `aria-current="page"`.
- **Comportement de la persistance sous 100+ streams concurrents** : la session est ouverte via `get_session_factory()` après la boucle (conforme au plan). Le pool de connexions n'est pas stressé par cette story, mais un test de charge réel est un follow-up de perf, pas un test s19.
- **404-not-403 sur cross-tenant detail sous race** : si la conversation est supprimée entre le load et le check, la réponse est 404 (helper catch 403 → raise 404). Un cross-tenant attacker ne peut pas distinguer « exists then deleted » de « doesn't exist », conforme au plan. Acceptable.

## Files reviewed

Backend (modèles, service, router, schemas, config, tests) :
- `backend/app/core/database/models.py`
- `backend/app/services/chat_history/service.py`
- `backend/app/api/chat/history.py`
- `backend/app/api/chat/history_schemas.py`
- `backend/app/api/chat/router.py`
- `backend/app/api/chat/__init__.py`
- `backend/app/main.py`
- `backend/app/core/config.py`
- `backend/tests/api/test_chat_history.py`
- `backend/tests/api/test_chat_stream.py`
- `backend/tests/services/chat_history/test_service.py`
- `backend/tests/core/test_models.py`

Frontend (lib, pages, components, i18n, e2e) :
- `frontend/lib/api/history.ts` + `history.test.ts`
- `frontend/lib/intl/relativeTime.ts` + `relativeTime.test.ts`
- `frontend/app/(dashboard)/[locale]/history/page.tsx`
- `frontend/app/(dashboard)/[locale]/history/HistoryListClient.tsx`
- `frontend/app/(dashboard)/[locale]/history/[conversation_id]/page.tsx`
- `frontend/app/(dashboard)/[locale]/history/[conversation_id]/HistoryDetailClient.tsx`
- `frontend/components/Header.tsx`
- `frontend/messages/fr.json` et `en.json`
- `frontend/e2e/history.spec.ts`

Docs (story + ADR) :
- `docs/research/s19-historique-conversations.md`
- `docs/designs/s19-historique-conversations.md` et `.html`
- `docs/plans/s19-historique-conversations.md` (validé yes)
- `docs/decisions/015-chat-history-conversation-granularity-and-storage.md`

## Conclusion

L'implémentation est complète, testée, et conforme au plan. Les 4 findings sont des notes de qualité mineures (commentaires trompeurs, docstring imprécise, écart de plan sur aria-busy qui est en fait une amélioration, tab bar mobile documenté comme gap design system) — aucun n'affecte la correctness ni la sécurité. Le gate mécanique peut être passé.

Max severity: minor
Ship allowed: yes
