'use client';

import { useEffect, useRef } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { CheckCircle, AlertCircle, AlertTriangle, Loader2 } from 'lucide-react';
import { FileUpload } from '@/components/FileUpload';
import { Button } from '@/components/Button';
import { Card } from '@/components/Card';
import { Label } from '@/components/Label';
import { Select } from '@/components/Select';
import { useAuthStore, isValidPseudo } from '@/lib/stores/authStore';
import { useUploadStore, type Subject } from '@/lib/stores/uploadStore';

/*
 * UploadClient — client subcomponent of the /upload page (s11c).
 *
 * Form for uploading a single document to the s10 backend. Consumes
 * the authStore (cookie-backed pseudo) and the uploadStore (multipart
 * state, error mapping). The server entry (page.tsx) renders
 * <UploadClient />; this is the standard next-intl pattern for client
 * components that need useTranslations + Zustand.
 *
 * All copy is i18n-ised via useTranslations('upload') and
 * useTranslations('errors'). The 7 result states (1 success, 1
 * warning, 5 errors + 1 network) are mutually exclusive: the JSX
 * evaluates them in priority order so the highest-priority card wins.
 *
 * The PickerReopen effect: when the backend returns 415 (unsupported
 * extension), the local input ref opens the picker again so the user
 * can pick a different file. This is local-only state — the store
 * stays pure.
 *
 * cf. docs/research/s11c-frontend-upload.md, design § 4.3.
 */
const MAX_UPLOAD_MB = 20;

export function UploadClient() {
  const t = useTranslations('upload');
  const tErrors = useTranslations('errors');
  const locale = useLocale();

  const pseudo = useAuthStore((s) => s.pseudo);
  const hydrated = useAuthStore((s) => s.hydrated);
  const hydrateAuth = useAuthStore((s) => s.hydrate);

  const selectedFile = useUploadStore((s) => s.selectedFile);
  const subject = useUploadStore((s) => s.subject);
  const isUploading = useUploadStore((s) => s.isUploading);
  const lastResponse = useUploadStore((s) => s.lastResponse);
  const lastError = useUploadStore((s) => s.lastError);
  const lastHttpStatus = useUploadStore((s) => s.lastHttpStatus);
  const selectFile = useUploadStore((s) => s.selectFile);
  const setSubject = useUploadStore((s) => s.setSubject);
  const clearFile = useUploadStore((s) => s.clearFile);
  const upload = useUploadStore((s) => s.upload);
  const retry = useUploadStore((s) => s.retry);
  const storeHydrated = useUploadStore((s) => s.hydrated);
  const storeHydrate = useUploadStore((s) => s.hydrate);

  // Picker input ref forwarded to <FileUpload> via forwardRef. The
  // ref points to the picker's underlying <input type="file">, so we
  // can re-open the picker on a 415 error (cf. Q3 research).
  const pickerInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!hydrated) hydrateAuth();
    if (!storeHydrated) storeHydrate();
  }, [hydrated, hydrateAuth, storeHydrated, storeHydrate]);

  // Picker reopen on 415: dispatch a custom event the FileUpload picks
  // up via a window listener. We register a one-shot listener that
  // triggers the picker click.
  useEffect(() => {
    if (lastHttpStatus !== 415) return;
    function reopen() {
      pickerInputRef.current?.click();
    }
    // Give the DOM a tick to render the error card before the picker
    // reopens (avoids the picker stealing focus before the user sees
    // the error message).
    const id = window.setTimeout(reopen, 100);
    return () => window.clearTimeout(id);
  }, [lastHttpStatus]);

  const pseudoValid = isValidPseudo(pseudo);
  const canSend =
    pseudoValid &&
    subject !== null &&
    selectedFile !== null &&
    !isUploading;

  function handleSend() {
    if (!canSend) return;
    void upload();
  }

  function handleRetry() {
    if (lastHttpStatus === 415) {
      // Re-open the picker so the user can pick a different file.
      pickerInputRef.current?.click();
      clearFile();
      return;
    }
    void retry();
  }

  // Error message mapping (discriminate on lastHttpStatus first — see
  // Piège T4: 413 and 415 share code "invalid_file").
  let errorTitle: string | null = null;
  let showRetry = false;
  if (lastError) {
    if (lastHttpStatus === 413) {
      errorTitle = t('error413', { maxSize: MAX_UPLOAD_MB });
      showRetry = true;
    } else if (lastHttpStatus === 415) {
      errorTitle = t('error415');
      showRetry = true;
    } else if (lastError.code === 'invalid_pseudo') {
      errorTitle = t('errorInvalidPseudo');
      showRetry = true;
    } else if (lastError.code === 'ocr_failure') {
      errorTitle = t('errorOcrFailure');
      // No retry: re-OCR'ing the same file won't help.
    } else if (lastHttpStatus === null && lastError.code === 'network') {
      errorTitle = tErrors('network');
      showRetry = true;
    } else {
      // storage_failure or anything else.
      errorTitle = t('errorStorageFailure');
      showRetry = true;
    }
  }

  // Picker ref forwarding: we can't pass a ref through the FileUpload
  // component without changing its public API. Instead, we wrap a
  // hidden <input> in this page that mirrors the FileUpload's
  // ref-target. Since the FileUpload owns its own picker input, we
  // use a custom-event approach: dispatch a 'ktutor:open-picker' event
  // from this effect, and the FileUpload (via a useEffect registered
  // on mount) would forward it to its picker. For now, we ship the
  // page WITHOUT the auto-reopen and rely on the user clicking the
  // "Prendre une photo" / "Choisir un fichier" button to pick a new
  // file. The 415 state is still clearly displayed.
  //
  // To enable picker reopen: pass a ref via the FileUpload forwardRef
  // API. Not implemented in s11c (kept simple).

  return (
    <div className="max-w-2xl mx-auto px-4 md:px-6 py-4 md:py-6 flex flex-col gap-4">
      <h1 className="text-2xl md:text-3xl font-semibold tracking-tight text-text-primary">
        {t('title')}
      </h1>
      <p className="text-sm md:text-base text-text-secondary">{t('subtitle')}</p>

      <div className="flex flex-col gap-2">
        <Label htmlFor="upload-subject">{t('subjectLabel')}</Label>
        <Select
          id="upload-subject"
          value={subject ?? ''}
          onChange={(event) => setSubject(event.target.value as Subject)}
          options={[
            { value: 'maths', label: t('subjectMaths') },
            { value: 'francais', label: t('subjectFrancais') },
          ]}
          aria-describedby="upload-subject-help"
        />
        <span id="upload-subject-help" className="sr-only">
          {t('subjectLabel')}
        </span>
      </div>

      {!pseudoValid ? (
        <p className="text-sm text-warning" role="status">
          {t('noPseudo')}
        </p>
      ) : null}

      <div className="flex flex-col gap-2">
        <FileUpload
          id="upload-file"
          ref={pickerInputRef}
          accept=".pdf,.png,.jpg,.jpeg,.txt"
          maxSizeMb={MAX_UPLOAD_MB}
          selectedFile={selectedFile}
          disabled={isUploading}
          onFileSelect={selectFile}
          label={t('dropZoneLabel')}
          helpText={t('dropZoneHelp', { maxSize: MAX_UPLOAD_MB })}
        />
      </div>

      <div>
        <Button
          variant="primary"
          size="md"
          onClick={handleSend}
          disabled={!canSend}
          aria-disabled={!canSend}
          tabIndex={canSend ? 0 : -1}
          type="button"
          leftIcon={
            isUploading ? (
              <Loader2 size={20} className="animate-spin" aria-hidden="true" />
            ) : undefined
          }
        >
          {isUploading ? t('sending') : t('send')}
        </Button>
      </div>

      {lastResponse && lastResponse.status === 'indexed' ? (
        <Card className="bg-success/10 border border-success/30">
          <div className="flex items-start gap-3">
            <CheckCircle
              className="text-success shrink-0"
              size={24}
              aria-hidden="true"
            />
            <div className="flex-1 min-w-0">
              <h2 className="text-base font-semibold text-text-primary">
                {t('success', {
                  name: selectedFile?.name ?? '',
                  chunks: lastResponse.chunks_count,
                })}
              </h2>
            </div>
          </div>
          <div className="mt-3 pt-3 border-t border-success/30 flex justify-end">
            <Button
              variant="secondary"
              size="sm"
              type="button"
              onClick={() => clearFile()}
            >
              {t('uploadAnother')}
            </Button>
          </div>
        </Card>
      ) : null}

      {lastResponse && lastResponse.status === 'manual_review_needed' ? (
        <Card className="bg-warning/10 border border-warning/30">
          <div className="flex items-start gap-3">
            <AlertCircle
              className="text-warning shrink-0"
              size={24}
              aria-hidden="true"
            />
            <div className="flex-1 min-w-0">
              <h2 className="text-base font-semibold text-text-primary">
                {t('manualReview')}
              </h2>
            </div>
          </div>
          <div className="mt-3 pt-3 border-t border-warning/30 flex justify-end">
            <Button
              variant="secondary"
              size="sm"
              type="button"
              onClick={() => clearFile()}
            >
              {t('uploadAnother')}
            </Button>
          </div>
        </Card>
      ) : null}

      {errorTitle ? (
        <Card className="bg-error/10 border border-error/30" role="alert">
          <div className="flex items-start gap-3">
            <AlertTriangle
              className="text-error shrink-0"
              size={24}
              aria-hidden="true"
            />
            <div className="flex-1 min-w-0">
              <h2 className="text-base font-semibold text-text-primary">
                {errorTitle}
              </h2>
              {lastError?.code ? (
                <p className="text-xs text-text-secondary mt-1">
                  {t('errorCode', { code: lastError.code })}
                </p>
              ) : null}
            </div>
          </div>
          {showRetry ? (
            <div className="mt-3 pt-3 border-t border-error/30 flex justify-end">
              <Button
                variant="secondary"
                size="sm"
                type="button"
                onClick={handleRetry}
              >
                {t('retry')}
              </Button>
            </div>
          ) : null}
        </Card>
      ) : null}
    </div>
  );
}
