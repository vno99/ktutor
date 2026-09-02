import { forwardRef, type TextareaHTMLAttributes } from 'react';

/*
 * Textarea — shared, accessible multi-line input.
 *
 * Reused by s11b (chat question, 1-2000 chars) and by s11c+
 * (document descriptions, admin forms in s17+). The API mirrors
 * <Input> so consumers can swap freely:
 *  - forwardRef<HTMLTextAreaElement>
 *  - id: string (paired with a <Label htmlFor> by the caller)
 *  - invalid?: boolean (aria-invalid + border-error)
 *  - maxLength?: number (forwarded to the native element)
 *  - any other TextareaHTMLAttributes (rows, value, onChange, etc.)
 *
 * The visual treatment is aligned with <Input>: same focus ring,
 * same border tokens, same disabled state. The min-h-24 gives 4
 * lines of breathing room; vertical resize is left to the browser
 * default to respect WCAG 2.1 reflow.
 *
 * cf. docs/research/s11b-frontend-chat.md § 3.2 — D2 du research.
 */
export interface TextareaProps
  extends Omit<TextareaHTMLAttributes<HTMLTextAreaElement>, 'id'> {
  id: string;
  invalid?: boolean;
}

const baseClasses =
  'block w-full min-h-24 rounded-sm bg-surface text-text-primary ' +
  'placeholder:text-text-tertiary border focus:outline-none ' +
  'focus-visible:ring-2 focus-visible:ring-primary/30 ' +
  'focus-visible:ring-offset-2 focus-visible:ring-offset-canvas ' +
  'transition-colors px-3 py-2 resize-y disabled:opacity-50 ' +
  'disabled:cursor-not-allowed';

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(
  function Textarea({ id, invalid, className = '', ...rest }, ref) {
    const classes = `${baseClasses} ${
      invalid ? 'border-error' : 'border-border focus:border-primary'
    } ${className}`.trim();
    return (
      <textarea
        ref={ref}
        id={id}
        className={classes}
        aria-invalid={invalid || undefined}
        {...rest}
      />
    );
  },
);
