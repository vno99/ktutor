import createMiddleware from 'next-intl/middleware';
import { routing } from './i18n/routing';

/*
 * next-intl middleware: rewrites the URL so that /, /chat, /upload etc.
 * resolve to the locale-prefixed routes (/fr/, /fr/chat, /fr/upload, ...).
 * The cookie NEXT_LOCALE is read to pick the user's preferred locale.
 * cf. docs/research/s11-frontend-upload-chat.md Piège #8.
 */
export default createMiddleware(routing);

export const config = {
  // Match all paths except API, _next, and files with an extension.
  matcher: ['/((?!api|_next|.*\\..*).*)'],
};
