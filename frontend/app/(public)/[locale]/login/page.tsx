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
  return <LoginClient />;
}
