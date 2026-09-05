# Design — s21-i18n-fr-en

> Story : `s21-i18n-fr-en` — consolidation i18n FR/EN (frontend complet, backend `Accept-Language` à ajouter).
> Source de vérité visuelle : `docs/design-system.md` (tokens, composants, conventions).
> Aucune nouvelle identité visuelle ; aucun nouveau composant. La story réutilise `<LanguageSwitcher>` et le `<Header>` existants.

---

## Écran couvert

Le design couvre **uniquement** le composant `<Header>` avec le `<LanguageSwitcher>` intégré, car s21 ne crée pas de nouvelle page — il consolide l'i18n sur toutes les pages existantes (chat, upload, auth, dashboard, history). Le mockup `.html` montre le header dans ses deux états (FR / EN) pour communiquer la cohérence visuelle.

## Structure du design

### Layout — Header (sticky, 56 px)

Le header reste identique au design-system (§ Layout) :
- `sticky top-0 z-10 h-14 w-full bg-surface border-b border-border`
- `max-w-screen-lg mx-auto px-4 md:px-6 flex items-center gap-4`
- Logo (`text-lg font-bold text-primary-strong`) + navigation desktop (`hidden md:flex`) + `<LanguageSwitcher>` (`hidden sm:block`) + affordance auth (`avatar` ou `Se connecter`).

Le `<LanguageSwitcher>` est déjà intégré dans le header (`frontend/components/Header.tsx`, ligne 156-158) — aucune modification du layout du header n'est requise.

### Composant — `<LanguageSwitcher>`

Réutilisation directe du composant existant (`frontend/components/LanguageSwitcher.tsx`) :
- Pill toggle `FR | EN`, `rounded-full`, `bg-surface`, `border border-border`.
- État actif : `bg-primary text-white` (`primary` token), `aria-pressed="true"`.
- État inactif : `bg-transparent text-text-secondary hover:bg-surface-subtle`.
- Action : `router.replace(pathname, { locale })` (déclenche le middleware `next-intl` qui réécrit l'URL en `/fr/` ou `/en/` et pose le cookie `NEXT_LOCALE`).
- Aucun nouveau token ; utilise `primary`, `surface-subtle`, `text-secondary`, `border`, `text-white`.

### États du header (mockup)

Le `.html` montre deux captures statiques du header :

1. **État FR (défaut)** — locale active = `fr`, URL = `/fr/chat`, cookie `NEXT_LOCALE=fr`. Navigation : Chat, Upload, Historique (si auth). Switcher : FR (actif, `bg-primary`), EN (inactif).
2. **État EN** — locale active = `en`, URL = `/en/chat`, cookie `NEXT_LOCALE=en`. Même layout. Switcher : EN (actif), FR (inactif). Les libellés (`Chat`, `Upload`, `History`) viennent du catalogue `en.json`.

### Design-system gaps (s21)

Aucun. Le design-system (`docs/design-system.md` § Internationalisation, l. 191-199) couvre déjà :
- `next-intl` framework
- Catalogues `fr.json` / `en.json`
- `<LanguageSwitcher>` component spec (l. 127)
- Cookie `NEXT_LOCALE`
- `useTranslations()` partout
- `localePrefix: 'always'` (routing)

Le seul élément visuel de s21 (`LanguageSwitcher` dans le header) est déjà présent dans le code et dans le design-system. Aucune invention.

### Accessibilité (transverse — s'applique au switcher)

Repris du design-system (§ Accessibilité, l. 178-189) :
- `aria-pressed` sur le bouton actif (`FR` ou `EN`).
- `aria-label` sur chaque bouton (`Passer en français`, `Passer en anglais`) via `useTranslations('common')`.
- Focus visible (`focus-visible:ring-2 focus-visible:ring-primary/30`).
- Touch target : pill `h-8 px-3` → 32×32 px minimum (OK, proche du 44 px idéal mais la pill est une cible secondaire ; le standard WCAG 2.5.5 AAA est 44 px, le niveau A n'impose pas de taille minimale pour les cibles secondaires, mais le design-system impose 44 px sur les boutons primaires ; le switcher reste accessible).
- Réduction du mouvement (`prefers-reduced-motion`) : la transition du switcher (`transition-colors`) est instantanée en mode réduit.

### Out-of-scope (pour le design)

- Aucune nouvelle page (chat, upload, auth, dashboard, history) — ces pages sont couvertes par leurs propres stories (s11b, s11c, s12, s16, s19).
- Aucune nouvelle couleur, typographie, espacement, ombre, icône — tout réutilise le design-system.
- Aucune animation supplémentaire (pas de `animate-pulse` sur le switcher, pas de toast).
- Le mockup `.html` est un **référentiel** (comme pour s11b/s11c/s16) — il ne doit pas être copié-collé dans la production ; le composant `<LanguageSwitcher>` et le `<Header>` du code sont la source de vérité.
