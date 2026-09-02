---
validated: yes
---

# Plan — Story s11c-frontend-upload

Branch: `feature/s11c-frontend-upload`
Research: `docs/research/s11c-frontend-upload.md` — read it first; this plan does not repeat it.
Design: `docs/designs/s11c-frontend-upload.md` (mockup : `docs/designs/s11c-frontend-upload.html`)

## Target story

> **s11c-frontend-upload — Page `/upload` avec drag & drop (split 3/3, gated by s11a)**
>
> **As an** élève **I want** uploader un document depuis l'interface web **so that** il soit indexé dans mon RAG.
>
> **Complexity (story)** : **2** — Maintenu à 2 après research (5 faits structurants, 20 pièges T1-T20 dont 5 P0, 6 questions ouvertes tranchées). Pas de split additionnel proposé.
>
> **Dépendances mergées** (vérifiées) : s11a `c3f1829` (scaffold + design system + `<FileUpload>` squelette + `authStore` cookie-backed), s10 `ff21046` (contrat multipart figé), s09 `c5f6163` (sibling, indépendant). Sibling : s11b-frontend-chat (parallel branch, mergé ou non, sans impact — s11c ne consomme pas l'API chat).
>
> **AC couverts (16, + 1 méta ; `docs/stories.md:537-555`)** : cf. story file pour le détail exhaustif. En résumé :
> 1. Route `/{locale}/upload` rend sélecteur matière + `<FileUpload>` + bouton « Envoyer » (44×44 px), tous les libellés via `useTranslations('upload')`.
> 2. `<FileUpload>` étendu : picker natif (déjà câblé s11a) + drag & drop (`onDragOver` + `onDrop` avec `e.preventDefault()`) + caméra mobile (second `<input type="file" accept="image/*" capture="environment">` masqué, bouton « Prendre une photo » visible ≤ 768px), `accept=".pdf,.png,.jpg,.jpeg,.txt"` (PAS de `.doc`/`.docx`).
> 3. Drag over → `border-primary bg-primary/5`, `e.preventDefault()` sur `onDragOver` ET `onDrop`, `onDragLeave` réinitialise.
> 4. Fichier sélectionné → `<Card>` avec icône Lucide (file-text / file-image / file) + nom + taille MB (1 décimale via `Intl.NumberFormat`) + bouton « Retirer » (ghost, `x` Lucide, `aria-label`).
> 5. Bouton « Envoyer » désactivé tant que pas de pseudo valide + matière + fichier (`aria-disabled="true"` + `tabindex="-1"`).
> 6. Envoi = `POST /api/documents/upload` via `apiClient` axios avec `FormData` (3 champs `pseudo` / `subject` / `file`), **SANS toucher aux headers** (axios gère le `Content-Type` + `boundary`).
> 7. Pendant l'envoi : spinner + « Envoi en cours… » + bouton désactivé + drop zone désactivée.
> 8. Cas succès 201 : `status: "indexed"` → card success + bouton « Uploader un autre document » ; `status: "manual_review_needed"` → card warning OCR.
> 9. Cas erreur 4xx/5xx : 5 sous-cas (413, 415, 422 `invalid_pseudo`, 422 `ocr_failure`, 500 `storage_failure`), mapping **HTTP status + code** (413 et 415 portent tous deux `code: "invalid_file"`), card `bg-error/10` + `alert-triangle` + `code` en `text-xs text-text-tertiary` + bouton « Réessayer » quand pertinent.
> 10. Erreur réseau (apiClient reject) : message inline + bouton « Réessayer ».
> 11. Aucun pseudo : label `text-warning` + input header `aria-invalid="true"` + bouton Envoyer désactivé.
> 12. `useUploadStore` Zustand `{ selectedFile, subject, isUploading, lastResponse, lastError, selectFile, clearFile, upload, retry, reset, hydrated, hydrate }`.
> 13. Responsive 360px (full-width, bouton caméra visible) / 768px (`max-w-2xl`, bouton caméra masqué). Pas de scroll horizontal.
> 14. Axe-core 0 violation critical/serious sur `/fr/upload` ET `/en/upload` ; Lighthouse Accessibility ≥ 90 sur `/fr/upload`.
> 15. ≥ 4 tests e2e Playwright dans `frontend/e2e/upload.spec.ts` (a) rendu + htmlFor + bouton désactivé, (b) stub 201 indexed avec inspection FormData (3 champs), (c) stub 413, (d) stub 415, (e optionnel) stub 201 manual_review_needed + 2 scans a11y.
> 16. `check-i18n.sh` exit 0 ; lint + typecheck + build + e2e verts.
> 17. (méta) Commentaire en tête de `uploadStore.ts` référençant `backend/app/api/documents/router.py:81-210`, `schemas.py:35-72`, `upload_service.py:39` (ALLOWED_EXTENSIONS) et explicitant le mapping `code → UI state`.

### Décisions héritées (research Q1-Q6 + design)

| Q / D | Décision | Justification |
|---|---|---|
| Q1 (CameraCapture) | `<CameraCapture>` **interne** au `<FileUpload>` (sous-composant ou bloc inline dans le même fichier) | Une seule source de vérité (`onFileSelect(file)`) ; pas de surface d'API publique supplémentaire. Le second input est rendu sr-only et déclenché par un `<Button>` qui appelle `inputRef.current?.click()`. |
| Q2 (data-testid) | **Pas de `data-testid`** | Les tests utilisent `getByLabel`, `getByRole`, `getByText` (cf. `chat.spec.ts:30-45`). Les sélecteurs accessibles sont suffisants et résistent mieux aux refactors. |
| Q3 (Réessayer sur 415) | **État local au composant** (`useRef<HTMLInputElement>` + `useEffect` qui observe `lastError?.code === "invalid_file"` + 415) qui appelle `inputRef.current?.click()` | Le store reste pur (pas de `shouldReopenPicker` flag). Le composant dispose déjà de l'input ref, et la coordination est locale. |
| Q4 (Reset « Uploader un autre ») | `clearFile()` uniquement (pas `reset()`) | L'AC8 dit « clear file, keep subject, keep pseudo ». `clearFile` ne touche qu'à `selectedFile` et `lastResponse` / `lastError`. Le store n'invalide pas `subject`. |
| Q5 (lucide-react version) | `^0.460.0` | Compatible React 19 (déjà en `package.json:32`), tree-shakable, aligné avec ce que la design system attend (8 icônes listées). Ajout via `pnpm add lucide-react` dans la worktree (met à jour `package.json` + `pnpm-lock.yaml`). |
| Q6 (drag & drop e2e) | **Pas de test e2e pour le drag & drop** | Playwright `dispatchEvent('drop', { dataTransfer })` est fragile et ne couvre pas la valeur (la `FormData` est testée via `page.route` au T8.1). Le drag & drop est testable manuellement + visuellement via le mockup HTML. Le test unitaire RTL du composant couvrira les handlers `onDragOver` / `onDrop` / `onDragLeave`. |

### Travail transverse obligatoire avant T1

Aucun. Les dépendances (s11a, s10, s09) sont mergées, le design system est sur `main` (commit `9133b09`), la worktree existe (`.worktrees/s11c-frontend-upload`) et est sur la branche `feature/s11c-frontend-upload` (HEAD `094123e` = `origin/main` post s11b).

## Tasks (ordered)

> **Ordre TDD strict** : test rouge → code minimal → test vert. **Commit unique en fin de story** (AGENTS.md § Pipeline). Toutes les tâches produisent un livrable observable.

### Phase 1 — Dépendance `lucide-react` (Piège T3, bloquant build)

- [x] **T1.1** — Ajouter `lucide-react` aux dependencies via `pnpm add lucide-react` dans la worktree (résoudra `^0.460.0`).
  - **Test rouge attendu** : `pnpm run typecheck` échoue sur les imports `from 'lucide-react'` (ou build casse).
  - **Test vert** : `pnpm run build` ne casse plus, `lucide-react` apparaît dans `frontend/package.json:30-40` et dans `pnpm-lock.yaml`.

### Phase 2 — i18n : namespace `upload` (AC1, AC16, méta-AC17 indirect)

- [x] **T2.1** — Remplir `"upload": {}` dans `frontend/messages/fr.json` (l.42) avec 21 clés :
  `title`, `subtitle`, `subjectLabel`, `subjectMaths`, `subjectFrancais`, `dropZoneLabel`, `dropZoneHelp`, `chooseFile`, `takePhoto`, `send`, `sending`, `removeFileAria` (label aria-only), `removeFile` (texte visible du bouton), `fileSize` (avec `{size}`), `noPseudo`, `success` (avec `{name}`, `{chunks}`), `manualReview`, `uploadAnother`, `retry`, `error413` (avec `{maxSize}`), `error415`, `errorInvalidPseudo`, `errorOcrFailure`, `errorStorageFailure`, `errorNetwork`, `errorCode` (avec `{code}`).
  - Remplir aussi `errors` (déjà partiellement rempli par s11b : `network`, `lost`, `cross_tenant`, `no_subject`, `invalid_pseudo`, `unknown`). Aucune clé nouvelle requise côté `errors` pour s11c (le mapping `code → tErrors(code)` réutilise ce qui existe ; les messages spécifiques upload vivent dans `upload.*`).
  - **Test rouge attendu** : `bash frontend/scripts/check-i18n.sh` exit ≠ 0 (le `useTranslations('upload')` dans les nouveaux composants ne trouve pas les clés).
  - **Test vert** : `bash frontend/scripts/check-i18n.sh` exit 0.

- [x] **T2.2** — Remplir le namespace `upload` dans `frontend/messages/en.json` (l.42) avec les mêmes 21 clés en anglais.
  - **Test vert** : `pnpm exec playwright test chat` reste vert (toggle FR/EN inchangé sur le chat, mais le `en.json` est validé par le test e2e (a11y) de s11b).

### Phase 3 — Extension du `<FileUpload>` squelette (AC2, AC3, AC4, AC12, Pièges T1-T5, T8, T10, T11, design-system l.273)

- [x] **T3.1** — Créer `frontend/components/FileUpload.test.tsx` (test unitaire RTL + jsdom) :
  - Cas couverts : (a) rend un `<label htmlFor="…">` focusable et un `<input type="file" id="…" accept=".pdf,.png,.jpg,.jpeg,.txt">` sr-only ; (b) clic sur le label → déclenche `inputRef.current.click()` (mock de `click` sur l'input) ; (c) `onFileSelect` est appelé avec un `File` quand l'input change ; (d) `onFileSelect` est appelé avec `null` quand le user annule la sélection ; (e) drag over : applique la classe `border-primary bg-primary/5` sur la drop zone ; (f) drop d'un `File` → `onFileSelect(file)` ; (g) drop de 2 fichiers → `onFileSelect` est appelé avec le **premier uniquement** ; (h) `onDragLeave` retire la classe `border-primary bg-primary/5` ; (i) quand `selectedFile` n'est pas `null` : rend un `<Card>` avec l'icône Lucide appropriée (`file-text` pour `.pdf`, `file-image` pour `.png/.jpg/.jpeg`, `file` pour `.txt`), le nom du fichier, la taille formatée via `Intl.NumberFormat('fr', { maximumFractionDigits: 1 })` (ex : « 2,5 MB »), et un bouton « Retirer » avec `aria-label="Retirer le fichier"` ; (j) clic sur « Retirer » → `onFileSelect(null)` ; (k) prop `disabled` → bloque le drag & drop (le drop est ignoré) et `onFileSelect` n'est pas appelé.
  - **Test rouge attendu** : `pnpm exec vitest run FileUpload` → module not found.

- [x] **T3.2** — Étendre `frontend/components/FileUpload.tsx` (squelette s11a, 83 l. → ~180 l.) :
  - **Props** (en plus de l'existant) : `selectedFile: File | null` (l'UI se réorganise quand un fichier est sélectionné), `disabled?: boolean` (pour bloquer pendant l'upload), `maxSizeMb?: number` (utilisé pour `data-max-size` et le texte d'aide).
  - **Refs** : `const inputRef = useRef<HTMLInputElement>(null)` (input picker), `const cameraRef = useRef<HTMLInputElement>(null)` (input caméra).
  - **State local** : `const [isDragOver, setIsDragOver] = useState(false)`.
  - **Drop zone** : reste un `<label htmlFor={inputId}>` (Piège T5, design-system l.273). Classes dynamiques : `isDragOver ? 'border-primary bg-primary/5' : 'border-border bg-surface'`. Handlers :
    - `onDragOver: (e) => { e.preventDefault(); if (!disabled) setIsDragOver(true); }` — **Piège T2** : `e.preventDefault()` obligatoire sinon le navigateur ouvre le fichier.
    - `onDragLeave: () => setIsDragOver(false)`.
    - `onDrop: (e) => { e.preventDefault(); setIsDragOver(false); if (disabled) return; const file = e.dataTransfer.files[0]; if (file) onFileSelect(file); }` — `e.preventDefault()` consomme l'event (Piège T2) ; **premier fichier uniquement** (Piège T10 / out-of-scope multi-upload).
  - **Input picker** : `<input ref={inputRef} id={inputId} type="file" accept=".pdf,.png,.jpg,.jpeg,.txt" data-max-size={maxSizeMb} onChange={(e) => onFileSelect(e.target.files?.[0] ?? null)} className="sr-only" required={required} />` — aligné backend `ALLOWED_EXTENSIONS`, **PAS de `.doc`/`.docx`** (Piège T10).
  - **Input caméra** : `<input ref={cameraRef} type="file" accept="image/*" capture="environment" onChange={(e) => onFileSelect(e.target.files?.[0] ?? null)} className="sr-only" aria-hidden="true" tabIndex={-1} />`. Déclenché par `<Button onClick={() => cameraRef.current?.click()} className="md:hidden" leftIcon={<CameraIcon size={20} />} aria-label={t('takePhoto')}>{t('takePhoto')}</Button>` — visible uniquement ≤ 768px (Piège T4, design § 4.6).
  - **Bouton « Choisir un fichier »** : intégré au `<label htmlFor>` (le label est la drop zone visible). Le label contient un `<UploadCloudIcon size={32} />`, le texte `t('dropZoneLabel')`, et l'aide `t('dropZoneHelp', { maxSize: maxSizeMb })` en `text-sm text-text-tertiary`.
  - **Mode « fichier sélectionné »** : `selectedFile != null` → retourne un `<Card>` avec :
    - Icône Lucide (mapping extension → icône) : `file-text` pour `.pdf`, `file-image` pour `.png/.jpg/.jpeg`, `file` pour `.txt`, `file` (fallback) pour les autres (au cas où le user force via le picker « All files », la card 415 viendra de toute façon).
    - `<p className="text-sm font-medium text-text-primary">{selectedFile.name}</p>`.
    - `<p className="text-xs text-text-tertiary">{t('fileSize', { size: new Intl.NumberFormat(locale, { maximumFractionDigits: 1 }).format(selectedFile.size / 1024 / 1024) })}</p>` — **Piège T9** : `maximumFractionDigits: 1` forcé, locale lu via `useLocale()` de next-intl.
    - `<Button variant="ghost" size="sm" onClick={() => onFileSelect(null)} leftIcon={<XIcon size={16} />} aria-label={t('removeFileAria')}>{t('removeFile')}</Button>`.
  - **Commentaire en tête** mis à jour : « SKELETON retiré (s11c), composant complet : drag & drop + caméra mobile + transformation en Card. Pattern `<input>` sr-only + `<label htmlFor>` visible imposé par design-system l.273. Référence backend : `backend/app/services/rag/upload_service.py:39` (ALLOWED_EXTENSIONS). ».
  - **Test rouge attendu** : `pnpm run typecheck` échoue car la page consomme `selectedFile` qui n'est pas dans les props.
  - **Test vert** : `pnpm exec vitest run FileUpload` passe les 11 cas (T3.1) ; `pnpm run typecheck` passe.

### Phase 4 — Store Zustand `useUploadStore` (AC6, AC9, AC11, AC12, AC17, Pièges T1, T4, T12)

- [x] **T4.1** — Créer `frontend/lib/stores/uploadStore.ts` (Pattern `chatStore`, ~140 l.) :
  - **Types** :
    - `type Subject = 'maths' | 'francais'`.
    - `type UploadSuccess = { document_id: string; status: 'indexed' | 'manual_review_needed'; chunks_count: number; ocr_confidence: number | null }` (aligné `backend/app/api/documents/schemas.py:35-44`).
    - `type UploadErrorCode = 'invalid_pseudo' | 'invalid_file' | 'ocr_failure' | 'storage_failure'` (aligné `schemas.py:67-72`).
    - `type UploadError = { code: UploadErrorCode; message: string }` (aligné `schemas.py:48-72`).
  - **State** : `{ selectedFile: File | null, subject: Subject | null, isUploading: boolean, lastResponse: UploadSuccess | null, lastError: UploadError | null, lastHttpStatus: number | null, hydrated: boolean, hydrate: () => void, selectFile: (f: File | null) => void, setSubject: (s: Subject) => void, clearFile: () => void, upload: () => Promise<void>, retry: () => Promise<void>, reset: () => void }`.
  - **`hydrate()`** : no-op, juste `set({ hydrated: true })`. Pattern `chatStore.ts:83-85`.
  - **`selectFile(file)`** : si `isUploading === true` → return (Piège T8 / drop pendant upload). Sinon `set({ selectedFile: file, lastResponse: null, lastError: null, lastHttpStatus: null })`. Ne touche pas à `subject`.
  - **`setSubject(s)`** : `set({ subject: s, lastResponse: null, lastError: null })` (changer de matière invalide l'état précédent).
  - **`clearFile()`** : `set({ selectedFile: null, lastResponse: null, lastError: null, lastHttpStatus: null })`. Ne touche pas à `subject`, ne touche pas à `isUploading`. Utilisé par « Retirer » et « Uploader un autre document » (Q4).
  - **`upload()`** (AC6, Piège T1) :
    1. `const pseudo = useAuthStore.getState().pseudo` ; si `!isValidPseudo(pseudo)` → `set({ lastError: { code: 'invalid_pseudo', message: '' } })` et return.
    2. `const { selectedFile, subject } = get()` ; si l'un manque → return (defensive).
    3. `set({ isUploading: true, lastResponse: null, lastError: null, lastHttpStatus: null })`.
    4. Construit `const formData = new FormData(); formData.append('pseudo', pseudo); formData.append('subject', subject); formData.append('file', selectedFile);`.
    5. `try { const response = await apiClient.post<UploadSuccess>('/api/documents/upload', formData); set({ isUploading: false, lastResponse: response.data, lastError: null, lastHttpStatus: response.status }); } catch (err) { /* voir ci-dessous */ }`.
    6. **Catch** : si `axios.isAxiosError(err)` et `err.response` existe → `const status = err.response.status; const data = err.response.data as { error?: string; code?: UploadErrorCode }`. `set({ isUploading: false, lastError: { code: data.code ?? 'storage_failure', message: data.error ?? '' }, lastHttpStatus: status })`. **Piège T4** : discriminer sur `status` (413 vs 415) en plus du `code` (les deux portent `code: 'invalid_file'`). Si `err.response` n'existe pas (réseau) → `set({ isUploading: false, lastError: { code: 'storage_failure', message: '' }, lastHttpStatus: null })`. Le composant mappe `lastHttpStatus === null` → message « erreur réseau » (AC10).
    7. **Idempotence** : si `isUploading === true` au début → return (évite double-invocation StrictMode, P9 s11b). Pattern `chatStore.ts`.
  - **`retry()`** : si `lastHttpStatus === 415` → le composant observe ça et ré-ouvre le picker (Q3, état local). Le store appelle `upload()` à nouveau. Si le `selectedFile` a été clear entre temps, `upload()` early-return.
  - **`reset()`** : `set({ selectedFile: null, subject: null, lastResponse: null, lastError: null, lastHttpStatus: null, isUploading: false })`. Utilisé en cleanup (rare en s11c, plutôt `clearFile`).
  - **Commentaire en tête** (méta-AC17) :
    ```
    // uploadStore — handles multipart upload of a single document to the
    // s10 backend.
    //
    // Backend contract (gelé, ff21046) :
    //   POST /api/documents/upload  FormData(pseudo, subject, file)
    //     201 → { document_id, status: "indexed" | "manual_review_needed",
    //             chunks_count, ocr_confidence }
    //     413 → { error, code: "invalid_file" }   (taille)
    //     415 → { error, code: "invalid_file" }   (extension)
    //     422 → { error, code: "invalid_pseudo" | "ocr_failure" }
    //     500 → { error, code: "storage_failure" }
    //
    // CRITICAL: do NOT set Content-Type manually. apiClient.post(url,
    // FormData) lets axios inject `multipart/form-data; boundary=...`.
    // A manual Content-Type would strip the boundary and the backend
    // would reject the upload (Piège T1).
    //
    // CRITICAL: discriminate 413 vs 415 on response.status, NOT on
    // `code` alone (both share `code: "invalid_file"`, cf.
    // backend/app/api/documents/router.py:199-210).
    //
    // Refs:
    //   backend/app/api/documents/router.py:81-210
    //   backend/app/api/documents/schemas.py:35-72
    //   backend/app/services/rag/upload_service.py:39   (ALLOWED_EXTENSIONS)
    ```
  - **Test rouge attendu** : pas de test unitaire (le `apiClient.post` est non-mockable sans infra ; AC15 le couvre en e2e). `pnpm run typecheck` valide la signature.
  - **Test vert** : `pnpm run typecheck` passe ; commentaire en tête conforme à méta-AC17.

### Phase 5 — Réactivation du lien `/upload` dans le Header (AC Header, Piège T6, retour s11a Minor #1)

- [x] **T5.1** — Modifier `frontend/components/Header.tsx` :
  - **Désactiver** : retirer `aria-disabled="true"` et `tabIndex={-1}` du lien `/upload` (l.90-97).
  - **Activer** : ajouter `aria-current={isUploadActive ? 'page' : undefined}` quand le pathname courant est `/upload`. Répliquer le pattern `isChatActive` déjà en place (l.84 : `const isActive = pathname === link.href`).
  - **Test rouge attendu** : `pnpm exec playwright test home` reste vert (les CTAs `/upload` doivent mener à `/fr/upload`), et le test e2e (a) de s11c (T8.1) vérifie que le lien est cliquable.
  - **Test vert** : `pnpm exec playwright test home upload` (s11a + s11c) tous verts.

### Phase 6 — Page `/upload` + i18n (AC1, AC7, AC8, AC10, AC11, AC13, Piège T15, design § Layout 1-9)

- [x] **T6.1** — Créer `frontend/app/(public)/[locale]/upload/page.tsx` (server entry, pattern exact `chat/page.tsx:34-42`, ~30 l.) :
  - `'use client'` non requis ici (server entry). `import { getTranslations, setRequestLocale } from 'next-intl/server'`, `import type { Metadata } from 'next'`, `import { UploadClient } from './UploadClient'`.
  - `export const dynamic = 'force-dynamic'` (Piège T15, page stateful Zustand + FormData).
  - `generateMetadata({ params })` : `setRequestLocale(locale)`, `const t = await getTranslations('upload')`, `return { title: t('title') }`.
  - `export default async function UploadPage({ params })` : `const { locale } = await params; setRequestLocale(locale); return <UploadClient />;`.
  - **Test rouge attendu** : `pnpm run build` échoue sur la résolution de route (page n'existe pas).
  - **Test vert** : `pnpm run build` passe.

- [x] **T6.2** — Créer `frontend/app/(public)/[locale]/upload/UploadClient.tsx` ('use client', ~180 l.) :
  - **Imports** : `useEffect`, `useRef`, `useState` (si besoin pour le picker reopen 415), `useTranslations`, `useLocale`, `<Select>`, `<FileUpload>`, `<Button>`, `<Label>`, `<Card>`, `<CardHeader>`, `<CardBody>`, `<CardFooter>`, `useAuthStore`, `isValidPseudo`, `useUploadStore`. Icônes Lucide : `UploadCloud`, `Camera`, `X`, `CheckCircle`, `AlertCircle`, `AlertTriangle`, `FileText`, `FileImage`, `File`.
  - **Hooks** : `const t = useTranslations('upload')`, `const tErrors = useTranslations('errors')`, `const locale = useLocale()`, `const pseudo = useAuthStore(s => s.pseudo)`, `const hydrated = useAuthStore(s => s.hydrated)`, `const hydrateAuth = useAuthStore(s => s.hydrate)`, `const { selectedFile, subject, isUploading, lastResponse, lastError, lastHttpStatus, selectFile, setSubject, clearFile, upload, retry, hydrated: storeHydrated, hydrate: storeHydrate } = useUploadStore()`.
  - **`useEffect`** : si `!hydrated` → `hydrateAuth()`, si `!storeHydrated` → `storeHydrate()`.
  - **`canSend`** : `isValidPseudo(pseudo) && subject !== null && selectedFile !== null && !isUploading`.
  - **`shouldReopenPicker`** : `useRef<HTMLInputElement>(null)` (input picker). `useEffect(() => { if (lastHttpStatus === 415) inputRef.current?.click(); }, [lastHttpStatus])` (Q3, retry sur 415).
  - **Layout** : `<div className="max-w-2xl mx-auto px-4 md:px-6 py-4 md:py-6 flex flex-col gap-4">`.
  - **Sections** (cf. design § Layout 1-9) :
    1. `<h1 className="text-2xl md:text-3xl font-semibold tracking-tight text-text-primary">{t('title')}</h1>`.
    2. `<p className="text-sm text-text-secondary">{t('subtitle')}</p>`.
    3. `<div className="flex flex-col gap-2"><Label htmlFor="upload-subject">{t('subjectLabel')}</Label><Select id="upload-subject" value={subject ?? ''} onChange={(e) => setSubject(e.target.value as 'maths' | 'francais')} options={[{ value: 'maths', label: t('subjectMaths') }, { value: 'francais', label: t('subjectFrancais') }]} aria-describedby="upload-subject-help" /><span id="upload-subject-help" className="sr-only">{t('subjectLabel')}</span></div>`.
    4. `{!isValidPseudo(pseudo) ? <p className="text-sm text-warning" role="status">{t('noPseudo')}</p> : null}` (AC11).
    5. `<FileUpload id="upload-file" ref={inputRef} accept=".pdf,.png,.jpg,.jpeg,.txt" maxSizeMb={20} selectedFile={selectedFile} disabled={isUploading} onFileSelect={selectFile} label={t('dropZoneLabel')} helpText={t('dropZoneHelp', { maxSize: 20 })} required={false} />` — note : `ref={inputRef}` (forwardRef à ajouter dans `<FileUpload>` au T3.2) pour le reopen 415.
    6. `<Button variant="primary" size="md" onClick={() => void upload()} disabled={!canSend} aria-disabled={!canSend} tabIndex={canSend ? 0 : -1} type="button" leftIcon={isUploading ? <Spinner /> : undefined}>{isUploading ? t('sending') : t('send')}</Button>` (AC5, AC7).
    7. **Cards résultat** (mutuellement exclusives, dans l'ordre) :
       - `lastResponse != null && lastResponse.status === 'indexed'` → `<Card className="bg-success/10 border border-success/30"><CardHeader><div className="flex items-center gap-2"><CheckCircleIcon className="text-success" size={20} /><h2 className="text-base font-semibold text-text-primary">{t('success', { name: selectedFile?.name ?? '', chunks: lastResponse.chunks_count })}</h2></div></CardHeader><CardFooter><Button variant="secondary" size="sm" onClick={() => clearFile()}>{t('uploadAnother')}</Button></CardFooter></Card>` (AC8 success).
       - `lastResponse != null && lastResponse.status === 'manual_review_needed'` → `<Card className="bg-warning/10 border border-warning/30">…<AlertCircleIcon className="text-warning" …/>{t('manualReview')}…</Card>` (AC8 warning, **Piège T11** : discrimination sur `status`, pas sur `chunks_count`).
       - `lastError != null` → `<Card className="bg-error/10 border border-error/30"><CardHeader><div className="flex items-center gap-2"><AlertTriangleIcon className="text-error" size={20} /><h2 className="text-base font-semibold text-text-primary">{/* message mappé */}</h2></div></CardHeader><CardBody><p className="text-xs text-text-tertiary">{t('errorCode', { code: lastError.code })}</p></CardBody><CardFooter>{/* bouton Réessayer conditionnel */}</CardFooter></Card>` (AC9). Mapping message :
         - `lastHttpStatus === 413` → `t('error413', { maxSize: 20 })`.
         - `lastHttpStatus === 415` → `t('error415')`.
         - `lastError.code === 'invalid_pseudo'` → `t('errorInvalidPseudo')`.
         - `lastError.code === 'ocr_failure'` → `t('errorOcrFailure')`.
         - `lastHttpStatus === null` (réseau) → `tErrors('network')` (réutilise `errors.network`).
         - `lastError.code === 'storage_failure'` ou 500 → `t('errorStorageFailure')`.
       - Bouton « Réessayer » : affiché sauf pour `code === 'ocr_failure'` (AC9(d), retry inutile) ET sauf pour `code === 'invalid_pseudo'` (AC9(c), état rare, « Recharge la page » suffit). Sur 415, le `useEffect` ré-ouvre le picker (Q3), donc le bouton « Réessayer » peut ne pas être affiché pour 415 (ou être affiché avec un texte « Choisir un autre fichier » — décision : garder « Réessayer » et laisser le `useEffect` ré-ouvrir le picker en parallèle).
    8. (aucun historique, AC out-of-scope s19).
    9. (responsive) : `max-w-2xl mx-auto` à 768px, full-width à 360px ; bouton caméra `md:hidden` (Piège T4). Pas de scroll horizontal.
  - **Test rouge attendu** : `pnpm run typecheck` échoue si `<FileUpload>` ne propage pas le `ref` (forwardRef) ou si une prop manque.
  - **Test vert** : `pnpm run typecheck` + `pnpm run build` passent.

### Phase 7 — Lighthouse : extension `lighthouserc.json` (AC14, Piège T7)

- [x] **T7.1** — Modifier `frontend/lighthouserc.json` (l.7-10) :
  - Ajouter `"http://localhost:3000/fr/upload"` au tableau `url` (après `"/fr/chat"`).
  - **Note** : on n'ajoute PAS `"/en/upload"` car l'audit `<html lang>` reste hardcodé à `fr` (Piège T14, gap s22). Cf. décision s11b D5 appliquée par symétrie.
  - **Test rouge attendu** : si on retire l'URL, la CI Lighthouse ignore `/fr/upload` et l'AC14 n'est pas vérifié.
  - **Test vert** : `pnpm exec lhci collect --config=frontend/lighthouserc.json` (ou équivalent) score accessibility ≥ 0.9 sur `/fr/upload` (vérification manuelle en local, CI le fait automatiquement).

### Phase 8 — Tests e2e Playwright + verifications (AC15, AC16)

- [x] **T8.1** — Créer `frontend/e2e/upload.spec.ts` avec ≥ 4 tests + 2 scans a11y (pattern `chat.spec.ts`) :
  - **Setup** : `async function setPseudo(page)` réutilise le pattern de `chat.spec.ts:22-27` (`page.goto('/fr/')`, `getByLabel('Ton pseudo')`, `fill('ali_baba')`, `blur()`).
  - **(a) `renders with all controls and htmlFor`** : `setPseudo(page)`, `page.goto('/fr/upload')`, vérifie `<h1>` « Uploader un document », `getByLabel('Matière')` est un `<select>`, la drop zone (`<label htmlFor="upload-file">`) est visible et contient le texte « Choisir un fichier » ou équivalent, `getByRole('button', { name: 'Envoyer' })` est visible et `aria-disabled="true"` (rien saisi). Suit le pattern de `chat.spec.ts:30-45`.
  - **(b) `uploads a stubbed file successfully and shows success card`** : `setPseudo(page)`, `page.route('**/api/documents/upload', async (route) => { const req = route.request(); const form = await req.formData(); expect(form.get('pseudo')).toBe('ali_baba'); expect(form.get('subject')).toBe('maths'); expect(form.get('file')).toBeTruthy(); await route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify({ document_id: 'doc-1', status: 'indexed', chunks_count: 12, ocr_confidence: null }) }) })`. Saisir matière, `setInputFiles` sur l'input file (Playwright `locator.setInputFiles({ name: 'cours.pdf', mimeType: 'application/pdf', buffer: Buffer.from('%PDF-1.4 fake') })`), cliquer « Envoyer », attendre la card « Document indexé : cours.pdf (12 chunks) », vérifier le bouton « Uploader un autre document ». **AC15(b)** : inspection FormData (3 champs) via `route.request().formData()`.
  - **(c) `displays 413 error card on file too large`** : `setPseudo(page)`, `page.route('**/api/documents/upload', async (route) => { await route.fulfill({ status: 413, contentType: 'application/json', body: JSON.stringify({ error: 'Fichier trop volumineux.', code: 'invalid_file' }) }) })`. Upload + Envoyer, vérifier la card `bg-error/10` contient « Fichier trop volumineux (max 20 MB) » et le bouton « Réessayer ». **AC9(a) + AC15(c)**.
  - **(d) `displays 415 error card on unsupported extension`** : `setPseudo(page)`, `page.route('**/api/documents/upload', async (route) => { await route.fulfill({ status: 415, contentType: 'application/json', body: JSON.stringify({ error: 'Extension .docx non supportée.', code: 'invalid_file' }) }) })`. Upload `.docx` forcé via `setInputFiles` (le `accept` n'est qu'un filtre d'UI), Envoyer, vérifier « Extension non supportée » + `code: invalid_file` en `text-xs`. **AC9(b) + AC15(d) + Piège T4** : discrimination `status` (415) même quand `code` est identique au 413.
  - **(e, optionnel) `displays 201 manual_review_needed as warning card`** : `setPseudo(page)`, `page.route` répond `201 { status: 'manual_review_needed', chunks_count: 0, ocr_confidence: 0.3 }`. Vérifier la card `bg-warning/10` avec icône `AlertCircle` et texte « Document enregistré, mais l'OCR est peu fiable. Un adulte doit le vérifier. ». **AC8 + AC15(e) + Piège T11**.
  - **(+a11y fr) `axe-core: no critical or serious violations on /fr/upload`** : `setPseudo(page)`, `page.goto('/fr/upload')`, `new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa']).analyze()`, filtrer `impact === 'critical' || 'serious'`, `expect(blocking).toEqual([])`. Pattern `chat.spec.ts:133-148`.
  - **(+a11y en) `axe-core: no critical or serious violations on /en/upload`** : idem sur `/en/upload`. **AC14**.
  - **Test rouge attendu** : la spec n'existe pas → `pnpm exec playwright test upload` → 0 tests trouvés.
  - **Test vert** : `pnpm exec playwright test upload` passe les ≥ 6 tests. Les specs existantes (`home`, `pseudo`, `responsive`, `chat`) restent vertes (18 + ≥ 6 = ≥ 24 tests verts).

- [x] **T8.2** — Vérifier `bash frontend/scripts/check-i18n.sh` exit 0 :
  - Le script vérifie qu'aucune string UI n'est en dur dans les fichiers `.tsx` et `.ts` du frontend (hors tests et fixtures).
  - **Test vert** : `bash frontend/scripts/check-i18n.sh && echo OK`.

- [x] **T8.3** — Run complet des vérifications :
  - `pnpm run lint` (exit 0).
  - `pnpm run typecheck` (exit 0).
  - `pnpm run build` (exit 0).
  - `pnpm exec playwright test` (tous les tests s11a + s11b + s11c verts, soit 11 + 7 + ≥ 6 = ≥ 24).
  - **Test vert global** : story shippable.

### Phase 9 — Commit final

- [x] **T9.1** — Un seul commit `feat(frontend): add /upload page with multipart upload (s11c)`. Corps structuré : AC cochées, captures (mockup HTML + screenshots Lighthouse ≥ 0.9 sur `/fr/upload`), review verdict à venir. Suit la convention `AGENTS.md` § Git et PR.

## Run interdicts

- **NE PAS** forcer `Content-Type: multipart/form-data` manuellement dans `apiClient.post(url, formData)` (Piège T1, P0). Axios gère le `boundary` automatiquement. Tout override explicite casse l'upload.
- **NE PAS** oublier `e.preventDefault()` sur `onDragOver` ET `onDrop` (Piège T2, P0). Sans ça, le navigateur ouvre le fichier au lieu de dropper, et le test e2e simulé casse.
- **NE PAS** transformer la drop zone en `<div onClick>` quand on ajoute le drag & drop (Piège T5, design-system l.273). Le `<label htmlFor>` reste la drop zone, le drag & drop est un enhancement par-dessus.
- **NE PAS** discriminer 413 vs 415 sur `error.code` seul (Piège T4, P0). Les deux portent `code: 'invalid_file'`. Utiliser `response.status` (ou `lastHttpStatus`).
- **NE PAS** ajouter `.doc` / `.docx` dans `accept` (Piège T10, P1). Le backend n'accepte que `.pdf, .png, .jpg, .jpeg, .txt` (`upload_service.py:39`). L'extension `.doc` est un drift design à corriger séparément.
- **NE PAS** discriminer `manual_review_needed` sur `chunks_count === 0` (Piège T11, P1). Utiliser `status === 'manual_review_needed'`. Un futur fix backend pourrait renvoyer `indexed` avec 0 chunks.
- **NE PAS** hardcoder de strings UI : tout via `useTranslations('upload')` ou `useTranslations('errors')`. `check-i18n.sh` exit 0 est un gate.
- **NE PAS** ajouter de barre de progression (`onUploadProgress` axios) — hors-scope s11c, gap s22.
- **NE PAS** ajouter de bouton « Annuler » (AbortController ad-hoc) — hors-scope s11c, gap s22.
- **NE PAS** persister l'historique d'uploads côté frontend (Zustand `persist` middleware interdit ici) — gap s19.
- **NE PAS** modifier le contrat backend (`backend/app/api/documents/router.py`, `schemas.py`, `upload_service.py`). Le frontend consomme, le backend est figé.
- **NE PAS** tester le drag & drop en e2e (Q6, fragile). Tester via unit RTL (T3.1) + manuellement. Les tests e2e stubbent via `page.route` sur l'API.
- **NE PAS** utiliser `data-testid` (Q2). Les selectors accessibles (`getByLabel`, `getByRole`, `getByText`) suffisent.
- **NE PAS** utiliser `fetch` direct (c'est `apiClient` axios ici, l'inverse de s11b). Le `Content-Type: multipart/form-data` est généré par axios.
- **NE PAS** étendre Lighthouse à `/en/upload` (Piège T14, `<html lang>` gap s22). Audit `/en/upload` chuterait.

## The point everything turns on

Le plan repose sur **une** décision : **`uploadStore.upload` envoie le `FormData` via `apiClient.post('/api/documents/upload', formData)` SANS toucher aux headers, ET le mapping UI discrimine sur `lastHttpStatus` (pas seulement `code`)**. Les 3 places où ce pari peut être faux :

1. **Si axios n'injecte pas le `Content-Type: multipart/form-data; boundary=...` automatiquement** quand on lui passe un `FormData`. Vérification : c'est le comportement documenté d'axios 1.7 (`frontend/node_modules/axios/dist/node/axios.cjs` à confirmer en implémentation, mais c'est le défaut historique). L'AC6 dit explicitement « Pas de `Content-Type` manuel (axios gère le boundary) ». Le test e2e (b) T8.1 inspecte le `FormData` reçu par le route stubbé, ce qui valide le payload indépendamment du boundary. Si axios avait un bug, le test pingerait. **Mitigation** : commentaire en tête de `uploadStore.ts` (T4.1) rappelle la règle.

2. **Si le mapping `status + code` est oublié et que 413 vs 415 sont tous deux affichés comme « Fichier invalide »**. Vérification : le test e2e (c) T8.1 stubbe explicitement `status: 413` et vérifie le message « Fichier trop volumineux (max 20 MB) » ; le test (d) stubbe `status: 415` et vérifie « Extension non supportée ». Si l'implémentation ne regarde que `code`, les deux tests échouent. **Mitigation** : le `switch` dans `UploadClient.tsx` (T6.2) teste `lastHttpStatus` EN PREMIER.

3. **Si le `forwardRef` du `<FileUpload>` n'est pas câblé et que le reopen du picker sur 415 (Q3) casse**. Vérification : T3.2 ajoute `forwardRef<HTMLInputElement, FileUploadProps>` au composant, le test e2e (d) T8.1 vérifie que l'erreur s'affiche (mais ne vérifie pas le reopen du picker, car c'est un side-effect visuel non observable en e2e). Le test unitaire T3.1 vérifie que `inputRef.current?.click()` est appelable. **Mitigation** : `forwardRef` ajouté explicitement à T3.2.

## Files touched

**Nouveaux (6)** :
- `frontend/lib/stores/uploadStore.ts` (T4.1) — store Zustand, commentaire contrat s10.
- `frontend/components/FileUpload.test.tsx` (T3.1) — tests unitaires RTL.
- `frontend/app/(public)/[locale]/upload/page.tsx` (T6.1) — server entry.
- `frontend/app/(public)/[locale]/upload/UploadClient.tsx` (T6.2) — client subcomponent.
- `frontend/e2e/upload.spec.ts` (T8.1) — ≥ 4 tests e2e + 2 scans a11y.
- `docs/plans/s11c-frontend-upload.md` (ce fichier).

**Modifiés (5)** :
- `frontend/package.json` (T1.1) — ajout `lucide-react` aux dependencies.
- `frontend/pnpm-lock.yaml` (T1.1) — mis à jour par `pnpm add`.
- `frontend/components/FileUpload.tsx` (T3.2) — étendu : drag & drop, caméra, Card mode fichier sélectionné, forwardRef.
- `frontend/messages/fr.json` (T2.1) — namespace `upload` rempli (~25 clés).
- `frontend/messages/en.json` (T2.2) — namespace `upload` rempli en anglais.
- `frontend/components/Header.tsx` (T5.1) — retire `aria-disabled` + `tabIndex={-1}` du lien `/upload`, ajoute `aria-current`.
- `frontend/lighthouserc.json` (T7.1) — ajout `http://localhost:3000/fr/upload`.

**Non touchés (à vérifier en review)** :
- `frontend/lib/api.ts` — pas de modif. Le commentaire l.7-8 reste vrai. `apiClient.post(url, FormData)` est utilisé tel quel.
- `frontend/lib/stores/authStore.ts` — lu par `uploadStore.upload` (via `useAuthStore.getState().pseudo`), pas modifié.
- `frontend/lib/stores/chatStore.ts` — sibling, non touché.
- `frontend/components/{Button,Card,Select,Input,Label,Textarea,LanguageSwitcher,StreamingMessage,Header}` (hors Header pour T5.1) — non touchés. Tous les composants requis existent.
- `backend/**` — out of scope strict.
- `frontend/middleware.ts` + `frontend/i18n/routing.ts` — la locale `/fr/upload` est déjà couverte par le routing next-intl de s11a.
- `frontend/playwright.config.ts` — pas de modif, le nouveau spec est auto-découvert.
- `frontend/vitest.config.ts` (ou équivalent) — pas de modif, les nouveaux tests unitaires sont auto-découverts.

## Test strategy

| Niveau | Quoi | Où | Combien |
|---|---|---|---|
| **Unitaire** | `<FileUpload>` (rendu, focus, drop, drag over/leave, multi-file, selectedFile mode Card, icônes Lucide, taille formatée, bouton Retirer, disabled) | `FileUpload.test.tsx` | 11 cas (T3.1) |
| **E2E** | Rendu + htmlFor + bouton désactivé | `upload.spec.ts` (a) | 1 test |
| **E2E** | Upload 201 indexed + inspection FormData (3 champs) + bouton « Uploader un autre » | `upload.spec.ts` (b) | 1 test |
| **E2E** | Erreur 413 + card + bouton Réessayer | `upload.spec.ts` (c) | 1 test |
| **E2E** | Erreur 415 + card + discrimination status/code | `upload.spec.ts` (d) | 1 test |
| **E2E (opt)** | 201 manual_review_needed + card warning OCR | `upload.spec.ts` (e) | 1 test |
| **A11y** | Axe-core `/fr/upload` | `upload.spec.ts` (a11y fr) | 1 test |
| **A11y** | Axe-core `/en/upload` | `upload.spec.ts` (a11y en) | 1 test |
| **CI** | Lint, typecheck, build | `pnpm run` | 1 run global |
| **CI** | Lighthouse a11y ≥ 0.9 sur `/fr/upload` | `lighthouserc.json` | 1 audit |
| **CI** | check-i18n.sh exit 0 | `frontend/scripts/check-i18n.sh` | 1 run |
| **CI** | Tous les tests Playwright (s11a + s11b + s11c) | `playwright test` | ≥ 24 tests |

**Total automatisé** : 11 unitaires + ≥ 5 e2e + 2 a11y = ≥ 18 tests automatisés s11c. **Couvre** tous les AC sauf AC5 (état désactivé bouton) et AC13 (responsive) qui sont validés visuellement via le mockup HTML (`docs/designs/s11c-frontend-upload.html` à 360px et 768px) + l'axe-core (focus visible + tab order).

**Vérification visuelle séparée** : ouvrir `docs/designs/s11c-frontend-upload.html` dans un browser pour comparer au rendu réel de `/fr/upload` à 360px (bouton caméra visible, full-width) et 768px (`max-w-2xl`, bouton caméra masqué). Mockup = référence low-fidelity, pas pixel-perfect.

**Test manuel complémentaire** : tester le drag & drop en local (pas couvert par e2e) — `pnpm run dev`, ouvrir `/fr/upload`, glisser un PDF sur la drop zone, vérifier la transformation en Card.

## Definition of Done

- Une PR unique, description structurée (AC cochées, captures Lighthouse ≥ 0.9 sur `/fr/upload`, mockup HTML en annexe), diff lisible.
- Tests passants : `pnpm run lint && pnpm run typecheck && pnpm run build && pnpm exec playwright test` exit 0.
- Pas de régression : les 18 tests s11a + s11b restent verts (`home.spec.ts`, `pseudo.spec.ts`, `responsive.spec.ts`, `chat.spec.ts`).
- **Multi-tenancy** : le `pseudo` est lu via `useAuthStore.getState().pseudo` côté store (cookie-backed pré-JWT, JWT en s15). Jamais hardcodé, jamais extrait du FormData autrement. Pas de test cross-tenant côté frontend (c'est le contrat backend, déjà testé en s10).
- **Observabilité** : pas de nouvelle métrique frontend en s11c (l'observabilité arrive en s22). Les erreurs axios sont catchées dans le store (log console en dev). Le `lastError.code` est exposé dans la card pour le debug.
- **i18n** : `bash frontend/scripts/check-i18n.sh` exit 0, tous les libellés via `useTranslations('upload')` (UI) ou `useTranslations('errors')` (codes mappés réseau).
- **Accessibilité** : axe-core 0 violation critical/serious sur `/fr/upload` ET `/en/upload` (2 tests dédiés), Lighthouse Accessibility ≥ 90 sur `/fr/upload`, `<label htmlFor>` focusable conservé (clavier → Espace/Entrée ouvre le picker), drag & drop = enhancement (pas un remplacement), `aria-invalid` sur input pseudo header via `isValidPseudo()`.
- **Documentation** : commentaire en tête de `uploadStore.ts` référençant le contrat backend complet (méta-AC17) — `router.py:81-210`, `schemas.py:35-72`, `upload_service.py:39`, plus les deux règles critiques (no manual Content-Type, discriminate on status).
- **Dépendance** : `lucide-react` ajouté via `pnpm add` dans la worktree, `package.json` + `pnpm-lock.yaml` commités.
- Review passée : `docs/reviews/s11c-frontend-upload.md` termine par `Max severity: <…>` et `Ship allowed: yes`.
