import { getTranslations, setRequestLocale } from 'next-intl/server';
import type { Metadata } from 'next';
import { UploadClient } from './UploadClient';

// The upload page is stateful (Zustand + FormData) and is not
// cacheable. Skipping prerender is the right trade-off: the server
// entry's only job is to set the locale for the nested client
// subcomponent and to expose the upload.title for the <head>.
export const dynamic = 'force-dynamic';

/*
 * /upload page (s11c) — server entry point.
 *
 * Mirror of /chat/page.tsx (s11b). The page is server-rendered only
 * to bootstrap the locale and the title metadata; the actual UI lives
 * in the client subcomponent (UploadClient) because it consumes
 * Zustand stores and a multipart FormData. The server entry also runs
 * `setRequestLocale` so that nested server components (none today)
 * can call `getTranslations` without falling back to dynamic rendering.
 */
export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations('upload');
  return {
    title: t('title'),
  };
}

export default async function UploadPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  return <UploadClient />;
}
