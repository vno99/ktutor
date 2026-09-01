'use client';

import type { ReactNode } from 'react';

/*
 * StreamingMessage — SKELETON (SSE consumption arrives in s11b).
 *
 * For s11a, this component renders a polite live region with the
 * standard typing indicator (3 pulsing dots) while isStreaming is true
 * and no content has been received yet. The actual fetch + ReadableStream
 * wiring is added in s11b.
 *
 * TODO s11b: connect to /api/chat/stream (fetch + ReadableStream, not
 * EventSource — see ADR 006 and recherche Piège #2).
 */
export interface StreamingMessageProps {
  isStreaming: boolean;
  hasContent: boolean;
  children?: ReactNode;
}

export function StreamingMessage({
  isStreaming,
  hasContent,
  children,
}: StreamingMessageProps) {
  const showTyping = isStreaming && !hasContent;
  return (
    <div
      role="log"
      aria-live="polite"
      aria-busy={isStreaming}
      className="min-h-12"
    >
      {children}
      {showTyping ? <TypingIndicator /> : null}
    </div>
  );
}

function TypingIndicator() {
  return (
    <div
      aria-hidden="true"
      className="flex items-center gap-1 text-text-secondary"
    >
      <span className="h-2 w-2 rounded-full bg-text-tertiary animate-pulse" />
      <span
        className="h-2 w-2 rounded-full bg-text-tertiary animate-pulse"
        style={{ animationDelay: '150ms' }}
      />
      <span
        className="h-2 w-2 rounded-full bg-text-tertiary animate-pulse"
        style={{ animationDelay: '300ms' }}
      />
    </div>
  );
}
