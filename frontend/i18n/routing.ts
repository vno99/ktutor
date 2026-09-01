import { defineRouting } from 'next-intl/routing';

/*
 * Routing configuration for next-intl.
 * Locales: fr (default), en.
 * The middleware (frontend/middleware.ts) uses this to redirect any URL
 * that is not prefixed with the locale to the user's preferred locale.
 */
export const routing = defineRouting({
  locales: ['fr', 'en'] as const,
  defaultLocale: 'fr',
  localePrefix: 'always',
});

export type AppLocale = (typeof routing.locales)[number];
