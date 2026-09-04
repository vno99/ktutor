import { getTranslations, setRequestLocale } from 'next-intl/server';
import type { Metadata } from 'next';
import { ParentListClient } from './ParentListClient';

/*
 * /dashboard/parent page (s17) — server entry.
 *
 * Mirrors the /dashboard/eleve page pattern (s16): the page is
 * server-rendered only to bootstrap the locale and the title
 * metadata; the actual UI lives in the client subcomponent
 * (ParentListClient) because:
 *   1. It needs the JWT bearer, which lives in localStorage.
 *   2. It manages 4 UI states (loading / empty / error / success)
 *      that depend on a runtime fetch.
 *
 * The (dashboard)/[locale]/layout.tsx wraps the page in an
 * AuthGuard that handles the unauthenticated case.
 */
export const dynamic = 'force-dynamic';

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations('dashboard.parent');
  return {
    title: t('listTitle'),
  };
}

export default async function ParentListPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  return <ParentListClient />;
}
