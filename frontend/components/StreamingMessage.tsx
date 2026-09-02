'use client';

import type { ReactNode } from 'react';
import { Card } from './Card';
import { Button } from './Button';

/*
 * StreamingMessage — the s11a skeleton evolved.
 *
 * s11a shipped a 3-prop skeleton (isStreaming, hasContent, children)
 * with the typing indicator wired to isStreaming && !hasContent.
 * s11b extends it with three additional, optional props:
 *
 *  - error?: ChatStreamError | null
 *      When set, the component renders a Card with the i18n-mapped
 *      message and a Retry button. The streaming indicator is hidden.
 *
 *  - sources?: SourceCitation[] | null
 *      When set and non-empty, a "Sources : <filenames>" line is
 *      rendered after the children. The line truncates to 5 names
 *      and appends "… and N more" when there are more.
 *
 *  - streamingStatus?: 'idle' | 'streaming' | 'done' | 'error'
 *      The "new" prop that supersedes isStreaming/hasContent for new
 *      callers. The old props are kept for backward-compat with the
 *      s11a skeleton and now optional.
 *
 * The i18n is injected as `t` and `tErrors` props (functions) rather
 * than called via useTranslations inside the component, so the
 * component can be unit-tested without a next-intl provider. The
 * page wires these to `useTranslations('chat')` and
 * `useTranslations('errors')`.
 *
 * A11y: the wrapper remains role="log" aria-live="polite" so screen
 * readers announce new content. aria-busy is derived from the
 * streaming status (or the legacy isStreaming prop).
 *
 * cf. docs/research/s11b-frontend-chat.md § 3.1.
 */

export type SourceCitation = { filename: string; chunk_index: number };
export type ChatStreamErrorCode =
  | 'cross_tenant'
  | 'no_subject'
  | 'invalid_pseudo'
  | 'unknown'
  | 'network'
  | 'lost';
export type ChatStreamError = { code: ChatStreamErrorCode; message: string };
export type StreamingStatus = 'idle' | 'streaming' | 'done' | 'error';

export type Translator = (
  key: string,
  values?: Record<string, string | number>,
) => string;

export interface StreamingMessageProps {
  // Legacy (s11a) — kept optional for backward-compat.
  isStreaming?: boolean;
  hasContent?: boolean;
  children?: ReactNode;

  // New (s11b) — the chatStore-driven shape.
  error?: ChatStreamError | null;
  sources?: SourceCitation[] | null;
  streamingStatus?: StreamingStatus;

  // i18n — injected by the page so the component stays testable.
  t?: Translator;
  tErrors?: Translator;

  // Actions — when error is set, the Retry button calls this.
  onRetry?: () => void;
}

const SOURCES_DISPLAY_LIMIT = 5;

export function StreamingMessage({
  isStreaming = false,
  hasContent = false,
  children,
  error,
  sources,
  streamingStatus,
  t = (k) => k,
  tErrors = (k) => k,
  onRetry,
}: StreamingMessageProps) {
  const status: StreamingStatus =
    streamingStatus ??
    (error ? 'error' : isStreaming ? 'streaming' : 'idle');

  const showTyping = status === 'streaming' && !hasContent;
  const showError = error != null;
  const showSources =
    !showError && Array.isArray(sources) && sources.length > 0;

  return (
    <div
      role="log"
      aria-live="polite"
      aria-busy={status === 'streaming'}
      className="min-h-32 border border-border rounded-md p-4 bg-surface"
    >
      {children}
      {showTyping ? <TypingIndicator /> : null}
      {showError ? (
        <Card
          role="alert"
          className="mt-3 bg-error/10 border border-error/30"
        >
          <div className="flex items-start gap-3">
            <span
              aria-hidden="true"
              className="text-error text-2xl leading-none"
            >
              !
            </span>
            <div className="flex-1">
              <p className="text-sm text-text-primary">
                {tErrors(error.code)}
              </p>
              <p className="mt-1 text-xs text-text-tertiary font-mono">
                {error.code}
              </p>
              {onRetry ? (
                <div className="mt-3">
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={onRetry}
                    type="button"
                  >
                    {t('retry')}
                  </Button>
                </div>
              ) : null}
            </div>
          </div>
        </Card>
      ) : null}
      {showSources ? <SourcesLine sources={sources!} t={t} /> : null}
    </div>
  );
}

function SourcesLine({
  sources,
  t,
}: {
  sources: SourceCitation[];
  t: Translator;
}) {
  const visible = sources.slice(0, SOURCES_DISPLAY_LIMIT);
  const remaining = sources.length - visible.length;
  const filenames = visible.map((s) => s.filename).join(' · ');
  return (
    <p className="text-xs text-text-secondary mt-3">
      <span className="font-medium">{t('sourcesLabel')}</span> {filenames}
      {remaining > 0 ? <> {t('sourcesMore', { n: remaining })}</> : null}
    </p>
  );
}

function TypingIndicator() {
  return (
    <div
      aria-hidden="true"
      className="flex items-center gap-1 text-text-secondary motion-reduce:animate-none"
    >
      <span className="h-2 w-2 rounded-full bg-text-tertiary animate-pulse motion-reduce:animate-none" />
      <span
        className="h-2 w-2 rounded-full bg-text-tertiary animate-pulse motion-reduce:animate-none"
        style={{ animationDelay: '150ms' }}
      />
      <span
        className="h-2 w-2 rounded-full bg-text-tertiary animate-pulse motion-reduce:animate-none"
        style={{ animationDelay: '300ms' }}
      />
    </div>
  );
}
