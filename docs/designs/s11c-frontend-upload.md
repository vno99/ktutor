# Design — Story s11c-frontend-upload

> Mockup statique HTML : `docs/designs/s11c-frontend-upload.html`. Référence visuelle, low-fidelity, **pas du code à copier**. L'implémentation réelle utilise les composants du design system (`<Header>`, `<Select>`, `<FileUpload>` étendu, `<Button>`, `<Card>`).
> Source unique de vérité visuelle : `docs/design-system.md`. Aucun token ou composant n'est inventé ici.
> Écrans conçus : **page `/upload`** uniquement, FR par défaut + EN, en mobile (360px) et tablette (768px+).
> Anchor points : `docs/research/s11c-frontend-upload.md` (5 structuring facts, 20 traps, 6 OQ).

## 1. Objectif et contexte

**Story** : s11c-frontend-upload — troisième split de s11 (sibling de s11b). L'élève doit pouvoir uploader un document depuis la page `/upload` en drag & drop, via le picker natif, ou via la caméra mobile. Le fichier est envoyé au backend (contrat s10, gelé) et la page affiche une card résultat selon la réponse HTTP.

**Anchor points** :
- Contrat API : `POST /api/documents/upload` (`backend/app/api/documents/router.py:81-196`) — 201 succès, 413/415/422/500 erreurs. `ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".txt"}` (`upload_service.py:39`). Taille max 20 MB (`core/config.py:67`).
- Composants à réutiliser : `<Header>` (réactivé), `<Select>`, `<FileUpload>` (étendu du squelette s11a), `<Button>` (4 variants × 3 sizes), `<Card>` (composé). Icônes Lucide (à ajouter aux deps — `lucide-react` absent du `package.json`, cf. recherche T3).
- Pattern page : répliquer `chat/page.tsx:34-42` (server entry + client subcomponent + `dynamic = "force-dynamic"`).

**Hors-scope explicite** :
- Multi-upload (un seul fichier à la fois) → PRD backend ne le supporte pas, hors-scope.
- Drag & drop multiple (plusieurs fichiers) → on prend le premier, on ignore les autres.
- Barre de progression réelle (`onUploadProgress` axios) → s22 (UX pass) ou s25 (toasts).
- Bouton « Annuler » pendant l'upload → s22.
- Prévisualisation du fichier (PDF first page, image thumbnail) → hors-scope, pas dans le PRD.
- OCR côté frontend (Tesseract.js) → non, délégation backend.
- Lien « Voir mes documents » dans la card succès → mort en s11c (s19 pas encore shippé), gap.
- Persistance de l'historique d'uploads côté frontend → s19 (history serveur).
- Upload réessayable automatique (retry exponential backoff) → le bouton « Réessayer » est manuel.
- `.doc` / `.docx` dans `accept` → drift design s11 (le backend n'accepte que `.pdf, .png, .jpg, .jpeg, .txt`), gap documenté design-system l.246, **PAS** corrigé en s11c (figé au contrat backend).

## 2. Composants du design system réutilisés

| Composant | Page | Source |
|---|---|---|
| `<Header>` (réactivé) | Layout `(public)/[locale]/layout.tsx` | `frontend/components/Header.tsx:23-139` — lien `/upload` perd `aria-disabled` + `tabIndex={-1}` |
| `<LanguageSwitcher>` (FR/EN, cookie-backed) | Header | design-system l.171 |
| `<Select>` (natif) | Upload page (matière) | `frontend/components/Select.tsx` — options Maths/Français |
| `<FileUpload>` (étendu du squelette s11a) | Upload page (drop zone) | `frontend/components/FileUpload.tsx:1-83` — squelette à compléter : drag & drop handlers, second input caméra (≤ 768px), transformation en Card une fois fichier sélectionné |
| `<Button>` variants primary, secondary, ghost | Envoyer, Retirer, Prendre une photo, Réessayer, Uploader un autre | `frontend/components/Button.tsx` — `size="md"` 44px, `size="sm"` 36px |
| `<Card>` (composé : Card / Card.Header / Card.Body / Card.Footer) | Cards résultat (succès, warning, erreur) | design-system l.159-162 — `bg-success/10 border-success/30` etc. |
| `<Label>` (`htmlFor` sur chaque input) | Sélecteur matière, drop zone, caméra | `frontend/components/Label.tsx` |
| Iconographie **Lucide** | file-text, file-image, file, x, check-circle, alert-circle, alert-triangle, upload-cloud | design-system l.113 — **dépendance à ajouter** : `lucide-react` |

**Aucun nouveau composant créé en s11c.** L'extension de `<FileUpload>` est in-place (le fichier existant).

## 3. Tokens utilisés (rappel exhaustif)

### Couleurs (light mode, défaut — dark via classe `dark:` que le shell supporte déjà)

| Token | Hex light | Usage dans le mockup |
|---|---|---|
| `--color-primary` | `#3D5AFE` | Focus ring, drop zone `border-primary bg-primary/5` pendant drag over, bouton primary, lien actif |
| `--color-primary-strong` | `#1E2A8A` | Logo "ktutor" (sur light), hover/active primary |
| `--color-canvas` | `#FAFBFC` | Fond `body` |
| `--color-surface` | `#FFFFFF` | Header, inputs, cards état (avec opacité 10% pour le fond) |
| `--color-surface-subtle` | `#F4F6FA` | Drop zone inactive, hover bouton ghost, intro mockup |
| `--color-border` | `#E2E6EE` | Bordures input, cards, séparateurs, mockup-cell border |
| `--color-text-primary` | `#0D0F14` | Texte principal, titre de page |
| `--color-text-secondary` | `#5B6472` | Sous-titre, label « Matière », nom fichier dans la Card |
| `--color-text-tertiary` | `#8B95A3` | Help text, code machine d'erreur en `text-xs` |
| `--color-success` | `#16A34A` | Card succès, icône `check-circle` |
| `--color-warning` | `#D97706` | Card warning OCR, label « Choisis un pseudo » |
| `--color-error` | `#DC2626` | Card erreur (toutes), message code 4xx/5xx, input `aria-invalid` |

### Typographie
- Sans (UI) : **Inter** (fallback `system-ui, sans-serif`).
- Mono (code) : **JetBrains Mono** (utilisé pour le `code` machine d'erreur en petit).
- Échelle : `text-xs 12px` (help, code), `text-sm 14px` (labels, sous-titre), `text-base 16px` (body, message card), `text-lg 18px` (h2 mockup-cell), `text-2xl 24px` (titre page mobile), `text-3xl 30px` (titre page tablette+).
- Line-height : `1.5` body, `1.2` headings, letter-spacing `-0.011em` sur `text-2xl`+.

### Espacement (Tailwind scale)
- `gap-2` (8px) entre label et input, entre les lignes de la card.
- `gap-3` (12px) entre icône et body dans la card.
- `gap-4` (16px) entre sections de la page (titre / sélecteur / drop zone / bouton / card).
- `px-4 py-4` mobile, `px-6 py-6` tablette.
- `p-3` (12px) padding Card standard.
- `mt-2` / `mt-3` (8px / 12px) marges internes à la card.

### Radius
- `--radius-sm 6px` : boutons, inputs.
- `--radius-md 8px` : cards résultat.
- `--radius-full 9999px` : avatar (déjà dans Header).

### Shadows
- `shadow-kt-default` (cards standard).
- Pas d'ombre sur la drop zone inactive (le border-dashed suffit).

## 4. Layout et structure

### 4.1. Structure de routes (réplique du pattern s11b)

```
app/
├── layout.tsx                          ← Root layout (data-theme, fonts, NextIntlClientProvider)
├── (public)/
│   └── [locale]/
│       ├── layout.tsx                  ← <Header /> + <main> (déjà livré s11a)
│       ├── page.tsx                    ← Home (déjà livré s11a)
│       ├── chat/
│       │   └── page.tsx                ← Page chat (livré s11b)
│       └── upload/                     ← NOUVEAU
│           ├── page.tsx                ← Server entry (locale + metadata)
│           └── UploadClient.tsx        ← Client component (form + cards)
```

### 4.2. Header (réactivation du lien `/upload`)

Cf. `Header.tsx:90-97`. Modifications s11c :
- **Retirer** `aria-disabled="true"` et `tabIndex={-1}` du lien `/upload`.
- Le lien devient un vrai `<Link href="/upload">` cliquable, full keyboard-accessible, focusable.
- Le test d'a11y Lighthouse / axe-core sur la page header continue de passer (les deux liens sont maintenant légitimes).

Le pseudo dans le header reste géré par `<Input>` (inchangé). L'avatar dérive toujours du pseudo via `pseudo.charAt(0).toUpperCase()`.

### 4.3. Page `/upload`

**Container** : `max-w-2xl mx-auto`, `px-4 md:px-6`, `py-4 md:py-6`. Plus étroit que le chat (`max-w-3xl`) car la page n'a pas de zone de stream longue.

**Sections** (de haut en bas) :
1. **Titre de page** (`text-2xl md:text-3xl font-semibold tracking-tight`) : « Uploader un document » (FR) / « Upload a document » (EN).
2. **Sous-titre** (`text-sm md:text-base text-text-secondary`) : « Choisis une matière, glisse ton fichier, le RAG s'en occupe. » (FR) / équivalent EN.
3. **Sélecteur de matière** (`<Select>` Maths / Français, 44px), `<Label>` au-dessus. Le placeholder « Choisir une matière » est la valeur `''` (default), comme dans s11b.
4. **Drop zone** (`<FileUpload>` étendu) : `<label htmlFor="upload-file">` visible, hauteur `min-h-48` (mobile) / `min-h-56` (tablette), `border-2 border-dashed border-border bg-surface-subtle`, focus visible `focus-within:ring-2 focus-within:ring-primary/30`. À l'intérieur : icône `upload-cloud` Lucide 32px en `text-text-tertiary` (centered), texte « Glisse ton fichier ici ou clique pour parcourir » (label prop), help text « PDF, image, texte (max 20 MB) » en `text-xs text-text-tertiary`. **Bouton « Prendre une photo »** : `<Button variant="secondary" size="sm">` avec icône Lucide (caméra, hors-design-system → à confirmer), visible **uniquement ≤ 768px** (`md:hidden`), déclenche un second input `<input type="file" accept="image/*" capture="environment">` masqué.
5. **Card « Fichier sélectionné »** (affichée à la place de la drop zone une fois un fichier choisi) : `<Card>` `bg-surface border border-border`, layout `flex items-start gap-3`. Icône Lucide à gauche : `file-text` pour `.pdf`, `file-image` pour `.png/.jpg/.jpeg`, `file` pour `.txt`. Texte à droite : nom du fichier (`text-sm font-medium text-text-primary`), taille en MB sous le nom (`text-xs text-text-tertiary`, formatée via `Intl.NumberFormat(locale, { maximumFractionDigits: 1 })`). Bouton « Retirer » à droite : `<Button variant="ghost" size="sm">` avec icône `x` Lucide, `aria-label="Retirer le fichier"`.
6. **Label « pseudo manquant »** (cf. AC11) : affiché en `text-warning text-sm` au-dessus de la drop zone quand `!isValidPseudo(pseudo)`. L'input pseudo du Header passe en `aria-invalid="true"`.
7. **Bouton « Envoyer »** : `<Button variant="primary" size="md">` 44×44 px minimum, `w-full md:w-auto` (full-width mobile, auto-width tablette). Icône `send` Lucide 20px à gauche du label. Désactivé tant que (pas de pseudo valide OU matière vide OU pas de fichier OU `isUploading`). État désactivé : `aria-disabled="true"` + `tabindex="-1"` + `disabled:opacity-50` (auto via Button). Pendant l'envoi : icône remplacée par un spinner Tailwind (`animate-spin` Lucide `loader-2` 20px), texte remplacé par « Envoi en cours… ».
8. **Card résultat** (cf. § 5 — apparaît une fois la réponse reçue, succès ou erreur) : `<Card>` `bg-{success|warning|error}/10 border border-{success|warning|error}/30 rounded-md p-4`, layout `flex items-start gap-3`. Icône Lucide 24px à gauche (`check-circle` / `alert-circle` / `alert-triangle`). Body à droite : titre en `text-base font-medium text-text-primary`, sous-titre en `text-sm text-text-secondary` (ex. « 12 chunks indexés » pour succès, message humain pour erreur). Code machine en `text-xs text-text-tertiary` sous le message (utile pour le debug). Bouton d'action en bas de la card (`<Button variant="secondary" size="sm">` ou `ghost`) : « Uploader un autre document » (succès/warning, reset le fichier mais keep subject + pseudo), « Réessayer » (erreurs 4xx/5xx avec retry pertinent, ré-émet la requête avec les mêmes paramètres).

### 4.4. États (4 par écran + 1 chargement + états dérivés)

| État | Déclencheur | Pattern |
|---|---|---|
| **Empty** (initial, sans fichier) | Au mount, avant 1ère sélection | Drop zone visible avec icône `upload-cloud` + label + help + bouton « Prendre une photo » (≤ 768px). Bouton « Envoyer » désactivé. |
| **Drag over** | `onDragOver` sur la drop zone, `isUploading === false` | Drop zone `border-primary bg-primary/5` (couleurs primary à 5% d'opacité). `e.preventDefault()` pour autoriser le drop. |
| **Drag leave** | `onDragLeave` (hors zone) | Drop zone revient à `border-border bg-surface-subtle`. |
| **Fichier sélectionné** (par n'importe quel moyen : picker, drop, caméra) | `onFileSelect(file)` non-null | Card « Fichier sélectionné » remplace la drop zone. Bouton « Envoyer » devient actif (si matière + pseudo valides). |
| **Soumettant** | `isUploading === true` | Bouton « Envoyer » en spinner + « Envoi en cours… », drop zone désactivée (pas de re-sélection, pas de drag & drop), boutons « Retirer » masqués. |
| **Succès** (201, `status: "indexed"`) | Réponse backend OK | Card succès `bg-success/10 border-success/30` + icône `check-circle` + « Document indexé : `nom.pdf` (12 chunks) » + bouton « Uploader un autre document ». |
| **MANUAL_REVIEW** (201, `status: "manual_review_needed"`) | Réponse backend OK avec OCR faible | Card warning `bg-warning/10 border-warning/30` + icône `alert-circle` + « Document enregistré, mais l'OCR est peu fiable. Un adulte doit le vérifier. » + bouton « Uploader un autre document ». |
| **Erreur 413** (taille) | `code: "invalid_file"`, status 413 | Card erreur `bg-error/10 border-error/30` + icône `alert-triangle` + « Fichier trop volumineux (max 20 MB). » + code `invalid_file` + bouton « Réessayer » (re-émet la requête). |
| **Erreur 415** (extension) | `code: "invalid_file"`, status 415 | Card erreur + « Extension non supportée. Formats acceptés : PDF, image, texte. » + code `invalid_file` + bouton « Réessayer » (le re-tentative ré-ouvre le picker car le fichier est invalide). |
| **Erreur 422 `invalid_pseudo`** | `code: "invalid_pseudo"`, status 422 | Card erreur + « Pseudo invalide. Recharge la page. » + code + bouton « Réessayer ». |
| **Erreur 422 `ocr_failure`** | `code: "ocr_failure"`, status 422 | Card erreur + « Échec de l'OCR. Le fichier est trop dégradé pour être lu. » + code + **pas de bouton Réessayer** (re-tentative inutile). |
| **Erreur 500 `storage_failure`** | `code: "storage_failure"`, status 500 | Card erreur + « Erreur serveur. Réessaie dans quelques minutes. » + code + bouton « Réessayer ». |
| **Erreur réseau** | `apiClient.post` rejette avant HTTP | Card erreur + « Erreur réseau. Vérifie ta connexion. » + bouton « Réessayer ». |
| **Aucun pseudo** | `!isValidPseudo(pseudo)` | Label `text-warning text-sm` au-dessus de la drop zone, input header `aria-invalid="true"`, bouton « Envoyer » désactivé. |

## 5. Responsive (360px smartphone + 768px tablette)

### 5.1. Mobile (≤ 768px)

- **Header** : 56px, logo + `<LanguageSwitcher>` + input pseudo + avatar. Liens desktop Chat/Upload **toujours masqués** sur mobile (la bottom tab bar n'est pas livrée en s11, gap design-system l.232 ; s11c ne change pas ça).
- **Container** : `px-4 py-4`, pas de `max-w-*` (le contenu occupe toute la largeur).
- **Titre de page** : `text-2xl` (24px).
- **Drop zone** : full-width, `min-h-48` (192px), bouton « Prendre une photo » **visible** sous la drop zone (`md:hidden`).
- **Card fichier sélectionné** : layout `flex flex-col gap-3` (icône au-dessus, nom + taille, bouton « Retirer » en dessous full-width), pas de row horizontal.
- **Bouton « Envoyer »** : full-width, hauteur 44px.
- **Card résultat** : layout `flex flex-col gap-3` (icône au-dessus, body, bouton en dessous full-width).
- **Touch targets** : 44×44 px minimum partout (boutons, drop zone, sélecteur, tab bar).

### 5.2. Tablette+ (≥ 768px)

- **Header** : 56px, logo + liens Chat/Upload (texte) + `<LanguageSwitcher>` + input pseudo + avatar. Les deux liens sont maintenant cliquables.
- **Container** : `max-w-2xl mx-auto`, `px-6 py-6`.
- **Titre de page** : `text-3xl` (30px).
- **Drop zone** : centrée dans le `max-w-2xl`, plus haute `min-h-56` (224px), bouton « Prendre une photo » **masqué** (la capture se fait via l'attribut `capture` du picker principal, ou via le seul bouton « Choisir un fichier »).
- **Card fichier sélectionné** : layout `flex flex-row items-center gap-3` (icône à gauche, nom + taille au centre, bouton « Retirer » à droite, aligné à droite).
- **Bouton « Envoyer »** : auto-width, aligné à droite.
- **Card résultat** : layout `flex flex-row items-start gap-3` (icône à gauche, body au centre, bouton à droite aligné en bas).

### 5.3. Vérification

- Pas de scroll horizontal à 360px ni à 768px.
- Tous les touch targets ≥ 44×44 px.
- Test Playwright (AC15) couvre les deux viewports.

## 6. Accessibilité (WCAG 2.1 A minimum)

- **Labels** : `<Label htmlFor="upload-subject">` sur le sélecteur, `<Label htmlFor="upload-file">` sur la drop zone (le `<label htmlFor>` EST la drop zone — c'est l'afford visible, pas un `<div onClick>`). Le second input caméra est `sr-only` (jamais visible), déclenché par le bouton « Prendre une photo » qui a un `aria-label="Prendre une photo avec la caméra"`.
- **Aria** :
  - `aria-describedby="upload-file-help"` lie la drop zone au texte d'aide « max 20 MB ».
  - `aria-invalid="true"` sur l'input pseudo du Header quand le cookie est vide (déjà câblé, juste la propagation à ajouter dans la page upload).
  - `aria-busy="true"` sur la drop zone pendant `isUploading` (info screen reader).
  - `aria-disabled="true"` + `tabindex="-1"` sur le bouton « Envoyer » désactivé (cf. design-system l.228).
  - `aria-label="Retirer le fichier"` sur le bouton ghost qui porte l'icône `x` (sinon NVDA/JAWS lisent « button » seul).
  - `aria-label="Prendre une photo avec la caméra"` sur le bouton caméra (idem).
- **Focus** : `focus-within:ring-2 focus-within:ring-primary/30 focus-within:ring-offset-2 focus-within:ring-offset-canvas` sur la drop zone. `:focus-visible` sur tous les boutons. Ne jamais supprimer l'outline.
- **Contraste** : toutes les combinaisons `text-*` sur `bg-*` respectent AA. `text-text-primary` sur `bg-surface` (15.3:1) et `text-text-secondary` sur `bg-surface` (7.0:1) sont validées (cf. design-system l.184). `text-error/strong` sur `bg-error/10` est validé visuellement.
- **Touch targets** : 44×44 px partout.
- **Keyboard** : tout est navigable au Tab. La drop zone est focusable (`<label htmlFor>`), pas un `<div onClick>`. Tab → drop zone → Sélecteur → Bouton Envoyer → Card résultat (bouton Réessayer / Uploader un autre). Le drag & drop est un enhancement (le clavier marche via le label, Espace/Entrée ouvre le picker).
- **Reduced motion** : `prefers-reduced-motion: reduce` désactive le `animate-spin` du spinner d'envoi. Les animations restent techniquement présentes (pour les screen readers) mais à 0.01 ms.
- **axe-core** : 0 violation `critical` / `serious` sur `/fr/upload` et `/en/upload`. Test dans le CI via `@axe-core/playwright` (ajout à `frontend/e2e/upload.spec.ts`).
- **Lighthouse a11y** : ≥ 90 sur `/fr/upload` (assertion CI). **Nécessite d'étendre `lighthouserc.json`** avec `http://localhost:3000/fr/upload` au tableau `collect.url` (cf. recherche T7). Sans cette extension, l'AC14 n'est pas vérifié en CI.

## 7. i18n

- **Catalogues** : `frontend/messages/fr.json` (défaut) et `frontend/messages/en.json`. Le namespace `upload` (vide en s11a/s11b) est rempli par s11c avec **20+ clés** :
  - `upload.title` — « Uploader un document » / « Upload a document »
  - `upload.subtitle` — sous-titre d'intro
  - `upload.subjectLabel` — « Matière » / « Subject »
  - `upload.dropZoneLabel` — « Glisse ton fichier ici ou clique pour parcourir » / « Drop your file here or click to browse »
  - `upload.dropZoneHelp` — « PDF, image, texte (max 20 MB) » / « PDF, image, text (max 20 MB) »
  - `upload.chooseFile` — « Choisir un fichier » / « Choose a file » (utilisé en fallback si la drop zone n'est pas trouvable)
  - `upload.takePhoto` — « Prendre une photo » / « Take a photo »
  - `upload.send` — « Envoyer » / « Send »
  - `upload.sending` — « Envoi en cours… » / « Uploading… »
  - `upload.removeFile` — « Retirer » / « Remove » (avec `{name}` pour aria-label)
  - `upload.fileSize` — `{size} MB` (paramétré)
  - `upload.noPseudo` — « Choisis un pseudo pour commencer » / « Choose a pseudo to start »
  - `upload.success` — « Document indexé : {name} ({chunks} chunks) »
  - `upload.manualReview` — « Document enregistré, mais l'OCR est peu fiable. Un adulte doit le vérifier. »
  - `upload.uploadAnother` — « Uploader un autre document » / « Upload another document »
  - `upload.retry` — « Réessayer » / « Retry »
  - `upload.error413` — « Fichier trop volumineux (max 20 MB). »
  - `upload.error415` — « Extension non supportée. Formats acceptés : PDF, image, texte. »
  - `upload.errorInvalidPseudo` — « Pseudo invalide. Recharge la page. »
  - `upload.errorOcrFailure` — « Échec de l'OCR. Le fichier est trop dégradé pour être lu. »
  - `upload.errorStorageFailure` — « Erreur serveur. Réessaie dans quelques minutes. »
  - `upload.errorNetwork` — « Erreur réseau. Vérifie ta connexion. »
  - `upload.errorCode` — « Code : {code} » (sous le message d'erreur)
- **Pas de hardcoded strings** : `useTranslations('upload')` partout dans `UploadClient.tsx` et `FileUpload.tsx` (étendu). Vérifié par `frontend/scripts/check-i18n.sh` (exit 0 obligatoire en CI, AC15).
- **Format de taille** : `Intl.NumberFormat(useLocale(), { maximumFractionDigits: 1 })` (cf. design-system l.198). La locale next-intl est lue via `useLocale()` du hook.
- **Toggle FR/EN** : `<LanguageSwitcher>` (déjà livré s11a) persiste le choix via cookie `NEXT_LOCALE`. La page upload est re-rendue automatiquement par next-intl middleware (réplique du comportement `/chat`).

## 8. Mockup HTML

Le mockup statique est dans `docs/designs/s11c-frontend-upload.html`. Il illustre les **7 états critiques** côte à côte sur grand écran, empilés sur mobile :

1. **Empty** (état initial, drop zone vide, sans fichier, sans matière, bouton Envoyer désactivé).
2. **Drag over** (drop zone `border-primary bg-primary/5`, fichier simulé survolant).
3. **Fichier sélectionné** (Card avec icône + nom + taille, bouton « Retirer »).
4. **Soumettant** (bouton « Envoyer » en spinner, drop zone désactivée).
5. **Succès** (Card `bg-success/10 border-success/30` + `check-circle` + recap chunks + bouton « Uploader un autre document »).
6. **MANUAL_REVIEW** (Card `bg-warning/10 border-warning/30` + `alert-circle` + message + bouton « Uploader un autre document »).
7. **Erreur 413** (Card `bg-error/10 border-error/30` + `alert-triangle` + message + code + bouton « Réessayer »).

Le mockup utilise **uniquement** des tokens CSS du design system (variables `--color-*`, classes Tailwind décrites dans `docs/design-system.md`). Les icônes Lucide sont inlinées en SVG (data-uri ou chemins tirés de la lib open source) puisque `lucide-react` n'est pas encore installé — c'est une dépendance à ajouter par l'implémentation, pas par le mockup.

**Statut du mockup** : c'est une **référence** pour l'implémentation, pas du code à coller. Le code de production utilise les composants maison (`<Button>`, `<Input>`, `<FileUpload>`, `<Card>`) importés depuis `frontend/components/`.

## 9. Design system gaps (à noter pour follow-ups)

| Gap | Impact | Story qui le résoudra |
|---|---|---|
| `lucide-react` n'est pas installé dans `package.json` (alors que la design system liste 8 icônes pour l'upload) | Implémentation impossible sans commit de dépendance | **s11c** (commit `pnpm add lucide-react` + lockfile, plan task) |
| Icône caméra (pour le bouton « Prendre une photo ») absente de la liste design-system l.113 | Le bouton a une icône attendue par l'AC2 mais elle n'est pas documentée | **s22** (UX pass) ou ajout design-system |
| Pas de bottom tab bar (mobile) | Navigation mobile passe par les liens desktop du Header (≥ 768px) uniquement, à 360px l'utilisateur n'a pas de next step | **s16** (dashboard) ou **s22** (design-system gap l.232) |
| Pas de toast d'upload réussi | UX : confirmation inline uniquement | **s25** (toasts) |
| Pas de lien « Voir mes documents » dans la card succès | UX : pas de next step après upload | **s19** (history) |
| Pas de barre de progression réelle (`onUploadProgress` axios) | UX : pas de feedback pendant l'upload, juste un spinner | **s22** (UX pass) ou **s25** (toasts) |
| Pas de bouton « Annuler » pendant l'upload | UX : impossible d'interrompre | **s22** |
| `<html lang>` reste hardcodé à `fr` | Mineur, hors-scope s11c | **s22** ou **s11b'** |
| `output: "standalone"` omis dans `next.config.ts` | EPERM Windows, Lighthouse peut demander la refacto | suivi s11b si Lighthouse en prod le demande |
| Drift design `.doc` (s11c originel) | Le design suggère « PDF, DOC, image » mais le backend n'accepte que `.pdf, .png, .jpg, .jpeg, .txt` | **figé en s11c** (gap connu, design l.246) — la story suit le contrat backend, pas le mockup original |
| `capture="environment"` non garanti sur tous les navigateurs mobiles (Chrome Android ignore `capture="user"` depuis 2024, Firefox Android ne supporte pas) | Sur certains mobiles, l'utilisateur ne peut pas prendre de photo | hors-scope (limitation navigateur) |
| Pas d'avatar variations (6-8 teintes uniques par hash de pseudo) | Avatar monochrome | **s17** (parent dashboard) ou **s22** |
| Empty states non illustrés (svg) | Texte uniquement, pas d'illustration | **s22** |

## 10. Liens

- `docs/stories.md:527-609` — story s11c (16 ACs, complexity 2, agentic notes, traps, OQs, out-of-scope).
- `docs/research/s11c-frontend-upload.md` — recherche complète (5 structuring facts, 20 traps T1-T20, 6 OQ, anchor points).
- `docs/design-system.md` — source unique de vérité visuelle (258 lignes).
- `docs/designs/s11-frontend-upload-chat.md:139-156, 189-193` — design original de `/upload` (référence, drift `.doc` documenté l.246).
- `docs/designs/s11b-frontend-chat.md` — sibling story, pattern page (`max-w-3xl` pour le chat, ici `max-w-2xl` pour l'upload).
- `backend/app/api/documents/router.py:81-210` — contrat s10 (handler + mapping UploadError → HTTP).
- `backend/app/api/documents/schemas.py:35-72` — `UploadResponse` + `UploadErrorResponse`.
- `backend/app/services/rag/upload_service.py:39` — `ALLOWED_EXTENSIONS`.
- `frontend/lib/api.ts:18-23` — `apiClient` (axios, sans Content-Type forcé).
- `frontend/lib/stores/authStore.ts:17, 19-21` — regex pseudo, `isValidPseudo()`.
- `frontend/lib/stores/chatStore.ts:74-86, 91-93` — pattern Zustand + hydratation.
- `frontend/components/FileUpload.tsx:1-83` — squelette à étendre.
- `frontend/components/Header.tsx:90-97` — lien `/upload` à réactiver.
- `frontend/lighthouserc.json:7-10` — à étendre avec `/fr/upload`.
- `frontend/messages/{fr,en}.json:42` — namespace `upload` vide à remplir.
- `frontend/app/(public)/[locale]/chat/page.tsx:34-42` — pattern server entry à répliquer.
- `AGENTS.md` § Frontend + Multi-tenancy — conventions obligatoires.
- `ADR 006` (Next.js + Zustand + i18n) + `ADR 011` (pseudo cookie pré-JWT).
- `templates/design-screen.md` — structure de ce fichier.
