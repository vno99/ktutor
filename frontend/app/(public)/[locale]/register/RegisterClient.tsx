'use client';

import { useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { useRouter, useSearchParams } from 'next/navigation';
import { AlertTriangle, Loader2 } from 'lucide-react';
import { Button } from '@/components/Button';
import { Card } from '@/components/Card';
import { Input } from '@/components/Input';
import { Label } from '@/components/Label';
import { Link } from '@/i18n/navigation';
import { apiClient } from '@/lib/api';
import { useAuthStore } from '@/lib/stores/authStore';

/*
 * RegisterClient — client subcomponent of the /register page (s13).
 *
 * s12 shipped the POST /api/auth/register endpoint but no UI for
 * it (the user-facing flow landed in s13 along with the login
 * form). The form posts { pseudo, password } and surfaces the
 * specific error codes from the backend:
 *
 *  - 409 ``pseudo_taken``  → ``errors.pseudo.taken`` under the
 *    pseudo field
 *  - 422 ``invalid_pseudo`` → ``errors.invalidPseudo`` under the
 *    pseudo field (defence in depth — the client regex should
 *    catch this first)
 *  - 422 ``weak_password`` → ``errors.weakPassword`` under the
 *    password field
 *  - other (500, network)  → top-of-form card with a retry
 *    button.
 *
 * On success the backend returns 201 with no tokens. We redirect
 * to ``/login?next=...?registered=1`` so the user can sign in with
 * their new account. Showing a success toast on the login page is
 * a s25 follow-up; s13 just redirects.
 *
 * Like LoginClient, this is a presentation-only form — it does
 * not log the user in directly. The login page is the single
 * entry point for setting tokens (s15 will switch to auto-login
 * on register; out of scope here).
 */
const PSEUDO_PATTERN = /^[a-zA-Z0-9_]{3,32}$/;
const MIN_PASSWORD_LENGTH = 8;

export function RegisterClient() {
  const t = useTranslations('auth.register');
  const tErrors = useTranslations('auth.errors');
  const router = useRouter();
  const searchParams = useSearchParams();

  const hydrated = useAuthStore((s) => s.hydrated);
  const isAuth = useAuthStore((s) => s.isAuthenticated);
  const hydrateAuth = useAuthStore((s) => s.hydrate);

  const [pseudo, setPseudo] = useState('');
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [networkError, setNetworkError] = useState(false);
  const [pseudoError, setPseudoError] = useState<string | null>(null);
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [pseudoTouched, setPseudoTouched] = useState(false);

  useEffect(() => {
    if (!hydrated) hydrateAuth();
  }, [hydrated, hydrateAuth]);

  // A logged-in user has no business on the register page —
  // bounce them to /chat (or ?next).
  useEffect(() => {
    if (hydrated && isAuth) {
      const next = searchParams.get('next') ?? '/chat';
      router.push(next);
    }
  }, [hydrated, isAuth, router, searchParams]);

  const pseudoInvalid = pseudoTouched && !PSEUDO_PATTERN.test(pseudo);
  const passwordInvalid = password.length > 0 && password.length < MIN_PASSWORD_LENGTH;
  const canSubmit =
    PSEUDO_PATTERN.test(pseudo) &&
    password.length >= MIN_PASSWORD_LENGTH &&
    !submitting;

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!canSubmit) return;
    setSubmitting(true);
    setPseudoError(null);
    setPasswordError(null);
    setNetworkError(false);
    try {
      await apiClient.post<{ pseudo: string }>('/api/auth/register', {
        pseudo,
        password,
      });
      // Success: redirect to the login page with a query so a
      // future s25 toast can be wired in.
      const next = searchParams.get('next');
      const target = next
        ? `/login?next=${encodeURIComponent(next)}&registered=1`
        : '/login?registered=1';
      router.push(target);
    } catch (err) {
      const e = err as {
        response?: { status?: number; data?: { code?: string } };
        code?: string;
      };
      const status = e.response?.status;
      const code = e.response?.data?.code;
      if (status === 409 || code === 'pseudo_taken') {
        setPseudoError('pseudoTaken');
      } else if (code === 'invalid_pseudo') {
        setPseudoError('invalidPseudo');
      } else if (code === 'weak_password') {
        setPasswordError('weakPassword');
      } else if (status === 422) {
        // Generic 422 with no recognised code — fall back to
        // the password error to avoid leaking the field that
        // failed.
        setPasswordError('weakPassword');
      } else {
        setNetworkError(true);
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="max-w-sm mx-auto px-4 md:px-6 mt-8 md:mt-12">
      <Card>
        <h1 className="text-2xl md:text-3xl font-semibold tracking-tight text-text-primary">
          {t('title')}
        </h1>
        <p className="mt-2 text-sm md:text-base text-text-secondary">
          {t('subtitle')}
        </p>

        {networkError ? (
          <div
            role="alert"
            className="mt-4 p-3 rounded-sm bg-error/10 border border-error/30 flex items-start gap-2"
          >
            <AlertTriangle
              className="text-error shrink-0 mt-0.5"
              size={20}
              aria-hidden="true"
            />
            <div className="flex-1 min-w-0">
              <p className="text-sm text-text-primary">{tErrors('network')}</p>
            </div>
            <Button
              variant="secondary"
              size="sm"
              type="button"
              onClick={() => setNetworkError(false)}
            >
              {tErrors('retry')}
            </Button>
          </div>
        ) : null}

        <form
          onSubmit={handleSubmit}
          noValidate
          className="mt-4 flex flex-col gap-3"
        >
          <div className="flex flex-col gap-1">
            <Label htmlFor="register-pseudo">{t('pseudoLabel')}</Label>
            <Input
              id="register-pseudo"
              name="pseudo"
              autoComplete="username"
              value={pseudo}
              onChange={(e) => setPseudo(e.target.value)}
              onBlur={() => setPseudoTouched(true)}
              invalid={pseudoInvalid || pseudoError !== null}
              required
              placeholder={t('pseudoPlaceholder')}
              aria-invalid={pseudoInvalid || pseudoError !== null || undefined}
              aria-describedby={
                pseudoInvalid || pseudoError ? 'register-pseudo-error' : undefined
              }
            />
            {pseudoError ? (
              <p
                id="register-pseudo-error"
                role="alert"
                className="text-sm text-error"
              >
                {tErrors(pseudoError)}
              </p>
            ) : pseudoInvalid ? (
              <p
                id="register-pseudo-error"
                role="alert"
                className="text-sm text-error"
              >
                {tErrors('invalidPseudo')}
              </p>
            ) : null}
          </div>

          <div className="flex flex-col gap-1">
            <Label htmlFor="register-password">{t('passwordLabel')}</Label>
            <Input
              id="register-password"
              name="password"
              type="password"
              autoComplete="new-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              invalid={passwordError !== null}
              required
              placeholder={t('passwordPlaceholder')}
              aria-invalid={passwordError !== null || undefined}
              aria-describedby={
                passwordError ? 'register-password-error' : undefined
              }
            />
            {passwordError ? (
              <p
                id="register-password-error"
                role="alert"
                className="text-sm text-error"
              >
                {tErrors(passwordError)}
              </p>
            ) : null}
          </div>

          <div className="mt-2">
            <Button
              type="submit"
              variant="primary"
              size="md"
              disabled={!canSubmit}
              aria-disabled={!canSubmit}
              aria-busy={submitting || undefined}
              tabIndex={canSubmit ? 0 : -1}
              leftIcon={
                submitting ? (
                  <Loader2 size={20} className="animate-spin" aria-hidden="true" />
                ) : undefined
              }
            >
              {submitting ? t('submitting') : t('submit')}
            </Button>
          </div>
        </form>

        <p className="mt-4 text-sm text-text-secondary">
          {t('hasAccount')}{' '}
          <Link
            href={{
              pathname: '/login',
              query: searchParams.get('next')
                ? { next: searchParams.get('next') ?? undefined }
                : undefined,
            }}
            className="text-primary hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/30 focus-visible:ring-offset-2 focus-visible:ring-offset-canvas rounded-sm"
          >
            {t('loginLink')}
          </Link>
        </p>
      </Card>
    </div>
  );
}
