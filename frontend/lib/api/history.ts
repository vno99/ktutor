/*
 * history.ts — pure types + thin fetch helpers for the conversation
 * history endpoints (s19, ADR 015).
 *
 * The two read-only endpoints:
 *  - GET /api/chat/history           — paginated list, newest first
 *  - GET /api/chat/history/{id}      — conversation + its messages
 *
 * The apiClient interceptor adds the JWT bearer (s15); the ``pseudo``
 * is NOT in the body or the URL. The helpers return typed objects
 * directly — the call sites do not need to re-validate the shape.
 *
 * ``HistoryError`` mirrors the chat-side error shape so a page can
 * branch on ``code``. The four codes the backend can surface:
 *  - ``network``     : fetch failed (no response)
 *  - ``http_401``    : JWT missing/expired (apiClient already retried
 *                      and bounced; the page redirects to /login)
 *  - ``http_403``    : RBAC blocked (defence-in-depth, should not
 *                      fire because the backend returns 404 for
 *                      cross-tenant ids — ADR 015 § Decision 3)
 *  - ``http_404``    : unknown or cross-tenant id (same body for
 *                      both — the page shows a "not found" state)
 *  - ``http_5xx``    : server error (page shows retry)
 *  - ``unknown``     : any other shape (defence in depth)
 */
import { AxiosError } from 'axios';
import { apiClient } from '@/lib/api';
import type { SourceCitation } from './chat';

export type HistorySubject = 'maths' | 'francais';

export interface ConversationListItem {
  id: string;
  subject: HistorySubject;
  first_question: string;
  last_activity_at: string;
  message_count: number;
}

export interface MessageItem {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  sources: SourceCitation[] | null;
  created_at: string;
}

export interface HistoryListResponse {
  items: ConversationListItem[];
  total: number;
  limit: number;
  offset: number;
}

export type ConversationDetail = ConversationListItem & {
  messages: MessageItem[];
};

export type HistoryErrorCode =
  | 'network'
  | 'http_401'
  | 'http_403'
  | 'http_404'
  | 'http_5xx'
  | 'unknown';

export class HistoryError extends Error {
  code: HistoryErrorCode;
  status?: number;
  constructor(message: string, code: HistoryErrorCode, status?: number) {
    super(message);
    this.code = code;
    this.status = status;
    this.name = 'HistoryError';
  }
}

export interface FetchHistoryArgs {
  limit?: number;
  offset?: number;
  subject?: HistorySubject | null;
}

export async function fetchHistory(
  args: FetchHistoryArgs = {},
): Promise<HistoryListResponse> {
  try {
    const resp = await apiClient.get<HistoryListResponse>('/api/chat/history', {
      params: {
        limit: args.limit,
        offset: args.offset,
        subject: args.subject ?? undefined,
      },
    });
    return resp.data;
  } catch (err) {
    throw toHistoryError(err);
  }
}

export async function fetchConversation(
  id: string,
): Promise<ConversationDetail> {
  try {
    const resp = await apiClient.get<ConversationDetail>(
      `/api/chat/history/${encodeURIComponent(id)}`,
    );
    return resp.data;
  } catch (err) {
    throw toHistoryError(err);
  }
}

function toHistoryError(err: unknown): HistoryError {
  if (err instanceof AxiosError) {
    if (!err.response) {
      return new HistoryError(
        err.message || 'Network error',
        'network',
      );
    }
    const status = err.response.status;
    if (status === 401) return new HistoryError('Unauthorized', 'http_401', status);
    if (status === 403) return new HistoryError('Forbidden', 'http_403', status);
    if (status === 404) return new HistoryError('Not found', 'http_404', status);
    if (status >= 500) return new HistoryError('Server error', 'http_5xx', status);
    return new HistoryError(`HTTP ${status}`, 'unknown', status);
  }
  if (err instanceof Error) {
    return new HistoryError(err.message, 'unknown');
  }
  return new HistoryError('Unknown error', 'unknown');
}
