import { Suspense } from 'react';
import { getTranslations, setRequestLocale } from 'next-intl/server';
import type { Metadata } from 'next';
import { LoginClient } from './LoginClient';

/*
 * /login page (s13) — server entry. Renders the <LoginClient /> form,
 * which holds the interactive state (validation, submit, redirect).
 *
 * The page itself is a server component so the metadata is
 * i18n-ised server-side. The form is a client component (uses
 * useRouter, useState, useSearchParams, useTranslations).
 *
 * The <Suspense> wrapper is required by Next.js 16: any client
 * component that calls useSearchParams() must be inside a Suspense
 * boundary so the static prerender can bail out gracefully (the
 * searchParams are only known at request time).
 */
export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations('auth.login');
  return {
    title: t('title'),
    description: t('subtitle'),
  };
}

export default async function LoginPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  return (
    <Suspense fallback={null}>
      <LoginClient />
    </Suspense>
  );
}
