---
name: research-s11c-frontend-upload
description: Research report for the third split of s11 — `/upload` page with drag & drop, camera capture, multipart upload and result cards.
---

# Research — Story s11c-frontend-upload

> Worktree : `C:\Workspace\ktutor\.worktrees\s11c-frontend-upload` · branche `feature/s11c-frontend-upload` · HEAD `094123e` (= `origin/main` post s11b).
> Stories ready : `yes` (cf. `docs/reviews/stories.md`).

## The five structuring facts

1. **`POST /api/documents/upload` est gelé** : `backend/app/api/documents/router.py:81-196`, contrat Pydantic dans `schemas.py:35-72`. HTTP 201 sur succès (avec `status: "indexed" | "manual_review_needed"`), 413 (taille), 415 (extension), 422 (pseudo/OCR), 500 (stockage). Le `code` est l'un de `invalid_pseudo | invalid_file | ocr_failure | storage_failure` — **le frontend doit combiner HTTP status + code** pour discriminer 413 vs 415 (les deux portent `code: "invalid_file"`).
2. **`<FileUpload>` est un SQUELETTE livré en s11a** (`frontend/components/FileUpload.tsx:1-83`) : juste un `<label htmlFor>` qui déclenche le picker natif. Le drag & drop, le bouton caméra, la transformation en Card une fois un fichier sélectionné, sont **à ajouter en s11c**. Le pattern « `<input>` sr-only + `<label htmlFor>` visible » est imposé par Piège #11 (cf. design-system l.273) et reste obligatoire.
3. **Le namespace i18n `upload` est vide** (`frontend/messages/fr.json:42` et `en.json:42` : `"upload": {}`). Toutes les chaînes de la page et de la card résultat sont à créer — pas d'i18n à reprendre d'un autre écran.
4. **Le store `useUploadStore` n'existe PAS** : seuls `authStore` (cookie-backed, ADR 011) et `chatStore` (SSE, livré s11b) sont présents. Le contrat de l'état est imposé par l'AC11 : `{selectedFile, subject, isUploading, lastResponse, lastError, selectFile, clearFile, upload, retry, reset}` + flag `hydrated`. Hydratation client-side only via `hydrate()`.
5. **Le lien `/upload` du Header est actuellement désactivé** (`Header.tsx:90-97` : `aria-disabled="true" tabIndex={-1}`). La story doit le réactiver en supprimant ces deux attributs (Retour s11a Minor #1).

## Target story

**s11c-frontend-upload — Page /upload avec drag & drop (split 3/3, gated by s11a)** (`docs/stories.md:527-609`).

> **As an** élève **I want** uploader un document depuis l'interface web **so that** il soit indexé dans mon RAG.

Complexity storyboard : **2** (Page `/upload` + `<FileUpload>` complet + axios multipart + carte résultat selon code HTTP). Pas d'OCR côté frontend, pas d'upload multiple, pas de barre de progression.

**16 ACs** (cf. `docs/stories.md:537-555`) :
- AC1 — Route `/{locale}/upload` + sélecteur matière + `<FileUpload>` + bouton Envoyer 44×44 px, tous via `useTranslations('upload')`.
- AC2 — `<FileUpload>` étendu : picker natif (déjà câblé) + drag & drop + caméra mobile (second input `capture="environment"`, visible ≤ 768px), `accept=".pdf,.png,.jpg,.jpeg,.txt"` (aligné backend).
- AC3 — Drag over change l'apparence (`border-primary bg-primary/5`), `e.preventDefault()` sur dragover et drop.
- AC4 — Fichier sélectionné → `<Card>` avec icône Lucide + nom + taille MB (1 décimale) + bouton « Retirer » (ghost, `x` Lucide, `aria-label="Retirer le fichier"`).
- AC5 — Bouton « Envoyer » désactivé tant que pas de pseudo valide + matière + fichier. `aria-disabled="true"` + `tabindex="-1"`.
- AC6 — `POST /api/documents/upload` via `apiClient` (axios) avec `FormData` 3 champs : `pseudo`, `subject`, `file`. Pas de `Content-Type` manuel (axios gère le boundary).
- AC7 — Pendant l'envoi : spinner + texte « Envoi en cours… » + bouton désactivé + drop zone désactivée.
- AC8 — Cas succès : `status: "indexed"` → card success, `status: "manual_review_needed"` → card warning. Bouton « Uploader un autre document » reset (clear file, keep subject, keep pseudo).
- AC9 — Cas erreur 4xx/5xx : 5 sous-cas (413, 415, 422 invalid_pseudo, 422 ocr_failure, 500 storage_failure), tous avec card `bg-error/10 border-error/30` + icône `alert-triangle` + `code` en `text-xs text-text-tertiary` + bouton « Réessayer » quand pertinent.
- AC10 — Erreur réseau (apiClient reject) : message inline + bouton « Réessayer ».
- AC11 — Aucun pseudo : label `text-warning` au-dessus de la `<FileUpload>`, input header en `aria-invalid="true"`, bouton Envoyer désactivé.
- AC12 — `useUploadStore` Zustand avec le contrat imposé.
- AC13 — Responsive 360px (full-width, bouton caméra visible) / 768px (`max-w-2xl mx-auto`, bouton caméra masqué). Pas de scroll horizontal.
- AC14 — axe-core 0 critical/serious sur `/fr/upload` et `/en/upload` ; Lighthouse a11y ≥ 90 sur `/fr/upload`.
- AC15 — Tests e2e ≥ 4 cas dans `frontend/e2e/upload.spec.ts` (rend les contrôles, stub 201 indexed, stub 413, stub 415, stub 201 manual_review_needed). Le test (b) vérifie le payload `FormData` (3 champs `pseudo` / `subject` / `file`).
- AC16 — `bash frontend/scripts/check-i18n.sh` exit 0, lint + typecheck + build + e2e verts.
- AC17 (méta) — Commentaire en tête de `uploadStore.ts` référençant le contrat s10.

## Current state of the code

### Fichiers à créer (4)
| Fichier | Rôle | Lignes attendues |
|---|---|---|
| `frontend/app/(public)/[locale]/upload/page.tsx` | Server entry (locale + metadata), délègue à `<UploadClient />`. Pattern exact de `chat/page.tsx:34-42`. | ~30 |
| `frontend/app/(public)/[locale]/upload/UploadClient.tsx` | Client component : `<Header>`-aware, `<Select>` matière, `<FileUpload>`, bouton Envoyer, card résultat. | ~180 |
| `frontend/lib/stores/uploadStore.ts` | Zustand store : `selectedFile, subject, isUploading, lastResponse, lastError, hydrated, selectFile, clearFile, upload, retry, reset, hydrate`. | ~140 |
| `frontend/e2e/upload.spec.ts` | ≥ 4 tests Playwright + 2 a11y scans. | ~180 |

### Fichiers à modifier (4)
| Fichier | Modification | Lignes ciblées |
|---|---|---|
| `frontend/components/FileUpload.tsx` | Étendre le squelette : props `onFileSelect(file)` reçoit un `File` ou `null`, support drag & drop (state local `isDragOver`), bouton caméra conditionnel (visible ≤ 768px, second input `<input type="file" accept="image/*" capture="environment">` masqué), transformation en Card une fois fichier sélectionné. **Conserver le pattern `<input>` sr-only + `<label htmlFor>` visible** (Piège #11). | tout le fichier, 83 → ~180 |
| `frontend/messages/fr.json` | Remplir `"upload": {}` (l.42) : `title`, `subtitle`, `subjectLabel`, `dropZoneLabel`, `dropZoneHelp`, `chooseFile`, `takePhoto`, `send`, `sending`, `removeFile` (avec `{name}`), `fileSize` (avec `{size}`), `noPseudo`, `success` (avec `{name}`, `{chunks}`), `manualReview`, `uploadAnother`, `retry`, `error413` (avec `{maxSize}`), `error415`, `errorInvalidPseudo`, `errorOcrFailure`, `errorStorageFailure`, `errorNetwork`, `errorCode` (avec `{code}`). | l.42 + ajouts 16-20 |
| `frontend/messages/en.json` | Idem en anglais. | l.42 + ajouts |
| `frontend/lighthouserc.json` | Ajouter `http://localhost:3000/fr/upload` (et `en/upload` si symétrie) au tableau `collect.url` (l.7-10). | l.7-10 |
| `frontend/components/Header.tsx` | Retirer `aria-disabled="true"` et `tabIndex={-1}` du lien `/upload` (l.93-94). | l.90-97 |

### Fichiers à NE PAS toucher (contrat respecté)
- `frontend/lib/api.ts` — `apiClient` déjà configuré avec `Accept: application/json` (l.21-22), ne pas ajouter d'interceptor qui forcerait le Content-Type. Le `FormData` + axios fait le reste.
- `frontend/lib/stores/authStore.ts` — le `pseudo` vient de là, déjà en cookie, regex `^[a-zA-Z0-9_]{3,32}$` exposée via `isValidPseudo()`.
- `backend/app/**` — l'API est stable (s10 merged `ff21046`), la story est front-only.

### Inventaire frontend livré (rappel s11a + s11b)
- Composants partagés : `Button.tsx` (4 variants × 3 sizes), `Card.tsx` (Header/Body/Footer), `Input.tsx` (text/file, `forwardRef`, `invalid` prop), `Label.tsx` (`htmlFor`, `srOnly`), `Select.tsx` (natif, `options`/`value`/`onChange`), `LanguageSwitcher.tsx` (FR|EN pill), `Header.tsx` (sticky 56px, nav desktop, pseudo, avatar), `FileUpload.tsx` (squelette), `StreamingMessage.tsx` (chat uniquement), `Textarea.tsx` (chat uniquement, pas requis par s11c).
- Stores : `authStore.ts` (pseudo cookie), `chatStore.ts` (SSE).
- API : `lib/api.ts` (axios `apiClient`), `lib/api/chat.ts` (SSE parser, non utilisé par s11c).
- Routes : `app/(public)/[locale]/layout.tsx` (Header + NextIntlClientProvider), `app/(public)/[locale]/page.tsx` (Home), `app/(public)/[locale]/chat/{page,ChatClient}.tsx` (chat).
- Tests : `chatStore.test.ts`, `StreamingMessage.test.tsx`, `Textarea.test.tsx`, `e2e/{chat,home,pseudo,responsive}.spec.ts` (11 tests s11a + 7 tests s11b = 18 verts, à ne PAS régresser).
- i18n : `fr.json` (52 l.), `en.json` (51 l.) — namespace `upload` vide à remplir.

## Anchor points

### Backend (contrat s10, stable)
- `backend/app/api/documents/router.py:81-196` — handler `POST /upload` (status 201, Form params, 3 niveaux de défense taille, mapping `UploadError → HTTP`).
- `backend/app/api/documents/router.py:199-210` — `_status_for_upload_error` : `INVALID_PSEUDO → 422`, `INVALID_FILE → _map_invalid_file_to_status` (413 ou 415 selon message), `OCR_FAILURE → 422`, `STORAGE_FAILURE → 500`.
- `backend/app/api/documents/router.py:66-78` — `_map_invalid_file_to_status` : message contient « extension ... non supportée » → 415, sinon 413.
- `backend/app/api/documents/schemas.py:35-72` — `UploadResponse` (201) et `UploadErrorResponse` (4xx/5xx), codes alignés avec `UploadErrorKind`.
- `backend/app/services/rag/upload_service.py:39` — `ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".txt"}` (5 extensions, **PAS de `.doc` ni `.docx`**).
- `backend/app/core/config.py:67` — `max_upload_size_mb: int = 20`.

### Frontend (intégration)
- `frontend/lib/api.ts:18-23` — `apiClient` axios avec `baseURL = NEXT_PUBLIC_API_URL ?? "http://localhost:8000"` et header `Accept: application/json`. **Le store upload doit utiliser `apiClient.post('/api/documents/upload', formData)` SANS toucher aux headers** (Piège #1, l'AC6 le rappelle).
- `frontend/lib/stores/authStore.ts:17, 19-21` — `PSEUDO_PATTERN = /^[a-zA-Z0-9_]{3,32}$/`, export `isValidPseudo()`. Le bouton « Envoyer » vérifie `isValidPseudo(useAuthStore.getState().pseudo)`.
- `frontend/lib/stores/chatStore.ts:74-86, 91-93` — pattern Zustand : `useXxxStore = create<XxxState>((set, get) => ({...}))`, hydrate() no-op, lecture du pseudo via `useAuthStore.getState().pseudo` (pas depuis un hook).
- `frontend/components/FileUpload.tsx:1-83` — squelette à étendre. Props actuelles : `id?, name?, accept?, maxSize?, required?, describedBy?, onFileSelect: (file) => void, label, helpText?`.
- `frontend/components/Header.tsx:90-97` — lien `/upload` à réactiver (retirer `aria-disabled` + `tabIndex={-1}`).
- `frontend/messages/{fr,en}.json:42` — namespace `upload` vide à remplir.
- `frontend/lighthouserc.json:7-10` — tableau `url` à étendre avec `http://localhost:3000/fr/upload`.
- `frontend/app/(public)/[locale]/chat/page.tsx:34-42` — pattern server entry : `dynamic = "force-dynamic"`, `generateMetadata` avec `getTranslations('chat')`, `setRequestLocale(locale)`, rend `<ChatClient />`. **À répliquer à l'identique pour `/upload`**.

## Verified APIs / functions

| Élément | Vérifié | Signature / comportement |
|---|---|---|
| `apiClient` | ✓ `frontend/lib/api.ts:18-23` | `axios.create({ baseURL, headers: { Accept: "application/json" } })`. Retourne un AxiosInstance. `apiClient.post(url, FormData)` envoie multipart avec boundary auto. |
| `useAuthStore.getState().pseudo` | ✓ `authStore.ts:52-70` | Synchrone, lit le state Zustand actuel. `pseudo: string` (vide si cookie vide). |
| `isValidPseudo(value)` | ✓ `authStore.ts:19-21` | Regex `^[a-zA-Z0-9_]{3,32}$`. Retourne `true`/`false`. |
| `useAuthStore.getState().hydrate()` | ✓ `authStore.ts:55-59` | Lit le cookie, set `pseudo` + `hydrated: true`. No-op côté serveur. |
| `useChatStore.getState().hydrate()` | ✓ `chatStore.ts:83-85` | No-op, juste set `hydrated: true`. Pattern à répliquer pour `useUploadStore`. |
| `<FileUpload>` props | ✓ `FileUpload.tsx:20-30` | `onFileSelect: (file: File \| null) => void` déjà câblé (l.74-77). Le store appelle `selectFile(file)`. |
| `<Button variant="ghost" size="sm" aria-label="...">` | ✓ `Button.tsx:13-37, 39-65` | Pattern « Retirer fichier » et « Réessayer » et « Uploader un autre document ». |
| `<Card>` | ✓ `Card.tsx:43-47` | Composé : `Card`, `Card.Header`, `Card.Body`, `Card.Footer`. Classes pour les états : `bg-success/10 border-success/30`, `bg-warning/10 border-warning/30`, `bg-error/10 border-error/30` (cf. design-system l.159-162). |
| `<Select>` | ✓ `Select.tsx:26-41` | `options: { value, label }[]`, `value`, `onChange`. Pattern « Matière : Maths / Français » répliqué depuis `ChatClient.tsx:89-100`. |
| `Intl.NumberFormat(locale, { maximumFractionDigits: 1 })` | à utiliser | Format MB (design-system l.198). Locale lu depuis `useLocale()` de next-intl. |
| `lucide-react` | ✗ **NON INSTALLÉ** | Liste dans design-system l.108-113 mais absent de `frontend/package.json`. **À ajouter aux dependencies**. |
| `axios.post('/api/documents/upload', FormData)` | ✓ contrat | 201 succès, 4xx/5xx avec body `{error, code}`. Codes : `invalid_pseudo | invalid_file | ocr_failure | storage_failure`. |
| HTTP status 413 | ✓ `router.py:117-124, 131-138` | `code: "invalid_file"`, message « Fichier trop volumineux. ». |
| HTTP status 415 | ✓ `router.py:66-78, 86-87` | `code: "invalid_file"`, message « Extension ... non supportée ». |
| HTTP status 422 `invalid_pseudo` | ✓ `router.py:201-202` | `code: "invalid_pseudo"`. |
| HTTP status 422 `ocr_failure` | ✓ `router.py:205-206` | `code: "ocr_failure"`. |
| HTTP status 500 `storage_failure` | ✓ `router.py:207-208` | `code: "storage_failure"`. |
| HTTP 201 `status: "indexed"` | ✓ `schemas.py:42-44` | `chunks_count > 0`, `ocr_confidence: float \| None`. |
| HTTP 201 `status: "manual_review_needed"` | ✓ `schemas.py:42-44` | `chunks_count === 0` (par convention, OCR confiance < seuil). |
| `capture="environment"` iOS Safari | ✓ (limitation navigateur) | Respecté. Chrome Android ignore `capture="user"` mais respecte `capture="environment"`. Firefox Android : non supporté. **Piège #5 design, pas un blocker.** |

## Traps & constraints

### P0 (bloquants)
- **T1 (P0) — `Content-Type` NE DOIT PAS être forcé** : `apiClient.post('/api/documents/upload', formData)` sans toucher aux headers. Axios détecte `FormData` et ajoute `Content-Type: multipart/form-data; boundary=...` automatiquement. Tout override explicite casse le boundary et le backend rejette en 422. Documenter dans le commentaire du store (cf. AC17). Source : `frontend/lib/api.ts:21-23`, AC6 ligne 544.
- **T2 (P0) — `e.preventDefault()` obligatoire sur `onDragOver`** : sans ça, le navigateur ouvre le fichier au lieu de dropper. Idem sur `onDrop` (consommer l'event). Le test e2e qui simule un drop ne fonctionnera pas sinon. Source : Piège #3 recherche s11.
- **T3 (P0) — `lucide-react` absent du `package.json`** : la design system liste 8 icônes pour l'upload (file-text, file-image, file, x, check-circle, alert-circle, alert-triangle, upload-cloud). Aucune n'est importée aujourd'hui. **Le plan doit explicitement ajouter `lucide-react` aux dependencies** (`pnpm add lucide-react` dans la worktree, mettre à jour `pnpm-lock.yaml`, commit). Sans ça, le build casse.
- **T4 (P0) — Mapping HTTP status + code, pas seulement code** : 413 et 415 portent tous deux `code: "invalid_file"`. Le frontend doit discriminer sur `response.status` (cf. `router.py:199-210`). Source : AC9 ligne 547.
- **T5 (P0) — `<label htmlFor>` reste la drop zone, pas un `<div onClick>`** : le drag & drop est un enhancement par-dessus le label focusable. Le clavier (Tab → Espace/Entrée) doit continuer à ouvrir le picker. Source : `FileUpload.tsx:52-66`, Piège #11, design-system l.273.

### P1 (importants)
- **T6 (P1) — Lien `/upload` du Header à réactiver** : `Header.tsx:90-97` a `aria-disabled="true"` et `tabIndex={-1}`. La story doit retirer ces deux attributs. Source : Retour s11a Minor #1, AC Header.
- **T7 (P1) — Lighthouse a11y ≥ 90 sur `/fr/upload`** : nécessite **d'étendre `lighthouserc.json`** (ajouter `http://localhost:3000/fr/upload` au tableau `url`). Sans ça, l'AC14 ne sera pas vérifié en CI. Source : AC14 ligne 553, design-system l.189.
- **T8 (P1) — Drop pendant upload** : si l'utilisateur drop un fichier pendant `isUploading=true`, on ignore. Le store doit bloquer `selectFile(file)` ou le composant doit early-return. Source : Piège #12.
- **T9 (P1) — `Intl.NumberFormat` avec 1 décimale forcée** : sans `maximumFractionDigits: 1`, un fichier de `1.234567 MB` s'affiche tel quel. Le test e2e (b) peut stubber `2.5 MB` et vérifier l'affichage. Source : AC4 ligne 542, Piège #6.
- **T10 (P1) — `accept` aligné sur `ALLOWED_EXTENSIONS`** : `accept=".pdf,.png,.jpg,.jpeg,.txt"`. **PAS de `.doc` ni `.docx`** dans `accept`. Le design suggère « PDF, DOC, image » dans `designs/s11-frontend-upload-chat.md:145, 191` mais le backend n'accepte pas `.doc` (gap documenté design-system l.246). Source : Piège recherche s11 #2, AC2.
- **T11 (P1) — Discrimination `status: "manual_review_needed"` vs `chunks_count === 0`** : utiliser `status` (pas `chunks_count === 0`) pour afficher la card warning. Le contrat actuel a `chunks_count === 0` quand `status === "manual_review_needed"`, mais c'est une coïncidence — un futur changement backend pourrait renvoyer `indexed` avec 0 chunks. Source : `schemas.py:42-44`, Trap spécifique MANUAL_REVIEW dans stories.md.
- **T12 (P1) — Multi-tenant : `pseudo` du store, jamais du FormData** : `useAuthStore.getState().pseudo` est la source unique. Le store passe le pseudo à l'API dans le FormData, pas via un input utilisateur. Source : AGENTS.md § Multi-tenancy.
- **T13 (P1) — CORS déjà configuré** : `backend/app/main.py:62-66` autorise `http://localhost:3000`. Pas de modification backend.
- **T14 (P1) — `<html lang>` reste `fr`** : gap design-system l.243, hors-scope s11c.

### P2 (rappels)
- **T15 (P2) — `dynamic = "force-dynamic"` sur la page** : stateful (Zustand + FormData), pas de prerender (cf. `chat/page.tsx:9`).
- **T16 (P2) — `pnpm run test` = typecheck + lint + unit + e2e** : le test e2e upload s'ajoute aux 18 existants (s11a + s11b). Doit passer sans régresser.
- **T17 (P2) — `frontend/scripts/check-i18n.sh` exit 0** : pas de string en dur dans `UploadClient.tsx`, `uploadStore.ts`, `FileUpload.tsx` (étendu). Toute chaîne passe par `useTranslations('upload')` ou `useTranslations('errors')` si code d'erreur mappé.
- **T18 (P2) — `useTranslations` dans un composant client** : pattern next-intl + `'use client'`. Le `page.tsx` server appelle `setRequestLocale(locale)` puis rend `<UploadClient />`.
- **T19 (P2) — `useTranslations('errors')` pour les codes d'erreur 4xx/5xx** : déjà câblé dans s11b (`fr.json:43-50`, `en.json:43-50`). L'upload store peut mapper `code → tErrors(code)`. Pour les messages spécifiques à l'upload (taille max, extension, etc.), utiliser `useTranslations('upload')`.
- **T20 (P2) — `Intl.NumberFormat` avec locale next-intl** : `const locale = useLocale(); const fmt = new Intl.NumberFormat(locale, { maximumFractionDigits: 1 });`. Formatte `{fmt.format(sizeMb)} MB`.

## Open questions

- **Q1 — `accept="image/*"` ou `"image/*;capture=environment"` pour le second input ?** : l'AC2 dit « second input `<input type="file" accept="image/*" capture="environment">` ». Le `accept="image/*"` autorise png/jpg/jpeg, OK. Pas de question ouverte, c'est spécifié. **À fermer au plan : importer le second input comme un composant interne à `FileUpload` ou dans un nouveau mini-composant `<CameraCapture>` ?** Le pattern actuel du store upload est d'avoir une seule source de vérité (`selectedFile`), donc le second input peut vivre dans `FileUpload` et appeler `onFileSelect`. Recommandation : `<CameraCapture>` interne (sous-dossier `frontend/components/upload/` ou inline dans `FileUpload.tsx`).
- **Q2 — `data-testid` pour les tests e2e ?** : l'AC15 ne le mentionne pas. Le pattern s11b utilise les `getByLabel`, `getByRole`, `getByText` (cf. `chat.spec.ts:30-45`). À répliquer. **Recommandation : pas de `data-testid`, utiliser les selectors accessibles.**
- **Q3 — Comportement du bouton « Réessayer » sur erreur 415 ?** : l'AC9(b) dit « le re-tentative ré-ouvre le picker car le fichier est invalide ». Le store doit `selectFile(null)` puis déclencher le picker (via `inputRef.current?.click()` côté composant). À clarifier en plan : le store expose-t-il un flag `shouldReopenPicker` que le composant observe, ou le composant gère-t-il ça localement ? **Recommandation : état local au composant (`useRef<HTMLInputElement>` + `useEffect` sur `lastError?.code === "invalid_file"` et 415).**
- **Q4 — Le `subject` doit-il être réinitialisé après « Uploader un autre document » ?** : l'AC8 dit « clear file, keep subject, keep pseudo ». Le store doit appeler `clearFile()` (pas `reset()`) + ne pas toucher à `subject` et `pseudo`. À vérifier en plan.
- **Q5 — Versioning de `lucide-react`** : design-system n'impose pas de version. Recommandation : `^0.460.0` (compatible React 19 et tree-shakable). À fixer au plan.
- **Q6 — `e2e/upload.spec.ts` : peut-on tester le drag & drop via Playwright ?** : Playwright `locator.dispatchEvent('drop', { dataTransfer: ... })` permet de simuler un drop. Mais le test s11c (b) teste plutôt l'upload via `page.route` (sans passer par l'UI). Le drag & drop peut être testé dans un 5e test optionnel (AC15 liste 4 cas + 1 optionnel). **Recommandation : ne pas tester le drag & drop en e2e, garder la priorité sur les codes HTTP ; le drag & drop est testable manuellement ou via un test unitaire du composant (RTL).**

## Real complexity

**Score storyboard : 2.** Le code à toucher est connu (4 nouveaux fichiers, 4 modifications), tous les contrats sont gelés, les patterns à répliquer sont livrés (chatStore, ChatClient, FileUpload squelette).

**Mon score : 2. Pourquoi je n'ai pas bougé :**
- L'AC2 introduit un second input caméra + un state `isDragOver` + un état « fichier sélectionné » → c'est 3 sous-comportements dans un seul composant, mais tous dérivent du pattern `onFileSelect: (file | null) => void` déjà câblé. **Pas de hausse.**
- L'AC8-9 introduit 7 cards d'état différentes (1 success + 1 warning + 5 erreurs + 1 réseau) → c'est verbeux mais mécanique, et la design system fournit déjà les classes Tailwind pour chaque (`bg-success/10 border-success/30`, etc.). **Pas de hausse.**
- L'ajout de `lucide-react` est un piège non documenté (T3) qui force un commit de dépendance. **Pas une hausse, c'est un rattrapage de drift.**
- Le mapping `status + code` (T4) est un piège de logique, mais 7 sous-cas dans un `switch` propre ne justifient pas un score 3. **Pas de hausse.**

**Pas de proposition de split.** Le code rentre dans 10-12 tâches TDD, le plan reste dans l'enveloppe de complexité 2.

**Risques résiduels :**
- L'ajout de `lucide-react` peut révéler un drift de `pnpm-lock.yaml` qu'il faut résoudre proprement (utiliser `pnpm add` dans la worktree, laisser pnpm mettre à jour le lock).
- Le test e2e (b) qui inspecte le FormData envoyé nécessite Playwright ≥ 1.49 (déjà OK, cf. `package.json:39`).

## Split proposal

Pas de split. Le story est dans l'enveloppe.

## Liens

- `docs/stories.md:527-609` — story s11c (16 ACs, complexity 2, agentic notes, traps, OQs, out-of-scope).
- `docs/designs/s11-frontend-upload-chat.md:139-156, 189-193` — design original de la page `/upload` (référence, drift `.doc` documenté l.246).
- `docs/designs/s11b-frontend-chat.md:36-37` — pattern pour le label « pseudo manquant » (réutilisé tel quel).
- `docs/design-system.md:108-113, 137, 159-162, 198, 222-223, 246` — icônes Lucide, table `useUploadStore`, classes Tailwind des cards état, `Intl.NumberFormat`, « axios pour multipart / fetch pour SSE », drift `.doc`.
- `backend/app/api/documents/router.py:81-210` — contrat s10 (handler + mapping UploadError → HTTP).
- `backend/app/api/documents/schemas.py:35-72` — `UploadResponse` + `UploadErrorResponse` (codes stables).
- `backend/app/services/rag/upload_service.py:39` — `ALLOWED_EXTENSIONS`.
- `frontend/lib/api.ts:18-23` — `apiClient` (axios, sans Content-Type forcé).
- `frontend/lib/stores/{authStore,chatStore}.ts` — patterns Zustand + hydratation client-side.
- `frontend/components/FileUpload.tsx:1-83` — squelette à étendre (s11a, base de s11c).
- `frontend/components/Header.tsx:90-97` — lien `/upload` à réactiver.
- `frontend/lighthouserc.json:7-10` — à étendre avec `/fr/upload`.
- `frontend/messages/{fr,en}.json:42` — namespace `upload` vide à remplir.
- `frontend/app/(public)/[locale]/chat/page.tsx:34-42` — pattern server entry à répliquer.
- `templates/research.md` — structure du rapport.
- `AGENTS.md` § Frontend + Multi-tenancy — conventions obligatoires.
- `ADR 006` (Next.js + Zustand + i18n) + `ADR 011` (pseudo cookie pré-JWT).
