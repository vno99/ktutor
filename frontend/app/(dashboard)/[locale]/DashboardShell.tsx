'use client';

import type { ReactNode } from 'react';
import { useAuthStore } from '@/lib/stores/authStore';
import { Header } from '@/components/Header';

/*
 * DashboardShell — the client-side wrapper for the (dashboard)
 * layout (s17).
 *
 * The layout itself is an async server component (it must
 * resolve the locale + messages on the server). The authStore is
 * hydrated client-side only (ADR 011 § Hydratation client-side
 * only), so the server cannot know the role. We isolate the
 * role-dependent render in this client component and read
 * `useAuthStore.role` after hydration to compute `activeNav`.
 *
 * `activeNav` is fed to <Header> so the post-JWT nav (s17) is
 * shown only when the user is in a role with a dashboard
 * (eleve → /dashboard/eleve, parent → /dashboard/parent). For
 * an admin or a pre-role-fetch render, the public nav is
 * preserved.
 */
export function DashboardShell({
  children,
}: {
  children: ReactNode;
}) {
  const role = useAuthStore((s) => s.role);
  const activeNav: 'eleve' | 'parent' | null =
    role === 'eleve' ? 'eleve' : role === 'parent' ? 'parent' : null;

  return (
    <>
      <Header activeNav={activeNav} />
      <main id="main" className="min-h-[calc(100vh-3.5rem)] bg-canvas">
        {children}
      </main>
    </>
  );
}
