# Design — s11-frontend-upload-chat

> Mockup statique HTML : `docs/designs/s11-frontend-upload-chat.html`. Référence visuelle pour `/ks-execute` (puis `/ks-plan`).
> Tous les tokens viennent de `docs/design-system.md` (cf. ADR 006). Aucune valeur inventée.
> Écrans conçus : **page `/chat`**, **page `/upload`**, **header partagé (FR/EN + pseudo)**, **état d'erreur SSE**, **état d'erreur upload**.

## 1. Objectif et contexte

**Story** : s11-frontend-upload-chat — première story frontend. L'élève doit pouvoir uploader un document et chatter avec l'agent depuis un navigateur, sur smartphone (360px) ou tablette (768px+), en français (défaut) ou en anglais.

**Anchor points** (issus de `docs/research/s11-frontend-upload-chat.md`) :
- `POST /api/chat/stream` → SSE `text/event-stream` avec `data: {token|done+sources|error+code}` (`backend/app/api/chat/router.py:64-133`).
- `POST /api/documents/upload` → multipart `pseudo`+`subject`+`file`, 201/413/415/422/500 (`backend/app/api/documents/router.py:81-196`).
- CORS déjà configuré pour `http://localhost:3000` (`backend/app/main.py:62-66`).

**Hors-scope explicite** :
- Authentification (s12-s15). Le `pseudo` vit dans un cookie posé par l'utilisateur (input header).
- Dashboard élève/parent/admin (s16+).
- Historique des conversations (s19).
- Toasts (s25) — les messages d'erreur sont **inline** en s11.
- Toast d'upload réussi (s25) — confirmation **inline** sur la page upload.
- Toggle dark/light (s16) — le shell s11 supporte déjà la classe `dark:` mais le toggle arrive plus tard.
- shadcn/ui (décision non tranchée, hors-scope s11 — composants maison).
- Indicateur « Stop » sur le stream SSE : ajouté dans une story ultérieure (s11 trap appelle « Stop » mais l'AC7 ne le demande pas explicitement ; on le note en gap).

## 2. Composants du design system réutilisés

Tous les composants sont **déjà spécifiés** dans `docs/design-system.md` § Available components. Aucun nouveau composant n'est inventé pour cette story.

| Composant | Page | Source |
|---|---|---|
| `<Header>` (logo + pseudo + `<LanguageSwitcher>`) | Layout `(public)/[locale]/layout.tsx` | design-system § Composants signature |
| `<LanguageSwitcher>` (FR/EN, cookie-backed) | Header | design-system l.171, l.252 |
| `<Button>` variants primary, secondary, ghost | chat + upload | design-system l.158, l.180 |
| `<Input>` (text, file) | header (pseudo), upload (file) | design-system l.159, l.182 |
| `<Label>` (`htmlFor` sur chaque input) | header, chat, upload | design-system l.160, l.241 |
| `<Card>` (header / body / footer) | chat (réponse), upload (résultat) | design-system l.161, l.181 |
| `<Select>` (natif `<select>`) | chat + upload (matière) | design-system l.166 |
| `<FileUpload>` (drag & drop + caméra) | upload | design-system l.169 |
| `<StreamingMessage>` (`aria-live="polite"`) | chat | design-system l.170, l.185 |
| Iconographie Lucide | header (chevron), upload (file), chat (send) | design-system l.189 |

**Composants cibles non utilisés en s11** (référencés pour mémoire) : `<Toast>`, `<Avatar>`, `<Tabs>`, `<Dialog>`, `<Table>`, `<Chart>`, `<NotificationBell>`.

## 3. Tokens utilisés (rappel exhaustif)

### Couleurs (light mode uniquement pour le mockup — dark via classe `dark:`)

| Token | Hex light | Usage dans le mockup |
|---|---|---|
| `--color-primary` | `#3D5AFE` | Bouton primary, focus ring, bordure message user |
| `--color-primary-strong` | `#1E2A8A` | Logo "ktutor" |
| `--color-canvas` | `#FAFBFC` | Fond `body` |
| `--color-surface` | `#FFFFFF` | Cards, header, inputs |
| `--color-surface-subtle` | `#F4F6FA` | Hover bouton ghost, fond drop zone inactive |
| `--color-border` | `#E2E6EE` | Bordures input, cards, séparateurs |
| `--color-text-primary` | `#0D0F14` | Texte principal |
| `--color-text-secondary` | `#5B6472` | Légendes, labels, méta |
| `--color-text-tertiary` | `#8B95A3` | Placeholder input pseudo |
| `--color-error` | `#DC2626` | Message d'erreur inline |
| `--color-success` | `#16A34A` | Confirmation upload réussi |

### Typographie

- Sans (UI) : **Inter** (fallback `system-ui, sans-serif`).
- Mono (code) : **JetBrains Mono** (utilisé pour les formules éventuelles dans le chat, pas dans ce mockup).
- Échelle : `xs 12px`, `sm 14px`, `base 16px`, `lg 18px`, `xl 20px`, `2xl 24px`, `3xl 30px`.
- Line-height : `1.5` body, `1.2` headings, letter-spacing `-0.011em` sur headings.

### Espacement (Tailwind scale)

`px`, `0.5` (2px), `1` (4px), `1.5` (6px), `2` (8px), `2.5` (10px), `3` (12px), `4` (16px), `6` (24px), `8` (32px), `12` (48px), `16` (64px), `20` (80px), `24` (96px).

### Radius

`sm 6px` (boutons, inputs), `md 8px` (cards), `full 9999px` (pills langue).

### Shadows

`sm 0 1px 2px 0 rgba(13,15,20,0.04)` (cards subtiles), `default 0 2px 4px ...` (cards standards), `md 0 4px 12px ...` (modale, hors-scope s11).

## 4. Layout et structure

### 4.1. Structure de routes (Next.js App Router, ADR 006)

```
app/
├── layout.tsx                          ← Root layout (data-theme, fonts, NextIntlClientProvider)
├── (public)/
│   └── [locale]/
│       ├── layout.tsx                  ← <Header /> + <main> + bottom tab bar (mobile)
│       ├── page.tsx                    ← Home (mini-hero + 2 CTAs)
│       ├── chat/
│       │   └── page.tsx                ← Page chat
│       └── upload/
│           └── page.tsx                ← Page upload
```

Justification `(public)` : la story dit `(auth-less)`, mais la convention Next.js la plus lisible est `(public)` (cf. recherche Q3). Le story note `(auth-less)` est indicatif ; le split en `(public)` est sémantiquement équivalent et respecte ADR 006 (`(auth)` = login/register, `(dashboard)` = protégé).

### 4.2. Header partagé (layout `(public)/[locale]/layout.tsx`)

- **Hauteur** : 56px (sticky, `bg-surface`, `border-b` 1px, `z-10`).
- **Composition** (de gauche à droite, sur la même ligne) :
  1. **Logo "ktutor"** (text, font-bold, `text-text-primary-strong`).
  2. **Lien Chat** + **Lien Upload** (desktop ≥ 768px, cachés sur mobile, remplacés par bottom tab bar).
  3. **Spacer** (`flex-1`).
  4. **`<LanguageSwitcher>`** (pill toggle FR | EN, `radius-full`).
  5. **Input pseudo** (`<Label>` invisible visuellement mais `sr-only`, `<Input>` text court, max 32 chars).
  6. **Avatar initiales** (`<Avatar>` 32px, fond `--color-primary`, texte blanc) — la couleur de fond est dérivée du hash du pseudo (cf. recherche D5).

### 4.3. Bottom tab bar (mobile ≤ 768px)

- **Hauteur** : 64px, sticky bottom, `bg-surface`, `border-t` 1px.
- **4 entrées** (icônes Lucide 24px + label `xs 12px`) :
  1. **Chat** (icône `message-circle`).
  2. **Upload** (icône `upload-cloud`).
  3. **Dashboard** (icône `layout-dashboard`) — désactivé en s11, `text-text-tertiary`, `aria-disabled="true"`.
  4. **Profil** (icône `user`) — désactivé en s11.

### 4.4. Page `/chat`

- **Container** : `max-w-3xl mx-auto`, `px-4 md:px-6`, `py-4`.
- **Header de page** : titre "Chat" (`text-2xl font-semibold tracking-tight`), sous-titre "Choisis une matière, pose une question, la réponse arrive en temps réel." (`text-sm text-text-secondary`).
- **Sélecteur de matière** : `<Select>` natif (Maths / Français), `mt-6`.
- **Zone de stream** : `<StreamingMessage>` (cf. § 4.5).
- **Champ de saisie** : `<Input>` (multiline `<textarea>`, `rows=3`, `max-w-full`), bouton **Envoyer** (`<Button>` primary, icône `send` Lucide) collé à droite, hauteur 44px (touch target).
- **Bouton "Stop"** : apparaît uniquement quand `isStreaming=true`. `<Button>` variant secondary, icône `square` Lucide. Note : non demandé par l'AC mais mentionné comme Piège #1 dans la recherche ; **hors-scope s11**, à noter en gap.

### 4.5. `<StreamingMessage>` (composant signature)

- Le chat n'est **pas** un système de bulles à la Messenger.
- Le chat est un **flux vertical** :
  - **Message user** : `border-l-2 border-primary pl-4 py-2` (bordure gauche 2px), pas de fond distinct.
  - **Message assistant** : texte courant avec curseur clignotant en fin de mot (3 petits cercles animés tant que `isStreaming=true` et aucun chunk reçu), puis accumulation des tokens en `text-base text-text-primary`.
  - **Sources** (sur événement `done`) : ligne en dessous, `text-xs text-text-secondary`, format "Sources : `fichier1.pdf` (chunk 3), `fichier2.pdf` (chunk 1)".
- **a11y** : `aria-live="polite"` sur la zone, `aria-busy={isStreaming}`.

### 4.6. Page `/upload`

- **Container** : `max-w-2xl mx-auto`, `px-4 md:px-6`, `py-4`.
- **Header de page** : titre "Uploader un document" + sous-titre.
- **Sélecteur de matière** : `<Select>` Maths / Français.
- **`<FileUpload>`** (composant signature) :
  - **État vide** : drop zone `border-2 border-dashed border-border bg-surface-subtle`, hauteur `min-h-48`, message central "Glisse ton fichier ici ou clique pour parcourir" + bouton "Choisir un fichier" (`<Button>` secondary) + petit texte "PDF, DOC, image (max 20 MB)".
  - **État avec fichier** : la drop zone devient une `Card` avec icône `file-text` (PDF) ou `file-image` (image), nom du fichier, taille en MB, bouton "Retirer" (`<Button>` ghost).
  - **État soumettant** : spinner Tailwind, bouton "Envoyer" désactivé.
- **Bouton "Envoyer"** : `<Button>` primary, plein largeur sur mobile, désactivé tant que pas de fichier + matière + pseudo.
- **Résultat** (en dessous, après soumission) :
  - **Succès** : `Card` `bg-success/10 border border-success/30`, icône `check-circle` Lucide, texte "Document indexé : `nom.pdf` (12 chunks)". Lien "Voir mes documents" (s19, lien mort en s11 — note en gap).
  - **MANUAL_REVIEW** : `Card` `bg-warning/10 border border-warning/30`, icône `alert-circle` Lucide, texte "Document enregistré, mais l'OCR est peu fiable. Un adulte doit le vérifier."
  - **Erreur (taille 413)** : `Card` `bg-error/10 border border-error/30`, icône `alert-triangle`, texte + bouton "Réessayer" (`<Button>` ghost).
  - **Erreur (extension 415)** : idem, message "Extension non supportée. Formats acceptés : PDF, DOC, image."
  - **Erreur (validation 422)** : idem, message selon le `code` reçu.

### 4.7. Home `/`

- **Container** : `max-w-2xl mx-auto`, `py-16`, centré.
- **Hero** : titre `text-3xl font-semibold tracking-tight` "Bienvenue sur ktutor", sous-titre `text-base text-text-secondary` "Un assistant IA pour réviser, uploader tes cours et chatter avec tes agents."
- **2 CTAs** (stacked mobile, side-by-side tablette ≥ 768px) :
  - "Commencer à chatter" → `/chat` (`<Button>` primary).
  - "Uploader un document" → `/upload` (`<Button>` secondary).

## 5. États (4 états par écran + états de stream)

### 5.1. Page `/chat`

| État | Pattern |
|---|---|
| **Loading** (initial) | Pas applicable : la page rend immédiatement, le store Zustand démarre vide. |
| **Empty** (avant la première question) | Zone de stream vide, message d'accueil centré "Pose ta première question." + 2-3 exemples de questions. |
| **Streaming** | Indicateur typing (3 cercles `animate-pulse`) tant que `isStreaming=true` et aucun token. Puis accumulation de tokens avec curseur clignotant en fin. Bouton "Envoyer" remplacé par bouton "Stop" (gap, hors-scope s11). |
| **Succès** (done) | Sources affichées sous la réponse, format discret. |
| **Erreur SSE** (`error` event reçu) | Message inline rouge dans la zone de stream : icône `alert-triangle` + message + code (`text-xs text-text-tertiary`). Pas de toast. |
| **Connexion perdue** (stream coupé avant `done`) | Message inline "Connexion perdue. Réessayer ?" + bouton "Réessayer" (gap, hors-scope s11 — l'AC ne le demande pas, mais le story trap le mentionne). |
| **Erreur réseau** (`fetch` rejette) | Message inline "Erreur réseau. Vérifie ta connexion." |
| **Aucun pseudo** (cookie vide) | L'input pseudo du header est mis en évidence `aria-invalid="true"`, label "Choisis un pseudo pour commencer" au-dessus de la zone de stream. |

### 5.2. Page `/upload`

| État | Pattern |
|---|---|
| **Loading** (initial) | Pas applicable : la page rend immédiatement. |
| **Empty** (avant sélection fichier) | Drop zone avec message d'invite. |
| **Drag over** | Drop zone `border-primary bg-primary/5`. |
| **Fichier sélectionné** | Card avec nom + taille + bouton "Retirer". |
| **Soumettant** | Spinner, bouton "Envoyer" désactivé, texte "Envoi en cours…". |
| **Succès** (201) | Card succès avec récap. |
| **MANUAL_REVIEW** (201, `chunks_count=0`) | Card warning. |
| **Erreur 413** (taille) | Card erreur : "Fichier trop volumineux (max 20 MB)." |
| **Erreur 415** (extension) | Card erreur : "Extension non supportée. Formats acceptés : PDF, DOC, image." |
| **Erreur 422** (pseudo invalide / OCR) | Card erreur : message du backend. |
| **Erreur 500** (S3 / DB) | Card erreur : "Erreur serveur. Réessaie dans quelques minutes." + bouton "Réessayer". |

## 6. Responsive (360px smartphone + 768px tablette)

### 6.1. Mobile (≤ 768px)

- **Header** : 56px, logo + `<LanguageSwitcher>` + input pseudo + avatar (les liens Chat/Upload sont dans la bottom tab bar).
- **Bottom tab bar** : 64px, 4 entrées.
- **Container** : `px-4`, `py-4`, pas de `max-w-*` (le contenu occupe toute la largeur).
- **Header de page** : titre `text-2xl`, sous-titre `text-sm`.
- **`<FileUpload>`** : full-width.
- **Bouton "Envoyer"** : full-width, hauteur 44px.
- **Touch targets** : 44×44 px minimum partout (boutons, tab bar, sélecteur).

### 6.2. Tablette+ (≥ 768px)

- **Header** : 56px, logo + liens Chat/Upload (texte) + `<LanguageSwitcher>` + input pseudo + avatar. **Pas de bottom tab bar** (la nav du header suffit).
- **Container** : `max-w-3xl` (chat) ou `max-w-2xl` (upload), `mx-auto`, `px-6`.
- **Header de page** : titre `text-3xl`, sous-titre `text-base`.
- **`<FileUpload>`** : centré dans le `max-w-2xl`, drop zone plus haute (`min-h-56`).
- **Bouton "Envoyer"** : auto-width (aligné à droite du champ de saisie).

### 6.3. Vérification

- Pas de scroll horizontal à 360px ni à 768px.
- Tous les touch targets ≥ 44×44 px.
- Test Playwright (recherche AC6 + AC7) couvre les deux viewports.

## 7. Accessibilité

- **Labels** : `<label htmlFor="pseudo">` sur l'input pseudo, `<label htmlFor="subject">` sur le sélecteur, `<label htmlFor="question">` sur la textarea, `<label htmlFor="file">` sur l'input file (caché visuellement mais `sr-only`, le bouton "Choisir un fichier" est un `<label htmlFor="file">` qui le déclenche — Piège #11 recherche).
- **Aria** :
  - `<StreamingMessage>` : `aria-live="polite"`, `aria-busy={isStreaming}`.
  - Boutons icon-only : `aria-label="Envoyer la question"`, `aria-label="Retirer le fichier"`, etc.
  - Drop zone : `aria-label="Zone de dépôt de fichier"`, `aria-describedby="file-help"`.
  - Liens désactivés (Dashboard, Profil en s11) : `aria-disabled="true"`, `tabindex="-1"`.
- **Focus** : `focus:ring-2 focus:ring-primary/30 focus:ring-offset-2 focus:ring-offset-canvas` sur tous les interactifs. Ne jamais supprimer l'outline.
- **Contraste** : toutes les combinaisons `text-*` sur `bg-*` respectent AA (vérifié sur le design-system l.239). Le test bite : `axe-core` sur les deux pages, 0 violation critique.
- **Touch targets** : 44×44 px minimum (cf. responsive).
- **Keyboard** : tout est navigable au Tab. La drop zone est focusable (button), pas un `<div onClick>` (Piège design-system l.273).
- **Reduced motion** : `prefers-reduced-motion: reduce` désactive le `animate-pulse` du typing indicator et le curseur clignotant.

## 8. i18n

- **Catalogues** : `frontend/messages/fr.json` (défaut) et `frontend/messages/en.json`.
- **Namespaces** : `common` (boutons, header, langue), `chat` (page chat), `upload` (page upload), `errors` (codes d'erreur).
- **Pas de hardcoded strings** : `useTranslations('chat')` partout. Vérifié par règle ESLint custom (cf. design-system l.251).
- **`<LanguageSwitcher>`** : pill toggle `FR | EN`, choix persisté en cookie `NEXT_LOCALE` (next-intl middleware). Au clic, `router.replace(pathname, { locale: nextLocale })`.
- **Format de date / nombre** : `Intl.NumberFormat(locale)` pour la taille des fichiers (MB), `Intl.DateTimeFormat(locale)` si une date apparaît (pas le cas en s11).

## 9. Mockup HTML

Le mockup statique est dans `docs/designs/s11-frontend-upload-chat.html`. Il illustre :

1. **Header** (sticky 56px) avec logo, `<LanguageSwitcher>`, input pseudo, avatar.
2. **Page `/chat`** en mobile (360px) et tablette (768px) — 3 états : empty, streaming, succès avec sources.
3. **Page `/upload`** en mobile et tablette — 4 états : empty, fichier sélectionné, succès, erreur (taille).
4. **État d'erreur SSE** (chat) — message inline rouge avec icône.

Le mockup utilise **uniquement** des tokens CSS du design system (variables `--color-*`, classes Tailwind décrites dans `docs/design-system.md`). Les icônes Lucide sont inlinées en SVG.

**Statut du mockup** : c'est une **référence** pour l'implémentation, pas du code à coller. Le code de production utilise les composants maison (`<Button>`, `<Input>`, etc.) importés depuis `frontend/components/`.

## 10. Design system gaps (à noter pour follow-ups)

| Gap | Impact | Story qui le résoudra |
|---|---|---|
| Pas de bouton "Stop" sur le stream | UX : l'utilisateur ne peut pas interrompre un agent qui boucle | s22 (a11y + UX pass) |
| Pas de bouton "Réessayer" sur "connexion perdue" SSE | UX : l'utilisateur doit rafraîchir la page | s22 |
| Pas de toast d'upload réussi | UX : confirmation uniquement inline | s25 (toasts) |
| Lien "Voir mes documents" mort en s11 (s19 pas encore shippé) | UX : l'utilisateur n'a pas de next step | s19 (history) |
| Toggle dark/light absent du header | Le shell supporte `dark:` mais le toggle arrive en s16 | s16 (dashboard) |
| `capture="environment"` non garanti sur iOS Safari | Le story trap le suppose mais l'API ne marche pas sur tous les navigateurs | hors-scope (limitation navigateur) |
| Pas d'avatar variations (6-8 teintes uniques par hash de pseudo) | Design-system l.290 | s17 (parent dashboard) |
| Empty states non illustrés (texte seul) | Design-system l.291 — decision reportée | s22 (illustrations) |

## 11. Liens

- `docs/stories.md:409-447` — story s11 (AC + agentic notes + traps).
- `docs/research/s11-frontend-upload-chat.md` — recherche complète, anchor points, split proposal.
- `docs/design-system.md` — tokens et composants (source unique).
- `docs/decisions/006-frontend-nextjs-app-router.md` — verrouille Next.js + i18n + a11y dès le départ.
- `docs/architecture.md` § Frontend — stack imposée.
- `templates/design-screen.md` — squelette (n'existe pas dans le repo, structure libre).
