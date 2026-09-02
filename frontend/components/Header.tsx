'use client';

import { useEffect, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Link } from '@/i18n/navigation';
import { usePathname } from 'next/navigation';
import { useAuthStore, isValidPseudo } from '@/lib/stores/authStore';
import { Label } from './Label';
import { Input } from './Input';
import { LanguageSwitcher } from './LanguageSwitcher';

/*
 * Header — sticky 56px, contains the logo, navigation (tablet+), the
 * LanguageSwitcher, the pseudo input and avatar. The pseudo is mirrored
 * to a cookie via the authStore so that the upload/chat flows in s11b/s11c
 * can read it on the server.
 *
 * The input is uncontrolled — we hold a ref to the DOM node and only
 * read its `value` on blur. The auth store remains the single source of
 * truth for the committed pseudo, and the avatar initial derives from
 * it. This avoids the setState-in-effect anti-pattern.
 */
export function Header() {
  const t = useTranslations('header');
  const pseudo = useAuthStore((s) => s.pseudo);
  const hydrated = useAuthStore((s) => s.hydrated);
  const hydrate = useAuthStore((s) => s.hydrate);
  const setPseudo = useAuthStore((s) => s.setPseudo);

  const [invalid, setInvalid] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const pathname = usePathname() ?? '';
  const isChatActive = pathname.endsWith('/chat');

  useEffect(() => {
    if (!hydrated) hydrate();
  }, [hydrated, hydrate]);

  // Hydrate the input's value from the cookie on first hydration.
  useEffect(() => {
    if (hydrated && inputRef.current && inputRef.current.value !== pseudo) {
      inputRef.current.value = pseudo;
    }
  }, [hydrated, pseudo]);

  const initial = pseudo ? pseudo.charAt(0).toUpperCase() : '?';

  function commitDraft() {
    const value = inputRef.current?.value ?? '';
    const trimmed = value.trim();
    if (trimmed.length === 0) {
      setInvalid(false);
      return;
    }
    if (!isValidPseudo(trimmed)) {
      setInvalid(true);
      return;
    }
    setPseudo(trimmed);
    setInvalid(false);
  }

  return (
    <header
      className="sticky top-0 z-10 h-14 w-full bg-surface border-b border-border"
      role="banner"
    >
      <div className="h-full max-w-screen-lg mx-auto px-4 md:px-6 flex items-center gap-4">
        <Link
          href="/"
          className="text-lg font-bold text-primary-strong shrink-0"
          aria-label={t('logo')}
        >
          {t('logo')}
        </Link>

        <nav
          aria-label="Primary"
          className="hidden md:flex items-center gap-4 text-sm text-text-secondary"
        >
          <Link
            href="/chat"
            className={`hover:text-text-primary transition-colors ${
              isChatActive ? 'text-text-primary font-medium' : ''
            }`}
            aria-current={isChatActive ? 'page' : undefined}
          >
            {t('navChat')}
          </Link>
          <Link
            href="/upload"
            className="hover:text-text-primary transition-colors"
            aria-disabled="true"
            tabIndex={-1}
          >
            {t('navUpload')}
          </Link>
        </nav>

        <div className="flex-1" />

        <div className="hidden sm:block">
          <LanguageSwitcher />
        </div>

        <div className="flex items-center gap-2">
          <Label htmlFor="header-pseudo" srOnly>
            {t('pseudoLabel')}
          </Label>
          <Input
            ref={inputRef}
            id="header-pseudo"
            name="pseudo"
            type="text"
            defaultValue={pseudo}
            placeholder={t('pseudoLabel')}
            maxLength={32}
            invalid={invalid}
            aria-describedby="header-pseudo-help"
            onChange={() => {
              if (invalid) setInvalid(false);
            }}
            onBlur={commitDraft}
            className="w-28 sm:w-36"
          />
          <span
            aria-hidden="true"
            className="inline-flex items-center justify-center h-8 w-8 rounded-full bg-primary text-white text-sm font-semibold shrink-0"
          >
            {initial}
          </span>
          <span id="header-pseudo-help" className="sr-only">
            {t('pseudoHelp')}
          </span>
        </div>
      </div>
    </header>
  );
}
