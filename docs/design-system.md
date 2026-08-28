# Design System — ktutor

> Référence visuelle unique, lue par `/ks-design` à chaque story.
> Direction visuelle validée le **2026-08-28** — inspiration Linear, palette bleu / gris avec accent corail pour la gamification.
> Contraintes structurelles imposées par `docs/architecture.md` (cf. ADR 006) et `CLAUDE.md` § Frontend.

## Direction visuelle

**Ambiance** : sobre, focalisée, professionnelle mais pas froide. Style SaaS B2B moderne, dense sans être étouffant. Inspiré de **Linear** (typographie soignée, grilles strictes, accent minimal, beaucoup de whitespace en zone de travail).

**Public** : double — élève de collège (mobile, doit rester engageant sans être « cartoon ») + parent (tablette/desktop, doit inspirer confiance). Le ton visuel est unique, l'adaptation vient des layouts (stack vertical mobile vs grille desktop).

**Règle d'or** : un seul accent chaud (corail), réservé à la **gamification** (points, badges, streaks, succès). Tout le reste est en bleu / gris. Le corail signale visuellement la récompense sans concurrencer l'action principale.

## Tokens

### Couleurs

| Token | Light | Dark | Usage |
|---|---|---|---|
| `--color-primary` | `#3D5AFE` (indigo vif) | `#7B8CFF` | CTA principal, liens, focus ring |
| `--color-primary-strong` | `#1E2A8A` (navy) | `#3D5AFE` | Titres, branding, nav active |
| `--color-canvas` | `#FAFBFC` (off-white) | `#0D0F14` | Fond principal |
| `--color-surface` | `#FFFFFF` | `#161A22` | Cards, panels |
| `--color-surface-subtle` | `#F4F6FA` | `#1E232E` | Hover, zones secondaires |
| `--color-border` | `#E2E6EE` | `#2A2F3B` | Séparateurs, inputs |
| `--color-text-primary` | `#0D0F14` | `#F4F6FA` | Texte principal |
| `--color-text-secondary` | `#5B6472` | `#9AA3B2` | Légendes, meta |
| `--color-text-tertiary` | `#8B95A3` | `#6B7484` | Disabled, placeholders |
| `--color-accent-warm` | `#FF6B4A` (corail doux) | `#FF8B6F` | Badges récompense, streaks, succès |
| `--color-success` | `#16A34A` | `#22C55E` | Confirmations |
| `--color-warning` | `#D97706` | `#F59E0B` | Alertes non-bloquantes |
| `--color-error` | `#DC2626` | `#EF4444` | Erreurs, validation |
| `--color-info` | `#0284C7` | `#38BDF8` | Messages d'aide |

Toutes les couleurs sont définies comme **CSS variables** dans `frontend/app/globals.css`, et consommées via `tailwind.config.ts` (ex : `colors: { primary: 'var(--color-primary)' }`). **Jamais de hex en dur dans les composants.**

### Typographie

| Niveau | Famille | Usage |
|---|---|---|
| **Sans (UI)** | **Inter** (variable) | Tout le chrome UI, body, boutons |
| **Mono (code/maths)** | **JetBrains Mono** | Formules, code, équations |
| **Display** | Inter Bold tracking-tight | Titres écran (Chat, Dashboard) |

Échelle (mobile-first, `clamp()` pour fluidité) :

| Token | Taille | Usage |
|---|---|---|
| `xs` | 12px / 0.75rem | Légendes, meta |
| `sm` | 14px / 0.875rem | Texte secondaire, boutons |
| `base` | 16px / 1rem | Body |
| `lg` | 18px / 1.125rem | Texte mis en avant |
| `xl` | 20px / 1.25rem | Sous-titres |
| `2xl` | 24px / 1.5rem | Titres de section |
| `3xl` | 30px / 1.875rem | Titres d'écran |
| `4xl` | 36px / 2.25rem | Hero (rare) |

- **Line-height** : 1.5 (body), 1.2 (headings)
- **Letter-spacing** : `-0.011em` sur les headings, 0 sur le body

### Espacement

Échelle Tailwind par défaut (multiples de 4px) : `0`, `px`, `0.5`, `1`, `1.5`, `2`, `2.5`, `3`, `4`, `5`, `6`, `8`, `10`, `12`, `16`, `20`, `24`, `32` (en rem).

### Radius

| Token | Valeur | Usage |
|---|---|---|
| `xs` | 4px | Badges, tags |
| `sm` | 6px | Inputs, boutons |
| `md` | 8px | Cards, dialogs |
| `lg` | 12px | Modales larges |
| `xl` | 16px | Hero panels |
| `full` | 9999px | Avatars, pills |

### Shadows

Ombres très discrètes (style Linear) — le contraste vient des couleurs de fond, pas des ombres fortes.

| Token | Valeur | Usage |
|---|---|---|
| `sm` | `0 1px 2px 0 rgba(13,15,20,0.04)` | Cards subtiles |
| `default` | `0 2px 4px 0 rgba(13,15,20,0.06), 0 1px 2px 0 rgba(13,15,20,0.04)` | Cards standards |
| `md` | `0 4px 12px 0 rgba(13,15,20,0.08)` | Modales, dropdowns |
| `lg` | `0 12px 32px 0 rgba(13,15,20,0.12)` | Toasts, popovers |

### Breakpoints

Tailwind par défaut : `sm` 640px, `md` 768px, `lg` 1024px, `xl` 1280px, `2xl` 1536px.

Cible principale : **360px (smartphone)** et **768px (tablette)** — testés dans s11 et s22.

### Mode sombre / clair

- Support natif des deux modes (`prefers-color-scheme` + toggle manuel via attribut `data-theme`).
- Composants utilisent les classes `dark:` de Tailwind.
- Toutes les couleurs ci-dessus ont une variante light ET dark.
- Le toggle est ajouté au shell du dashboard (cf. s16).

## Conventions d'implémentation

### CSS variables

```css
/* frontend/app/globals.css */
:root {
  --color-primary: #3D5AFE;
  --color-canvas: #FAFBFC;
  /* ... */
}
[data-theme="dark"] {
  --color-primary: #7B8CFF;
  --color-canvas: #0D0F14;
  /* ... */
}
```

### Tailwind config

```ts
// tailwind.config.ts
export default {
  theme: {
    extend: {
      colors: {
        primary: 'var(--color-primary)',
        canvas: 'var(--color-canvas)',
        // ...
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
      borderRadius: {
        xs: '4px',
        sm: '6px',
        md: '8px',
        lg: '12px',
        xl: '16px',
      },
    },
  },
};
```

### Règle d'or

- Toujours les **tokens Tailwind** (`bg-primary`, `text-text-primary`, `rounded-md`).
- Jamais de hex en dur dans les composants.
- Jamais de `style={{ color: '#...' }}` inline.
- Pour les variantes dark, utiliser les classes `dark:` (`dark:bg-canvas`).

## Available components

| Composant | Usage | Story qui l'introduit |
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

Quand un Claude Design project sera créé, le projet adoptera probablement **shadcn/ui** comme base (copie locale des composants, total contrôle sur le code, intégration native avec Tailwind + Radix). Cette adoption n'est pas une story en soi — c'est une décision d'outillage prise au moment où la direction visuelle est finalisée. Cf. note « Décisions restantes ».

### Composants signature

- **Bouton primary** : fond `--color-primary`, texte blanc, `radius-sm` (6px), padding `8px 14px`, `font-weight: 500`. Hover : assombrir 8%. Focus : `ring-2 ring-primary/30 ring-offset-2 ring-offset-canvas`.
- **Card "élève"** : `bg-surface`, `border` 1px, `radius-md` (8px), padding 16-20px, shadow `default`. Élévation subtile.
- **Input** : `bg-surface`, `border` 1px, `radius-sm` (6px), padding `8px 12px`, focus ring `--color-primary`. Pas de label flottant Material — label au-dessus, statique.
- **Avatar** : cercle `radius-full` avec initiales du pseudo sur fond `--color-primary` (variation teinte unique par hash du pseudo). 32px (header) / 40px (cards).
- **Toast** : apparaît en haut à droite (desktop) / haut centré (mobile), shadow `lg`, durée 4s, dismissable, `role="status"`.
- **Streaming message (chat)** : pas de bubble à la Messenger. Le chat est un **flux vertical** avec un indicateur de typing (3 points animés) puis accumulation de tokens en texte courant, comme Linear AI. Le message de l'élève est distingué par une bordure gauche 2px `--color-primary`. Pas de fond différent.

## Iconographie

- **Set** : **Lucide** (open source, tree-shakable, cohérent avec Linear dans le trait). Pas d'emoji dans l'UI chrome.
- **Tailles** : 16px (inline), 20px (bouton), 24px (feature), 32px (hero).
- **Couleur** : héritée du contexte (`currentColor`), sauf pour les icônes d'accent (gamification) qui utilisent `--color-accent-warm`.

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

- **Toasts** : pour les confirmations brèves (succès, erreur réseau). 4s d'affichage, dismissable, accessible (`role="status"`).
- **Inline** : pour les erreurs de validation et les messages d'aide contextuels.
- **Pas de modal** pour les erreurs de validation (trop intrusif).

### Streaming (chat et notifications)

- Zone de stream avec `aria-live="polite"` pour que les lecteurs d'écran annoncent les nouveaux chunks.
- Indicateur visuel de "en train d'écrire" (cursor clignotant).
- Bouton "Stop" pour interrompre le stream (cf. s11 trap — la connexion SSE peut dropper).

### Navigation

- **Header fixe** : logo / pseudo / sélecteur de langue / lien dashboard / toggle dark/light / déconnexion.
- **Mobile** : bottom tab bar 64px avec 4 entrées max (Chat, Upload, Dashboard, Profil).
- **Tablette/Desktop** : sidebar 240px collapsible à gauche, pas de bottom tab bar.

## Layout & responsive

- **Mobile (360px)** : stack vertical, padding latéral 16px, header sticky 56px, bottom tab bar 64px.
- **Tablette (768px+)** : layout à deux colonnes pour les dashboards (sidebar 240px + main), pas de bottom tab bar.
- **Desktop (1280px+)** : container centré `max-width: 1200px`, sidebar collapsible, plus de densité horizontale.

## Accessibilité (cf. ADR 006 + stories s11, s22)

- **WCAG 2.1 A minimum**, AA cible.
- **Contraste** : ratio ≥ 4.5:1 pour le texte normal, ≥ 3:1 pour le texte large. Les combinaisons light/dark ci-dessus respectent AA.
- **Focus visible** : `ring-2 ring-primary/30 ring-offset-2 ring-offset-canvas`. Ne JAMAIS supprimer l'outline sans le remplacer.
- **Labels** : `<label htmlFor>` sur chaque input. Pas de placeholder seul.
- **Touch targets** : ≥ 44×44 px (WCAG 2.5.5).
- **Keyboard** : tout est navigable au Tab, logique de tabulation respectée. Pas de piège au focus.
- **Screen reader** : `aria-live` sur les streams, `aria-label` sur les boutons icon-only, `aria-describedby` pour les messages d'aide.
- **`prefers-reduced-motion`** : respecté — les animations de typing sont désactivées.

## i18n (cf. ADR 006 + stories s11, s21)

- **next-intl** dès la première story UI (s11).
- **Catalogues** : `frontend/messages/fr.json` (par défaut), `frontend/messages/en.json`.
- **Pas de hardcoded strings** : `useTranslations()` partout. Vérifié par une règle ESLint custom (story s11).
- **Sélecteur de langue** dans le header. Choix persisté en cookie.
- **Format de date / nombre** : `Intl.DateTimeFormat` et `Intl.NumberFormat`, locale dérivée du `Accept-Language` ou du cookie.
- **Pas de traduction** du contenu uploadé (manuscrit, documents) — seulement l'UI chrome.

## Do / Don't

### ✅ Do

- Utiliser les tokens (`bg-primary`, `text-text-primary`, `rounded-md`) — pas de CSS custom.
- Préférer les composants natifs (`<select>`, `<button>`) aux composants custom ARIA.
- Garder l'accent corail pour la **gamification uniquement** (points, badges, streaks, succès).
- Préférer le whitespace à la densité (style Linear).
- Tester au clavier et au lecteur d'écran avant de marquer une story UI comme « done ».
- Tester en dark mode dès la première story UI.
- Documenter tout nouveau composant ajouté dans la table.

### ❌ Don't

- Pas de couleurs hardcodées (`#3b82f6`). Toujours via tokens.
- Pas de typo hardcodée (`font-['Inter']`). Toujours via tokens.
- Pas de `style={{}}` inline pour les couleurs / espacement.
- Pas de `<div onClick>` — utiliser `<button>`.
- Pas d'icône sans `aria-label` ou texte adjacent.
- Pas d'animation sans `prefers-reduced-motion` respecté.
- Pas d'emoji dans l'UI chrome.
- Pas de gradient (les surfaces sont plates, l'accent est la couleur pure).
- Pas d'ombre forte (style Material) — rester subtil.
- Pas de bleu dans la zone d'écriture manuscrite (laisser le fond canvas).
- Pas de state global pour les valeurs éphémères (formulaire, hover) — local state suffit.
- **Pas d'invention de palette / typo**. Si la direction évolue, mettre à jour ce document d'abord.

## Décisions restantes

Quand un Claude Design project sera créé, les éléments suivants seront affinés ici :

- Adoption (ou non) de **shadcn/ui** comme base de composants — actuellement optionnelle.
- Logo et identité de marque (à produire).
- Illustrations (si applicable).
- Variations des avatars (teintes uniques par hash de pseudo — 6-8 variations à définir précisément).
- Empty states illustrés (vs texte seul).

Cette section sera mise à jour par story via `/ks-design <story>` au fil de l'eau.

## Workflow d'évolution

1. **Une story demande un écran** (ex : s11 `/chat`).
2. `/ks-design <story>` lit ce document + le Claude Design project (s'il existe), et produit `docs/designs/<story-id>.md` (mockup + tokens spécifiques à l'écran).
3. L'agent d'exécution (`/ks-execute`) implémente en respectant ce doc.
4. Si un nouveau composant émerge, il est ajouté ici (catalogue).
5. Si une décision structurelle est prise (ex : adopter shadcn/ui), elle est consignée dans `docs/decisions/`.

## Liens

- `templates/design-system.md` — squelette de base.
- `templates/design-screen.md` — squelette par écran (sortie de `/ks-design <story>`).
- `templates/design-brief.md` — brief de design pour une story.
- `docs/architecture.md` § Design / UX — cadre général.
- ADR 006 — choix Next.js App Router + i18n + a11y dès le départ.
- Stories s11 (frontend chat/upload), s16 (dashboard élève), s17 (dashboard parent), s21 (i18n), s22 (a11y) — premières stories qui consommeront ce système.
