'use client';

import { useEffect, useState } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { useRouter } from 'next/navigation';
import { AlertTriangle, ArrowLeft, FileText, Loader2, RefreshCw } from 'lucide-react';
import { Button } from '@/components/Button';
import { Card } from '@/components/Card';
import { useAuthStore } from '@/lib/stores/authStore';
import {
  fetchConversation,
  HistoryError,
  type ConversationDetail,
  type HistorySubject,
} from '@/lib/api/history';
import { formatRelativeTime } from '@/lib/intl/relativeTime';

/*
 * HistoryDetailClient — client subcomponent of the
 * /history/{conversation_id} page (s19).
 *
 * Fetches the conversation + its messages from
 * GET /api/chat/history/{id} (the apiClient interceptor adds the
 * JWT bearer). 4 UI states: loading, not_found (404), error, success.
 *
 * The not_found state shows the same card as the error state's
 * 404 branch — the backend's "404 for unknown AND cross-tenant"
 * invariant (ADR 015 § Decision 3) means a cross-tenant attacker
 * cannot distinguish the two.
 *
 * Message bubbles: user = right-aligned `bg-surface-subtle`,
 * assistant = left-aligned with a `border-l-4 border-primary`
 * (per the design). Sources are pills (cf. design-system gap #1
 * — a <Badge> shared component is reserved for s22; the pill
 * classes are inline here, not a new shared component).
 *
 * All copy is i18n-ised via useTranslations('history'). No hardcoded
 * strings.
 */
type State =
  | { kind: 'loading' }
  | { kind: 'not_found' }
  | { kind: 'error'; code: 'network' | 'http_401' | 'http_403' | 'http_5xx' | 'unknown' }
  | { kind: 'success'; data: ConversationDetail };

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

export function HistoryDetailClient({ conversationId }: { conversationId: string }) {
  const t = useTranslations('history');
  const tChat = useTranslations('chat');
  const locale = useLocale();
  const router = useRouter();

  const accessToken = useAuthStore((s) => s.accessToken);
  const hydrated = useAuthStore((s) => s.hydrated);

  const [state, setState] = useState<State | null>(null);

  // The setState calls are inside ``.then`` / ``.catch``
  // promise-chain callbacks, which the
  // react-hooks/set-state-in-effect rule does not track (it
  // analyses the synchronous call chain only).
  useEffect(() => {
    if (!hydrated) return;
    if (!accessToken) return;
    fetchConversation(conversationId)
      .then((data) => {
        setState({ kind: 'success', data });
      })
      .catch((err: unknown) => {
        if (err instanceof HistoryError) {
          if (err.code === 'http_404') {
            setState({ kind: 'not_found' });
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
  }, [hydrated, accessToken, conversationId]);

  function refetch() {
    fetchConversation(conversationId)
      .then((data) => setState({ kind: 'success', data }))
      .catch((err: unknown) => {
        if (err instanceof HistoryError) {
          if (err.code === 'http_404') {
            setState({ kind: 'not_found' });
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
      <div>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => router.push(`/${locale}/history`)}
          leftIcon={<ArrowLeft size={20} aria-hidden="true" />}
          aria-label={t('back')}
          data-testid="history-back"
        >
          {t('back')}
        </Button>
      </div>

      {state === null ? (
        <Card role="status" aria-live="polite" className="flex items-center justify-center gap-2">
          <Loader2 size={20} className="animate-spin text-text-secondary" aria-hidden="true" />
          <span className="text-sm text-text-secondary">{t('loading')}</span>
        </Card>
      ) : null}

      {state?.kind === 'not_found' ? (
        <Card role="alert" className="bg-error/10 border border-error/30">
          <div className="flex items-start gap-3">
            <AlertTriangle size={24} className="text-error shrink-0" aria-hidden="true" />
            <div className="flex-1 flex flex-col gap-1">
              <p className="text-base text-text-primary font-medium">{t('error404')}</p>
              <p className="text-sm text-text-secondary">{t('notFound')}</p>
            </div>
          </div>
        </Card>
      ) : null}

      {state?.kind === 'error' ? (
        <ErrorState code={state.code} onRetry={refetch} />
      ) : null}

      {state?.kind === 'success' ? (
        <SuccessState data={state.data} locale={locale} />
      ) : null}
    </div>
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

function SuccessState({ data, locale }: { data: ConversationDetail; locale: string }) {
  const t = useTranslations('history');
  const tChat = useTranslations('chat');
  return (
    <>
      <Card
        data-testid="history-detail-header"
        className="flex flex-col gap-2"
        aria-labelledby="history-detail-title"
      >
        <div className="flex items-center gap-2">
          <span
            className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${SUBJECT_PILL[data.subject]}`}
          >
            {tChat(SUBJECT_LABELS[data.subject])}
          </span>
        </div>
        <h1
          id="history-detail-title"
          className="text-lg md:text-xl font-medium text-text-primary"
        >
          {data.first_question}
        </h1>
        <div className="flex flex-wrap items-center gap-2 text-xs text-text-secondary">
          <span>{t('metaCount', { count: data.message_count })}</span>
          <span aria-hidden="true">·</span>
          <time dateTime={data.last_activity_at}>
            {formatRelativeTime(data.last_activity_at, locale)}
          </time>
        </div>
      </Card>

      <ol className="flex flex-col gap-3" data-testid="history-messages">
        {data.messages.map((m) => (
          <li
            key={m.id}
            data-testid={`history-message-${m.role}`}
            className={
              m.role === 'user'
                ? 'flex justify-end'
                : 'flex justify-start'
            }
          >
            <div
              className={
                m.role === 'user'
                  ? 'max-w-2xl px-4 py-3 rounded-md bg-surface-subtle text-text-primary'
                  : 'max-w-2xl px-4 py-3 rounded-md bg-surface border-l-4 border-primary text-text-primary'
              }
            >
              <div className="text-xs text-text-secondary mb-1">
                {m.role === 'user'
                  ? t('roleYou')
                  : t('roleAssistant', {
                      subject: tChat(SUBJECT_LABELS[data.subject]),
                    })}
              </div>
              <p className="text-base whitespace-pre-wrap">{m.content}</p>
              {m.sources && m.sources.length > 0 ? (
                <div
                  className="mt-2 flex flex-col gap-1"
                  aria-label={t('sourcesLabel')}
                >
                  <span className="text-xs text-text-secondary">
                    {t('sourcesLabel')}
                  </span>
                  <ul className="flex flex-wrap gap-1">
                    {m.sources.map((s, i) => (
                      <li key={i}>
                        <a
                          href="#"
                          className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs text-text-secondary bg-surface-subtle hover:bg-surface focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/30"
                          aria-label={`${s.filename}:${s.chunk_index}`}
                        >
                          <FileText size={12} aria-hidden="true" />
                          <span>
                            {s.filename}:{s.chunk_index}
                          </span>
                        </a>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </div>
          </li>
        ))}
      </ol>
    </>
  );
}
