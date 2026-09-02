# Research — Story s11b-frontend-chat

> Recherche en français. Code identifiers (snake_case, PascalCase) dans leur forme d'origine. Diacritiques : « élève », « réactivité », « téléchargement », « collège », «ächement ».

## 0. Statut du worktree et du repo (vérifié)

- **Worktree** : `C:\Workspace\ktutor\.worktrees\s11b-frontend-chat` — créé par le sous-agent `worktree-manager` (task `af3c807138668ae13`), branche `feature/s11b-frontend-chat`, `HEAD = 9133b09` (= `origin/main` post-`docs: design system`), `git status --porcelain` ne montre que `.env.bak` (gitignored, ne commit pas).
- **Branche par défaut locale** : `main` à `9133b09` après le commit de `docs/design-system.md`. Le sous-agent a créé le worktree **frais depuis main** : `pnpm install --frozen-lockfile` a réussi offline (643 paquets, 26.4s, 0 téléchargement).
- **`docs/reviews/stories.md` → `Stories ready: yes`** (`Max severity: minor`, 3 findings non-bloquants résiduels). Le périmètre de la story est validé.
- **Note process** : `docs/research/s11-frontend-upload-chat.md` (mémoire du projet, antérieur au split s11a/b/c) est conservé comme historique de la recherche initiale mais ne représente **plus** l'état actuel du code (s11a a été merge depuis, le scaffold Next.js existe, les 9 composants du design system sont shippés). Le research s11b est désormais l'entrée de référence pour cette story.

## 1. Les cinq faits structurants

1. **Le frontend s11a est shippé sur `main`** (`c3f1829`). 9 composants existent dans `frontend/components/` (Button, Card, FileUpload, Header, Input, Label, LanguageSwitcher, Select, StreamingMessage). Le design system est documenté dans `docs/design-system.md` (`9133b09`). Le bootstrap technique n'est **plus** un concern de s11b — la story travaille sur une base stable.
2. **`<StreamingMessage>` est un **squelette** livré par s11a** (`frontend/components/StreamingMessage.tsx:6-14`) avec seulement les props `isStreaming`, `hasContent`, `children`. Le TODO s11b est explicite : « connect to /api/chat/stream (fetch + ReadableStream, not EventSource) ». s11b **étend** ce squelette (ajout de `error?: ChatStreamError | null` et `sources?: SourceCitation[] | null`) sans le remplacer.
3. **Le contrat SSE s09 est figé** sur `main` (`backend/app/api/chat/router.py:64-134`, `sse.py:21-30`, `schemas.py:34-77`) avec 3 formes d'event : `{token}`, `{done, sources}`, `{error, code}`. Les codes mappés côté backend sont : `cross_tenant`, `no_subject`, `invalid_pseudo`, `unknown` (l.46-61). Le backend filtre déjà les tokens vides (l.99-102) et plafonne à `chat_stream_max_chunks` (défaut 5000). Headers SSE : `Cache-Control: no-cache`, `X-Accel-Buffering: no` (l.128-132). **Le frontend consomme, ne modifie pas le contrat.**
4. **`apiClient` axios est instancié** dans `frontend/lib/api.ts:18-23` avec `baseURL = NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'` et `Accept: application/json`. **MAIS** le commentaire l.7-8 dit explicitement : « chat and upload flows added in s11b/s11c import this client and rely on the baseURL ». s11b ne doit **pas** utiliser `apiClient` pour le stream (Piège P0 confirmé : axios bufferise par défaut). `apiClient` reste pour les futurs endpoints non-streaming.
5. **L'identité transitoire (cookie + store)** est verrouillée par `useAuthStore` (`frontend/lib/stores/authStore.ts`) avec la regex client `^[a-zA-Z0-9_]{3,32}$`. Le header `<Header>` duplique cette logique pour son input pseudo (`Header.tsx:45-58` appelle `isValidPseudo(trimmed)`). **TRAP détecté** : la regex backend (s09) est `^[a-zA-Z0-9_]+$` avec `min_length=1` (`schemas.py:31, 41-44`), donc un pseudo de 1 ou 2 caractères passe le backend mais est rejeté par le client. Le design system impose la regex 3-32 client-side. C'est cohérent (belt-and-braces), mais la story doit le savoir : un test qui envoie un pseudo `"a"` au backend réussirait côté HTTP, ce qui n'est **pas** ce que veut l'AC2 de s11b.

## 2. Rappel de la story

Source : `docs/stories.md:459-525`. 13 acceptance criteria, complexity 3.

**As an** élève **I want** chatter avec l'agent depuis l'interface web **so that** je voie la réponse s'afficher mot par mot.

**Dépend de** : s11a (merged `c3f1829`) + s09 (merged `c5f6163`) + s10 (merged `ff21046`).

**Ferme sur** : page `/chat` bout-en-bout, SSE consommé token par token, état d'erreur réseau/connexion coupée/erreur code-mappée, a11y WCAG 2.1 A, responsive 360/768, i18n FR/EN, ≥ 5 tests e2e Playwright.

## 3. État actuel du code (vérifié sur HEAD `9133b09`)

### 3.1. Ce qui existe déjà (s11a) et que s11b consomme

| Fichier | État | Usage pour s11b |
| --- | --- | --- |
| `frontend/app/globals.css` | Tokens CSS (light + dark) | Source des utility classes Tailwind. Pas de modification. |
| `frontend/tailwind.config.ts` | Mapping tokens → classes | `bg-primary`, `text-text-primary`, `rounded-md`, `shadow-kt-default`, `animate-pulse` |
| `frontend/components/StreamingMessage.tsx` | Squelette (props `isStreaming`, `hasContent`, `children`) | **Étendre** : ajouter `error?: ChatStreamError \| null` et `sources?: SourceCitation[] \| null` au type, rendre une card d'erreur si `error != null`, rendre une ligne « Sources : » si `sources != null`. Le typing indicator 3 points reste câblé sur `isStreaming && !hasContent`. |
| `frontend/components/Header.tsx` | Header sticky, lien `/chat` actuellement `aria-disabled="true"` (l.81) | **Débloquer** le lien `/chat` (l'AC9 de s11b dit « les liens desktop du header sont visibles »). Le lien `/upload` reste `aria-disabled="true"` en attendant s11c. |
| `frontend/components/Input.tsx` | Wrapper `<input>` (text + file) | Réutiliser pour la textarea (mais `<textarea>` ≠ `<input>` : il faut soit un nouveau `<Textarea>` partagé, soit un `<textarea>` natif avec les classes de design — c'est une décision de plan). |
| `frontend/components/Select.tsx` | Wrapper `<select>` (44 px, focus ring) | Réutiliser pour le sélecteur de matière. Options : `{value: 'maths', label: 'Mathématiques'}`, `{value: 'francais', label: 'Français'}` (cf. `schemas.py:48` — Literal `maths` \| `francais`). |
| `frontend/components/Label.tsx` | Wrapper `<label>` avec `htmlFor` + `srOnly?` | Réutiliser pour la matière, la question, l'input pseudo manquant. |
| `frontend/components/Card.tsx` | `Card.Header` / `Card.Body` / `Card.Footer` | Réutiliser pour la card d'erreur (warning/success/error states cf. design-system § UI patterns). |
| `frontend/components/Button.tsx` | Variants primary / secondary / ghost / destructive | Réutiliser pour « Envoyer » (primary), « Réessayer » (secondary), « Stop » (gap, hors-scope). |
| `frontend/lib/stores/authStore.ts` | Zustand `useAuthStore` avec `pseudo`, `hydrated`, `hydrate`, `setPseudo`, `clearPseudo`, `isValidPseudo` | **Lire** le pseudo côté client. `useAuthStore.getState().pseudo` (cf. ADR 011 — `path=/; max-age=30d; SameSite=Lax`). |
| `frontend/lib/api.ts` | `apiClient` axios + `API_BASE_URL` | **Ne pas utiliser pour le stream** (axios bufferise). Garder pour le jour où un endpoint non-streaming apparaît. |
| `frontend/messages/fr.json` + `en.json` | Namespaces `common`, `home`, `header` remplis ; `chat: {}`, `upload: {}`, `errors: {}` vides | **Remplir** le namespace `chat` (~12-15 clés) et le namespace `errors` (codes d'erreur mappés) en fr ET en. |
| `frontend/lighthouserc.json` | Audite `/fr/` | **Étendre** à `/fr/chat` (AC10 de s11b). `/en/chat` optionnel selon les moyens CI (gap potentiel à noter en review). |
| `frontend/playwright.config.ts` | baseURL `http://localhost:3000`, webServer `pnpm dev` | Réutiliser tel quel. Les tests s11b s'ajoutent dans `frontend/e2e/chat.spec.ts`. |
| `frontend/e2e/{home,pseudo,responsive}.spec.ts` | 3 specs s11a (10 tests) | Pattern à dupliquer pour s11b : `page.goto('/fr/chat')`, `getByLabel(...)`, `getByRole(...)`, `AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa'])`. |
| `frontend/middleware.ts` + `frontend/i18n/routing.ts` | next-intl middleware | Réutiliser. Le toggle FR/EN est déjà testé par `home.spec.ts` (l.30-39). |

### 3.2. Ce qui n'existe **pas** encore (à créer dans s11b)

- `frontend/app/(public)/[locale]/chat/page.tsx` — la page chat.
- `frontend/lib/stores/chatStore.ts` — le store Zustand du chat.
- `frontend/lib/api/chat.ts` — helper pur de parsing SSE (séparable du store pour faciliter les tests unitaires futurs).
- `frontend/e2e/chat.spec.ts` — ≥ 5 tests e2e (AC11).

### 3.3. Backend (déjà sur main, contracts figés)

**`POST /api/chat/stream`** (`backend/app/api/chat/router.py:64-134`) — **vérifié ligne par ligne** :
- Body : `ChatStreamRequest { pseudo: str (regex `^[a-zA-Z0-9_]+$`, 1-32 chars), subject: Literal["maths", "francais"], question: str (1-2000 chars) }`.
- Réponse : `StreamingResponse(media_type="text/event-stream")` avec headers `Cache-Control: no-cache` et `X-Accel-Buffering: no`.
- Événements SSE (préfixe `data: ` + JSON + `\n\n`) :
  - `{"token": "..."}` — incrémental. Le backend ignore les `event.content` vides (commentaire l.100-101), mais le frontend doit quand même gérer un `{token: ""}` sans crash (concat no-op).
  - `{"done": true, "sources": [{"filename", "chunk_index"}]}` — final, exactement une fois.
  - `{"error": "...", "code": "..."}` — sur `ValueError` agent. Codes : `cross_tenant`, `no_subject`, `invalid_pseudo`, `unknown` (mappés par `_map_code` substring match l.46-61).
- Erreurs Pydantic 422 **AVANT** ouverture du stream (commentaire `schemas.py:6-8`). Donc si le body est mal formé, le frontend ne reçoit **jamais** de stream — il reçoit un 422 JSON.
- Safety net : `max_chunks` (défaut 5000) → après N chunks, émet un `data: {error: "Stream exceeded the N-chunk safety net.", code: "unknown"}` puis ferme (l.88-98).

**`format_sse`** (`backend/app/api/chat/sse.py:21-30`) — vérifié : `f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode()`. `ensure_ascii=False` préserve les accents UTF-8. Le frontend n'a pas besoin de `unescape` Unicode.

### 3.4. CORS et dev server

- Backend CORS : `Settings.cors_allow_origins` défaut `http://localhost:3000` (cf. `backend/app/core/config.py:30`). Le frontend dev tourne sur le port 3000.
- Le frontend appelle `process.env.NEXT_PUBLIC_API_URL + '/api/chat/stream'` **directement** (pas via une route Next.js proxyfiée — décision D3 de la research s11). CORS est déjà géré côté backend, et ça évite le piège du buffering Next.js (Piège #3 de la research s11 : « le dev server bufferise le SSE »).
- Le `next dev` n'a pas besoin de configuration spéciale pour le SSE puisque le browser parle directement à `:8000`.

## 4. Anchor points (où s11b se branche)

| Code backend | Anchor | À utiliser côté frontend |
| --- | --- | --- |
| `backend/app/api/chat/router.py:64` | `@router.post("/stream")` | `POST ${NEXT_PUBLIC_API_URL}/api/chat/stream` |
| `backend/app/api/chat/router.py:99-112` | Boucle `event_generator` | Le frontend doit parser 3 formes : `{token}`, `{done, sources}`, `{error, code}`. |
| `backend/app/api/chat/router.py:117-122` | `except ValueError` → SSE error event | Le frontend mappe `code` sur un message i18n (`chat.errors.cross_tenant`, etc.). |
| `backend/app/api/chat/sse.py:30` | `format_sse` | Le frontend parse la ligne `data: <json>\n\n` (strip préfixe `data: `, parse JSON). |
| `backend/app/api/chat/schemas.py:34-57` | `ChatStreamRequest` | Le body envoyé : `{pseudo, subject, question}`. Validation côté client (regex pseudo, question 1-2000) = UX ; côté backend = sécurité. |
| `backend/app/api/chat/schemas.py:60-77` | `StreamErrorEvent` | Type frontend : `{error: string, code: 'cross_tenant' \| 'no_subject' \| 'invalid_pseudo' \| 'unknown'}`. |

| Code frontend (s11a) | Anchor | Action s11b |
| --- | --- | --- |
| `frontend/components/StreamingMessage.tsx:16-20` | `StreamingMessageProps` | Étendre avec `error?: ChatStreamError \| null` et `sources?: SourceCitation[] \| null`. |
| `frontend/components/StreamingMessage.tsx:29-38` | Wrapper `role="log"` | Ajouter le rendu conditionnel : si `error != null` → `<Card>` d'erreur ; si `sources != null` → ligne « Sources : … » après les tokens. |
| `frontend/components/Header.tsx:79-84` | `<Link href="/chat" aria-disabled="true">` | Retirer `aria-disabled="true"` et le `tabindex="-1"` (s11b rend `/chat` actif). |
| `frontend/lib/stores/authStore.ts:19-21, 60-66` | `isValidPseudo` + `setPseudo` | Lire `useAuthStore.getState().pseudo` dans le `chatStore.send`. |
| `frontend/messages/fr.json:24-26` | `"chat": {}, "errors": {}, "upload": {}` | Remplir les namespaces `chat` et `errors` (fr ET en). |

## 5. Pièges identifiés

### P1 — `EventSource` vs `fetch` + `ReadableStream` (P0, ADR 006)

`EventSource` ne supporte pas `POST` et impose `text/event-stream` sans pouvoir customiser les headers (impossible d'envoyer `Content-Type: application/json` proprement, et le re-fit `Authorization: Bearer` en s15 ne passera pas). **Décision** : `fetch(url, { method: 'POST', body: JSON.stringify(...), signal: AbortController.signal, headers: { 'Accept': 'text/event-stream' } })` + `response.body!.getReader()` + `TextDecoder('utf-8')` + parser ligne par ligne.

Mitigation : isoler le parsing dans `frontend/lib/api/chat.ts` (fonction pure `parseSSEChunk(text: string): SSEEvent[]`) pour pouvoir le tester unitairement. Le store appelle ce helper.

### P2 — Buffering du dev server Next.js (P0, Piège #3 research s11)

Le dev server Next.js peut bufferiser les réponses. **Mitigation déjà appliquée** : le frontend appelle directement `${NEXT_PUBLIC_API_URL}/api/chat/stream` (cross-origin vers `:8000`), pas via une route Next.js. Le backend émet `X-Accel-Buffering: no` (l.131), ce qui désactive le buffering nginx. **Côté JS** : ne jamais faire `await response.text()` (qui bufferise), toujours lire via `getReader()` chunk par chunk.

### P3 — Tokens vides en début de stream (P1, Piège #6 research s11)

Le backend filtre les `event.content` vides, mais le LLM upstream peut émettre un `{token: ""}` (commentaire backend l.100-101). Le frontend doit gérer `{token: ""}` comme un no-op (concat vide, pas d'erreur).

### P4 — `prefers-reduced-motion` sur le typing indicator (P1, Piège #7 research s11)

Le `animate-pulse` Tailwind v4 doit être désactivé via `motion-reduce:animate-none`. Le squelette actuel de `StreamingMessage.tsx:46-55` n'a **pas** cette classe — gap à corriger en s11b (cf. design-system § A11y).

### P5 — `<html lang>` hardcodé à `fr` en s11a (P2, retour s11a Minor #2)

Le test Playwright (e) « toggle FR/EN bascule toute l'UI chat en anglais » devrait fonctionner côté contenu (le `<LanguageSwitcher>` et `useTranslations` sont client-side), mais Lighthouse `/en/chat` pourrait chuter parce que `<html lang="fr">` ne reflète pas la locale. **Mitigation** : hors-scope s11b, gap à noter dans la review (suivi s22).

### P6 — `output: "standalone"` omis dans `next.config.ts` (P2, retour s11a Minor #3)

EPERM Windows sur le build standalone. Lighthouse en prod peut demander la refacto. **Mitigation** : hors-scope s11b.

### P7 — `aria-disabled` sur lien désactivé (P0, Piège #11 + retour s11a Minor #1)

Le header `<Link href="/upload" aria-disabled="true">` (`Header.tsx:86-91`) **doit** avoir `tabindex="-1"` en plus (cf. design-system l.228). Le lien `/chat` perd son `aria-disabled="true"` (s11b le rend actif). Le lien `/upload` reste désactivé tant que s11c n'est pas merge. **Note** : le code actuel n'a **pas** `tabindex="-1"` sur le lien `/upload` — c'est un trou à corriger en s11b pour rester cohérent avec le design system (cf. ligne 230 du design-system.md).

### P8 — Connexion coupée avant `done` (P0, trap spécifique SSE)

Une erreur proxy (ngrok, Cloudflare) peut couper le stream avant le `done`. Le handler fetch doit détecter `reader.closed` (ou `read()` qui throw) et afficher « Connexion perdue. Réessayer ? ». Le test (c) couvre uniquement `{error, code: "unknown"}` — la coupure réseau est plus difficile à stubber. **Recommandation** : `page.route` qui retourne un `Response` avec un `ReadableStream` qu'on abort après N octets (`controller.enqueue(...)` puis `controller.close()` ou `controller.error(new Error('aborted'))`).

### P9 — Double-invocation React StrictMode (P1)

`reactStrictMode: true` (Next.js 16) double-invoque les composants en dev. Le `fetch` SSE peut être appelé 2× → connexions multiples. **Mitigation** : `useRef<AbortController>` dans le composant, fermer le précédent avant d'en créer un nouveau. Le store Zustand doit être idempotent (deux `send` rapides → un seul stream actif).

### P10 — Linter check-i18n.sh doit exit 0 (P0)

Le script `frontend/scripts/check-i18n.sh` (déjà en s11a) interdit les chaînes en dur dans les composants, pages et stores. Le `chatStore.ts` ne doit avoir **aucun** literal i18nisé en dur. Tous les messages d'erreur, libellés de bouton, placeholder, etc. passent par `useTranslations('chat')` ou `useTranslations('errors')`.

### P11 — Regex client ≠ regex backend (P1, trap spécifique)

Backend : `^[a-zA-Z0-9_]+$` (1-32) — accepte `"a"`, `"ab"`.
Client : `^[a-zA-Z0-9_]{3,32}$` (3-32) — refuse `"a"`, `"ab"`, accepte `"ali_baba"`.

**Comportement attendu par l'AC2** : le bouton Envoyer est désactivé tant que le pseudo n'est pas valide selon la regex **client** (3-32). Un pseudo court ne peut donc pas être envoyé via l'UI. Si un attaquant bypass l'UI (curl direct), le backend accepte — c'est un risque accepté par ADR 011 (pré-JWT). **Pas un blocker**, mais à documenter dans le commentaire de tête de `chatStore.ts`.

### P12 — `text/event-stream` content-type sur le mock Playwright (P1)

Le test (b) doit stubber un SSE via `page.route('**/api/chat/stream', route => route.fulfill({ status: 200, headers: { 'Content-Type': 'text/event-stream' }, body: 'data: {"token":"foo"}\n\ndata: {"token":"bar"}\n\ndata: {"done":true,"sources":[]}\n\n' }))`. **Important** : le `body` peut être une string OU un `ReadableStream`. Pour un stream avec flush progressif, il faut un `ReadableStream` (cf. MDN Response.body + Playwright `page.route`).

### P13 — `i18nKey` dynamique dans le store Zustand (P2)

Le store ne peut pas appeler `useTranslations()` (hook React, pas Zustand). Les codes d'erreur sont mappés sur des **clés i18n**, et le composant (`page.tsx`) fait `t(errorKey)`. Pattern recommandé :

```ts
// chatStore.ts
error: ChatStreamError = { code: 'cross_tenant', i18nKey: 'chat.errors.cross_tenant' }

// page.tsx
const t = useTranslations('chat');
{error && <Card>{t(`errors.${error.code}`)}</Card>}
```

## 6. Questions ouvertes (à trancher en `ks-plan` ou PR)

### Q1 — Faut-il un bouton « Stop » pour interrompre un stream en cours ?

L'AC7 original du story mentionnait ce bouton mais l'AC actuel de s11b ne l'inclut pas (cf. design-system § 10 gaps : « ajouté dans une story ultérieure »). **Recommandation** : hors-scope s11b, gap à noter dans la review, suivi **s22** (a11y/UX pass).

### Q2 — Cumul des messages (historique de conversation) ?

L'AC1 demande « question + matière + réponse streamée » (singulier) ; le design § 4.4 parle d'un « flux vertical » (implicite : cumulatif). **Recommandation** : `chatStore.messages` est cumulatif en mémoire (un message user + un message assistant par question). Persistance côté backend = **s19** (`/chat/history`). Pas d'historique persistant en s11b.

### Q3 — Comment stubber un SSE coupé dans le test Playwright ?

Le test (c) couvre `{error, code}` (coupure propre). Pour tester « connexion perdue avant done », il faut un mock qui coupe le stream brutalement. **Recommandation** : `page.route` avec un `ReadableStream` dont le `start(controller)` enqueue quelques chunks puis `controller.error(new Error('network lost'))`. Si trop complexe pour l'AC11, **gap** à noter dans la review, suivi s22.

### Q4 — Le namespace `chat` doit-il gérer les codes d'erreur via `errors.*` ou `chat.errors.*` ?

Les catalogues actuels (`fr.json:24-26`) ont `chat: {}` et `errors: {}` séparés. **Recommandation** : `chat.*` pour les libellés chat-spécifiques (titre, placeholder, sélecteur matière, bouton Envoyer, label Sources, message connexion perdue, message pseudo manquant) ; `errors.*` pour les codes (`cross_tenant`, `no_subject`, `invalid_pseudo`, `unknown`). Le store retourne `{code, i18nKey}` où `i18nKey = 'errors.${code}'`, et la page fait `t(errorKey)`.

### Q5 — Le test e2e (e) « toggle FR/EN » : reload ou pas ?

Le test `home.spec.ts:30-39` (s11a) ne recharge pas — il clique sur EN et attend que l'URL change. Le middleware next-intl écrit le cookie `NEXT_LOCALE=en` et le `useTranslations('chat')` côté client bascule. **Recommandation** : pour le test (e) de s11b, suivre le même pattern (pas de reload), juste `await expect(page.getByRole('heading', { name: '...' })).toBeVisible()` avec le libellé EN.

### Q6 — Le store `chatStore` doit-il avoir un `AbortController` interne ou le composant le gère-t-il ?

**Recommandation** : `chatStore.send(input)` retourne une `Promise<void>` qui résout quand le stream est terminé. Le composant stocke l'`AbortController` dans un `useRef` pour pouvoir annuler sur unmount (évite les warnings React « state update on unmounted component »). Le store **n'a pas** à connaître l'AbortController — il fait `fetch` direct. La séparation des concerns (store = état pur, composant = cycle de vie) est plus testable.

### Q7 — Le typing indicator doit-il disparaître dès le 1er token ou après N tokens ?

Le squelette actuel : `isStreaming && !hasContent` (1er token fait disparaître les points). **Recommandation** : garder ce comportement (le design system dit « Tant que `isStreaming && !hasContent` »). Si l'utilisateur trouve le flashing trop rapide, ajustement en s22.

### Q8 — Le placeholder de la textarea doit-il afficher une longueur (« 1-2000 caractères ») ?

Le backend plafonne à 2000 chars (`schemas.py:55`). **Recommandation** : `placeholder={t('placeholder')}` sans mention de longueur dans le placeholder, mais afficher un compteur `2000 chars max` sous la textarea via `aria-describedby` quand on s'approche de la limite. Cf. AC1 « 1-2000 chars ».

## 7. Faux premises et invalidez détectées

- **« `<StreamingMessage>` est complet en s11a »** : FAUX. C'est un squelette, l'extension (props `error`/`sources`, rendu conditionnel) fait partie de s11b.
- **« Utiliser `apiClient` axios pour le stream »** : FAUX. Axios bufferise par défaut. `chatStore.send` fait un `fetch` direct.
- **« Le lien `/chat` du header est actif en s11a »** : FAUX. Il a `aria-disabled="true"` (Header.tsx:81). s11b le débloque.
- **« L'AC10 Lighthouse audite déjà `/fr/chat` »** : FAUX. `lighthouserc.json:8` n'audite que `http://localhost:3000/fr/`. s11b doit étendre à `/fr/chat`.
- **« Le backend renvoie 422 sur pseudo court »** : FAUX pour s09. Le backend accepte `^[a-zA-Z0-9_]+$` (1-32). Seul le client (regex 3-32) refuse. Belt-and-braces, à documenter.
- **« Le namespace `chat` est vide, c'est un oubli de s11a »** : Vrai et attendu. C'est l'espace réservé pour s11b. Idem `errors` et `upload`.

## 8. Real complexity et verdict

**Score docs/stories.md** : **3**.

**Score après ouverture du code** : **3**.

**Justification du maintien à 3** :
- ✅ Pas de bootstrap : s11a a fait le gros du travail. La base technique est stable.
- ✅ Contrat SSE s09 figé et bien documenté (3 formes d'event, codes d'erreur, headers, safety net).
- ✅ Composants UI déjà disponibles (Input, Select, Button, Card, Label, StreamingMessage squelette). La textarea est le seul élément à créer (trivial — `<textarea>` natif avec classes Tailwind, ou nouveau `<Textarea>` partagé, c'est une décision de plan).
- ✅ Store `authStore` prêt à être lu.
- ⚠️ SSE parsing manuel : 1 tâche, isolable dans `frontend/lib/api/chat.ts` (fonction pure, testable).
- ⚠️ Mapping erreurs : 1 tâche (4 codes → 4 clés i18n).
- ⚠️ Tests e2e : 5 tests, mais pattern Playwright déjà rodé (s11a).
- ⚠️ Namespace i18n : 12-15 clés × 2 langues = ~25-30 entrées, mais c'est de la config.
- ⚠️ Extension `<StreamingMessage>` : 1 tâche, props + rendu conditionnel.
- ⚠️ Page `chat/page.tsx` : 1 tâche, suit le pattern de `home/page.tsx`.

**Risques résiduels** (P0-P1) :
- R1 — La regex backend ≠ regex client peut surprendre un reviewer (P11, P1).
- R2 — Le test Playwright (b) doit stubber un SSE correctement (P12, P1).
- R3 — `chatStore.send` doit être idempotent sous StrictMode (P9, P1).
- R4 — Le `tabindex="-1"` sur le lien `/upload` du header doit être ajouté en même temps que le déblocage de `/chat` (P7, P0).

**Pas de split proposé** : la story est faisable en une PR d'environ **15-20 fichiers** et **~500-800 lignes ajoutées** (vs 3000 pour s11a monolithique). Les concerns sont liés (page + store + parser + tests), les scinder ajouterait de la friction sans réduire le risque.

## 9. Pré-requis pour passer à `/ks-design` puis `/ks-plan`

- **Décision D1** : `chat` namespace = libellés chat, `errors` namespace = codes d'erreur mappés. À valider en `/ks-design` (impliqué par Q4).
- **Décision D2** : `<Textarea>` partagé dans `frontend/components/Textarea.tsx` ou `<textarea>` natif dans la page ? **Recommandation** : composant partagé (réutilisable par s11c pour les descriptions, et par les formulaires d'admin en s17+).
- **Décision D3** : `chatStore.send` retourne `Promise<void>` ou expose un `cancel()` ? **Recommandation** : `Promise<void>` simple, l'AbortController vit dans le composant.
- **Décision D4** : Quelle stratégie pour le test « connexion perdue » ? **Recommandation** : gap assumé en s11b, à noter dans la review. Test du flux `{error, code}` suffit pour l'AC11.
- **Décision D5** : Lighthouse `/en/chat` ou pas ? **Recommandation** : étendre à `/fr/chat` seulement (cf. AC10). Le `<html lang>` dynamique est un gap s22, mais l'audit `/fr/chat` reste valide.

Une fois ces décisions tranchées, **`/ks-design s11b-frontend-chat`** peut produire `docs/designs/s11b-frontend-chat.md` (mockup du sélecteur matière + textarea + zone de stream + card d'erreur), puis **`/ks-plan s11b-frontend-chat`** peut découper la story en tâches.

## 10. Sources (vérifiées sur HEAD `9133b09`)

### Code lu

- `backend/app/api/chat/router.py` (134 lignes) — endpoint, event_generator, _map_code.
- `backend/app/api/chat/sse.py` (30 lignes) — format_sse, ensure_ascii=False.
- `backend/app/api/chat/schemas.py` (77 lignes) — ChatStreamRequest, StreamErrorEvent.
- `frontend/components/StreamingMessage.tsx` (59 lignes) — squelette, typing indicator.
- `frontend/components/Header.tsx` (133 lignes) — header, lien /chat aria-disabled, input pseudo.
- `frontend/components/Select.tsx` (41 lignes) — wrapper select, 44 px, focus ring.
- `frontend/lib/api.ts` (25 lignes) — apiClient axios, baseURL.
- `frontend/lib/stores/authStore.ts` (76 lignes) — useAuthStore, isValidPseudo, cookie.
- `frontend/messages/fr.json` + `en.json` — namespaces existants.
- `frontend/lighthouserc.json` — config actuelle (`/fr/`).
- `frontend/playwright.config.ts` (40 lignes) — baseURL, webServer, projects.
- `frontend/e2e/home.spec.ts` (68 lignes) — pattern Playwright + AxeBuilder.
- `frontend/e2e/pseudo.spec.ts` (46 lignes) — pattern getByLabel.
- `frontend/e2e/responsive.spec.ts` (37 lignes) — pattern setViewportSize.
- `frontend/app/(public)/[locale]/page.tsx` (56 lignes) — pattern Server Component + getTranslations.

### Spécification lue

- `docs/stories.md:459-525` — story s11b complète (13 ACs, complexité 3, dépendances, agentic notes, traps, open questions, out-of-scope).
- `docs/design-system.md` (commit 9133b09) — tokens, composants, UI patterns, a11y, i18n, Do/Don't, gaps.
- `docs/architecture.md` § Frontend — stack imposée, route groups, hydration.
- `docs/decisions/011-frontend-pseudo-cookie-pre-jwt.md` — pourquoi le pseudo est en cookie, pas en URL/body.
- `AGENTS.md` § Frontend (l.108-120) — conventions Zustand, API client, identités, i18n, a11y, composants UI.
- `CLAUDE.md` § Stack + § Variables d'Environnement — `NEXT_PUBLIC_API_URL`, port 3000 frontend, port 8000 backend.
- `docs/research/s11-frontend-upload-chat.md` — recherche initiale pré-split, conservée pour mémoire historique (Piège #1-#12 documentés).

### Code adjacent non lu (out of scope strict)

- `backend/app/services/agents/supervisor.py` — le frontend ne parle qu'à l'API, pas au service.
- `backend/app/services/agents/factory.py` — pareil, opaque pour le frontend.
- `frontend/app/layout.tsx` et `frontend/app/(public)/[locale]/layout.tsx` — pattern Server Component, le composant chat est une page client, le layout est serveur.

## 11. Conclusion

La story s11b-frontend-chat est **faisable en l'état** sur la base de ce qui est déjà shippé. Le contrat SSE s09 est figé, les composants UI existent (sauf la textarea), le store d'identité est prêt. Les pièges sont identifiés et les questions ouvertes sont tranchables en `/ks-plan`.

**Next step** : `/ks-design s11b-frontend-chat` pour produire le mockup de la page chat (sélecteur matière, textarea, zone de stream avec typing indicator, card d'erreur, ligne « Sources : »), puis `/ks-plan s11b-frontend-chat` pour découper en tâches TDD.
