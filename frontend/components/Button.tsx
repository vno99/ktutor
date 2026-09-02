import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from 'react';

/*
 * Button — design system signature component.
 * Variants: primary (default), secondary, ghost, destructive.
 * Sizes: sm, md (default), lg.
 *
 * All variants honor the design system focus ring and meet the
 * WCAG 2.5.5 touch target minimum (44x44 px on md/lg).
 *
 * cf. docs/design-system.md l.158, l.180, l.241.
 */
type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'destructive';
type ButtonSize = 'sm' | 'md' | 'lg';

const baseClasses =
  'inline-flex items-center justify-center font-medium rounded-sm transition-colors ' +
  'focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/30 ' +
  'focus-visible:ring-offset-2 focus-visible:ring-offset-canvas ' +
  'disabled:opacity-50 disabled:cursor-not-allowed';

const sizeClasses: Record<ButtonSize, string> = {
  sm: 'h-9 px-3 text-sm',
  md: 'h-11 px-4 text-base',
  lg: 'h-12 px-6 text-base',
};

const variantClasses: Record<ButtonVariant, string> = {
  primary:
    'bg-primary text-white hover:bg-primary-strong active:bg-primary-strong',
  secondary:
    'bg-surface text-text-primary border border-border hover:bg-surface-subtle',
  ghost:
    'bg-transparent text-text-primary hover:bg-surface-subtle',
  destructive:
    'bg-error text-white hover:opacity-90 active:opacity-80',
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  leftIcon?: ReactNode;
  children: ReactNode;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  function Button(
    {
      variant = 'primary',
      size = 'md',
      type = 'button',
      className = '',
      leftIcon,
      children,
      ...rest
    },
    ref,
  ) {
    const classes =
      `${baseClasses} ${sizeClasses[size]} ${variantClasses[variant]} ${className}`.trim();
    return (
      <button ref={ref} type={type} className={classes} {...rest}>
        {leftIcon ? <span className="mr-2 inline-flex shrink-0">{leftIcon}</span> : null}
        {children}
      </button>
    );
  },
);
