import { forwardRef, type SelectHTMLAttributes } from 'react';

/*
 * Select — thin wrapper over the native <select>.
 * Native <select> is keyboard and screen-reader accessible by default
 * (cf. docs/design-system.md § Composants signature).
 */
export interface SelectOption {
  value: string;
  label: string;
}

export interface SelectProps
  extends Omit<SelectHTMLAttributes<HTMLSelectElement>, 'children'> {
  id: string;
  options: SelectOption[];
  invalid?: boolean;
}

const baseClasses =
  'block w-full h-11 px-3 py-2 rounded-sm bg-surface text-text-primary ' +
  'border focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/30 ' +
  'focus-visible:ring-offset-2 focus-visible:ring-offset-canvas transition-colors ' +
  'disabled:opacity-50 disabled:cursor-not-allowed';

export const Select = forwardRef<HTMLSelectElement, SelectProps>(function Select(
  { id, options, invalid, className = '', ...rest },
  ref,
) {
  const classes = `${baseClasses} ${invalid ? 'border-error' : 'border-border'} ${className}`.trim();
  return (
    <select ref={ref} id={id} className={classes} aria-invalid={invalid || undefined} {...rest}>
      {options.map((opt) => (
        <option key={opt.value} value={opt.value}>
          {opt.label}
        </option>
      ))}
    </select>
  );
});
