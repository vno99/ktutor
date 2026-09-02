'use client';

import { useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Select } from '@/components/Select';
import { Textarea } from '@/components/Textarea';
import { Button } from '@/components/Button';
import { Label } from '@/components/Label';
import { StreamingMessage } from '@/components/StreamingMessage';
import { useAuthStore, isValidPseudo } from '@/lib/stores/authStore';
import { useChatStore } from '@/lib/stores/chatStore';
import type { ChatInput } from '@/lib/stores/chatStore';

/*
 * ChatClient — client subcomponent of the /chat page (s11b).
 *
 * Stream-driven conversation with the agent. Consumes both the
 * authStore (cookie-backed pseudo) and the chatStore (SSE state).
 * The server entry (page.tsx) renders <ChatClient />; this is the
 * standard next-intl pattern for client components that need
 * useTranslations + Zustand.
 *
 * All copy is i18n-ised via useTranslations('chat') and
 * useTranslations('errors'). The StreamingMessage receives the
 * translator functions as props (see the component's note).
 *
 * cf. docs/research/s11b-frontend-chat.md § 3.1.
 */
const MAX_QUESTION_LENGTH = 2000;

export function ChatClient() {
  const t = useTranslations('chat');
  const tErrors = useTranslations('errors');

  const pseudo = useAuthStore((s) => s.pseudo);
  const hydrated = useAuthStore((s) => s.hydrated);
  const hydrateAuth = useAuthStore((s) => s.hydrate);

  const messages = useChatStore((s) => s.messages);
  const isStreaming = useChatStore((s) => s.isStreaming);
  const send = useChatStore((s) => s.send);
  const retry = useChatStore((s) => s.retry);
  const chatHydrate = useChatStore((s) => s.hydrate);
  const chatHydrated = useChatStore((s) => s.hydrated);

  const [subject, setSubject] = useState<'' | 'maths' | 'francais'>('');
  const [question, setQuestion] = useState('');

  useEffect(() => {
    if (!hydrated) hydrateAuth();
    if (!chatHydrated) chatHydrate();
  }, [hydrated, hydrateAuth, chatHydrated, chatHydrate]);

  const pseudoValid = isValidPseudo(pseudo);
  const canSend =
    pseudoValid && subject !== '' && question.trim().length > 0 && !isStreaming;

  const remaining = MAX_QUESTION_LENGTH - question.length;
  const lowRemaining = remaining < 100;

  function handleSend() {
    if (!canSend) return;
    const input: ChatInput = {
      subject: subject as 'maths' | 'francais',
      question: question.trim(),
    };
    setQuestion('');
    void send(input);
  }

  const lastAssistant = messages[messages.length - 1];
  const showErrorCard =
    lastAssistant?.role === 'assistant' && lastAssistant.error != null;
  const showSources =
    !showErrorCard &&
    lastAssistant?.role === 'assistant' &&
    Array.isArray(lastAssistant.sources) &&
    (lastAssistant.sources?.length ?? 0) > 0;
  const showEmpty = messages.length === 0 && !isStreaming;

  return (
    <div className="max-w-3xl mx-auto px-4 md:px-6 py-4 md:py-6 flex flex-col gap-4">
      <h1 className="text-2xl md:text-3xl font-semibold tracking-tight text-text-primary">
        {t('title')}
      </h1>

      <div className="flex flex-col gap-2">
        <Label htmlFor="chat-subject">{t('subjectLabel')}</Label>
        <Select
          id="chat-subject"
          options={[
            { value: 'maths', label: t('subjectMaths') },
            { value: 'francais', label: t('subjectFrancais') },
          ]}
          value={subject}
          onChange={(event) =>
            setSubject(event.target.value as '' | 'maths' | 'francais')
          }
          aria-describedby="chat-subject-help"
        />
        <span id="chat-subject-help" className="sr-only">
          {t('subjectLabel')}
        </span>
      </div>

      <div className="flex flex-col gap-2">
        <Label htmlFor="chat-question">{t('questionLabel')}</Label>
        <Textarea
          id="chat-question"
          value={question}
          onChange={(event) => {
            const next = event.target.value.slice(0, MAX_QUESTION_LENGTH);
            setQuestion(next);
          }}
          placeholder={t('questionPlaceholder')}
          maxLength={MAX_QUESTION_LENGTH}
          rows={4}
          aria-describedby="chat-question-count"
        />
        <div
          id="chat-question-count"
          className="text-xs text-text-secondary"
          aria-live={lowRemaining ? 'polite' : 'off'}
        >
          {t('charCountRemaining', { n: remaining })}
        </div>
      </div>

      {!pseudoValid ? (
        <p className="text-sm text-warning" role="status">
          {t('pseudoMissing')}
        </p>
      ) : null}

      <div>
        <Button
          variant="primary"
          size="md"
          onClick={handleSend}
          disabled={!canSend}
          aria-disabled={!canSend}
          tabIndex={canSend ? 0 : -1}
          type="button"
        >
          {t('send')}
        </Button>
      </div>

      <StreamingMessage
        streamingStatus={
          isStreaming
            ? 'streaming'
            : showErrorCard
              ? 'error'
              : messages.length > 0
                ? 'done'
                : 'idle'
        }
        isStreaming={isStreaming}
        hasContent={messages.length > 0}
        sources={showSources ? (lastAssistant?.sources ?? null) : null}
        error={showErrorCard ? (lastAssistant?.error ?? null) : null}
        t={t}
        tErrors={tErrors}
        onRetry={retry}
      >
        {messages.map((message, index) => (
          <div key={index} className="mb-3" data-role={message.role}>
            {message.role === 'user' ? (
              <p className="text-sm text-text-secondary">
                <span className="font-medium">{pseudo || '?'}:</span>{' '}
                {message.content}
              </p>
            ) : message.content.length > 0 ? (
              <p className="text-base text-text-primary whitespace-pre-wrap">
                {message.content}
              </p>
            ) : null}
          </div>
        ))}
        {showEmpty ? (
          <div className="text-text-secondary text-sm">
            <p>{t('emptyState')}</p>
            <p className="mt-2 font-medium">{t('examplesTitle')}</p>
            <ul className="list-disc pl-5 mt-1">
              <li>{t('exampleMaths')}</li>
              <li>{t('exampleFrancais')}</li>
            </ul>
          </div>
        ) : null}
      </StreamingMessage>
    </div>
  );
}
