import { getTranslations, setRequestLocale } from 'next-intl/server';
import type { Metadata } from 'next';
import { ChatClient } from './ChatClient';

// The chat page is stateful (live SSE stream + Zustand state) and
// is not cacheable. Skipping prerender is the right trade-off: the
// server entry's only job is to set the locale for the nested
// client subcomponent and to expose the chat.title for the <head>.
export const dynamic = 'force-dynamic';

/*
 * /chat page (s11b) — server entry point.
 *
 * The page is server-rendered only to bootstrap the locale and the
 * title metadata; the actual UI lives in the client subcomponent
 * (ChatClient) because it consumes Zustand stores and a streaming
 * SSE connection. The server entry also runs `setRequestLocale` so
 * that nested server components (none today, but reserved) can call
 * `getTranslations` without falling back to dynamic rendering.
 */
export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations('chat');
  return {
    title: t('title'),
  };
}

export default async function ChatPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  return <ChatClient />;
}
