# Design — Story s19-historique-conversations

> Source de vérité visuelle : `docs/design-system.md`. Mockup HTML : `docs/designs/s19-historique-conversations.html` (référence, pas code à copier — l'Execute construit avec les vrais composants).

## Screen(s)

L'écran de la story s19 se décompose en **deux pages**, conformément à l'AC4 (« the `/history` page lists the conversations and clicking one opens the detail »). Les deux pages vivent sous `(dashboard)/[locale]/history/...` (JWT guard, portée post-s15) :

1. **Page liste** : `/(dashboard)/[locale]/history/page.tsx` — la conversation de l'élève, groupée par matière, la plus récente en haut.
2. **Page détail** : `/(dashboard)/[locale]/history/[conversation_id]/page.tsx` — le fil complet des messages d'une conversation, avec ses sources RAG.

### 1. Page liste — `/history`

**Layout** :

- `<Header>` sticky 56 px (logo + LanguageSwitcher + pseudo + avatar) — déjà livré par s11a.
- Bottom tab bar mobile sticky 64 px (chat / upload / history / dashboard) — déjà livré par s11a. L'onglet actif = « history », `aria-current="page"`.
- Titre de page : `<h1>` « Mes conversations » (`text-2xl font-semibold tracking-tight`).
- Sélecteur de matière : `<Select>` (maths / français / toutes) au-dessus de la liste, aligné à droite desktop, pleine largeur mobile.
- **Liste de cards** : une `<Card>` par conversation, empilées verticalement avec un gap de 12 px. Chaque card est cliquable (entière, `<Link>` enveloppant le contenu), affiche :
  - **Matière** : badge pill colorée à gauche (maths = `--color-primary`, français = `--color-accent-warm`, cf. gap ci-dessous).
  - **`first_question`** : tronquée à 80 caractères, `text-base text-text-primary line-clamp-2` (overflow visible sur 2 lignes max).
  - **Méta** : `message_count` (« 12 messages »), `last_activity_at` formatée en relatif (« il y a 2 h », « hier », « 12 sept. »).
  - **Indicateur de fin** : chevron-right Lucide 20 px, `text-text-tertiary`.
- **Pagination** : 2 boutons « Précédent » / « Suivant » en bas (alignés horizontalement, full-width sur mobile, inline sur tablette+). Désactivés aux extrémités. `aria-label` explicites.
- **Empty state** : si l'élève n'a aucune conversation, message centré « Tu n'as pas encore posé de question. » + lien CTA « Démarrer une conversation → » vers `/chat`.

**Responsive** :
- Mobile (≤ 768 px) : `px-4 py-4`, cards full-width, sélecteur de matière `w-full`, pagination en colonne (`flex-col gap-2`).
- Tablette+ (≥ 768 px) : `max-w-3xl mx-auto px-6 py-8`, cards en pleine largeur du conteneur, sélecteur à droite (`w-48`), pagination en ligne (`flex-row justify-between`).

**Couleurs des badges matière** : on réutilise `--color-primary` (maths) et `--color-accent-warm` (français) — tokens déjà définis. Pas de nouveau token.

### 2. Page détail — `/history/[conversation_id]`

**Layout** :

- `<Header>` + bottom tab bar (active = « history »).
- **Bouton retour** : `<Button variant="ghost" size="sm">` avec icône `arrow-left` Lucide 20 px, en haut à gauche, `aria-label="Retour à l'historique"`. Cliquer = retour à `/history` (préserve la pagination si possible, sinon page 1).
- **En-tête de conversation** : `<Card.Header>` avec :
  - **Matière** (badge pill, même styling que la liste).
  - **`first_question`** complète (`text-lg font-medium`).
  - **Méta** : `message_count` + `last_activity_at` (`text-sm text-text-secondary`).
- **Fil de messages** : rendu vertical, full-width. Chaque message est un bloc :
  - **Message user** (rôle = « user ») : `<Card>` `bg-surface-subtle`, aligné à droite, `max-w-2xl ml-auto`, padding `px-4 py-3`, `rounded-md`.
  - **Message assistant** (rôle = « assistant ») : `<Card>` `bg-surface` avec bordure gauche `border-l-4 border-primary`, `max-w-2xl`, padding `px-4 py-3`, `rounded-md`. **Le contenu est rendu en `text-base`** (markdown léger autorisé, mais pas de HTML brut). En dessous du contenu, si `sources` non vide : liste de pills compactes `text-xs text-text-secondary` avec icône `file-text` Lucide 16 px + `filename:chunk_index` (ex. « cours-derivees.pdf:3 »). Cliquer une pill = ouvre le document côté `/documents/...` (hors-scope s19, mais l'afford est là, le lien est préparé en ADR pour s22).
- **Empty state** : impossible (si l'ID existe, il y a au moins un message user + un assistant). Si 404 : message d'erreur « Conversation introuvable » + bouton retour.

**Responsive** : identique à la liste.

## Mockup

`docs/designs/s19-historique-conversations.html` — mockup statique low-fi, en deux sections (liste + détail), responsive 360 px et 768 px. Construit **uniquement** avec les tokens listés dans `docs/design-system.md`. But : montrer layout, états (default / empty), et la hiérarchie visuelle — pas d'être du code production.

## Reused components (from the design system)

| Composant | Usage |
|---|---|
| `<Header>` | Header sticky 56 px, livré par s11a, réutilisé tel quel |
| `<Button>` | Bouton retour détail + boutons pagination, `variant="ghost" \| "secondary"`, `size="sm" \| "md"` |
| `<Card>` + `Card.Header` / `Card.Body` / `Card.Footer` | Chaque conversation en liste + blocs message en détail + header conversation |
| `<Select>` | Filtre matière (option : « Toutes / Maths / Français ») |
| Bottom tab bar | Mobile sticky, livré par s11a, l'entrée « history » reçoit `aria-current="page"` |
| Icônes Lucide | `arrow-left` (retour), `chevron-right` (fin de card), `file-text` (source), `message-circle` (badge matière, optionnel — peut être juste la couleur) |
| `useTranslations('history')` | Toutes les chaînes UI : titre, labels, empty, pagination, badges |
| `Intl.DateTimeFormat` / `Intl.RelativeTimeFormat` | Format des dates relatives (cf. design-system § i18n) |

## States

### Page liste

| État | Pattern |
|---|---|
| **Loading** | Pas de skeleton (gap design-system). `aria-busy="true"` sur la `<ul>` pendant le fetch. Le store démarre vide → page rend la structure immédiatement. |
| **Empty** | Card centrée `bg-surface border border-border` avec message + CTA « Démarrer une conversation » (lien vers `/chat`). |
| **Erreur réseau** | `<Card>` `bg-error/10 border-error/30` avec icône `alert-triangle` + message + bouton « Réessayer » (`onClick` re-tente le fetch). Cf. design-system § « Feedback ». |
| **403** (cross-tenant) | Théoriquement impossible si le filtre est bon, mais prévoir une `<Card>` erreur si le backend renvoie 403 (defense in depth). |
| **Pagination active** | Bouton « Précédent » / « Suivant » enabled si `offset > 0` / `offset + limit < total`. Désactivés = `aria-disabled="true" tabindex="-1"` (cf. design-system « boutons désactivés »). |

### Page détail

| État | Pattern |
|---|---|
| **Loading** | Idem liste. |
| **Conversation absente (404)** | Card erreur « Conversation introuvable » + bouton retour. |
| **Erreur réseau** | Idem liste. |
| **403 cross-tenant** | Idem — redirige ou affiche une erreur. (Le backend ne devrait pas renvoyer 403 si l'élève est propriétaire, mais un parent lié appelle la conversation d'un enfant ≠ → 403 attendu → message « Tu n'as pas accès à cette conversation ».) |
| **Sources absentes** | Pas de liste de pills sous le message assistant — c'est un cas normal (réponse RAG sans citation, fallback no-document). |

## Design system gaps

Tous les composants nécessaires sont déjà dans le design system. Trois points qui restent à clarifier (pas d'invention ici) :

1. **Pas de composant `<Badge>` / `<Pill>`** : la liste des sources et les badges matière (« maths », « français ») sont des pills. Le design-system l'utilise déjà implicitement dans s11c (cf. design system ligne 113 pour les icônes, ligne 138 pour `<LanguageSwitcher>`) mais ne l'expose pas comme composant nommé. Pour s19, on utilise un simple `<span>` stylé (`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium`) **inline dans la page**, sans créer de nouveau composant partagé. **À documenter en gap design-system** : un `<Badge>` partagé sera peut-être créé en s22. (Sinon, à chaque story on réinvente la pill, c'est de la dette.)
2. **Pas de composant `<RelativeTime>`** : la `last_activity_at` doit être affichée en relatif (« il y a 2 h », « hier », « 12 sept. »). Le design-system mentionne `Intl.DateTimeFormat` mais pas le format relatif. Pour s19, on utilise `Intl.RelativeTimeFormat(locale, { numeric: 'auto' })` **inline dans la page** (helper de 10 lignes), sans nouveau composant. Même logique : à s22, extraire en `<RelativeTime>` partagé si 3+ stories s'en servent.
3. **Pas de bottom tab bar avec 5 entrées** : la bottom tab bar actuelle (s11a) a 4 entrées : chat / upload / exercises (placeholder) / dashboard. Il faut y ajouter **history**. Vérifier que l'implémentation actuelle de la tab bar accepte une 5e entrée (s11a l'a peut-être figée à 4). Si non, c'est un quick fix d'une ligne — pas un gap de design system, juste un test à faire au moment de l'implémentation.

Aucun nouveau token, aucune nouvelle couleur, aucune nouvelle typographie. Tous les besoins visuels s'expriment avec ce qui existe.
