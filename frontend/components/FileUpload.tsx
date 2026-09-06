'use client';

import { forwardRef, useId, useImperativeHandle, useRef, useState, type DragEvent, type ChangeEvent } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { FileText, FileImage, File as FileIcon, X, Camera, UploadCloud } from 'lucide-react';
import { Card } from './Card';
import { Button } from './Button';

/*
 * FileUpload — s11c full version.
 *
 * Renders a focusable <label htmlFor> as the visible drop zone (pattern
 * imposed by design-system l.273: <input> sr-only + <label htmlFor>
 * visible). The drag & drop is an enhancement on top of the label, not
 * a replacement: keyboard users (Tab → Espace/Entrée) still open the
 * native picker via the <label htmlFor> binding.
 *
 * s11c adds:
 *  - drag & drop (e.preventDefault() on onDragOver and onDrop,
 *    first-file-only on multi-file drops)
 *  - second input for the camera capture (sr-only, opened via
 *    "Prendre une photo" button, visible only on mobile via md:hidden)
 *  - a selectedFile mode: when a file is picked, the drop zone is
 *    replaced by a <Card> showing the icon + name + size + Retirer button
 *
 * The accept list mirrors backend ALLOWED_EXTENSIONS
 * (backend/app/services/rag/upload_service.py:39) — NO .doc / .docx.
 *
 * i18n: every visible string is routed through useTranslations('upload').
 * The component accepts an optional `ref` for the picker input (used by
 * the parent page to re-open the picker on a 415 error).
 */
export interface FileUploadProps {
  id?: string;
  name?: string;
  accept?: string;
  maxSizeMb?: number;
  required?: boolean;
  describedBy?: string;
  selectedFile?: File | null;
  disabled?: boolean;
  onFileSelect: (file: File | null) => void;
  label: string;
  helpText?: string;
}

const DEFAULT_ACCEPT = '.pdf,.png,.jpg,.jpeg,.txt';

function isImageExtension(name: string): boolean {
  const lower = name.toLowerCase();
  return lower.endsWith('.png') || lower.endsWith('.jpg') || lower.endsWith('.jpeg');
}

function isPdfExtension(name: string): boolean {
  return name.toLowerCase().endsWith('.pdf');
}

export const FileUpload = forwardRef<HTMLInputElement, FileUploadProps>(
  function FileUpload({
    id: providedId,
    name,
    accept = DEFAULT_ACCEPT,
    maxSizeMb,
    required,
    describedBy,
    selectedFile = null,
    disabled = false,
    onFileSelect,
    label,
    helpText,
  }, ref) {
  const generatedId = useId();
  const id = providedId ?? `fileupload-${generatedId}`;
  const t = useTranslations('upload');
  const locale = useLocale();
  const [isDragOver, setIsDragOver] = useState(false);

  const inputRef = useRef<HTMLInputElement>(null);
  const cameraRef = useRef<HTMLInputElement>(null);

  // Expose the picker input ref to the parent so it can re-open the
  // picker programmatically (e.g. on a 415 "unsupported extension"
  // error — cf. docs/research/s11c-frontend-upload.md Q3).
  useImperativeHandle(ref, () => inputRef.current as HTMLInputElement, []);

  function handleChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0] ?? null;
    onFileSelect(file);
  }

  function handleDragOver(event: DragEvent<HTMLLabelElement>) {
    // Piège T2: preventDefault is required to authorize the drop.
    event.preventDefault();
    if (disabled) return;
    setIsDragOver(true);
  }

  function handleDragLeave() {
    setIsDragOver(false);
  }

  function handleDrop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    setIsDragOver(false);
    if (disabled) return;
    const file = event.dataTransfer.files?.[0];
    if (file) onFileSelect(file);
  }

  if (selectedFile) {
    const sizeMb = selectedFile.size / 1024 / 1024;
    const sizeLabel = new Intl.NumberFormat(locale, {
      maximumFractionDigits: 1,
    }).format(sizeMb);
    const isPdf = isPdfExtension(selectedFile.name);
    const isImage = isImageExtension(selectedFile.name);
    return (
      <div className="space-y-2">
        <Card className="bg-surface border border-border">
          <div className="flex flex-col sm:flex-row sm:items-center gap-3">
            {isPdf ? (
              <FileText
                className="text-primary shrink-0"
                size={32}
                aria-hidden="true"
              />
            ) : isImage ? (
              <FileImage
                className="text-primary shrink-0"
                size={32}
                aria-hidden="true"
              />
            ) : (
              <FileIcon
                className="text-primary shrink-0"
                size={32}
                aria-hidden="true"
              />
            )}
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-text-primary break-words">
                {selectedFile.name}
              </p>
              <p className="text-xs text-text-secondary">
                {t('fileSize', { size: sizeLabel })}
              </p>
            </div>
            <Button
              variant="ghost"
              size="sm"
              type="button"
              onClick={() => onFileSelect(null)}
              leftIcon={<X size={16} aria-hidden="true" />}
              aria-label={t('removeFileAria')}
            >
              {t('removeFile')}
            </Button>
          </div>
        </Card>
      </div>
    );
  }

  const dropZoneClasses = [
    'flex flex-col items-center justify-center min-h-48 px-4 py-6',
    'border-2 border-dashed rounded-md cursor-pointer',
    'transition-colors focus-within:ring-2 focus-within:ring-primary/30',
    'focus-within:ring-offset-2 focus-within:ring-offset-canvas',
    isDragOver
      ? 'border-primary bg-primary/5 text-text-primary'
      : 'border-border bg-surface-subtle text-text-secondary hover:border-primary hover:text-text-primary',
    disabled ? 'pointer-events-none opacity-60' : '',
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <div className="space-y-2">
      <label
        htmlFor={id}
        className={dropZoneClasses}
        aria-describedby={describedBy}
        aria-disabled={disabled || undefined}
        aria-busy={disabled || undefined}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        <UploadCloud
          className="text-text-secondary mb-2"
          size={32}
          aria-hidden="true"
        />
        <span className="text-sm font-medium text-center">{label}</span>
        {helpText ? (
          <span className="mt-1 text-xs text-text-secondary text-center">
            {helpText}
          </span>
        ) : null}
        <Button
          variant="secondary"
          size="sm"
          type="button"
          className="md:hidden mt-3"
          onClick={(e) => {
            e.preventDefault();
            cameraRef.current?.click();
          }}
          leftIcon={<Camera size={16} aria-hidden="true" />}
          aria-label={t('takePhoto')}
        >
          {t('takePhoto')}
        </Button>
      </label>

      {/* Picker input (sr-only). */}
      <input
        ref={inputRef}
        id={id}
        name={name}
        type="file"
        accept={accept}
        required={required}
        aria-describedby={describedBy}
        data-max-size={maxSizeMb}
        onChange={handleChange}
        className="sr-only"
      />

      {/* Camera capture input (sr-only, opened via the "Prendre une photo" button). */}
      <input
        ref={cameraRef}
        type="file"
        accept="image/*"
        // capture is honored by Chrome Android + iOS Safari for the
        // rear camera. Firefox Android ignores it; that's a known
        // browser limitation, not a blocker (Piège #5 design).
        capture="environment"
        onChange={handleChange}
        className="sr-only"
        aria-hidden="true"
        tabIndex={-1}
      />
    </div>
  );
  },
);
