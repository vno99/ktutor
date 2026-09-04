---
id: s15-restrictions-rbac
story: docs/stories.md § s15-restrictions-rbac (lignes 763-794)
base_commit: 87a3c9f
date: 2026-09-03
---

# Research — s15-restrictions-rbac

## Résumé en une ligne

Les fondations JWT/RBAC (s12, s13, s13b, s14) sont **en place** sur `main`. S15 ne construit plus l'authentification : il **branche** `Depends(get_current_user)` dans les deux endpoints restants (`/api/chat/stream` et `/api/documents/upload`), retire `body.pseudo` des contrats, ajoute la garde cross-tenant HTTP-level, et aligne le frontend sur l'identité dérivée du token.

## Périmètre de la story (deps vérifiées)

Source : `docs/stories.md` (AC #1 à #5, complexité déclarée 3) + ADR 005 § JWT, ADR 010 D3 (s15 remplace `body.pseudo` par `request.state.pseudo`).

| Dépendance | Statut sur `main` | Évidence |
| --- | --- | --- |
| `User` model + table `users` (s12) | ✅ livré | `app/core/database/models.py:224-266` |
| Bcrypt + register/login/refresh/logout (s12 + s13) | ✅ livré | `app/api/auth/router.py` |
| JWT RS256 + decode whitelist (s13) | ✅ livré | `app/core/auth/jwt.py:50` `_ALLOWED_ALGORITHMS = ("RS256",)` |
| `get_current_user` (s13) | ✅ livré | `app/core/auth/middleware.py:58-103` |
| `require_role` (s13b) | ✅ livré | `app/core/auth/middleware.py:106-135` |
| Token blacklist + rotation (s13) | ✅ livré | `app/core/auth/token_blacklist.py` |
| Parent-child link (s14) | ✅ livré | `app/api/users/router.py:437-597` |
| Frontend `Authorization: Bearer` interceptor (s13) | ✅ livré | `frontend/lib/api.ts:128-135` |

**La prémisse de s15 tient :** la story dit « ne plus faire confiance à `body.pseudo` », et l'infrastructure qui permet de le faire existe. Pas de re-découverte, pas de re-construction.

## Faits structurants vérifiés dans le code

### Fait 1 — Deux endpoints lisent encore `pseudo` côté body/Form

| Endpoint | Source du `pseudo` | Référence |
| --- | --- | --- |
| `POST /api/chat/stream` | `body.pseudo: str` (Pydantic) | `app/api/chat/router.py:85` (passé à `supervisor.astream`), `app/api/chat/schemas.py:34-44` |
| `POST /api/documents/upload` | `Form(..., alias="pseudo")` | `app/api/documents/router.py:94` (passé à `service.upload(tmp_path, pseudo, subject)` ligne 162) |

Aucun de ces deux endpoints n'a `Depends(get_current_user)` ni `Depends(require_role(...))`. Ils sont publiquement accessibles — la sécurité est aujourd'hui uniquement **post-hoc** dans la couche service.

### Fait 2 — `get_current_user` existe mais n'applique aucune garde cross-tenant

`app/core/auth/middleware.py:58-103` : la dépendance décode le JWT, vérifie l'algorithme, les claims, la blacklist, et **retourne l'objet `User`**. Point. Aucune comparaison entre `user.pseudo` et un éventuel `pseudo` body/URL. La garde cross-tenant est **explicitement hors-scope** de la dépendance ; c'est à l'endpoint (ou à un helper appelé par l'endpoint) de la faire.

### Fait 3 — Le test cross-tenant existant est au niveau service, pas HTTP

`backend/tests/api/test_chat_stream.py:172-193` (`test_cross_tenant_via_body_swap`) :
- Stub l'agent pour qu'il lève `ValueError("different pseudo")` quand `body.pseudo != "alice"`.
- Vérifie que le code SSE `cross_tenant` est émis.

C'est un test **service-level** (l'agent refuse), pas **HTTP-auth-level** (le middleware refuse). Si un attaquant forge un JWT valide pour `bob` et envoie `body.pseudo: "alice"`, le test actuel **ne couvre rien** — la requête aboutit avec un agent qui refuse de servir, et l'attaquant a quand même accédé à la session authentifiée de `bob`. S15 doit ajouter un test qui couvre la couche manquante.

### Fait 4 — Le frontend envoie le `pseudo` en double (cookie + body)

| Source | Fichier | Ligne |
| --- | --- | --- |
| `useAuthStore.getState().pseudo` (cookie `path=/; max-age=30d`) | `frontend/lib/stores/chatStore.ts:91,139` | lu et envoyé dans `body.pseudo` |
| Idem (upload FormData) | `frontend/lib/stores/uploadStore.ts:129,144` | `formData.append('pseudo', pseudo)` |
| `Authorization: Bearer` | `frontend/lib/api.ts:128-135` | déjà attaché par l'interceptor (s13) |

L'interceptor JWT est **déjà en place** (s13). Le `pseudo` dans le body est devenu redondant — c'est précisément cette redondance que s15 supprime côté frontend.

### Fait 5 — Les modèles `Document`, `Exercise`, `Attempt` ont un `student_pseudo` non-FK (s15 ferme cette boucle)

`app/core/database/models.py:67-72`, `:119-124`, `:185-190` : `student_pseudo: Mapped[str] = mapped_column(String(64), nullable=False, index=True, # FK intentionally deferred to s15 migration (users table not yet created).)`.

**Faux** : la table `users` existe depuis s12 (commit vérifié). Les FKs « différées à s15 » ne l'étaient pas par impossibilité — elles étaient différées par **stratégie** (s12 voulait rester focalisé). S15 peut maintenant matérialiser ces FKs en Alembic (si la décision est prise) ou laisser `init_db()` en `create_all` les créer implicitement (cf. décision §8 ci-dessous).

## Ancres d'implémentation

### Backend — fichiers à toucher

| Fichier | Changement attendu |
| --- | --- |
| `app/api/chat/router.py` | Ajouter `user: User = Depends(get_current_user)` ; retirer `body.pseudo` ; appeler `supervisor.astream(user.pseudo, body.subject, body.question)` ; ajouter la garde cross-tenant si un `pseudo` reste dans le body (période de transition) ; logger `security.cross_tenant_attempt` |
| `app/api/chat/schemas.py` | Retirer `pseudo: str` de `ChatStreamRequest` ; le commentaire « migration to JWT-derived pseudo happens in s15 » devient désuet, le supprimer |
| `app/api/documents/router.py` | Ajouter `user: User = Depends(get_current_user)` ; retirer `pseudo: str = Form(...)` ; passer `user.pseudo` à `service.upload(...)` ; logger `security.cross_tenant_attempt` |
| `app/api/documents/schemas.py` | Pas de changement (les schémas sont uniquement la réponse) |
| `app/core/auth/middleware.py` | Étendre `get_current_user` (ou nouveau helper) avec une **option** de garde : comparer le `pseudo` JWT au `pseudo` body/URL si présent ; admin bypass ; lever 403 `forbidden` (pas 401) avec un `code: "cross_tenant"` distinct |
| `app/core/database/models.py` | Documenter la matérialisation des FKs (s15 ferme la dette) |

### Backend — fichiers de tests à toucher

| Fichier | Test à ajouter |
| --- | --- |
| `backend/tests/api/test_chat_stream.py` | `test_jwt_required_returns_401_when_missing` ; `test_jwt_required_returns_401_when_invalid` ; `test_cross_tenant_body_swap_returns_403` (HTTP-level) ; `test_admin_can_stream_with_other_pseudo` |
| `backend/tests/api/test_documents_upload.py` | Idem : tests JWT-required + cross-tenant 403 (admin bypass) |
| `backend/tests/api/test_auth_router.py` | Aucun changement (déjà couvert) |

### Frontend — fichiers à toucher

| Fichier | Changement attendu |
| --- | --- |
| `frontend/lib/stores/chatStore.ts` | Retirer `pseudo` du body envoyé ; passer uniquement `{subject, question}` ; reconnaître le code `cross_tenant` côté UI (le router émet `StreamErrorEvent.code: "cross_tenant"` qui existe déjà) |
| `frontend/lib/stores/uploadStore.ts` | Retirer `formData.append('pseudo', ...)` ; le token dans le header suffit |
| `frontend/lib/api/chat.ts` | Vérifier que `ChatStreamErrorCode` inclut `'cross_tenant'` (c'est déjà le cas côté backend ; aligner côté frontend) |

## APIs vérifiées (telles que le code les expose aujourd'hui)

### `POST /api/chat/stream` (s09, **non-migré en s15**)

```http
POST /api/chat/stream
Content-Type: application/json

{ "pseudo": "alice", "subject": "maths", "question": "2+2 ?" }
```

- Aucun header d'auth requis. `body.pseudo` est la seule source d'identité.
- Réponse : `text/event-stream` (cf. `app/api/chat/router.py:64-134`).
- Erreur SSE : `{error, code}` où `code ∈ {"cross_tenant", "no_subject", "invalid_pseudo", "unknown"}` (cf. `app/api/chat/schemas.py:62-77`).

### `POST /api/documents/upload` (s10, **non-migré en s15**)

```http
POST /api/documents/upload
Content-Type: multipart/form-data; boundary=...

pseudo=alice
subject=maths
file=@cours.pdf
```

- Aucun header d'auth requis. `pseudo` est un champ Form.
- Réponse 201 : `{document_id, status, chunks_count, ocr_confidence}` (cf. `app/api/documents/schemas.py:35-54`).
- Erreur : `{error, code}` où `code ∈ {"invalid_pseudo", "invalid_file", "ocr_failure", "storage_failure"}` (cf. `app/api/documents/schemas.py:57-72`).

### `GET /api/auth/me` — point d'attention

`get_current_user` retourne un `User`, ce qui rend trivial l'ajout d'un endpoint `GET /api/auth/me` qui retourne `{pseudo, role, created_at}`. **Hors-scope s15** mais l'ancrage est déjà en place.

## Pièges et contraintes

1. **Le pseudo dans le body ne disparaît pas en un seul commit** si on veut garder la rétro-compat. S15 peut :
   - (a) **Hard cut** : retirer `body.pseudo` partout dans la même PR, frontend et backend alignés. Casse les clients qui envoient encore `body.pseudo`, mais le seul client connu est le frontend livré par le même repo — donc safe.
   - (b) **Transition** : accepter les deux, logger `security.cross_tenant_attempt` quand `body.pseudo != jwt.pseudo` (sauf admin), puis dans une story ultérieure retirer le champ.
   - **Recommandation : (a) hard cut**, parce qu'on contrôle les deux côtés. Documenter la décision dans un ADR court si (b) est choisi.
2. **Le `get_current_user` ne doit pas devenir un monstre**. Le helper de cross-tenant doit être séparé (ex. `assert_jwt_pseudo_matches(user, claimed_pseudo)` dans `app/core/auth/middleware.py`), pas greffé sur la dépendance. Raison : `get_current_user` est appelé par `require_role` (s13b), par `logout` (s13), par `add_child`/`list_children` (s14) — aucun de ces trois n'a de `body.pseudo` à comparer.
3. **Le test HTTP-level cross-tenant doit forger un JWT valide pour `bob`** et envoyer `body.pseudo: "alice"`. Le test actuel (s09) forge via stub LLM — pour s15, il faut un helper de forge JWT (déjà implicite via `create_access_token` en s13). Si le helper n'existe pas dans `conftest.py`, l'ajouter ; sinon, l'utiliser.
4. **Admin bypass**. S15 AC#2 dit « la requête est rejetée (ou processed pour admin) ». Le test admin-bypass doit prouver qu'un admin peut streamer/upload pour le pseudo d'un élève. C'est le seul cas où la garde cross-tenant cède — le parent **ne doit pas** pouvoir envoyer `body.pseudo: "enfant_X"` s'il n'est pas admin (le parent a déjà son propre accès à `/api/users/{parent}/children`, et il n'a pas de raison légitime d'usurper un enfant à `/api/chat/stream` ou `/api/documents/upload` qui sont des actions **personnelles**).
5. **Logs `security.cross_tenant_attempt`** : ne jamais logger le JWT, le `jti`, le `body` complet, ou le fichier uploadé. Logger : `caller_pseudo`, `claimed_pseudo`, `route`, `role`, `request_id`. (cf. AGENTS.md § Backend logging.)
6. **Le frontend ne doit PAS continuer à envoyer `body.pseudo`**. Si l'API rejette un body contenant un `pseudo` (en dur cut), le frontend reçoit un 422 Pydantic — mais le `chatStore.send()` ne se base pas sur le 422 pour le moment. Le store doit ignorer silencieusement tout résidu de `body.pseudo` (le retirer du `JSON.stringify` suffit).
7. **Le `pseudo` côté frontend reste dans le cookie** (`useAuthStore.pseudo`) — il sert à afficher le nom dans le `<Header>` et à l'UI. C'est la **source d'affichage**, pas la **source d'auth**. Cette distinction doit être explicite dans le store (déjà le cas en pratique).
8. **Les FKs `student_pseudo → users.pseudo`** : matérialiser ou pas ? S12 a choisi `init_db()` plutôt qu'Alembic (cf. ADR 010). Si s15 suit la même doctrine, **pas d'Alembic**, et les FKs sont créées implicitement par `Base.metadata.create_all` au prochain démarrage. Si on choisit Alembic, c'est un ADR séparé. **Recommandation : pas d'Alembic, confirmer `init_db()` suffit** (vérifier que la déclaration `ForeignKey("users.pseudo", ondelete="CASCADE")` côté `ParentChildLink` ne casse pas `create_all` quand on ajoute la même FK aux autres tables — réponse : non, c'est la même syntaxe, déjà supportée).

## Questions ouvertes (à confirmer au planning)

1. **Hard cut vs transition** sur `body.pseudo` → recommandation hard cut (voir Piège 1).
2. **Admin bypass** sur la garde cross-tenant → confirmation : admin peut-il streamer/upload pour **n'importe quel pseudo** ? Le récit s15 dit « processed for admin » sans borner ; l'ADR 005 suggère que oui. À acter formellement dans le plan.
3. **Parent bypass** ? Le récit s15 ne le mentionne pas. **Recommandation : pas de bypass parent** — un parent a son propre compte, et le lien parent-enfant est un modèle d'**accès indirect** (le parent lit les données de l'enfant via `GET /api/users/{parent}/children` puis un endpoint enfant), pas un modèle d'**impersonation**. Une story ultérieure (s18+ ?) traitera le « parent agit pour le compte de l'enfant ».
4. **`GET /api/auth/me`** — in-scope s15 ou s18+ ? S15 n'en parle pas, mais le terrain est prêt. **Recommandation : out-of-scope**, pour ne pas gonfler le plan.
5. **FK `student_pseudo → users.pseudo`** matérialisée dans cette PR ? **Recommandation : oui, dans le même commit, sans Alembic** (cf. Piège 8). Permet aux tests d'utiliser des FK ON DELETE CASCADE et aligne le code sur la réalité.

## Complexité re-scoring

| Source | Score | Justification |
| --- | --- | --- |
| `docs/stories.md` (déclaré) | 3 | Bornes « trois endpoints à modifier, tests, frontend » |
| Re-score après lecture du code | **3** | Bornes confirmées. La story **ne construit plus** d'auth (s12-s14 l'ont fait), elle **branche** l'existant. Risques集中在 dans le hard cut (Piège 1), l'admin bypass (Question 2), et le retrait cohérent côté frontend (Piège 6). Aucun n'est un 5. |

Pas de split proposé — la story tient en ≤ 10 tâches.

## Plan d'attaque esquissé (pour le `/ks-plan` à venir)

1. Étendre `get_current_user` (ou nouveau helper) avec `assert_jwt_pseudo_matches(user, claimed)`.
2. Migrer `POST /api/chat/stream` : `Depends(get_current_user)`, retrait `body.pseudo`.
3. Migrer `POST /api/documents/upload` : `Depends(get_current_user)`, retrait `Form(pseudo)`.
4. Ajouter les 3 tests HTTP-level par endpoint (401 sans token, 401 token invalide, 403 cross-tenant sauf admin).
5. Aligner le frontend : `chatStore` + `uploadStore` retirent `pseudo` du payload.
6. Materialiser les FKs `student_pseudo → users.pseudo` dans les modèles (sans Alembic, via `create_all`).
7. Vérifier que tous les tests existants (`pytest backend/tests`) passent.
8. Lancer le linter / typecheck.
9. Capturer le verdict (max severity, ship allowed) dans `docs/reviews/s15-restrictions-rbac.md`.

## Verdict

- **Prémisse** : valide. Les fondations existent.
- **Risque principal** : la transition frontend (Piège 1, 6) et l'admin bypass (Question 2). Tous deux ont une réponse simple.
- **Verdict complexité** : 3 (statu quo).
- **Pas de split** requis.
