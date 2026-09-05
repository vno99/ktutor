import { getTranslations, setRequestLocale } from 'next-intl/server';
import type { Metadata } from 'next';
import { HistoryDetailClient } from './HistoryDetailClient';

/*
 * /history/{conversation_id} page (s19) — server entry point.
 *
 * The detail page is JWT-protected and not cacheable (depends on
 * the caller's identity). The server entry only sets the locale +
 * the title metadata; the actual UI lives in HistoryDetailClient
 * because it consumes the Zustand authStore and reads the
 * conversation id from the URL.
 *
 * The conversation_id is typed as a string (the route segment is
 * a free-form slug). The detail client passes it to the API
 * verbatim — the backend validates it as a UUID and returns 404
 * if the id is unknown or cross-tenant (the same body for both,
 * cf. ADR 015 § Decision 3 — a cross-tenant attacker cannot
 * enumerate ids).
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
  return { title: t('detailTitle') };
}

export default async function HistoryDetailPage({
  params,
}: {
  params: Promise<{ locale: string; conversation_id: string }>;
}) {
  const { locale, conversation_id } = await params;
  setRequestLocale(locale);
  return <HistoryDetailClient conversationId={conversation_id} />;
}
