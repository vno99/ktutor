---
validated: yes
---

# Plan — Story s11-frontend-upload-chat (split en s11a / s11b / s11c)

Branch: `feature/s11-frontend-upload-chat`
Research: `docs/research/s11-frontend-upload-chat.md` — read it first; this plan does not repeat it.
Design: `docs/designs/s11-frontend-upload-chat.md` (mockup : `docs/designs/s11-frontend-upload-chat.html`)

> **Note orchestrateur (split en 3 sous-stories)** : la recherche a remonté un score de complexité **5** (vs 4 dans `docs/stories.md`). Décision utilisateur : **splitter en 3 sous-stories** (`s11a-frontend-bootstrap`, `s11b-frontend-chat`, `s11c-frontend-upload`). Ce plan couvre **uniquement s11a** (le bootstrap). s11b et s11c seront planifiés séparément après le merge de s11a, sur des branches `feature/s11b-frontend-chat` et `feature/s11c-frontend-upload` (worktrees dédiés). La PR de s11a inclut la **renumérotation** de s11 en s11a dans `docs/stories.md` (T0.1).

## Target story

> **s11-frontend-upload-chat** (re-numérotée **s11a-frontend-bootstrap** après merge de cette PR)
>
> As an élève, I want utiliser une interface web responsive (smartphone + tablette) so that je puisse uploader et chatter sans installer quoi que ce soit.
>
> **Complexity (story)** : 4 — **Re-scored complexity** : **5** (research § 16). **Split validé** : ce plan ne couvre que la sous-story **s11a-frontend-bootstrap**, complexity **3** (scaffold + design system + i18n + CI).
>
> **AC couverts par s11a** (extrait de `docs/stories.md:418-427`, scope réduit) :
> 1. **AC scaffold** : `pnpm install && pnpm dev` démarre le serveur sur `http://localhost:3000` et sert une home page.
> 2. **AC i18n** : le toggle FR/EN dans le header change la langue et persiste en cookie.
> 3. **AC responsive** : la home et le header sont utilisables à 360px (mobile) et 768px (tablette), sans scroll horizontal.
> 4. **AC composants DS** : les 8 composants cibles (Button, Input, Label, Card, Select, FileUpload, StreamingMessage, LanguageSwitcher) sont implémentés en squelette (signature + a11y), même s'ils ne sont pas tous utilisés en s11a.
> 5. **AC CI** : le job `frontend` du CI GitHub Actions passe (lint, typecheck, build), et un test e2e Playwright smoke (la home rend) + axe-core (0 violation critique) sont verts.
> 6. **AC a11y** : Lighthouse Accessibility ≥ 90 sur la home (run Lighthouse CI dans le job CI).
> 7. **AC zéro régression backend** : `pytest` passe toujours (412 tests, `pytest --cov-fail-under=80`).
> 8. **AC tests Playwright e2e placeholder** : un test `home.spec.ts` est créé, stubbé via `page.route` si besoin. Les e2e chat/upload (AC6 et AC7 du story original) sont **hors-scope** s11a, ils arrivent en s11b et s11c.
>
> **ACs reportés à s11b/s11c** : AC1 (page `/upload`), AC2 (page `/chat`), AC4 (SSE consumption), AC6 (e2e upload), AC7 (e2e chat avec SSE).

### Décisions héritées de la recherche (`docs/research/s11-frontend-upload-chat.md`)

| Q / D | Décision | Justification |
|---|---|---|
| Q1 (package manager) | **pnpm** | Tranché utilisateur. Plus rapide en CI que npm, standard Next.js 16. |
| Q2 (shadcn/ui) | **Composants maison** | Pas de shadcn/ui en s11a. Composants signature (Button, Input, etc.) implémentés from scratch. Décision reportée à s22 si le besoin s'en fait sentir. |
| Q3 (nom du groupe de routes) | **`(public)/[locale]/`** | Convention Next.js la plus lisible. `(auth-less)` du story est indicatif. |
| Q5 (CI frontend) | **Étendre le job `frontend` existant** | Le job existe déjà (`.github/workflows/ci.yml:207-271`), en `continue-on-error: true` pour lint/typecheck. s11a le durcit (suppression du `continue-on-error`) et ajoute Playwright + axe-core + Lighthouse CI. |
| D1 (étendue du scaffold) | **Split 3 stories** | Tranché utilisateur. s11a = bootstrap seul. |
| D2 (routes) | **`(public)/[locale]/`** | cf. Q3. |
| D3 (SSE stratégie) | **N/A en s11a** | Le SSE arrive en s11b. La décision (fetch direct vs route proxy) sera tranchée en s11b. |
| D4 (axe-core + Lighthouse CI) | **Les deux** | Tranché utilisateur. axe-core dans Playwright e2e, Lighthouse CI dans un job dédié. |
| D5 (persistance du pseudo) | **Cookie `pseudo`** | s11a pose le cookie via un `<Input>` dans le header. L'auth réelle (JWT) arrive en s12-s15. |
| D6 (mode d'erreur SSE) | **N/A en s11a** | SSE arrive en s11b. |

### Dépendances

- **s09 (chat API)** mergé ✅ (vérifié : `ff21046` contient le squash s09).
- **s10 (upload API)** mergé ✅ (vérifié : `ff21046` contient le squash s10).
- **Pas de nouvelle dépendance backend**. s11a est strictement frontend + CI.

### Travail transverse obligatoire avant T1

- **T0.1** — Renuméroter s11 en s11a dans `docs/stories.md` (T0.1.a : ajouter un en-tête de split + modifier la ligne 410 du fichier pour s11a-frontend-bootstrap, T0.1.b : ajouter les entrées s11b et s11c avec leur complexité estimée). Cette action est **atomique** dans la PR s11a, c'est la première chose mergée.
- **T0.2** — Vérifier que le CI job `frontend` (lignes 207-271) déclenche bien sur la création de `frontend/package.json`. Vérifié par la lecture de `.github/workflows/ci.yml:218-231` : oui, le job détecte `frontend/package.json` et tourne. Le job utilise `npm` (ligne 244) : **incompatibilité avec pnpm** (T0.3).
- **T0.3** — Modifier le job `frontend` pour utiliser **pnpm** : `actions/setup-node@v5` avec `cache: pnpm` + `cache-dependency-path: frontend/pnpm-lock.yaml`, puis `pnpm install --frozen-lockfile` au lieu de `npm ci`. Ce changement est **inclus dans la PR s11a** (T0.3 fait partie de T5 — CI).
- **T0.4** — Confirmer que `next@16.0.0`, `react@19.0.0`, `tailwindcss@4.0.0` sont les versions cibles. Pin exact dans `package.json`. Pas de `^` sur les versions majeures.

## Tasks (ordered)

> Ordre TDD strict : test rouge → code minimal → test vert. **Commit unique en fin de story** (AGENTS.md). Toutes les tâches produisent un livrable observable (un fichier, un test, un build artifact).

### Phase 0 — Pré-tâches (renommage + vérifications)

- [x] **T0.1** — Renuméroter s11 en s11a dans `docs/stories.md` :
  - T0.1.a : modifier la ligne 410 (titre `### Story s11-frontend-upload-chat`) en `### Story s11a-frontend-bootstrap — Bootstrap de l'application frontend` (sous-story 1 du split).
  - T0.1.b : ajouter deux nouvelles entrées juste en-dessous : `### Story s11b-frontend-chat — Page /chat avec streaming SSE` (complexity 3, dépend de s11a) et `### Story s11c-frontend-upload — Page /upload avec drag & drop` (complexity 2, dépend de s11a). Le contenu de chaque sous-story sera détaillé dans une PR future (s11b, s11c).
  - T0.1.c : ajouter un en-tête de split en haut de `docs/stories.md` section « Phase 2 » : « Note : s11 a été split en 3 sous-stories (s11a bootstrap, s11b chat, s11c upload) suite à la recherche `docs/research/s11-frontend-upload-chat.md` § 16. »
  - T0.1.d : adapter l'AC list (lignes 418-427) au scope réduit de s11a (cf. section « AC couverts par s11a » ci-dessus). Les 5 ACs non couverts sont déplacés dans les futures sous-stories.
  - **Test** : `git diff docs/stories.md` montre le renommage. Pas de test pytest.

- [x] **T0.2** — Vérifier l'environnement : `node --version` ≥ 20.0.0, `pnpm --version` ≥ 9.0.0 (sinon installer via `npm install -g pnpm`). Le CI utilise Node 20, donc on s'aligne.
  - **Test** : `pnpm --version` retourne `9.x.x` ou plus. Pas de test automatisé (commande shell).

- [x] **T0.3** — Préparer le repo pour le scaffold (`.gitignore` racine) : ajouter `frontend/node_modules/`, `frontend/.next/`, `frontend/coverage/`, `frontend/playwright-report/`, `frontend/test-results/`, `frontend/lighthouseci/`, `frontend/.env*.local`, `frontend/pnpm-debug.log*` à `.gitignore` (s'ils n'y sont pas déjà). Vérifier aussi qu'il existe une racine `.gitignore` (sinon, créer).
  - **Test** : `git check-ignore frontend/node_modules/foo` retourne 0.

- [x] **T0.4** — Vérifier que `next@16.0.0` est la dernière stable au moment de l'exécution. Si une 16.x plus récente existe, on prend la dernière. Documenter la version dans le commit.
  - **Test** : `pnpm view next@latest version` retourne `16.x.x`.

### Phase 1 — Scaffold Next.js 16 (config + dépendances)

> TDD : on commence par un **test smoke** : « la commande `pnpm build` produit un artifact `.next/` ». Ce test est implémenté comme un script shell vérifié par le CI, pas un test pytest.

- [x] **T1.1** — Créer `frontend/package.json` minimal : `name: "ktutor-frontend"`, `version: "0.1.0"`, `private: true`, `type: "module"`, `engines: { node: ">=20.0.0", pnpm: ">=9.0.0" }`, `packageManager: "pnpm@9.x.x"`, `scripts: { dev: "next dev", build: "next build", start: "next start", lint: "next lint", typecheck: "tsc --noEmit", test:e2e: "playwright test", test: "pnpm run typecheck && pnpm run lint && pnpm run test:e2e" }`. Pas encore de dépendances.
  - **Test rouge attendu** : `pnpm install` échoue car `next`, `react`, etc. ne sont pas déclarés. Ce test est capturé par le CI job `frontend` qui tente `pnpm install` et échoue.

- [x] **T1.2** — Ajouter les dépendances de production (versions pinnées) : `next@16.0.0`, `react@19.0.0`, `react-dom@19.0.0`, `next-intl@4.x.x` (vérifier la dernière stable), `zustand@5.x.x`, `axios@1.x.x`. Dépendances dev : `typescript@5.x.x`, `@types/node@20.x.x`, `@types/react@19.x.x`, `@types/react-dom@19.x.x`, `tailwindcss@4.x.x`, `postcss@8.x.x`, `autoprefixer@10.x.x`, `@playwright/test@1.x.x`, `@axe-core/playwright@4.x.x`, `eslint@9.x.x`, `eslint-config-next@16.0.0`, `@lhci/cli@0.14.x` (Lighthouse CI).
  - **Test rouge attendu** : `pnpm install` échoue si le lockfile n'est pas généré.

- [x] **T1.3** — Générer le lockfile : `pnpm install` à la racine de `frontend/`. Cela crée `pnpm-lock.yaml`. Commit le lockfile.
  - **Test** : `pnpm install --frozen-lockfile` réussit (le lockfile est cohérent). `test:install` est implicite dans le CI.

- [x] **T1.4** — Créer `frontend/tsconfig.json` avec `strict: true`, `target: "ES2022"`, `lib: ["dom", "dom.iterable", "esnext"]`, `module: "esnext"`, `moduleResolution: "bundler"`, `jsx: "preserve"`, `allowJs: false`, `skipLibCheck: true`, `noEmit: true`, `esModuleInterop: true`, `resolveJsonModule: true`, `isolatedModules: true`, `incremental: true`, `paths: { "@/*": ["./*"] }`, `plugins: [{ name: "next" }]`.
  - **Test rouge attendu** : `pnpm run typecheck` échoue car il n'y a pas encore de code TypeScript à compiler (ou échoue sur l'absence de fichiers `.ts`).

- [x] **T1.5** — Créer `frontend/next.config.ts` minimal : `reactStrictMode: true`, `output: "standalone"` (utile pour la prod même si pas Docker en POC), `experimental: { typedRoutes: true }` (cohérent avec TS strict), `transpilePackages: []` (vide en s11a). **Note** : `transpilePackages` n'est PAS nécessaire pour `next-intl` ou `zustand` (ils sont déjà ESM-compatible).
  - **Test** : `pnpm run build` échoue car `app/` n'existe pas.

- [x] **T1.6** — Créer `frontend/tailwind.config.ts` qui consomme les tokens du design system (`docs/design-system.md`) : `theme.extend.colors` avec les 14 tokens (`primary`, `primary-strong`, `canvas`, `surface`, `surface-subtle`, `border`, `text-primary`, `text-secondary`, `text-tertiary`, `accent-warm`, `success`, `warning`, `error`, `info`) mappant vers `var(--color-*)`. `theme.extend.fontFamily` avec `sans: ['Inter', 'system-ui', 'sans-serif']` et `mono: ['JetBrains Mono', 'monospace']`. `theme.extend.borderRadius` avec `xs: '4px'`, `sm: '6px'`, `md: '8px'`, `lg: '12px'`, `xl: '16px'`. `content: ['./app/**/*.{ts,tsx}', './components/**/*.{ts,tsx}']`.
  - **Test** : `pnpm run build` échoue toujours (pas de `app/`).

- [x] **T1.7** — Créer `frontend/postcss.config.mjs` : `plugins: { tailwindcss: {}, autoprefixer: {} }`. Format ESM (`.mjs`) car `package.json` est `type: "module"`.
  - **Test** : `pnpm run build` échoue toujours.

- [x] **T1.8** — Créer `frontend/.eslintrc.json` : `{ "extends": "next/core-web-vitals" }`. La règle custom « no hardcoded strings » mentionnée dans le design-system § i18n n'est pas une règle ESLint standard — elle est vérifiée par un script shell (T2.8), pas par ESLint.
  - **Test** : `pnpm run lint` échoue car il n'y a pas de code à linter (ou passe à vide).

- [x] **T1.9** — Créer `frontend/.prettierrc` : `{ "semi": false, "singleQuote": true, "trailingComma": "all", "printWidth": 100 }` (aligné sur le style backend Python).
  - **Test** : aucun test automatisé (Prettier est utilisé manuellement et en CI plus tard si décidé).

- [x] **T1.10** — Créer `frontend/app/globals.css` avec les 14 CSS variables (`:root` pour light, `[data-theme="dark"]` pour dark) selon `docs/design-system.md` § Conventions d'implémentation. Inclure `@tailwind base; @tailwind components; @tailwind utilities;` en haut. Inclure la règle `prefers-reduced-motion` pour les animations (`@media (prefers-reduced-motion: reduce) { *, *::before, *::after { animation-duration: 0.01ms !important; } }`).
  - **Test** : `pnpm run build` échoue toujours (pas de layout).

- [x] **T1.11** — Créer `frontend/app/layout.tsx` minimal : `<html lang="fr" data-theme="light">` (la locale sera injectée par next-intl en T2), `<body className="bg-canvas text-text-primary font-sans">`, import de `./globals.css`. Le root layout **ne fait pas** le `NextIntlClientProvider` ici — c'est le layout `(public)/[locale]/layout.tsx` qui le fera (T2.4).
  - **Test rouge attendu** : `pnpm run build` échoue (probablement sur l'absence de `page.tsx`).

- [x] **T1.12** — Créer `frontend/app/page.tsx` minimal : une page « Welcome » qui rend `<h1>Welcome</h1>` en dur (sera i18n-isée en T2.7). C'est la page d'accueil de la racine (qui sera réécrite par `(public)/[locale]/page.tsx` en T2.5, mais le scaffold a besoin d'au moins une page pour builder).
  - **Test** : `pnpm run build` doit réussir et produire `.next/standalone/`. Si oui, le test smoke passe.

- [x] **T1.13** — Vérification smoke : `pnpm run build && pnpm run typecheck && pnpm run lint` doivent tous passer. C'est le test global de la phase 1.
  - **Test** : CI job `frontend` exit 0. **Note** : le job existe mais en `continue-on-error: true` pour lint/typecheck — sera durci en T5.

### Phase 2 — Design system + i18n (composants squelette + next-intl)

> TDD : un test e2e Playwright vérifie que la home page rend en français, que le toggle FR/EN marche, que `prefers-reduced-motion` est respecté. Un test axe-core vérifie 0 violation critique.

- [x] **T2.1** — Créer `frontend/i18n/routing.ts` : définit `routing = defineRouting({ locales: ['fr', 'en'], defaultLocale: 'fr', localePrefix: 'always' })`. Export depuis `frontend/i18n/request.ts` la fonction `getRequestConfig` qui charge le bon catalogue via `import messages from '@/messages/fr.json'`.
  - **Test rouge** : la home n'a pas encore de `[locale]` segment, donc le routing next-intl ne s'applique pas encore.

- [x] **T2.2** — Créer `frontend/messages/fr.json` avec la structure `{ "common": { "language": "Langue", "french": "Français", "english": "Anglais" }, "home": { "title": "Bienvenue sur ktutor", "subtitle": "Un assistant IA pour réviser, uploader tes cours et chatter avec tes agents.", "ctaChat": "Commencer à chatter", "ctaUpload": "Uploader un document" } }`. Tous les namespaces futurs (chat, upload, errors) sont vides `{}` pour l'instant, à enrichir en s11b/s11c.
  - **Test rouge** : `pnpm run typecheck` échoue si le type des messages n'est pas déclaré (résolu en T2.3).

- [x] **T2.3** — Créer `frontend/messages/en.json` avec la traduction : `{ "common": { "language": "Language", "french": "French", "english": "English" }, "home": { "title": "Welcome to ktutor", "subtitle": "An AI assistant to help you review, upload your courses and chat with your agents.", "ctaChat": "Start chatting", "ctaUpload": "Upload a document" } }`.
  - **Test** : pas de test automatisé pour le contenu du JSON. Le test e2e (T2.6) valide que le toggle change la langue.

- [x] **T2.4** — Créer `frontend/middleware.ts` : `import createMiddleware from 'next-intl/middleware'; import { routing } from './i18n/routing'; export default createMiddleware(routing); export const config = { matcher: ['/((?!api|_next|.*\\..*).*)'] }`.
  - **Test rouge** : la home est servie sans redirection vers `/fr/`. Le test e2e (T2.6) vérifie que `GET /` redirige vers `/fr/`.

- [x] **T2.5** — Créer `frontend/app/(public)/[locale]/layout.tsx` : `<NextIntlClientProvider>` qui enveloppe `<Header />` + `<main>{children}</main>` + (sur mobile) `<BottomTabBar />`. Charge les messages via `getMessages()` et `setRequestLocale(locale)`. La locale est validée par `routing` (Pydantic-like : unknown locale → 404).
  - **Test rouge** : `pnpm run build` peut échouer si `(public)/[locale]/page.tsx` n'existe pas.

- [x] **T2.6** — Créer `frontend/app/(public)/[locale]/page.tsx` (la vraie home) : utilise `useTranslations('home')` pour le titre et sous-titre, deux `<Button>` (primary "Commencer à chatter" → `/chat`, secondary "Uploader un document" → `/upload`). Les liens `/chat` et `/upload` ne pointent vers rien pour l'instant (404 attendu en s11a, c'est reporté à s11b/s11c).
  - **Test e2e** : `frontend/e2e/home.spec.ts` qui :
    1. Visite `/` → assert redirect vers `/fr/`.
    2. Vérifie que le titre `Bienvenue sur ktutor` est visible.
    3. Vérifie que le toggle FR/EN est cliquable et change la langue.
    4. Vérifie que les 2 CTAs sont rendus.
    5. Axe-core : 0 violation critique.

- [x] **T2.7** — Supprimer `frontend/app/page.tsx` (la page temporaire de T1.12) : le `(public)/[locale]/page.tsx` prend le relais. Si le middleware redirige bien `/` → `/fr/`, plus personne n'atteindra `/` directement.
  - **Test rouge** : `pnpm run build` peut échouer si Next.js détecte l'absence d'un root `page.tsx` (le `(public)/[locale]/layout.tsx` doit le remplacer complètement).
  - **Test vert** : `pnpm run build` passe, `pnpm run dev` + `curl http://localhost:3000/` → 307 redirect vers `/fr/`.

- [x] **T2.8** — Créer le script « no hardcoded strings » : `frontend/scripts/check-i18n.sh` qui grep les composants pour des chaînes UI non i18n-isées (regex : `>[A-Z][a-zA-Zà-ÿ]{2,} [a-zA-Z]`) et exit 1 si trouvé. Ce script sera exécuté par le CI plus tard (T5.6). Pour l'instant, on le commit.
  - **Test** : `bash frontend/scripts/check-i18n.sh` exit 0 (en s11a, la home est 100% i18n-isée).

- [x] **T2.9** — Créer `frontend/components/Button.tsx` (composant signature) : props `{ variant: 'primary' | 'secondary' | 'ghost' | 'destructive', size: 'sm' | 'md' | 'lg', children: ReactNode, onClick?, type?: 'button' | 'submit' | 'reset', disabled?, 'aria-label'?, 'aria-pressed'?, asChild?: boolean }`. Classes Tailwind par variant. `focus:ring-2 focus:ring-primary/30 focus:ring-offset-2 focus:ring-offset-canvas`. Hauteur minimum 44px (touch target). Ref forwardé. Le composant est documenté en JSDoc.
  - **Test unitaire React** (via `vitest` ? — **hors-scope s11a**, on s'appuie sur le test e2e pour Button). Pas de test unitaire pour Button en s11a : le design system a un test e2e qui clique sur le bouton et vérifie la navigation (T2.6).
  - **Note** : ajouter Vitest/React Testing Library ferait grossir le scope. Décision : on accepte que les composants sont validés uniquement par les tests e2e en s11a. Un futur story (s22) pourra ajouter Vitest.

- [x] **T2.10** — Créer `frontend/components/Input.tsx` (text + file variants) : props `{ id, name?, type: 'text' | 'file', value?, onChange?, placeholder?, maxLength?, accept?, 'aria-invalid'?, 'aria-describedby'?, required? }`. Forward ref. Hauteur 44px. `aria-invalid` ajoute `border-error`. Pour le type `file`, le composant rend un `<input type="file" className="sr-only" />` + un wrapper stylé (le label externe fournit le bouton visible).
  - **Test e2e** : `frontend/e2e/components.spec.ts` qui vérifie que les inputs du header (pseudo) ont un `<label htmlFor>` correct (axe-core attrape déjà ça).

- [x] **T2.11** — Créer `frontend/components/Label.tsx` : props `{ htmlFor: string, children: ReactNode, srOnly?: boolean }`. Si `srOnly`, applique `className="sr-only"`. Sinon, `className="block text-sm font-medium text-text-primary mb-1"`.
  - **Test e2e** : axe-core vérifie que chaque input a un label (déjà couvert par T2.10).

- [x] **T2.12** — Créer `frontend/components/Card.tsx` (header / body / footer) : 3 sous-composants `Card`, `CardHeader`, `CardBody`, `CardFooter`. `bg-surface border border-border rounded-md shadow-kt-default p-4`. Sub-composants ont `className` overridable.
  - **Test e2e** : la home n'utilise pas Card en s11a. Le test e2e ne couvre pas Card. Validation par smoke visuel sur le mockup (`docs/designs/s11-frontend-upload-chat.html`).

- [x] **T2.13** — Créer `frontend/components/Select.tsx` : wraps `<select>` natif (design-system l.166). Props `{ id, name?, value, onChange, options: Array<{ value: string, label: string }>, 'aria-invalid'?, disabled? }`. Classes Tailwind de Input. Le select natif est accessible par défaut (clavier, screen reader).
  - **Test e2e** : la home n'utilise pas Select en s11a (Select sera utilisé en s11b/s11c). Validation par smoke visuel.

- [x] **T2.14** — Créer `frontend/components/FileUpload.tsx` : **squelette uniquement** (l'implémentation complète drag & drop + caméra arrive en s11c). Pour s11a, le composant rend un `<input type="file">` + un `<label>` externe stylé (drop zone). Props `{ id, accept, maxSize?, onFileSelect: (file: File) => void, 'aria-describedby'? }`. Le composant NE gère PAS le drag & drop en s11a — c'est explicitement hors-scope, marqué `// TODO s11c: drag & drop + camera capture` dans le code.
  - **Test e2e** : la home n'utilise pas FileUpload en s11a. Validation par smoke visuel.

- [x] **T2.15** — Créer `frontend/components/StreamingMessage.tsx` : **squelette uniquement** (l'implémentation SSE arrive en s11b). Le composant pour s11a rend `<div aria-live="polite" aria-busy={isStreaming}>{children}</div>` avec un typing indicator (3 dots). Pas de connexion SSE. Marqué `// TODO s11b: connect to /api/chat/stream`.
  - **Test e2e** : la home n'utilise pas StreamingMessage en s11a. Validation par smoke visuel.

- [x] **T2.16** — Créer `frontend/components/LanguageSwitcher.tsx` : pill toggle FR | EN. Lit la locale via `useLocale()` de next-intl, navigue via `useRouter().replace(pathname, { locale: nextLocale })`. Boutons `aria-pressed` pour l'état actif. Persistance via cookie automatique (next-intl).
  - **Test e2e** : `frontend/e2e/home.spec.ts` (étendu de T2.6) vérifie :
    1. Click sur « EN » → URL devient `/en/`.
    2. Recharger `/en/` → reste en anglais (cookie persisté).
    3. Le titre passe à `Welcome to ktutor`.

- [x] **T2.17** — Créer `frontend/components/Header.tsx` : sticky 56px. Logo `ktutor` (text bold primary-strong) + LanguageSwitcher + Input pseudo (cookie via `useAuthStore`, créé en T2.18) + Avatar initiales (cercle bg-primary 32px).
  - **Test e2e** : axe-core sur la home, le header doit avoir 0 violation (le toggle, l'input et l'avatar sont tous labellisés).

- [x] **T2.18** — Créer `frontend/lib/stores/authStore.ts` (Zustand) : `{ pseudo: string, setPseudo: (p: string) => void }`. Le store persiste `pseudo` dans un cookie `pseudo` (via `js-cookie` ou `cookies-next`). Hydraté côté client uniquement (Next.js 16 : pas de SSR state).
  - **Test** : un test e2e `frontend/e2e/pseudo.spec.ts` qui :
    1. Visite `/fr/`.
    2. Tape `ali` dans l'input pseudo.
    3. Recharge la page.
    4. Vérifie que l'avatar affiche `A` (initiale de `ali`).
    5. Vérifie que le cookie `pseudo=ali` est posé (`page.context().cookies()`).

- [x] **T2.19** — Créer `frontend/lib/api.ts` (axios) : `axios.create({ baseURL: process.env.NEXT_PUBLIC_API_URL })`. En s11a, **pas d'interceptor JWT** (l'auth arrive en s12-s15). En s11a, l'axios n'est utilisé par aucun composant — il est créé et testé unitairement.
  - **Test** : `frontend/scripts/check-api-url.sh` qui grep les composants pour `localhost:8000` ou `http://api.` en dur, et exit 1 si trouvé (forçage de `process.env.NEXT_PUBLIC_API_URL`). En s11a, le script exit 0.
  - **Note** : le test unitaire de l'axios est dans `frontend/lib/api.test.ts` (Vitest) — **hors-scope s11a**, on s'appuie sur les tests e2e et le smoke manuel.

- [x] **T2.20** — Créer `frontend/.env.example` : `NEXT_PUBLIC_API_URL=http://localhost:8000`. NE PAS commit un `.env.local` (le fichier est dans `.gitignore`).
  - **Test** : `git check-ignore frontend/.env.local` retourne 0.

### Phase 3 — Mockup statique (validation visuelle)

- [x] **T3.1** — Le mockup `docs/designs/s11-frontend-upload-chat.html` existe déjà (produit par `/ks-design`). **Vérification** : ouvrir le fichier dans un navigateur (hors CI), confirmer que la home mobile + tablette + les 3 états (empty, streaming, done) + l'upload (empty, fichier sélectionné, succès, erreur 413) + l'erreur SSE + la bottom tab bar s'affichent correctement. Pas d'assertion automatisée — c'est une validation humaine (l'orchestrateur ouvre le HTML dans son navigateur).
  - **Test** : pas de test automatisé. Validation humaine : l'orchestrateur ouvre le HTML et confirme la conformité au design-system. **C'est le seul moment où le mockup est revu.**

### Phase 4 — Tests Playwright e2e (axe-core inclus)

- [x] **T4.1** — Créer `frontend/playwright.config.ts` : `testDir: './e2e'`, `timeout: 30_000`, `fullyParallel: false` (s11a a 3 tests seulement, pas la peine de paralléliser), `reporter: [['list'], ['html', { open: 'never' }]]`, `use: { baseURL: 'http://localhost:3000', screenshot: 'only-on-failure', trace: 'retain-on-failure' }`. **Note** : le `webServer` de Playwright (qui démarre `next dev` automatiquement) est en `command: 'pnpm dev'` + `url: 'http://localhost:3000'` + `reuseExistingServer: !process.env.CI`. En CI, le `webServer` est démarré par le job GitHub Actions (T5).
  - **Test** : `pnpm run test:e2e -- --list` liste les 3 specs (T2.6, T2.10, T2.18). Si vide, config cassée.

- [x] **T4.2** — Écrire `frontend/e2e/home.spec.ts` (T2.6 + T2.16 étendu). 5 tests :
  1. `redirect / → /fr/`
  2. `home renders in French by default`
  3. `toggle to English works and persists`
  4. `CTAs are visible and clickable`
  5. `axe-core: 0 critical violation on home`

- [x] **T4.3** — Écrire `frontend/e2e/pseudo.spec.ts` (T2.18). 3 tests :
  1. `pseudo input sets a cookie`
  2. `pseudo persists across reload`
  3. `avatar initiales match the pseudo`

- [x] **T4.4** — Écrire `frontend/e2e/responsive.spec.ts`. 2 tests :
  1. `home at 360px has no horizontal scroll`
  2. `home at 768px uses two-column layout for CTAs`
  - **Note** : on ne teste PAS explicitement 1280px (desktop) en s11a — le design-system cible le mobile et la tablette (l.92). Le desktop est secondaire.

- [x] **T4.5** — Vérification locale : `pnpm run test:e2e` doit passer (3 specs, 10 tests). Si un test échoue, c'est un bug, on corrige.
  - **Test** : exit 0 de la commande.

- [x] **T4.6** — Vérification axe-core : chaque spec inclut `@axe-core/playwright`. Le test `axe-core: 0 critical violation` est strict (0 violation « critical » ou « serious »). Les violations « moderate » ou « minor » sont loggées mais n'échouent pas le test (à durcir en s22).
  - **Test** : T4.5 exit 0 inclut implicitement la validation axe-core.

### Phase 5 — CI GitHub Actions (durcir le job `frontend`)

- [x] **T5.1** — Modifier `.github/workflows/ci.yml` job `frontend` (lignes 207-271) :
  - Remplacer `npm ci` (ligne 244) par `pnpm install --frozen-lockfile`.
  - Changer `actions/setup-node@v5` `cache: npm` (ligne 238) en `cache: pnpm` + `cache-dependency-path: frontend/pnpm-lock.yaml`.
  - **Supprimer** `continue-on-error: true` pour lint et typecheck (lignes 250, 256). Maintenant ils sont durs.
  - **Garder** le `Build` step (ligne 261) sans `continue-on-error` (déjà le cas).
  - **Garder** `Upload build artifact` (ligne 270).
  - **Test** : le fichier YAML est valide (`yamllint` ou `actionlint` local, ou commit + push + voir le job).

- [x] **T5.2** — Ajouter une étape `Install Playwright Browsers` après `Install dependencies` : `pnpm exec playwright install --with-deps chromium`. C'est lourd (~200MB, ~30s en CI) mais nécessaire pour les e2e.
  - **Test** : step exit 0.

- [x] **T5.3** — Ajouter une étape `Build` distincte de `next build` (Next.js build) : on garde `pnpm run build` (qui fait `next build`). C'est la même chose en s11a. Plus tard (s11b/s11c) on pourra ajouter une étape `Start server` séparée pour les e2e.

- [x] **T5.4** — Ajouter une étape `Run e2e tests` : `pnpm run test:e2e`. Cette étape doit avoir le serveur démarré. Deux options :
  - **Option A (recommandée)** : utiliser le `webServer` de Playwright (déjà configuré en T4.1) qui démarre `pnpm dev` automatiquement. C'est la config la plus simple.
  - **Option B** : ajouter une étape `Start Next.js` (`pnpm run start &` après `Build`) + `Wait for server` + `Run e2e`.
  - **Décision** : **Option A**. Le `webServer` de Playwright gère le démarrage/arrêt du serveur dans le test runner. Plus simple, plus déterministe.
  - **Test** : job `frontend` exit 0 en CI.

- [x] **T5.5** — Ajouter une étape `Run Lighthouse CI` : `@lhci/cli@0.14.x` avec la commande `pnpm exec lhci autorun --config=./lighthouserc.json`. Lighthouse CI doit :
  - Démarrer un serveur (lui aussi : `pnpm start` ou `pnpm dev` après build).
  - Audit `/fr/` (et plus tard `/fr/chat`, `/fr/upload` en s11b/s11c).
  - Échouer si le score a11y < 90 (`assertions: { 'categories:accessibility': ['error', { minScore: 0.9 }] }`).
  - **Note** : Lighthouse CI ajoute ~60s au job `frontend`. Acceptable pour la première story frontend.
  - **Test** : job exit 0.

- [x] **T5.6** — Ajouter une étape `Run no-hardcoded-strings check` : `bash frontend/scripts/check-i18n.sh` (créé en T2.8). Exit 1 si une chaîne UI non i18n-isée est trouvée.
  - **Test** : job exit 0.

- [x] **T5.7** — Vérification globale : push la branche, observe le job `frontend` complet : setup Node + pnpm install + lint + typecheck + build + install Playwright + e2e + Lighthouse CI + check-i18n. Tous verts.
  - **Test** : GitHub Actions job `frontend` est vert (visible sur l'UI de la PR).

### Phase 6 — Commit final + PR

- [x] **T6.1** — Vérifier que TOUS les fichiers de s11a sont commitables : `git status` montre :
  - `docs/stories.md` (renommage s11 → s11a + ajout s11b + s11c).
  - `docs/research/s11-frontend-upload-chat.md` (recherche).
  - `docs/designs/s11-frontend-upload-chat.md` + `.html` (design).
  - `docs/plans/s11-frontend-upload-chat.md` (ce plan, une fois validé).
  - `frontend/` (scaffold complet, ~30 fichiers).
  - `.github/workflows/ci.yml` (job frontend durci + Lighthouse CI).
  - `.gitignore` (ajout des patterns frontend).
  - **PAS** de `.env.local`, `frontend/node_modules/`, `frontend/.next/`, etc.

- [x] **T6.2** — Commit unique : `feat(frontend): bootstrap Next.js 16 app (s11a-frontend-bootstrap)`. Le message référence explicitement le split et le scope réduit. Body : `Refs s11-frontend-upload-chat (split en s11a/b/c). Premier frontend : scaffold Next.js 16 + i18n + design system + CI. Les pages /chat et /upload arrivent en s11b et s11c.` (cf. AGENTS.md § Git et PR : conventional commits, scope entre parenthèses).
  - **Test** : `git log -1 --format=%s` retourne le bon message.

- [x] **T6.3** — Push la branche : `git push -u origin feature/s11-frontend-upload-chat`. Le pre-push hook (s'il existe) vérifie le conventional commit message. Sinon, push direct.

- [x] **T6.4** — Ouvrir la PR : `gh pr create --title "feat(frontend): bootstrap Next.js 16 app (s11a-frontend-bootstrap)" --body "..."`. Le body est structuré (résumé, AC cochées, points d'attention, dépendances futures).
  - **Test** : PR existe sur GitHub, le job `frontend` CI est lancé automatiquement.

## Risks and mitigations

- **R1 — Pinning exact des versions npm peut bloquer une future mise à jour mineure** : mitigation = ADR dans `docs/decisions/011-frontend-pinning.md` qui justifie le pinning strict pour la première story. Les bumps mineurs se font dans des stories dédiées (s22 par exemple).
- **R2 — Lighthouse CI ajoute 60s au job frontend** : mitigation = acceptable pour s11a (première story, on pose les fondations). Si le coût devient prohibitif, on peut le rendre non-bloquant en s22 (warning au lieu d'erreur).
- **R3 — Le split s11a/b/c multiplie les renommages** : mitigation = le renommage s11→s11a est fait UNE fois dans s11a (T0.1). Les futures stories utilisent s11b et s11c directement, pas de re-renommage.
- **R4 — Le job CI est en `continue-on-error: true` actuellement, le durcir peut faire échouer des PRs d'autres stories** : mitigation = la PR s11a est la première à introduire le frontend, donc aucun autre job ne devrait être affecté. À vérifier au moment du merge.
- **R5 — Playwright + Lighthouse CI en CI consomme du temps runner** : mitigation = le job est `ubuntu-latest` (rapide), les deux étapes peuvent tourner en série (Playwright ~30s, Lighthouse ~60s = ~90s total pour les deux). Acceptable.

## Definition of Done (s11a)

- [ ] PR unique ouverte contre `main`, titre conventionnel.
- [ ] Job `frontend` CI vert : lint, typecheck, build, e2e (3 specs, 10 tests), Lighthouse CI (a11y ≥ 90 sur `/fr/`), check-i18n.
- [ ] Job `backend` CI vert (pas de régression : 412 tests pytest passent, coverage ≥ 80%).
- [ ] Job `docs` CI vert (markdownlint ne casse pas sur `docs/stories.md` renommé).
- [ ] Job `pr-lint` CI vert (conventional commit).
- [ ] Axe-core : 0 violation critique ou serious sur la home (mobile + tablette).
- [ ] Pas de string en dur dans les composants (vérifié par `scripts/check-i18n.sh`).
- [ ] Pas de `localhost:8000` ou URL en dur dans le code (vérifié par `scripts/check-api-url.sh`).
- [ ] `docs/stories.md` mis à jour avec le split (s11a/b/c).
- [ ] Mockup statique `docs/designs/s11-frontend-upload-chat.html` est visuellement conforme au design system (validation humaine par l'orchestrateur).
- [ ] Review passée (`docs/reviews/s11-frontend-upload-chat.md` avec `Ship allowed: yes`).

## Future stories (gated by s11a)

- **s11b-frontend-chat** — Page `/chat` + SSE consumer via `fetch` + `ReadableStream` + `chatStore` Zustand. Accepte : les 5 ACs `chat` du story original. Sur la branche `feature/s11b-frontend-chat`, après merge de s11a. **Complexity estimée : 3**.
- **s11c-frontend-upload** — Page `/upload` + `<FileUpload>` complet (drag & drop + caméra mobile) + axios upload. Accepte : les 3 ACs `upload` du story original. Sur la branche `feature/s11c-frontend-upload`, après merge de s11a. **Complexity estimée : 2**.

## Liens

- `docs/stories.md:409-447` — story source.
- `docs/research/s11-frontend-upload-chat.md` — recherche complète.
- `docs/designs/s11-frontend-upload-chat.md` + `.html` — design.
- `docs/architecture.md` § Frontend — stack imposée.
- `docs/design-system.md` — tokens et composants.
- `docs/decisions/006-frontend-nextjs-app-router.md` — verrouille Next.js + i18n + a11y.
- `.github/workflows/ci.yml:207-271` — job `frontend` à durcir en T5.
- AGENTS.md — règles pipeline, conventional commits, squash-merge.
