---
validated: yes
---
# Plan — s21-i18n-fr-en

Branch: `feature/s21-i18n-fr-en`
Worktree: `.worktrees/s21-i18n-fr-en` (vérifié : branch exacte, clean tracked)
Research: `docs/research/s21-i18n-fr-en.md` — lu. Design: `docs/designs/s21-i18n-fr-en.md` + `.html` (référence, pas code à copier).

## Target story

`docs/stories.md` l.1015-1046 : basculer l'interface FR ↔ EN (next-intl déjà en place côté frontend ; backend `Accept-Language` manquant).

Complexité : 3. Dépendance `s11` (chat page) — résolue (s11a/s11b/s11c mergées).

## Acceptance criteria (verbatim, vérifiables)

1. [ ] **UI strings** : toutes les chaînes UI proviennent de `frontend/messages/fr.json` et `en.json` — aucune chaîne en dur dans les composants. Vérifié par `frontend/scripts/check-i18n.sh` (exit 0).
2. [ ] **Switcher** : un `LanguageSwitcher` dans le header (`Header.tsx`, l.156-158) permet le basculement FR | EN. Vérifié visuellement + Playwright (clic, `aria-pressed`, URL `/fr/chat` → `/en/chat`).
3. [ ] **Cookie persistence** : le choix persiste après reload (cookie `NEXT_LOCALE`, middleware `next-intl`). Vérifié par Playwright + cookie inspection.
4. [ ] **Backend Accept-Language** : le backend lit le header `Accept-Language` (ou dérive du cookie/URL) et renvoie les messages d'erreur dans la bonne langue. Vérifié par un test HTTP (`requests`) avec `headers={"Accept-Language": "en"}` sur `POST /api/auth/login` (erreur 401) et comparaison du `message` dans la réponse.
5. [ ] **Test Playwright EN** : basculement EN traduit toutes les chaînes visibles sur `/chat` (titre, placeholder, bouton Envoyer, labels). Vérifié par `expect(page.locator('h1')).toContainText(...)` après toggle EN.
6. [ ] **Aucun nouveau composant inventé** : le design-system (`docs/design-system.md`) couvre déjà `LanguageSwitcher` et `Header`. Aucune nouvelle couleur / token / composant.

## Tasks (ordered, verifiable)

1. [x] **T1 — Catalog backend minimal** : créer `backend/app/core/i18n/messages_fr.json` et `messages_en.json` (format : `{ "register": { "pseudo_taken": "..." } }`) aligné sur `RegisterErrorCode` / `AuthErrorCode`. Vérifiable : fichier existe, format JSON valide, contient au moins `register.pseudo_taken`, `login.invalid_credentials` dans les deux langues.
2. [x] **T2 — Helper de lecture du header** : ajouter dans `backend/app/core/i18n/` une fonction `get_locale(request: Request) -> str` qui lit `Accept-Language` (par défaut `fr`, fallback `en`). Vérifiable : test unitaire `tests/core/i18n/test_locale_parser.py` avec 3 cas (`fr`, `en`, `fr;q=0.9,en;q=0.8`).
3. [x] **T3 — Intégration auth router** : modifier `backend/app/api/auth/router.py` (`register`, `login`) pour utiliser le catalog au lieu des messages hardcodés. Le `message` du payload passe par le catalog selon la locale. Vérifiable : `register` retourne `"This pseudo is already taken."` pour `Accept-Language: en` et `"Ce pseudo est déjà pris."` pour `fr`.
4. [x] **T4 — Vérifier autres endpoints (scope)** : vérifier `documents/upload`, `exercises/submit`, `evaluations/upload` — leurs messages d'erreur sont-ils couverts par le même contrat ? Si non, ajouter au catalog ou documenter le gap. Vérifiable : grep des `message=` dans `backend/app/api/` et comparaison avec le catalog.
5. [x] **T5 — Playwright : toggle EN sur chat** : créer `frontend/e2e/i18n-toggle.spec.ts` (ou étendre `chat.spec.ts`) : (a) charge `/fr/chat`, (b) clique `EN` dans le switcher, (c) vérifie que le titre contient le texte anglais (`Chat with an agent` au lieu de `Chatter avec un agent`). Vérifiable : test passe (`pnpm exec playwright test` exit 0).
6. [x] **T6 — Playwright : cookie persistence** : après reload de `/en/chat`, le cookie `NEXT_LOCALE=en` est présent et la page reste en EN. Vérifiable : `expect(context.cookies()).toContain(...)` dans le même test ou un test séparé.
7. [x] **T7 — i18n check** : `bash frontend/scripts/check-i18n.sh` exit 0. Vérifiable : commande exécutée dans CI (ou localement) sans erreur.
8. [x] **T8 — Design-system intact** : `frontend/app/globals.css` inchangé (pas de nouveau token) ; `frontend/components/` aucun nouveau fichier (le design-system couvre déjà le switcher). Vérifiable : `git diff` montre 0 ajout dans `globals.css` et 0 nouveau composant dans `components/` autre que le code i18n déjà présent.

## Run interdicts

- **Ne pas toucher `progressive.py`** (`backend/app/services/correction/progressive.py`) — interdict s08. Vérifiable : `git diff --exit-code` sur le fichier doit être vide après execution.
- **Ne pas inventer de nouveau composant UI** — le design-system (`docs/design-system.md`) couvre `LanguageSwitcher` et `Header`. Vérifiable : pas de nouveau `.tsx` dans `frontend/components/` au-delà des modifications sur le switcher existant (si nécessaire).
- **Ne pas ajouter de nouveau namespace i18n** — les namespaces `common`, `chat`, `upload`, `auth`, `dashboard`, `history`, `rewards`, `errors` existent déjà (`frontend/messages/fr.json` et `en.json` lus). Vérifiable : pas de nouveau namespace ajouté au fichier messages sans justification.
- **Multitenancy préservé** : l'i18n ne doit pas toucher `student_pseudo`, ni le filtrage des données. Vérifiable : aucun changement dans `backend/app/core/auth/middleware.py` qui altérerait la logique `get_current_user` au-delà du parsing du `Accept-Language` header.
- **Pas de code direct dans le répertoire base** — tout le travail se fait dans `.worktrees/s21-i18n-fr-en`. Vérifiable : `git status` dans le worktree montre uniquement la branche `feature/s21-i18n-fr-en`.

## The point everything turns on

**Le point critique** : le contrat du backend (`Accept-Language` → message traduit via catalog) doit être cohérent avec le contrat frontend (cookie `NEXT_LOCALE` + URL `/fr/` ou `/en/`).

Si le backend lit `Accept-Language` mais le frontend envoie le cookie `NEXT_LOCALE` sans le refléter dans l'URL, un utilisateur pourrait voir `/fr/chat` avec un header `Accept-Language: en` — le backend répondrait en anglais mais le frontend resterait en français. L'alignement doit être : le frontend envoie le même locale dans l'URL ET dans le header (via axios interceptors, ou au minimum le backend lit l'URL en priorité).

**Points de comparaison** :
- Comparer le comportement du `createMiddleware(routing)` (cookie → URL rewrite) avec le header envoyé par `apiClient` (`frontend/lib/api.ts`). Vérifier que `apiClient` n'envoyait pas déjà `Accept-Language` (il ne le fait pas actuellement, selon la lecture de `lib/api.ts` dans la session précédente — à vérifier dans le worktree).
- Si `apiClient` ne transmet pas le locale, le backend doit soit : (a) lire le cookie `NEXT_LOCALE` (non standard pour API FastAPI), ou (b) exiger que le frontend ajoute un header `X-Locale` ou `Accept-Language` basé sur `useLocale()`.
- La décision du plan : définir explicitement le mécanisme (ex. : `Accept-Language` lu par le backend, et le frontend s'assure de l'envoyer via un intercepteur). Cette décision doit être documentée dans le plan et dans un ADR si c'est un choix structurel nouveau.

## Files touched (anticipated)

- `docs/plans/s21-i18n-fr-en.md` (ce fichier)
- `backend/app/core/i18n/messages_fr.json` (nouveau)
- `backend/app/core/i18n/messages_en.json` (nouveau)
- `backend/app/core/i18n/__init__.py` (nouveau — helper `get_locale`)
- `backend/app/core/i18n/test_locale_parser.py` (nouveau — tests)
- `backend/app/api/auth/router.py` (modifié — utilisation du catalog)
- `backend/app/api/auth/schemas.py` (peut rester inchangé si le `message` est traduit au niveau du router, pas au niveau du schéma)
- `frontend/messages/fr.json`, `frontend/messages/en.json` (vérifiés, pas modifiés sauf si un namespace manque — mais le design-system couvre tout)
- `frontend/lib/stores/chatStore.ts` (si un commentaire d'en-tête doit référencer le contrat i18n backend — optionnel, conforme à AC17 s11b)
- `frontend/e2e/i18n-toggle.spec.ts` (nouveau — tests Playwright)
- `frontend/scripts/check-i18n.sh` (déjà présent — exécution de vérification)

## Test strategy

- **Unitaire backend** : `tests/core/i18n/test_locale_parser.py` (3 cas).
- **Intégration backend** : `tests/api/auth/test_register_i18n.py` (stub 2 requêtes : `Accept-Language: fr` → message français, `en` → message anglais). Utiliser `pytest` avec le `TestClient` FastAPI et injecter le header.
- **E2E frontend** : `frontend/e2e/i18n-toggle.spec.ts` — toggle EN sur `/fr/chat`, assertion sur le texte anglais visible (`t('chat.title')` → `"Chat with an agent"`). Utiliser `Playwright` + `axe-core` (0 violation).
- **Lighthouse / axe-core** : réutiliser la config existante (`frontend/playwright.config.ts`, `frontend/lighthouserc.json`). S'assurer que l'ajout du test i18n ne casse pas le score a11y (le switcher respecte `aria-pressed`, `aria-label`).
- **Multi-tenant isolation** : pas de test spécifique nécessaire (l'i18n ne touche pas les données élèves), mais vérifier que le middleware `get_current_user` reste inchangé dans sa logique d'isolation.

## Definition of Done (spécialisée s21)

- `docs/plans/s21-i18n-fr-en.md` avec `validated: yes` (checkpoint humain `/ks-plan`).
- `docs/research/s21-i18n-fr-en.md` lu (déjà présent).
- Design (`docs/designs/s21-i18n-fr-en.md` + `.html`) présent — réutilisation du design-system, aucun nouveau composant inventé.
- Tests verts : `pytest backend/` (tests i18n passants) + `pnpm exec playwright test frontend/e2e/i18n-toggle.spec.ts` (exit 0) + `bash frontend/scripts/check-i18n.sh` (exit 0).
- Aucune régression sur le code existant : `git diff` sur `progressive.py` vide (interdict s08) ; `global.css` inchangé ; `components/` aucun nouveau fichier (interdict design-system).
- Multi-tenant préservé : `get_current_user` dans `middleware.py` non altéré au-delà du parsing `Accept-Language`.
- Observabilité conforme : pas de nouveaux logs requis (l'i18n n'introduit pas de nouveau service), mais si le catalog backend est ajouté, aucun secret/token/message utilisateur ne doit être logué dans le message d'erreur traduit (suivre `loguru` conventions).
- i18n : aucune chaîne en dur dans le frontend (vérifié par `check-i18n.sh`) ; catalog backend couvre au moins `register` et `login`.
- Accessibilité : le switcher respecte `aria-pressed`, `focus-visible`, `prefers-reduced-motion`.
- PR unique, description structurée (résumé AC cochées, points d'attention : backend catalog format, alignement URL/cookie/header, design-system intact).
- Mode de merge : manuel (défaut). `Ship allowed: yes` dans `docs/reviews/s21-i18n-fr-en.md` après review. Pas de merge automatique sans `MERGED` prouvé.
