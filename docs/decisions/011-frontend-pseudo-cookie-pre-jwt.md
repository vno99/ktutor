# ADR 011 — Identité frontend en cookie `pseudo` + store Zustand hydraté (pré-JWT)

- Status: accepted
- Date: 2026-09-02
- Scope: story s11a (frontend bootstrap), projette sur s11b, s11c, s15

## Context

L'architecture impose un multi-tenancy strict par `student_pseudo` (ADR 005 + ADR 004). Le backend valide chaque requête via le `pseudo` extrait du JWT (ADR 005, réalisé en s15). Mais **avant s15** (s12-s14 livrent auth/register/refresh/JWT mais le chat et l'upload sont déjà accessibles via s11b/s11c), il faut un mécanisme d'identité transitoire côté frontend.

Options :

- **(a) Pseudo dans l'URL** : `/{locale}/chat?pseudo=ali_baba`. Simple mais leak dans l'historique navigateur, les logs serveur, le partage de liens. Mauvais.
- **(b) Pseudo dans le `body` POST** à chaque appel : `{pseudo, subject, question}`. C'est le contrat s09 (ADR 010). Mais c'est le **client** qui envoie le pseudo : impossible de garantir qu'il correspond à une session. Risque de spoofing.
- **(c) Pseudo en cookie non-HttpOnly** : posé par l'utilisateur via l'input pseudo du header, lu côté client par un store Zustand, mirroré en cookie `path=/; max-age=30d; SameSite=Lax`. Envoyé dans le `body` de chaque appel API. HttpOnly est exclu car le client JS doit le lire.
- **(d) Pseudo en `localStorage`** : persistant, mais pas lu par le serveur (Next.js middleware). Pas de SSR/CSR boundary cohérente. Et `localStorage` n'est pas accessible aux Server Components.

## Decision

**Option (c) : pseudo en cookie `pseudo` + store Zustand `authStore` hydraté client-side.**

Implémentation (s11a, `frontend/lib/stores/authStore.ts`) :

```ts
const PSEUDO_COOKIE = 'pseudo';
const PSEUDO_PATTERN = /^[a-zA-Z0-9_]{3,32}$/;

export const useAuthStore = create<AuthState>((set) => ({
  pseudo: '',
  hydrated: false,
  hydrate: () => { /* lit document.cookie, set {pseudo, hydrated: true} */ },
  setPseudo: (next) => { /* valide regex, écrit cookie, set {pseudo} */ },
  clearPseudo: () => { /* max-age=0, set {pseudo: ''} */ },
}));
```

- **Validation côté client** : la regex `^[a-zA-Z0-9_]{3,32}$` est appliquée à la fois par le frontend (UX : on désactive le bouton Envoyer tant que le pseudo n'est pas valide) et par le backend service (cf. `validate_pseudo` dans `chroma_store.py`). Belt-and-braces, mais le client n'est pas un rempart de sécurité — c'est le backend qui tranchera en s15.
- **Cookie non-HttpOnly** : nécessaire pour que `authStore` puisse le lire côté client (`document.cookie`). `SameSite=Lax` bloque les CSRF GET. `max-age=30d` aligné sur les standards SaaS grand public.
- **Hydratation client-side only** : Next.js 16 + App Router ne supporte pas le state Zustand pré-rendu (cf. note dans le fichier). `hydrate()` est appelé après mount, dans un `useEffect` ou dans un composant client racine. Pas de SSR state.
- **Migration vers JWT en s15** : le cookie `pseudo` est remplacé par un cookie `access_token` (HttpOnly) + `refresh_token`. `authStore` continue d'exposer `pseudo` (lu depuis `/api/auth/me` au mount), mais l'écriture passe par `POST /api/auth/login`. Le **contrat frontend vers backend** change : `pseudo` n'est plus dans le `body` mais dans le JWT.

## Considered options

- **(a) URL `?pseudo=`** — rejetée. Leak dans l'historique, mauvais UX, mauvais SEO, contredit la consigne « pas de PII en URL » du PRD.
- **(b) Pseudo dans le body sans cookie** — rejetée pour le pre-JWT. Le client envoie `{pseudo, ...}` mais rien ne garantit que `pseudo` correspond à une session. En s15, le pseudo vient du JWT, pas du body. C'est un **changement de contrat** qui ne peut pas être transparent.
- **(d) `localStorage`** — rejetée. Pas lisible par le middleware Next.js (donc flash de contenu non-authentifié si on SSR), et storage API throw parfois (private mode, blocked). Le cookie est plus robuste et marche avec SSR.

## Consequences

- **Simple à comprendre** : `useAuthStore.getState().pseudo` est l'unique source de vérité côté frontend. Pas de `Context`, pas de prop drilling, pas de re-render cascade.
- **Bilingue et a11y dès s11a** : le composant `<Header>` qui pose le cookie est traduit via `next-intl` et accessible (label, `aria-invalid`).
- **Migration JWT en s15 quasi-gratuite** : le `authStore` reste, seul le `hydrate()` change (lit `/api/auth/me` au lieu de `document.cookie`), et le `chatStore.send` / `uploadStore.upload` retirent `pseudo` du body pour le mettre dans le JWT.
- **Risque de spoofing pre-s15** : un élève peut технически envoyer un `pseudo` qui n'est pas le sien dans le body. Le backend s15 ferme cette faille. En attendant, l'isolation par collection ChromaDB (`rag_<subject>_<pseudo>`, ADR 004) limite l'impact : un élève A qui spoof un pseudo B accède à la collection de B, mais le body `{pseudo: "B"}` ne crée pas de session ; c'est un trou, mais borné par l'isolation ChromaDB. **Acceptable en POC** (cf. PRD § Identité « projet local, pas de PII réelle »). Le ship gate du s15 ferme définitivement.
- **Test isolation cross-tenant** : dès s11b/s11c, le test e2e stubbe `useAuthStore` pour vérifier que le body contient bien le pseudo du store (pas une string en dur). En s15, le test bascule sur le header `Authorization: Bearer <token>`.
