import { Suspense } from 'react';
import { getTranslations, setRequestLocale } from 'next-intl/server';
import type { Metadata } from 'next';
import { RegisterClient } from './RegisterClient';

/*
 * /register page (s13) — server entry. Renders the <RegisterClient />
 * form (interactive). Metadata is i18n-ised server-side.
 *
 * The <Suspense> wrapper is required by Next.js 16: any client
 * component that calls useSearchParams() must be inside a Suspense
 * boundary so the static prerender can bail out gracefully.
 */
export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations('auth.register');
  return {
    title: t('title'),
    description: t('subtitle'),
  };
}

export default async function RegisterPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  return (
    <Suspense fallback={null}>
      <RegisterClient />
    </Suspense>
  );
}
