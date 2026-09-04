import { NextIntlClientProvider, hasLocale } from 'next-intl';
import { getMessages, setRequestLocale } from 'next-intl/server';
import { notFound } from 'next/navigation';
import type { ReactNode } from 'react';
import { routing } from '@/i18n/routing';
import { AuthGuard } from './AuthGuard';

/*
 * Layout for the (dashboard) routes, locale-prefixed (s16).
 *
 * Mirrors the (public) layout structure (NextIntlClientProvider +
 * <Header> + <main>) but adds the <AuthGuard> wrapper. The guard
 * hydrates the authStore from localStorage on mount, then
 * redirects to /login?next=... if the user is not authenticated.
 * While the hydration is pending, the guard renders nothing —
 * server-side state is never trusted for the auth decision
 * (ADR 011 § Hydration client-side only).
 */
export function generateStaticParams() {
  return routing.locales.map((locale) => ({ locale }));
}

export default async function DashboardLayout({
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
      <AuthGuard>
        <main id="main" className="min-h-[calc(100vh-3.5rem)] bg-canvas">
          {children}
        </main>
      </AuthGuard>
    </NextIntlClientProvider>
  );
}
