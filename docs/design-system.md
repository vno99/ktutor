# Design System — ktutor

> Référence visuelle unique, lue par `/ks-design` à chaque story.
> Source : **squelette structurel** (2026-08-28). Aucune direction visuelle n'est figée à ce stade — la palette, la typographie et l'ambiance seront définies story par story via `/ks-design <story>`, qui pourra s'appuyer sur un Claude Design project quand il sera créé.
> Contraintes structurelles imposées par `docs/architecture.md` (cf. ADR 006) et `CLAUDE.md` § Frontend.

## Statut

Ce document est **explicitement non visuel**. Il pose les **rails structurels** (conventions, points d'extension, patterns imposés) que toute story `/ks-design` devra respecter. Il ne fixe pas :
- les couleurs (palette) — à définir dans le Claude Design project quand il sera créé
- la typographie (familles, échelles) — idem
- les espacements / radius exacts au token près — valeurs par défaut Tailwind, à raffiner
- les illustrations, icônes, ambiances — à définir

L'objectif est d'éviter qu'un agent `/ks-design` invente une direction par défaut. Chaque écran passe par `/ks-design` et pioche dans ce qui est défini **ici ou dans le Claude Design project**.

## Tokens

### Tokens techniques (imposés)

| Catégorie | Système | Justification |
|---|---|---|
| Couleurs (placeholder) | **Aucune valeur figée.** Le projet doit pointer vers des CSS variables Tailwind (`--color-primary`, `--color-bg`, etc.) qui restent à brancher sur un thème. | Le PRD ne fixe pas de charte. La palette sera importée du Claude Design project via `@dsCard` markers ou variables CSS. |
| Typographie (placeholder) | **Aucune valeur figée.** Utiliser la stack par défaut Tailwind (`font-sans`, `font-serif`, `font-mono`) jusqu'à injection. | Idem — la typo sera définie dans le Claude Design project. |
| Espacement | Échelle Tailwind par défaut : `0`, `px`, `0.5`, `1`, `1.5`, `2`, `2.5`, `3`, `4`, `5`, `6`, `8`, `10`, `12`, `16`, `20`, `24`, `32` (en rem). | Convention Next.js + Tailwind. Pas de token custom en l'absence de direction visuelle. |
| Radius | Échelle Tailwind par défaut : `none`, `sm` (0.125rem), `default` (0.25rem), `md` (0.375rem), `lg` (0.5rem), `xl` (0.75rem), `2xl` (1rem), `full` (9999px). | Idem. |
| Shadows | Échelle Tailwind par défaut : `sm`, `default`, `md`, `lg`, `xl`, `2xl`, `inner`, `none`. | Idem. |
| Breakpoints | Tailwind par défaut : `sm` 640px, `md` 768px, `lg` 1024px, `xl` 1280px, `2xl` 1536px. | Cible 360px (smartphone) et 768px (tablette) — testés dans s11 et s22. |

### Mode sombre / clair

- Le projet doit supporter les deux modes (`prefers-color-scheme`).
- Les composants utilisent les classes `dark:` de Tailwind.
- Le toggle n'est **pas** une story à part entière — il est ajouté au shell du dashboard quand le Claude Design project le définit.

## Conventions d'implémentation des tokens

Quand un Claude Design project sera créé, les tokens seront injectés via :

1. **CSS variables dans `frontend/app/globals.css`** :
   ```css
   :root {
     --color-primary: <depuis Claude Design>;
     --color-bg: <depuis Claude Design>;
     /* ... */
   }
   [data-theme="dark"] {
     --color-primary: <variante sombre>;
     /* ... */
   }
   ```
2. **Tailwind config** consomme les variables :
   ```ts
   // tailwind.config.ts
   theme: { extend: { colors: { primary: 'var(--color-primary)' } } }
   ```
3. **Composants** utilisent les classes Tailwind (`bg-primary`, `text-fg`) — pas de valeurs hex en dur.

## Available components (catalogue)

> Le projet n'a pas encore de bibliothèque de composants (pas de shadcn/ui installé, pas de boilerplate UI). Cette section liste les composants **à créer** au fil des stories.

| Composant | Usage prévu | Story qui l'introduit |
|---|---|---|
| `<Button>` (primary, secondary, ghost, destructive) | Actions principales des formulaires et écrans | s12 (register), s11 (upload/chat) |
| `<Input>` (text, email, password, file) | Champs de formulaire | s12, s10 |
| `<Label>` | Associé à chaque input (`htmlFor`) | s12 (a11y dès le départ) |
| `<Card>` (header / body / footer) | Conteneur pour les unités de contenu (résultat de chat, exercice, dashboard) | s11 (chat), s16/s17 (dashboard) |
| `<Toast>` | Notifications transitoires (succès, erreur) | s25 |
| `<Avatar>` (avec initiales) | Header parent/élève, attribution d'exercices | s17 (vue parent) |
| `<Tabs>` | Dashboard élève (par matière) | s16 |
| `<Dialog>` (modale) | Confirmation suppression, saisie manuelle score | s15 (RBAC), s18b |
| `<Select>` (natif) | Sélecteur de matière, sélecteur de difficulté | s06, s18 |
| `<Table>` (simple) | Liste des documents, historique des conversations | s19, s15 |
| `<Chart>` (via Recharts) | Dashboard progression | s16, s17 |
| `<FileUpload>` (drag & drop + caméra mobile) | Upload de documents (PDF, photo) | s10, s11 |
| `<StreamingMessage>` (avec `aria-live="polite"`) | Affichage incrémental des chunks SSE | s11, s09 |
| `<LanguageSwitcher>` | FR/EN | s11, s21 |
| `<NotificationBell>` (compteur non-lus) | Header dashboard | s25 |

### Bibliothèque cible : shadcn/ui (à confirmer)

Quand le Claude Design project sera créé, le projet adoptera probablement **shadcn/ui** comme base (copie locale des composants, total contrôle sur le code, intégration native avec Tailwind + Radix). Cette adoption n'est pas une story en soi — c'est une décision d'outillage prise au moment où la direction visuelle existe. Cf. note ci-dessous.

## UI patterns imposés

### Formulaires

- Chaque input a un `<label htmlFor="...">` visible (a11y).
- Validation inline (message d'erreur sous le champ, pas en `alert()` JS).
- Bouton submit désactivé tant que le formulaire est invalide OU affiche un état "submitting" avec spinner.
- Sur erreur 422, les champs concernés sont mis en évidence (`aria-invalid="true"`).
- Sur succès, redirection ou confirmation explicite — pas de redirection silencieuse.

### États (loading / empty / error / success)

| État | Pattern |
|---|---|
| **Loading** | Skeleton (placeholder animé) ou spinner Tailwind. Ne JAMAIS afficher une page vide. Annoncer `aria-busy="true"` sur la zone. |
| **Empty** | Message clair (« Aucun document uploadé. Commence par importer ton cours. ») + CTA principal. |
| **Error** | Message en français + code d'erreur discret pour le support + bouton « Réessayer » si retry possible. |
| **Success** | Toast (s25) + redirection OU mise à jour inline de l'UI. |

### Feedback (toast, inline)

- **Toasts** : pour les confirmations brèves (succès erreur réseau). 4s d'affichage, dismissable, accessible (`role="status"`).
- **Inline** : pour les erreurs de validation et les messages d'aide contextuels.
- **Pas de modal** pour les erreurs de validation (trop intrusif).

### Streaming (chat et notifications)

- Zone de stream avec `aria-live="polite"` pour que les lecteurs d'écran annoncent les nouveaux chunks.
- Indicateur visuel de "en train d'écrire" (cursor clignotant).
- Bouton "Stop" pour interrompre le stream (cf. s11 trap — la connexion SSE peut dropper).

### Navigation

- Header fixe avec : logo / pseudo / sélecteur de langue / lien dashboard / déconnexion.
- Bottom tab bar sur mobile (smartphone) avec 3-4 entrées max (Chat, Upload, Dashboard, Profil).
- Pas de sidebar sur smartphone. Sidebar collapsible sur tablette/desktop (à confirmer avec le Claude Design project).

## Accessibilité (cf. ADR 006 + stories s11, s22)

- **WCAG 2.1 A minimum**, AA cible.
- **Contraste** : ratio ≥ 4.5:1 pour le texte normal, ≥ 3:1 pour le texte large.
- **Focus visible** : `:focus-visible` Tailwind, outline custom ou ring. Ne JAMAIS supprimer l'outline sans le remplacer.
- **Labels** : `<label htmlFor>` sur chaque input. Pas de placeholder seul.
- **Touch targets** : ≥ 44×44 px (WCAG 2.5.5).
- **Keyboard** : tout est navigable au Tab, logique de tabulation respectée. Pas de piège au focus.
- **Screen reader** : `aria-live` sur les streams, `aria-label` sur les boutons icon-only, `aria-describedby` pour les messages d'aide.

## i18n (cf. ADR 006 + stories s11, s21)

- **next-intl** dès la première story UI (s11).
- **Catalogues** : `frontend/messages/fr.json` (par défaut), `frontend/messages/en.json`.
- **Pas de hardcoded strings** : `useTranslations()` partout. Vérifié par une règle ESLint custom (story s11).
- **Sélecteur de langue** dans le header. Choix persisté en cookie.
- **Format de date / nombre** : `Intl.DateTimeFormat` et `Intl.NumberFormat`, locale dérivée du `Accept-Language` ou du cookie.
- **Pas de traduction** du contenu uploadé (manuscrit, documents) — seulement l'UI chrome.

## Responsive

- **Mobile-first**. Styles de base pour 360px, puis breakpoints `md` (768px) et `lg` (1024px) pour les enrichissements.
- **Layout fluide** : grilles et flexbox, pas de largeurs fixes en px.
- **Tests Playwright** sur 360 / 768 / 1280 dans s11 et s22.

## Do / Don't

### ✅ Do

- Utiliser les classes Tailwind utilitaires, pas de CSS custom.
- Préférer les composants natifs (`<select>`, `<button>`) aux composants custom ARIA.
- Préférer les CSS variables pour les couleurs, jamais de hex en dur dans les composants.
- Tester au clavier et au lecteur d'écran avant de marquer une story UI comme « done ».
- Documenter tout nouveau composant ajouté dans cette table.

### ❌ Don't

- Pas de couleurs hardcodées (`#3b82f6`). Toujours via tokens.
- Pas de typo hardcodée (`font-['Inter']`). Toujours via tokens.
- Pas de `style={{}}` inline pour les couleurs / espacement.
- Pas de `<div onClick>` — utiliser `<button>`.
- Pas d'icône sans `aria-label` ou texte adjacent.
- Pas d'animation sans `prefers-reduced-motion` respecté.
- Pas de state global pour les valeurs éphémères (formulaire, hover) — local state suffit.
- Pas d'invention de palette / typo par défaut. Si la direction visuelle n'est pas définie, revenir à l'équipe.

## Décisions à prendre (en attente du Claude Design project)

Quand un Claude Design project sera créé, les éléments suivants seront importés ici :

- Palette (primary, secondary, accent, neutrals, success, warning, error) en light et dark.
- Typographie (familles, échelles, line-heights, letter-spacings).
- Iconographie (lucide-react, heroicons, ou set custom).
- Illustrations (si applicable).
- Composants shadcn/ui à installer (`<Button>`, `<Input>`, `<Dialog>`, etc.).
- Logo et identité de marque.

Cette section sera mise à jour par story via `/ks-design <story>` au fil de l'eau.

## Workflow d'évolution

1. **Le Claude Design project est créé** (par l'humain, hors-pipeline killer-saas).
2. **Une story demande un écran** (ex : s11 `/chat`).
3. `/ks-design <story>` lit ce document + le Claude Design project, et produit `docs/designs/<story-id>.md` (mockup + tokens spécifiques à l'écran).
4. L'agent d'exécution (`/ks-execute`) implémente en respectant ce doc.
5. Si un nouveau composant émerge, il est ajouté ici (catalogue).
6. Si une décision structurelle est prise (ex : adopter shadcn/ui), elle est consignée dans `docs/decisions/`.

## Liens

- `templates/design-system.md` — squelette de base.
- `templates/design-screen.md` — squelette par écran (sortie de `/ks-design <story>`).
- `templates/design-brief.md` — brief de design pour une story.
- `docs/architecture.md` § Design / UX — cadre général.
- ADR 006 — choix Next.js App Router + i18n + a11y dès le départ.
- Stories s11 (frontend chat/upload), s16 (dashboard élève), s17 (dashboard parent), s21 (i18n), s22 (a11y) — premières stories qui consommeront ce système.
