# Design — s25-notifications-in-app

## Screen(s)

- **Header (desktop + mobile)** : ajout d'une icône `NotificationBell` (Lucide `bell`) dans le `<Header>` à côté du `LanguageSwitcher` et du pseudo input. Badge rouge avec nombre non lus (`bg-error`, `text-xs text-white`, `rounded-full`, taille min 18×18 px).
- **Toast inline (non modal)** : un composant `<Toast>` affiché sous le header ou au-dessus du contenu de la page (position `fixed top-16 right-4 z-50`, width `max-w-sm`). Style : `bg-surface border border-border shadow-kt-md rounded-md p-4`, icône `info` (Lucide `info-circle`) `text-info`, titre `text-text-primary font-semibold`, message `text-text-secondary text-sm`. Toast disparaît automatiquement après 5s ou au clic sur un bouton fermer (`x`).
- **Aucun changement de page** : pas de page `/notifications` dédiée. Les notifs sont consultées via le bell (dropdown simple) et le toast est un feedback visuel.
- **Poll status** : pas de loader visible pour le poll. Le badge se met à jour silencieusement.

## Mockup

`docs/designs/s25-notifications-in-app.html` — mockup statique du header avec la cloche et du toast en haut à droite.

## Reused components (from the design system)

- `<NotificationBell>` — nouveau composant, réutilise `<Button>` (variant ghost, icon-only `bell`) + badge via `badge` CSS (`bg-error rounded-full`). Props : `unreadCount: number`, `onClick: () => void`.
- `<Toast>` — nouveau composant. Réutilise `<Card>` (style surface, bordure, ombre `shadow-kt-md`) et `<Button>` ghost pour fermer. Props : `message: string`, `type?: 'info' | 'success' | 'warning'`, `onClose?: () => void`.
- `<Header>` — modifié (`Header.tsx`) : ajout de `<NotificationBell>` entre le `LanguageSwitcher` et le pseudo/initiale.

## States

- **Header avec badge 0** : cloche sans badge (état par défaut après lecture).
- **Header avec badge N > 0** : badge rouge `N` superposé en haut à droite de la cloche.
- **Header cloche ouverte (click)** : dropdown simple (liste verticale de notifs récentes, max 5, avec un bouton "Tout marquer comme lu"). Pas de composant `Dialog` nécessaire (le dropdown est un `div` positionné, pas une modale).
- **Toast info (nouvelle évaluation)** : message "Nouvelle évaluation traitée" + sujet (ex. "maths"). Type `info`.
- **Toast success (points gagnés)** : message "+7 points gagnés !". Type `success` (`text-success`, icône `check-circle`).
- **Toast warning (évaluation manuelle)** : message "Ta copie d'évaluation a besoin d'une vérification". Type `warning`.
- **Toast fermé** : disparaît (fade out optionnel, mais simple `display: none` après timeout suffit pour le POC).

## Design system gaps

Le design-system (`docs/design-system.md`) liste déjà ces gaps à la ligne 231 (`Pas de <Toast>`) et 237 (`Pas de <NotificationBell>`). Cette story ferme ces deux gaps. Aucun nouveau token nécessaire (`--color-info` `#0284C7` existe déjà pour les notifications, `--color-success` `#16A34A` pour les points, `--color-warning` `#D97706` pour les évaluations manuelles). Aucun composant inventé hors du système.
