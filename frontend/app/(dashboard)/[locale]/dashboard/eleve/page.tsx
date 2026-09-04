import { getTranslations, setRequestLocale } from 'next-intl/server';
import type { Metadata } from 'next';
import { DashboardClient } from './DashboardClient';

// The dashboard reads aggregated DB state that depends on the JWT
// (which is in localStorage, not in a cookie). It cannot be SSRed
// safely — the server has no way to read the bearer. Skipping
// prerender is the right trade-off: the page is small, the data
// is cacheable on the backend (5 min TTL), and the AuthGuard in
// the (dashboard)/[locale]/layout.tsx handles the no-JWT case via
// a client-side redirect.
export const dynamic = 'force-dynamic';

/*
 * /dashboard/eleve page (s16) — server entry.
 *
 * The page is server-rendered only to bootstrap the locale and the
 * title metadata; the actual UI lives in the client subcomponent
 * (DashboardClient) because:
 *   1. It needs the JWT bearer, which lives in localStorage and
 *      is not readable from a server component.
 *   2. It manages 4 UI states (loading / empty / error / success)
 *      that depend on a runtime fetch.
 *
 * The (dashboard)/[locale]/layout.tsx wraps the page in an
 * AuthGuard that handles the unauthenticated case.
 */
export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations('dashboard.layout');
  return {
    title: t('title'),
  };
}

export default async function EleveDashboardPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  return <DashboardClient />;
}
