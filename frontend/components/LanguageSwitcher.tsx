'use client';

import { useLocale, useTranslations } from 'next-intl';
import { usePathname, useRouter } from '@/i18n/navigation';
import { useTransition, type ReactNode } from 'react';
import { routing } from '@/i18n/routing';

/*
 * LanguageSwitcher — pill toggle FR | EN.
 *
 * The locale is persisted via the next-intl middleware (which writes the
 * NEXT_LOCALE cookie on every navigation). Clicking a locale calls
 * router.replace(pathname, { locale }) which triggers the middleware to
 * re-run and rewrite the URL.
 *
 * cf. docs/research/s11-frontend-upload-chat.md Piège #8.
 */
function LocaleButton({
  children,
  isActive,
  onClick,
  ariaLabel,
}: {
  children: ReactNode;
  isActive: boolean;
  onClick: () => void;
  ariaLabel: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={isActive}
      aria-label={ariaLabel}
      className={`px-3 h-8 text-sm font-medium rounded-full transition-colors
        ${
          isActive
            ? 'bg-primary text-white'
            : 'bg-transparent text-text-secondary hover:bg-surface-subtle'
        }`}
    >
      {children}
    </button>
  );
}

export function LanguageSwitcher() {
  const locale = useLocale();
  const router = useRouter();
  const pathname = usePathname();
  const t = useTranslations('common');
  const [isPending, startTransition] = useTransition();

  function switchTo(nextLocale: (typeof routing.locales)[number]) {
    if (nextLocale === locale) return;
    startTransition(() => {
      router.replace(pathname, { locale: nextLocale });
    });
  }

  return (
    <div
      role="group"
      aria-label={t('language')}
      className="inline-flex items-center gap-1 p-1 border border-border rounded-full bg-surface"
    >
      {routing.locales.map((loc) => (
        <LocaleButton
          key={loc}
          isActive={loc === locale}
          onClick={() => switchTo(loc)}
          ariaLabel={t('switchTo', { locale: loc === 'fr' ? t('french') : t('english') })}
        >
          {loc.toUpperCase()}
        </LocaleButton>
      ))}
      {isPending ? (
        <span className="sr-only" aria-live="polite">
          …
        </span>
      ) : null}
    </div>
  );
}
