import type { HTMLAttributes, ReactNode } from 'react';

/*
 * Card — composable surface for grouped content.
 * Composed of Card (root), CardHeader, CardBody, CardFooter.
 * Uses design-system tokens (bg-surface, border, rounded-md, shadow-kt-default).
 */
function CardRoot({ className = '', children, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={`bg-surface border border-border rounded-md shadow-kt-default p-4 ${className}`.trim()}
      {...rest}
    >
      {children}
    </div>
  );
}

function CardHeader({ className = '', children, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={`mb-3 ${className}`.trim()} {...rest}>
      {children}
    </div>
  );
}

function CardBody({ className = '', children, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={className} {...rest}>
      {children}
    </div>
  );
}

function CardFooter({ className = '', children, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={`mt-3 pt-3 border-t border-border ${className}`.trim()} {...rest}>
      {children}
    </div>
  );
}

export const Card = Object.assign(CardRoot, {
  Header: CardHeader,
  Body: CardBody,
  Footer: CardFooter,
});
