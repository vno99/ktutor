# Design — Story s16-dashboard-eleve

> Mockup statique HTML : `docs/designs/s16-dashboard-eleve.html`. Référence visuelle, low-fidelity, **pas du code à copier**. L'implémentation réelle utilise les composants du design system (`<Header>`, `<Card>`, `<LanguageSwitcher>`, `<Button>`) + la lib **Recharts** pour le `<BarChart>`.
> Source unique de vérité visuelle : `docs/design-system.md`. Aucun token ou composant n'est inventé ici.
> Écran conçu : **page `/dashboard/eleve`** uniquement, FR par défaut + EN, en mobile (360px) et tablette (768px+).
> Anchor points : `docs/research/s16-dashboard-eleve.md` (3 prémisses à arbitrer, 8 faits structurants, 8 OQ, complexité re-scorée 4).

## 1. Objectif et contexte

**Story** : s16-dashboard-eleve — première story à introduire (a) le sous-domaine backend `app/api/dashboard/`, (b) la route group frontend `(dashboard)/`, et (c) la dépendance `recharts`. L'élève doit voir un dashboard récapitulatif de sa progression, agrégé par matière.

**Arbitrages de la recherche (à acter en plan)** :
- **`score_avg` → proxy `mean(Attempt.is_success)` × 100**, label UI **« Taux de réussite »** (pas « Score moyen », qui serait mensonger vu que la donnée stockée est un booléen).
- **`last_activity_at` → `MAX(attempts.submitted_at)`** joint à `exercises` filtré par `subject` et `student_pseudo`.
- **`exercises_count` → `COUNT(attempts.id)`** (= nombre de tentatives, pas d'exercices uniques).
- **Cache in-process** TTL 5 min + invalidation explicite sur nouvelle `Attempt` (filet de sécurité).
- **Admin bypass** : `?pseudo=...` autorisé via helper s15 (`assert_jwt_pseudo_matches_or_403`) — décision de la recherche, à acter en plan.

**Anchor points** :
- Contrat API : `GET /api/dashboard/eleve` (s16, à créer) — JWT auth, retour 200 avec `subjects: [...]` + `global: {...}`.
- Schéma Pydantic : `SubjectSummary { name, score_avg, exercises_count, last_activity_at }` + `GlobalSummary` + `EleveDashboardResponse`.
- Multi-tenancy : filtrage `WHERE student_pseudo = :pseudo` (extrait du JWT, jamais du body).
- Composants à réutiliser : `<Header>` (réactivé), `<LanguageSwitcher>`, `<Card>`, `<Button>`, `<Label>` (pour les `<table>` sr-only), `<Select>` (filtre matière — pas dans la story, gap). Icônes **Lucide** (déjà installé en s11c).
- **Nouveau** : `<BarChart>` via **Recharts** + `<table>` sr-only pour a11y (gap design-system l.235).
- Pattern page : répliquer `(public)/[locale]/chat/page.tsx:34-42` (server entry + client subcomponent + `dynamic = "force-dynamic"`).

**Hors-scope explicite** :
- « Time spent » (somme des durées de session login→logout) → recherche Piège n°6 (l'onglet peut rester ouvert). Non implémenté, label UI abandonné. **POC** : la story fournit `last_activity_at` qui est un proxy plus honnête.
- Multi-tenancy admin bypass via `?pseudo=...` → **dans le scope** (debug ops).
- Filtre par matière côté frontend → **out of scope v1** (la story affiche toutes les matières, futur gap design).
- Graphique de progression temporelle (line chart) → **out of scope v1**, gap à noter.
- Empty state illustré (svg) → gap design-system l.240, on reste textuel.
- Toast de succès « Dashboard mis à jour » → gap design-system l.231 (s25).
- Toggle dark/light dans le header → gap design-system l.238 (s22), le mockup supporte `prefers-color-scheme` mais le toggle UI n'est pas s16.
- Dashboard temps réel (WebSocket) → non, refresh à la demande + cache 5 min suffit.
- Pagination des matières → 2 matières maximum dans le périmètre POC (`Subject.MATHS`, `Subject.FRANCAIS`).

## 2. Composants du design system réutilisés

| Composant | Page | Source |
|---|---|---|
| `<Header>` (réactivé) | Layout `(dashboard)/[locale]/layout.tsx` | `frontend/components/Header.tsx:23-139` — lien `/dashboard/eleve` **désactivé** avec `aria-disabled="true"` (l'élève est déjà sur son dashboard), avatar pseudo à droite |
| `<LanguageSwitcher>` (FR/EN, cookie-backed) | Header | design-system l.171 |
| `<Card>` (composé : Card / Card.Header / Card.Body / Card.Footer) | Summary card global, Subject cards | design-system l.159-162 |
| `<Button>` variants primary, secondary, ghost | Rafraîchir, Voir les détails (futur), Réessayer | `frontend/components/Button.tsx` |
| `<Label>` (`htmlFor` sur les `<select>`/filtres) | Filtres futurs, table sr-only | `frontend/components/Label.tsx` |
| Iconographie **Lucide** | `refresh-cw` (bouton Rafraîchir), `trending-up` / `trending-down` (indicateurs de score), `bar-chart-3` (chart header), `check-circle-2` (succès), `clock` (last activity), `book-open` (subject), `alert-triangle` (erreur), `loader-2` (spinner refresh) | design-system l.113 — déjà installé en s11c |
| `<table>` natif + `sr-only` (a11y) | Doublon accessible du `<BarChart>` | **Nouveau pattern** documenté ici, pas un composant partagé — l'`<table>` reste inline dans la page |

**Aucun composant partagé nouveau n'est créé en s16**. L'extension du design system (gaps comblés : `<Chart>` non créé en shared component, juste usage direct de Recharts + `<table>` inline) est une décision pragmatique : Recharts n'a pas besoin d'un wrapper pour ce qu'on lui demande. La story s22 (UX pass) pourra factoriser un `<Chart>` partagé si d'autres stories en ont besoin.

**Nouvelle dépendance** : `recharts@^2.13.0` dans `frontend/package.json` (commit `pnpm add recharts`, lockfile régénéré).

## 3. Tokens utilisés (rappel exhaustif)

### Couleurs (light mode, défaut — dark via classe `dark:` que le shell supporte déjà)

| Token | Hex light | Usage dans le mockup |
|---|---|---|
| `--color-primary` | `#3D5AFE` | Focus ring, barres du chart (couleur unique), bouton primary (Rafraîchir), lien actif |
| `--color-primary-strong` | `#1E2A8A` | Logo "ktutor" (sur light), hover/active primary |
| `--color-canvas` | `#FAFBFC` | Fond `body` |
| `--color-surface` | `#FFFFFF` | Header, cards (Summary, Subject, table sr-only invisible) |
| `--color-surface-subtle` | `#F4F6FA` | Fond du chart container (Recharts `bg-surface-subtle`), hover bouton ghost |
| `--color-border` | `#E2E6EE` | Bordures input, cards, séparateur de la bottom tab bar, séparateur interne des Subject cards |
| `--color-text-primary` | `#0D0F14` | Texte principal, titre de page, valeurs du chart, "Taux de réussite : 75 %" |
| `--color-text-secondary` | `#5B6472` | Sous-titre, labels, "12 tentatives", "il y a 3 jours" |
| `--color-text-tertiary` | `#8B95A3` | Help text, légende du chart, "Dernière activité" label |
| `--color-success` | `#16A34A` | Indicateur `trending-up` (taux ≥ 70 %), accent "bon taux" dans les Subject cards, icône `check-circle-2` |
| `--color-warning` | `#D97706` | Indicateur `trending-up`/`trending-down` mitigé (taux entre 40 % et 70 %), `alert-triangle` empty/error |
| `--color-error` | `#DC2626` | Indicateur `trending-down` (taux < 40 %), Card erreur, message d'erreur |

### Couleurs du chart (Recharts)

Recharts consomme des couleurs par `fill` ou via `<Cell>`. Le mockup utilise **3 couleurs** dérivées des tokens :
- **Barre Maths** : `--color-primary` (matière principale par défaut, le chart est mono-couleur pour la POC).
- **Barre Français** : `--color-primary` (idem, pas de variation — la distinction Maths/Français passe par le label de l'axe X).
- **Grid lines** : `--color-border` (Recharts `<CartesianGrid stroke="var(--color-border)">`).
- **Texte des axes** : `--color-text-tertiary` (Recharts `<XAxis tick={{ fill: 'var(--color-text-tertiary)' }}>`).

L'idée : **un seul hue de barre** pour ne pas créer une légende couleur→matière qui mange de la place à 360px. La distinction Maths/Français passe par l'axe X (toujours visible, même en vertical) et par les Subject cards individuelles sous le chart. Si on veut un jour un gradient de couleur par matière, c'est un gap noté.

### Typographie

- Sans (UI) : **Inter** (fallback `system-ui, sans-serif`).
- Échelle :
  - `text-xs 12px` — légende chart, "Dernière activité" label, "il y a 3 jours", code erreur.
  - `text-sm 14px` — labels de Card, "12 tentatives", "Taux de réussite" label.
  - `text-base 16px` — body, message card, valeur "75 %" dans les Subject cards.
  - `text-2xl 24px` — titre de page mobile, **valeur globale** dans la Summary card ("69 %" en hero).
  - `text-3xl 30px` — titre de page tablette+.
- Line-height : `1.5` body, `1.2` headings, letter-spacing `-0.011em` sur `text-2xl`+ (donc le titre de page et la valeur globale du dashboard).

### Espacement (Tailwind scale)

- `gap-2` (8px) entre la valeur et le label dans une Subject card.
- `gap-3` (12px) entre les 3 Subject cards.
- `gap-4` (16px) entre les sections de la page (titre / summary / chart / subject cards).
- `px-4 py-4` mobile, `px-6 py-6` tablette.
- `p-4` (16px) padding Card (un peu plus généreux que les cards s11c p-3, car les Subject cards contiennent des données denses).
- `mt-2` (8px) marges internes dans une Subject card.

### Radius

- `--radius-sm 6px` : boutons, badges indicateurs (taux, dernière activité).
- `--radius-md 8px` : cards.
- `--radius-full 9999px` : avatar (Header).

### Shadows

- `shadow-kt-default` (cards standard : Summary, Subject).
- Pas d'ombre sur le chart container (le `bg-surface-subtle` + `border-border` suffit à le détacher visuellement).

## 4. Layout et structure

### 4.1. Structure de routes (réplique du pattern s11b, nouveau groupe `(dashboard)`)

```
app/
├── layout.tsx                          ← Root layout (data-theme, fonts, NextIntlClientProvider)
├── (public)/
│   └── [locale]/
│       ├── layout.tsx                  ← <Header /> + <main> (déjà livré s11a)
│       ├── page.tsx                    ← Home (déjà livré s11a)
│       ├── chat/                       ← (déjà livré s11b)
│       └── upload/                     ← (déjà livré s11c)
└── (dashboard)/                        ← NOUVEAU (s16)
    └── [locale]/
        ├── layout.tsx                  ← <Header /> + auth guard (redirect → /login si !isAuthenticated après hydration) + <main>
        └── eleve/
            └── dashboard/
                ├── page.tsx            ← Server entry (locale + metadata + initial fetch)
                └── DashboardClient.tsx ← 'use client' — gère loading/error/success, rend Summary + Chart + Subject cards
```

**Layout `(dashboard)/[locale]/layout.tsx`** (s16, nouveau) :
- Réplique la structure de `(public)/[locale]/layout.tsx` (`<Header>` + `<main>` + `<NextIntlClientProvider>`).
- Ajoute un `useEffect` qui appelle `useAuthStore.hydrate()` au mount, puis redirige vers `/(public)/[locale]/login?next=/dashboard/eleve` si `!isAuthenticated` après hydration.
- Pendant l'hydratation, affiche un placeholder (le `<Header>` + `<main>` vide, ou un état « chargement » léger — pas un spinner plein écran, design-system l.155).
- Réutilisable par s17 (parent), s18 (admin), etc. : le layout est générique, c'est la page qui détermine le rôle attendu.

**Header (réactivation des liens)** :
- `(public)/[locale]/layout.tsx` actuel a les liens `Chat` et `Upload` activés (s11c). s16 ne modifie pas le Header partagé — il y a une **vue Header par layout** : `(public)/layout.tsx` garde les liens pré-JWT, `(dashboard)/layout.tsx` a sa propre version avec les liens post-JWT (`Dashboard`, `Documents`, `Exercices`, `Logout`) à venir (s17, s18, s19).
- En s16, le header du layout `(dashboard)/` n'a que : logo + `<LanguageSwitcher>` + avatar (sans lien actif sur `/dashboard/eleve` — l'élève est déjà sur son dashboard, on l'indique visuellement par un border-bottom primary sur l'item correspondant à la nav, mais la nav n'existe pas encore en s16).
- Le pseudo est lu de `useAuthStore.pseudo` (hydraté en s15) et affiché dans l'avatar (`pseudo.charAt(0).toUpperCase()`).

### 4.2. Page `/dashboard/eleve`

**Container** : `max-w-3xl mx-auto`, `px-4 md:px-6`, `py-4 md:py-6`. Plus large que `max-w-2xl` (upload) car on a 3 Subject cards côte à côte sur tablette.

**Sections** (de haut en bas) :

1. **Titre de page** (`text-2xl md:text-3xl font-semibold tracking-tight`) : « Mon tableau de bord » (FR) / « My dashboard » (EN). Sous-titre optionnel (`text-sm md:text-base text-text-secondary`) : « Ta progression, par matière. » / « Your progress, by subject. ».

2. **Summary card globale** (1 card, pleine largeur) :
   - `<Card>` `bg-surface border border-border rounded-md p-4 md:p-6 shadow-kt-default`.
   - Layout : `flex flex-col md:flex-row md:items-center md:justify-between gap-4`.
   - **À gauche** (flex-1) :
     - Icône Lucide `bar-chart-3` 24px en `text-text-tertiary` (visuel statique, pas une action).
     - Titre : « Taux de réussite global » (`text-sm text-text-secondary`).
     - Valeur : **« 69 % »** en `text-2xl md:text-3xl font-semibold tracking-tight text-text-primary`.
     - Indicateur sous la valeur : `trending-up` Lucide 16px + `text-sm text-success` + « +4 pts ce mois-ci » (mockup, valeur statique pour la POC ; le calcul réel est out of scope v1).
   - **À droite** (auto-width) :
     - « 20 tentatives » (`text-sm text-text-secondary`).
     - « Dernière activité : 4 sept. 2026 à 08:22 » (`text-xs text-text-tertiary`, formaté via `Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeStyle: 'short' })`).

3. **Chart container** (1 card, pleine largeur) :
   - `<Card>` `bg-surface-subtle border border-border rounded-md p-4 md:p-6`.
   - Titre : « Taux de réussite par matière » (`text-base md:text-lg font-semibold text-text-primary`) avec icône `bar-chart-3` Lucide 16px en `text-text-tertiary` à gauche.
   - `<BarChart>` Recharts :
     - `data` = `[{ name: 'Maths', taux: 75 }, { name: 'Français', taux: 60 }]`.
     - `<CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />`.
     - `<XAxis dataKey="name" tick={{ fill: 'var(--color-text-tertiary)', fontSize: 12 }} />`.
     - `<YAxis domain={[0, 100]} tickFormatter={(v) => `${v}%`} tick={{ fill: 'var(--color-text-tertiary)', fontSize: 12 }} />`.
     - `<Tooltip content={<CustomTooltip />} />` (custom tooltip qui affiche « Maths : 75 % » au hover).
     - `<Bar dataKey="taux" fill="var(--color-primary)" radius={[4, 4, 0, 0]} />` (radius top pour adoucir les barres).
     - **`<Legend verticalAlign="bottom" wrapperStyle={{ fontSize: 12, color: 'var(--color-text-tertiary)' }} />`** (légende **en-dessous** du chart, requis par AC #3 pour le responsive 360px).
   - `<ResponsiveContainer width="100%" height={240}>` pour le scaling.
   - **`<table>` sr-only** (doublon accessible pour screen readers) : 1 table avec 3 colonnes (`Matière`, `Taux de réussite`, `Tentatives`) et 2 lignes (Maths, Français). Lisible par NVDA/JAWS, invisible à l'œil.

4. **Subject cards** (1 row de 2 cards sur tablette+, stack vertical sur mobile) :
   - Layout : `grid grid-cols-1 md:grid-cols-2 gap-3`.
   - Chaque Subject card = `<Card>` `bg-surface border border-border rounded-md p-4 shadow-kt-default`.
   - Contenu :
     - Header : icône `book-open` Lucide 20px en `text-primary` + nom de la matière (`text-base font-semibold text-text-primary`).
     - Valeur : « 75 % » en `text-2xl font-semibold tracking-tight text-text-primary`, label `text-sm text-text-secondary` « Taux de réussite ».
     - Indicateur : badge `rounded-full px-2 py-0.5` avec icône `trending-up` 12px + `text-xs` :
       - `bg-success/10 text-success` si taux ≥ 70 %.
       - `bg-warning/10 text-warning` si taux entre 40 % et 70 %.
       - `bg-error/10 text-error` si taux < 40 %.
     - Méta : « 12 tentatives » (`text-sm text-text-secondary`) + « Dernière activité : il y a 3 jours » (`text-xs text-text-tertiary`).
   - Action : `<Button variant="ghost" size="sm">` « Voir les détails » (futur lien vers l'historique par matière, **désactivé** en s16, `aria-disabled="true"` + `tabindex="-1"`).
   - Pas de card pour une matière sans tentative (filtrée à la source par l'API : `COUNT(attempts) > 0` par matière).

5. **Bouton « Rafraîchir »** (en bas, à droite, full-width mobile) :
   - `<Button variant="primary" size="md">` avec icône `refresh-cw` Lucide 20px à gauche du label « Rafraîchir les données » (FR) / « Refresh data » (EN).
   - Déclenche un `apiClient.get('/api/dashboard/eleve', { headers: { 'Cache-Control': 'no-cache' } })` (header pour forcer le bypass du cache backend, ou alors appel direct au service sans cache). État pendant le refresh : icône remplacée par `loader-2` Lucide 20px + `animate-spin`, label « Rafraîchissement… » (FR) / « Refreshing… » (EN).
   - **Cache invalidation** : le bouton appelle aussi un endpoint `POST /api/dashboard/eleve/invalidate` (admin/eleve self) qui vide la clé cache pour le pseudo courant. Pour la POC, l'AC #4 dit « cached for 5 minutes » et l'AC #1 dit « invalidated on each new attempt » — l'invalidation côté backend (sur nouvelle `Attempt`) est ce qui compte, le bouton « Rafraîchir » est un raccourci UX. **Recommandation** : pas d'endpoint invalidate exposé, le bouton fait juste un refetch (qui hit le cache ou l'attend 5 min, c'est OK pour la POC). Le `Cache-Control: no-cache` header force l'API à invalider localement. **Décision à acter en plan**.

### 4.3. États (4 par écran + 1 chargement)

| État | Déclencheur | Pattern |
|---|---|---|
| **Loading** (initial) | `useEffect` mount, `data === null && !error` | Summary card + chart + Subject cards rendus avec un **skeleton loader** (futur, gap design-system l.239). Pour la POC v1 : un texte centré « Chargement de ton tableau de bord… » (`text-sm text-text-secondary`) + icône `loader-2` Lucide 20px `animate-spin` centrée. Pas un spinner plein écran. |
| **Empty** | Réponse 200 mais `subjects.length === 0` (aucune matière avec tentative) | `<Card>` `bg-surface border border-border rounded-md p-6` centré : icône `book-open` Lucide 32px en `text-text-tertiary` + « Tu n'as pas encore tenté d'exercice. » (`text-base text-text-primary`) + « Commence par générer un exercice depuis l'onglet Chat. » (`text-sm text-text-secondary`) + `<Button variant="primary" size="md">` « Aller au chat » (lien vers `/chat`, futur gap design-system car `/chat` est public — pas de garde auth, **OK en s16**). Pas d'illustration svg (gap design-system l.240). |
| **Empty (réponse 0 attempt globale)** | `global.exercises_count === 0` | Idem empty ci-dessus (le dashboard entier est vide). |
| **Error 401** | JWT expiré / invalide | `<Card>` `bg-error/10 border border-error/30 rounded-md p-4` : icône `alert-triangle` Lucide 24px en `text-error` + « Session expirée. Reconnecte-toi. » (`text-base text-text-primary`) + code `unauthorized` en `text-xs text-text-tertiary` + `<Button variant="primary" size="md">` « Se reconnecter » (lien vers `/login?next=/dashboard/eleve`). |
| **Error 403** | `role !== eleve && role !== admin` (helper s15 refuse) | Idem 401 mais avec message « Accès refusé. » + code `forbidden`. |
| **Error réseau** | `apiClient.get` rejette avant HTTP | `<Card>` `bg-error/10 border border-error/30 rounded-md p-4` + icône `alert-triangle` + « Erreur réseau. Vérifie ta connexion. » + code `network_error` + `<Button variant="secondary" size="md">` « Réessayer ». |
| **Error 500** | Backend renvoie 500 | Idem réseau mais avec message « Erreur serveur. Réessaie dans quelques minutes. » + code `internal_error` + bouton « Réessayer ». |
| **Succès** (défaut) | Réponse 200 avec données | Rendu normal : Summary + Chart + Subject cards. |
| **Refresh en cours** | Bouton « Rafraîchir » cliqué, `isRefreshing === true` | Bouton avec spinner + label changé, reste des sections inchangé (pas de skeleton, on garde les données stale jusqu'à la nouvelle réponse). |

**Pas d'état « manual review »** — le dashboard ne déclenche pas d'OCR, c'est de l'agrégation SQL.

## 5. Responsive (360px smartphone + 768px tablette)

### 5.1. Mobile (≤ 768px)

- **Header** : 56px, logo + `<LanguageSwitcher>` + avatar. Liens desktop **masqués** (pas de nav post-JWT en s16). La bottom tab bar est un gap design-system l.232 — non livrée en s16 (out of scope, le dashboard est une page isolée pour la POC).
- **Container** : `px-4 py-4`, pas de `max-w-*` (le contenu occupe toute la largeur).
- **Titre de page** : `text-2xl` (24px).
- **Summary card** : layout **vertical** (`flex-col`), valeur globale en `text-2xl`, méta en dessous. Pas de `md:flex-row`.
- **Chart container** : pleine largeur, **hauteur fixe 240px** (Recharts `<ResponsiveContainer height={240}>`). Légende **en-dessous** du chart (AC #3 — `<Legend verticalAlign="bottom" />`). Tooltip au tap (Recharts gère). **Test critique** : à 360px, le chart doit afficher 2 barres Maths/Français sans scroll horizontal, les labels d'axe X lisibles.
- **Subject cards** : **stack vertical** (`grid-cols-1`), pleine largeur chacune. Icône + nom en haut, valeur + label, indicateur, méta. Bouton « Voir les détails » ghost full-width.
- **Bouton « Rafraîchir »** : full-width, hauteur 44px.
- **Touch targets** : 44×44 px minimum partout (boutons, avatar cliquable).

### 5.2. Tablette+ (≥ 768px)

- **Header** : 56px, logo + `<LanguageSwitcher>` + avatar. Liens desktop **masqués** (gap design-system l.232, nav post-JWT arrive en s17).
- **Container** : `max-w-3xl mx-auto`, `px-6 py-6`.
- **Titre de page** : `text-3xl` (30px).
- **Summary card** : layout **horizontal** (`md:flex-row md:items-center md:justify-between`), valeur globale en `text-3xl` (hero de la page).
- **Chart container** : pleine largeur dans le `max-w-3xl`, légende en-dessous. Hauteur 280px (`md:height={280}`).
- **Subject cards** : **row de 2** (`md:grid-cols-2`). Si une seule matière a des tentatives, l'autre colonne est vide (pas une card fantôme). Si zéro matière, l'empty state prend toute la largeur.
- **Bouton « Rafraîchir »** : auto-width, aligné à droite.

### 5.3. Vérification

- Pas de scroll horizontal à 360px ni à 768px.
- Tous les touch targets ≥ 44×44 px.
- Test Playwright couvre les deux viewports (AC #3).
- Le chart reste lisible à 360px : `ResponsiveContainer` scale, mais on garde `height={240}` pour la lisibilité (barres pas trop écrasées).
- La `<table>` sr-only est présente à toutes les viewports (elle est `sr-only`, donc invisible — mais elle scale le DOM, pas le rendu visuel).

## 6. Accessibilité (WCAG 2.1 A minimum)

- **Labels** : `<Label htmlFor="...">` sur les `<select>` (filtres futurs) et `<Label srOnly>` sur les `<table>` sr-only pour les nommer (`<table aria-labelledby="dashboard-table-caption">` + caption).
- **Aria** :
  - `aria-live="polite"` sur la **Summary card** (la valeur globale change après refresh).
  - `aria-busy="true"` sur la **page entière** pendant le refresh (info screen reader que le contenu se met à jour).
  - `aria-describedby="dashboard-last-updated"` lie la Summary card au texte « Dernière activité : 4 sept. 2026 à 08:22 ».
  - `aria-disabled="true"` + `tabindex="-1"` sur le bouton « Voir les détails » (futur, désactivé en s16).
  - `aria-label="Rafraîchir les données"` sur le bouton Rafraîchir (sinon NVDA lit « button » seul avec l'icône `refresh-cw`).
- **Doublon accessible du chart** : `<table>` sr-only avec `<caption>« Taux de réussite par matière (version accessible, équivalente au graphique) »` + `<thead>` + `<tbody>`. Recharts utilise `<svg>` qui est mal lu par les screen readers — cette table est la **source de vérité** pour les assistive technologies, le chart visuel est un enhancement. Pattern documenté par WAI-ARIA Authoring Practices pour `<figure>` et `<figcaption>`.
- **Focus** : `:focus-visible` sur tous les boutons (déjà géré par le design system). Le bouton Rafraîchir a un ring primary visible.
- **Contraste** : toutes les combinaisons `text-*` sur `bg-*` respectent AA. `text-success` sur `bg-success/10` est validé visuellement (le design system l'a documenté pour les cards s11c). `text-warning` sur `bg-warning/10` idem.
- **Touch targets** : 44×44 px partout.
- **Keyboard** : tout est navigable au Tab. Le bouton Rafraîchir est atteignable depuis le header (Tab navigation). Pas de `<div onClick>` (Piège n°11 recherche, design-system l.216).
- **Reduced motion** : `prefers-reduced-motion: reduce` désactive le `animate-spin` du spinner de refresh et du loader initial.
- **axe-core** : 0 violation `critical` / `serious` sur `/fr/dashboard/eleve` et `/en/dashboard/eleve`. Test dans le CI via `@axe-core/playwright` (ajout à `frontend/e2e/dashboard.spec.ts`).
- **Lighthouse a11y** : ≥ 90 sur `/fr/dashboard/eleve` (assertion CI). **Nécessite d'étendre `lighthouserc.json`** avec `http://localhost:3000/fr/dashboard/eleve` au tableau `collect.url`.

## 7. i18n

- **Catalogues** : `frontend/messages/fr.json` (défaut) et `frontend/messages/en.json`. Le namespace `dashboard` (vide en s16 avant la story) est rempli par s16 avec **~15 clés** :
  - `dashboard.eleve.title` — « Mon tableau de bord » / « My dashboard »
  - `dashboard.eleve.subtitle` — « Ta progression, par matière. » / « Your progress, by subject. »
  - `dashboard.eleve.globalRate` — « Taux de réussite global » / « Overall success rate »
  - `dashboard.eleve.trend` — « +4 pts ce mois-ci » / « +4 pts this month » (mockup statique, futur calculé)
  - `dashboard.eleve.attempts` — `{count} tentatives` (paramétré, plurals : `tentative` / `tentatives` en FR, `attempt` / `attempts` en EN via `useTranslations` plural rules)
  - `dashboard.eleve.lastActivity` — « Dernière activité : {date} » / « Last activity: {date} »
  - `dashboard.eleve.chartTitle` — « Taux de réussite par matière » / « Success rate by subject »
  - `dashboard.eleve.chartLegend` — « Taux de réussite (%) » / « Success rate (%) » (axe Y)
  - `dashboard.eleve.tableCaption` — « Taux de réussite par matière (version accessible, équivalente au graphique) » / idem EN
  - `dashboard.eleve.subjectRate` — « Taux de réussite » / « Success rate »
  - `dashboard.eleve.seeDetails` — « Voir les détails » / « See details »
  - `dashboard.eleve.refresh` — « Rafraîchir les données » / « Refresh data »
  - `dashboard.eleve.refreshing` — « Rafraîchissement… » / « Refreshing… »
  - `dashboard.eleve.empty` — « Tu n'as pas encore tenté d'exercice. » / « You haven't tried any exercise yet. »
  - `dashboard.eleve.emptyCta` — « Commence par générer un exercice depuis l'onglet Chat. » / « Start by generating an exercise from the Chat tab. »
  - `dashboard.eleve.emptyButton` — « Aller au chat » / « Go to chat »
  - `dashboard.eleve.error401` — « Session expirée. Reconnecte-toi. » / « Session expired. Please log in again. »
  - `dashboard.eleve.error403` — « Accès refusé. » / « Access denied. »
  - `dashboard.eleve.errorNetwork` — « Erreur réseau. Vérifie ta connexion. » / « Network error. Check your connection. »
  - `dashboard.eleve.error500` — « Erreur serveur. Réessaie dans quelques minutes. » / « Server error. Please try again in a few minutes. »
  - `dashboard.eleve.retry` — « Réessayer » / « Retry »
  - `dashboard.eleve.reconnect` — « Se reconnecter » / « Log in again »
  - `dashboard.eleve.loading` — « Chargement de ton tableau de bord… » / « Loading your dashboard… »
- **Pas de hardcoded strings** : `useTranslations('dashboard.eleve')` partout dans `DashboardClient.tsx`. Vérifié par `frontend/scripts/check-i18n.sh` (exit 0 obligatoire en CI).
- **Format de date** : `Intl.DateTimeFormat(useLocale(), { dateStyle: 'medium', timeStyle: 'short' })` pour `last_activity_at` (cf. design-system l.198).
- **Format de pourcentage** : `Intl.NumberFormat(useLocale(), { style: 'percent', maximumFractionDigits: 0 })` (0 décimales, arrondi à l'unité — un dashboard qui affiche 74,83 % est trop précis, on reste sur 75 %).
- **Plurals** : `useTranslations` gère les plurals via `t.rich('attempts', { count })` (next-intl ICU MessageFormat).
- **Toggle FR/EN** : `<LanguageSwitcher>` (déjà livré s11a) persiste le choix via cookie `NEXT_LOCALE`. La page dashboard est re-rendue automatiquement par next-intl middleware.

## 8. Mockup HTML

Le mockup statique est dans `docs/designs/s16-dashboard-eleve.html`. Il illustre **5 états critiques** côte à côte sur grand écran, empilés sur mobile :

1. **Loading** (état initial, skeleton ou texte centré + spinner).
2. **Empty** (aucune tentative, message d'accueil + CTA vers `/chat`).
3. **Succès — 2 matières** (Maths 75 %, Français 60 % — chart + Subject cards).
4. **Succès — 1 matière** (Maths 75 %, Français absent — chart avec 1 barre, 1 Subject card).
5. **Error réseau** (Card erreur + bouton « Réessayer »).
6. **Mobile 360px** (chart avec légende en-dessous, Subject cards stackées, bouton Rafraîchir full-width).

Le mockup utilise **uniquement** des tokens CSS du design system (variables `--color-*`, classes Tailwind décrites dans `docs/design-system.md`). Les icônes Lucide sont inlinées en SVG (la lib `lucide-react` est déjà installée depuis s11c). Le chart est **rendu en HTML/CSS** dans le mockup (pas de Recharts en runtime) — des `<div>` stylés simulent les barres Recharts pour la lisibilité du mockup. **L'implémentation réelle utilise `<BarChart>` Recharts** (cf. § 4.2).

**Statut du mockup** : c'est une **référence** pour l'implémentation, pas du code à coller. Le code de production utilise les composants maison (`<Card>`, `<Button>`, `<Header>`) + Recharts + `<table>` sr-only inline.

## 9. Design system gaps (à noter pour follow-ups)

| Gap | Impact | Story qui le résoudra |
|---|---|---|
| `recharts` n'est pas installé dans `package.json` (alors que la design system l'attend pour s16) | Implémentation impossible sans commit de dépendance | **s16** (commit `pnpm add recharts` + lockfile, plan task) |
| Pas de `<Chart>` shared component | Recharts utilisé directement dans la page | **s22** (factorisation si d'autres stories ont besoin de charts) |
| Pas de `<Skeleton>` loader | UX : pas de feedback de chargement, juste un texte + spinner | **s22** |
| Pas de `<Table>` shared component | `<table>` sr-only inline dans la page | **s17** (parent dashboard liste enfants) ou s22 (factorisation) |
| Pas de bottom tab bar (mobile) post-JWT | Navigation mobile du dashboard limitée au bouton Rafraîchir | **s17** ou **s22** |
| Pas de toggle dark/light dans le header | Le shell supporte `data-theme` mais le toggle UI n'est pas là | **s16** ou **s22** (recherche dit « s16 », décision à acter ; recommandation : out of scope, **s22**) |
| Pas de toast d'erreur refresh | UX : confirmation erreur refresh uniquement inline | **s25** (toasts) |
| Pas de filtre par matière (frontend) | UX : toutes les matières affichées en même temps | **s22** (filtre) ou **s17** (parent dashboard) |
| Pas de line chart de progression temporelle | UX : dashboard statique, pas d'évolution | **s18** (evaluations) ou s22 (factorisation) |
| Pas de pagination des matières | OK pour POC (2 matières), bloquant à 5+ | **s22** ou quand une story ajoute des matières |
| `output: "standalone"` omis dans `next.config.ts` | EPERM Windows, Lighthouse peut demander la refacto | suivi s11b si Lighthouse en prod le demande |
| `<html lang>` reste hardcodé à `fr` | Mineur, hors-scope s16 | **s22** ou **s11b'** |
| Avatar monochrome (pas de hash de pseudo) | Avatar à une seule teinte | **s17** (parent dashboard) ou s22 |
| Empty state non illustré (svg) | Texuel uniquement | **s22** |
| `+4 pts ce mois-ci` (indicateur de tendance) mockup statique | Calcul réel non implémenté | **s18** (evaluations) ou s22 (rétrofit métriques) |

## 10. Liens

- `docs/stories.md:799-830` — story s16 (6 ACs, complexité déclarée 3, agentic notes, traps).
- `docs/research/s16-dashboard-eleve.md` — recherche complète (3 prémisses fausses, 8 faits structurants, 8 OQ, complexité re-scorée 4, split optionnel).
- `docs/design-system.md` — source unique de vérité visuelle (258 lignes).
- `docs/designs/s11c-frontend-upload.md:255-265` — pattern page server entry + client subcomponent à répliquer.
- `docs/designs/s11b-frontend-chat.md` — sibling story, server component avec fetch initial.
- `backend/app/api/dashboard/eleve.py` (à créer) — router `GET /api/dashboard/eleve` avec `Depends(get_current_user)` + `require_role(["eleve"])`.
- `backend/app/services/dashboard/aggregator.py` (à créer) — `aggregate_eleven_dashboard(db, pseudo) -> EleveDashboardResponse`.
- `backend/app/services/dashboard/cache.py` (à créer) — cache in-process TTL 5 min + invalidation explicite.
- `backend/app/core/auth/middleware.py:58-135` — `get_current_user`, `require_role` (livré s13/s13b).
- `backend/app/core/database/models.py:101-207` — `Exercise`, `Attempt` (modèles existants).
- `frontend/lib/api.ts:128-135` — interceptor `Authorization: Bearer` (livré s13).
- `frontend/lib/stores/authStore.ts:75-103` — `isAuthenticated`, `role` (livré s13).
- `frontend/components/Header.tsx:23-139` — à étendre ou répliquer pour le layout `(dashboard)/`.
- `frontend/app/(public)/[locale]/chat/page.tsx:34-42` — pattern server entry à répliquer.
- `frontend/messages/{fr,en}.json:42` — namespace `dashboard` vide à remplir.
- `frontend/package.json` — à étendre avec `recharts@^2.13.0` (commande `pnpm add recharts`).
- `frontend/lighthouserc.json:7-10` — à étendre avec `/fr/dashboard/eleve`.
- `AGENTS.md` § Frontend + Multi-tenancy — conventions obligatoires.
- `ADR 006` (Next.js + Zustand + i18n) + `ADR 011` (pseudo cookie pré-JWT) + `ADR 005` (admin bypass JWT).
