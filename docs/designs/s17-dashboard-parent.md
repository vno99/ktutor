# Design — Story s17-dashboard-parent

> Mockup statique HTML : `docs/designs/s17-dashboard-parent.html`. Référence visuelle, low-fidelity, **pas du code à copier**. L'implémentation réelle réutilise les composants du design system (`<Header>`, `<Card>`, `<LanguageSwitcher>`, `<Button>`) + la lib **Recharts** (déjà livrée en s16) pour le `<BarChart>`.
> Source unique de vérité visuelle : `docs/design-system.md`. Aucun token ou composant n'est inventé ici.
> Écrans conçus : **page liste `/dashboard/parent`** + **page child-detail `/dashboard/parent/[child_pseudo]`**, FR par défaut + EN, en mobile (360px) et tablette (768px+).
> Anchor points : `docs/research/s17-dashboard-parent.md` (5 faits structurants, 10 OQ, complexité re-scorée 3, point chaud = refactor `readOnly`).

## 1. Objectif et contexte

**Story** : s17-dashboard-parent — introduit la **vue lecture seule du dashboard eleve pour les parents** + la page liste des enfants liés. Le parent suit la progression de ses enfants sans pouvoir la modifier.

**Arbitrages de la recherche (à acter en plan)** :
- **Refactor `readOnly` prop** sur `DashboardClient` s16 (option a, plus chirurgicale que l'option b extraction `<DashboardView>`). Justification : `DashboardClient` est déjà self-contained, ajouter une prop booléenne est 5 lignes de diff + masquer 2 boutons. Extraire un composant partagé ajouterait 2 fichiers (le view + un wrapper eleve), soit ~80 lignes de refactor, sans gain de surface API (les deux écrans s16 et s17 appellent le même composant de toute façon).
- **Cache partagé eleve/parent** : `dashboard:eleve:{child_pseudo}` est réutilisé tel quel (cf. recherche Piège n°3 — l'invalidation est par `pseudo` enfant, donc l'eleve qui soumet un Attempt invalide son cache, le parent en bénéficie).
- **Endpoint unique `GET /api/dashboard/parent`** (option a, recherche n°5) qui agrège les dashboards en 1 requête. Évite le N+1.
- **Helper `assert_parent_linked_to_child_or_403`** ajouté à `backend/app/core/auth/middleware.py`, aligné sur le pattern s15.
- **RBAC endpoint** : `require_role(["parent", "admin"])` sur `/api/dashboard/parent` (un eleve qui hit cet endpoint reçoit 403).
- **Header post-JWT** : la nav `(dashboard)/[locale]/layout.tsx` est partagée entre s16 (eleve) et s17 (parent). Le lien actif est calculé à partir de `useAuthStore.role`. Cf. § 4.1.

**Anchor points** :
- Contrat API : `GET /api/dashboard/parent` (s17, à créer) — JWT auth, retour 200 avec `{ children: [{ pseudo, linked_at, dashboard: EleveDashboardResponse }] }`.
- Helper auth : `assert_parent_linked_to_child_or_403(user, claimed_child_pseudo, route=...)` (s17, à créer dans `backend/app/core/auth/middleware.py`).
- Schéma Pydantic : nouveau `ParentDashboardResponse` + `ChildDashboardEntry` qui wrappe `EleveDashboardResponse` + `linked_at` (date de liaison parent↔enfant).
- Multi-tenancy : filtrage `WHERE parent_pseudo = :user.pseudo` (extrait du JWT) sur `ParentChildLink`, puis itération sur les `child_pseudo` liés.
- Composants à réutiliser : `<Header>` (réactivé), `<LanguageSwitcher>`, `<Card>` (+ `Card.Header` / `Card.Body` / `Card.Footer`), `<Button>`, `<Card>` (pour les Child cards de la liste).
- **Réutilisé de s16** : `DashboardClient` (avec nouvelle prop `readOnly: boolean`).
- Icônes **Lucide** : `users` (page liste), `user` (card enfant), `book-open` (matière), `bar-chart-3` (chart), `trending-up`/`trending-down` (indicateurs), `refresh-cw` (rafraîchir), `arrow-right` (chevron card → détail), `alert-triangle` (erreur), `inbox` (empty state), `info` (info-bulles), `eye` (icône « lecture seule » sur le header de la child-detail).

**Hors-scope explicite** :
- **Écriture** (le parent ne peut PAS soumettre d'attempt, générer d'exercice, uploader de document) — l'AC #6 le garantit. Tous les boutons d'action edit/write sont absents (cf. § 6 readOnly).
- **Notifications parent** (« alice a tenté un nouvel exercice ») → gap s25, hors-scope.
- **Filtre par matière côté frontend** → gap s22.
- **Graphique de progression temporelle** (line chart) → gap s18/s22.
- **« Voir ce que mon enfant voit exactement »** (toggle de perspective) → hors-scope, le parent a sa propre vue, alignée mais distincte.
- **Avatar avec hash de pseudo** → gap design-system l.232 (s17 a été identifié comme résolveur potentiel, mais c'est optionnel ici — on garde l'avatar monochrome s16).
- **Page de profil parent** → hors-scope s17, gap s19+.
- **Filtre/tri des enfants** (alphabétique / dernière activité) → gap s22, hors-scope POC.
- **Pull-to-refresh mobile** → gap s22, le bouton Rafraîchir suffit pour la POC.

## 2. Composants du design system réutilisés

| Composant | Page | Source / rôle |
|---|---|---|
| `<Header>` (réactivé avec nav post-JWT) | Layout `(dashboard)/[locale]/layout.tsx` (mutualisé s16+s17) | `frontend/components/Header.tsx:23-139` — lien actif calculé via `useAuthStore.role` (`eleve` → `/dashboard/eleve`, `parent` → `/dashboard/parent`). Avatar pseudo à droite. |
| `<LanguageSwitcher>` (FR/EN) | Header | design-system l.171 |
| `<Card>` (+ `Card.Header` / `Card.Body` / `Card.Footer`) | Child cards (liste), wrapper de `DashboardClient` | design-system l.159-162 |
| `<Button>` variants primary, secondary, ghost | Rafraîchir (parent + child-detail) | `frontend/components/Button.tsx` |
| Iconographie **Lucide** | `users` (titre liste), `user` (enfant), `book-open` (matière dans Subject card), `bar-chart-3` (chart), `trending-up`/`trending-down`, `refresh-cw`, `arrow-right` (chevron card), `alert-triangle` (erreur), `inbox` (empty), `info` (info-bulle « lecture seule »), `eye` (pastille read-only) | design-system l.113 — déjà installé en s11c |
| **Recharts `<BarChart>`** | Child-detail (réutilisé via `DashboardClient` avec `readOnly={true}`) | Livré s16, `frontend/package.json` |
| `<table>` sr-only (a11y) | Child-detail (réutilisé via `DashboardClient`) | Pattern s16, inline dans la page |

**Aucun composant partagé nouveau n'est créé en s17**. L'extension du design system est minime : on comble **2 gaps** identifiés par la recherche :
- **`Avatar` avec initiale + ring primary** (pastille read-only) → reste monochrome, on coche le gap en l'état (cf. `design-system.md:232`).
- **`<Table>` shared component** → reste inline (gap design-system l.235), pas le moment de factoriser.

## 3. Tokens utilisés (rappel exhaustif)

### Couleurs

Identiques à s16 (cf. `docs/designs/s16-dashboard-eleve.md:60-71`). S17 n'introduit pas de nouveau token. Le `readOnly` mode se signale par :

- **Pastille read-only** : `bg-primary/10 text-primary` (transparence 10 % sur primary), avec icône `eye` Lucide 16px + label « Vue parent — lecture seule » (`text-xs font-medium`). Token déjà supporté par le shell.
- **Hover card enfant** : `hover:border-primary/40` (subtil, conserve `border-border` au repos, indique la cliquabilité).
- **Pas de variant destructive** (le parent ne fait que lire, pas supprimer).

### Typographie

- `text-xs 12px` — pastille read-only, légendes, code erreur, méta dates.
- `text-sm 14px` — labels, méta, « 5 enfants liés », « Dernière activité il y a 3 jours ».
- `text-base 16px` — body, nom enfant dans la card.
- `text-lg 18px` — sous-titre (« Progression globale de l'élève »).
- `text-2xl 24px` — titre de page mobile.
- `text-3xl 30px` — titre de page tablette+, **valeur globale du dashboard** (« 75 % » dans la Summary card du child-detail, identique à s16).
- Line-height : `1.5` body, `1.2` headings, letter-spacing `-0.011em` sur `text-2xl`+.

### Espacement

- `gap-3` (12px) entre les Child cards.
- `gap-4` (16px) entre les sections de la page liste (titre / pastille read-only / cards).
- `px-4 py-4` mobile, `px-6 py-6` tablette.
- `p-4` (16px) padding Card (identique s16, les Child cards contiennent un résumé + chevron).

### Radius / Shadows

- `--radius-sm 6px` : pastille read-only, badges indicateurs.
- `--radius-md 8px` : cards.
- `shadow-kt-default` : Child cards, Summary/Subject cards (via DashboardClient).

## 4. Layout et structure

### 4.1. Structure de routes (extension de s16)

```
app/
├── (public)/
│   └── [locale]/
│       └── (déjà livré s11a-s11c)
└── (dashboard)/                        ← LIVRÉ s16
    └── [locale]/
        ├── layout.tsx                  ← <Header /> + auth guard (réutilisé tel quel, nav post-JWT conditionnelle par rôle)
        ├── eleve/
        │   └── dashboard/
        │       ├── page.tsx            ← LIVRÉ s16 (inchangé)
        │       └── DashboardClient.tsx ← LIVRÉ s16 + prop `readOnly: boolean` (nouveau)
        └── parent/                     ← NOUVEAU s17
            ├── page.tsx                ← Server entry (liste des enfants)
            ├── ParentListClient.tsx    ← 'use client' — liste des Child cards
            └── [child_pseudo]/
                ├── page.tsx            ← Server entry (child-detail)
                └── ParentChildClient.tsx ← 'use client' — wrappe <DashboardClient readOnly={true}>
```

**Layout `(dashboard)/[locale]/layout.tsx` (mutualisé s16+s17)** :
- Réplique la structure s16 (`<Header>` + auth guard + `<main>`).
- **Header dynamique par rôle** : `useAuthStore.role` est lu après hydration. Si `role === "eleve"`, le lien actif est `/dashboard/eleve` ; si `role === "parent"`, le lien actif est `/dashboard/parent`. L'autre lien est masqué. Pattern documenté dans s16 (`Header.tsx:23-139`, à étendre en s17 pour supporter le 2e rôle — 1 nav item par rôle suffit pour la POC).
- **Avatar commun** : `pseudo.charAt(0).toUpperCase()` à droite (parent ou eleve, peu importe — l'avatar montre l'identité du user connecté, pas son rôle).
- **Pseudo en cookie** : `useAuthStore.hydrate()` lit le cookie `pseudo` (cf. ADR 011).

### 4.2. Page liste `/dashboard/parent`

**Container** : `max-w-4xl mx-auto` (plus large que s16 `max-w-3xl` car on affiche une grille de Child cards 2 colonnes sur tablette, pas un Summary + Chart plein largeur). `px-4 md:px-6`, `py-4 md:py-6`.

**Sections** (de haut en bas) :

1. **Titre de page** (`text-2xl md:text-3xl font-semibold tracking-tight`) :
   - « Mes enfants » (FR) / « My children » (EN).
   - Sous-titre (`text-sm md:text-base text-text-secondary`) : « Suis la progression de chacun de tes enfants. » / « Track the progress of each of your children. ».

2. **Pastille read-only** (1 ligne, au-dessus de la grille, `self-start`) :
   - `<div>` `inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-primary/10 text-primary-strong text-xs font-medium` (cohérent avec les badges indicateurs s16, juste teinte primary ; le `text-primary-strong` au lieu de `text-primary` est un ajustement WCAG AA — `text-primary` sur `bg-primary/10` est borderline).
   - Contenu : icône `eye` Lucide 16px (`aria-hidden="true"`) + label « Vue parent — lecture seule » / « Parent view — read-only ».
   - `aria-label="Mode lecture seule : tu peux consulter les données de tes enfants mais pas les modifier."` (annonce screen reader du contexte).

3. **Grille de Child cards** (`grid grid-cols-1 md:grid-cols-2 gap-3`) :
   - Chaque Child card = `<a href={/${locale}/dashboard/parent/${child.pseudo}}>` stylé comme un `<Card>` (le lien englobe la card pour rendre toute la zone cliquable, hit area 44 px respectée). Au repos : `bg-surface border border-border rounded-md p-4 shadow-kt-default`. Hover : `hover:border-primary/40` (subtil), `transition-colors`.
   - Contenu de la card (flex row, gap-3) :
     - **Avatar à gauche** : `<div>` `w-10 h-10 rounded-full bg-primary/10 text-primary flex items-center justify-center text-base font-semibold` avec l'initiale du `child.pseudo` (`pseudo.charAt(0).toUpperCase()`). Fallback si vide : `?` Lucide 16px.
     - **Bloc central** (flex-1) :
       - Nom enfant (`text-base font-semibold text-text-primary`).
       - Pseudo en `text-xs text-text-secondary` sous le nom (utile si le parent a lié deux enfants dont les noms s'affichent pareil — rare mais explicite ; `text-text-secondary` au lieu de `text-text-tertiary` pour passer WCAG AA 4.5:1).
       - Méta : « Lié depuis le {date} » (`text-xs text-text-secondary`, formaté via `Intl.DateTimeFormat(locale, { dateStyle: 'medium' })`).
     - **Indicateur de progression** à droite (flex-col, items-end, gap-1) :
       - Valeur « 75 % » (`text-lg font-semibold text-text-primary`) si l'enfant a des tentatives, sinon « — » (`text-lg text-text-tertiary`).
       - Label « Taux de réussite » (`text-xs text-text-tertiary`).
       - Badge indicateur (mêmes règles que s16 : `bg-success/10` ≥ 70 %, `bg-warning/10` 40-70 %, `bg-error/10` < 40 %, `text-xs`). **Note implémentation** : le mockup HTML affichait `+4 pts` (delta de points du jour) dans le badge, mais le système de récompenses n'est pas encore branché (gap s25). L'implémentation s17 affiche le pourcentage arrondi (ex. `75 %`) comme contenu visible. Le badge garde le même code couleur et la même forme, seul le texte diffère.
     - **Chevron** (`arrow-right` Lucide 20px en `text-text-tertiary`) à l'extrême droite, indique la navigation.

4. **Empty state parent** (aucun enfant lié) :
   - `<Card>` `bg-surface border border-border rounded-md p-6 md:p-8 text-center flex flex-col items-center gap-3`.
   - Icône `users` Lucide 48px en `text-text-tertiary` (`aria-hidden="true"`).
   - « Aucun enfant lié à ton compte. » (`text-base md:text-lg font-semibold text-text-primary`).
   - « Demande à un administrateur de lier un enfant à ton compte pour suivre sa progression. » (`text-sm text-text-secondary`).
   - Pas de CTA (pas d'action user-side — c'est un workflow admin, gap à noter pour s26+).

5. **Bouton « Rafraîchir la liste »** (en bas, à droite, full-width mobile) :
   - `<Button variant="primary" size="md">` avec icône `refresh-cw` Lucide 20px à gauche du label « Rafraîchir la liste » (FR) / « Refresh list » (EN).
   - Déclenche un refetch via `apiClient.get('/api/dashboard/parent')`. État pendant le refresh : icône remplacée par `loader-2` Lucide 20px + `animate-spin`, label « Rafraîchissement… » / « Refreshing… ».
   - Identique au bouton Rafraîchir de s16, juste avec une autre i18n key.

### 4.3. Page child-detail `/dashboard/parent/[child_pseudo]`

**Container** : `max-w-3xl mx-auto` (réduit, identique à `/dashboard/eleve` car on rend le même DashboardClient). `px-4 md:px-6`, `py-4 md:py-6`.

**Sections** (de haut en bas) :

1. **Fil d'ariane (back link)** :
   - Lien `← Retour à la liste` (`text-sm text-text-secondary hover:text-primary` + icône `arrow-left` Lucide 16px) pointant vers `/${locale}/dashboard/parent`. Au-dessus du titre de page.

2. **Titre de page** (`text-2xl md:text-3xl font-semibold tracking-tight`) :
   - « Progression de {child_pseudo} » (FR) / « Progress of {child_pseudo} » (EN). Le `child_pseudo` est interpolé via `t.rich('titleWithChild', { child: child_pseudo })` (next-intl ICU MessageFormat).

3. **Pastille read-only** (identique à la page liste, juste au-dessus du DashboardClient) :
   - « Vue parent — lecture seule · {child_pseudo} » / « Parent view — read-only · {child_pseudo} ».
   - `aria-label` étendu avec le nom de l'enfant.

4. **Dashboard client en mode read-only** :
   - Réutilise `<DashboardClient readOnly={true} />` (s16) avec l'API `GET /api/dashboard/eleve?pseudo={child_pseudo}` (le backend accepte le `?pseudo=` via le helper s15 admin bypass, ici on l'utilise pour la lecture parent : un nouveau helper `assert_parent_linked_to_child_or_403` vérifie la liaison).
   - Le composant est rendu avec exactement la même UI que s16 (Summary card + Chart + Subject cards), mais **les boutons d'édition sont absents** (cf. § 6 readOnly).
   - Les **Subject cards** n'ont pas de bouton « Voir les détails » (déjà `aria-disabled` en s16, mais en s17 on supprime carrément l'élément du DOM — pas d'afford fantôme).
   - Le **bouton Rafraîchir** reste présent (le parent peut rafraîchir manuellement). Icône `refresh-cw` Lucide 20px + label « Rafraîchir » / « Refresh ».

5. **Empty state** (l'enfant n'a aucune tentative) :
   - Affiché par le `DashboardClient` interne (réutilisé) : « {child_pseudo} n'a pas encore tenté d'exercice. » (FR) / « {child_pseudo} hasn't tried any exercise yet. » (EN).
   - **Mais** : le **CTA « Aller au chat »** de l'empty state s16 est masqué (`readOnly` prop → ne pas afficher le bouton CTA, juste le message texte). Cf. § 6 readOnly.

6. **Error states** (identiques à s16, ré-utilisés via DashboardClient) :
   - 401 → « Session expirée. » + lien « Se reconnecter ».
   - 403 (helper `assert_parent_linked_to_child_or_403` rejette) → « Accès refusé. Cet enfant n'est pas lié à ton compte. » + code `forbidden` + bouton « Retour à la liste » (variante secondaire).
   - Erreur réseau → « Erreur réseau. » + bouton « Réessayer » (réutilisé de s16, le parent peut retry comme l'eleve).
   - 500 → « Erreur serveur. » + bouton « Réessayer ».

### 4.4. États (4 par écran + 1 chargement)

| État | Page | Déclencheur | Pattern |
|---|---|---|---|
| **Loading** (initial) | Liste | `useEffect` mount, `data === null && !error` | Texte centré « Chargement de tes enfants… » + icône `loader-2` Lucide 20px `animate-spin`. Pas un spinner plein écran (design-system l.155). |
| **Loading** (initial) | Child-detail | Identique | Texte « Chargement du tableau de bord de {child_pseudo}… ». |
| **Empty (aucun enfant lié)** | Liste | Réponse 200 mais `children.length === 0` | Card centrée avec icône `users` 48px + message + sous-message (cf. § 4.2). Pas de CTA. |
| **Empty (enfant sans tentative)** | Child-detail | `global.exercises_count === 0` | Affiché par `DashboardClient` interne (readOnly, sans CTA « Aller au chat »). |
| **Succès — 1+ enfants, avec data** | Liste | Réponse 200 | Grille de Child cards avec valeur globale + indicateur + chevron. |
| **Succès — 1+ enfants, sans data (pas encore tenté)** | Liste | Réponse 200, `subjects.length === 0` pour l'enfant | Child card affichée avec valeur « — » et label « Taux de réussite » + badge `bg-warning/10 text-warning` « Pas encore d'activité ». |
| **Error 401** | Les 2 | JWT expiré / invalide | Card erreur + lien « Se reconnecter » (identique s16). |
| **Error 403** (parent pas lié à l'enfant) | Child-detail | `assert_parent_linked_to_child_or_403` rejette | Card erreur + message « Accès refusé. Cet enfant n'est pas lié à ton compte. » + bouton « Retour à la liste ». |
| **Error 403** (role !== parent/admin) | Liste | `require_role(["parent", "admin"])` rejette | Card erreur + message « Accès refusé. Cette page est réservée aux parents. » + bouton « Retour à l'accueil ». |
| **Error réseau** | Les 2 | `apiClient.get` rejette | Card erreur + bouton « Réessayer » (réutilisé de s16). |
| **Error 500** | Les 2 | Backend renvoie 500 | Idem réseau avec message « Erreur serveur. ». |
| **Refresh en cours** | Les 2 | Bouton Rafraîchir cliqué | Bouton avec spinner + label changé, reste des sections inchangé. |

## 5. Responsive (360px smartphone + 768px tablette)

### 5.1. Mobile (≤ 768px)

- **Header** : 56px, logo + `<LanguageSwitcher>` + avatar. Lien actif visible selon rôle.
- **Container** : `px-4 py-4`, pas de `max-w-*` côté liste (le `max-w-4xl` est neutre à 360px), `max-w-3xl` côté child-detail.
- **Titre de page** : `text-2xl` (24px) sur les 2 pages.
- **Pastille read-only** : full-width inline, wrap autorisé si le label est long (FR + EN).
- **Grille Child cards (liste)** : `grid-cols-1` (stack vertical), pleine largeur chacune. Layout interne : avatar en haut à gauche, nom + pseudo en dessous, indicateur à droite (peut wrap si le `taux` est long).
- **Child-detail** : titre + pastille + DashboardClient (qui stack vertical : Summary / Chart / Subject cards, comme s16). Bouton Rafraîchir full-width.
- **Bouton « Rafraîchir la liste »** : full-width, hauteur 44px.
- **Touch targets** : 44×44 px partout (cards cliquables entières = hit area large, bouton Rafraîchir 44px).

### 5.2. Tablette+ (≥ 768px)

- **Header** : 56px, logo + `<LanguageSwitcher>` + lien actif + avatar.
- **Container** : `max-w-4xl mx-auto` (liste) ou `max-w-3xl mx-auto` (child-detail), `px-6 py-6`.
- **Titre de page** : `text-3xl` (30px).
- **Pastille read-only** : auto-width, alignée à gauche.
- **Grille Child cards (liste)** : `md:grid-cols-2` (row de 2). Si un seul enfant, la 2e colonne est vide (pas une card fantôme).
- **Child-detail** : DashboardClient rendu avec `md:flex-row` pour la Summary card, `md:grid-cols-2` pour les Subject cards (identique s16).
- **Bouton « Rafraîchir la liste »** : auto-width, aligné à droite.

### 5.3. Vérification

- Pas de scroll horizontal à 360px ni à 768px.
- Tous les touch targets ≥ 44×44 px.
- Test Playwright couvre les deux viewports (AC #2, #3).
- Le chart reste lisible à 360px (réutilisation s16, déjà validé).
- Les Child cards entières sont cliquables (hit area large) et ont un focus-visible primary ring.

## 6. Read-only — masquage des actions d'édition (AC #3, #6)

C'est **le point chaud de la story** (cf. recherche Piège n°1). Le `DashboardClient` s16 est self-contained et ne dépend pas d'un contexte. On lui ajoute **une prop `readOnly: boolean`**, et on wrappe chaque action d'édition par cette prop.

**Diff sur `DashboardClient.tsx` (s16 → s17)** :
- Ajout d'une prop `readOnly?: boolean` (défaut `false` pour ne pas casser s16).
- **Bouton « Rafraîchir les données » (l. 278)** : **toujours affiché**, parent ou pas. Le parent a aussi besoin de rafraîchir manuellement.
- **Bouton « Réessayer » dans l'Error card (l. 370)** : **affiché** même en readOnly. Une erreur réseau, c'est pareil pour l'eleve et le parent.
- **Empty state CTA « Aller au chat » (l. 395-400)** : **masqué en readOnly** (`{!readOnly && <a ...>}`). Le parent n'a pas de chat à ouvrir.
- **Bouton « Voir les détails » dans les Subject cards** (déjà `aria-disabled` en s16) : **élément supprimé du DOM en readOnly** (`{!readOnly && <Button ...>}`). Pas d'afford fantôme.

**Pas d'autre modification** : les Subject cards, le chart, la Summary card, le « Taux de réussite » label, les badges indicateurs — tout est identique. La seule différence visible est l'absence des 2 boutons (CTA empty + Voir détails).

**Refactor transversal minimal** : 5 lignes de diff dans `DashboardClient.tsx` + un type union `readOnly?: boolean` dans l'interface props. La story s16 reste cohérente (readOnly = false par défaut).

**Pourquoi pas extraire un `<DashboardView>` partagé** : cf. recherche arbitrage #1 + § 1 ci-dessus. L'option a est 5 lignes de diff, l'option b ajouterait ~80 lignes (le view + un wrapper eleve). L'option a est plus chirurgicale et garde la trace de l'usage (s16 vs s17) au même endroit.

**Alternatives écartées** :
- **Wrapper `<ReadOnlyDashboard>`** qui compose `DashboardClient` avec une copie de l'UI masquée — dupliquerait l'UI, source de drift.
- **CSS-only masquage** (`hidden readOnly:block readOnly:hidden` sur les boutons) — fonctionne mais ne supprime pas l'afford du DOM, les screen readers le voient toujours. Le masquage DOM est plus propre pour l'a11y.

## 7. Accessibilité (WCAG 2.1 A minimum)

- **Labels** : `<Label htmlFor="...">` sur les `<select>` (filtres futurs) et `<Label srOnly>` sur les `<table>` sr-only pour les nommer (réutilisé de s16).
- **Aria** :
  - `aria-label="Mode lecture seule : tu peux consulter les données de tes enfants mais pas les modifier."` sur la pastille read-only (annonce contexte aux screen readers).
  - `aria-live="polite"` sur la **Summary card** (héritée de `DashboardClient`).
  - `aria-busy="true"` sur la **page entière** pendant le refresh.
  - `aria-label="Accéder au tableau de bord de {child_pseudo}"` sur chaque Child card (la card est un `<a>`, le screen reader annonce la destination explicitement, pas juste « utilisateur 75 % »).
  - `aria-disabled` + `tabindex="-1"` sur les actions désactivées (héritées s16).
- **Doublon accessible du chart** : `<table>` sr-only (héritée s16).
- **Focus** : `:focus-visible` primary ring sur tous les éléments interactifs (cards, boutons, header). Le `<a>` Child card a un ring primary visible quand Tab le sélectionne.
- **Contraste** : identique s16. Le `text-primary-strong` sur `bg-primary/10` est validé visuellement (utilisé pour les badges indicateurs s16). L'ancien `text-primary` sur ce fond était borderline AA ; l'implémentation a été ajustée pour passer WCAG 2.1 niveau A 4.5:1.
- **Touch targets** : 44×44 px partout. Les Child cards entières sont cliquables (hit area > 44×44).
- **Keyboard** : Tab → Card1 → Card2 → ... → Bouton Rafraîchir. `<a>` Child card accessible au clavier, Enter suit le lien.
- **Reduced motion** : `prefers-reduced-motion: reduce` désactive `animate-spin` (héritée s16).
- **axe-core** : 0 violation `critical` / `serious` sur `/fr/dashboard/parent` et `/fr/dashboard/parent/<child_pseudo>`. Test dans le CI via `@axe-core/playwright` (ajout à `frontend/e2e/dashboard.spec.ts`).
- **Lighthouse a11y** : ≥ 90 sur les 2 URLs (assertion CI). **Nécessite d'étendre `lighthouserc.json`** avec `http://localhost:3000/fr/dashboard/parent` et `http://localhost:3000/fr/dashboard/parent/alice` au tableau `collect.url`.

## 8. i18n

- **Catalogues** : `frontend/messages/fr.json` (défaut) et `frontend/messages/en.json`. Le namespace `dashboard.parent` est créé par s17 avec **~25 clés** :
  - `dashboard.parent.listTitle` — « Mes enfants » / « My children »
  - `dashboard.parent.listSubtitle` — « Suis la progression de chacun de tes enfants. » / « Track the progress of each of your children. »
  - `dashboard.parent.readOnly` — « Vue parent — lecture seule » / « Parent view — read-only »
  - `dashboard.parent.readOnlyAria` — « Mode lecture seule : tu peux consulter les données de tes enfants mais pas les modifier. » / « Read-only mode: you can view your children's data but not modify it. »
  - `dashboard.parent.linkedSince` — « Lié depuis le {date} » / « Linked since {date} »
  - `dashboard.parent.successRate` — « Taux de réussite » / « Success rate » (réutilisé du namespace `dashboard.eleve` — déplacé ou dupliqué ? **Recommandation : dupliquer** pour garder chaque namespace autonome, 5 clés en commun, pas un coût.)
  - `dashboard.parent.noActivity` — « Pas encore d'activité » / « No activity yet »
  - `dashboard.parent.refreshList` — « Rafraîchir la liste » / « Refresh list »
  - `dashboard.parent.refreshingList` — « Rafraîchissement… » / « Refreshing… »
  - `dashboard.parent.emptyTitle` — « Aucun enfant lié à ton compte. » / « No children linked to your account. »
  - `dashboard.parent.emptySubtitle` — « Demande à un administrateur de lier un enfant à ton compte pour suivre sa progression. » / « Ask an administrator to link a child to your account to track their progress. »
  - `dashboard.parent.error403Role` — « Accès refusé. Cette page est réservée aux parents. » / « Access denied. This page is for parents only. »
  - `dashboard.parent.backHome` — « Retour à l'accueil » / « Back to home »
  - `dashboard.parent.backToList` — « Retour à la liste » / « Back to list »
  - `dashboard.parent.detailTitle` — « Progression de {child} » / « Progress of {child} » (`t.rich` avec interpolation)
  - `dashboard.parent.detailReadOnly` — « Vue parent — lecture seule · {child} » / « Parent view — read-only · {child} » (`t.rich`)
  - `dashboard.parent.cardAria` — « Accéder au tableau de bord de {child} » / « Go to {child}'s dashboard » (`t.rich`)
  - `dashboard.parent.detailNoActivity` — « {child} n'a pas encore tenté d'exercice. » / « {child} hasn't tried any exercise yet. » (`t.rich` — pas dans le DashboardClient car il ne sait pas qui est `child`, c'est la page parent qui wrappe et passe le texte via une prop — **ou** le DashboardClient reste générique et c'est le parent qui affiche son propre empty state par-dessus. **Recommandation : page parent wrappe le DashboardClient et override l'empty state via une prop, OU on accepte que le DashboardClient affiche son empty state générique « Tu n'as pas encore tenté d'exercice. » — la 2e option est plus simple**.)
  - `dashboard.parent.detail403` — « Accès refusé. Cet enfant n'est pas lié à ton compte. » / « Access denied. This child is not linked to your account. »
  - `dashboard.parent.loadingList` — « Chargement de tes enfants… » / « Loading your children… »
  - `dashboard.parent.loadingDetail` — « Chargement du tableau de bord de {child}… » / « Loading {child}'s dashboard… » (`t.rich`)
  - `dashboard.parent.refresh` — « Rafraîchir » / « Refresh » (réutilisé du namespace `dashboard.eleve.refresh` — **dupliquer** pour autonomie)
  - `dashboard.parent.refreshing` — « Rafraîchissement… » / « Refreshing… » (idem)
  - `dashboard.parent.retry` — « Réessayer » / « Retry » (idem)
- **Réutilisation** : les clés d'erreur 401/réseau/500 et les labels de la Summary card sont **réutilisés** depuis `dashboard.eleve.*` (cf. détail s16 § 7). Le `DashboardClient` reste tel quel — c'est la page parent qui injecte le namespace.
- **Pas de hardcoded strings** : `useTranslations('dashboard.parent')` partout dans `ParentListClient.tsx` et `ParentChildClient.tsx`. Vérifié par `frontend/scripts/check-i18n.sh`.
- **Format de date** : `Intl.DateTimeFormat(useLocale(), { dateStyle: 'medium' })` pour `linked_at`.
- **Format de pourcentage** : identique s16 (`Intl.NumberFormat` `style: 'percent'`, 0 décimales).

## 9. Mockup HTML

Le mockup statique est dans `docs/designs/s17-dashboard-parent.html`. Il illustre **6 états critiques** côte à côte sur grand écran, empilés sur mobile :

1. **Loading initial — page liste** (texte centré + spinner).
2. **Empty — aucun enfant lié** (Card centrée avec icône `users` 48px + message).
3. **Succès — 3 enfants liés** (grille 2 colonnes, chaque card avec valeur + indicateur + chevron).
4. **Loading — child-detail** (texte centré « Chargement du tableau de bord de alice… »).
5. **Child-detail read-only — 2 matières** (DashboardClient rendu avec `readOnly={true}`, donc sans CTA empty ni bouton « Voir les détails »).
6. **Error 403 — parent pas lié à l'enfant** (Card erreur + bouton « Retour à la liste »).
7. **Mobile 360px — page liste** (grille stack vertical, pastille read-only full-width).

Le mockup utilise **uniquement** des tokens CSS du design system (variables `--color-*`, classes Tailwind décrites dans `docs/design-system.md`). Les icônes Lucide sont inlinées en SVG. Le chart est **rendu en HTML/CSS** dans le mockup (pas de Recharts en runtime).

**Statut du mockup** : c'est une **référence** pour l'implémentation, pas du code à coller. Le code de production utilise les composants maison (`<Card>`, `<Button>`, `<Header>`) + Recharts + `<table>` sr-only inline + `<DashboardClient readOnly={true} />`.

## 10. Design system gaps (à noter pour follow-ups)

| Gap | Impact | Story qui le résoudra |
|---|---|---|
| Header `(dashboard)/` n'a pas de nav post-JWT active (s16 livré sans) | UX : le parent ne voit pas où il est dans la nav | **s17** (extension Header pour supporter 2 rôles, plan task) |
| Pas de `<Avatar>` avec hash de pseudo (variations de teinte) | UX : avatar monochrome | **s22** (s17 était candidat, écarté pour rester focus) |
| Pas de `<Table>` shared component | `<table>` sr-only inline (héritée s16) | **s22** |
| Pas de bottom tab bar (mobile) post-JWT | UX : pas de nav mobile entre eleve/parent | **s22** |
| Pas de toggle dark/light dans le header | Le shell supporte `data-theme` mais pas le toggle UI | **s22** |
| Pas de toast d'erreur refresh | UX : confirmation erreur refresh uniquement inline | **s25** |
| Pas de filtre par matière (frontend) | UX : toutes les matières affichées en même temps | **s22** |
| Pas de line chart de progression temporelle | UX : dashboard statique, pas d'évolution | **s18** ou s22 |
| Pas de pagination des enfants | OK pour POC (1-3 enfants par parent), bloquant à 10+ | **s22** ou quand une story ajoute une vue liste plus large |
| Pas de pull-to-refresh mobile | UX : refresh = bouton dédié uniquement | **s22** |
| Pas de filtre/tri des enfants (alphabétique, dernière activité) | UX : ordre serveur, figé | **s22** |
| Pas de notification parent (« alice a tenté un exercice ») | UX : parent doit refresh manuellement | **s25** |
| Pas de « Vue ce que mon enfant voit exactement » (toggle perspective) | UX : le parent a sa propre vue, alignée mais distincte | **s22** (ou hors-scope) |
| Empty state non illustré (svg) | Texuel uniquement | **s22** |
| `<html lang>` reste hardcodé à `fr` | Mineur | **s22** ou **s11b'** |
| Pas de gestion du cas « parent lié à un autre parent / un admin » (POC s14) | Edge case rare, dashboard vide pour l'enfant « admin » | **s22** (politique de rôle sur l'enfant) |

## 11. Liens

- `docs/stories.md:833-863` — story s17 (6 ACs, complexité déclarée 3, agentic notes, traps).
- `docs/research/s17-dashboard-parent.md` — recherche complète (5 faits structurants, 10 OQ, complexité re-scorée 3, split optionnel).
- `docs/design-system.md` — source unique de vérité visuelle (258 lignes).
- `docs/designs/s16-dashboard-eleve.md` — sibling story, DashboardClient + Recharts + Summary/Subject cards réutilisés tels quels (avec `readOnly={true}`).
- `backend/app/api/dashboard/eleve.py` (s16 livré) — `GET /api/dashboard/eleve` + `assert_jwt_pseudo_matches_or_403` (pattern à répliquer).
- `backend/app/api/dashboard/parent.py` (s17, à créer) — `GET /api/dashboard/parent` + nouveau helper `assert_parent_linked_to_child_or_403`.
- `backend/app/services/dashboard/aggregator.py` (s16 livré) — `aggregate_eleve_dashboard` (pure, réutilisé par s17).
- `backend/app/services/dashboard/cache.py` (s16 livré) — `dashboard:eleve:{pseudo}` (cache key réutilisée, partagée eleve/parent).
- `backend/app/core/auth/middleware.py:149-211` (s15 livré) — pattern `assert_jwt_pseudo_matches_or_403` (à répliquer pour `assert_parent_linked_to_child_or_403`).
- `backend/app/core/database/models.py:269-317` (s14 livré) — `ParentChildLink` (composite PK, FK CASCADE).
- `backend/app/api/users/router.py:559` (s14 livré) — `list_children` (pattern à répliquer pour l'agrégation parent).
- `frontend/app/(dashboard)/[locale]/dashboard/eleve/DashboardClient.tsx` (s16 livré) — composant à refactorer avec prop `readOnly: boolean`.
- `frontend/app/(dashboard)/[locale]/dashboard/eleve/page.tsx` (s16 livré) — server entry pattern à répliquer.
- `frontend/app/(dashboard)/[locale]/layout.tsx` (s16 livré) — auth guard + Header (mutualisé s16+s17, à étendre pour la nav par rôle).
- `frontend/components/Header.tsx:23-139` (s11a livré) — Header, à étendre pour la nav post-JWT par rôle.
- `frontend/messages/{fr,en}.json:42` — namespace `dashboard` (s16 a ajouté `dashboard.eleve.*`, s17 ajoute `dashboard.parent.*`).
- `frontend/lighthouserc.json:7-10` — à étendre avec `/fr/dashboard/parent` et `/fr/dashboard/parent/<child_pseudo>`.
- `AGENTS.md` § Frontend + Multi-tenancy — conventions obligatoires (i18n, a11y, isolation cross-tenant, RBAC).
- `ADR 006` (Next.js + Zustand + i18n) + `ADR 011` (pseudo cookie pré-JWT) + `ADR 005` (admin bypass JWT).
