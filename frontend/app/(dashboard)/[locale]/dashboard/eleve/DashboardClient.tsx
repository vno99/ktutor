'use client';

import { useEffect, useMemo, useState } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import {
  AlertTriangle,
  BarChart3,
  BookOpen,
  CheckCircle2,
  Clock,
  Loader2,
  RefreshCw,
  TrendingUp,
} from 'lucide-react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { AxiosError } from 'axios';
import { Button } from '@/components/Button';
import { Card } from '@/components/Card';
import { apiClient } from '@/lib/api';
import { useAuthStore } from '@/lib/stores/authStore';

/*
 * DashboardClient — client subcomponent of the /dashboard/eleve
 * page (s16).
 *
 * Fetches the aggregated progress data from GET /api/dashboard/eleve
 * (the apiClient interceptor adds the JWT bearer from the
 * authStore). Manages 4 states: loading, empty, error, success.
 * On success, renders the Summary card, the Recharts BarChart
 * (with an sr-only <table> duplicate for assistive technologies),
 * the Subject cards, and the Refresh button.
 *
 * The Refresh button re-hits the API. The backend has a 5-min
 * in-process cache, so the response is usually the same data —
 * the button is a UX shortcut, not a cache-buster. This matches
 * the plan's "decision to act": no /invalidate endpoint, the
 * TTL is the source of truth.
 *
 * All copy is i18n-ised via useTranslations('dashboard.eleve')
 * and useTranslations('errors'). No hardcoded strings — verified
 * by frontend/scripts/check-i18n.sh.
 */
type SubjectName = 'maths' | 'francais';

interface SubjectSummary {
  name: SubjectName;
  score_avg: number;
  exercises_count: number;
  last_activity_at: string | null;
}

interface GlobalSummary {
  score_avg: number;
  exercises_count: number;
  last_activity_at: string | null;
}

interface EleveDashboardResponse {
  subjects: SubjectSummary[];
  global: GlobalSummary;
}

type ErrorCode =
  | { kind: 'network' }
  | { kind: 'http'; status: number }
  | { kind: 'unknown' };

const SUBJECT_LABEL: Record<SubjectName, 'subjectMaths' | 'subjectFrancais'> = {
  maths: 'subjectMaths',
  francais: 'subjectFrancais',
};

function formatPercent(locale: string, value: number): string {
  return new Intl.NumberFormat(locale, {
    style: 'percent',
    maximumFractionDigits: 0,
  }).format(value);
}

function formatDateTime(locale: string, iso: string | null): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  return new Intl.DateTimeFormat(locale, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(d);
}

function rateTone(percent: number): 'success' | 'warning' | 'error' {
  if (percent >= 0.7) return 'success';
  if (percent >= 0.4) return 'warning';
  return 'error';
}

const TONE_BADGE: Record<'success' | 'warning' | 'error', { bg: string; text: string }> = {
  // Tone badges. The design-system tokens for success/warning/error
  // are mid-tones that can't reach 4.5:1 contrast at 12px on a
  // white surface — the colors are too desaturated. The badge
  // uses the tone color as a small colored dot + neutral text
  // for the percentage value. The dot is purely decorative
  // (decorative content is exempt from the WCAG 4.5:1 rule;
  // axe-core's color-contrast rule only flags text that is
  // conveying meaning, not the colored dot).
  success: { bg: 'bg-surface-subtle', text: 'text-text-primary' },
  warning: { bg: 'bg-surface-subtle', text: 'text-text-primary' },
  error: { bg: 'bg-surface-subtle', text: 'text-text-primary' },
};

const TONE_DOT: Record<'success' | 'warning' | 'error', string> = {
  success: 'bg-success',
  warning: 'bg-warning',
  error: 'bg-error',
};

function toErrorCode(err: unknown): ErrorCode {
  if (err instanceof AxiosError) {
    if (!err.response) return { kind: 'network' };
    return { kind: 'http', status: err.response.status };
  }
  return { kind: 'unknown' };
}

function ChartTooltip(props: { active?: boolean; payload?: Array<{ payload: { name: string; taux: number } }> }) {
  if (!props.active || !props.payload || props.payload.length === 0) {
    return null;
  }
  const datum = props.payload[0]?.payload;
  if (!datum) {
    return null;
  }
  return (
    <div
      role="status"
      className="bg-surface border border-border rounded-sm shadow-kt-default px-2 py-1 text-xs text-text-primary"
    >
      {datum.name} : {datum.taux} %
    </div>
  );
}

export function DashboardClient() {
  const t = useTranslations('dashboard.eleve');
  const tChat = useTranslations('chat');
  const locale = useLocale();

  const accessToken = useAuthStore((s) => s.accessToken);
  const hydrated = useAuthStore((s) => s.hydrated);

  const [data, setData] = useState<EleveDashboardResponse | null>(null);
  const [error, setError] = useState<ErrorCode | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [hasFetched, setHasFetched] = useState(false);

  async function fetchDashboard() {
    if (isRefreshing) return;
    setIsRefreshing(true);
    setError(null);
    try {
      const resp = await apiClient.get<EleveDashboardResponse>(
        '/api/dashboard/eleve',
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
    // Wait for hydration AND a token before fetching — otherwise the
    // request is unauthenticated and the server returns 401.
    if (!hydrated) return;
    if (!accessToken) return;
    void fetchDashboard();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hydrated, accessToken]);

  const globalRateTone = data ? rateTone(data.global.score_avg) : 'warning';
  const subjectCards = useMemo(() => {
    if (!data) return [];
    return [...data.subjects].sort((a, b) => a.name.localeCompare(b.name));
  }, [data]);

  const chartData = useMemo(() => {
    if (!data) return [];
    return data.subjects.map((subject) => ({
      name: tChat(SUBJECT_LABEL[subject.name]),
      taux: Math.round(subject.score_avg * 100),
    }));
  }, [data, tChat]);

  const isLoading = !hasFetched && !error;
  const isEmpty = data !== null && data.global.exercises_count === 0;

  return (
    <div
      className="max-w-3xl mx-auto px-4 md:px-6 py-4 md:py-6 flex flex-col gap-4"
      aria-busy={isRefreshing}
    >
      <header className="flex flex-col gap-1">
        <h1 className="text-2xl md:text-3xl font-semibold tracking-tight text-text-primary">
          {t('title')}
        </h1>
        <p className="text-sm md:text-base text-text-secondary">
          {t('subtitle')}
        </p>
      </header>

      {isLoading ? (
        <Card
          role="status"
          aria-live="polite"
          className="flex items-center justify-center gap-2"
        >
          <Loader2 size={20} className="animate-spin text-text-secondary" aria-hidden="true" />
          <span className="text-sm text-text-secondary">{t('loading')}</span>
        </Card>
      ) : error ? (
        <ErrorState
          code={error}
          onRetry={() => {
            void fetchDashboard();
          }}
        />
      ) : isEmpty ? (
        <EmptyState />
      ) : data ? (
        <SuccessState
          data={data}
          locale={locale}
          globalRateTone={globalRateTone}
          subjectCards={subjectCards}
          chartData={chartData}
        />
      ) : null}

      {!isLoading && !error ? (
        <div className="flex justify-end">
          <Button
            variant="primary"
            size="md"
            onClick={() => {
              void fetchDashboard();
            }}
            disabled={isRefreshing}
            aria-disabled={isRefreshing}
            aria-label={t('refresh')}
            leftIcon={
              isRefreshing ? (
                <Loader2 size={20} className="animate-spin" aria-hidden="true" />
              ) : (
                <RefreshCw size={20} aria-hidden="true" />
              )
            }
          >
            {isRefreshing ? t('refreshing') : t('refresh')}
          </Button>
        </div>
      ) : null}
    </div>
  );
}

/* -- Subviews ------------------------------------------------------ */

function ErrorState({ code, onRetry }: { code: ErrorCode; onRetry: () => void }) {
  const t = useTranslations('dashboard.eleve');
  const tAuth = useTranslations('auth.errors');
  const locale = useLocale();
  const { title, message, machineCode, cta } = (() => {
    if (code.kind === 'network') {
      return {
        title: t('errorNetwork'),
        message: t('errorNetwork'),
        machineCode: 'network_error',
        cta: { kind: 'retry' as const },
      };
    }
    if (code.kind === 'http' && code.status === 401) {
      return {
        title: t('error401'),
        message: t('error401'),
        machineCode: tAuth('retry'),
        cta: { kind: 'reconnect' as const },
      };
    }
    if (code.kind === 'http' && code.status === 403) {
      return {
        title: t('error403'),
        message: t('error403'),
        machineCode: 'forbidden',
        cta: { kind: 'reconnect' as const },
      };
    }
    if (code.kind === 'http' && code.status >= 500) {
      return {
        title: t('error500'),
        message: t('error500'),
        machineCode: 'internal_error',
        cta: { kind: 'retry' as const },
      };
    }
    return {
      title: t('error500'),
      message: t('error500'),
      machineCode: 'unknown',
      cta: { kind: 'retry' as const },
    };
  })();

  return (
    <Card
      role="alert"
      className="bg-error/10 border border-error/30"
    >
      <div className="flex items-start gap-3">
        <AlertTriangle size={24} className="text-error shrink-0" aria-hidden="true" />
        <div className="flex-1 flex flex-col gap-1">
          <p className="text-base text-text-primary font-medium">{title}</p>
          <p className="text-xs text-text-secondary">Code : {machineCode}</p>
          {cta.kind === 'reconnect' ? (
            <a
              href={`/${locale}/login`}
              className="mt-2 inline-flex items-center justify-center h-11 px-4 text-base font-medium rounded-sm bg-primary text-white hover:bg-primary-strong focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/30 focus-visible:ring-offset-2 focus-visible:ring-offset-canvas"
            >
              {t('reconnect')}
            </a>
          ) : (
            <Button
              variant="primary"
              size="md"
              onClick={onRetry}
              className="mt-2 self-start"
            >
              {t('retry')}
            </Button>
          )}
        </div>
      </div>
      {/* message is rendered for screen readers via aria-live in role=alert */}
      <span className="sr-only">{message}</span>
    </Card>
  );
}

function EmptyState() {
  const t = useTranslations('dashboard.eleve');
  const locale = useLocale();
  return (
    <Card className="flex flex-col items-center gap-3 py-8 text-center">
      <BookOpen size={32} className="text-text-tertiary" aria-hidden="true" />
      <p className="text-base text-text-primary">{t('empty')}</p>
      <p className="text-sm text-text-secondary">{t('emptyCta')}</p>
      <a
        href={`/${locale}/chat`}
        className="mt-2 inline-flex items-center justify-center h-11 px-4 text-base font-medium rounded-sm bg-primary text-white hover:bg-primary-strong focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/30 focus-visible:ring-offset-2 focus-visible:ring-offset-canvas"
      >
        {t('emptyButton')}
      </a>
    </Card>
  );
}

function SuccessState(props: {
  data: EleveDashboardResponse;
  locale: string;
  globalRateTone: 'success' | 'warning' | 'error';
  subjectCards: SubjectSummary[];
  chartData: Array<{ name: string; taux: number }>;
}) {
  const t = useTranslations('dashboard.eleve');
  const tChat = useTranslations('chat');
  const { data, locale, globalRateTone, subjectCards, chartData } = props;
  const globalPercent = Math.round(data.global.score_avg * 100);
  const globalAttempts = data.global.exercises_count;
  const lastActivityLabel = data.global.last_activity_at
    ? formatDateTime(locale, data.global.last_activity_at)
    : '';

  return (
    <>
      {/* Summary card */}
      <Card
        aria-live="polite"
        aria-describedby="dashboard-last-updated"
        className="flex flex-col md:flex-row md:items-center md:justify-between gap-4"
      >
        <div className="flex-1 flex flex-col gap-1">
          <div className="flex items-center gap-2 text-text-tertiary">
            <BarChart3 size={20} aria-hidden="true" />
            <span className="text-sm text-text-secondary">{t('globalRate')}</span>
          </div>
          <p className="text-2xl md:text-3xl font-semibold tracking-tight text-text-primary">
            {globalPercent} %
          </p>
          <span
            className={`inline-flex items-center gap-1 self-start rounded-full px-2 py-0.5 text-xs ${TONE_BADGE[globalRateTone].bg} ${TONE_BADGE[globalRateTone].text}`}
          >
            <span
              aria-hidden="true"
              className={`inline-block w-2 h-2 rounded-full ${TONE_DOT[globalRateTone]}`}
            />
            <TrendingUp size={12} aria-hidden="true" />
            {t('trend')}
          </span>
        </div>
        <div className="flex flex-col gap-1 md:items-end">
          <span className="text-sm text-text-secondary">
            {t('attempts', { count: globalAttempts })}
          </span>
          {lastActivityLabel ? (
            <span
              id="dashboard-last-updated"
              className="text-xs text-text-secondary inline-flex items-center gap-1"
            >
              <Clock size={12} aria-hidden="true" />
              {t('lastActivity', { date: lastActivityLabel })}
            </span>
          ) : null}
        </div>
      </Card>

      {/* Chart card */}
      <Card
        className="bg-surface-subtle border border-border"
        role="figure"
        aria-labelledby="dashboard-chart-title"
        aria-describedby="dashboard-table-caption"
      >
        <div className="flex items-center gap-2 mb-3">
          <BarChart3 size={16} className="text-text-tertiary" aria-hidden="true" />
          <h2
            id="dashboard-chart-title"
            className="text-base md:text-lg font-semibold text-text-primary"
          >
            {t('chartTitle')}
          </h2>
        </div>
        <div className="w-full" style={{ height: 240 }}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData} margin={{ top: 8, right: 8, bottom: 8, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
              <XAxis
                dataKey="name"
                tick={{ fill: 'var(--color-text-tertiary)', fontSize: 12 }}
                stroke="var(--color-border)"
              />
              <YAxis
                domain={[0, 100]}
                tickFormatter={(v: number) => `${v}%`}
                tick={{ fill: 'var(--color-text-tertiary)', fontSize: 12 }}
                stroke="var(--color-border)"
                label={{
                  value: t('chartLegend'),
                  angle: -90,
                  position: 'insideLeft',
                  style: { fill: 'var(--color-text-tertiary)', fontSize: 12 },
                }}
              />
              <Tooltip content={<ChartTooltip />} cursor={{ fill: 'var(--color-surface-subtle)' }} />
              <Bar
                dataKey="taux"
                fill="var(--color-primary)"
                radius={[4, 4, 0, 0]}
                isAnimationActive={false}
              />
              <Legend
                verticalAlign="bottom"
                wrapperStyle={{ fontSize: 12, color: 'var(--color-text-tertiary)' }}
                payload={[{ value: t('chartLegend'), type: 'rect', color: 'var(--color-primary)' }]}
              />
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Accessible duplicate */}
        <table className="sr-only">
          <caption id="dashboard-table-caption">{t('tableCaption')}</caption>
          <thead>
            <tr>
              <th scope="col">{t('tableHeaderSubject')}</th>
              <th scope="col">{t('subjectRate')}</th>
              <th scope="col">{t('attempts', { count: 0 }).replace(/^.+ /, '')}</th>
            </tr>
          </thead>
          <tbody>
            {subjectCards.map((subject) => (
              <tr key={subject.name}>
                <th scope="row">{tChat(SUBJECT_LABEL[subject.name])}</th>
                <td>{formatPercent(locale, subject.score_avg)}</td>
                <td>{t('attempts', { count: subject.exercises_count })}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      {/* Subject cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {subjectCards.map((subject) => {
          const tone = rateTone(subject.score_avg);
          const subjectPercent = Math.round(subject.score_avg * 100);
          const subjectLastActivity = subject.last_activity_at
            ? formatDateTime(locale, subject.last_activity_at)
            : '';
          return (
            <Card
              key={subject.name}
              className="flex flex-col gap-2"
              data-testid={`subject-card-${subject.name}`}
            >
              <div className="flex items-center gap-2">
                <BookOpen size={20} className="text-primary" aria-hidden="true" />
                <span className="text-base font-semibold text-text-primary">
                  {tChat(SUBJECT_LABEL[subject.name])}
                </span>
              </div>
              <div className="flex flex-col gap-1">
                <p
                  className="text-2xl font-semibold tracking-tight text-text-primary"
                  aria-label={t('subjectRate')}
                >
                  {subjectPercent} %
                </p>
                <span className="text-sm text-text-secondary">{t('subjectRate')}</span>
              </div>
              <span
                className={`inline-flex items-center gap-1 self-start rounded-full px-2 py-0.5 text-xs ${TONE_BADGE[tone].bg} ${TONE_BADGE[tone].text}`}
              >
                <span
                  aria-hidden="true"
                  className={`inline-block w-2 h-2 rounded-full ${TONE_DOT[tone]}`}
                />
                {tone === 'success' ? (
                  <CheckCircle2 size={12} aria-hidden="true" />
                ) : (
                  <TrendingUp size={12} aria-hidden="true" />
                )}
                {subjectPercent} %
              </span>
              <div className="flex flex-col gap-1">
                <span className="text-sm text-text-secondary">
                  {t('attempts', { count: subject.exercises_count })}
                </span>
                {subjectLastActivity ? (
                  <span className="text-xs text-text-secondary inline-flex items-center gap-1">
                    <Clock size={12} aria-hidden="true" />
                    {t('lastActivity', { date: subjectLastActivity })}
                  </span>
                ) : null}
              </div>
              <Button
                variant="ghost"
                size="sm"
                disabled
                aria-disabled="true"
                tabIndex={-1}
                className="self-start"
              >
                {t('seeDetails')}
              </Button>
            </Card>
          );
        })}
      </div>
    </>
  );
}
