'use client';

import { useEffect } from 'react';
import { useTranslations } from 'next-intl';
import { Link } from '@/i18n/navigation';
import { usePathname } from 'next/navigation';
import { LogOut } from 'lucide-react';
import { useAuthStore } from '@/lib/stores/authStore';
import { apiClient } from '@/lib/api';
import { LanguageSwitcher } from './LanguageSwitcher';

/*
 * Header — sticky 56px, contains the logo, navigation (tablet+), the
 * LanguageSwitcher, and the auth affordance.
 *
 * s11a shipped a pseudo input here (ADR 011) so the chat/upload
 * flows could read the identity off a non-HttpOnly cookie. s13
 * replaces that input with an auth-aware affordance:
 *
 *   - if ``useAuthStore.isAuthenticated`` (hydrated + access token
 *     present) → an avatar circle composed inline + a native
 *     ``<details>/<summary>`` menu with "Mon espace" and "Se
 *     déconnecter" (which calls ``POST /api/auth/logout`` then
 *     ``clearTokens()``);
 *   - otherwise → a "Se connecter" link that points to /login.
 *
 * Design notes (per docs/designs/s13-login-eleve.md):
 *  - The avatar is composed inline (no new shared component).
 *  - The menu uses native ``<details>/<summary>`` (no Popover /
 *    Headless UI dependency).
 *  - The legacy cookie pseudo is still mirrored on login, so the
 *    chat / upload flows keep reading ``authStore.pseudo`` without
 *    a refactor (cf. ADR 011 § Migration).
 *  - The auth bootstrap endpoints (login, refresh, logout) go
 *    through ``apiClient``; the logout POST is intentionally not
 *    gated by a network failure — if the backend is unreachable,
 *    the local store is still cleared so the user is not stuck.
 */
export function Header() {
  const t = useTranslations('header');
  const tAuth = useTranslations('auth.logout');

  const pseudo = useAuthStore((s) => s.pseudo);
  const hydrated = useAuthStore((s) => s.hydrated);
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const hydrate = useAuthStore((s) => s.hydrate);
  const clearTokens = useAuthStore((s) => s.clearTokens);

  const pathname = usePathname() ?? '';
  const isChatActive = pathname.endsWith('/chat');
  const isUploadActive = pathname.endsWith('/upload');

  useEffect(() => {
    if (!hydrated) hydrate();
  }, [hydrated, hydrate]);

  const initial = pseudo ? pseudo.charAt(0).toUpperCase() : '?';
  const showAuthed = hydrated && isAuthenticated;

  async function handleLogout() {
    // Snapshot the access token BEFORE clearing so the request
    // can carry it; ``apiClient`` will add the bearer header
    // from the live store snapshot at request time.
    const accessToken = useAuthStore.getState().accessToken;
    // UI is updated immediately so the avatar disappears while
    // the network call is in flight.
    clearTokens();
    if (!accessToken) return;
    try {
      await apiClient.post('/api/auth/logout');
    } catch {
      // Logout is best-effort: the local store is already
      // cleared, the user is signed out from the UI's point of
      // view. A failed server call (network, 5xx) is logged
      // upstream by the apiClient; we don't surface it here.
    }
  }

  return (
    <header
      className="sticky top-0 z-10 h-14 w-full bg-surface border-b border-border"
      role="banner"
    >
      <div className="h-full max-w-screen-lg mx-auto px-4 md:px-6 flex items-center gap-4">
        <Link
          href="/"
          className="text-lg font-bold text-primary-strong shrink-0"
          aria-label={t('logo')}
        >
          {t('logo')}
        </Link>

        <nav
          aria-label="Primary"
          className="hidden md:flex items-center gap-4 text-sm text-text-secondary"
        >
          <Link
            href="/chat"
            className={`hover:text-text-primary transition-colors ${
              isChatActive ? 'text-text-primary font-medium' : ''
            }`}
            aria-current={isChatActive ? 'page' : undefined}
          >
            {t('navChat')}
          </Link>
          <Link
            href="/upload"
            className={`hover:text-text-primary transition-colors ${
              isUploadActive ? 'text-text-primary font-medium' : ''
            }`}
            aria-current={isUploadActive ? 'page' : undefined}
          >
            {t('navUpload')}
          </Link>
        </nav>

        <div className="flex-1" />

        <div className="hidden sm:block">
          <LanguageSwitcher />
        </div>

        {showAuthed ? (
          <details className="relative">
            <summary
              className="list-none cursor-pointer inline-flex items-center justify-center h-8 w-8 rounded-full bg-primary text-white text-sm font-semibold shrink-0 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/30 focus-visible:ring-offset-2 focus-visible:ring-offset-canvas"
              aria-label={t('avatarAlt', { pseudo })}
            >
              <span aria-hidden="true">{initial}</span>
            </summary>
            <div
              className="absolute right-0 mt-2 w-48 bg-surface border border-border rounded-md shadow-kt-default py-1 z-20"
              role="menu"
            >
              <Link
                href="/chat"
                className="block px-3 py-2 text-sm text-text-primary hover:bg-surface-subtle focus:outline-none focus-visible:bg-surface-subtle"
                role="menuitem"
              >
                {tAuth('menuLabel')}
              </Link>
              <button
                type="button"
                onClick={() => {
                  void handleLogout();
                }}
                className="w-full text-left px-3 py-2 text-sm text-error hover:bg-error/10 focus:outline-none focus-visible:bg-error/10 inline-flex items-center gap-2"
                role="menuitem"
              >
                <LogOut size={16} aria-hidden="true" />
                {tAuth('button')}
              </button>
            </div>
          </details>
        ) : (
          <Link
            href="/login"
            className="inline-flex items-center justify-center h-9 px-3 text-sm font-medium rounded-sm bg-primary text-white hover:bg-primary-strong transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/30 focus-visible:ring-offset-2 focus-visible:ring-offset-canvas"
          >
            {tAuth('loginCta')}
          </Link>
        )}
      </div>
    </header>
  );
}
