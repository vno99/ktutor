---
validated: yes
---

# Plan — Story s11b-frontend-chat

Branch: `feature/s11b-frontend-chat`
Research: `docs/research/s11b-frontend-chat.md` — read it first; this plan does not repeat it.
Design: `docs/designs/s11b-frontend-chat.md` (mockup : `docs/designs/s11b-frontend-chat.html`)

## Target story

> **s11b-frontend-chat** — Page `/chat` avec streaming SSE (split 2/3, gated by s11a)
>
> **As an** élève **I want** chatter avec l'agent depuis l'interface web **so that** je voie la réponse s'afficher mot par mot.
>
> **Complexity (story)** : **3** — Maintenu à 3 après research (5 faits structurants, 13 pièges identifiés, 8 questions ouvertes tranchées). Pas de split additionnel proposé.
>
> **Dépendances mergées** (vérifiées) : s11a `c3f1829` (scaffold + design system + authStore cookie-backed), s09 `c5f6163` (contrat SSE figé), s10 `ff21046` (axios instancié dans `frontend/lib/api.ts` — non utilisé pour le stream).
>
> **AC couverts (13, `docs/stories.md:471-483`)** : cf. story file pour le détail exhaustif. En résumé :
> 1. Page `/{locale}/chat` rend sélecteur matière + textarea + bouton « Envoyer » + zone de stream, tous les libellés via `useTranslations('chat')`.
> 2. Bouton « Envoyer » désactivé tant que pseudo invalide / matière vide / question vide (`aria-disabled="true"` + `tabindex="-1"`).
> 3. Envoi = `POST ${NEXT_PUBLIC_API_URL}/api/chat/stream` (fetch direct, PAS axios, PAS EventSource), body `{ pseudo, subject, question }`.
> 4. Consommation SSE via `fetch().body.getReader()` : parse 3 formes `{token}` / `{done, sources}` / `{error, code}`.
> 5. Zone de réponse = `<StreamingMessage>` étendu (`role="log"`, `aria-live="polite"`, `aria-busy`).
> 6. Erreurs 4xx/5xx → « Erreur réseau. Vérifie ta connexion. » + bouton « Réessayer ». Connexion coupée avant `done` → « Connexion perdue. Réessayer ? ».
> 7. Pseudo manquant/invalide → label warning + `aria-invalid="true"` sur l'input header + bouton Envoyer désactivé.
> 8. `chatStore` Zustand avec `{ messages, isStreaming, lastQuestion, send, retry, reset }`, hydratation client-side.
> 9. Responsive 360px (textarea+bouton full-width, liens desktop header masqués) et 768px (`max-w-3xl`, liens header visibles), pas de scroll horizontal.
> 10. Axe-core 0 violation critical/serious sur `/fr/chat` ET `/en/chat` ; Lighthouse Accessibility ≥ 90 sur `/fr/chat`.
> 11. ≥ 5 tests e2e Playwright dans `frontend/e2e/chat.spec.ts` : (a) rendu + htmlFor, (b) SSE stubbé token-par-token, (c) erreur code-mappée + bouton Réessayer, (d) navigation clavier, (e) toggle FR/EN.
> 12. `check-i18n.sh` exit 0 ; lint + typecheck + build + Playwright verts.
> 13. Commentaire en tête de `chatStore.ts` référençant `backend/app/api/chat/router.py:64-134`, `sse.py:21-30`, `schemas.py:34-77` et explicitant les 3 formes d'event.

### Décisions héritées (research D1-D5 + design)

| Q / D | Décision | Justification |
|---|---|---|
| D1 (i18n) | `chat.*` = libellés chat, `errors.*` = codes mappés | Sépare le domaine (chat) de la couche (erreurs). Réutilisable par s11c. |
| D2 (Textarea) | **Composant partagé** `frontend/components/Textarea.tsx` | Réutilisable par s11c (descriptions) et admin (s17+). API calquée sur `<Input>` (forwardRef, 44 px min, focus ring, `maxLength`, `invalid`). |
| D3 (AbortController) | `chatStore.send` retourne `Promise<void>`, l'`AbortController` vit dans `useRef` du composant | Séparation store / cycle de vie. Le store est testable sans DOM. |
| D4 (test « connexion perdue ») | **Gap assumé en s11b** | Le test (c) couvre `{error, code}` (coupure propre). Le coup brutal de stream (mock ReadableStream aborté) est trop complexe pour l'AC11 — noté en review, suivi s22. |
| D5 (Lighthouse /en/chat) | Étendre à `/fr/chat` seulement | `<html lang>` dynamique est un gap s22 (cf. retour s11a Minor #2). Audit `/en/chat` chuterait artificiellement. |
| Q2 (historique) | `chatStore.messages` cumulatif en mémoire | Persistance s19. L'AC1 dit « question + matière + réponse streamée » (singulier implicite) — le design cumulatif enrichit l'UX sans contredire l'AC. |
| Q4 (i18n namespace codes erreur) | `errors.cross_tenant`, `errors.no_subject`, `errors.invalid_pseudo`, `errors.unknown`, `errors.network`, `errors.lost` | Cohérent avec le catalogue fr.json actuel (namespace `errors: {}` vide). |

### Travail transverse obligatoire avant T1

Aucun. Les dépendances (s11a, s09, s10) sont mergées, le design system est sur `main` (commit `9133b09`), la worktree existe et est sur la branche `feature/s11b-frontend-chat`.

## Tasks (ordered)

> **Ordre TDD strict** : test rouge → code minimal → test vert. **Commit unique en fin de story** (AGENTS.md § Pipeline). Toutes les tâches produisent un livrable observable.

### Phase 1 — Composant `<Textarea>` partagé (nouveau, gap design system)

- [x] **T1.1** — Créer `frontend/components/Textarea.test.tsx` (test unitaire) :
  - Vérifie : (a) le composant rend un `<textarea>` avec l'`id` passé en prop, (b) applique `min-h-24` (4 lignes), (c) applique `aria-invalid="true"` quand `invalid` est `true`, (d) expose un `forwardRef<HTMLTextAreaElement>`, (e) accepte `maxLength` et le passe au `<textarea>` natif.
  - **Test rouge attendu** : `pnpm exec vitest run Textarea` (ou équivalent) → module not found.

- [x] **T1.2** — Créer `frontend/components/Textarea.tsx` :
  - `forwardRef<HTMLTextAreaElement, TextareaProps>`, props : `id: string`, `invalid?: boolean`, `maxLength?: number`, plus toutes les `TextareaHTMLAttributes` standard (via `Omit<…, 'id'>`).
  - Classes de base calquées sur `<Input>` (l.18-21) : `block w-full min-h-24 rounded-sm bg-surface text-text-primary placeholder:text-text-tertiary border focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/30 focus-visible:ring-offset-2 focus-visible:ring-offset-canvas transition-colors px-3 py-2 border-border focus:border-primary disabled:opacity-50 disabled:cursor-not-allowed`. `invalid` → `border-error`.
  - Commentaire en tête : « Réutilisable par s11c (descriptions), s17+ (formulaires admin). Convention alignée sur `<Input>`. ».
  - **Test vert** : `pnpm exec vitest run Textarea` passe les 5 assertions.

### Phase 2 — Helper pur de parsing SSE (logique testable isolée du store)

- [x] **T2.1** — Créer `frontend/lib/api/chat.test.ts` (test unitaire) :
  - Cas couverts : (a) ligne `data: {"token":"a"}\n\n` → `[{type:'token', content:'a'}]`, (b) ligne `data: {"token":""}\n\n` → `[{type:'token', content:''}]` (no-op accepté), (c) `data: {"done":true,"sources":[{"filename":"x.pdf","chunk_index":0}]}\n\n` → `[{type:'done', sources:[…]}]`, (d) `data: {"error":"oops","code":"unknown"}\n\n` → `[{type:'error', error:'oops', code:'unknown'}]`, (e) chunk vide ignoré, (f) `data:` vide (commentaire SSE) ignoré, (g) chunk avec plusieurs events collés (`data: {…}\n\ndata: {…}\n\n`) → 2 events parsés.
  - **Test rouge attendu** : module not found.

- [x] **T2.2** — Créer `frontend/lib/api/chat.ts` :
  - Types exportés : `type SSEEvent = { type: 'token'; content: string } | { type: 'done'; sources: SourceCitation[] } | { type: 'error'; error: string; code: ChatStreamErrorCode }`, `type SourceCitation = { filename: string; chunk_index: number }`, `type ChatStreamErrorCode = 'cross_tenant' | 'no_subject' | 'invalid_pseudo' | 'unknown'`.
  - Fonction `parseSSEChunk(raw: string): SSEEvent[]` : split par `\n\n`, pour chaque bloc garder les lignes commençant par `data: `, strip le préfixe, `JSON.parse` le reste, map vers le discriminated union. Lignes `data:` (vide) et `:` (commentaire) ignorées. Erreurs de parse → retourne `[]` (le store log un warning en dev).
  - **Test vert** : tous les cas T2.1 passent.
  - Commentaire en tête référençant `backend/app/api/chat/sse.py:21-30` (format exact) et `router.py:99-112` (boucle event_generator).

### Phase 3 — `chatStore` Zustand + extension `<StreamingMessage>`

- [x] **T3.1** — Créer `frontend/lib/stores/chatStore.ts` :
  - Types : `type Role = 'user' | 'assistant'`, `type ChatMessage = { role: Role; content: string; sources?: SourceCitation[] | null; error?: ChatStreamError | null }`, `type ChatStreamError = { code: ChatStreamErrorCode; message: string }`. `SourceCitation` et `ChatStreamErrorCode` réimportés depuis `frontend/lib/api/chat.ts`.
  - State : `{ messages: ChatMessage[], isStreaming: boolean, lastQuestion: string | null, lastInput: ChatInput | null, hydrated: boolean, hydrate: () => void, send: (input) => Promise<void>, retry: () => Promise<void>, reset: () => void }`. `ChatInput = { subject: 'maths' | 'francais'; question: string }`.
  - `hydrate()` : no-op (Zustand n'a pas de persistence ici ; l'identité transitoire reste sur `useAuthStore`).
  - `send(input)` :
    1. Lit `useAuthStore.getState().pseudo` ; si invalide → set `messages[last].error = { code: 'invalid_pseudo', message: '' }` et return.
    2. Push un message user `{role:'user', content: input.question}`.
    3. Push un message assistant vide `{role:'assistant', content: '', sources: null, error: null}`.
    4. `set({ isStreaming: true, lastQuestion: input.question, lastInput: input })`.
    5. `fetch(${process.env.NEXT_PUBLIC_API_URL}/api/chat/stream, { method: 'POST', headers: { 'Content-Type': 'application/json', 'Accept': 'text/event-stream' }, body: JSON.stringify({ pseudo, subject: input.subject, question: input.question }) })`.
    6. Si `!response.ok` → set le message assistant `error = { code: 'unknown', message: '' }`, `isStreaming = false`, return.
    7. Lit le stream via `response.body!.getReader()` + `TextDecoder('utf-8')` ; accumule dans un buffer texte, split par `\n\n`, pour chaque bloc applique `parseSSEChunk(block)`. Sur event `token` → append `content` au dernier message assistant. Sur event `done` → set `sources`. Sur event `error` → set `error` sur le dernier message assistant et stop. Quand le reader ferme → `isStreaming = false`.
    8. **Try/catch** autour de `getReader().read()` : si throw → set `error = { code: 'lost', message: '' }` (ou un nouveau code dédié à la coupure — décision finale à l'implémentation ; le test (c) ne couvre que `{error, code: 'unknown'}`).
  - `retry()` : si `lastInput != null` → `send(lastInput)`.
  - `reset()` : clear `messages`, `lastQuestion = null`, `lastInput = null`, `isStreaming = false`.
  - `AbortController` : pas dans le store. Le composant (T4.x) gère le cycle de vie.
  - Idempotence : `send` no-op si `isStreaming === true` (évite la double-invocation StrictMode, P9).
  - Commentaire en tête référençant `backend/app/api/chat/router.py:64-134`, `sse.py:21-30`, `schemas.py:34-77`. Explicite les 3 formes d'event. Note la divergence regex client (3-32) vs backend (1-32) — ADR 011.
  - **Test rouge attendu** : pas de test unitaire pour le store (le fetch est non-mockable sans infrastructure ; AC11 le couvre en e2e). Le test de comportement se fait via Playwright.
  - **Test vert** : `pnpm run typecheck` passe sur le nouveau store.

- [x] **T3.2** — Étendre `frontend/components/StreamingMessage.tsx` (squelette de s11a) :
  - Props : ajouter `error?: ChatStreamError | null`, `sources?: SourceCitation[] | null`, `streamingStatus?: 'idle' | 'streaming' | 'done' | 'error'`. Conserver rétrocompat : `isStreaming` et `hasContent` deviennent optionnels (s11a les utilisait encore).
  - Rendu : si `error != null` → `<Card>` d'erreur avec `<Button variant="secondary" size="sm">Réessayer</Button>` (le onClick appelle une prop `onRetry?`). Si `sources != null && sources.length > 0` → `<p className="text-xs text-text-secondary mt-2">Sources : {filenames séparés par ` · `, max 5 + `… et N autres`}</p>`.
  - **Fix gap P4** : ajouter `motion-reduce:animate-none` aux 3 `<span>` du `TypingIndicator` (cf. `docs/designs/s11b-frontend-chat.md` § Design system gaps, ligne « Pas de `motion-reduce:animate-none` »).
  - Mettre à jour le commentaire en tête : « SKELETON retiré (s11b), composant branché sur le store via les props `error` / `sources` / `streamingStatus`. ».
  - **Test rouge attendu** : `pnpm run typecheck` échoue si la page n'envoie pas les nouvelles props.
  - **Test vert** : le composant compile, et le rendu conditionnel est vérifié visuellement via le mockup HTML (cf. design § Mockup).

### Phase 4 — Page `/chat` + i18n + Header fixes + Lighthouse

- [x] **T4.1** — Remplir le namespace `chat` dans `frontend/messages/fr.json` ET `frontend/messages/en.json` (~16 clés, cf. `docs/designs/s11b-frontend-chat.md` § i18n) : `title`, `subjectLabel`, `subjectMaths`, `subjectFrancais`, `questionLabel`, `questionPlaceholder`, `send`, `sourcesLabel`, `sourcesMore`, `emptyState`, `pseudoMissing`, `retry`, `charCountRemaining`, `emptyExamplesTitle`, `exampleMaths`, `exampleFrancais`. Remplir `errors` : `network`, `lost`, `cross_tenant`, `no_subject`, `invalid_pseudo`, `unknown`.
  - **Test rouge attendu** : `bash frontend/scripts/check-i18n.sh` exit ≠ 0 (le `useTranslations('chat')` dans la page ne trouve pas les clés).
  - **Test vert** : `bash frontend/scripts/check-i18n.sh` exit 0.

- [x] **T4.2** — Créer `frontend/app/(public)/[locale]/chat/page.tsx` :
  - `'use client'` (la page consomme le store Zustand + `useAuthStore` + `useTranslations`).
  - Layout : `flex flex-col gap-4 px-4 py-4 max-w-3xl mx-auto` (responsive : à 768px, `px-6 py-6`).
  - Sections (cf. design § Layout, 1-9) : `<Header>` (réutilisé de s11a) → titre `<h1>{t('title')}</h1>` → `<Select>` matière (44 px) → `<Textarea>` question (min-h-24, maxLength 2000, `aria-describedby` vers compteur) → compteur (`{2000 - question.length} {t('charCountRemaining')}`, `text-xs text-text-tertiary`, `aria-live="polite"` `srOnly` quand <100 chars restants) → `<Button variant="primary" leftIcon={<SendIcon size={20} />}>Envoyer</Button>` (44 px, désactivé si `!pseudo || !subject || !question.trim() || isStreaming`) → `<StreamingMessage>` (étendu) → ligne Sources (rendue par `<StreamingMessage>` si sources) → label warning « Choisis un pseudo pour commencer » si `!isValidPseudo(pseudo)`.
  - Hooks : `const t = useTranslations('chat')`, `const tErrors = useTranslations('errors')`, `const { pseudo, hydrated } = useAuthStore()`, `const { messages, isStreaming, send, retry } = useChatStore()`.
  - State local : `subject: 'maths' | 'francais' | ''`, `question: string`.
  - `aria-invalid={!isValidPseudo(pseudo)}` sur l'input pseudo du `<Header>` (prop à ajouter ou condition dans le composant — choix d'implémentation laissé à l'agent, mais le résultat visible doit être `aria-invalid="true"` quand le pseudo est vide). **Note** : le `<Header>` est partagé ; on ne le modifie pas pour s11b (T4.3 ajoute juste le `tabindex="-1"` sur `/upload`). Le rendu `aria-invalid` est interne au `<Header>` via l'usage de `isValidPseudo(pseudo)`.
  - **Test rouge attendu** : la page n'existe pas → `pnpm run build` échoue sur la résolution de route.
  - **Test vert** : `pnpm run build` passe. `pnpm exec playwright test home` reste vert (pas de régression).

- [x] **T4.3** — Modifier `frontend/components/Header.tsx` (cf. P7 recherche, retour s11a Minor #1) :
  - **Débloquer** le lien `/chat` : retirer `aria-disabled="true"` (l.81).
  - **Activer** l'aria-current : ajouter `aria-current={isActive ? 'page' : undefined}` quand le pathname courant est `/chat` (utiliser `usePathname()` de `next/navigation`).
  - **Ajouter** `tabindex="-1"` au lien `/upload` (l.86) — c'est un trou de s11a (P0, design-system l.230 l'exige).
  - **Test rouge attendu** : le test e2e (a) de s11b (T5.1) vérifie que le lien `/chat` est cliquable et mène à `/fr/chat`.
  - **Test vert** : `pnpm exec playwright test home` reste vert ; le nouveau `chat.spec.ts` (a) passe.

- [x] **T4.4** — Étendre `frontend/lighthouserc.json` (cf. AC10) :
  - Ajouter `"http://localhost:3000/fr/chat"` au tableau `url` (l.8).
  - **Test rouge attendu** : si on retire l'URL, la CI Lighthouse échoue (mais on l'ajoute, donc le test rouge est ailleurs — vérifié au T5.4 que le build produit la page).
  - **Test vert** : `pnpm exec lhci collect --config=frontend/lighthouserc.json` (ou équivalent) score accessibility ≥ 0.9 sur `/fr/chat`.

### Phase 5 — Tests e2e Playwright + verifications

- [x] **T5.1** — Créer `frontend/e2e/chat.spec.ts` avec 5+ tests :
  - (a) **`renders with all controls and htmlFor`** : `page.goto('/fr/chat')`, vérifie `<h1>` « Chatter avec un agent », `getByLabel('Matière')` est un `<select>`, `getByLabel('Ta question')` est un `<textarea>`, `getByRole('button', { name: 'Envoyer' })` est visible et `aria-disabled="true"` (rien saisi). Suit le pattern de `home.spec.ts:41-52`.
  - (b) **`streams a stubbed SSE token by token`** : `page.route('**/api/chat/stream', async (route) => { await route.fulfill({ status: 200, headers: { 'Content-Type': 'text/event-stream' }, body: 'data: {"token":"Une "}\n\ndata: {"token":"dérivée."}\n\ndata: {"done":true,"sources":[{"filename":"cours.pdf","chunk_index":0}]}\n\n' }) })`. Saisir matière + question, cliquer Envoyer, attendre que la zone contienne « Une dérivée. », vérifier la ligne « Sources : cours.pdf ». Suivre le pattern de `responsive.spec.ts` (page.route + `waitFor`).
  - (c) **`displays inline error card on stream error event`** : stub `data: {"error":"oops","code":"unknown"}\n\n`. Vérifier que la card d'erreur contient « Une erreur est survenue. » ET un bouton « Réessayer ». Cliquer Réessayer → la même requête repart (vérifier via `page.route` spy).
  - (d) **`keyboard navigation reaches textarea, select, send button`** : `page.goto('/fr/chat')`, Tab successifs depuis le body, vérifier que le focus atteint successivement le sélecteur, la textarea, le bouton Envoyer (utiliser `page.keyboard.press('Tab')` + `expect(page.locator(':focus')).toMatch(...)`).
  - (e) **`toggle FR/EN switches chat UI to English`** : `page.goto('/fr/chat')`, cliquer « Passer en Anglais » (suit `home.spec.ts:30-39`), vérifier que `<h1>` devient « Chat with an agent », que le placeholder textarea devient « Ask a question about your course… », que le bouton devient « Send ». Suivre le pattern de `home.spec.ts:30-39` (pas de reload).
  - **(+) `axe-core: no critical/serious violations on /fr/chat AND /en/chat`** (cf. AC10) : 2 tests qui scannent `/fr/chat` et `/en/chat` avec `AxeBuilder.withTags(['wcag2a','wcag2aa'])`, filtrent `impact === 'critical' || impact === 'serious'`, et `expect(...).toEqual([])`. Pattern de `home.spec.ts:54-66`.
  - **Test rouge attendu** : la spec n'existe pas → `pnpm exec playwright test chat` → 0 tests trouvés.
  - **Test vert** : `pnpm exec playwright test chat` passe les 5+ tests. Le test `home.spec.ts` reste vert (pas de régression sur la nav).

- [x] **T5.2** — Gap assumé (cf. D4) : le test (c) couvre la branche `{error, code:'unknown'}`. Le mock ReadableStream aborté est trop complexe pour l'AC11. À noter en review pour suivi s22.
  - **Test (optionnel)** : le mieux qu'on puisse faire sans réseau réel.

- [x] **T5.3** — Vérifier `bash frontend/scripts/check-i18n.sh` exit 0 :
  - Le script vérifie qu'aucune string UI n'est en dur dans les fichiers `.tsx` et `.ts` du frontend (hors tests et fixtures).
  - **Test vert** : `bash frontend/scripts/check-i18n.sh && echo OK`.

- [x] **T5.4** — Run complet des vérifications :
  - `pnpm run lint` (exit 0).
  - `pnpm run typecheck` (exit 0).
  - `pnpm run build` (exit 0).
  - `pnpm exec playwright test` (tous les tests s11a + s11b verts, soit 11 + ≥ 5 = ≥ 16).
  - **Test vert global** : story shippable.

### Phase 6 — Commit final

- [x] **T6.1** — Un seul commit `feat(frontend): add /chat page with SSE streaming (s11b)`. Corps structuré : AC cochées, captures (mockup HTML + screenshots Lighthouse), review verdict à venir. Suit la convention `AGENTS.md` § Git et PR.

## Run interdicts

- **NE PAS utiliser `EventSource`** pour consommer le SSE (ADR 006, P1 recherche). Toujours `fetch().body.getReader()`.
- **NE PAS utiliser `apiClient` axios** pour le stream (buffering). Garder pour les endpoints non-streaming (s11c upload).
- **NE PAS modifier le contrat backend** (`backend/app/api/chat/router.py`, `sse.py`, `schemas.py`). Le frontend consomme, le backend est figé.
- **NE PAS hardcoder de strings UI** : tout via `useTranslations('chat')` ou `useTranslations('errors')`. `check-i18n.sh` exit 0 est un gate.
- **NE PAS ajouter de bouton « Stop »** : hors-scope (cf. design § Design system gaps, ligne « Pas de bouton Stop »). Suivi s22.
- **NE PAS persister l'historique** côté backend ou frontend (Zustand `persist` middleware interdit ici). Cumul en mémoire, perdu au refresh. Persistance = s19.
- **NE PAS toucher au design system** au-delà des 2 fix scopés : (a) `motion-reduce:animate-none` sur le typing indicator (T3.2), (b) ajout du composant `<Textarea>` (T1.1-T1.2). Toute autre modif = ADR séparé.
- **NE PAS étendre Lighthouse à `/en/chat`** : le `<html lang>` dynamique est un gap s22 (cf. D5). Audit `/en/chat` chuterait.
- **NE PAS utiliser un test qui dépend d'un LLM réel** : les tests e2e stubbent via `page.route`, l'AC11 ne fait pas d'appel réel.

## The point everything turns on

Le plan repose sur **une** décision : **`chatStore.send` consomme le SSE via `fetch().body.getReader()`** (et non `EventSource` ni `apiClient` axios). Les 3 places où ce pari peut être faux :

1. **Si le backend émet un `Content-Type` autre que `text/event-stream`** en cas d'erreur 4xx/5xx avant le stream (par ex. JSON 422 Pydantic). Vérification : `backend/app/api/chat/router.py:64-134` lève l'erreur **après** ouverture du stream (le stream est toujours `text/event-stream`, le 422 ne sort pas du endpoint). Donc `response.ok` est la seule sentinelle, et le parsing SSE n'est jamais invoqué sur un body JSON. Si l'agent a un bug et que le 422 fuit, le `parseSSEChunk` retournera `[]` (try/catch) et le store ne progressera pas → `isStreaming` reste `true` indéfiniment. **Mitigation** : T3.1 étape 6 vérifie `response.ok` AVANT d'invoquer `getReader()`. Couvert.

2. **Si le `page.route` Playwright ne sait pas stubber un `text/event-stream` proprement**. Vérification : la doc Playwright autorise `route.fulfill({ headers: { 'Content-Type': 'text/event-stream' }, body: 'data: ...' })` (cf. P12 recherche). Le test (b) T5.1 utilise exactement ce pattern.

3. **Si l'extension de `<StreamingMessage>` casse la rétrocompat avec le squelette de s11a**. Vérification : s11a n'utilise `<StreamingMessage>` dans aucune page (vérifié par grep `StreamingMessage` dans `frontend/app/` → 0 résultat autre que la home qui ne l'utilise pas non plus). Seule la home pourrait l'utiliser, mais elle ne le fait pas. Donc l'extension est safe. Si l'agent trouve un caller caché, il remonte en review comme blocker.

## Files touched

**Nouveaux (4)** :
- `frontend/components/Textarea.tsx` (T1.2) — composant partagé.
- `frontend/components/Textarea.test.tsx` (T1.1) — test unitaire.
- `frontend/lib/api/chat.ts` (T2.2) — helper pur parsing SSE + types.
- `frontend/lib/api/chat.test.ts` (T2.1) — test unitaire.
- `frontend/lib/stores/chatStore.ts` (T3.1) — store Zustand.
- `frontend/app/(public)/[locale]/chat/page.tsx` (T4.2) — page `/chat`.
- `frontend/e2e/chat.spec.ts` (T5.1) — ≥ 5 tests e2e.
- `docs/plans/s11b-frontend-chat.md` (ce fichier).

**Modifiés (4)** :
- `frontend/components/StreamingMessage.tsx` (T3.2) — ajout props `error` / `sources` / `streamingStatus`, fix `motion-reduce:animate-none`.
- `frontend/components/Header.tsx` (T4.3) — débloque `/chat`, ajoute `tabindex="-1"` à `/upload`, `aria-current`.
- `frontend/messages/fr.json` (T4.1) — namespace `chat` + `errors` remplis (~22 clés).
- `frontend/messages/en.json` (T4.1) — idem en anglais.
- `frontend/lighthouserc.json` (T4.4) — ajout URL `/fr/chat`.

**Non touchés (à vérifier en review)** :
- `frontend/lib/api.ts` — pas de modif. Le commentaire l.7-8 reste vrai (« chat and upload flows import this client… »). Le store `chatStore` **n'importe pas** `apiClient`, conformément à P1.
- `backend/**` — out of scope strict.
- `frontend/lib/stores/authStore.ts` — lu par `chatStore.send`, pas modifié.
- `frontend/middleware.ts` + `frontend/i18n/routing.ts` — la locale `/fr/chat` est déjà couverte par le routing next-intl de s11a.

## Test strategy

| Niveau | Quoi | Où | Combien |
|---|---|---|---|
| **Unitaire** | `<Textarea>` (forwardRef, classes, aria-invalid, maxLength) | `Textarea.test.tsx` | 5 assertions |
| **Unitaire** | `parseSSEChunk` (3 formes, no-op, multi-event, vide) | `chat.test.ts` | 7 cas |
| **E2E** | Rendu + htmlFor + désactivation bouton | `chat.spec.ts` (a) | 1 test |
| **E2E** | Stream SSE stubbé token-par-token + sources | `chat.spec.ts` (b) | 1 test |
| **E2E** | Erreur code-mappée + bouton Réessayer | `chat.spec.ts` (c) | 1 test |
| **E2E** | Navigation clavier | `chat.spec.ts` (d) | 1 test |
| **E2E** | Toggle FR/EN bascule toute l'UI | `chat.spec.ts` (e) | 1 test |
| **E2E** | Axe-core `/fr/chat` + `/en/chat` | `chat.spec.ts` (a11y) | 2 tests |
| **CI** | Lint, typecheck, build | `pnpm run` | 1 run global |
| **CI** | Lighthouse a11y ≥ 0.9 sur `/fr/chat` | `lighthouserc.json` | 1 audit |
| **CI** | check-i18n.sh exit 0 | `frontend/scripts/check-i18n.sh` | 1 run |
| **CI** | Tous les tests Playwright (s11a + s11b) | `playwright test` | ≥ 16 tests |

**Total automatisé** : ≥ 5 e2e + 2 a11y + 12 unitaires ≈ 19 tests automatisés. **Couvre** tous les AC sauf AC2 (état désactivé) qui est validé visuellement via le mockup HTML + l'axe-core (focus visible + tab order).

**Vérification visuelle séparée** : ouvrir `docs/designs/s11b-frontend-chat.html` dans un browser pour comparer au rendu réel de `/fr/chat` à 360px et 768px (mockup = référence low-fidelity, pas pixel-perfect).

## Definition of Done

- Une PR unique, description structurée (AC cochées, captures Lighthouse ≥ 0.9 sur `/fr/chat`, mockup HTML en annexe), diff lisible.
- Tests passants : `pnpm run lint && pnpm run typecheck && pnpm run build && pnpm exec playwright test` exit 0.
- Pas de régression : les 11 tests s11a restent verts (`home.spec.ts`, `pseudo.spec.ts`, `responsive.spec.ts`).
- **Multi-tenancy** : non applicable côté frontend (le pseudo est lu côté cookie, l'isolation cross-tenant est côté backend, testée en s09).
- **Observabilité** : pas de nouvelle métrique frontend en s11b (l'observabilité arrive en s22). Les erreurs SSE sont catchées dans le store (log console en dev).
- **i18n** : `bash frontend/scripts/check-i18n.sh` exit 0, tous les libellés via `useTranslations`.
- **Accessibilité** : axe-core 0 violation critical/serious sur `/fr/chat` ET `/en/chat` (2 tests dédiés), Lighthouse Accessibility ≥ 90 sur `/fr/chat`, `prefers-reduced-motion` honoré sur le typing indicator.
- **Documentation** : commentaire en tête de `chatStore.ts` référençant le contrat backend (AC13).
- Review passée : `docs/reviews/s11b-frontend-chat.md` termine par `Max severity: <…>` et `Ship allowed: yes`.
