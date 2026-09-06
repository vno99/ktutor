# Design — s22-accessibilite-responsive

## Screen(s)

Pas de nouveau écran. S22 audite et corrige l'accessibilité et la réactivité des pages existantes livrées par s11a/s11b/s11c/s16/s19 :

- `/fr/chat` et `/en/chat` (StreamingMessage, Header, input chat)
- `/fr/upload` et `/en/upload` (FileUpload, Select matière, Header)
- `/fr/dashboard/eleve`, `/fr/dashboard/parent`, `/en/dashboard/eleve` (DashboardClient, Header avec avatar/menu)
- `/fr/history`, `/en/history` (HistoryListClient)

Le design est le design-system existant (`docs/design-system.md`), appliqué aux 4 pages ci-dessus. Aucune nouvelle page, aucun nouveau composant partagé.

## Mockup

`docs/designs/s22-accessibilite-responsive.html` — document de référence statique (pas un écran). Il montre :
- Les 4 pages concernées avec leurs états d'accessibilité (focus visible sur bouton/envoyer, `aria-live="polite"` sur le stream, `aria-disabled` sur le bouton désactivé, `label htmlFor` sur la drop zone, `prefers-reduced-motion` désactivant le pulse).
- Les 3 breakpoints (360px, 768px, 1280px) sans scroll horizontal.
- Les tokens du design-system utilisés (pas d'invention).

## Reused components (from the design system)

- `<Button>` — focus ring (`focus-visible:ring-2`), disabled (`aria-disabled` possible via props natifs), touch target 44×44 px (`md` = h-11).
- `<StreamingMessage>` — `role="log"`, `aria-live="polite"`, `aria-busy` (l.98-103 dans le composant).
- `<FileUpload>` — `<label htmlFor>` visible et focusable (drop zone), `aria-disabled`, `aria-busy`, `sr-only` input natif, `capture="environment"` (l.178-243).
- `<Header>` — `aria-label` logo, `aria-current` navigation, `role="menu"`/`menuitem` sur le dropdown avatar.
- `<Select>` — wrapper natif `<select>` (accessible par défaut, pas de custom dropdown inventé).
- `<Label>` — `htmlFor` systématique, `srOnly` pour les labels invisibles.
- `<Card>` — surface standard (`bg-surface`, `border`, `rounded-md`, `shadow-kt-default`).
- `globals.css` — `focus-visible` (l.96-99), `prefers-reduced-motion` (l.84-93), tokens couleurs/typographie.

## States

S22 ne définit pas de nouveaux états UI. Les états existants des 4 pages sont audités pour leur conformité a11y :

- **Chat** : streaming (`aria-busy=true`, `aria-live`), erreur (`role="alert"`), sources (`SourcesLine`).
- **Upload** : drag over (`border-primary bg-primary/5`), fichier sélectionné (`Card` avec icône, nom, taille, bouton Retirer `aria-label`).
- **Dashboard / History** : chargement (pas de spinner plein écran — conforme au design-system), vide (message d'accueil), succès (cards progression), erreur réseau (carte erreur + bouton Réessayer).

## Design system gaps

Aucun nouveau gap inventé par s22. Les gaps existants du design-system (Skeleton loader, `<Dialog>`, `<Tabs>`, `<Table>`, `<NotificationBell>`, dark/light toggle, bouton Stop sur stream) restent hors-scope pour cette story car l'AC s22 ne demande aucun d'entre eux.

Le seul besoin non couvert directement est le **test responsive automatisé** : le Playwright config actuel (`frontend/playwright.config.ts`) n'a pas de viewport mobile/tablette ni d'intégration `axe-core`. Ce n'est pas un gap visuel (le responsive est couvert par le CSS et Tailwind), mais un gap de **tests/outillage**. Il doit être résolu dans le plan (ajout de viewport override ou nouveau projet Playwright, plus intégration axe-core), pas par un nouveau composant visuel.

---

*Référence : `docs/design-system.md` (tokens, composants, accessibilité, gaps) ; `frontend/components/*.tsx` ; `frontend/app/globals.css` ; `frontend/playwright.config.ts` ; `frontend/lighthouserc.json`. Aucune nouvelle couleur, aucun nouveau composant, aucun nouveau token inventé.*
