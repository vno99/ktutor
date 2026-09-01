import { NextIntlClientProvider, hasLocale } from 'next-intl';
import { getMessages, setRequestLocale } from 'next-intl/server';
import { notFound } from 'next/navigation';
import type { ReactNode } from 'react';
import { routing } from '@/i18n/routing';
import { Header } from '@/components/Header';

/*
 * Layout for the (public) routes, locale-prefixed.
 * Wraps children with NextIntlClientProvider (so client components can
 * call useTranslations) and renders the <Header />. The page itself
 * (/fr/page.tsx) is a server component.
 *
 * setRequestLocale is required by next-intl for any server component
 * nested under a [locale] segment. Without it, useTranslations on a
 * child server component would throw.
 */
export function generateStaticParams() {
  return routing.locales.map((locale) => ({ locale }));
}

export default async function PublicLayout({
  children,
  params,
}: {
  children: ReactNode;
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  if (!hasLocale(routing.locales, locale)) {
    notFound();
  }
  setRequestLocale(locale);
  const messages = await getMessages();

  return (
    <NextIntlClientProvider locale={locale} messages={messages}>
      <Header />
      <main id="main" className="min-h-[calc(100vh-3.5rem)] bg-canvas">
        {children}
      </main>
    </NextIntlClientProvider>
  );
}
