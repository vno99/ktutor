# Design — Story s12-creer-compte-eleve

> **Note de périmètre (2026-09-02)** : cette story est **strictement backend**. Aucun écran frontend n'est listé dans ses acceptance criteria (`docs/stories.md` — Phase 3, s12). Pas de mockup HTML produit en s12. Le formulaire d'inscription/création de compte sera mockupé en **s13-login-eleve**, en même temps que le formulaire de login (même écran `/login`, deux onglets ou un toggle). Le présent fichier consigne cette décision pour qu'elle ne soit pas ré-ouverte.

## 1. Objectif et contexte

**Story** : s12-creer-compte-eleve — Phase 3 (Authentification, RBAC, isolation multi-tenant transverse). Première story d'auth : crée la table `users` (PostgreSQL), le wrapper bcrypt, et l'endpoint public `POST /api/auth/register`. Le login (JWT) est en s13, le RBAC en s15.

**Acceptance criteria** (rappel exhaustif, `docs/stories.md` Phase 3 s12) :
- `POST /api/auth/register` accepte `{pseudo, password}` → 201 + `{pseudo}`.
- Mot de passe hashé bcrypt (jamais en clair).
- Pseudo unique case-insensitive → 409 si doublon.
- Pseudo 3-32 chars, `[a-zA-Z0-9_]` → 422 sinon.
- Password ≥ 8 chars → 422 sinon.
- `User` row créée avec `role='eleve'` par défaut.
- Test happy path + duplicate.

**Files involved** (extrait de `docs/stories.md`) :
- `backend/app/api/auth/register.py` (nouveau)
- `backend/app/core/database/models.py` (ajout classe `User`)
- `backend/app/core/auth/passwords.py` (nouveau — wrapper bcrypt)
- `backend/requirements.txt` (ajout `bcrypt>=4.0`)
- `backend/app/main.py` (1 ligne — `app.include_router(register_router)`)
- `backend/tests/api/test_auth_register.py` (nouveau)
- `backend/tests/core/test_models.py` (ajout `TestUserModel`)

**Anchor points** :
- `docs/research/s12-creer-compte-eleve.md` (5 structuring facts, 10 traps, 4 OQ).
- `docs/decisions/005-auth-rs256-rbac.md` (algorithme RS256, RBAC trois rôles, `register` public crée `eleve` uniquement).
- `docs/decisions/011-frontend-pseudo-cookie-pre-jwt.md` (cookie transitoire pré-JWT ; s15 ferme la migration).

## 2. Pourquoi pas de mockup

1. **La story ne produit aucune UI.** Les 7 AC listent des contraintes backend (endpoint, hash, validation, modèle, test). Aucun composant React, aucune page Next.js, aucune route frontend.
2. **Le frontend ne consomme pas encore cet endpoint en s12.** Le frontend public actuel (s11a-c) utilise un `pseudo` en cookie non-HttpOnly (ADR 011) ; le `register` ne sera appelé par le frontend qu'à partir de **s13** (premier écran `/login` qui combine login + register, ou deux onglets).
3. **Pas de design system pour un écran transitoire.** Créer un mockup d'un écran register qu'on n'implémentera pas en s12 et qu'on redéfinira probablement en s13 (quand on aura les contraintes de login) introduit un livrable orphelin qui n'est pas ancré dans le périmètre de la story.
4. **Le design system est en place** pour quand s13 l'utilisera. Tokens (`--color-primary`, `--color-surface`, etc.), composants (`<Input>`, `<Label>`, `<Button>`, `<Card>`, `<Header>`, `<LanguageSwitcher>`), patterns (label+input, 4 états, focus ring, ARIA), namespace i18n `auth` à créer — tout est défini dans `docs/design-system.md`. Le mockup de `/login` se fera en s13 sur ces fondations.

## 3. Reused components (from the design system)

**Aucun composant frontend n'est réutilisé en s12.** La story est 100 % backend.

Pour information (consommé en s13, pas en s12) :
- `<Input>` — champ pseudo + password (`text`, `password`)
- `<Label>` — `<label htmlFor="pseudo">` et `<label htmlFor="password">`
- `<Button variant="primary" size="md">` — bouton « Créer mon compte » / « Se connecter »
- `<Card>` — wrapper de la zone formulaire (centré, `max-w-sm`, `bg-surface`, `border`, `rounded-md`, `shadow-kt-default`)
- `<Header>` — header sticky, masqué sur la route `/login` (overlay plein écran) ou simplifié
- `<LanguageSwitcher>` — toggle FR/EN dans le header
- États : empty, validation error, network error, success → redirige vers `/chat` ou `/upload`
- i18n : nouveau namespace `auth` dans `frontend/messages/{fr,en}.json` (clés : `auth.title`, `auth.pseudo`, `auth.password`, `auth.submit`, `auth.errors.pseudo_taken`, `auth.errors.weak_password`, `auth.errors.invalid_pseudo`, etc.)

## 4. States (côté backend, référence pour s13)

Les états observables côté backend (mappés par le futur frontend en s13) :

| État | Réponse HTTP | Forme de la réponse | UX cible (s13) |
|---|---|---|---|
| **Empty** (formulaire vierge) | — | — | Page rend immédiatement, `<Button>` désactivé tant que les champs ne sont pas valides |
| **Validation client** (pseudo ou password invalide) | — | — | `aria-invalid="true"` + message inline sous le champ, `<Button>` désactivé |
| **Validation serveur** (422) | 422 | `{detail: {error, code: "invalid_pseudo" \| "weak_password"}}` | Idem, message d'erreur inline |
| **Doublon** (409) | 409 | `{detail: {error, code: "pseudo_taken"}}` | Message d'erreur inline sous le champ pseudo |
| **Network error** | — | — | Card erreur réseau avec bouton « Réessayer » |
| **Succès** (201) | 201 | `{pseudo}` | Redirection vers `/chat` (ou `/upload`) — comportement à s13 |
| **Loading** | — | — | `<Button>` avec `disabled` + label « Création… » + `aria-busy="true"` |

## 5. Design system gaps

Aucun gap côté design system. Les composants et patterns requis pour le futur écran `/login` sont tous disponibles dans `docs/design-system.md`. Le namespace i18n `auth` reste à créer en s13.

## 6. Lien vers la story s13

L'écran `/login` (qui abritera aussi le formulaire register) sera mockupé en **s13-login-eleve** dans `docs/designs/s13-login-eleve.md` + `docs/designs/s13-login-eleve.html`. Référence à la PRD : § Authentification.

## 7. Conclusion

s12 shippe sans mockup, sans écran, sans dépendance frontend. La séparation backend/UI est nette : s12 ferme la partie « persistance + contrat HTTP » ; s13 ferme la partie « écran + JWT + i18n ».

---

**Statut** : design skipped, périmètre backend-only confirmé. Mockup à produire en s13.
