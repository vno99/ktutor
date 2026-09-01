'use client';

import { useId } from 'react';
import { Input } from './Input';
import { Label } from './Label';

/*
 * FileUpload — SKELETON (drag & drop + camera capture arrives in s11c).
 *
 * For s11a, this component renders:
 *  - a <Label> (sr-only) paired with the input
 *  - a visible <label htmlFor> styled as a drop zone
 *
 * cf. Piège #11 recherche: the input itself is sr-only; the visible
 * button is a <label htmlFor> that triggers the native file picker.
 *
 * TODO s11c: drag & drop + camera capture (`accept` only, not `capture`,
 * because iOS Safari does not honor `capture` on <input type="file">).
 */
export interface FileUploadProps {
  id?: string;
  name?: string;
  accept?: string;
  maxSize?: number;
  required?: boolean;
  describedBy?: string;
  onFileSelect: (file: File | null) => void;
  label: string;
  helpText?: string;
}

export function FileUpload({
  id: providedId,
  name,
  accept,
  maxSize,
  required,
  describedBy,
  onFileSelect,
  label,
  helpText,
}: FileUploadProps) {
  const generatedId = useId();
  const id = providedId ?? `fileupload-${generatedId}`;

  return (
    <div className="space-y-2">
      <Label htmlFor={id} srOnly>
        {label}
      </Label>
      {/* Visible drop zone — native <label htmlFor> triggers the sr-only input. */}
      <label
        htmlFor={id}
        className="flex flex-col items-center justify-center min-h-48 px-4 py-6
                   border-2 border-dashed border-border rounded-md
                   bg-surface-subtle text-text-secondary
                   cursor-pointer hover:border-primary hover:text-text-primary
                   transition-colors focus-within:ring-2 focus-within:ring-primary/30
                   focus-within:ring-offset-2 focus-within:ring-offset-canvas"
        aria-describedby={describedBy}
      >
        <span className="text-sm font-medium">{label}</span>
        {helpText ? (
          <span className="mt-1 text-xs text-text-tertiary">{helpText}</span>
        ) : null}
      </label>
      <Input
        id={id}
        name={name}
        type="file"
        accept={accept}
        required={required}
        aria-describedby={describedBy}
        onChange={(event) => {
          const file = event.target.files?.[0] ?? null;
          onFileSelect(file);
        }}
        // maxSize is enforced server-side; the browser cannot enforce it.
        data-max-size={maxSize}
      />
    </div>
  );
}
