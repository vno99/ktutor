'use client';

import { useEffect, type ReactNode } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { useAuthStore } from '@/lib/stores/authStore';

/*
 * AuthGuard — the JWT-required wrapper for the (dashboard) route
 * group (s16).
 *
 * The store is hydrated client-side only (ADR 011 § Hydratation
 * client-side only). The guard:
 *
 *   1. Calls ``useAuthStore.getState().hydrate()`` on mount.
 *   2. Reads the store's ``hydrated`` and ``isAuthenticated`` flags.
 *   3. If still hydrating → renders nothing (no spinner, no flash).
 *   4. If hydrated and not authenticated → ``router.replace`` to
 *      ``/login?next=<current path>``.
 *   5. If authenticated → renders ``{children}``.
 *
 * The redirect uses ``replace`` (not ``push``) so the dashboard URL
 * is not in the history stack — pressing "back" after a forced
 * logout does not bounce the user back to the protected page.
 */
export function AuthGuard({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname() ?? '/';

  const hydrated = useAuthStore((s) => s.hydrated);
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);

  useEffect(() => {
    // Hydrate on mount — idempotent, the store is a singleton across
    // the React tree.
    useAuthStore.getState().hydrate();
  }, []);

  useEffect(() => {
    if (hydrated && !isAuthenticated) {
      const next = encodeURIComponent(pathname);
      router.replace(`/login?next=${next}`);
    }
  }, [hydrated, isAuthenticated, pathname, router]);

  if (!hydrated) {
    return null;
  }
  if (!isAuthenticated) {
    return null;
  }
  return <>{children}</>;
}
