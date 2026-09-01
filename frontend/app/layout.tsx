import type { ReactNode } from 'react';
import type { Metadata } from 'next';
import './globals.css';

/*
 * Root layout — data-theme on <html>, fonts loaded via CSS variables in globals.css.
 * The (public)/[locale]/layout.tsx is the i18n-aware layout that wraps the actual
 * content with NextIntlClientProvider. The root layout here is intentionally
 * minimal so that next-intl's middleware can rewrite the URL.
 *
 * `metadata.title` and `description` are static defaults; route-level
 * `generateMetadata` overrides them per page (see `app/(public)/[locale]/page.tsx`).
 *
 * `lang` stays `fr` here (the default locale). The locale-specific layout
 * cannot change the <html> lang from the root layout in Next 16 App Router;
 * the live locale is exposed via the next-intl `useLocale()` hook for any
 * client component that needs to reflect the active language.
 */
export const metadata: Metadata = {
  title: 'ktutor',
  description: 'Assistant de devoir IA multi-agents',
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="fr" data-theme="light">
      <body className="bg-canvas text-text-primary font-sans antialiased">
        {children}
      </body>
    </html>
  );
}
