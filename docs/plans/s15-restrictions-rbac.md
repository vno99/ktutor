---
validated: yes
---

# Plan — Story s15-restrictions-rbac

Branch: `feature/s15-restrictions-rbac`
Research: `docs/research/s15-restrictions-rbac.md` — read it first; this plan does not repeat it.
Design: `docs/designs/s15-restrictions-rbac.md` — backend-only, no mockup.

## Target story

Brancher `Depends(get_current_user)` sur les deux endpoints restants (`POST /api/chat/stream`, `POST /api/documents/upload`), retirer `pseudo` du payload, ajouter la garde cross-tenant HTTP-level avec admin bypass (cf. ADR 005 § « RBAC »), aligner le frontend (chatStore + uploadStore) sur l'identité JWT.

| Endpoint | Body in (post-s15) | Body out | Codes |
| --- | --- | --- | --- |
| `POST /api/chat/stream` | `{subject, question}` | `text/event-stream` | 200, 401, 403, 422 |
| `POST /api/documents/upload` | FormData(`subject`, `file`) | 201 `{document_id, status, chunks_count, ocr_confidence}` | 201, 401, 403, 413, 415, 422, 500 |

**Acceptance criteria** (5, tous dans le scope) — AC1-AC2 comportement, AC3-AC5 tests.

## Tasks (ordered)

1. [x] **Étendre `backend/app/core/auth/middleware.py`** avec un helper `assert_jwt_pseudo_matches_or_403(user, claimed, *, route) -> None` :
   - Signature : `assert_jwt_pseudo_matches_or_403(user: User, claimed: str | None, *, route: str) -> None`.
   - Si `claimed is None` (pas de `pseudo` dans le body/URL) → no-op (le caller n'a rien à comparer).
   - Si `claimed` est fourni **et** `user.role is UserRole.ADMIN` → no-op + log DEBUG `auth.middleware.admin_bypass pseudo={user.pseudo} route={route}`.
   - Si `claimed` est fourni **et** `claimed.lower() == user.pseudo.lower()` (case-insensitive aligné sur `func.lower()` du s12) → no-op.
   - Sinon → log INFO `security.cross_tenant_attempt caller={user.pseudo} claimed={claimed} role={user.role.value} route={route}` **puis** raise `HTTPException(403, detail={"error": "Accès refusé.", "code": "forbidden"})`. **Aucun mot de passe, token, jti, ou body dans le log.**
   - **Vérification** : `python -c "from app.core.auth.middleware import assert_jwt_pseudo_matches_or_403"` passe.

2. [x] **Migrer `POST /api/chat/stream`** dans `backend/app/api/chat/router.py` + `schemas.py` :
   - **`schemas.py`** : retirer `pseudo: str` du `ChatStreamRequest` (ligne 34-44). Retirer le commentaire « migration to JWT-derived pseudo happens in s15 » qui devient désuet. Le schéma résultant est `{subject: Literal["maths","francais"], question: str}`.
   - **`router.py`** :
     - Ajouter le paramètre `user: User = Depends(get_current_user)` à `stream_chat`.
     - Retirer `body.pseudo` de l'appel à `supervisor.astream` (ligne 85) → passer `user.pseudo` (le tenant key dérive du JWT).
     - **Garde cross-tenant** : appeler `assert_jwt_pseudo_matches_or_403(user, None, route="/api/chat/stream")` (no-op ici puisque `body.pseudo` n'existe plus — la garde est defensive pour les futures régressions ; voir Tâche 3 pour la version "si jamais le body revient").
     - **Vérification** : `python -c "from app.api.chat.router import router; print([r.path for r in router.routes])"` liste `/api/chat/stream` ; `python -c "from app.api.chat.schemas import ChatStreamRequest; print(ChatStreamRequest.model_fields.keys())"` ne contient pas `pseudo`.

3. [x] **Migrer `POST /api/documents/upload`** dans `backend/app/api/documents/router.py` :
   - Retirer `pseudo: str = Form(..., min_length=1, max_length=MAX_PSEUDO_CHARS)` de la signature de `upload` (ligne 94).
   - Ajouter `user: User = Depends(get_current_user)`.
   - Remplacer `service.upload(tmp_path, pseudo, subject)` (ligne 162) par `service.upload(tmp_path, user.pseudo, subject)`.
   - **Garde cross-tenant** : appeler `assert_jwt_pseudo_matches_or_403(user, None, route="/api/documents/upload")` (no-op).
   - **Imports** : ajouter `from app.core.auth.middleware import get_current_user, assert_jwt_pseudo_matches_or_403` et `from app.core.database.models import User`.
   - **Vérification** : `python -c "from app.api.documents.router import router; print([r.path for r in router.routes])"` ; `grep -n "pseudo" backend/app/api/documents/router.py` ne montre plus `Form(.*pseudo`.
   - **Note d'implémentation** : FastAPI's `Form()` / `File()` ne rejectent pas les champs inconnus. Pour matérialiser le hard cut (rejet d'un `Form(pseudo)` legacy), un check explicite via `await request.form()` valide la liste des champs et raise 422 si extras. Test ``TestDocumentsUploadJwtRequired::test_body_pseudo_field_is_rejected_with_422`` couvre ce cas.

4. [ ] **Matérialiser les FKs `student_pseudo → users.pseudo`** dans `backend/app/core/database/models.py` :
   - `Document.student_pseudo` (ligne 67) : remplacer `String(64)` par `String(64), ForeignKey("users.pseudo", ondelete="CASCADE")` (mêmes paramètres que `ParentChildLink` ligne 297-308 ; case-sensitivity alignée sur l'index `uq_users_pseudo_lower`).
   - `Exercise.student_pseudo` (ligne 119) : idem.
   - `Exercise.document_id` (ligne 133) : ajouter `ForeignKey("documents.id", ondelete="CASCADE")` (commentaire ligne 134 « FK to documents.id (deferred to s15) » devient désuet).
   - `Attempt.exercise_id` (ligne 180) : ajouter `ForeignKey("exercises.id", ondelete="CASCADE")` (commentaire ligne 181 idem).
   - `Attempt.student_pseudo` (ligne 185) : idem `String(64), ForeignKey(...)`.
   - **Pas d'Alembic** (cf. ADR 010 — `init_db()` est l'outil canonique, `Base.metadata.create_all` crée les FKs au prochain démarrage). SQLite in-memory tests pick up automatiquement.
   - **Vérification** : `python -c "from app.core.database.models import Document, Exercise, Attempt; [print(c.name, list(c.foreign_keys)) for c in (Document.__table__.columns + Exercise.__table__.columns + Attempt.__table__.columns)]"` liste les FKs.

5. [ ] **Étendre `backend/app/api/chat/schemas.py`** avec un Literal `StreamErrorCode` aligné (déjà existant `StreamErrorEvent.code: Literal["cross_tenant", "no_subject", "invalid_pseudo", "unknown"]`, ligne 62-77) — **aucune modification** : le code est déjà aligné, on documente juste que l'event 403-côté-auth utilise **le même `code: "forbidden"` que les autres 403** (au niveau HTTP, pas SSE), et que le SSE `cross_tenant` reste pour le cas service-level pré-existant.
   - **Vérification** : `grep -n "cross_tenant" backend/app/api/chat/schemas.py` confirme la présence dans `StreamErrorEvent.code`.

6. [ ] **Tests `POST /api/chat/stream`** dans `backend/tests/api/test_chat_stream.py` (nouvelles classes, ≥ 6 tests) :
   - **Fixtures à dupliquer** depuis `test_users_create.py:79-162` + `test_auth_middleware.py:48-117` (cf. research trap 9 + AGENTS.md « Pas de refactor transverse ») : `rsa_keypair`, `_point_settings`, `db_engine`, `session_factory`, `client`, `seeded_admin`, `seeded_eleve_alice`, `seeded_eleve_bob` (3 élèves pour les tests cross-tenant).
   - **Helper à dupliquer** : `_bearer(user) -> dict[str, str]` (équivalent de `_admin_bearer` dans `test_users_create.py:165-166`).
   - **`TestChatStreamJwtRequired`** :
     - `test_no_token_returns_401_invalid_token` : pas de header `Authorization` → 401 avec `code: "invalid_token"`, body SSE **non ouvert** (la réponse est `application/json`, pas `text/event-stream`).
     - `test_junk_token_returns_401_invalid_token` : `Authorization: Bearer garbage` → 401.
     - `test_expired_token_returns_401_invalid_token` : `create_access_token(seeded_eleve_alice.pseudo, seeded_eleve_alice.role, expires_delta=timedelta(seconds=-1))` → 401.
   - **`TestChatStreamCrossTenant`** (le test qu'il manquait en s09) :
     - `test_eleve_bob_token_with_no_body_pseudo_streams_for_bob` : bearer `bob` + body `{subject: "maths", question: "Q"}` (pas de `pseudo`) → 200 SSE, l'agent stub reçoit `pseudo="bob"` (pas `alice`).
     - `test_eleve_bob_token_cannot_impersonate_alice_via_body_pseudo_returns_403` : bearer `bob` + body `{pseudo: "alice", subject: "maths", question: "Q"}` → **422 Pydantic** (le champ `pseudo` n'existe plus dans le schéma) — variante 1. Variante 2 (si on garde une période de transition où `pseudo` reste dans le body) : 403 `forbidden` + log `security.cross_tenant_attempt`. **Décision : variante 1** (hard cut, le seul client connu est le frontend livré par le même repo — cf. research Piège 1). Si on choisit la transition, la Tâche 2 doit être ré-écrite pour **garder** `body.pseudo` et appeler `assert_jwt_pseudo_matches_or_403(user, body.pseudo, route="...")`.
     - `test_admin_token_can_stream_for_any_pseudo` : bearer admin + body `{subject: "maths", question: "Q"}` → 200, l'agent stub reçoit `pseudo` extrait du contexte (par défaut, l'admin lui-même ; on n'implémente PAS l'admin impersonation explicite via body.pseudo en s15, c'est hors-scope — l'admin n'a pas de cas d'usage légitime sur `/api/chat/stream` et `/api/documents/upload` en s15). Cf. Question 2 du research.
   - **Régression** : `test_existing_stream_happy_path_unchanged` (s09) : bearer `alice` + body `{subject: "maths", question: "2+2 ?"}` → 200, 3 tokens SSE + 1 `done`. Garantit qu'on n'a pas cassé le contrat.
   - **Vérification** : `pytest backend/tests/api/test_chat_stream.py -v` → tous les anciens tests + les nouveaux passent.

7. [x] **Tests `POST /api/documents/upload`** dans `backend/tests/api/test_documents.py` (nouvelles classes, ≥ 5 tests) :
   - **Fixtures** : dupliquer les fixtures de chat (cf. Tâche 6). Réutiliser `client`, `sample_pdf_path`, `tmp_upload` (existants dans `conftest.py`).
   - **`TestDocumentsUploadJwtRequired`** :
     - `test_no_token_returns_401_invalid_token` : pas de `Authorization` + FormData `{subject, file}` (sans `pseudo`) → 401, body `{"error": "Token invalide ou expiré.", "code": "invalid_token"}`.
     - `test_junk_token_returns_401_invalid_token` : idem avec token garbage.
   - **`TestDocumentsUploadCrossTenant`** :
     - `test_eleve_bob_token_uploads_for_bob` : bearer `bob` + FormData `{subject: "maths", file: <pdf>}` (pas de `pseudo`) → 201, `document.student_pseudo == "bob"` en DB (vérifier via `session.query(Document).filter_by(id=response["document_id"]).one().student_pseudo == "bob"`).
     - `test_eleve_bob_token_with_body_pseudo_alice_returns_422` : bearer `bob` + FormData `{pseudo: "alice", subject: "maths", file: <pdf>}` → 422 Pydantic (champ `pseudo` n'existe plus dans la signature de l'endpoint).
     - `test_admin_token_uploads_for_admin_itself` : bearer admin + FormData `{subject: "maths", file: <pdf>}` → 201, `document.student_pseudo == admin.pseudo` (admin s'upload pour lui-même ; pas d'impersonation via body, cf. Tâche 6).
   - **Régression** : `test_existing_upload_happy_path_unchanged` (s10) : bearer `alice` + FormData → 201 avec le même body. Garantit qu'on n'a pas cassé le contrat de réponse.
   - **Vérification** : `pytest backend/tests/api/test_documents.py -v` → tous les anciens tests + les nouveaux passent.

8. [ ] **Test du helper `assert_jwt_pseudo_matches_or_403`** dans `backend/tests/core/test_middleware.py` (nouveau fichier, ≥ 6 tests) :
   - **Fixtures** : `seeded_admin`, `seeded_eleve_alice` (dupliquées depuis `test_users_create.py:79-162`).
   - **`TestAssertJwtPseudoMatches`** :
     - `test_claimed_none_is_noop` : `claimed=None` → no raise, no log INFO (DEBUG seulement).
     - `test_claimed_matches_user_pseudo_is_noop` : alice + "alice" → no raise.
     - `test_claimed_matches_user_pseudo_case_insensitive` : alice + "ALICE" / "Alice" → no raise.
     - `test_claimed_mismatch_raises_403_for_eleve` : alice + "bob" → 403 `forbidden`, log INFO `security.cross_tenant_attempt`.
     - `test_claimed_mismatch_is_noop_for_admin` : admin + "alice" → no raise, log DEBUG `auth.middleware.admin_bypass`.
     - `test_log_does_not_contain_token_material` : `caplog`-style sur le buffer `_isolated_loguru_sink` → aucune ligne ne contient `Bearer `, `jti`, `password`, `token`, ou le body.
   - **Vérification** : `pytest backend/tests/core/test_middleware.py -v` → 6/6 pass.

9. [ ] **Aligner le frontend** : `frontend/lib/stores/chatStore.ts` + `frontend/lib/stores/uploadStore.ts` :
   - **`chatStore.ts`** : retirer `pseudo` du body envoyé (ligne 138-142 : `body: JSON.stringify({pseudo, subject: input.subject, question: input.question})` → `body: JSON.stringify({subject: input.subject, question: input.question})`). **Note** : la lecture `useAuthStore.getState().pseudo` ligne 91 reste pour le guard `isValidPseudo` local (UX, pas auth) — c'est le `pseudo` du cookie, pas une donnée envoyée.
   - **`uploadStore.ts`** : retirer `formData.append('pseudo', pseudo)` (ligne 144). `formData` ne contient plus que `subject` et `file`. Le `pseudo` ligne 129 reste pour le guard local.
   - **Vérification** : `grep -n "pseudo" frontend/lib/stores/chatStore.ts frontend/lib/stores/uploadStore.ts` ne montre plus `pseudo` dans les `body:` / `formData.append`.

10. [ ] **Run full backend + frontend test suite** :
    - `pytest backend/tests/ -v --tb=short` → 0 régression sur les tests s09, s10, s12, s13, s13b, s14 existants.
    - `cd frontend && npx tsc --noEmit` → 0 erreur TypeScript (couvre la Tâche 9).
    - `cd backend && ruff check app/ tests/` → 0 nouveau warning.
    - `cd backend && mypy app/` → 0 nouvelle erreur.
    - **Vérification** : tous les jobs CI restent verts.

11. [ ] **Conventional commit unique** : `feat(api): enforce JWT-derived tenant key on /api/chat/stream and /api/documents/upload (s15)` couvrant tous les fichiers modifiés + créés + le research + le plan + le design.
    - **Vérification** : `git log -1` montre un seul commit avec tous les fichiers.

## Run interdicts

- **Pas de migration Alembic** : `init_db()` (`backend/app/core/database/session.py:56`) crée les FKs implicitement via `Base.metadata.create_all` au prochain démarrage. SQLite in-memory les pick up automatiquement. Cf. ADR 010.
- **Pas de nouvel endpoint** : s15 ne crée pas `GET /api/auth/me`, pas de `DELETE /api/users/{parent}/children/{child}`, pas d'admin impersonation explicite. Tout ça est hors-scope (cf. Questions 3-4 du research).
- **Pas de `require_role` ici** : les deux endpoints migrés utilisent `get_current_user`, pas `require_role` (ils sont accessibles aux 3 rôles, la garde est cross-tenant, pas rôle). C'est l'inverse de s13b et s14.
- **Pas de parent bypass sur la garde cross-tenant** : seul l'admin bypass (cf. ADR 005). Un parent utilise son propre JWT, pas celui de son enfant, pour streamer/upload. (Le parent lit les données de l'enfant via `GET /api/users/{parent}/children`, c'est un modèle d'accès indirect, pas d'impersonation — extension future, hors-scope s15.)
- **Pas de transition `body.pseudo`** : hard cut (le seul client connu est le frontend livré par le même repo, donc safe). Documenté en Piège 1 du research. Si on revient sur cette décision au planning, ré-écrire la Tâche 2 et 3 pour garder `body.pseudo` et appeler `assert_jwt_pseudo_matches_or_403(user, body.pseudo, ...)`.
- **Pas de log du password, hash, token, jti, ou body** dans la nouvelle log line `security.cross_tenant_attempt` (vérifié par `TestAssertJwtPseudoMatches::test_log_does_not_contain_token_material`).
- **Pas de nouveau composant React / nouveau fichier dans `frontend/components/`** : la Tâche 9 modifie uniquement les stores existants. Les `Card error` pour les 401/403 sont déjà en place (cf. design § 3.1-3.2).
- **Pas de `i18n` nouvelle clé** : `auth.errors.forbidden` (« Action non autorisée. ») est déjà prévue dans le namespace `auth` du design system ; pas d'extension à créer. Si on l'ajoute quand même côté frontend, c'est uniquement dans `frontend/messages/fr.json` (et `en.json`) sous `auth.errors.forbidden`.
- **Pas de refactor transverse** : la duplication des fixtures `rsa_keypair`, `_point_settings`, `db_engine`, etc. depuis `test_users_create.py` est assumée (cf. AGENTS.md + research trap 9). Le helper `assert_jwt_pseudo_matches_or_403` est dans `middleware.py` (pas dans un nouveau `auth/helpers.py`).
- **Pas de commit sur la branche par défaut** : tout part sur `feature/s15-restrictions-rbac` (worktree dédié). Le squash-merge vers `main` est manuel après review.
- **Pas de session globale dans les tests** : chaque test crée son propre `db_engine` (cf. pattern `test_users_create.py:79-92`) pour ne pas polluer.

## The point everything turns on

**La décision centrale** : la garde cross-tenant est une **comparaison explicite** entre `user.pseudo` (JWT) et un éventuel `pseudo` body/URL, avec **admin bypass** (cf. ADR 005). Elle est implémentée comme un **helper appelé par l'endpoint**, pas comme une logique greffée sur `get_current_user` — parce que `get_current_user` est appelé par des endpoints sans `pseudo` body/URL (logout, add_child, list_children), et la garde y serait toujours no-op.

Trois pièges à surveiller :

1. **Hard cut `body.pseudo` casse les tests s09 et s10**. Le plan **met à jour** `test_chat_stream.py` et `test_documents.py` pour retirer `pseudo` des body des tests existants (Tâches 6 et 7 incluent des tests de régression). Si l'implémenteur oublie de mettre à jour les tests, ils restent à 422 (Pydantic refuse `pseudo`).

2. **FK `student_pseudo → users.pseudo` peut casser des tests s01-s10 qui seedent `Document` / `Exercise` / `Attempt` avec un `student_pseudo` qui n'existe pas dans `users`**. Le plan **garde `init_db()` (pas Alembic)** et la FK est créée au prochain démarrage, donc les tests existants qui font `Document(student_pseudo="alice")` cassent si `User(pseudo="alice")` n'existe pas dans la même transaction. **Mitigation** : dans les fixtures de test, créer le `User` AVANT le `Document` (pattern déjà en place dans `test_users_create.py:79-117`). Le reviewer vérifiera que les tests existants qui touchent `Document` / `Exercise` / `Attempt` ont leur fixture utilisateur en place.

3. **Le helper `assert_jwt_pseudo_matches_or_403` doit être importé du bon endroit** : `app.core.auth.middleware`, pas un nouveau module. Si l'implémenteur crée `app/core/auth/helpers.py`, il faudra un ADR pour expliquer pourquoi (probablement pas justifié — duplication mineure, refactor transverse = s15+).

Vérification finale par le reviewer : (a) `grep -n "Depends(get_current_user)" backend/app/api/chat/router.py backend/app/api/documents/router.py` montre bien l'import ; (b) `grep -n "Form.*pseudo" backend/app/api/documents/router.py` ne retourne RIEN ; (c) `grep -n "pseudo" backend/app/api/chat/schemas.py` ne montre que les références non-body (StreamErrorEvent, par exemple).

## Files touched

**Créés** :
- `backend/tests/core/test_middleware.py` (~120 lignes, 6 tests)
- `docs/research/s15-restrictions-rbac.md` (déjà créé)
- `docs/designs/s15-restrictions-rbac.md` (déjà créé, no mockup)
- `docs/plans/s15-restrictions-rbac.md` (ce fichier)

**Modifiés** :
- `backend/app/core/auth/middleware.py` (~30 lignes ajoutées : helper `assert_jwt_pseudo_matches_or_403` + docstring)
- `backend/app/api/chat/router.py` (~5 lignes : ajout `user: User = Depends(get_current_user)`, retrait `body.pseudo`, garde)
- `backend/app/api/chat/schemas.py` (~5 lignes : retrait `pseudo` du `ChatStreamRequest`)
- `backend/app/api/documents/router.py` (~5 lignes : ajout `user: User = Depends(get_current_user)`, retrait `Form(pseudo)`, garde)
- `backend/app/core/database/models.py` (~10 lignes : ajout `ForeignKey(...)` sur 5 colonnes, suppression des commentaires « deferred to s15 »)
- `backend/tests/api/test_chat_stream.py` (régression : retrait `pseudo` des body existants, ~5 lignes ; ajout 6 tests cross-tenant, ~150 lignes)
- `backend/tests/api/test_documents.py` (régression : retrait `pseudo` des body existants, ~5 lignes ; ajout 5 tests cross-tenant, ~130 lignes)
- `frontend/lib/stores/chatStore.ts` (~2 lignes : retrait `pseudo` du body)
- `frontend/lib/stores/uploadStore.ts` (~2 lignes : retrait `formData.append('pseudo', ...)`)

**Non touchés (volontairement)** :
- `backend/app/core/auth/jwt.py` — pas de modification JWT (s15 n'émet pas de token)
- `backend/app/core/auth/passwords.py` — pas de hash dans s15
- `backend/app/core/auth/token_blacklist.py` — pas de blacklist dans s15
- `backend/app/core/auth/__init__.py` — le commentaire « s13 / s15 will land here » est déjà désuet (s12-s14 ont atterri) ; on **n'y touche pas** car c'est un commentaire cosmétique hors-scope
- `backend/app/api/auth/router.py` — s12-s13 inchangés
- `backend/app/api/users/router.py` — s13b-s14 inchangés (utilisent déjà `get_current_user` / `require_role`)
- `backend/app/api/users/schemas.py` — pas de nouveau schéma
- `backend/app/main.py` — `chat_router` et `documents_router` déjà montés (s09, s10)
- `backend/app/api/documents/schemas.py` — schémas de réponse uniquement, pas de body
- `backend/scripts/` — pas de bootstrap
- `frontend/lib/api.ts` — l'interceptor `Authorization: Bearer` est déjà en place (s13)
- `frontend/lib/stores/authStore.ts` — le `pseudo` cookie reste pour l'UI (`<Header>`)
- `frontend/app/`, `frontend/components/` — pas de nouveau composant
- `frontend/messages/` — pas de nouvelle clé i18n (les erreurs utilisent le namespace `auth` existant)

## Test strategy

**Couche principale** : tests d'API (FastAPI TestClient + SQLite in-memory + StaticPool + `app.dependency_overrides[get_db]`) — pattern `test_users_create.py:79-117`. C'est la couche qui prouve les ACs 1-5.

**Couche fixtures** : duplication assumée depuis `test_users_create.py` (cf. AGENTS.md + research trap 9). 3 fixtures `seeded_*` à dupliquer : `seeded_admin`, `seeded_eleve_alice`, `seeded_eleve_bob`.

**Tests d'isolation cross-tenant (AC3 + AC5)** :
- `TestChatStreamCrossTenant::test_eleve_bob_token_uploads_for_bob` (le bearer `bob` ne peut pas streamer pour `alice` via body)
- `TestChatStreamCrossTenant::test_eleve_bob_token_cannot_impersonate_alice_via_body_pseudo_returns_403` (l'AC5 explicite)
- `TestDocumentsUploadCrossTenant::test_eleve_bob_token_uploads_for_bob`
- `TestDocumentsUploadCrossTenant::test_eleve_bob_token_with_body_pseudo_alice_returns_422`

**Tests unitaires du helper** : `test_middleware.py::TestAssertJwtPseudoMatches` (6 tests) couvre les branches no-op, mismatch, admin bypass, case-insensitive.

**Tests qui n'existent pas et n'existent pas besoin d'exister** :
- Pas de test E2E frontend (Playwright) — les changements frontend sont minimes (2 lignes), couverts par `tsc --noEmit` + une vérification manuelle.
- Pas de test d'intégration PostgreSQL (POC local, SQLite suffit).
- Pas de test d'admin impersonation explicite (hors-scope, Question 2 du research).

**Couverture attendue** : ≥ 17 nouveaux tests (6 chat + 5 upload + 6 middleware) + tests existants mis à jour (régression). Tous indépendants, tous passants sur SQLite/CI. La review vérifiera qu'aucun test n'est skipped ou xfail sans justification.

## Definition of Done

- [ ] Tous les ACs 1-5 sont couverts par un test qui passe (`pytest backend/tests/ -v`).
- [ ] Aucune régression : les tests s09, s10, s12, s13, s13b, s14 restent verts.
- [ ] Lint clean : `ruff check backend/app/api/chat/ backend/app/api/documents/ backend/app/core/auth/ backend/tests/` → 0 issue.
- [ ] Typecheck clean : `mypy backend/app/api/chat/ backend/app/api/documents/ backend/app/core/auth/` → 0 issue.
- [ ] Frontend typecheck : `cd frontend && npx tsc --noEmit` → 0 issue.
- [ ] Multi-tenancy (cf. AGENTS.md § DoD) : tests d'isolation cross-tenant obligatoires pour AC3 + AC5 — `TestChatStreamCrossTenant::*` et `TestDocumentsUploadCrossTenant::*` passent.
- [ ] Observabilité : `security.cross_tenant_attempt` loggue avec `caller`, `claimed`, `role`, `route` (jamais password/hash/token — vérifié par `TestAssertJwtPseudoMatches::test_log_does_not_contain_token_material`).
- [ ] Conventional commit unique : `feat(api): enforce JWT-derived tenant key on /api/chat/stream and /api/documents/upload (s15)`.
- [ ] PR ouverte depuis `feature/s15-restrictions-rbac` vers `main` avec description structurée (résumé, ACs cochées, points d'attention sur le hard cut `body.pseudo`, l'admin bypass, les FKs matérialisées).

<< IP Mike: task granularity, what a good plan contains/avoids. >>
