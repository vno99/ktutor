import createMiddleware from 'next-intl/middleware';
import { routing } from './i18n/routing';

/*
 * next-intl middleware: rewrites the URL so that /, /chat, /upload etc.
 * resolve to the locale-prefixed routes (/fr/, /fr/chat, /fr/upload, ...).
 * The cookie NEXT_LOCALE is read to pick the user's preferred locale.
 */
export default createMiddleware(routing);

export const config = {
  matcher: ['/((?!api|_next|.*\\..*).*)'],
};
