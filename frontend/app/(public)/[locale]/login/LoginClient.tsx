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
import { useAuthStore, isValidPseudo } from '@/lib/stores/authStore';
import type { Role } from '@/lib/stores/authStore';

/*
 * LoginClient — client subcomponent of the /login page (s13).
 *
 * Form: pseudo + password → POST /api/auth/login → on success
 * ``authStore.setTokens(...)`` and redirect to ``?next=`` (or
 * ``/chat``). The auth flow is timing-constant on the server
 * (Piège 2 research), so a wrong pseudo vs. wrong password
 * produces an identical 401 — the form maps both to the
 * ``invalidCredentials`` translation.
 *
 * States (design § 6):
 *  - empty / typing : form visible, button disabled until the
 *    pseudo passes the client-side regex.
 *  - submitting : ``aria-busy=true`` on the button, no navigation
 *    away (the user must wait for the response).
 *  - 401 : form error ``invalidCredentials``.
 *  - 422 (defence in depth) : same ``invalidCredentials`` key —
 *    we do not leak the field that failed.
 *  - network failure : top-of-form card with a retry button.
 *
 * Mount-time redirect: if the user is already authenticated
 * (authStore hydrated AND a token is present), bounce to
 * ``?next ?? '/chat'`` so a logged-in user can never see the
 * login form. This is a UX nicety, not a security gate (the
 * route is still (public) in s13).
 *
 * The form uses the existing shared components (``<Input>``,
 * ``<Label>``, ``<Button>``, ``<Card>``) — no new design-system
 * surface. Inline copy comes from ``useTranslations('auth.login')``
 * and ``useTranslations('auth.errors')``; never hardcoded.
 */
const PSEUDO_PATTERN = /^[a-zA-Z0-9_]{3,32}$/;

export function LoginClient() {
  const t = useTranslations('auth.login');
  const tErrors = useTranslations('auth.errors');
  const router = useRouter();
  const searchParams = useSearchParams();

  const hydrated = useAuthStore((s) => s.hydrated);
  const isAuth = useAuthStore((s) => s.isAuthenticated);
  const setTokens = useAuthStore((s) => s.setTokens);
  const clearTokens = useAuthStore((s) => s.clearTokens);
  const hydrateAuth = useAuthStore((s) => s.hydrate);

  const [pseudo, setPseudo] = useState('');
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [networkError, setNetworkError] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [pseudoTouched, setPseudoTouched] = useState(false);

  // Hydrate the auth store on mount if it hasn't been hydrated
  // yet (Header normally does it, but a user landing directly
  // on /login may not have visited the home page).
  useEffect(() => {
    if (!hydrated) hydrateAuth();
  }, [hydrated, hydrateAuth]);

  // If the user is already logged in, bounce to ?next or /chat.
  // We rely on the authStore's ``isAuthenticated`` derived flag
  // (hydrated + accessToken) to avoid an infinite redirect loop
  // if the API later redirects here on a stale token.
  useEffect(() => {
    if (hydrated && isAuth) {
      const next = searchParams.get('next') ?? '/chat';
      router.push(next);
    }
  }, [hydrated, isAuth, router, searchParams]);

  const pseudoInvalid = pseudoTouched && !PSEUDO_PATTERN.test(pseudo);
  const canSubmit =
    PSEUDO_PATTERN.test(pseudo) && password.length > 0 && !submitting;

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!canSubmit) return;
    setSubmitting(true);
    setFormError(null);
    setNetworkError(false);
    // Clear any stale tokens before a fresh login so the API
    // client doesn't try to refresh on a 401 from the new
    // credential set.
    clearTokens();
    try {
      const resp = await apiClient.post<{
        access_token: string;
        refresh_token: string;
        expires_in: number;
        role?: string;
        pseudo?: string;
      }>('/api/auth/login', { pseudo, password });
      const role: Role = (resp.data.role as Role) ?? 'eleve';
      setTokens({
        accessToken: resp.data.access_token,
        refreshToken: resp.data.refresh_token,
        role,
        pseudo: resp.data.pseudo ?? pseudo,
      });
      const next = searchParams.get('next') ?? '/chat';
      router.push(next);
    } catch (err) {
      const e = err as { response?: { status?: number }; code?: string };
      const status = e.response?.status;
      if (status === 401 || status === 422) {
        setFormError('invalidCredentials');
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
          aria-describedby={formError ? 'login-form-error' : undefined}
        >
          <div className="flex flex-col gap-1">
            <Label htmlFor="login-pseudo">{t('pseudoLabel')}</Label>
            <Input
              id="login-pseudo"
              name="pseudo"
              autoComplete="username"
              value={pseudo}
              onChange={(e) => setPseudo(e.target.value)}
              onBlur={() => setPseudoTouched(true)}
              invalid={pseudoInvalid}
              required
              placeholder={t('pseudoPlaceholder')}
              aria-invalid={pseudoInvalid || undefined}
              aria-describedby={pseudoInvalid ? 'login-pseudo-error' : undefined}
            />
            {pseudoInvalid ? (
              <p
                id="login-pseudo-error"
                role="alert"
                className="text-sm text-error"
              >
                {tErrors('invalidPseudo')}
              </p>
            ) : null}
          </div>

          <div className="flex flex-col gap-1">
            <Label htmlFor="login-password">{t('passwordLabel')}</Label>
            <Input
              id="login-password"
              name="password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              placeholder={t('passwordPlaceholder')}
            />
          </div>

          {formError ? (
            <p
              id="login-form-error"
              role="alert"
              className="text-sm text-error"
            >
              {tErrors(formError)}
            </p>
          ) : null}

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
          {t('noAccount')}{' '}
          <Link
            href={{
              pathname: '/register',
              query: searchParams.get('next')
                ? { next: searchParams.get('next') ?? undefined }
                : undefined,
            }}
            className="text-primary-strong underline underline-offset-2 hover:no-underline focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/30 focus-visible:ring-offset-2 focus-visible:ring-offset-canvas rounded-sm"
          >
            {t('registerLink')}
          </Link>
        </p>
      </Card>
    </div>
  );
}
