import { getRequestConfig } from 'next-intl/server';
import { hasLocale } from 'next-intl';
import { routing } from './routing';

/*
 * Loads the message catalog for the requested locale.
 * Falls back to the default locale (fr) if the requested locale is unknown.
 * Imported by next-intl's plugin (see next.config.ts) and by server components
 * that need the messages via getMessages().
 */
export default getRequestConfig(async ({ requestLocale }) => {
  const requested = await requestLocale;
  const locale = hasLocale(routing.locales, requested) ? requested : routing.defaultLocale;

  return {
    locale,
    messages: (await import(`../messages/${locale}.json`)).default,
  };
});
