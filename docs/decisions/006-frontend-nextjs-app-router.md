# ADR 006 — Frontend Next.js 16 App Router + i18n + a11y dès le départ

- Status: accepted
- Date: 2026-08-28
- Scope: framing

## Context

Le PRD exige un frontend responsive (smartphone ≥ 360px, tablette ≥ 768px), accessible (WCAG 2.1 A minimum), i18n français par défaut + anglais, et un chatbot qui streame les réponses LLM. Le POC n'a pas de frontend (CLI uniquement).

Plusieurs choix s'offrent :

- Next.js 16 App Router (le PRD l'impose, mais l'App Router vs Pages Router reste à choisir)
- Vite + React (plus léger, mais perd le SSR, l'i18n intégré, le routing)
- SvelteKit / Remix (alternatives)

## Decision

- **Next.js 16 App Router** (comme imposé par le PRD).
- **Structure de routes par groupe** : `app/(auth)/` pour login/register, `app/(dashboard)/` pour les pages protégées (admin, parent, eleve).
- **State management** : Zustand (léger, peu de boilerplate, suffisant pour le POC). Pas de Redux.
- **i18n** : `next-intl` dès le départ (s11 amorce le scaffold, s21 consolide). Toute string UI passe par les catalogues `frontend/messages/fr.json` et `en.json`. Pas de hardcoded strings.
- **SSE consumption** : `fetch` + `ReadableStream` (l'API `EventSource` du navigateur ne supporte pas POST). Documentation dans s11.
- **Styling** : Tailwind CSS, classes utilitaires. Pas de CSS-in-JS, pas de CSS modules custom.
- **Charts** : Recharts pour les dashboards (s16). Pas de SVG custom from scratch.
- **Accessibilité** : dès la première story frontend (s11), `<label>` associés, focus visible, contraste AA. Lighthouse a11y ≥ 90 imposé par story (s11, s22).

## Considered options

- **Pages Router** (l'ancien) — rejeté. L'App Router est la voie officielle Next.js 16. RSC (React Server Components) réduit le JS envoyé au client. Pas de raison de revenir en arrière.

- **Vite + React + React Router** — rejeté. Le PRD mandate Next.js. Vite est plus rapide en dev, mais on perd le routing fichier, l'i18n middleware natif, le SSR, et l'écosystème de plugins.

- **State Redux Toolkit** — rejeté. Le PRD n'a pas de state global complexe (juste l'auth, le chat en cours, les notifications). Zustand fait le job en 50 lignes.

- **CSS Modules** — rejeté. Tailwind est imposé par le PRD et c'est plus productif pour un POC.

- **i18n via react-i18next** — rejeté. `next-intl` est l'option officielle pour Next.js App Router et gère le routing par locale nativement.

## Consequences

- **SSR-friendly** : les pages protégées peuvent être SSR avec cookie de session (cf. s15), réduisant le flash de contenu non-authentifié.
- **Bundle splitting** : Next.js gère le code splitting par route. Pas besoin de configurer Webpack.
- **i18n first** : tout le code est écrit bilingue dès le départ. Réduire la dette de traduction.
- **Responsive** : Tailwind breakpoints par défaut (`sm`, `md`, `lg`) couvrent 360/768/1280. Tests Playwright sur trois viewports.
- **Coût de la migration vers Pages Router** : nul, on n'a pas de frontend à migrer (POC = CLI).
- **Coût d'une refonte vers un autre framework** : élevé. C'est un choix structurant qu'on assume pour la durée du projet.
