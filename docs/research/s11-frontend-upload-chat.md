---
name: research-s11-frontend-upload-chat
description: s11-frontend-upload-chat — recherche de contexte pour /ks-plan
metadata:
  type: project
  story: s11-frontend-upload-chat
---

# Research — Story s11-frontend-upload-chat

> Recherche en français. Code identifiers (snake_case, PascalCase) dans leur forme d'origine. Diacritiques : « élève », « réactivité », « téléchargement », « collège ».

## 0. Statut du worktree et du repo (vérifié)

- **Worktree** : `C:/Workspace/ktutor/.worktrees/s11-frontend-upload-chat` — créé par le sous-agent `worktree-manager`, branche `feature/s11-frontend-upload-chat`, HEAD = `ff21046` (= `origin/main` post s10), `git status --porcelain` vide.
- **Branche par défaut locale** : `main` était à `473181c` (s07) en début de session. Le sous-agent `worktree-manager` a fait `git fetch origin && git checkout -b feature/s11-frontend-upload-chat origin/main`, ce qui a aussi déclenché un fast-forward local de `main` vers `ff21046` (s08 + s09 + s10). Pas d'action de ma part sur la branche par défaut.
- **`docs/reviews/stories.md` → `Stories ready: yes`** (story s11 dans le périmètre).

## 1. Les cinq faits structurants

1. **Il n'y a aucun `frontend/` dans le repo** (`git ls-tree -r origin/main --name-only | grep -E "frontend/|package\.json|next\.config"` retourne vide). s11 est la **première story frontend** : la totalité du scaffold Next.js 16 (config, dépendances, lockfile, build, CI) doit être créée dans cette PR.
2. **Deux API contrats sont déjà shippés sur `main`** : `POST /api/chat/stream` (s09) — `text/event-stream` avec `data: {token|done|error}` + `Content-Length: keep-alive` et `POST /api/documents/upload` (s10) — multipart `pseudo`+`subject`+`file`, 201 avec `{document_id, status, chunks_count, ocr_confidence?}` ou 4xx/5xx avec `{error, code}`. Le frontend ne fait que consommer.
3. **CORS est déjà configuré côté backend** (`Settings.cors_allow_origins` défaut `http://localhost:3000`, propriété `cors_allow_origins_list`, middleware enregistré dans `main.py:62-66`). Le frontend doit tourner sur `localhost:3000` en dev (convention Next.js).
4. **Le design system est figé** dans `docs/design-system.md` : tokens couleurs (palette indigo + accent corail), typo Inter + JetBrains Mono, espacement Tailwind standard, 14 composants cible déjà spécifiés pour s11 (`<Button>`, `<Input>`, `<Label>`, `<Card>`, `<FileUpload>`, `<StreamingMessage>`, `<LanguageSwitcher>`, `<Select>`). Pas d'invention permise.
5. **ADR 006 verrouille la stack frontend** : Next.js 16 App Router, TypeScript, Tailwind, Zustand, Axios, `next-intl` dès le départ, `fetch` + `ReadableStream` pour SSE (l'EventSource natif ne supporte pas POST). Toute déviation = nouvel ADR.

## 2. Rappel de la story

Source : `docs/stories.md:409-447`.

**As an** élève **I want** utiliser une interface web responsive (smartphone + tablette) **so that** je puisse uploader et chatter sans installer quoi que ce soit.

**Complexity** : **4** (Next.js 16 + SSE consumption + Zustand + responsive UI + i18n scaffold).

### Acceptance criteria (8 ACs)

1. Page `/upload` : sélection de fichier, choix de matière, soumission. Succès → confirmation. Erreur → message clair.
2. Page `/chat` : question + matière + réponse streamée en temps réel.
3. Responsive : utilisable sur 360px (smartphone) et 768px (tablette), pas de scroll horizontal.
4. La page chat lit le flux SSE et ajoute les chunks à mesure.
5. Sélecteur de langue FR/EN dans le header (ou footer).
6. Test Playwright e2e du flow upload contre un backend stubbé.
7. Test que la page chat rend sans erreur JS et que la connexion SSE est ouverte.
8. Lighthouse Accessibility ≥ 90 sur les deux pages.

### Fichiers anticipés par la story (verrouillés par le scope d'ADR 006)

`frontend/app/(auth-less)/upload/page.tsx`, `frontend/app/(auth-less)/chat/page.tsx`, `frontend/lib/api.ts`, `frontend/lib/stores/chatStore.ts`, `frontend/messages/fr.json`, `frontend/messages/en.json`, `frontend/middleware.ts`.

## 3. État actuel du code (vérifié, pas supposé)

### 3.1. Frontend — strictement rien

`git ls-tree -r origin/main --name-only` ne retourne aucun fichier sous `frontend/`, aucun `package.json`, aucun `tsconfig.json`, aucun `next.config.*`, aucun `tailwind.config.*`. Confirmé par :

```bash
$ git ls-tree -r origin/main --name-only | grep -E "frontend/|package\.json|next\." | head
(vide)
```

**Conséquence directe** : la story ne peut pas « étendre » un frontend existant — elle doit le **créer** intégralement. Le premier commit de la branche introduit des dizaines de fichiers (scaffold, config, lockfile, .gitignore, etc.).

### 3.2. Backend — API contracts figés sur `main`

**`POST /api/chat/stream`** (`backend/app/api/chat/router.py:64-133` + `schemas.py:34-57`) :
- Body : `ChatStreamRequest { pseudo: str (regex `^[a-zA-Z0-9_]+$`, 1-32 chars), subject: Literal["maths", "francais"], question: str (1-2000 chars) }`.
- Réponse : `StreamingResponse(media_type="text/event-stream")`.
- Événements SSE (préfixe `data: ` + JSON + `\n\n`) :
  - `{"token": "..."}` — incrémental, plusieurs fois.
  - `{"done": true, "sources": [{"filename", "chunk_index"}]}` — final, exactement une fois.
  - `{"error": "...", "code": "..."}` — sur `ValueError` agent (codes : `cross_tenant`, `no_subject`, `invalid_pseudo`, `unknown`).
- Headers : `Cache-Control: no-cache`, `X-Accel-Buffering: no`.
- Erreurs Pydantic 422 AVANT ouverture du stream.
- `max_chunks` plafonné à `settings.chat_stream_max_chunks` (défaut 5000).

**`POST /api/documents/upload`** (`backend/app/api/documents/router.py:81-196` + `schemas.py`) :
- Body multipart : `pseudo` (str 1-32), `subject` (Literal), `file` (UploadFile).
- Réponses succès (201) : `UploadResponse { document_id: UUID, status: "indexed"|"manual_review_needed"|"error", chunks_count: int (≥ 0), ocr_confidence: float | None }`.
- Réponses erreur : `UploadErrorResponse { error: str, code: "invalid_pseudo"|"invalid_file"|"ocr_failure"|"storage_failure" }`.
- Mapping status : 413 (taille), 415 (extension), 422 (pseudo / OCR), 500 (S3).
- Limite : `max_upload_size_mb * 1024 * 1024` octets (défaut 20 MB).
- `MANUAL_REVIEW` est un **201** avec `chunks_count=0` (Piège 7 s10) — pas un 4xx.

### 3.3. Configuration partagée

- Backend `Settings.cors_allow_origins` défaut `http://localhost:3000` (`config.py:30`). Le frontend dev tourne donc sur port 3000 (convention Next.js).
- `NEXT_PUBLIC_API_URL` côté frontend (convention `CLAUDE.md` § Variables d'Environnement) doit pointer sur `http://localhost:8000`.

### 3.4. Contexte CI

`.github/workflows/ci.yml` référence des jobs backend (pytest, build SeaweedFS). **Aucun job frontend n'existe** : Playwright, `next build`, lint ESLint, typecheck TS devront être ajoutés dans cette story (cf. § 6 D1).

### 3.5. Worktrees déjà créés

`git worktree list` montre `C:/Workspace/ktutor` (main) et `C:/Workspace/ktutor/.worktrees/s11-frontend-upload-chat` (branche s11). **Aucun autre worktree** n'existe (s09 et s10 ont été nettoyés). Pas de collision de merge.

## 4. Anchor points (où la feature se branche)

| Fichier backend | API | Méthode à utiliser côté frontend |
| --- | --- | --- |
| `backend/app/api/chat/router.py:64-133` | `POST /api/chat/stream` | `fetch(url, {method: 'POST', body: JSON, signal})` + `response.body.getReader()` + parse `data: <json>\n\n` |
| `backend/app/api/documents/router.py:81-196` | `POST /api/documents/upload` | `fetch(url, {method: 'POST', body: FormData})` |

| Côté frontend | Convention imposée par |
| --- | --- |
| `frontend/middleware.ts` (next-intl) | ADR 006 + design-system § i18n |
| `frontend/lib/api.ts` (axios + JWT interceptor) | AGENTS.md § Frontend — mais l'interceptor JWT n'est pas utile en s11 (auth en s12-s15), il sera ajouté en s15 |
| `frontend/lib/stores/chatStore.ts` (Zustand) | AGENTS.md § Frontend |
| `frontend/messages/{fr,en}.json` (catalogues) | design-system § i18n |
| `frontend/app/globals.css` (tokens CSS) | design-system § Conventions d'implémentation |
| `frontend/tailwind.config.ts` (tokens Tailwind) | design-system § Conventions d'implémentation |
| `frontend/next.config.ts` (serverExternalPackages, output) | Next.js 16 conventions |

## 5. Verified APIs / functions (à utiliser, pas à inventer)

**Backend (déjà sur `main`, shippés) :**

- `POST /api/chat/stream` — body `{pseudo, subject, question}` → `text/event-stream`. Forme : `data: {token}\n\n`, `data: {done, sources}\n\n`, `data: {error, code}\n\n`. Source : `backend/app/api/chat/router.py:64-133`.
- `POST /api/documents/upload` — body `multipart/form-data` `{pseudo, subject, file}` → `201 {document_id, status, chunks_count, ocr_confidence?}` ou `4xx/5xx {error, code}`. Source : `backend/app/api/documents/router.py:81-196`.

**Frontend (à importer depuis le scaffold) :**

- `next-intl` : `useTranslations('Namespace')` côté composant, `getRequestConfig` dans `i18n.ts`, `createMiddleware` dans `middleware.ts`.
- `zustand` : `create<State>()((set) => ({...}))` — pattern store. La `chatStore`doit gérer : `messages[]`, `isStreaming`, `currentSubject`, `submit(question)`, `appendToken(token)`, `closeStream(sources)`, `errorEvent(error, code)`.
- `tailwindcss` : classes utilitaires uniquement. `bg-primary`, `text-text-primary`, `rounded-md` (cf. design-system § Tokens).
- `axios` : configuré dans `lib/api.ts` avec `baseURL: process.env.NEXT_PUBLIC_API_URL`. En s11 l'interceptor JWT est inutile (l'auth arrive en s15) — un `baseURL` propre suffit.

## 6. Pièges identifiés

### Piège #1 — Le scaffold est l'essentiel de la PR

Le scaffold Next.js 16 (App Router, TS strict, Tailwind v4, ESLint, Prettier, `next.config.ts`, `tsconfig.json`, `package.json`, `package-lock.json`, `.gitignore`, `app/globals.css`, `app/layout.tsx`, structure de routes `(auth-less)/` vs `(dashboard)/`) représente **~20-30 fichiers de configuration et de mise en place**. Le risque n'est pas dans les pages elles-mêmes mais dans :
- le **typage du `ReadableStream`** pour SSE (l'API n'est pas typée nativement — il faut caster ou envelopper),
- la **désactivation du buffering** côté Next.js pour le SSE (le dev server bufferise par défaut — Piège story s11 § Traps #2),
- la **gestion des erreurs réseau** (stream coupé, timeout, CORS preflight qui échoue silencieusement),
- le **package manager** : npm / pnpm / yarn — choix qui doit être documenté.

Mitigation : tâche dédiée « scaffold + dev server boots » avant tout composant.

### Piège #2 — SSE via `fetch` + `ReadableStream` (pas `EventSource`)

`EventSource` ne supporte pas `POST` (s09 l'a explicitement noté dans `router.py:16`). Le frontend doit :
1. Appeler `fetch(url, { method: 'POST', body: JSON.stringify(body), signal: AbortController.signal, headers: { 'Accept': 'text/event-stream' } })`.
2. Lire `response.body!.getReader()`.
3. Décoder via `TextDecoder('utf-8')`.
4. Parser manuellement le format `data: <json>\n\n` (split sur `\n\n`, puis strip du préfixe `data: `, puis `JSON.parse`).
5. Tolérer le multi-event par chunk (rare mais possible — `data: foo\ndata: bar\n\n`).

Le test bite à injecter un mock SSE qui produit 3 chunks + 1 done, vérifie que le DOM contient 3 `<p>` + 1 badge de sources.

### Piège #3 — Next.js dev server bufferise le SSE

Le dev server de Next.js bufferise les réponses par défaut. Symptôme : le navigateur ne reçoit rien tant que le stream n'est pas fermé. Le story note ce piège explicitement (`docs/stories.md:443`).

Mitigation : configurer `next.config.ts` pour exposer `/api/chat/stream` via une route **proxifiée** (le frontend appelle le backend sur `:8000` directement, pas via le dev server), OU utiliser un `runtime = 'nodejs'` explicite sur la route. **Recommandation : la première option est plus simple** (pas de route Next.js pour le SSE — le composant client appelle directement `process.env.NEXT_PUBLIC_API_URL + '/api/chat/stream'`).

### Piège #4 — Le mode strict de React 19 + TypeScript

Next.js 16 + React 19 activent `reactStrictMode: true` par défaut, ce qui **double-invoque** les composants en dev pour détecter les effets de bord. Conséquences :
- Le `fetch` SSE peut être appelé 2× → connexions multiples.
- Les stores Zustand doivent être idempotents.

Mitigation : utiliser `useEffect` avec un `controller` local (`useRef<AbortController>`), fermer le précédent avant d'en créer un nouveau.

### Piège #5 — `Accept-Language` du backend ≠ frontend

Le backend n'envoie **pas encore** de messages localisés (la i18n côté backend est s21). En s11, le frontend doit assumer que les erreurs backend arrivent en **français** (constaté sur s09/s10 : `UploadError.message` est en français). Pas de header `Accept-Language` à envoyer pour l'instant.

### Piège #6 — Le test Playwright e2e nécessite un backend stubbé

L'AC6 demande « un test e2e contre un backend stubbé ». Le test ne doit PAS démarrer le vrai backend (trop lourd en CI). Options :
- `MSW` (Mock Service Worker) intercepte les requêtes côté navigateur.
- Un `route.fulfill()` de Playwright qui répond directement.
- Un fixture backend JetBrains / TestClient FastAPI démarré dans le test Playwright (via `playwright-python` plutôt que `playwright/test`).

**Recommandation** : `page.route()` de Playwright (la plus simple, pas de dépendance externe). Le test stubbe `/api/documents/upload` et `/api/chat/stream` et asserte le DOM.

### Piège #7 — Lighthouse ne s'exécute pas dans un CI déterministe sans Chrome

Lighthouse CI (`@lhci/cli`) nécessite un Chrome headless. Sur Windows runner GitHub Actions, c'est disponible (`ubuntu-latest` en CI). Le job CI frontend à ajouter doit :
- Démarrer le backend (test client ou mock).
- Lancer `next build` + `next start` (port 3001).
- Exécuter `playwright test` (e2e).
- Exécuter `lhci autorun` sur les deux pages.

Si trop lourd pour s11 : asserter juste que la commande `lhci` est **exécutable** (le test e2e valide les a11y critiques via `@axe-core/playwright`, Lighthouse est un follow-up).

### Piège #8 — Le sélecteur de langue doit persister

L'AC5 dit « A footer or header allows switching the UI language between French (default) and English ». Le `next-intl` middleware écrit un cookie `NEXT_LOCALE`. Le `<LanguageSwitcher>` doit appeler `useRouter().replace(pathname, { locale })` puis `setLocale(locale)`. Pas de rechargement complet.

### Piège #9 — Le `capture="environment"` n'est pas standardisé

L'histoire note Piège #7 : « file upload from a smartphone camera requires `accept="image/*" capture="environment"` ». En pratique, iOS Safari ne supporte pas `capture` directement sur `<input type="file">` (Apple préfère un bouton séparé). Sur Android Chrome, ça marche. **Recommandation** : ajouter `accept` seulement, ne pas promettre `capture` (le story trap est imprécis — `capture` ne marche pas sur tous les navigateurs). Garder un `<input type="file" accept=".pdf,image/png,image/jpeg">` simple. Le bouton « Prendre une photo » est un futur nice-to-have.

### Piège #10 — L'AC7 « le SSE est ouvert » est trivial à valider mal

Un test naïf vérifie que la fonction `fetch` est appelée. Mais ça ne prouve pas que la connexion est **établie** (le `response.ok` peut être `false` sans déclencher d'erreur). Le test bite doit :
1. Stubble `/api/chat/stream` via `page.route` avec un `fulfill` qui streame 2 chunks + done.
2. Soumettre la question.
3. Attendre que le DOM contienne les 2 chunks + le badge sources.
4. Vérifier qu'**aucune erreur JS** n'a été loggée (`page.on('pageerror')`).

### Piège #11 — Le `display: none` sur le `<FileUpload>` n'est pas accessible

Pour styler un input file, on le cache souvent avec `opacity: 0` + `position: absolute`. **WCAG 2.1** exige que les éléments focusables soient **visibles** ou explicitement `aria-hidden`. Solution : `sr-only` (Tailwind `class="sr-only"`) sur l'input, le bouton visible est un `<label htmlFor="file-input">`. L'AC8 (Lighthouse ≥ 90) détecte ce piège.

### Piège #12 — Le store Zustand chat doit gérer le `done` et l'`error` comme états finaux

Si le store marque `isStreaming=false` trop tôt, l'UI perd l'état « réponse en cours ». Le store doit :
- `submit` → `isStreaming = true`.
- `appendToken` → append + NE PAS changer `isStreaming`.
- `closeStream(sources)` → `isStreaming = false`, push des sources.
- `errorEvent(error, code)` → `isStreaming = false`, push d'un message d'erreur.

Le test bite mute `closeStream` pour qu'il ne reset pas `isStreaming` → l'UI affiche « En attente… » indéfiniment.

## 7. Questions ouvertes

### Q1 — Package manager : npm, pnpm, yarn ?

Aucun choix documenté. Recommandation : **pnpm** (le lockfile `pnpm-lock.yaml` est le standard des projets Next.js récents, et `pnpm` est plus rapide en CI). Décision à prendre au `/ks-plan`.

### Q2 — shadcn/ui ou composants maison ?

Le design system mentionne shadcn/ui comme « à confirmer ». L'ADR 006 ne tranche pas. s11 a besoin de : `<Button>`, `<Input>`, `<Label>`, `<Card>`, `<Select>`, `<FileUpload>`, `<StreamingMessage>`, `<LanguageSwitcher>`. **Recommandation** : composants maison pour s11 (8 composants, scope borné, contrôle total sur les tokens). shadcn/ui sera introduit en s22 (audit a11y) si le besoin s'en fait sentir.

### Q3 — Faut-il un layout `(auth-less)` distinct du `(dashboard)` ?

L'ADR 006 prévoit `app/(auth)/` et `app/(dashboard)/`. Le s11 Agentic note écrit `(auth-less)/` (sans auth en s11, on n'est pas encore dans le flow `(auth)`). **Recommandation** : nommer le groupe `app/(public)/` (cohérent avec la terminologie Next.js — `(public)` = accessible sans auth, `(auth)` = login/register, `(dashboard)` = protégé). L'AC5 du story (footer/header pour switcher la langue) sera dans le layout `(public)`.

### Q4 — Le frontend doit-il démarrer via `docker compose` ou en standalone ?

CLAUDE.md § Développement indique « Terminal 3: Frontend → `npm run dev` ». Pas de `docker-compose.yml` service frontend. **Recommandation** : standalone, ajouter un `frontend/Dockerfile` est **hors-scope** (POC). L'AC de DoD « pas de régression sur le code existant » ne s'applique pas puisque le frontend n'existe pas.

### Q5 — Faut-il ajouter le job CI frontend dans cette story ?

`.github/workflows/ci.yml` n'a aucun job frontend. **Recommandation** : oui, ajouter un job `frontend` qui : (1) `npm ci`, (2) `npm run lint`, (3) `npm run typecheck`, (4) `npm run build`, (5) `npx playwright test`. C'est un effort substantiel (~80 lignes de YAML) mais c'est le seul moyen de garantir que le frontend ne régresse pas.

### Q6 — Comment valider l'AC8 « Lighthouse Accessibility ≥ 90 » sans Chrome dans le test ?

Lighthouse CI nécessite Chrome. Trois options :
- Ajouter Chrome dans le job CI (coût en temps, ~30s par page).
- Déléguer la validation à `@axe-core/playwright` dans le test e2e (couvre 80% des violations, pas 100%).
- Documenter l'AC8 comme « vérifié manuellement » et reporter le job Lighthouse à s22.

**Recommandation** : option 2 (axe-core dans le test e2e), reporter Lighthouse CI à s22 où l'audit complet aura lieu.

### Q7 — Le frontend doit-il gérer un état « loading » entre la soumission et le premier chunk SSE ?

Le backend met un certain temps avant d'émettre le premier token (latence LLM). Le frontend doit afficher un indicateur « en train de réfléchir… ». Le design system mentionne un « typing indicator 3 points animés ». **Recommandation** : oui, l'UI affiche un spinner Tailwind (`animate-pulse` sur 3 cercles) tant qu'aucun token n'est arrivé et que `isStreaming=true`.

## 8. Décisions d'architecture à prendre

### D1 — Étendue du scaffold initial

**Question** : scope du premier commit de la branche ?

- **Option A** : scaffold minimal viable (Next.js + Tailwind + next-intl + 2 pages) sans CI, sans tests e2e. PR plus petite mais aucune garantie de non-régression.
- **Option B** : scaffold + CI frontend + 2 tests e2e Playwright + axe-core. PR plus grosse (estimée ~3000 lignes ajoutées), mais le pipeline est complet dès le premier commit.
- **Option C** : split (cf. § 10 Split proposal) — s11a scaffold + CI, s11b chat, s11c upload. Permet de merger s11a avant de risquer s11b/s11c.

**Recommandation** : **Option C** (split). Le scaffold seul est un travail substantiel ; les deux pages + SSE + i18n + a11y = 3 concerns indépendants qui peuvent chacun bloater.

### D2 — Bootstrap story : structure de routes

**Question** : `(public)` vs `(auth-less)` vs routes plates ?

**Recommandation** : `app/(public)/[locale]/chat/page.tsx` (locale-routing via next-intl). Avantage : le `<LanguageSwitcher>` peut utiliser `useRouter().push({ pathname, query }, { locale })` sans hack.

### D3 — Stratégie SSE : route proxy ou direct

**Question** : le composant chat appelle-t-il `process.env.NEXT_PUBLIC_API_URL + '/api/chat/stream'` directement, ou via une route Next.js proxyfiée ?

- **Option A** : appel direct. Le navigateur fait un `fetch` cross-origin vers `:8000`. CORS est déjà configuré côté backend (s09).
- **Option B** : route proxy Next.js `app/api/chat/stream/route.ts` qui forwarde vers le backend. Plus complexe, ajoute un hop réseau, mais unifie les erreurs (CORS, timeout, etc.) sous le même origine.

**Recommandation** : **Option A**. Le backend a déjà CORS configuré pour `localhost:3000`. Le piège #3 (buffering du dev server) disparaît complètement.

### D4 — Test e2e : Playwright + axe-core, ou Playwright + Lighthouse CI ?

Voir Q6. **Recommandation** : axe-core dans le test e2e (couvre l'AC8 à 80%), Lighthouse CI en follow-up s22.

### D5 — Persistance du pseudo côté frontend

**Question** : où stocker le `pseudo` de l'utilisateur (s11 n'a pas encore d'auth) ?

- **Option A** : cookie `pseudo` posé par un `<input>` au premier accès. Le store Zustand le lit.
- **Option B** : un champ texte dans le header (l'utilisateur le tape à chaque requête).
- **Option C** : URL query param `?pseudo=...`.

**Recommandation** : **Option A** (cookie). L'utilisateur le tape une fois, ensuite le chat et l'upload l'utilisent. L'auth réelle (JWT) arrive en s12-s15, le cookie sera remplacé par le JWT.

### D6 — Mode d'erreur SSE : comment afficher une erreur de stream

**Question** : quand le SSE émet `{error, code}`, l'UI doit afficher quoi ?

- **Option A** : toast transitoire (4s) + le message d'erreur dans le chat comme un message « système ».
- **Option B** : juste un message dans le chat (pas de toast).

**Recommandation** : **Option B**. Pas de toast (les toasts sont introduits en s25). Le message d'erreur dans le chat est auto-suffisant.

## 9. Fichiers anticipés (si non-split, à titre indicatif)

| Fichier | Action | Justification |
| --- | --- | --- |
| `frontend/package.json` | **new** | Manifeste npm : next@16, react@19, typescript@5, tailwindcss@4, next-intl, zustand, axios, @axe-core/playwright, @playwright/test. |
| `frontend/pnpm-lock.yaml` | **new** | Lockfile pnpm (D1). |
| `frontend/tsconfig.json` | **new** | TS strict, `paths` pour `@/*`. |
| `frontend/next.config.ts` | **new** | `reactStrictMode: true`, `experimental.serverActions`, `output: 'standalone'` (pour le dev prod). |
| `frontend/tailwind.config.ts` | **new** | Tokens (cf. design-system). |
| `frontend/postcss.config.mjs` | **new** | Tailwind v4 pipeline. |
| `frontend/.eslintrc.json` | **new** | Next.js + TS + a11y plugins. |
| `frontend/.prettierrc` | **new** | Formatage cohérent. |
| `frontend/.gitignore` | **new** | `.next/`, `node_modules/`, `pnpm-debug.log*`. |
| `frontend/app/layout.tsx` | **new** | Root layout (next-intl `<NextIntlClientProvider>`, design system tokens dans `<html data-theme>`). |
| `frontend/app/globals.css` | **new** | CSS variables tokens (cf. design-system). |
| `frontend/app/(public)/[locale]/layout.tsx` | **new** | Layout pour les pages publiques, inclut `<Header>` + `<LanguageSwitcher>`. |
| `frontend/app/(public)/[locale]/page.tsx` | **new** | Home page (mini-hero + lien vers `/chat` et `/upload`). |
| `frontend/app/(public)/[locale]/chat/page.tsx` | **new** | Page chat (subject selector + input + streaming). |
| `frontend/app/(public)/[locale]/upload/page.tsx` | **new** | Page upload (file picker + subject + submit). |
| `frontend/components/Button.tsx` | **new** | Variants primary / secondary / ghost / destructive. |
| `frontend/components/Input.tsx` | **new** | text + file variants. |
| `frontend/components/Label.tsx` | **new** | Associé à chaque input (`htmlFor`). |
| `frontend/components/Card.tsx` | **new** | Conteneur résultat. |
| `frontend/components/Select.tsx` | **new** | Select natif (`<select>`), accessible par défaut. |
| `frontend/components/FileUpload.tsx` | **new** | Drag & drop + caméra mobile. |
| `frontend/components/StreamingMessage.tsx` | **new** | `aria-live="polite"`, accumulate tokens. |
| `frontend/components/LanguageSwitcher.tsx` | **new** | FR / EN, persiste en cookie. |
| `frontend/components/Header.tsx` | **new** | Logo + pseudo + language + links. |
| `frontend/lib/api.ts` | **new** | `axios.create({ baseURL: process.env.NEXT_PUBLIC_API_URL })`. |
| `frontend/lib/sse.ts` | **new** | `streamChat(body, onToken, onDone, onError)` qui parse SSE via `fetch` + `ReadableStream`. |
| `frontend/lib/stores/chatStore.ts` | **new** | Zustand : messages, isStreaming, currentSubject, submit/appendToken/closeStream/errorEvent. |
| `frontend/lib/stores/authStore.ts` | **new** | Zustand : pseudo (cookie-backed). |
| `frontend/i18n/request.ts` | **new** | `getRequestConfig` pour next-intl. |
| `frontend/i18n/routing.ts` | **new** | Configuration locales (`fr`, `en`), default `fr`. |
| `frontend/middleware.ts` | **new** | `createMiddleware` de next-intl. |
| `frontend/messages/fr.json` | **new** | Catalog FR (toutes les strings UI). |
| `frontend/messages/en.json` | **new** | Catalog EN. |
| `frontend/.env.example` | **new** | `NEXT_PUBLIC_API_URL=http://localhost:8000`. |
| `frontend/playwright.config.ts` | **new** | Config Playwright. |
| `frontend/e2e/upload.spec.ts` | **new** | Test e2e upload avec `page.route` stub. |
| `frontend/e2e/chat.spec.ts` | **new** | Test e2e chat + axe-core. |
| `.github/workflows/ci.yml` | **extend** | Ajouter un job `frontend` (lint, typecheck, build, e2e). |
| `docker-compose.yml` | **extend** ? | **NON** — pas de service frontend (cf. Q4). |

**Total estimé** : ~50 fichiers, ~3000 lignes (scaffold + tests inclus). Justification du split (cf. § 10) : c'est trop pour une seule PR review-able.

## 10. Tests à prévoir (un par AC)

| AC | Test | Stack |
| --- | --- | --- |
| AC1 | Upload happy path | Playwright + `page.route` stub du 201 |
| AC1 | Upload erreur (fichier trop gros) | Stub 413 |
| AC1 | Upload erreur (mauvaise extension) | Stub 415 |
| AC2 | Chat : soumission + réception du stream | Playwright + `page.route` stub SSE |
| AC3 | Responsive : viewport 360px + 768px, pas de scroll horizontal | Playwright `setViewportSize` |
| AC4 | Chat : chunks apparaissent dans le DOM dans l'ordre | Playwright + stub 3 chunks + 1 done |
| AC5 | Switch FR ↔ EN : la langue change dans l'UI | Playwright + `useTranslations` snapshot |
| AC6 | E2e upload complet | Playwright e2e |
| AC7 | Chat : la connexion SSE est ouverte, aucune erreur JS | Playwright + `page.on('pageerror')` |
| AC8 | axe-core : 0 violation critique | Playwright + `@axe-core/playwright` |

**Couverture totale** : 9+ tests. Avec axe-core inclus dans AC2/AC7, on couvre l'AC8 indirectement.

## 11. Risques

- **R1 — Premier frontend, zéro base** : tout est nouveau. La revue va voir passer beaucoup de config boilerplate. **Mitigation** : le story risk note le dit, et la solution est de **scinder** (cf. § 10 split). **Probabilité forte, impact modéré**.
- **R2 — Le scaffold Next.js 16 + Tailwind 4 + React 19 est très récent** : documentation encore fragmentaire, breaking changes possibles entre versions mineures. **Mitigation** : pin les versions exactes (`next@16.0.0`, `react@19.0.0`, `tailwindcss@4.0.0`). **Probabilité moyenne, impact modéré**.
- **R3 — i18n : la migration `next-intl` v3 vs v4** : l'API a changé entre v3 (deprecated) et v4 (actuelle). **Mitigation** : utiliser la dernière stable documentée dans le `package.json`. **Probabilité faible, impact modéré**.
- **R4 — Le test e2e Playwright nécessite un navigateur** : l'install Chromium en CI prend ~200MB et ~30s. **Mitigation** : utiliser `playwright install --with-deps chromium` dans le job CI, ou `mcr.microsoft.com/playwright` Docker image. **Probabilité forte, impact faible** (standard de l'industrie).
- **R5 — Lighthouse CI en local n'est pas trivial** (cf. Q6). **Mitigation** : axe-core suffit pour l'AC8, Lighthouse reporté. **Probabilité forte, impact faible**.
- **R6 — Les composants du design system doivent tous être testés visuellement**. Pas de Storybook en s11. **Mitigation** : les composants sont simples (Button, Input, etc.), le test e2e valide leur usage sur les pages. **Probabilité forte, impact faible**.

## 12. Definition of Done (spécialisé s11)

- Une PR unique par sous-story (s11a, s11b, s11c).
- Description structurée : résumé, AC cochées, captures si UI, points d'attention.
- Tests passants :
  - s11a : `npm run build` + `npm run lint` + `npm run typecheck`.
  - s11b : `npx playwright test chat.spec.ts` (≥ 5 tests).
  - s11c : `npx playwright test upload.spec.ts` (≥ 3 tests).
- Pas de régression sur le code backend (les 412 tests pytest passent toujours).
- **i18n vérifié** : `useTranslations()` est utilisé partout, audit par script shell `grep -R ">[A-Z][a-z]\+<" frontend/components frontend/app` ne retourne pas de string en dur non-i18n-isée.
- **a11y vérifié** : 0 violation critique axe-core sur les deux pages.
- **Responsive vérifié** : test Playwright sur 360px et 768px.
- **Pas de hardcoded API URL** : `process.env.NEXT_PUBLIC_API_URL` partout.
- **CI verte** : tous les jobs (backend pytest, SeaweedFS build, frontend lint/typecheck/build/e2e).
- **Le diff est minimal** : pas de `Dockerfile` frontend (POC), pas de `package-lock.json` autre que celui du package manager choisi (D1), pas de migration de stack.

## 13. Faux premises et invalidez détectées

- **« Reuse the existing boilerplate from previous stories »** : NON. Aucune story frontend n'existe, il n'y a pas de boilerplate à réutiliser. La story doit tout créer.
- **« 1 PR = 1 commit (always squash) »** : Vrai pour chaque sous-story s11a, s11b, s11c. Mais l'ensemble de la story s11 = 3 PRs.
- **« Playwright e2e »** : OK, mais l'install Chromium en CI n'est pas documenté. La story doit ajouter le job CI.
- **« Lighthouse Accessibility ≥ 90 »** : reporté à s22 (axe-core couvre l'AC8 à 80%). Décision D4.
- **« use `EventSource` for SSE »** : NON. `EventSource` ne supporte pas POST. Le story dit « use `fetch` with `ReadableStream` » — vérifié dans ADR 006.
- **« next-intl from the start (no hardcoded strings) »** : Vrai. La règle s'applique dès s11a.
- **« Multi-tenancy verified »** : la story s11 n'a **pas de test cross-tenant** explicite (le multi-tenancy est imposé par le backend, le frontend n'envoie que le `pseudo` qu'il a). Le test vérifie que le frontend envoie bien le `pseudo` (du cookie) à l'API. Le test cross-tenant réel est côté backend (s09, s10).

## 14. Sources (vérifiées sur le HEAD `ff21046`)

### Code lu

- `backend/app/main.py` (75 lignes) — entry FastAPI, lifespan, CORS, routers.
- `backend/app/api/chat/router.py` (133 lignes) — `POST /api/chat/stream`.
- `backend/app/api/chat/schemas.py` (77 lignes) — `ChatStreamRequest`, `StreamErrorEvent`.
- `backend/app/api/documents/router.py` (213 lignes) — `POST /api/documents/upload`.
- `backend/app/api/documents/schemas.py` (73 lignes) — `UploadResponse`, `UploadErrorResponse`.
- `backend/app/core/config.py` (161 lignes) — `Settings.cors_allow_origins`, `chat_stream_max_chunks`.

### Spécification lue

- `docs/stories.md:409-447` — story s11 complète (AC, dépendances, agentic notes, traps).
- `docs/architecture.md` § Frontend (l.27-37) — stack imposée.
- `docs/architecture.md` § Patterns & conventions (l.139-149) — conventions Next.js.
- `docs/design-system.md` (294 lignes) — tokens, composants cible, conventions.
- `docs/decisions/006-frontend-nextjs-app-router.md` — verrouille stack + i18n + a11y.
- `CLAUDE.md` § Frontend + § Variables d'Environnement (notamment `NEXT_PUBLIC_API_URL`).
- `AGENTS.md` § Frontend (conventions) + § Pipeline.
- `.github/workflows/ci.yml` — job backend uniquement, pas de job frontend.

### Code adjacent non lu (out of scope strict)

- `backend/app/api/chat/sse.py` (non lu — format exact connu via router + schemas).
- `backend/app/services/agents/supervisor.py` (non lu — le frontend ne parle qu'à l'API, pas au service).

## 15. Re-vérification après merge s10 (2026-09-01)

Cette recherche est écrite **après** que s10 (squash `ff21046`) a été mergé sur `origin/main`. L'API documents est stable. L'API chat (squash `c5f6163`) aussi. **Aucun rebasculement attendu** côté backend.

**Conclusion** : la story s11 est faisable en l'état. Le seul blocage est le **split** (verdict complexity 5 — cf. § 16).

## 16. Real complexity et split proposal

**Score docs/stories.md** : 4.

**Score après ouverture du code** : **5**.

**Justification du 5** :

1. **Premier frontend, scaffold from zero** : ~50 fichiers de config + boilerplate (Piège #1).
2. **SSE via `fetch` + `ReadableStream`** : parsing manuel, gestion d'erreurs réseau, Piège #2.
3. **i18n dès le départ** : middleware, routing, 2 catalogues, switcher persistant.
4. **a11y** : Lighthouse ≥ 90, axe-core, focus visible, `aria-live` sur stream.
5. **Responsive** : test à 360px et 768px.
6. **CI** : nouveau job frontend (lint + typecheck + build + e2e).
7. **8 composants cible** à créer dans le design system.
8. **2 pages** avec state management.

Cumulé : c'est **trop pour une PR review-able**. Le story risk note le dit (« three concerns that can each blow up »), j'ajoute le bootstrap.

### Split proposal (3 stories)

- **s11a-frontend-bootstrap** — Scaffold + design system + CI + i18n. Accepte : (a) `next dev` démarre et sert une home page `Welcome`, (b) le toggle FR/EN fonctionne, (c) `pnpm lint` + `pnpm typecheck` + `pnpm build` passent en CI, (d) `axe-core` sur la home retourne 0 violation critique, (e) le job CI frontend est vert. **Complexity : 3**. **Ferme sur** : la base technique.
- **s11b-frontend-chat** — Page `/chat` + SSE consumer + chat store. Accepte : (a) les 5 tests e2e chat passent, (b) `axe-core` sur la page chat retourne 0 violation critique, (c) le viewport 360px affiche correctement le chat. **Complexity : 3**. **Ferme sur** : le chat streamé bout-en-bout.
- **s11c-frontend-upload** — Page `/upload` + `<FileUpload>` + axios upload. Accepte : (a) les 3 tests e2e upload passent, (b) `axe-core` sur la page upload retourne 0 violation critique, (c) les 3 cas d'erreur (taille, extension, validation) sont testés. **Complexity : 2**. **Ferme sur** : l'upload bout-en-bout.

**Dépendances du split** : s11a (bootstrap) → s11b (chat) + s11c (upload). s11b et s11c sont parallélisables sur des branches séparées après le merge de s11a.

**Révision du score** : docs/stories.md dit « 4 ». La lecture du code confirme 5. Le score 5 est un signal pour **splitter** — le plan détaillé reste faisable sur chaque sous-story individuellement.

## 17. Pré-requis pour passer à `/ks-design` puis `/ks-plan`

- **D1** (étendue du scaffold) : trancher. Recommandation = split en 3 stories. Si l'utilisateur préfère 1 PR monolithique, c'est possible mais le review gate va galérer.
- **Q1** (package manager) : trancher. Recommandation = pnpm.
- **Q2** (shadcn/ui) : trancher. Recommandation = composants maison pour s11.
- **Q3** (nom du groupe de routes) : trancher. Recommandation = `(public)`.
- **Q5** (CI frontend) : trancher. Recommandation = oui, ajouter le job.

Une fois ces décisions tranchées, **`/ks-design <id>` peut produire `docs/designs/s11-frontend-upload-chat.md`** (mockup + tokens pour chat et upload), puis **`/ks-plan s11a-frontend-bootstrap`** peut démarrer la planification de la première sous-story.

**Note importante sur le split** : si l'utilisateur approuve le split, il faut **renuméroter** s11 en s11a/b/c dans `docs/stories.md` (et probablement créer un ADR de split pour la traçabilité). Le pipeline s'applique alors à chaque sous-story individuellement.
