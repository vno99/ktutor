import { describe, it, expect, beforeEach, vi } from 'vitest';
import { AxiosError, type AxiosResponse, type InternalAxiosRequestConfig } from 'axios';
import {
  fetchHistory,
  fetchConversation,
  HistoryError,
  type HistoryListResponse,
  type ConversationDetail,
} from './history';

/*
 * Unit tests for the history API helpers (s19).
 *
 * The helpers are thin wrappers around ``apiClient``. We mock the
 * client via ``vi.mock('@/lib/api')`` so the test does not depend on
 * the real interceptor / network. The two surfaces under test:
 *
 *  - happy path : ``fetchHistory({...})`` returns the parsed body
 *    and ``fetchConversation(id)`` returns the parsed body
 *  - error path : an ``AxiosError`` is mapped to ``HistoryError``
 *    with the right ``code`` for the four interesting statuses
 *    (401 / 403 / 404 / 5xx) and the network case (no response)
 *
 * The page-level error handling is a thin switch on ``code``; the
 * contract between helper and page is the ``HistoryError.code`` set.
 */

const LIST_ITEM = {
  id: '11111111-1111-1111-1111-111111111111',
  subject: 'maths' as const,
  first_question: 'Qu\'est-ce qu\'une dérivée ?',
  last_activity_at: '2026-09-04T08:22:00Z',
  message_count: 4,
};

const HISTORY_PAYLOAD: HistoryListResponse = {
  items: [LIST_ITEM],
  total: 1,
  limit: 20,
  offset: 0,
};

const DETAIL_PAYLOAD: ConversationDetail = {
  ...LIST_ITEM,
  messages: [
    {
      id: 'm1',
      role: 'user',
      content: 'Qu\'est-ce qu\'une dérivée ?',
      sources: null,
      created_at: '2026-09-04T08:22:00Z',
    },
    {
      id: 'm2',
      role: 'assistant',
      content: 'Une dérivée mesure la variation instantanée…',
      sources: [{ filename: 'cours.pdf', chunk_index: 3 }],
      created_at: '2026-09-04T08:22:01Z',
    },
  ],
};

const mockGet = vi.fn();

vi.mock('@/lib/api', () => ({
  apiClient: { get: (...args: unknown[]) => mockGet(...args) },
}));

function makeAxiosError(status: number | null): AxiosError {
  const config: InternalAxiosRequestConfig = {
    url: '/api/chat/history',
    method: 'get',
    headers: {} as never,
  } as InternalAxiosRequestConfig;
  if (status === null) {
    return new AxiosError('Network Error', 'ECONNABORTED', config);
  }
  const response = {
    status,
    data: {},
    statusText: 'Error',
    headers: {},
    config,
  } as AxiosResponse;
  return new AxiosError(
    `Request failed with status ${status}`,
    String(status),
    config,
    undefined,
    response,
  );
}

beforeEach(() => {
  mockGet.mockReset();
});

describe('fetchHistory', () => {
  it('returns the parsed body on 200', async () => {
    mockGet.mockResolvedValueOnce({ data: HISTORY_PAYLOAD });
    const out = await fetchHistory({ limit: 10, offset: 0 });
    expect(out).toEqual(HISTORY_PAYLOAD);
    expect(mockGet).toHaveBeenCalledWith(
      '/api/chat/history',
      expect.objectContaining({
        params: expect.objectContaining({ limit: 10, offset: 0 }),
      }),
    );
  });

  it('forwards the subject filter when set', async () => {
    mockGet.mockResolvedValueOnce({ data: HISTORY_PAYLOAD });
    await fetchHistory({ subject: 'maths' });
    expect(mockGet).toHaveBeenCalledWith(
      '/api/chat/history',
      expect.objectContaining({
        params: expect.objectContaining({ subject: 'maths' }),
      }),
    );
  });

  it('omits the subject param when not provided (None)', async () => {
    mockGet.mockResolvedValueOnce({ data: HISTORY_PAYLOAD });
    await fetchHistory();
    const call = mockGet.mock.calls[0];
    expect(call).toBeDefined();
    const params = (call![1] as { params: Record<string, unknown> }).params;
    expect(params.subject).toBeUndefined();
  });

  it('maps a 401 to HistoryError(http_401)', async () => {
    mockGet.mockRejectedValueOnce(makeAxiosError(401));
    await expect(fetchHistory()).rejects.toMatchObject({
      name: 'HistoryError',
      code: 'http_401',
      status: 401,
    });
  });

  it('maps a 404 to HistoryError(http_404)', async () => {
    mockGet.mockRejectedValueOnce(makeAxiosError(404));
    await expect(fetchHistory()).rejects.toMatchObject({
      code: 'http_404',
      status: 404,
    });
  });

  it('maps a 500 to HistoryError(http_5xx)', async () => {
    mockGet.mockRejectedValueOnce(makeAxiosError(500));
    await expect(fetchHistory()).rejects.toMatchObject({
      code: 'http_5xx',
      status: 500,
    });
  });

  it('maps a network failure to HistoryError(network)', async () => {
    mockGet.mockRejectedValueOnce(makeAxiosError(null));
    await expect(fetchHistory()).rejects.toMatchObject({
      code: 'network',
    });
  });
});

describe('fetchConversation', () => {
  it('returns the parsed body on 200', async () => {
    mockGet.mockResolvedValueOnce({ data: DETAIL_PAYLOAD });
    const out = await fetchConversation(DETAIL_PAYLOAD.id);
    expect(out).toEqual(DETAIL_PAYLOAD);
  });

  it('encodes the id in the URL', async () => {
    mockGet.mockResolvedValueOnce({ data: DETAIL_PAYLOAD });
    await fetchConversation('some/odd id?with&special=chars');
    const call = mockGet.mock.calls[0];
    expect(call).toBeDefined();
    const url = call![0] as string;
    expect(url).toBe('/api/chat/history/some%2Fodd%20id%3Fwith%26special%3Dchars');
  });

  it('maps a 404 to HistoryError(http_404)', async () => {
    mockGet.mockRejectedValueOnce(makeAxiosError(404));
    await expect(fetchConversation('00000000-0000-0000-0000-000000000000')).rejects.toBeInstanceOf(
      HistoryError,
    );
  });
});
