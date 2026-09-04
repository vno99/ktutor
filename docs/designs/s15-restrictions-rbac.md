# Design — Story s15-restrictions-rbac

> **Note de périmètre (2026-09-03)** : cette story est **strictement backend**. Aucun écran frontend n'est listé dans ses acceptance criteria (`docs/stories.md` Phase 3 § s15-restrictions-rbac). Pas de mockup HTML produit en s15. Le présent fichier consigne cette décision et inventorie les **implications UX mineures** qui découlent du contrat HTTP mis à jour (codes d'erreur 401/403 reconnus par le frontend), pour qu'elles ne soient pas ré-ouvertes.

## 1. Objectif et contexte

**Story** : s15-restrictions-rbac — Phase 3 (Rôles et sécurité). Dernière story d'auth côté backend : ferme la migration `body.pseudo` → `request.state.pseudo` (cf. ADR 010 D3), ajoute la garde cross-tenant HTTP-level, et aligne le frontend sur l'identité dérivée du token.

**Acceptance criteria** (rappel exhaustif, `docs/stories.md:771-794`) :
1. Every authenticated endpoint extracts the `pseudo` from the JWT and uses it as the tenant key.
2. Any request where a body/URL field contains a `pseudo` different from the JWT's `pseudo` is rejected with 403 (for an élève) or processed (for an admin).
3. Every existing endpoint that returns or mutates data has a corresponding test that verifies cross-tenant access is blocked.
4. The middleware logs a `security.cross_tenant_attempt` event when a block occurs.
5. A test simulates a student JWT trying to access another student's data via URL manipulation and verifies the 403.

**Files involved** (extrait de `docs/stories.md`) + ancré par `docs/research/s15-restrictions-rbac.md` :
- `backend/app/core/auth/middleware.py` (étendre avec garde cross-tenant optionnelle)
- `backend/app/api/chat/router.py` + `schemas.py` (retrait `body.pseudo`, ajout `Depends(get_current_user)`)
- `backend/app/api/documents/router.py` (retrait `Form(pseudo)`, ajout `Depends(get_current_user)`)
- `backend/app/core/database/models.py` (matérialisation FKs `student_pseudo → users.pseudo`, sans Alembic, via `create_all`)
- `backend/tests/api/test_chat_stream.py` + `test_documents_upload.py` (tests HTTP-level 401/403)
- `frontend/lib/stores/chatStore.ts` + `uploadStore.ts` (retrait `pseudo` du payload sortant)

**Anchor points** :
- `docs/research/s15-restrictions-rbac.md` (5 structuring facts, 8 traps, 5 OQ)
- `docs/decisions/005-auth-rs256-rbac.md` (RS256, 3 rôles, admin bypass)
- `docs/decisions/010-frontend-mock-pre-jwt.md` § D3 (s15 remplace `body.pseudo` par `request.state.pseudo`)
- `docs/decisions/011-frontend-pseudo-cookie-pre-jwt.md` (cookie transitoire, fermé en s15)

## 2. Pourquoi pas de mockup

1. **La story ne produit aucune UI.** Les 5 AC listent des contraintes backend (middleware, garde, log, tests). Aucun composant React, aucune page Next.js, aucune route frontend nouvelle.
2. **Les écrans touchés (`/chat`, `/upload`) sont déjà livrés (s11b, s11c).** Leur UI n'est pas modifiée par s15 — seul le contrat HTTP change (body sans `pseudo`, header `Authorization: Bearer` déjà attaché par l'interceptor s13). L'utilisateur ne voit **rien** de différent dans un cas nominal.
3. **Le seul changement visible côté UI** est l'apparition d'un `<Card error>` (cf. design-system § Card) si le serveur retourne un nouveau 403 `cross_tenant` (cas pathologique : un JWT forgé manuellement ou un cookie résiduel après changement de session). Ce comportement est **déjà couvert** par le pattern existant de gestion d'erreur (le `chatStore` et l'`uploadStore` reconnaissent un `code` dans le body et le mappe vers le `Card error` du design system).
4. **Le design system est en place** et **aucun nouveau composant n'est requis**. Tokens (`--color-error`, `--color-warning`, etc.), composants (`<Card>`, `<Button>`, `<Header>`, `<Input>`), patterns (focus ring, ARIA, 4 états), namespace i18n `auth` — tout est défini dans `docs/design-system.md`. Le mockup de la bannière d'erreur 403 pourrait être fait, mais c'est le **même** `<Card error>` que l'erreur réseau (s11b) ou l'erreur OCR (s11c) — un mockup dupliquerait s11b ou s11c sans rien apporter.

## 3. Implications UX (mineures, déjà couvertes par le design system existant)

### 3.1 Code HTTP 401 — Token manquant / expiré / invalide

**Réponse** : `{"error": "Token invalide ou expiré.", "code": "invalid_token"}` (cf. `app/core/auth/middleware.py:39-42`).

**UX existante (s13)** : l'interceptor `apiClient` d'`api.ts:142-208` tente **une seule fois** un `POST /api/auth/refresh`. Si le refresh échoue, le store `authStore` est vidé et l'utilisateur est redirigé vers `/login?next=<pathname>`. C'est la couverture de l'état « session perdue » — déjà en place, non touchée par s15.

**Pas de mockup requis** : la redirection vers `/login` est déjà mockupée par `docs/designs/s13-login-eleve.{md,html}`.

### 3.2 Code HTTP 403 — Cross-tenant attempt (nouveau)

**Réponse** : `{"error": "Accès refusé.", "code": "forbidden"}` (cf. `app/core/auth/middleware.py:44-47` — déjà existant pour le cas rôle insuffisant ; s15 le réutilise pour la garde cross-tenant).

**UX** : le `Card error` du design system (cf. `docs/design-system.md` § Card) avec `--color-error` en bordure gauche et `--color-text-primary` pour le titre « Action non autorisée ». L'icône `x-circle` (lucide) dans le coin. Le label i18n `auth.errors.forbidden` à créer (namespace `auth`).

**Composant existant réutilisé** : `<Card variant="error">` (déjà utilisé pour l'erreur réseau `code: "network"` dans `chatStore` et l'erreur 422 dans `uploadStore`).

**Pas de mockup requis** : la card d'erreur suit le pattern établi. L'utilisateur qui tombe dessus (forgery manuelle ou cookie résiduel) reçoit un `<Card error>` avec un message i18n générique — c'est le pattern normal du design system.

### 3.3 Code SSE `cross_tenant` — Cas pathologique streaming

**Réponse** : `data: {"error": "...", "code": "cross_tenant"}\n\n` (cf. `app/api/chat/schemas.py:62-77` — déjà existant pour le cas service-level ; s15 le réutilise au niveau auth).

**UX** : même `<Card error>` que ci-dessus, rendu inline dans le fil de chat (le `chatStore` colle l'erreur sur le dernier message assistant, cf. `chatStore.ts:213-223`).

**Pas de mockup requis** : le pattern « erreur SSE → erreur sur le dernier message » est déjà mockupé par `docs/designs/s11b-frontend-chat.{md,html}` § error states.

## 4. Reused components (from the design system)

| Composant | Source (design-system.md) | Réutilisation s15 |
| --- | --- | --- |
| `<Card variant="error">` | § Card, ligne 200-228 | Affichage des erreurs 401/403/cross-tenant côté chat et upload |
| Tokens `--color-error`, `--color-text-primary`, `--color-canvas` | § Tokens, ligne 11-27 | Bordure et fond du Card error |
| Pattern `aria-live="polite"` | § Accessibility | Annonce screen-reader du nouveau message d'erreur dans le chat |
| Namespace i18n `auth` | § i18n, ligne 180-195 | Nouvelle clé `auth.errors.forbidden` (« Action non autorisée. ») |
| Token Inter 14px / 16px | § Typographie, ligne 50-68 | Texte du Card error |

## 5. Design system gaps

**Aucun gap identifié.** Les seuls éléments visuels qu'introduit s15 (le `<Card error>` 403 et la bannière d'erreur SSE) sont déjà implémentés et mockupés par les stories antérieures. Le design system n'a pas besoin d'extension.

## 6. Décision de périmètre

Cette story ne livre **aucun mockup HTML** et **aucun composant partagé nouveau**. Le seul changement est :
- **Contrat HTTP** : suppression de `pseudo` dans le body des deux endpoints existants, ajout de `Authorization: Bearer` (déjà en place via s13).
- **Couche UX** : aucune nouvelle UI ; les cas d'erreur nouveaux (401/403/cross-tenant) sont absorbés par les `<Card error>` et le redirect `/login` déjà en place.
- **i18n** : ajout d'**une seule clé** dans le namespace `auth` (`auth.errors.forbidden` — déjà couverte par le namespace existant, pas de nouveau namespace à créer).

**Pas de mockup, pas de page, pas de composant.** Le design s'arrête ici pour ne pas dupliquer s11b, s11c et s13.

## 7. Suivi pour les stories suivantes

- **s16+ (dashboards)** : si un dashboard expose un état « session perdue / token expiré », il réutilisera le même redirect `/login?next=...` (cf. design-system § auth pattern). Pas de design à refaire.
- **s18+ (parent agit pour le compte de l'enfant)** : si un jour la garde cross-tenant **bypass** le parent (recommandation Piège 3 du research : non-recommandé pour l'instant), il faudra un nouveau design. **Hors-scope s15.**
- **s22 (a11y + UX pass)** : vérifiera que le `<Card error>` 403 a un `role="alert"` (cf. design-system § a11y).
