import { create } from 'zustand';
import { useAuthStore, isValidPseudo } from '@/lib/stores/authStore';
import {
  parseSSEChunk,
  type ChatStreamErrorCode,
  type SourceCitation,
} from '@/lib/api/chat';

/*
 * chatStore — owns the chat conversation state for s11b.
 *
 * The stream is consumed with fetch().body.getReader() (NOT EventSource,
 * NOT apiClient/axios — both buffer). The contract consumed here is
 * frozen in s09 and verified line by line in the research:
 *  - backend/app/api/chat/router.py:64-134
 *  - backend/app/api/chat/sse.py:21-30   (format_sse)
 *  - backend/app/api/chat/schemas.py:34-77 (body + StreamErrorEvent)
 *
 * Three event shapes the backend emits (parsed by parseSSEChunk):
 *  - {token: "..."}    → append to the latest assistant message
 *  - {done, sources}   → mark the assistant message complete + attach sources
 *  - {error, code}     → attach the error to the assistant message and stop
 *
 * Multi-tenancy: the tenant key is derived server-side from the JWT
 * (s15-restrictions-rbac, ADR 005). The `pseudo` is read from
 * useAuthStore.getState().pseudo (cookie-backed, ADR 011) only for
 * the local `isValidPseudo` UX guard — it is NOT sent in the
 * request body. The client regex ^[a-zA-Z0-9_]{3,32}$ (3-32 chars)
 * is preserved as a local-only UX guard.
 *
 * History is NOT persisted (s19 owns the persistent history). State lives
 * only in this store and is lost on refresh. Messages accumulate in memory
 * for the duration of the tab.
 *
 * StrictMode safety: send() is idempotent — a second call while a stream is
 * in flight returns immediately. This prevents the double-invocation of
 * React 19 StrictMode from opening two SSE connections at once.
 */

export type ChatRole = 'user' | 'assistant';

export type ChatStreamError = {
  code: ChatStreamErrorCode;
  message: string;
};

export type ChatMessage = {
  role: ChatRole;
  content: string;
  sources?: SourceCitation[] | null;
  error?: ChatStreamError | null;
};

export type ChatInput = {
  subject: 'maths' | 'francais';
  question: string;
};

export interface ChatState {
  messages: ChatMessage[];
  isStreaming: boolean;
  lastQuestion: string | null;
  lastInput: ChatInput | null;
  hydrated: boolean;
  hydrate: () => void;
  send: (input: ChatInput) => Promise<void>;
  retry: () => Promise<void>;
  reset: () => void;
}

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

export const useChatStore = create<ChatState>((set, get) => ({
  messages: [],
  isStreaming: false,
  lastQuestion: null,
  lastInput: null,
  hydrated: false,

  // chatStore has nothing client-only to hydrate; the flag exists so the
  // page can wait for the first paint before letting the user submit.
  hydrate: () => {
    set({ hydrated: true });
  },

  send: async (input) => {
    // StrictMode guard — never open a second stream while one is active.
    if (get().isStreaming) return;

    const pseudo = useAuthStore.getState().pseudo;
    if (!isValidPseudo(pseudo)) {
      // Local guard: the <Header> already disables the button, but a
      // keyboard submit (Enter) could bypass the disabled state. The
      // assistant message carries the error so the page can show the
      // i18n label and the retry button.
      const assistant: ChatMessage = {
        role: 'assistant',
        content: '',
        sources: null,
        error: { code: 'invalid_pseudo', message: '' },
      };
      set((s) => ({
        messages: [
          ...s.messages,
          { role: 'user', content: input.question },
          assistant,
        ],
        isStreaming: false,
        lastQuestion: input.question,
        lastInput: input,
      }));
      return;
    }

    // Push the user message + an empty assistant message up front so the
    // UI can render the user turn before the first token arrives.
    const baseMessages: ChatMessage[] = [
      ...get().messages,
      { role: 'user', content: input.question },
      { role: 'assistant', content: '', sources: null, error: null },
    ];
    set({
      messages: baseMessages,
      isStreaming: true,
      lastQuestion: input.question,
      lastInput: input,
    });

    let response: Response;
    try {
      response = await fetch(`${API_BASE_URL}/api/chat/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Accept: 'text/event-stream',
        },
        body: JSON.stringify({
          subject: input.subject,
          question: input.question,
        }),
      });
    } catch {
      // Network refused: connection lost before any HTTP response.
      // Central-bet mitigation: check response.ok BEFORE getReader()
      // (we never reach the reader here, but the marker is the same).
      setErrorOnLast('network');
      return;
    }

    if (!response.ok || !response.body) {
      setErrorOnLast('network');
      return;
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder('utf-8');
    let buffer = '';

    try {
      // Outer loop: keep reading until the stream closes.
      // The buffer accumulates partial frames across reads; we split on
      // \n\n and feed each complete frame to the pure parser.
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        let splitAt = buffer.indexOf('\n\n');
        while (splitAt !== -1) {
          const frame = buffer.slice(0, splitAt);
          buffer = buffer.slice(splitAt + 2);
          handleFrames(frame);
          splitAt = buffer.indexOf('\n\n');
        }
      }
      // Flush any trailing frame that did not end with \n\n.
      if (buffer.trim().length > 0) {
        handleFrames(buffer);
      }
    } catch {
      // reader.read() threw — the connection was lost mid-stream.
      setErrorOnLast('lost');
      return;
    }

    set({ isStreaming: false });

    function handleFrames(text: string) {
      for (const ev of parseSSEChunk(text)) {
        if (ev.type === 'token') {
          if (ev.content.length === 0) continue;
          set((s) => {
            const next = s.messages.slice();
            const last = next[next.length - 1];
            if (!last || last.role !== 'assistant') return s;
            next[next.length - 1] = {
              ...last,
              content: last.content + ev.content,
            };
            return { messages: next };
          });
        } else if (ev.type === 'done') {
          set((s) => {
            const next = s.messages.slice();
            const last = next[next.length - 1];
            if (!last || last.role !== 'assistant') return s;
            next[next.length - 1] = { ...last, sources: ev.sources };
            return { messages: next };
          });
        } else {
          // error
          set((s) => {
            const next = s.messages.slice();
            const last = next[next.length - 1];
            if (!last || last.role !== 'assistant') return s;
            next[next.length - 1] = {
              ...last,
              error: { code: ev.code, message: ev.error },
            };
            return { messages: next };
          });
          return;
        }
      }
    }

    function setErrorOnLast(code: 'lost' | 'network') {
      set((s) => {
        const next = s.messages.slice();
        const last = next[next.length - 1];
        if (!last || last.role !== 'assistant') {
          return { isStreaming: false };
        }
        next[next.length - 1] = {
          ...last,
          error: { code, message: '' },
        };
        return { messages: next, isStreaming: false };
      });
    }
  },

  retry: async () => {
    const last = get().lastInput;
    if (!last) return;
    await get().send(last);
  },

  reset: () => {
    set({
      messages: [],
      isStreaming: false,
      lastQuestion: null,
      lastInput: null,
    });
  },
}));
