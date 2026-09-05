# Design — Story s20-systeme-recompenses

> Mockup statique HTML : `docs/designs/s20-systeme-recompenses.html`. Référence visuelle, low-fidelity, **pas du code à copier**. L'implémentation réelle utilise le composant `<LevelBadge>` (nouveau, partagé) + `<Card>` réutilisé depuis `frontend/components/Card.tsx`.
> Source unique de vérité visuelle : `docs/design-system.md`. Aucun token ou composant n'est inventé ici.
> Écran conçu : **extension du dashboard `GET /api/dashboard/eleve` (s20b)** — badge niveau + total points, dans la section en-tête du dashboard élève. FR par défaut + EN (`next-intl`). Responsive smartphone (≥ 360px) et tablette (≥ 768px).
> Anchor points : `docs/research/s20-systeme-recompenses.md` (complexité réévaluée 4, split s20a/s20b, dépendance s16), `docs/designs/s16-dashboard-eleve.md` (layout dashboard existant).

## 1. Objectif et contexte

**Story** : s20-systeme-recompenses — Système de récompenses + badge niveau (AC6 : dashboard montre points + niveau).
**Couverture** : s20b (UI / badge) + extension `dashboard/schemas.py` / `aggregator.py` (s20a côté backend). L'écran est un **ajout** au dashboard s16, pas une page indépendante.

**Arbitrages de la recherche** :
- **Niveau calculé côté service, pas côté DB** (cf. recherche D4 : `UserPoints.total_points` stocke le nombre, `levels.get_level()` calcule le label). Le badge lit le label + le nombre depuis la réponse `GET /api/dashboard/eleve` étendue.
- **Badge comme composant partagé `<LevelBadge>`** (Pas de nouveau design de page — le screen est l'extension du header du dashboard).
- **3 états de couleur** (pas de token dédié « level-* » — on réutilise le système existant, cf. Gaps).
- **i18n obligatoire** : label « Apprenti / Confirmé / Expert » et « Points » via `next-intl` (AGENTS.md § i18n).

## 2. Composants du design system réutilisés

| Composant | Usage dans le mockup | Source / justification |
|---|---|---|
| `<Card>` (Card / Card.Header / Card.Body) | Conteneur du badge + points dans le header du dashboard | `frontend/components/Card.tsx`; design-system l.159-162 |
| `<Header>` (réactivé) | Layout `(dashboard)/` — le badge apparaît dans la section supérieure du dashboard, sous le header | `docs/designs/s16-dashboard-eleve.md` l.42 |
| Icônes **Lucide** : `trophy` (niveau), `star` (points) | Icône à gauche du badge | design-system l.113 — déjà installé en s11c |
| `<Button>` (variant `ghost`, si bouton « Voir mes récompenses » futur) | Non utilisé dans v1 (hors scope s20) — noté en gap |
| `<Label>` (`htmlFor`) | Si un filtre par niveau est ajouté futurement — non dans s20b |

**Aucun composant partagé nouveau n'est créé en s20b** — le `<LevelBadge>` est un composant simple (pas de logique métier, juste un rendu conditionnel par couleur + texte). Il peut vivre dans `frontend/components/LevelBadge.tsx` (un fichier, PascalCase).

## 3. Tokens utilisés (exhaustif — copiés depuis `docs/design-system.md`)

### Couleurs (light mode — dark via `dark:` ou `prefers-color-scheme`)

| Token | Hex | Usage dans le badge |
|---|---|---|
| `--color-primary` | `#3D5AFE` | **Apprenti** (0-99 pts) — icône + bordure du badge |
| `--color-success` | `#16A34A` | **Confirmé** (100-499 pts) — icône + bordure |
| `--color-accent-warm` | `#FF6B4A` | **Expert** (500+ pts) — icône + bordure |
| `--color-surface` | `#FFFFFF` | Fond du badge (card) |
| `--color-surface-subtle` | `#F4F6FA` | Fond de la section du dashboard où le badge est placé (si besoin de contraste subtil) |
| `--color-text-primary` | `#0D0F14` | Texte du niveau + nombre de points |
| `--color-text-secondary` | `#5B6472` | Label secondaire (« Points » / « Niveau ») |
| `--color-border` | `#E2E6EE` | Bordure fine du badge |

**Nota** : il n'y a pas de token `--color-level-*` dédié dans le design system. Les 3 niveaux utilisent les tokens existants (`primary`, `success`, `accent-warm`) — c'est une décision pragmatique, documentée comme *gap comblé par réutilisation* (pas d'invention).

### Typographie

| Token | Valeur (design-system) | Usage badge |
|---|---|---|
| Heading (`h2`) | 24px, weight 600, `--color-text-primary` | Titre de la section « Récompenses » dans le dashboard (si ajouté) — **hors scope v1**, le badge est petit |
| Body | 14px, `--color-text-secondary` | Label « Points » / « Niveau » |
| Accent (badge text) | 16px, weight 700, `--color-text-primary` | Nombre de points (ex. « 127 ») et niveau (ex. « Confirmé ») |

### Espacement

- Badge : padding `1rem` (16px), border-radius `0.75rem` (12px) — aligné sur `<Card>` du design-system.
- Icône : 24px (Lucide `trophy` / `star`), couleur selon niveau.
- Ecart entre icône et texte : 12px (`gap-3` Tailwind).

## 4. Écran — Layout et sections

Le badge est une **extension du header / section supérieure du dashboard élève** (s16). Pas de page dédiée.

```
┌──────────────────────────────────────┐
│ <Header> (pseudo, lang switcher)     │  ← s16 existant
├──────────────────────────────────────┤
│  [Nouveau] Section Récompenses        │  ← s20b (badge)
│  ┌───────────────────────────────┐   │
│  │ <Card>                        │   │
│  │  🏆  Confirmé                  │   │  ← badge + niveau
│  │     127 points                 │   │  ← total points
│  └───────────────────────────────┘   │
├──────────────────────────────────────┤
│  Per-subject cards (s16)             │  ← existant, inchangé
│  [Maths]  [Français]                │
└──────────────────────────────────────┘
```

**Sections du screen** :
- **Section Récompenses (nouvelle)** : une seule `<Card>` avec le badge. Place dans la partie supérieure du dashboard, au-dessus des cartes par matière (pour visibilité immédiate). Responsive : sur 360px, le badge occupe la pleine largeur (12 colonnes) ; sur ≥ 768px, il peut être en colonne de 4/12 dans un grid, avec la carte globale s16 en 8/12.
- **Contenu du badge** : icône (`trophy`), texte niveau (`next-intl` key `level.apprentice` etc.), nombre (`total_points` depuis `GlobalSummary` étendu), label secondaire (`points`).

## 5. États

| État | Condition | Visuel | Couleur du badge |
|---|---|---|---|
| **Apprenti** | `0 ≤ total_points ≤ 99` | Icône `trophy` + texte « Apprenti » + nombre | `--color-primary` (`#3D5AFE`) |
| **Confirmé** | `100 ≤ total_points ≤ 499` | Icône `trophy` + texte « Confirmé » + nombre | `--color-success` (`#16A34A`) |
| **Expert** | `total_points ≥ 500` | Icône `trophy` + texte « Expert » + nombre | `--color-accent-warm` (`#FF6B4A`) |
| **Empty (0 pts)** | `total_points == 0` | Même que Apprenti (débutant) — pas d'état séparé | `--color-primary` |
| **Loading** | API `GET /api/dashboard/eleve` en cours | Skeleton / spinner `loader-2` (Lucide) dans le `<Card>` | `--color-surface-subtle` fond |

**Pas d'état erreur spécifique au badge** — si l'API échoue, le dashboard s16 déjà gère l'erreur (le badge n'est pas rendu, ou rendu avec `0` par défaut via le schema Pydantic). Pas besoin d'un état d'erreur distinct pour le badge seul.

## 6. Mockup HTML

`docs/designs/s20-systeme-recompenses.html` — low-fidelity, uniquement tokens CSS, pas de framework. Référence pour l'implémentation (`LevelBadge` + `<Card>`).

Le mockup montre :
- Une section « Récompenses » dans le dashboard.
- 3 variantes du badge (Apprenti / Confirmé / Expert) côte à côte pour la comparaison visuelle.
- Texte en français (puis en EN via `lang` attr).
- Responsive : `max-width: 360px` et `min-width: 768px`.

## 7. Design system gaps (à noter, pas inventé)

| Gap | Impact sur s20 | Action recommandée |
|---|---|---|
| **Pas de token `--color-level-*`** | Le badge doit choisir entre `primary` / `success` / `accent-warm`. C'est un choix de mapping, pas d'invention — accepté. | **Documenté ici** — pas d'ADR nécessaire car pas de nouvelle décision structurale, juste un mapping pragmatique. |
| **Pas de composant `<LevelBadge>` partagé** | Doit être créé en s20b (`frontend/components/LevelBadge.tsx`). C'est un composant simple (pas de logique métier), conforme à AGENTS.md § Composants UI. | **Créer** dans la story s20b. |
| **Pas de `rewards` dans le design-system** | Le badge est purement présentatif ; la logique des points vit côté backend et API. | **Pas de gap visuel** — le design system couvre le rendu, pas le calcul. |
| **Pas de `next-intl` pour « Apprenti / Confirmé / Expert » documenté** | Les clés `level.apprentice` etc. doivent être ajoutées dans `frontend/messages/fr.json` et `en.json`. | **Incluir** dans la tâche s20b (i18n obligatoire, AGENTS.md § i18n). |

---

*Design ready. Next step: `/ks-plan s20-systeme-recompenses` (valider le split s20a/s20b si la complexité est confirmée 4, ou plan unique sur le badge + backend).*
