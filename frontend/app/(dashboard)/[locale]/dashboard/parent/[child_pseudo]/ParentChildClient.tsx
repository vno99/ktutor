'use client';

import { useEffect, useState } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { AxiosError } from 'axios';
import { AlertTriangle, ArrowLeft, Loader2 } from 'lucide-react';
import { Card } from '@/components/Card';
import { Link } from '@/i18n/navigation';
import { apiClient } from '@/lib/api';
import { useAuthStore } from '@/lib/stores/authStore';
import { DashboardClient } from '../../eleve/DashboardClient';

/*
 * ParentChildClient — child-detail view of the parent dashboard
 * (s17).
 *
 * The page is rendered through the same DashboardClient as the
 * eleve dashboard (s16), with `readOnly={true}` so the parent's
 * view hides the action buttons (CTA "Aller au chat" on the
 * empty state, "Voir les détails" on the subject cards). The
 * Refresh + Retry buttons stay — a parent can refresh and the
 * retry semantics are identical for them.
 *
 * The page is fetched via GET /api/dashboard/eleve?pseudo=<child>
 * (the s16 endpoint), which delegates the cross-tenant check to
 * `assert_parent_linked_to_child_or_403` (s17 helper). On 403
 * we render a custom Card that points back to the list — the
 * generic DashboardClient error is overridden here.
 *
 * 401 falls through to the global AuthGuard (redirect to login).
 *
 * All copy is i18n-ised via useTranslations('dashboard.parent').
 */
type ErrorCode =
  | { kind: 'network' }
  | { kind: 'http'; status: number }
  | { kind: 'unknown' };

function toErrorCode(err: unknown): ErrorCode {
  if (err instanceof AxiosError) {
    if (!err.response) return { kind: 'network' };
    return { kind: 'http', status: err.response.status };
  }
  return { kind: 'unknown' };
}

export function ParentChildClient({ childPseudo }: { childPseudo: string }) {
  const t = useTranslations('dashboard.parent');
  const locale = useLocale();
  const accessToken = useAuthStore((s) => s.accessToken);
  const hydrated = useAuthStore((s) => s.hydrated);

  const [error, setError] = useState<ErrorCode | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    if (!hydrated) return;
    if (!accessToken) return;
    // The s16 endpoint accepts `?pseudo=` for admin bypass; the
    // s17 helper `assert_parent_linked_to_child_or_403` enforces
    // the parent↔child link for the parent caller. A 403 here
    // means the parent is NOT linked to this child.
    apiClient
      .get(`/api/dashboard/eleve`, { params: { pseudo: childPseudo } })
      .then(() => {
        setIsLoading(false);
      })
      .catch((err: unknown) => {
        setError(toErrorCode(err));
        setIsLoading(false);
      });
  }, [hydrated, accessToken, childPseudo]);

  if (isLoading && !error) {
    return (
      <div className="max-w-3xl mx-auto px-4 md:px-6 py-4 md:py-6 flex flex-col gap-4">
        <BackLink />
        <Card
          role="status"
          aria-live="polite"
          className="flex items-center justify-center gap-2"
        >
          <Loader2 size={20} className="animate-spin text-text-secondary" aria-hidden="true" />
          <span className="text-sm text-text-secondary">
            {t('loadingDetail', { child: childPseudo })}
          </span>
        </Card>
      </div>
    );
  }

  if (error && error.kind === 'http' && error.status === 403) {
    return (
      <div className="max-w-3xl mx-auto px-4 md:px-6 py-4 md:py-6 flex flex-col gap-4">
        <BackLink />
        <Card role="alert" className="bg-error/10 border border-error/30">
          <div className="flex items-start gap-3">
            <AlertTriangle
              size={24}
              className="text-error shrink-0"
              aria-hidden="true"
            />
            <div className="flex-1 flex flex-col gap-1">
              <p className="text-base text-text-primary font-medium">
                {t('detail403')}
              </p>
              <p className="text-xs text-text-secondary">Code : forbidden</p>
              <Link
                href="/dashboard/parent"
                className="mt-2 inline-flex items-center justify-center h-11 px-4 text-base font-medium rounded-sm bg-primary text-white hover:bg-primary-strong focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/30 focus-visible:ring-offset-2 focus-visible:ring-offset-canvas self-start"
              >
                {t('backToList')}
              </Link>
            </div>
          </div>
        </Card>
      </div>
    );
  }

  // Success (or generic error) — let the DashboardClient manage
  // its own 4 states. The readOnly prop hides the parent's
  // forbidden buttons (CTA + "Voir les détails"). Generic
  // network/500 errors fall through to DashboardClient's
  // ErrorState.
  return <DashboardClient readOnly={true} />;
}

function BackLink() {
  const t = useTranslations('dashboard.parent');
  return (
    <Link
      href="/dashboard/parent"
      className="text-sm text-text-secondary hover:text-primary inline-flex items-center gap-1 self-start"
    >
      <ArrowLeft size={16} aria-hidden="true" />
      <span>{t('backToList')}</span>
    </Link>
  );
}
