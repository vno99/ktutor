'use client';

import { useEffect, useState } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { Link } from '@/i18n/navigation';
import { AlertTriangle, ChevronRight, Loader2, MessageCircle, RefreshCw } from 'lucide-react';
import { Card } from '@/components/Card';
import { useAuthStore } from '@/lib/stores/authStore';
import {
  fetchHistory,
  HistoryError,
  type ConversationListItem,
  type HistoryListResponse,
  type HistorySubject,
} from '@/lib/api/history';
import { formatRelativeTime } from '@/lib/intl/relativeTime';

/*
 * HistoryListClient — client subcomponent of the /history page (s19).
 *
 * Fetches the paginated conversation list from GET /api/chat/history
 * (the apiClient interceptor adds the JWT bearer from the authStore).
 * 4 UI states: loading, empty, error, success.
 *
 * The page is pure presentational — no new shared component per
 * ADR 015 § Decision 5 (the relative-time formatter is the
 * lib/intl/relativeTime helper, not a <RelativeTime> component). The
 * subject badge is a <span> with the design-system pill classes,
 * inline (cf. design-system gap #1 — a <Badge> shared component is
 * reserved for s22).
 *
 * All copy is i18n-ised via useTranslations('history'). No hardcoded
 * strings — verified by frontend/scripts/check-i18n.sh.
 */
type FetchedState =
  | { kind: 'error'; code: 'network' | 'http_401' | 'http_403' | 'http_5xx' | 'unknown' }
  | { kind: 'success'; data: HistoryListResponse };

const PAGE_SIZE = 20;
const SUBJECT_LABELS: Record<HistorySubject, 'subjectMaths' | 'subjectFrancais'> = {
  maths: 'subjectMaths',
  francais: 'subjectFrancais',
};
const SUBJECT_PILL: Record<HistorySubject, string> = {
  // ``bg-primary`` (deep blue #3D5AFE) + white text passes 4.5:1
  // (the maths pill).
  maths: 'bg-primary text-white',
  // ``bg-accent-warm`` (light orange #FF6B4A) does NOT pass 4.5:1
  // with white text. We use ``text-text-primary`` (very dark
  // #0D0F14) instead — a light pill with dark text.
  francais: 'bg-accent-warm text-text-primary',
};

export function HistoryListClient() {
  const t = useTranslations('history');
  const tChat = useTranslations('chat');
  const locale = useLocale();

  const accessToken = useAuthStore((s) => s.accessToken);
  const hydrated = useAuthStore((s) => s.hydrated);

  const [state, setState] = useState<FetchedState | null>(null);
  const [subject, setSubject] = useState<HistorySubject | null>(null);
  const [offset, setOffset] = useState(0);

  // Re-fetch when the subject filter or the page offset changes.
  // The apiClient interceptor reads the token on the client side
  // before each request; we wait for hydration + a token to avoid
  // an unauthenticated first request.
  //
  // The setState calls are inside ``.then`` / ``.catch`` /
  // ``.finally`` promise-chain callbacks, which the
  // react-hooks/set-state-in-effect rule does not track (it
  // analyses the synchronous call chain only). The rule's IR
  // does not see setState through a promise, so the inline
  // setState in those callbacks is not flagged.
  useEffect(() => {
    if (!hydrated) return;
    if (!accessToken) return;
    fetchHistory({ limit: PAGE_SIZE, offset, subject })
      .then((data) => {
        setState({ kind: 'success', data });
      })
      .catch((err: unknown) => {
        if (err instanceof HistoryError) {
          if (err.code === 'http_404') {
            // 404 on the list endpoint is not in the contract — the
            // backend always returns 200 + an empty list. We collapse
            // it to the empty state for defence in depth.
            setState({
              kind: 'success',
              data: { items: [], total: 0, limit: PAGE_SIZE, offset },
            });
            return;
          }
          const code =
            err.code === 'network' ||
            err.code === 'http_401' ||
            err.code === 'http_403' ||
            err.code === 'http_5xx' ||
            err.code === 'unknown'
              ? err.code
              : 'unknown';
          setState({ kind: 'error', code });
          return;
        }
        setState({ kind: 'error', code: 'unknown' });
      });
  }, [hydrated, accessToken, subject, offset]);

  function refetch() {
    setOffset(0);
    fetchHistory({ limit: PAGE_SIZE, offset: 0, subject })
      .then((data) => {
        setState({ kind: 'success', data });
      })
      .catch((err: unknown) => {
        if (err instanceof HistoryError) {
          if (err.code === 'http_404') {
            setState({
              kind: 'success',
              data: { items: [], total: 0, limit: PAGE_SIZE, offset: 0 },
            });
            return;
          }
          const code =
            err.code === 'network' ||
            err.code === 'http_401' ||
            err.code === 'http_403' ||
            err.code === 'http_5xx' ||
            err.code === 'unknown'
              ? err.code
              : 'unknown';
          setState({ kind: 'error', code });
          return;
        }
        setState({ kind: 'error', code: 'unknown' });
      });
  }

  return (
    <div
      className="max-w-3xl mx-auto px-4 md:px-6 py-4 md:py-6 flex flex-col gap-4"
      aria-busy={state === null}
    >
      <header className="flex flex-col gap-1">
        <h1 className="text-2xl md:text-3xl font-semibold tracking-tight text-text-primary">
          {t('title')}
        </h1>
      </header>

      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-2">
        <label htmlFor="history-subject-filter" className="sr-only">
          {t('filterAllSubjects')}
        </label>
        <select
          id="history-subject-filter"
          data-testid="history-subject-filter"
          value={subject ?? ''}
          onChange={(e) => {
            const v = e.target.value;
            setSubject(v === '' ? null : (v as HistorySubject));
            setOffset(0);
          }}
          className="h-11 px-3 text-base bg-surface border border-border rounded-sm text-text-primary w-full md:w-48"
        >
          <option value="">{t('filterAllSubjects')}</option>
          <option value="maths">{t('filterMaths')}</option>
          <option value="francais">{t('filterFrancais')}</option>
        </select>
      </div>

      {state === null ? <LoadingCard label={t('loading')} /> : null}

      {state?.kind === 'error' ? (
        <ErrorState code={state.code} onRetry={refetch} />
      ) : null}

      {state?.kind === 'success' ? (
        state.data.items.length === 0 ? (
          <EmptyState />
        ) : (
          <SuccessState
            items={state.data.items}
            total={state.data.total}
            offset={offset}
            onPrev={() => setOffset((o) => Math.max(0, o - PAGE_SIZE))}
            onNext={() => setOffset((o) => o + PAGE_SIZE)}
            locale={locale}
          />
        )
      ) : null}

      {/* No router reference needed — the list navigates via <a>
          on each card (declared inline with locale prefix). */}
    </div>
  );
}

function LoadingCard({ label }: { label: string }) {
  return (
    <Card role="status" aria-live="polite" className="flex items-center justify-center gap-2">
      <Loader2 size={20} className="animate-spin text-text-secondary" aria-hidden="true" />
      <span className="text-sm text-text-secondary">{label}</span>
    </Card>
  );
}

function EmptyState() {
  const t = useTranslations('history');
  const locale = useLocale();
  return (
    <Card className="flex flex-col items-center gap-3 py-8 text-center">
      <MessageCircle size={32} className="text-text-tertiary" aria-hidden="true" />
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

function ErrorState({
  code,
  onRetry,
}: {
  code: 'network' | 'http_401' | 'http_403' | 'http_5xx' | 'unknown';
  onRetry: () => void;
}) {
  const t = useTranslations('history');
  const locale = useLocale();
  const message =
    code === 'network'
      ? t('errorNetwork')
      : code === 'http_401'
        ? t('error401')
        : code === 'http_403'
          ? t('error403')
          : t('error500');
  return (
    <Card role="alert" className="bg-error/10 border border-error/30">
      <div className="flex items-start gap-3">
        <AlertTriangle size={24} className="text-error shrink-0" aria-hidden="true" />
        <div className="flex-1 flex flex-col gap-2">
          <p className="text-base text-text-primary font-medium">{t('errorTitle')}</p>
          <p className="text-sm text-text-secondary">{message}</p>
          {code === 'http_401' ? (
            <a
              href={`/${locale}/login`}
              className="mt-2 inline-flex items-center justify-center h-11 px-4 text-base font-medium rounded-sm bg-primary text-white hover:bg-primary-strong focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/30 focus-visible:ring-offset-2 focus-visible:ring-offset-canvas self-start"
            >
              {t('reconnect')}
            </a>
          ) : (
            <button
              type="button"
              onClick={onRetry}
              className="mt-2 self-start inline-flex items-center justify-center h-11 px-4 text-base font-medium rounded-sm bg-primary text-white hover:bg-primary-strong focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/30 focus-visible:ring-offset-2 focus-visible:ring-offset-canvas"
            >
              <RefreshCw size={16} className="mr-2" aria-hidden="true" />
              {t('retry')}
            </button>
          )}
        </div>
      </div>
    </Card>
  );
}

function SuccessState({
  items,
  total,
  offset,
  onPrev,
  onNext,
  locale,
}: {
  items: ConversationListItem[];
  total: number;
  offset: number;
  onPrev: () => void;
  onNext: () => void;
  locale: string;
}) {
  const t = useTranslations('history');
  const tChat = useTranslations('chat');
  const prevDisabled = offset === 0;
  const nextDisabled = offset + items.length >= total;
  return (
    <>
      <ul className="flex flex-col gap-3" data-testid="history-list">
        {items.map((item) => (
          <li key={item.id}>
            <Link
              href={`/history/${item.id}`}
              className="block focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/30 rounded-md"
              aria-label={t('openConversation')}
              data-testid={`history-item-${item.id}`}
            >
              <Card
                className="flex flex-col gap-2 hover:bg-surface-subtle transition-colors cursor-pointer"
              >
                <div className="flex items-center justify-between gap-3">
                  <span
                    className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${SUBJECT_PILL[item.subject]}`}
                    data-testid={`history-subject-${item.id}`}
                  >
                    {tChat(SUBJECT_LABELS[item.subject])}
                  </span>
                  <ChevronRight size={20} className="text-text-tertiary shrink-0" aria-hidden="true" />
                </div>
                <p className="text-base text-text-primary line-clamp-2">{item.first_question}</p>
                <div className="flex flex-wrap items-center gap-2 text-xs text-text-secondary">
                  <span>{t('metaCount', { count: item.message_count })}</span>
                  <span aria-hidden="true">·</span>
                  <time dateTime={item.last_activity_at}>
                    {formatRelativeTime(item.last_activity_at, locale)}
                  </time>
                </div>
              </Card>
            </Link>
          </li>
        ))}
      </ul>
      <nav
        aria-label={t('paginationLabel')}
        className="flex flex-col md:flex-row gap-2 md:justify-between pt-2"
      >
        <button
          type="button"
          onClick={onPrev}
          disabled={prevDisabled}
          aria-disabled={prevDisabled}
          aria-label={t('previousAria')}
          tabIndex={prevDisabled ? -1 : 0}
          className="inline-flex items-center justify-center h-11 px-4 text-base font-medium rounded-sm bg-surface text-text-primary border border-border hover:bg-surface-subtle disabled:opacity-50 disabled:cursor-not-allowed focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/30 focus-visible:ring-offset-2 focus-visible:ring-offset-canvas"
          data-testid="history-prev"
        >
          {t('previous')}
        </button>
        <button
          type="button"
          onClick={onNext}
          disabled={nextDisabled}
          aria-disabled={nextDisabled}
          aria-label={t('nextAria')}
          tabIndex={nextDisabled ? -1 : 0}
          className="inline-flex items-center justify-center h-11 px-4 text-base font-medium rounded-sm bg-surface text-text-primary border border-border hover:bg-surface-subtle disabled:opacity-50 disabled:cursor-not-allowed focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/30 focus-visible:ring-offset-2 focus-visible:ring-offset-canvas"
          data-testid="history-next"
        >
          {t('next')}
        </button>
      </nav>
    </>
  );
}
