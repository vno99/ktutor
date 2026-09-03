import { getTranslations, setRequestLocale } from 'next-intl/server';
import type { Metadata } from 'next';
import { RegisterClient } from './RegisterClient';

/*
 * /register page (s13) — server entry. Renders the <RegisterClient />
 * form (interactive). Metadata is i18n-ised server-side.
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
  return <RegisterClient />;
}
