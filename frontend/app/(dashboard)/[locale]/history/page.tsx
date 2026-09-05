import { getTranslations, setRequestLocale } from 'next-intl/server';
import type { Metadata } from 'next';
import { HistoryListClient } from './HistoryListClient';

/*
 * /history page (s19) — server entry point.
 *
 * The list is JWT-protected and is not cacheable (the page depends
 * on the caller's identity via the apiClient bearer). The server
 * entry only sets the locale + the title metadata; the actual UI
 * lives in HistoryListClient because it consumes the Zustand
 * authStore and reads next/navigation for the pagination state.
 *
 * The (dashboard)/[locale]/layout.tsx already wraps this in an
 * AuthGuard, so an unauthenticated visit is redirected to /login
 * with the next= query string preserved (s15).
 */
export const dynamic = 'force-dynamic';

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations('history');
  return { title: t('title') };
}

export default async function HistoryPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  return <HistoryListClient />;
}
