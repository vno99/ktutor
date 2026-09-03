---
validated: yes
---
# Plan — Story s13-login-eleve

Branch: `feature/s13-login-eleve`
Research: `docs/research/s13-login-eleve.md` — read it first; this plan does not repeat it.
Design: `docs/designs/s13-login-eleve.md` (3 écrans : `/login`, `/register`, Header connecté).

## Target story

**s13-login-eleve — Se connecter et obtenir un JWT** (Phase 3). Reprend les 9 ACs `docs/stories.md` lignes 658-668. Complémente s12 (register, table `users`, bcrypt) par le login, le refresh, le logout, le middleware JWT, et — annoncé par le design s12 § 6 — les écrans frontend `/login` et `/register` (l'écran register que s12 n'a pas pu produire). Story à double scope : backend (JWT + 3 endpoints) **et** frontend (formulaires login/register + Header connecté + i18n `auth.*`).

**Note de périmètre** : la story s13 **introduit** le JWT mais **ne gate pas** encore les routes `(public)` — la protection `(dashboard)/` arrive en s15 (cf. research § Traps 5 + ADR 011 « le pseudo reste en cookie en s13, le JWT remplace en s15 »). L'unique « protecteur » visible de s13 est le Header (qui affiche « Se connecter » ou l'avatar selon `authStore.hydrated + tokens`).

**Open questions tranchées par le plan** (cf. research § Open questions) :
- Q1 tokens en `localStorage` (POC, dette s15+ documentée).
- Q2 un seul store Zustand (`authStore` étendu : `pseudo` reste, on ajoute `accessToken`/`refreshToken`/`role`).
- Q3 script `generate_jwt_keys.py` **inclus** (sans lui, l'app ne démarre pas — supporting task).
- Q4 `POST /api/auth/logout` **inclus** (sinon l'affordance « Se déconnecter » n'a pas de sens ; ~10 lignes + 1 test).
- Q5 claims additionnels `jti` (UUID) + `type` (`access` | `refresh`) **inclus** — n'entre pas en conflit avec AC7 (« contains the claims X » n'exclut pas d'autres claims).
- Q6 CORS : aucun changement (config déjà alignée).

## Tasks (ordered)

> Chaque tâche est petite, vérifiable, ancrée sur un test quand la règle est observable. Les références aux lignes sont sur la version actuelle d'`origin/main` (post-merge s12).

### Backend — bootstrap & config

1. [x] **Ajouter `pyjwt[crypto]>=2.8` à `backend/requirements.txt` section Auth.** Le suffixe `[crypto]` tire `cryptography` transitivement, qui fournit RSA + PEM. Pas de test direct (dépendance externe) ; vérification : `pip install -r backend/requirements.txt` réussit et `import jwt; jwt.algorithms.get_default_algorithms()["RS256"]` répond.
2. [x] **Étendre `Settings` (`backend/app/core/config.py` après ligne 162) avec 5 champs JWT** : `jwt_private_key_path: str = "./keys/jwt_private.pem"`, `jwt_public_key_path: str = "./keys/jwt_public.pem"`, `jwt_algorithm: str = "RS256"` (pinned, jamais `none` — Trap 1), `jwt_access_token_expire_minutes: int = 30` (AC3), `jwt_refresh_token_expire_days: int = 7` (AC4). Ajouter les 5 vars dans `backend/.env.example` et `.env.example` à la racine (sections distinctes `# Auth (s13)` et `# Frontend`).
3. [x] **Créer `backend/scripts/generate_jwt_keys.py`** — script idempotent : si `./keys/jwt_private.pem` et `./keys/jwt_public.pem` existent déjà, ne rien faire ; sinon générer une paire RSA 2048 via `cryptography.hazmat.primitives.asymmetric.rsa.generate_private_key(public_exponent=65537, key_size=2048)`, écrire la privée au format PEM PKCS8 (chiffrée non, le POC n'a pas de passphrase), la publique en `SubjectPublicKeyInfo`. Ajouter `keys/` au `.gitignore` (les clés ne sont JAMAIS commit). Vérification : `python backend/scripts/generate_jwt_keys.py && python backend/scripts/generate_jwt_keys.py` (2e run no-op).

### Backend — core auth : JWT, blacklist, middleware

4. [x] **Créer `backend/app/core/auth/token_blacklist.py`** — un `set[str]` de `jti` révoqués, exposé via `add(jti: str)`, `is_revoked(jti: str) -> bool`, `clear()` (utile en tests). Un module-level `_revoked: set[str] = set()`, thread-safe pour le POC (FastAPI sync dans `def` endpoint = pas de race). Test : `tests/core/test_token_blacklist.py` couvre add/is_revoked/clear + idempotence de `add`.
5. [x] **Créer `backend/app/core/auth/jwt.py`** avec 4 fonctions :
   - `_load_private_key() -> RSAPrivateKey` / `_load_public_key() -> RSAPublicKey` (lecture PEM via `cryptography.hazmat.primitives.serialization.load_pem_private_key` / `load_pem_public_key`, depuis `settings.jwt_*_key_path`).
   - `create_access_token(pseudo: str, role: UserRole, expires_delta: timedelta | None = None) -> str` — claims `{sub: pseudo, role: role.value, iat, exp, jti: uuid4(), type: "access"}`, signe avec privée via `jwt.encode(payload, _load_private_key(), algorithm="RS256")`.
   - `create_refresh_token(pseudo: str, role: UserRole) -> str` — idem avec `type: "refresh"` et `exp = now + 7 days`.
   - `decode_token(token: str, expected_type: Literal["access","refresh"]) -> dict` — `jwt.decode(token, _load_public_key(), algorithms=["RS256"], options={"require": ["sub","role","iat","exp","jti","type"]})`, vérifie `decoded["type"] == expected_type`, vérifie `not token_blacklist.is_revoked(decoded["jti"])` (sinon `raise jwt.InvalidTokenError("token revoked")`). **Le whitelist `algorithms=["RS256"]` est codé en dur ici (Piège 1, jamais `alg: none`).**

   Test `tests/core/test_jwt.py` :
   - `create_access_token` produit un JWT décodable par `jwt.decode` avec la publique.
   - Les 4 claims AC7 sont présents (`sub`, `role`, `iat`, `exp`) **plus** `jti` et `type: "access"` (Q5).
   - Round-trip : `decode_token(create_access_token(...), "access")` → claims d'origine.
   - Un token avec `alg: none` est rejeté (Piège 1) — test : `jwt.encode({"sub":"ali","role":"eleve","exp":...}, key="", algorithm="none")` → `decode_token` lève.
   - Un `jti` blacklisté est rejeté.
   - Un access token passé à `decode_token(..., "refresh")` est rejeté (Piège 3).
   - Un token expiré (`exp = now - 1`, généré via `expires_delta=timedelta(seconds=-1)`) est rejeté par `decode_token` (AC9).
6. [x] **Créer `backend/app/core/auth/middleware.py`** avec :
   - `get_current_user(authorization: str | None = Header(default=None, alias="Authorization"), db: Session = Depends(get_db)) -> User` — extrait le bearer, `decode_token(token, "access")`, query `db.query(User).filter(User.pseudo == claims["sub"]).one_or_none()` ; si user None (n'existe plus) ou token invalide → `HTTPException(401, detail={error, code: "invalid_token"})`. 401 **générique** (Piège 2 bis : ne pas leaker qu'un token est valide mais que le user a été supprimé — message identique à token invalide).
   - `require_role(*allowed: UserRole)` — décorateur-factory qui prend une `get_current_user = Depends(...)` et un `role: UserRole = Depends(get_current_user)` puis lève `HTTPException(403, detail={error, code: "forbidden"})` si `role not in allowed`.

   Test `tests/api/test_auth_middleware.py` :
   - `get_current_user` avec token valide → `User` retourné, claims corrects.
   - Sans header `Authorization` → 401 `invalid_token`.
   - `Authorization: Bearer <junk>` → 401 `invalid_token`.
   - Token expiré → 401 (AC9, neutralisation : `expires_delta=timedelta(seconds=-1)`).
   - Token avec `jti` blacklisté (via `token_blacklist.add(jti)` après login) → 401.
   - `require_role(UserRole.ADMIN)` avec un JWT `eleve` → 403 `forbidden`.
   - `require_role(UserRole.ADMIN)` avec un JWT `admin` → OK (test happy path).

### Backend — schémas & endpoints

7. [x] **Étendre `backend/app/api/auth/schemas.py`** avec :
   - `LoginRequest(pseudo: constr(pattern=r"^[a-zA-Z0-9_]+$", min_length=3, max_length=32), password: constr(min_length=1, max_length=128))` — on re-valide la regex côté serveur (défense en profondeur), `min_length=1` car la validation forte est côté `bcrypt` (et on veut 401 générique, pas 422).
   - `TokenPairResponse(access_token: str, refresh_token: str, token_type: Literal["bearer"] = "bearer", expires_in: int)` — `expires_in` = `settings.jwt_access_token_expire_minutes * 60` (en secondes, conforme OAuth2).
   - `RefreshRequest(refresh_token: str)`.
   - `AuthErrorResponse(error: str, code: Literal["invalid_credentials","invalid_token","forbidden","expired","token_revoked"])`.
   - Réutiliser `RegisterErrorResponse` pour `pseudo_taken` / `invalid_pseudo` / `weak_password` (s12).
8. [x] **Étendre `backend/app/api/auth/router.py`** avec 3 endpoints (un seul fichier, cf. AGENTS.md « un `router.py` par sous-domaine ») :
   - `POST /api/auth/login` — `request: LoginRequest, response: Response, db: Session = Depends(get_db)` :
     1. Query `db.query(User).filter(func.lower(User.pseudo) == request.pseudo.lower()).one_or_none()`.
     2. **Piège 2** : si `user is None`, appeler quand même `verify_password(request.password, DUMMY_HASH)` (constante module-level, hash bcrypt valide jeté une fois pour toutes ; ex. `hash_password("dummy_password_for_timing")` calculé au load via `bcrypt.hashpw(b"x"*32, bcrypt.gensalt(12))` puis gelé). Sans cela, l'attaquant time-attack l'existence du pseudo.
     3. Si `user is not None and verify_password(request.password, user.password_hash)` → créer `access = create_access_token(user.pseudo, user.role)`, `refresh = create_refresh_token(user.pseudo, user.role)`, retourner `TokenPairResponse(...)`. Log structuré `{"event": "login_success", "pseudo": user.pseudo, "role": user.role.value, "request_id": ...}` — **sans le password, le hash, ou les tokens** (Trap 16).
     4. Sinon → `HTTPException(401, detail={error: "Pseudo ou mot de passe incorrect.", code: "invalid_credentials"})`. Log `{"event": "login_failed", "pseudo_provided": request.pseudo, "request_id": ...}` (pseudo fourni mais pas de hash ni de token).
   - `POST /api/auth/refresh` — `request: RefreshRequest, db: Session = Depends(get_db)` :
     1. `claims = decode_token(request.refresh_token, "refresh")` (peut lever 401 → on laisse remonter en 401 `invalid_token`).
     2. `user = db.query(User).filter(User.pseudo == claims["sub"]).one_or_none()` ; si None → 401 `invalid_token` (utilisateur supprimé).
     3. **Blacklist l'ancien refresh** : `token_blacklist.add(claims["jti"])` (rotation, ADR 005).
     4. Émet une nouvelle paire (access + refresh) avec le même rôle que l'ancien (Piège 3 renforcé : on relit le rôle depuis la DB, pas depuis le token, pour gérer un changement de rôle par admin entre-temps — cohérent avec s13b).
     5. Log `{"event": "token_refreshed", "pseudo": user.pseudo, "request_id": ...}`.
   - `POST /api/auth/logout` — `user: User = Depends(get_current_user)` :
     1. Récupère le `jti` du access token courant (réutilise `decode_token` + extraction).
     2. `token_blacklist.add(jti)`.
     3. Retourne 204 No Content.
     4. Log `{"event": "logout", "pseudo": user.pseudo, "request_id": ...}`.

   Test `tests/api/test_auth_login.py` (hermétique, in-memory SQLite + StaticPool, fixtures copiées verbatim de `test_auth_register.py:32-70`) :
   - **AC1 + AC7** : login happy path → 200, `TokenPairResponse` valide, `jwt.decode` confirme claims `sub=ali`, `role="eleve"`, présence `iat`/`exp`/`jti`/`type="access"`. `expires_in == 1800`.
   - **AC2** : token décodé avec la publique RS256 réussit ; tentative avec un `RSAPublicKey` d'une autre paire échoue (Piège 1 renforcé : la signature est bien RSA).
   - **AC3** : `exp - iat == 30 * 60` (vérifier `expires_in` + décoder le token).
   - **AC4** : refresh token `exp - iat == 7 * 86400`.
   - **AC5** : `POST /api/auth/refresh` avec un refresh valide → 200, nouvelle paire. L'ancien refresh (même `jti`) est maintenant blacklisté → second appel au `/refresh` avec l'ancien → 401 `invalid_token`.
   - **AC6** : `{"pseudo": "ali", "password": "wrong"}` → 401, body `{"detail": {"code": "invalid_credentials"}}`. Le message ne contient ni "introuvable", ni "n'existe pas" (regex check).
   - **AC6 bis (Piège 2, timing)** : test qui appelle `/login` 50× avec (a) pseudo inexistant et (b) pseudo existant + mauvais password. La médiane des deux distributions doit être à < 50ms l'une de l'autre (P95 < 200ms, marge large pour CI). Skip avec `pytest.mark.skipif` si la machine est trop lente (variable d'env `KTUTOR_SKIP_TIMING=1`).
   - **AC8** : `assert decode_token(access)["sub"] == "ali"` — partie du test happy path.
   - **AC9** : générer un access expiré via `create_access_token("ali", UserRole.ELEVE, expires_delta=timedelta(seconds=-1))`, hit un endpoint protégé (ex. `/api/auth/logout` qui requiert `get_current_user`) → 401 `invalid_token`.
   - **Logout** : login → access valide → `/logout` → 204. Réutiliser l'access token sur un endpoint protégé → 401 `invalid_token` (jti blacklisté).
   - **Pas de token dans les logs** (Trap 16) : capture `loguru` dans un buffer, login + refresh + logout, grep `buffer` pour `eyJ` (début d'un JWT) et pour les `jti` UUIDs → 0 match.
   - **Register → login (parcours nominal)** : crée un user via `/register`, login immédiat → 200. Vérifie que le `User` créé par s12 est bien lu (s12 et s13 partagent la même table).

### Frontend — store, API, i18n

9. [x] **Étendre `frontend/lib/stores/authStore.ts`** :
   - Ajouter champs : `accessToken: string | null`, `refreshToken: string | null`, `role: "eleve" | "parent" | "admin" | null`.
   - Actions : `setTokens({accessToken, refreshToken, role, pseudo})` (persist dans `localStorage` sous la clé `ktutor.auth` — JSON sérialisé), `clearTokens()` (efface `localStorage` + reset), `hydrate()` étendu : à l'init, lire `localStorage.ktutor.auth` si présent, sinon retomber sur le cookie `pseudo` (rétro-compat ADR 011), sinon rester `hydrated: true, pseudo: null`. Sélecteur `isAuthenticated = state.hydrated && state.accessToken !== null`.
   - **Pas de SSR** : `persist` est en `localStorage` qui n'existe pas côté serveur, donc `hydrate()` est appelé dans un `useEffect` au mount du `<Header>` (déjà fait — `setHydrated(true)`). L'extension suit le même pattern.
   - Test : Zustand `vitest` (à créer — voir « Test strategy » ci-dessous) — `setTokens → getState().accessToken === ...`, `clearTokens` vide, `hydrate` lit `localStorage`, `hydrate` retombe sur cookie, `hydrate` no-op si `localStorage` est inaccessible (try/except).
10. [x] **Étendre `frontend/lib/api.ts`** :
    - **Request interceptor** : lit `useAuthStore.getState().accessToken` ; si présent, ajoute `Authorization: Bearer <token>` à chaque requête sortante. Si absent, ne touche pas (les endpoints publics s12 — register — ne le nécessitent pas).
    - **Response interceptor (401 + refresh)** : sur réponse 401 (sauf sur `/api/auth/login` et `/api/auth/refresh` eux-mêmes, pour éviter la boucle), tenter un `POST /api/auth/refresh` avec le `refreshToken` courant, mettre à jour le store avec la nouvelle paire, **rejouer** la requête initiale avec le nouveau `Authorization`. Si le refresh échoue (401), `clearTokens()` + redirection `router.push('/login?next=<pathname>')`. **Race condition** : si plusieurs requêtes 401 arrivent en parallèle, elles partagent la même promesse de refresh (`refreshPromise: Promise<TokenPair> | null` au niveau du module, réinitialisée à `null` après résolution).
    - Test (vitest + mock axios) : (a) requête sortante avec token dans le store → header `Authorization` présent ; (b) 401 + refresh réussi → requête réessayée avec le nouveau token ; (c) 401 + refresh échoué → `clearTokens` appelé + redirection ; (d) race : 3 requêtes en parallèle 401 → 1 seul appel `/refresh`, les 3 requêtes réessayées.
11. [x] **Étendre `frontend/messages/fr.json` et `en.json`** avec le namespace `auth` complet (conforme au design § 6 : `auth.login.*`, `auth.register.*`, `auth.logout.*`, `auth.errors.*`). Vérification : `frontend/scripts/check-i18n.sh` (script existant, AGENTS.md § i18n) doit passer sans warning.

### Frontend — pages

12. [x] **Créer `frontend/app/(public)/[locale]/login/page.tsx`** :
    - `'use client'` (formulaire interactif).
    - Utilise `useTranslations('auth.login')` + `useTranslations('auth.errors')` — **zéro string en dur** (AGENTS.md § i18n, validé par `check-i18n.sh`).
    - `useState` : `pseudo`, `password`, `errors: {pseudo?, password?, form?}`, `submitting`, `networkError`.
    - `useAuthStore` : `setTokens`, `clearTokens`.
    - `useRouter` (next/navigation) + `useSearchParams` (pour `?next=`).
    - `useEffect` (mount) : si `authStore.isAuthenticated` est déjà `true` → redirection immédiate vers `?next ?? '/chat'` (un user déjà connecté qui ouvre `/login` ne doit pas re-saisir).
    - `validate(pseudo)` côté client : regex `^[a-zA-Z0-9_]{3,32}$` — si KO, `setErrors({pseudo: 'invalidPseudo'})`, bouton désactivé. La validation password est vide (le backend 401/422 s'en charge, et on veut un message générique).
    - `handleSubmit(e)` :
      1. `e.preventDefault()`.
      2. `setSubmitting(true)`, `setErrors({})`.
      3. `try { await apiClient.post('/api/auth/login', {pseudo, password}) ; }` :
         - 200 : `setTokens(resp.data)` (`accessToken`, `refreshToken`, `role`, `pseudo` du body décodé), `router.push(searchParams.get('next') ?? '/chat')`.
         - 401 : `setErrors({form: 'invalidCredentials'})`.
         - 422 (defense in depth, ne devrait pas arriver si la validation client est OK) : `setErrors({form: 'invalidCredentials'})` (mêmes codes que 401, on ne leake pas).
         - network : `setNetworkError(true)`.
      4. `finally { setSubmitting(false) }`.
    - Rendu : `<Card>` centré (`max-w-sm mx-auto mt-12`), `<h1>{t('title')}</h1>`, `<form>` avec `<Label>` + `<Input id="pseudo" required>` + `<Input id="password" type="password" required>`, `<Button type="submit" disabled={!canSubmit || submitting} aria-busy={submitting}>{submitting ? t('submitting') : t('submitting') /* voir note */}</Button>`. Note : `submitting ? t('submitting') : t('submit')`. Lien `<Link href="/register">{t('noAccount')} {t('registerLink')}</Link>`.
    - États :
      - `networkError` : `<div className="bg-error/10 border border-error/30 ...">` au-dessus du form avec icône `alert-triangle`, message `t('errors.network')`, bouton `t('errors.retry')` qui re-tente.
      - `errors.pseudo` : `<Input invalid>` + `<p role="alert">{t('errors.invalidPseudo')}</p>` sous le champ.
      - `errors.form` : `<p role="alert">{t('errors.invalidCredentials')}</p>` au-dessus du bouton.
      - `submitting` : `<Button disabled aria-busy="true">` avec `<span className="sr-only">{t('submitting')}</span>` + label inchangé (l'`aria-busy` suffit pour l'a11y).

    **Vérification visuelle** : la page reproduit les 4 états du mockup `docs/designs/s13-login-eleve.html` (empty / 422 / 401 / network+loading). Lint : `pnpm lint` et `pnpm typecheck` (le projet utilise pnpm, cf. `frontend/package.json`).
13. [x] **Créer `frontend/app/(public)/[locale]/register/page.tsx`** — strictement le même squelette que `/login`, avec :
    - `t('register.*')` au lieu de `t('login.*')`.
    - Endpoint `POST /api/auth/register` au lieu de `/api/auth/login`.
    - Codes d'erreur supplémentaires : 409 `pseudo_taken` → `setErrors({pseudo: 'pseudoTaken'})` ; 422 `weak_password` → `setErrors({password: 'weakPassword'})` ; 422 `invalid_pseudo` → `setErrors({pseudo: 'invalidPseudo'})`. Le 201 ne renvoie pas de tokens, on redirige vers `/login?next=...` avec un `?registered=1` (le header affichera un toast non-bloquant en s25, **hors scope s13** : juste la redirection).
    - Lien en bas : `<Link href="/login">{t('hasAccount')} {t('loginLink')}</Link>`.
    - Vérification visuelle : reproduction de l'écran B du mockup (empty + 409). Lint + typecheck.
14. [x] **Modifier `frontend/components/Header.tsx`** :
    - Importer `useAuthStore` + `useTranslations('auth.logout')`.
    - Remplacer le bloc input pseudo actuel (lignes ~71-93) par un ternaire :
      - Si `authStore.hydrated && authStore.accessToken` → bouton avatar + menu.
      - Sinon → bouton `Se connecter` (variante `primary` `size="sm"`) qui pointe vers `/login`.
    - L'avatar est composé inline (gap #1 du design) : `<div className="w-8 h-8 rounded-full bg-primary text-white grid place-items-center font-semibold text-sm">{authStore.pseudo[0].toUpperCase()}</div>`.
    - Le menu est un `<details>/<summary>` natif (gap #2). Items : « Mon espace » (`<Link href="/chat" className="... disabled">{t('menu.label')}</Link>` — désactivé car la nav principale le fait déjà), « Se déconnecter » (`<button variant="destructive" onClick={handleLogout}>` + icône `log-out`).
    - `handleLogout()` :
      1. `const accessToken = authStore.accessToken` (snapshot avant clear).
      2. `authStore.clearTokens()` (UI réactive immédiate, le user voit l'avatar disparaître).
      3. `apiClient.post('/api/auth/logout', null, { headers: { Authorization: \`Bearer \${accessToken}\` } }).catch(() => {})` (fire-and-forget, le backend blackliste le `jti` mais l'UI n'attend pas).
      4. `router.push('/')` (redirection vers la home).
    - **Détail accessibilité** : `<details>` natif est focusable au clavier. Le `<summary>` a un `aria-label={t('menuAlt')}`. L'item désactivé a `aria-disabled="true"` + `tabindex="-1"` (cf. design-system l.228).
    - Vérification visuelle : reproduction de l'écran C du mockup (connecté + dropdown ouvert, déconnecté). Test e2e Playwright `frontend/e2e/auth.spec.ts` (créé si absent) : (a) non connecté → bouton « Se connecter » ; (b) login via UI → avatar visible ; (c) click avatar → menu visible ; (d) click « Se déconnecter » → retour à l'état (a).
    - **Régression** : le contrat actuel de `Header` (input pseudo + cookie) est **cassé** par cette PR. Le `setPseudo` reste utilisé par l'authStore pour le cache de transition (ADR 011), donc on **garde** la méthode mais on **ne rend plus l'input** — il devient un side-effect interne. Tests existants qui tapaient sur l'input pseudo seront mis à jour en fix mode par le reviewer.
15. [x] **Modifier `frontend/app/(public)/[locale]/layout.tsx`** : aucun changement (le `<NextIntlClientProvider>` et le `<Header>` sont déjà câblés). **Pas de tab bar bottom** dans `frontend/components/` — dette documentée (s22), no-op confirmé (vérification : `ls components/` retourne uniquement `Button`, `Card`, `FileUpload`, `Header`, `Input`, `Label`, `LanguageSwitcher`, `Select`, `StreamingMessage`, `Textarea`).

### Documentation & outillage

16. [x] **Pas d'Alembic** (Trap 15). Pas de nouvelle migration. `init_db()` reste la source de vérité.
17. [x] **Pas de nouvel ADR** — toutes les décisions structurantes sont déjà dans `005-auth-rs256-rbac.md` (algorithme, claims, rotation, blacklist, RBAC) et `011-frontend-pseudo-cookie-pre-jwt.md` (cookie transitoire). Les Q1-Q6 sont tranchées opérationnellement par ce plan, pas par un nouvel ADR. Si la review trouve une décision qui mérite un ADR (ex. ajout de `jti`/`type` au-delà d'ADR 005), elle sera ajoutée en fix mode.
18. [x] **Pas de modif `CLAUDE.md` ou `AGENTS.md`** — la stack, les conventions et les ADR couvrent déjà s13.
19. [x] **Mettre à jour `docs/architecture.md` § Frontend (si pertinent)** : section « Stores Zustand » : ajouter la note « `authStore` porte désormais `accessToken` + `refreshToken` + `role` en plus de `pseudo`. Source de vérité = JWT (lu via `decodeToken` côté backend), `pseudo` cookie = cache de transition. » — ~3 lignes.

## Run interdicts

- **Pas d'Alembic** (s12 a tranché D7 — pas de migration ; `init_db()` est la source de vérité). Si l'implémentation crée un fichier `backend/alembic/versions/...`, c'est un drift.
- **Pas de `JWT_ALGORITHM` lisible depuis le token** — l'algorithme est **toujours** `RS256` côté encode **et** côté decode. `decode_token` whitelist `algorithms=["RS256"]` (Piège 1). Un `decode_token(token, ..., algorithms=None)` est un drift.
- **Pas de token / hash / password dans les logs** (AGENTS.md § Backend). Un `grep -E "logger\.(info|warning|error|debug).*\b(password|token|hash|jwt|jti)\b" backend/app/core/auth/ backend/app/api/auth/` doit retourner 0.
- **Pas de nouveau composant UI partagé** (Button, Card, Input, Label sont réutilisés). L'avatar est composé inline (gap #1), le menu est un `<details>` natif (gap #2). Si l'implémentation crée `frontend/components/Avatar.tsx` ou `frontend/components/Popover.tsx`, c'est un drift — ces composants sont explicitement hors-scope (s17, s22).
- **Pas de `(auth)/` group au root** — les pages `/login` et `/register` vivent dans `frontend/app/(public)/[locale]/login/` et `frontend/app/(public)/[locale]/register/`, en réutilisant le layout `(public)/[locale]/layout.tsx` qui wrappe déjà `<Header />` + `<NextIntlClientProvider />`. Le split `(auth)/` arrive en s15+ (D1 du design).
- **Pas de middleware de gating des routes `(public)`** — la protection `(dashboard)/` est une story séparée (s15). Le seul « protecteur » visible de s13 est le Header.
- **Pas de HttpOnly cookie côté backend** — les tokens vont en `localStorage` (Q1, dette documentée pour s15+). Si l'implémentation appelle `response.set_cookie(...)` dans `/login` ou `/refresh`, c'est un drift.
- **Pas de bootstrap admin dans cette story** — ADR 005 le mandate, mais c'est **s13b** (`s13b-creer-compte-admin-parent`). Le script `scripts/bootstrap_admin.py` est hors-scope s13.
- **Pas de test qui sleep 31 minutes** (Piège 12) — les tokens expirés sont générés directement avec `expires_delta=timedelta(seconds=-1)`.
- **Pas de merge sur la branche par défaut** — mode manuel, conformément à AGENTS.md § Stratégie de ship.
- **Pas de modif des stories précédentes** (s11a, s11b, s11c, s12) — leur code reste intact sauf `Header.tsx` (tâche 14, modification ciblée).

## The point everything turns on

**Le point central** : la sérialisation `decode_token` doit **toujours** rejeter les tokens qui ne portent pas `algorithms=["RS256"]`, qui ont un `jti` blacklisté, ou qui ont un `type` ≠ attendu. C'est la seule barrière entre un attaquant et l'accès authentifié.

**Trois endroits où ça peut foirer** :

1. **L'encode vs le decode** : si `create_access_token` signe avec un algo et que `decode_token` whitelist un autre, les tokens émis sont rejetés → tous les tests login échouent. **À comparer** : `jwt.encode(payload, key, algorithm="RS256")` dans `jwt.py:create_access_token` vs `jwt.decode(token, pub_key, algorithms=["RS256"], ...)` dans `jwt.py:decode_token`. Les deux doivent être alignés.

2. **Le timing du `verify_password` pour les pseudos inexistants** (Piège 2) : si l'implémentation shortcut `if user is None: raise 401` sans appeler `verify_password` sur un dummy hash, l'attaquant time-attack l'existence. **À comparer** : `login.py:POST /api/auth/login` doit appeler `verify_password(plain, DUMMY_HASH)` dans la branche `user is None` **avant** de raise. Le test AC6 bis (timing) est le garde-fou — il sera skip-able en CI lente mais c'est l'invariant.

3. **La rotation du refresh** : si `/refresh` ne blackliste pas l'ancien `jti`, un attaquant qui a volé le refresh peut le rejouer indéfiniment. **À comparer** : `router.py:POST /api/auth/refresh` doit appeler `token_blacklist.add(claims["jti"])` **avant** d'émettre la nouvelle paire. Le test AC5 (rejeu de l'ancien refresh → 401) est le garde-fou.

Le reviewer portera son attention là. Il ne s'y limitera pas.

## Files touched

**Backend — new (7 fichiers)** :
- `backend/app/core/auth/jwt.py` — encode/decode/refresh, RS256, claims `sub`/`role`/`iat`/`exp`/`jti`/`type`.
- `backend/app/core/auth/middleware.py` — `get_current_user`, `require_role`.
- `backend/app/core/auth/token_blacklist.py` — `set[str]` in-memory, thread-safe POC.
- `backend/scripts/generate_jwt_keys.py` — génération idempotente RSA 2048.
- `backend/tests/core/test_jwt.py` — round-trip, RS256, blacklist, `alg: none` rejeté, swap access/refresh.
- `backend/tests/api/test_auth_login.py` — login + refresh + logout + expired + wrong-pw + timing + register→login + no-token-in-logs.
- `backend/tests/api/test_auth_middleware.py` — `get_current_user`, `require_role`, 401, 403.

**Backend — modified (5 fichiers)** :
- `backend/app/core/config.py` — +5 `jwt_*` knobs.
- `backend/app/api/auth/schemas.py` — +`LoginRequest`, `TokenPairResponse`, `RefreshRequest`, `AuthErrorResponse`.
- `backend/app/api/auth/router.py` — +3 endpoints (login, refresh, logout).
- `backend/requirements.txt` — +`pyjwt[crypto]>=2.8`.
- `backend/.env.example` + `.env.example` — +5 vars `JWT_*` ; `keys/` ajouté au `.gitignore`.

**Frontend — new (3 fichiers)** :
- `frontend/app/(public)/[locale]/login/page.tsx` — formulaire login (4 états : empty, 422, 401, network+loading).
- `frontend/app/(public)/[locale]/register/page.tsx` — formulaire register (empty, 409).
- `frontend/e2e/auth.spec.ts` — e2e Playwright (login → avatar → logout).

**Frontend — modified (5 fichiers)** :
- `frontend/lib/api.ts` — request interceptor (Authorization) + response interceptor (401 → refresh → retry).
- `frontend/lib/stores/authStore.ts` — +`accessToken`, `refreshToken`, `role`, `setTokens`, `clearTokens`, `hydrate` étendu.
- `frontend/components/Header.tsx` — bascule input pseudo → avatar + menu (D2 design).
- `frontend/messages/fr.json` + `frontend/messages/en.json` — namespace `auth.*` complet.
- `frontend/components/BottomTabBar.tsx` (vérification : si existe, masquer sur `/login` et `/register`).

**Generated, gitignored (2 fichiers)** :
- `./keys/jwt_private.pem` — RSA 2048, généré par `generate_jwt_keys.py`.
- `./keys/jwt_public.pem` — RSA 2048, généré par `generate_jwt_keys.py`.

**Doc — modified (1 fichier)** :
- `docs/architecture.md` § Frontend — note `authStore` étendu (3 lignes).

**Total : 10 nouveaux fichiers (8 code + 1 e2e + 1 keys-script) + 11 fichiers modifiés + 2 clés générées.**

## Test strategy

| Couche | Quoi | Fichier | Quand |
|---|---|---|---|
| **Unit (core)** | `token_blacklist` add/is_revoked/clear | `tests/core/test_token_blacklist.py` | T4 |
| **Unit (core)** | `create_access_token`, `create_refresh_token`, `decode_token`, `alg: none` rejeté, swap access/refresh, expired, blacklist | `tests/core/test_jwt.py` | T5 |
| **Integration (API)** | login happy + 401 + 422 + 409 (via register) + refresh rotation + logout + register→login + expired token sur endpoint protégé + pas de token dans logs | `tests/api/test_auth_login.py` | T8 |
| **Integration (API)** | `get_current_user` valide / 401 (header manquant, junk, expiré, blacklisté) / `require_role` 403 | `tests/api/test_auth_middleware.py` | T6 |
| **Unit (frontend)** | `authStore.setTokens/clearTokens/hydrate` (localStorage + cookie fallback) | `frontend/lib/stores/authStore.test.ts` (vitest) | T9 |
| **Unit (frontend)** | `apiClient` interceptor (Authorization, 401→refresh, race condition) | `frontend/lib/api.test.ts` (vitest) | T10 |
| **e2e (Playwright)** | parcours nominal : home → click « Se connecter » → login form → submit → avatar visible → click avatar → click « Se déconnecter » → retour à l'état initial | `frontend/e2e/auth.spec.ts` | T14 |
| **e2e (Playwright a11y)** | `@axe-core/playwright` sur `/login` et `/register` (Lighthouse a11y ≥ 90, cf. design-system) | `frontend/e2e/auth.a11y.spec.ts` | T12/T13 |
| **Lint + typecheck** | `pnpm lint` (ESLint), `pnpm typecheck` (tsc) | — | T12, T13, T14 |
| **Visual check** | Reproduction des 4 états du mockup `docs/designs/s13-login-eleve.html` (empty / 422 / 401 / network+loading) sur `/login` et des 2 états sur `/register` (empty / 409). Pas de diff de pixel — on vérifie « la structure et les tokens sont là » (cf. design § 2 « Mockup status »). | manuel | T12/T13/T14 |

**Herméticité** : les tests backend utilisent l'in-memory SQLite + StaticPool (pattern s12, `tests/api/test_auth_register.py:32-70` copié verbatim). Les clés RSA sont générées **une fois par session pytest** (fixture `scope="session"`) pour éviter le coût ~200ms de génération à chaque test (Piège 11). Les tests frontend utilisent `localStorage` mocké + Zustand en mémoire (pas de réseau).

**Couverture par AC** :
- AC1 → `test_login_happy_path` (200 + `TokenPairResponse`).
- AC2 → `test_token_signed_rs256` + `test_alg_none_rejected` (Piège 1).
- AC3 → `test_access_token_expires_in_30_min`.
- AC4 → `test_refresh_token_expires_in_7_days`.
- AC5 → `test_refresh_rotates_old_blacklisted`.
- AC6 → `test_wrong_password_returns_401_generic` + `test_timing_aligned_for_unknown_pseudo` (skip-able).
- AC7 → `test_token_contains_sub_role_iat_exp_jti_type`.
- AC8 → `test_login_returns_decodable_jwt` (partie du happy path).
- AC9 → `test_expired_token_rejected_by_middleware` (AC + e2e test `test_expired_token_returns_401_on_logout`).
- AC implicites s13 scope frontend (design) → `frontend/e2e/auth.spec.ts` + tests vitest du store + tests vitest de l'apiClient.

**Pas de test sur la tab bar** : si `BottomTabBar.tsx` n'existe pas, **pas de test** ; on documente l'absence en `docs/architecture.md` (« tab bar bottom planifiée s22 »).

## Definition of Done

DoD du repo (`AGENTS.md`) + spécialisations s13 :

- [ ] Une PR unique, description structurée (résumé, AC cochées, captures `/login` + `/register` + Header connecté, points d'attention sur les 3 pièges centraux), diff lisible.
- [ ] **9 tests AC** passants (cf. matrice ci-dessus).
- [ ] **Pas de régression** : `pytest backend/tests` reste vert, `pnpm test` (vitest + Playwright) reste vert.
- [ ] **Sécurité** : `grep -E "logger\.(info|warning|error|debug).*\b(password|token|hash|jwt|jti)\b" backend/app/core/auth/ backend/app/api/auth/` → 0 match. Le test `test_no_token_in_logs` le prouve.
- [ ] **i18n** : `frontend/scripts/check-i18n.sh` passe, 0 string en dur dans `/login`, `/register`, `Header.tsx`.
- [ ] **a11y** : `@axe-core/playwright` sur `/login` et `/register` rapporte 0 violation critique ; focus visible, labels `htmlFor` présents, `aria-invalid` + `aria-busy` corrects.
- [ ] **Pas de `keys/` commité** : `git status` ne montre jamais `keys/jwt_*.pem`. Le test `test_keys_dir_is_gitignored` (bash + `git check-ignore`) le prouve.
- [ ] **Review passée** (gate `Max severity: <level>` + `Ship allowed: <yes|no>`) — un critical = `no`, plan rejeté.
- [ ] **Documentation à jour** : `docs/architecture.md` § Frontend reflète l'extension de `authStore`.
