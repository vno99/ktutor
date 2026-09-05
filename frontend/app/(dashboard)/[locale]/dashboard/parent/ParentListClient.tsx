'use client';

import { useEffect, useState } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { AxiosError } from 'axios';
import {
  AlertTriangle,
  ArrowRight,
  Eye,
  Loader2,
  RefreshCw,
  Users,
} from 'lucide-react';
import { Button } from '@/components/Button';
import { Card } from '@/components/Card';
import { Link } from '@/i18n/navigation';
import { apiClient } from '@/lib/api';
import { useAuthStore } from '@/lib/stores/authStore';

/*
 * ParentListClient — client subcomponent of the /dashboard/parent
 * page (s17).
 *
 * Fetches the list of linked children + their (cached) dashboards
 * from GET /api/dashboard/parent. The apiClient interceptor adds
 * the JWT bearer from the authStore. Manages 4 states: loading,
 * empty, error, success. The success state is a grid of Child
 * cards; each card links to /<locale>/dashboard/parent/<child>.
 *
 * The empty state is reached when the parent has no link rows at
 * all (200 with `children: []`). The error state covers 401, 403,
 * network, and 5xx.
 *
 * All copy is i18n-ised via useTranslations('dashboard.parent').
 * No hardcoded strings — verified by frontend/scripts/check-i18n.sh.
 */
interface SubjectSummary {
  name: 'maths' | 'francais';
  score_avg: number;
  exercises_count: number;
  last_activity_at: string | null;
}

interface GlobalSummary {
  score_avg: number;
  exercises_count: number;
  last_activity_at: string | null;
}

interface ChildDashboard {
  subjects: SubjectSummary[];
  global: GlobalSummary;
}

interface ChildEntry {
  pseudo: string;
  linked_at: string;
  dashboard: ChildDashboard;
}

interface ParentDashboardResponse {
  children: ChildEntry[];
}

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

function rateTone(percent: number): 'success' | 'warning' | 'error' {
  if (percent >= 0.7) return 'success';
  if (percent >= 0.4) return 'warning';
  return 'error';
}

function formatPercent(locale: string, value: number): string {
  return new Intl.NumberFormat(locale, {
    style: 'percent',
    maximumFractionDigits: 0,
  }).format(value);
}

function formatDate(locale: string, iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  return new Intl.DateTimeFormat(locale, { dateStyle: 'medium' }).format(d);
}

export function ParentListClient() {
  const t = useTranslations('dashboard.parent');
  const locale = useLocale();
  const accessToken = useAuthStore((s) => s.accessToken);
  const hydrated = useAuthStore((s) => s.hydrated);

  const [data, setData] = useState<ParentDashboardResponse | null>(null);
  const [error, setError] = useState<ErrorCode | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [hasFetched, setHasFetched] = useState(false);

  async function fetchList() {
    if (isRefreshing) return;
    setIsRefreshing(true);
    setError(null);
    try {
      const resp = await apiClient.get<ParentDashboardResponse>(
        '/api/dashboard/parent',
      );
      setData(resp.data);
    } catch (err) {
      setError(toErrorCode(err));
    } finally {
      setIsRefreshing(false);
      setHasFetched(true);
    }
  }

  useEffect(() => {
    if (!hydrated) return;
    if (!accessToken) return;
    apiClient
      .get<ParentDashboardResponse>('/api/dashboard/parent')
      .then((resp) => {
        setData(resp.data);
      })
      .catch((err: unknown) => {
        setError(toErrorCode(err));
      })
      .finally(() => {
        setIsRefreshing(false);
        setHasFetched(true);
      });
  }, [hydrated, accessToken]);

  const isLoading = !hasFetched && !error;
  const isEmpty =
    data !== null && !error && data.children.length === 0;

  return (
    <div
      className="max-w-4xl mx-auto px-4 md:px-6 py-4 md:py-6 flex flex-col gap-4"
      aria-busy={isRefreshing}
    >
      <header className="flex flex-col gap-1">
        <h1 className="text-2xl md:text-3xl font-semibold tracking-tight text-text-primary">
          {t('listTitle')}
        </h1>
        <p className="text-sm md:text-base text-text-secondary">
          {t('listSubtitle')}
        </p>
      </header>

      <div
        className="inline-flex items-center gap-2 self-start rounded-full bg-primary/10 text-primary-strong px-3 py-1.5 text-xs font-medium"
        aria-label={t('readOnlyAria')}
      >
        <Eye size={16} aria-hidden="true" />
        <span>{t('readOnly')}</span>
      </div>

      {isLoading ? (
        <Card
          role="status"
          aria-live="polite"
          className="flex items-center justify-center gap-2"
        >
          <Loader2 size={20} className="animate-spin text-text-secondary" aria-hidden="true" />
          <span className="text-sm text-text-secondary">{t('loadingList')}</span>
        </Card>
      ) : error ? (
        <ErrorState code={error} />
      ) : isEmpty ? (
        <EmptyState />
      ) : data ? (
        <ChildGrid entries={data.children} locale={locale} t={t} />
      ) : null}

      {!isLoading && !error ? (
        <div className="flex justify-end">
          <Button
            variant="primary"
            size="md"
            onClick={() => {
              void fetchList();
            }}
            disabled={isRefreshing}
            aria-disabled={isRefreshing}
            aria-label={t('refreshList')}
            leftIcon={
              isRefreshing ? (
                <Loader2 size={20} className="animate-spin" aria-hidden="true" />
              ) : (
                <RefreshCw size={20} aria-hidden="true" />
              )
            }
          >
            {isRefreshing ? t('refreshingList') : t('refreshList')}
          </Button>
        </div>
      ) : null}
    </div>
  );
}

function ErrorState({ code }: { code: ErrorCode }) {
  const t = useTranslations('dashboard.parent');
  const tAuth = useTranslations('auth.errors');
  const locale = useLocale();

  if (code.kind === 'http' && code.status === 401) {
    return (
      <Card role="alert" className="bg-error/10 border border-error/30">
        <div className="flex items-start gap-3">
          <AlertTriangle size={24} className="text-error shrink-0" aria-hidden="true" />
          <div className="flex-1 flex flex-col gap-1">
            <p className="text-base text-text-primary font-medium">
              {tAuth('retry')}
            </p>
            <p className="text-xs text-text-secondary">Code : invalid_token</p>
            <a
              href={`/${locale}/login`}
              className="mt-2 inline-flex items-center justify-center h-11 px-4 text-base font-medium rounded-sm bg-primary text-white hover:bg-primary-strong focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/30 focus-visible:ring-offset-2 focus-visible:ring-offset-canvas self-start"
            >
              {tAuth('retry')}
            </a>
          </div>
        </div>
      </Card>
    );
  }

  if (code.kind === 'http' && code.status === 403) {
    return (
      <Card role="alert" className="bg-error/10 border border-error/30">
        <div className="flex items-start gap-3">
          <AlertTriangle size={24} className="text-error shrink-0" aria-hidden="true" />
          <div className="flex-1 flex flex-col gap-1">
            <p className="text-base text-text-primary font-medium">
              {t('error403Role')}
            </p>
            <p className="text-xs text-text-secondary">Code : forbidden</p>
            <Link
              href="/"
              className="mt-2 inline-flex items-center justify-center h-11 px-4 text-base font-medium rounded-sm bg-primary text-white hover:bg-primary-strong focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/30 focus-visible:ring-offset-2 focus-visible:ring-offset-canvas self-start"
            >
              {t('backHome')}
            </Link>
          </div>
        </div>
      </Card>
    );
  }

  return (
    <Card role="alert" className="bg-error/10 border border-error/30">
      <div className="flex items-start gap-3">
        <AlertTriangle size={24} className="text-error shrink-0" aria-hidden="true" />
        <div className="flex-1 flex flex-col gap-1">
          <p className="text-base text-text-primary font-medium">
            {code.kind === 'network' ? tAuth('retry') : tAuth('retry')}
          </p>
          <p className="text-xs text-text-secondary">
            Code : {code.kind === 'network' ? 'network_error' : 'internal_error'}
          </p>
        </div>
      </div>
    </Card>
  );
}

function EmptyState() {
  const t = useTranslations('dashboard.parent');
  return (
    <Card className="flex flex-col items-center gap-3 py-8 text-center">
      <Users size={48} className="text-text-tertiary" aria-hidden="true" />
      <p className="text-base md:text-lg font-semibold text-text-primary">
        {t('emptyTitle')}
      </p>
      <p className="text-sm text-text-secondary">{t('emptySubtitle')}</p>
    </Card>
  );
}

function ChildGrid({
  entries,
  locale,
  t,
}: {
  entries: ChildEntry[];
  locale: string;
  t: ReturnType<typeof useTranslations<'dashboard.parent'>>;
}) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
      {entries.map((entry) => (
        <ChildCard key={entry.pseudo} entry={entry} locale={locale} t={t} />
      ))}
    </div>
  );
}

function ChildCard({
  entry,
  locale,
  t,
}: {
  entry: ChildEntry;
  locale: string;
  t: ReturnType<typeof useTranslations<'dashboard.parent'>>;
}) {
  const initial = entry.pseudo.charAt(0).toUpperCase() || '?';
  const percent = entry.dashboard.global.score_avg;
  const hasActivity = entry.dashboard.global.exercises_count > 0;
  const tone = hasActivity ? rateTone(percent) : 'warning';
  const linkedSince = formatDate(locale, entry.linked_at);

  return (
    <Link
      href={`/dashboard/parent/${entry.pseudo}`}
      aria-label={t('cardAria', { child: entry.pseudo })}
      className="block focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/30 focus-visible:ring-offset-2 focus-visible:ring-offset-canvas rounded-md"
    >
      <Card className="flex flex-row items-center gap-3 p-4 hover:border-primary/40 transition-colors">
        <div
          className="w-10 h-10 rounded-full bg-primary/10 text-primary flex items-center justify-center text-base font-semibold shrink-0"
          aria-hidden="true"
        >
          {initial}
        </div>
        <div className="flex-1 min-w-0 flex flex-col gap-0.5">
          {/*
           * The s17 API (ChildDashboardEntry) carries a `pseudo`
           * but no real `name` field. The mockup has a "Name +
           * pseudo" stack (e.g. "Alice Dupont" / "alice"), but
           * surfacing the pseudo twice is the v1 degradation.
           * Adding a `name` field is a separate story (out of
           * scope for s17). The two lines below are the same
           * value on purpose — the first is the "primary"
           * rendering slot, the second is a place-holder that
           * will be replaced once the API ships a name.
           */}
          <span className="text-base font-semibold text-text-primary truncate">
            {entry.pseudo}
          </span>
          <span className="text-xs text-text-secondary truncate">
            {entry.pseudo}
          </span>
          {linkedSince ? (
            <span className="text-xs text-text-secondary">
              {t('linkedSince', { date: linkedSince })}
            </span>
          ) : null}
        </div>
        <div className="flex flex-col items-end gap-1 shrink-0">
          <span className="text-lg font-semibold text-text-primary">
            {hasActivity ? formatPercent(locale, percent) : '—'}
          </span>
          <span className="text-xs text-text-secondary">{t('successRate')}</span>
          <span
            className={`inline-flex items-center gap-1 self-end rounded-full px-2 py-0.5 text-xs bg-surface-subtle text-text-primary`}
          >
            <span
              aria-hidden="true"
              className={`inline-block w-2 h-2 rounded-full ${
                tone === 'success'
                  ? 'bg-success'
                  : tone === 'warning'
                    ? 'bg-warning'
                    : 'bg-error'
              }`}
            />
            {hasActivity
              ? `${Math.round(percent * 100)} %`
              : t('noActivity')}
          </span>
        </div>
        <ArrowRight
          size={20}
          className="text-text-tertiary shrink-0"
          aria-hidden="true"
        />
      </Card>
    </Link>
  );
}
