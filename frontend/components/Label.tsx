import type { ReactNode } from 'react';

/*
 * Label — accessible label for a form control.
 * Required pairing with <Input>, <Select>, <FileUpload>.
 * Pass srOnly when a visible label would be redundant (e.g. when an
 * adjacent button visually labels the field, as in the FileUpload
 * pattern). cf. docs/research/s11-frontend-upload-chat.md Piège #11.
 */
export interface LabelProps {
  htmlFor: string;
  children: ReactNode;
  srOnly?: boolean;
}

export function Label({ htmlFor, children, srOnly = false }: LabelProps) {
  const classes = srOnly
    ? 'sr-only'
    : 'block text-sm font-medium text-text-primary mb-1';
  return (
    <label htmlFor={htmlFor} className={classes}>
      {children}
    </label>
  );
}
