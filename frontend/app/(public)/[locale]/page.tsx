import { getTranslations, setRequestLocale } from 'next-intl/server';
import type { Metadata } from 'next';
import { Link } from '@/i18n/navigation';

/*
 * Home page (s11a) — minimal hero + 2 CTAs.
 * The /chat and /upload links point to routes that are gated by s11b/s11c;
 * clicking them now will 404, which is the expected behaviour for s11a.
 */
export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations('home');
  return {
    title: t('title'),
    description: t('subtitle'),
  };
}

export default async function HomePage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations('home');

  return (
    <div className="max-w-2xl mx-auto px-4 md:px-6 py-12 md:py-16 text-center">
      <h1 className="text-3xl md:text-4xl font-semibold tracking-tight text-text-primary">
        {t('title')}
      </h1>
      <p className="mt-4 text-base md:text-lg text-text-secondary">{t('subtitle')}</p>
      <div className="mt-8 flex flex-col sm:flex-row sm:justify-center sm:items-center gap-3">
        <Link
          href="/chat"
          className="inline-flex items-center justify-center h-11 px-6 text-base font-medium rounded-sm bg-primary text-white hover:bg-primary-strong transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/30 focus-visible:ring-offset-2 focus-visible:ring-offset-canvas"
        >
          {t('ctaChat')}
        </Link>
        <Link
          href="/upload"
          className="inline-flex items-center justify-center h-11 px-6 text-base font-medium rounded-sm bg-surface text-text-primary border border-border hover:bg-surface-subtle transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/30 focus-visible:ring-offset-2 focus-visible:ring-offset-canvas"
        >
          {t('ctaUpload')}
        </Link>
      </div>
    </div>
  );
}
