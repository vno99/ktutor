# Design — Story s13-login-eleve

> **Note de périmètre (2026-09-03)** : cette story a un **double scope** :
> 1. **Backend** (AC de la story) : `POST /api/auth/login`, `POST /api/auth/refresh`, `POST /api/auth/logout` (recommandation research Q4), middleware JWT (`Depends(get_current_user)`, `require_role`), clés RS256, blacklist `jti`, `Settings.jwt_*`.
> 2. **Frontend** (UI consommatrice des nouveaux endpoints, voir `docs/designs/s12-creer-compte-eleve.md` § 6 « Lien vers la story s13 ») : page `/login`, page `/register` (l'écran que s12 n'a pas pu produire, c'est ici qu'il vit), Header « connecté » avec bouton « Se déconnecter », namespace i18n `auth`.
>
> La séparation est nette : **le mockup couvre les écrans frontend** (ce que cette story shippe visuellement). **Le contrat HTTP est documenté dans le research et sera détaillé dans le plan** (côté backend uniquement).

## 1. Screen(s)

### Écran A — `/login` (nouveau)

**Layout** (mobile-first, identique tablette en `max-w-sm mx-auto`) :

```
┌──────────────────────────────────────────┐
│ [Header sticky : logo + LanguageSwitcher]│  ← 56px, bg-surface, border-b
├──────────────────────────────────────────┤
│                                          │
│  (vide, flex-1)                          │
│                                          │
│  ┌──────────────────────────────────┐   │  ← Card
│  │  Se connecter                    │   │  ← h1, text-2xl, font-semibold
│  │                                  │   │
│  │  Pseudo                          │   │  ← Label htmlFor
│  │  [_________________________]     │   │  ← Input type=text, 44px
│  │                                  │   │
│  │  Mot de passe                    │   │  ← Label htmlFor
│  │  [_________________________] 👁  │   │  ← Input type=password, 44px
│  │                                  │   │
│  │  ┌────────────────────────────┐  │   │  ← Button primary, full-width
│  │  │  Se connecter              │  │  │
│  │  └────────────────────────────┘  │   │
│  │                                  │   │
│  │  Pas de compte ? Créer un compte │   │  ← Lien vers /register
│  │                                  │   │
│  └──────────────────────────────────┘   │
│                                          │
│  (vide, flex-1)                          │
│                                          │
├──────────────────────────────────────────┤
│ [Bottom tab bar : Chat | Upload]         │  ← masquée sur /login (s22)
└──────────────────────────────────────────┘
```

**États de la Card** (mapping depuis le contrat backend, cf. `docs/designs/s12-creer-compte-eleve.md` § 4) :

| État | Rendu visuel | Code i18n |
|---|---|---|
| **Empty** | Formulaire vierge, bouton « Se connecter » désactivé tant que les deux champs ne sont pas remplis | — |
| **Validation client** (pseudo ne matche pas `^[a-zA-Z0-9_]{3,32}$`) | Input pseudo en `border-error` + `aria-invalid="true"`, message `auth.errors.invalidPseudo` sous le champ, bouton désactivé | `auth.errors.invalidPseudo` |
| **Validation client** (password vide) | Pas de validation client (le backend 422 si vide) | — |
| **Validation serveur 422** | Card `bg-error/10 border border-error/30`, message inline sous le champ concerné, code machine en `text-xs text-text-tertiary` | `auth.errors.invalidCredentials` (générique — ne leak pas la cause) |
| **Wrong password 401** | Idem, message générique « Pseudo ou mot de passe incorrect. » | `auth.errors.invalidCredentials` |
| **Network error** | Card `bg-error/10` au-dessus du formulaire, icône `alert-triangle`, message « Erreur réseau. Vérifie ta connexion. » + bouton « Réessayer » | `errors.network` (namespace existant) |
| **Loading** | `<Button>` avec `disabled` + label « Connexion… » + `aria-busy="true"`. Le formulaire n'est pas masqué, juste inerte. | `auth.submitting` |
| **Succès 200** | Pas d'écran : redirection immédiate vers `/chat` (ou `/upload` si la query `?next=` est présente). Le store `authStore` est hydraté avec `{accessToken, refreshToken, role, pseudo}` avant la navigation. | — |

### Écran B — `/register` (nouveau — promis par s12)

**Layout** : strictement identique à `/login` (même Card, même hauteur). Seuls changent le titre (« Créer un compte »), le bouton (« Créer mon compte »), le label du password (« Choisis un mot de passe (8 caractères minimum) »), et le lien en bas (« Déjà un compte ? Se connecter »).

**États** : strictement identiques à `/login` (cf. `docs/designs/s12-creer-compte-eleve.md` § 4 pour le mapping 422/409/network/loading/success). Codes i18n supplémentaires :

| État serveur | Code i18n |
|---|---|
| 409 `pseudo_taken` | `auth.errors.pseudoTaken` (« Ce pseudo est déjà pris. ») |
| 422 `weak_password` | `auth.errors.weakPassword` (« Mot de passe trop court. 8 caractères minimum. ») |
| 422 `invalid_pseudo` | `auth.errors.invalidPseudo` |
| 201 succès | Redirection vers `/chat` (ou `?next=`) |

### Écran C — `<Header>` connecté (modification)

**Layout** (intégré dans le Header sticky existant, 56px) :

```
┌──────────────────────────────────────────────────────────┐
│ [ktutor]  [Chat] [Upload]  · · ·  [FR|EN]  [👤 ali ▾]   │
└──────────────────────────────────────────────────────────┘
```

- Le **pseudo input** (input libre, ligne 71-93 de `Header.tsx`) est **remplacé** par un **bouton avatar + nom** quand `useAuthStore.hydrated === true` et `useAuthStore.accessToken !== null`.
- Click sur l'avatar → **dropdown menu** (gap : pas de `<Dialog>`/`<Popover>` dans le design system, cf. Gaps § 4). Fallback : un `<details>`/`<summary>` natif HTML, accessible sans JS.
- Items du menu : « Mon espace » (lien vers `/chat`, désactivé — la nav principale le fait déjà), « Se déconnecter » (bouton `destructive` qui appelle `useAuthStore.clearTokens()` + `POST /api/auth/logout`).
- L'avatar est l'initiale du `pseudo` en majuscule dans un cercle `bg-primary text-white` (24px sur mobile, 32px sur tablette).
- `<LanguageSwitcher>` reste à droite, intact.

**États** :

| État | Rendu |
|---|---|
| Non connecté (pas de tokens) | Avatar remplacé par un bouton « Se connecter » (variante `primary` `size="sm"`) qui pointe vers `/login` |
| Hydraté, connecté | Avatar + pseudo + menu |
| Hydraté, non connecté | Bouton « Se connecter » |
| Non hydraté (avant le 1er `useEffect`) | Bouton « Se connecter » (le SSR ne peut pas connaître l'état d'auth, l'hydratation corrige au mount) |

> **Note de rétro-compatibilité** : le `<Header>` actuel expose déjà `setPseudo` (cookie-backed, ADR 011). Après s13, **le cookie `pseudo` n'est plus nécessaire pour la nav** (le JWT porte l'info). Mais on **garde** le cookie pour le store Zustand (`authStore.pseudo` est lu depuis le JWT décodé, le cookie reste un cache de transition — ADR 011 § « Migration JWT en s15 quasi-gratuite »). Le bouton « Se connecter » remplace l'input.

### Écran D — Home `page.tsx` (modification mineure)

**Layout** (mobile + tablette) :

```
┌──────────────────────────────────────────┐
│ [Header connecté ou « Se connecter »]    │
├──────────────────────────────────────────┤
│                                          │
│       Bienvenue sur ktutor               │  ← h1 (existant)
│       Un assistant IA pour réviser…      │  ← p (existant)
│                                          │
│  [Commencer à chatter]  [Uploader]       │  ← CTAs (existants, inchangés)
│                                          │
└──────────────────────────────────────────┘
```

**Pas de modification** des CTAs : ils pointent toujours vers `/chat` et `/upload`. La protection par middleware JWT arrive en **s15**, pas en s13 (cf. research § Traps 5 — la story s13 introduit les tokens mais ne gate pas encore les routes `(public)`). C'est cohérent avec l'ADR 011 « le `pseudo` reste en cookie en s13, le JWT remplace en s15 ».

## 2. Mockup

`docs/designs/s13-login-eleve.html` — mockup HTML statique des écrans A (/login), B (/register), C (Header connecté), avec les **4 états critiques** (empty, validation serveur, network, loading) rendus en parallèle. **Un seul HTML**, ancré dans une grille 4 colonnes (un état par colonne), pour faciliter la revue.

**Conformité au design system** :
- Couleurs : tokens `bg-canvas`, `bg-surface`, `text-text-primary`, `text-text-secondary`, `text-text-tertiary`, `border-border`, `border-error`, `bg-error/10`, `bg-primary`, `text-white`. Zéro hex en dur.
- Typographie : `text-2xl font-semibold tracking-tight` (h1), `text-base` (body), `text-sm` (labels), `text-xs` (codes erreur).
- Espacement : Tailwind scale (px-3, py-2, gap-3, mt-4, etc.).
- Radius : `rounded-sm` (boutons, inputs), `rounded-md` (cards).
- Ombres : `shadow-kt-default` (cards), `shadow-kt-sm` (header dropdown).
- Icônes : Lucide (`alert-triangle`, `eye`, `eye-off`, `log-out`).
- Composants : `<Header>`, `<Card>`, `<Input>`, `<Label>`, `<Button>`, `<LanguageSwitcher>` (tous existants).
- i18n : toutes les chaînes dans des `data-i18n` (placeholder pour la prod), exemples en français.

## 3. Reused components (from the design system)

| Composant | Usage | Justification |
|---|---|---|
| `<Header>` | Bandeau sticky 56px (existant) | Réutilisé tel quel, modifié pour basculer entre « input pseudo » et « avatar + menu » selon `authStore.hydrated + tokens` |
| `<LanguageSwitcher>` | Pill FR \| EN dans le header | Existant, positionné à droite, intact |
| `<Card>` | Conteneur du formulaire login/register | Wrapper centré, `max-w-sm`, `bg-surface`, `border`, `rounded-md`, `shadow-kt-default` |
| `<Input>` | Champs pseudo + password | Hauteur 44px, `border-error` + `aria-invalid` quand applicable |
| `<Label>` | Labels accessibles (`htmlFor`) | Systématique sur les deux champs |
| `<Button>` | CTA principal (primary) | `size="md"` (44px), full-width dans la Card, `disabled` pendant loading |
| `<LanguageSwitcher>` (réutilisé) | Toggle langue | Inclus dans le `<Header>` (composé) |
| Icônes Lucide | `alert-triangle` (erreur), `eye`/`eye-off` (password reveal), `log-out` (déconnexion) | Tree-shakable, import depuis `lucide-react` |

## 4. States (mapping backend → UI, inspiré de s12 § 4)

| État backend | Réponse HTTP | Forme | UX cible (s13) |
|---|---|---|---|
| **Empty** (formulaire vierge) | — | — | Page rend immédiatement, `<Button>` désactivé tant que les deux champs ne sont pas remplis |
| **Validation client** (pseudo < 3 chars ou > 32 ou caractères interdits) | — | — | `aria-invalid="true"` sur l'Input + message inline, `<Button>` désactivé |
| **Validation serveur** 422 (pseudo ou password invalide côté serveur) | 422 | `{detail: {error, code: "invalid_pseudo" \| "weak_password"}}` | Card `bg-error/10 border-error/30`, message inline sous le champ, code en `text-xs text-text-tertiary` |
| **Wrong credentials** 401 | 401 | `{detail: {error, code: "invalid_credentials"}}` | **Message générique** « Pseudo ou mot de passe incorrect. » (ne leak pas l'existence du pseudo) |
| **Pseudo taken** 409 (register) | 409 | `{detail: {error, code: "pseudo_taken"}}` | Message inline « Ce pseudo est déjà pris. » sous le champ pseudo |
| **Network error** | — | — | Card `bg-error/10` au-dessus du formulaire, message « Erreur réseau. » + bouton « Réessayer » |
| **Loading** | — | — | `<Button disabled aria-busy="true">` avec label « Connexion… » (ou « Création… » sur register) |
| **Succès** 200 | 200 | `{access_token, refresh_token, token_type, expires_in}` | Store hydraté, redirection vers `/chat` (ou `?next=`). Toast éventuel en s25. |

**Détail sécurité (Piège 6 research)** : le message 401 est **toujours** « invalid_credentials » (générique), qu'il s'agisse d'un pseudo inexistant ou d'un mot de passe faux. L'implémentation backend (timing-constant via dummy hash) est documentée dans le research.

## 5. Design system gaps

| # | Gap | Impact | Résolu par |
|---|---|---|---|
| 1 | **Pas de `<Avatar>` dans le design system** | L'avatar dans le Header (initiale dans un cercle) doit être composé à la main avec `bg-primary text-white rounded-full w-8 h-8 flex items-center justify-center font-semibold` | s17 (parent dashboard) ou s22, comme listé dans `docs/design-system.md` l.231. **Workaround** documenté dans le plan. |
| 2 | **Pas de `<Popover>` / `<Dropdown>`** | Le menu « Se déconnecter » de l'avatar doit être fait avec un `<details>`/`<summary>` natif HTML (accessible, zéro JS, focusable) | s22. **Workaround** documenté. |
| 3 | **Pas de `<PasswordInput>`** avec bouton `eye`/`eye-off` | Le mockup montre un toggle de visibilité (commodité). L'implémentation peut soit (a) l'omettre et utiliser `<Input type="password">` brut, soit (b) créer un composant local `PasswordInput` dans `frontend/components/` | (a) **recommandé** pour s13 (YAGNI), (b) si usage répété. |
| 4 | **Pas de toast in-app** | La confirmation de login réussi passe par redirection, pas par toast. Les erreurs 401 sont inline (Card). | s25 (cf. design-system l.230). |
| 5 | **Pas de `<Skeleton>` loader** | Le formulaire affiche immédiatement avec champs vides + bouton désactivé. Pas de loader « page » plein écran. | s22. |
| 6 | **Pas de `<EmptyState>` illustré** | Le (vide, flex-1) en haut et en bas du formulaire ne montre rien. Acceptable pour un écran 100 % formulaire. | s22. |
| 7 | **Pas de gestion du focus sur erreur** | Quand le 401 arrive, le focus doit revenir sur le premier champ en erreur. Pas de pattern documenté. | À coder au cas par cas dans le composant login. **Pas bloquant**. |
| 8 | **Le bottom tab bar n'est pas masquée sur /login actuellement** | L'architecture doc dit « masquée sur la route /login (overlay plein écran) » mais le code de la tab bar n'a pas été vérifié sur s11a/b/c. Si la tab bar existe, le plan doit ajouter la condition `pathname !== '/login'`. | Vérification dans le plan. |

**Tous les gaps sont marqués « hors-scope s13 »** — aucun ne bloque l'implémentation, chacun a un workaround acceptable.

## 6. i18n — namespace `auth`

À créer dans `frontend/messages/fr.json` et `frontend/messages/en.json` :

```json
{
  "auth": {
    "login": {
      "title": "Se connecter",
      "pseudoLabel": "Pseudo",
      "passwordLabel": "Mot de passe",
      "submit": "Se connecter",
      "submitting": "Connexion…",
      "noAccount": "Pas de compte ?",
      "registerLink": "Créer un compte"
    },
    "register": {
      "title": "Créer un compte",
      "pseudoLabel": "Pseudo",
      "passwordLabel": "Mot de passe",
      "passwordHelp": "8 caractères minimum, 72 maximum.",
      "submit": "Créer mon compte",
      "submitting": "Création…",
      "hasAccount": "Déjà un compte ?",
      "loginLink": "Se connecter"
    },
    "logout": {
      "label": "Se déconnecter",
      "menuAlt": "Ouvrir le menu utilisateur"
    },
    "errors": {
      "invalidCredentials": "Pseudo ou mot de passe incorrect.",
      "invalidPseudo": "Pseudo invalide. 3 à 32 caractères (lettres, chiffres, underscore).",
      "weakPassword": "Mot de passe trop court. 8 caractères minimum.",
      "pseudoTaken": "Ce pseudo est déjà pris.",
      "passwordTooLong": "Mot de passe trop long (72 caractères maximum).",
      "network": "Erreur réseau. Vérifie ta connexion.",
      "retry": "Réessayer"
    }
  }
}
```

Toutes les chaînes UI passent par `useTranslations('auth.*')` — aucune string en dur (convention AGENTS.md § i18n, validée par `frontend/scripts/check-i18n.sh`).

## 7. Decisions locked at design time

| # | Décision | Justification |
|---|---|---|
| D1 | Le mockup est dans `(public)/[locale]/login/` (et `register/`), pas dans un nouveau `(auth)/` | Le `(public)/[locale]/layout.tsx` wrap déjà `<Header />` et `<NextIntlClientProvider />`. Créer un `(auth)/` au root forcerait à dupliquer le header OU à le ré-importer. **Minimal change pour s13** — le split `(auth)/` arrivera en s15+ si nécessaire. |
| D2 | Le `<Header>` bascule entre **input pseudo** (état actuel) et **avatar + menu** (état connecté) selon `useAuthStore.hydrated + accessToken` | Pas de breaking change pour les utilisateurs non connectés (l'input reste). Pas de nouveau composant `<Avatar>` (workaround inline, gap #1). |
| D3 | Le toggle `eye`/`eye-off` sur le password est **omis en s13** (YAGNI) | Le `<Input type="password">` natif suffit. Ré-évaluation en s22 si usage répété. |
| D4 | Le « menu » de l'avatar est un `<details>`/`<summary>` natif HTML | Pas de `<Popover>` dans le design system. Le natif est focusable et accessible par défaut. |
| D5 | Le bottom tab bar est **masquée** sur `/login` et `/register` | Cohérent avec « overlay plein écran » de l'architecture doc. Condition dans le composant : `if (pathname.endsWith('/login') \|\| pathname.endsWith('/register')) return null`. Vérifier que la tab bar existe (gap #8) avant de coder. |
| D6 | La redirection après login est `router.push(query.next ?? '/chat')` | Le `?next=` est l'URL de provenance, capturée par un `<Link href={{ pathname: '/login', query: { next: pathname } }}>` depuis les pages protégées (s15+) ou depuis le bouton « Se connecter » du header. En s13, le seul « protecteur » est le header lui-même. |
| D7 | Le 401 est rendu **identique** au « user not found » (Piège 6 research) | Conformité au design system `aria-invalid` + Card erreur. Le message est volontairement générique. |
| D8 | Les tokens sont stockés en `localStorage` (clé `ktutor.auth`) | Acceptable POC (ADR 005 § Considered options). Documenté comme dette s15+ (cookie HttpOnly). |
| D9 | L'écran `/register` est **créé en s13** (pas en s12) | s12 était backend-only, s13 introduit le premier frontend d'auth. C'est ici que le design system l'attend. |
| D10 | Le logout (D9 + Q4 research) **appelle un endpoint `POST /api/auth/logout`** qui blackliste le `jti` du access token | Plus robuste qu'un `clearTokens()` local. Le frontend vide `localStorage` immédiatement pour la réactivité, puis appelle l'endpoint en `fire-and-forget`. |

## 8. Liens

- `docs/research/s13-login-eleve.md` — 5 structuring facts, 18 traps, 6 OQ, files preview.
- `docs/designs/s12-creer-compte-eleve.md` § 4 — mapping des states backend (que s13 consomme).
- `docs/design-system.md` — tokens, composants, patterns (source unique).
- `docs/architecture.md` § Frontend — conventions App Router, `(public)/[locale]/` (réutilisé, pas créé), `authStore` extension.
- `docs/decisions/005-auth-rs256-rbac.md` — RS256, RBAC, claims, rotation, blacklist.
- `docs/decisions/011-frontend-pseudo-cookie-pre-jwt.md` — transition cookie → JWT (s13 = étape 1, s15 = étape 2).

---

**Statut** : design prêt (1 mockup HTML + ce document de référence). Mockup à utiliser comme **intention de layout**, jamais comme code à coller (cf. design-system § « Mockup status »).
