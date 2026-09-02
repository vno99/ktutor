import { forwardRef, type InputHTMLAttributes } from 'react';

/*
 * Input — text or file input.
 * Always pair with a <Label htmlFor> for accessibility (axe-core check).
 * Height 44px on md (touch target WCAG 2.5.5).
 * File variant renders an sr-only <input> so the visible UI is composed
 * by a <label htmlFor> (cf. Piège #11 recherche).
 */
export interface InputProps
  extends Omit<InputHTMLAttributes<HTMLInputElement>, 'type'> {
  id: string;
  type?: 'text' | 'file';
  variant?: 'default' | 'file';
  invalid?: boolean;
}

const baseClasses =
  'block w-full h-11 rounded-sm bg-surface text-text-primary placeholder:text-text-tertiary ' +
  'border focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/30 ' +
  'focus-visible:ring-offset-2 focus-visible:ring-offset-canvas transition-colors';

const textClasses =
  'px-3 py-2 border-border focus:border-primary disabled:opacity-50 disabled:cursor-not-allowed';

const fileClasses =
  'sr-only file:mr-3 file:py-2 file:px-3 file:rounded-sm ' +
  'file:border-0 file:bg-surface-subtle file:text-text-primary';

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { id, type = 'text', variant, invalid, className = '', ...rest },
  ref,
) {
  const isFile = type === 'file';
  const classes = `${baseClasses} ${isFile ? fileClasses : textClasses} ${
    invalid ? 'border-error' : ''
  } ${className}`.trim();
  return (
    <input
      ref={ref}
      id={id}
      type={type}
      className={classes}
      aria-invalid={invalid || undefined}
      {...rest}
    />
  );
});
