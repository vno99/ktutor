import { setRequestLocale } from 'next-intl/server';
import { ParentChildClient } from './ParentChildClient';

/*
 * /dashboard/parent/[child_pseudo] page (s17) — server entry.
 *
 * Mirrors the /dashboard/eleve pattern (s16). The page resolves
 * the locale + child_pseudo on the server; the actual UI lives
 * in ParentChildClient because the JWT is in localStorage and
 * the data fetch depends on it.
 *
 * The (dashboard)/[locale]/layout.tsx wraps the page in an
 * AuthGuard.
 */
export const dynamic = 'force-dynamic';

export default async function ParentChildPage({
  params,
}: {
  params: Promise<{ locale: string; child_pseudo: string }>;
}) {
  const { locale, child_pseudo } = await params;
  setRequestLocale(locale);
  return <ParentChildClient childPseudo={child_pseudo} />;
}
