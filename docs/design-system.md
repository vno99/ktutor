# Design System — ktutor

> Source unique de vérité visuelle pour tous les écrans frontend.
> Toute story qui produit une UI (s11, s16, s17, s19, s20, s22, s26…) **doit** réutiliser ces tokens et composants.
> Les écrans sont mockupés dans `docs/designs/<story-id>.md` (référence, pas code à copier) et implémentés via les composants `frontend/components/`.
> **Pas d'invention** : si un besoin n'est pas couvert ici, il devient un *gap* (cf. fin du document) qui sera comblé en s22 (a11y + UX pass) ou dans une nouvelle story.

## Tokens

### Couleurs (light mode, défaut)

| Token | Hex | Usage |
|---|---|---|
| `--color-primary` | `#3D5AFE` | Bouton primary, focus ring, bordure message user, logo "ktutor" (sur dark) |
| `--color-primary-strong` | `#1E2A8A` | Hover/active du primary, logo "ktutor" (sur light) |
| `--color-canvas` | `#FAFBFC` | Fond `body`, fond global |
| `--color-surface` | `#FFFFFF` | Cards, header, inputs, surface élevée |
| `--color-surface-subtle` | `#F4F6FA` | Hover bouton ghost, fond drop zone inactive, fond state subtle |
| `--color-border` | `#E2E6EE` | Bordures input, cards, séparateurs, séparateur de la bottom tab bar |
| `--color-text-primary` | `#0D0F14` | Texte principal, headings, body |
| `--color-text-secondary` | `#5B6472` | Légendes, labels, méta, sous-titres |
| `--color-text-tertiary` | `#8B95A3` | Placeholder input, hints, codes d'erreur en petit |
| `--color-accent-warm` | `#FF6B4A` | Réservé (badges promotionnels, états spéciaux — non utilisé en s11) |
| `--color-success` | `#16A34A` | Card succès (upload), icône `check-circle` |
| `--color-warning` | `#D97706` | Card warning OCR (manual_review_needed), label "Choisis un pseudo" |
| `--color-error` | `#DC2626` | Card erreur (upload, SSE, réseau), message d'erreur, bordure `aria-invalid` |
| `--color-info` | `#0284C7` | Réservé (notifications, info-bulles — non utilisé en s11) |

### Couleurs (dark mode, via `[data-theme="dark"]`)

| Token | Hex dark | Diff vs light |
|---|---|---|
| `--color-primary` | `#7B8CFF` | Plus clair (meilleur contraste sur fond sombre) |
| `--color-primary-strong` | `#3D5AFE` | Identique au primary light |
| `--color-canvas` | `#0D0F14` | Fond très sombre (≈ text-primary light, contraste inversé) |
| `--color-surface` | `#161A22` | Surface élevée (cards) |
| `--color-surface-subtle` | `#1E232E` | Hover / subtle |
| `--color-border` | `#2A2F3B` | Bordures discrètes |
| `--color-text-primary` | `#F4F6FA` | Texte principal (équivalent du canvas light) |
| `--color-text-secondary` | `#9AA3B2` | Méta |
| `--color-text-tertiary` | `#6B7484` | Placeholder / hints |
| `--color-accent-warm` | `#FF8B6F` | Plus saturé |
| `--color-success` | `#22C55E` | Vert plus vif |
| `--color-warning` | `#F59E0B` | Orange plus vif |
| `--color-error` | `#EF4444` | Rouge plus vif |
| `--color-info` | `#38BDF8` | Bleu cyan |

**Toggle dark/light** : hors-scope s11 (cf. ADR 006 + designs/s11 § 10 gaps). Le shell supporte déjà `data-theme` (cf. `frontend/app/globals.css` l. 36-52), le toggle UI arrive en s16 (dashboard). En attendant, on lit `prefers-color-scheme` (géré par le navigateur, fallback light).

### Typographie

- **Sans (UI)** : **Inter** (fallback `system-ui, sans-serif`). Variable font, weights 400 / 500 / 600 / 700.
- **Mono (code, formules)** : **JetBrains Mono** (utilisé pour les formules LaTeX éventuelles dans le chat, pas dans le mockup s11).
- **Échelle** (Tailwind defaults) :

| Classe Tailwind | px | Usage |
|---|---|---|
| `text-xs` | 12 | Légendes, codes d'erreur, labels de la bottom tab bar |
| `text-sm` | 14 | Labels de formulaire, sous-titres de Card header |
| `text-base` | 16 | Body, contenu principal |
| `text-lg` | 18 | Sous-titre de page (rare) |
| `text-xl` | 20 | Titre de section |
| `text-2xl` | 24 | Titre de page mobile |
| `text-3xl` | 30 | Titre de page tablette+, hero |

- **Line-height** : `1.5` pour le body, `1.2` pour les headings.
- **Letter-spacing** : `-0.011em` (tracking-tight) sur les headings (`text-2xl`+).
- **Font-weight** : `font-medium` (500) sur les boutons et labels, `font-semibold` (600) sur les titres, `font-bold` (700) sur le logo.

### Espacement (Tailwind scale)

| Token | px | Usage |
|---|---|---|
| `0.5` | 2 | Séparateur très fin |
| `1` | 4 | Icône dans badge |
| `1.5` | 6 | Padding inline court |
| `2` | 8 | Padding standard de composant |
| `2.5` | 10 | — |
| `3` | 12 | Padding card standard |
| `4` | 16 | Padding section |
| `6` | 24 | Padding conteneur mobile |
| `8` | 32 | Gap entre sections |
| `12` | 48 | — |
| `16` | 64 | — |
| `20` | 80 | — |
| `24` | 96 | Padding hero |

### Radius

| Token | px | Usage |
|---|---|---|
| `--radius-xs` | 4 | Petits badges, pills |
| `--radius-sm` | 6 | Boutons, inputs (défaut) |
| `--radius-md` | 8 | Cards (défaut) |
| `--radius-lg` | 12 | Modales (futur) |
| `--radius-xl` | 16 | — |
| `--radius-full` | 9999 | Avatar, pills langue (via `rounded-full` Tailwind) |

### Ombres (Tailwind `boxShadow`)

| Token | Définition | Usage |
|---|---|---|
| `shadow-kt-sm` | `0 1px 2px 0 rgba(13, 15, 20, 0.04)` | Subtile, presque imperceptible (rare) |
| `shadow-kt-default` | `0 2px 4px 0 rgba(13, 15, 20, 0.06), 0 1px 2px 0 rgba(13, 15, 20, 0.04)` | Cards standards, drop zone inactive |
| `shadow-kt-md` | `0 4px 12px 0 rgba(13, 15, 20, 0.08)` | Cards élevées, modales (futur) |
| `shadow-kt-lg` | `0 12px 32px 0 rgba(13, 15, 20, 0.12)` | Réservé (dropdowns, dialogs — s22+) |

### Icônes

- **Bibliothèque** : **Lucide** (open source, tree-shakable, support TypeScript).
- **Tailles** : 16px (inline), 20px (boutons icon-only), 24px (bottom tab bar, états de résultat).
- **Couleurs** : `currentColor` par défaut (suit la couleur du texte parent). Override possible via les tokens.
- **Icônes utilisées en s11** : `message-circle` (chat tab), `upload-cloud` (upload tab), `layout-dashboard` (dashboard tab, désactivé s11), `user` (profile tab, désactivé s11), `send` (bouton Envoyer), `x` (bouton Retirer fichier), `check-circle` (succès), `alert-circle` (warning), `alert-triangle` (erreur), `file-text` (PDF), `file-image` (image), `file` (txt), `chevron-down` (select natif), `globe` (language, optionnel).

## Available components

Tous les composants sont dans `frontend/components/`, un par fichier, props typées via interface exportée. Pas de logique métier dans un composant partagé.

| Composant | Fichier | Usage | Variantes / props clés |
|---|---|---|---|
| `<Button>` | `Button.tsx` | Action principale ou secondaire | `variant: 'primary' \| 'secondary' \| 'ghost' \| 'destructive'`, `size: 'sm' \| 'md' \| 'lg'`, focus ring + 44×44 px touch target par défaut |
| `<Card>` | `Card.tsx` | Surface élevée pour contenu groupé | Composé : `Card` (root), `Card.Header`, `Card.Body`, `Card.Footer`. bg-surface, border, rounded-md, shadow-kt-default |
| `<Input>` | `Input.tsx` | Champ texte ou fichier | `type: 'text' \| 'file'`, `invalid?: boolean` (bordure rouge + `aria-invalid`), `forwardRef`, hauteur 44 px (md) |
| `<Label>` | `Label.tsx` | Label accessible pour un input | `htmlFor: string`, `srOnly?: boolean` (label invisible vocalement, présent pour les screen readers) |
| `<Select>` | `Select.tsx` | Sélecteur natif (matière, langue, etc.) | Wrapper de `<select>` natif, `options: SelectOption[]`, `invalid?: boolean`, hauteur 44 px |
| `<FileUpload>` | `FileUpload.tsx` | Drop zone + input fichier (squelette s11a, complet s11c) | `accept?: string`, `maxSize?: number` (info, pas enforced), `onFileSelect: (file: File \| null) => void`, `label: string`, `helpText?: string`. Drop zone = `<label htmlFor>` focusable (jamais `<div onClick>`) |
| `<LanguageSwitcher>` | `LanguageSwitcher.tsx` | Pill toggle FR \| EN | `useLocale()` + `router.replace(pathname, { locale })`, `aria-pressed` sur le bouton actif |
| `<Header>` | `Header.tsx` | Header sticky 56 px | Logo, nav desktop (≥ 768 px), `<LanguageSwitcher>`, input pseudo, avatar initiale. Mirror du pseudo vers cookie `pseudo` via `useAuthStore` |
| `<StreamingMessage>` | `StreamingMessage.tsx` | Zone de réponse chat avec `aria-live` | `isStreaming: boolean`, `hasContent: boolean`, `children?: ReactNode`. `role="log"`, `aria-live="polite"`, `aria-busy`. Typing indicator 3 points (`animate-pulse`) quand streaming sans contenu |

### Stores Zustand (state global)

| Store | Fichier | Usage | Hydratation |
|---|---|---|---|
| `useAuthStore` | `lib/stores/authStore.ts` | `pseudo: string`, `setPseudo`, `clearPseudo`, `hydrate`. Mirror en cookie `path=/; max-age=30d; SameSite=Lax` (cf. ADR 011) | Client-side only, `hydrate()` après mount |
| `useChatStore` | `lib/stores/chatStore.ts` | **À venir (s11b)** — état du chat : messages, isStreaming, lastQuestion, send, retry, reset | Idem |
| `useUploadStore` | `lib/stores/uploadStore.ts` | **À venir (s11c)** — état de l'upload : selectedFile, subject, isUploading, lastResponse, lastError, upload, retry, reset | Idem |

## UI patterns

### Formulaires

- **Label toujours associé** : `<Label htmlFor="id-de-l-input">` systématique. `srOnly` uniquement quand un label visible ferait doublon (ex. : drop zone où le `<label htmlFor>` EST le label visible).
- **`<Input>` text** : hauteur 44 px (WCAG 2.5.5 touch target), `placeholder:text-text-tertiary`, `focus:border-primary` + `focus-visible:ring-2 focus-visible:ring-primary/30`.
- **`<Input>` file** : rendu `sr-only` (l'UI visible est composée par un `<label htmlFor>` qui déclenche le picker natif — cf. Piège #11 recherche).
- **`<Select>`** : wrapper de `<select>` natif. Keyboard et screen-reader accessibles par défaut.
- **Validation** : `invalid={true}` → bordure `border-error` + `aria-invalid="true"`. Le label d'erreur éventuel est rendu à part (sous le champ, `text-error text-sm`).
- **Bouton désactivé** : `disabled:opacity-50 disabled:cursor-not-allowed` (auto via Button). Pour les actions désactivées non-bouton (lien désactivé), utiliser `<span aria-disabled="true" tabindex="-1">` ou `<button disabled>` — **jamais** supprimer l'afford.
- **Pseudo** : regex `^[a-zA-Z0-9_]{3,32}$` alignée sur le service backend (`chroma_store.py:validate_pseudo`). Validation client = UX ; validation backend = sécurité.

### États (4 par écran + 1 chargement)

| État | Pattern |
|---|---|
| **Loading** (initial) | Pas de spinner plein-écran. Préférer skeleton loaders (futur, s22) ou laisser la page rendre immédiatement. Le store Zustand démarre vide et `hydrate()` après mount. |
| **Empty** | Message d'accueil centré + 2-3 exemples ou CTA. Pas de message "Aucun résultat" sec. |
| **Drag over** (s11c) | Drop zone `border-primary bg-primary/5` (couleurs primary à 5 % d'opacité). |
| **Streaming** (s11b) | `<StreamingMessage>` avec typing indicator 3 points (`animate-pulse`, désactivé via `prefers-reduced-motion`). Bouton "Envoyer" remplacé par bouton "Stop" (gap, hors-scope s11 — cf. s22). |
| **Succès** | `<Card>` `bg-success/10 border border-success/30`, icône `check-circle` Lucide 24px, message + recap. |
| **Warning** (manual_review_needed OCR) | `<Card>` `bg-warning/10 border border-warning/30`, icône `alert-circle`. |
| **Erreur** | `<Card>` `bg-error/10 border border-error/30`, icône `alert-triangle`. Code d'erreur machine en `text-xs text-text-tertiary` sous le message humain. |
| **Erreur réseau** | Idem erreur, message « Erreur réseau. Vérifie ta connexion. » + bouton « Réessayer ». |
| **Aucun pseudo** | Label `text-warning` au-dessus de la zone, input pseudo du header en `aria-invalid="true"`. Bouton d'action principal désactivé. |

### Feedback (toast vs inline)

- **s11 — inline uniquement** : pas de toast, pas d'`alert()`. Confirmation succès, erreur, warning : tous en Card inline sous la zone d'action. Cf. designs/s11-frontend-upload-chat.md § 10 gaps — le toast arrive en **s25**.
- **Sons, vibrations** : pas en s11. À reconsidérer en s22.

### Layout

- **Container mobile (≤ 768 px)** : `max-w-*` retiré, `px-4 py-4`, contenu full-width.
- **Container tablette (≥ 768 px)** : `max-w-3xl` (chat) ou `max-w-2xl` (upload) + `mx-auto` + `px-6`.
- **Header sticky** : hauteur 56 px, `bg-surface border-b border-border z-10`.
- **Bottom tab bar (mobile)** : hauteur 64 px, `bg-surface border-t border-border z-10`, 4 entrées icône 24 px + label `text-xs`. Visible ≤ 768 px uniquement.
- **Pas de scroll horizontal** : vérifier à 360 px et 768 px. Les grilles utilisent `grid-cols-1 md:grid-cols-2`, jamais de `overflow-x-scroll` au niveau page.

## Accessibilité (transverse, WCAG 2.1 A minimum)

- **Labels** : `<label htmlFor="...">` sur chaque input. Toujours. `srOnly` quand nécessaire mais jamais absent.
- **ARIA** : `aria-invalid` sur les inputs en erreur, `aria-busy` sur les zones de stream, `aria-live="polite"` sur `<StreamingMessage>`, `aria-pressed` sur les toggles (LanguageSwitcher), `aria-disabled="true"` + `tabindex="-1"` sur les actions désactivées.
- **Boutons icon-only** : `aria-label` systématique (`aria-label="Envoyer la question"`, `aria-label="Retirer le fichier"`, `aria-label="Prendre une photo avec la caméra"`, etc.).
- **Focus** : `:focus-visible` avec `outline: 2px solid var(--color-primary); outline-offset: 2px;` (cf. `frontend/app/globals.css`). Ne jamais supprimer l'outline sans remplacement.
- **Contraste** : AA (4.5:1) minimum. Les combinaisons `text-text-primary` sur `bg-surface` (15.3:1) et `text-text-secondary` sur `bg-surface` (7.0:1) sont validées. **Pas d'invention** : ne pas utiliser un texte tertiaire sur fond surface-subtle (contraste insuffisant).
- **Touch targets** : 44×44 px minimum partout (boutons md/lg, tab bar, sélecteur, drop zone).
- **Keyboard** : tout est navigable au Tab. La drop zone est focusable (`<label htmlFor>`), pas un `<div onClick>` (cf. Piège #11 recherche). Les actions désactivées sont `tabindex="-1"`, pas inaccessibles.
- **Reduced motion** : `prefers-reduced-motion: reduce` désactive l'`animate-pulse` du typing indicator, les transitions, le smooth scroll. Les animations restent présentes techniquement (pour les screen readers) mais à 0.01 ms.
- **axe-core** : 0 violation `critical` / `serious` sur les pages principales (chat, upload, dashboard, history). Test dans le CI via `@axe-core/playwright`.
- **Lighthouse a11y** : ≥ 90 sur `/`, `/chat`, `/upload`, `/dashboard/*`, `/history`. Config dans `frontend/lighthouserc.json`.

## Internationalisation (i18n)

- **Framework** : `next-intl` (App Router compatible).
- **Catalogues** : `frontend/messages/fr.json` (défaut) et `frontend/messages/en.json`.
- **Namespaces** (extensibles par story) : `common` (boutons, header, langue), `chat` (s11b), `upload` (s11c), `errors` (codes d'erreur), `dashboard` (s16+), etc.
- **Aucune string en dur** : `useTranslations('namespace')` partout. Vérifié par `frontend/scripts/check-i18n.sh` (exit 0 obligatoire en CI).
- **`<LanguageSwitcher>`** : pill toggle FR | EN, choix persisté via cookie `NEXT_LOCALE` (next-intl middleware). `useRouter().replace(pathname, { locale })`.
- **Format de date / nombre** : `Intl.NumberFormat(locale, options)` (taille fichier en MB), `Intl.DateTimeFormat(locale)` si une date apparaît.

## Do / Don't

### ✅ Do

- **Utiliser un token** pour chaque couleur, espacement, rayon, ombre, taille de texte. Pas de valeur en dur (`#3D5AFE` n'apparaît jamais dans un composant, sauf dans `globals.css`).
- **Utiliser un composant** du design system pour chaque UI. Pas de `<button className="bg-blue-500">` ad-hoc, toujours `<Button variant="primary">`.
- **Pair Label + Input / Select / FileUpload** systématiquement.
- **Annoncer les états de stream** via `aria-live="polite"` et `aria-busy`.
- **Respecter `prefers-reduced-motion`** dans toute animation.
- **Tester à 360 px et 768 px** systématiquement.
- **Écrire un commentaire en tête** de chaque nouveau composant partagé, qui pointe vers cette doc.
- **Ajouter le namespace i18n** correspondant (`messages/fr.json` + `messages/en.json`) en même temps que la page.

### ❌ Don't

- **Pas d'invention de tokens** : un nouveau token (ex. : `--color-accent-cool`) est ajouté dans `globals.css` ET listé ici en même temps. Pas de valeur hex en dur dans un composant.
- **Pas de `<div onClick>`** pour une action. Toujours un `<button>` ou un `<label htmlFor>` (pour la drop zone). Cf. Piège #11 recherche.
- **Pas de `disabled` muet** sur un lien : utiliser `aria-disabled="true"` + `tabindex="-1"` + `role="link"` si on doit garder la sémantique de lien.
- **Pas de string en dur** : `useTranslations('namespace')` toujours. Pas de `t('Hello')` en JSX sans import du hook.
- **Pas de `localStorage` pour l'identité** : utiliser le cookie `pseudo` (cf. ADR 011). `localStorage` casse le SSR et throw en private mode.
- **Pas de focus ring supprimé** sans remplacement : `focus:outline-none` est OK seulement si `focus-visible:ring-*` suit.
- **Pas de scroll horizontal** : `overflow-x-hidden` n'est pas une solution, c'est un symptôme. Corriger la cause (grille, padding, largeur fixe).
- **Pas d'EventSource** pour le SSE : utiliser `fetch().body.getReader()` (cf. ADR 006 + designs/s11 Piège #2).
- **Pas d'axios pour les streams** : `fetch` direct dans `chatStore.send`. Inversement, **pas de `fetch` pour l'upload** : `axios` gère `multipart/form-data` nativement (boundary auto).

## Gaps (design system gaps)

Items non couverts aujourd'hui, à traiter dans une story ultérieure (s22 a11y/UX pass, s25 toasts) ou en quick fix si trivial.

| Gap | Impact | Story qui le résoudra |
|---|---|---|
| Pas de `<Toast>` | UX : confirmation succès upload uniquement inline | **s25** (toasts in-app) |
| Pas de `<Avatar>` avec variations de teinte (6-8 hash de pseudo) | UX : avatar monochrome en attendant | **s17** (parent dashboard) ou s22 |
| Pas de `<Dialog>` / `<Modal>` | UX : pas de modale (confirmations, formulaires longs) | **s22** (UX pass) |
| Pas de `<Tabs>` | UX : impossible d'avoir des sous-sections | **s22** |
| Pas de `<Table>` | UX : listes structurées (history, evaluations) en cards | **s16** (dashboard) ou s22 |
| Pas de `<Chart>` | UX : graphiques de progression | **s16** (Recharts) |
| Pas de `<NotificationBell>` | UX : pas de badge de notifs non-lues | **s25** |
| Pas de toggle dark/light dans le header | Le shell supporte `data-theme` mais pas le toggle UI | **s16** ou s22 |
| Pas de `Skeleton` loader | UX : pas de feedback de chargement | **s22** |
| Pas d'empty state illustré (svg) | Texuel uniquement | **s22** |
| Pas de bouton "Stop" sur le stream SSE | UX : impossible d'interrompre l'agent | **s22** |
| Pas de bouton "Réessayer" sur "connexion perdue" SSE | UX : il faut refresh la page | **s22** |
| `<html lang>` dynamique | Hardcodé à `fr` actuellement (s11a minor #2) | **s22** ou s11b' |
| `output: "standalone"` manquant dans `next.config.ts` | EPERM Windows, Lighthouse peut demander la refacto | suivi s11b si Lighthouse en prod le demande |
| Capture caméra `capture="environment"` non garanti iOS Safari | Limitation navigateur | hors-scope (limitation navigateur) |
| Drift design `.doc` (s11c) | Le design suggère « PDF, DOC, image » mais le backend n'accepte que `.pdf, .png, .jpg, .jpeg, .txt` | design s11 à mettre à jour (story de maintenance) |

## Liens

- `frontend/app/globals.css` — source unique des tokens CSS (`@theme` + `:root` + `[data-theme="dark"]`).
- `frontend/tailwind.config.ts` — mapping des tokens vers les utility classes Tailwind.
- `frontend/components/*.tsx` — implémentation des composants partagés (un par fichier).
- `docs/designs/<story-id>.md` — écrans spécifiques par story (référence, pas code à copier).
- `docs/architecture.md` — patterns et conventions techniques (cf. § Frontend).
- `AGENTS.md` § Technical conventions — règles obligatoires (a11y, i18n, multi-tenancy).
- `ADR 006` — pourquoi Next.js App Router + Zustand + next-intl dès le départ.
- `ADR 011` — pourquoi pseudo en cookie + store Zustand hydraté, et migration JWT en s15.
- `CLAUDE.md` § Frontend — stack imposée.
