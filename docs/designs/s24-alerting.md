# Design — Story s24-alerting

## Écran(s)
Aucun écran UI — story pure infrastructure backend (alerting console + métriques Prometheus). Aucune page frontend, aucun composant visuel requis.

## Mockup
Pas de mockup HTML. Le POC ne produit pas d'interface graphique (log `ALERT` en console et endpoint `/metrics` existant).

## Reused components (design system)
Aucun — pas de UI.

## States
- POC console : `ALERT` log lines (success / warning dans le sens loguru)
- Metrics endpoint : `/metrics` (déjà livré s23)

## Design system gaps
- Aucune UI d'alerte (tableau de bord ops, page d'état) — hors périmètre s24, à traiter en s25+ si besoin.
- Pas de composant d'affichage d'alerte (toast, banner, modal) dans le design system — le gap reste ouvert.
