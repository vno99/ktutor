import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';
import { useChatStore } from './chatStore';
import { useAuthStore } from './authStore';

/*
 * Unit tests for the chatStore (s11b).
 *
 * Scope: the pure state transitions of the store. We do NOT test the
 * fetch path here — it requires real network, and the AC11 e2e
 * suite already covers it. We DO test the local guard rails that
 * keep the store from misbehaving in the browser:
 *
 *  - isStreaming gate (StrictMode safety, idempotent re-entry)
 *  - invalid pseudo → assistant message with the right error code
 *  - retry() is a no-op when lastInput is null
 *  - reset() clears messages and isStreaming
 *
 * authStore is a Zustand singleton just like chatStore, so we set
 * the pseudo via its setter and reset it after each test.
 */

function resetAuth() {
  // Force a clean pseudo so the invalid-pseudo test is deterministic.
  useAuthStore.setState({ pseudo: '', hydrated: true });
}

function setAuthPseudo(value: string) {
  useAuthStore.setState({ pseudo: value, hydrated: true });
}

describe('chatStore (state transitions only)', () => {
  beforeEach(() => {
    useChatStore.getState().reset();
    resetAuth();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('starts empty and not streaming', () => {
    const s = useChatStore.getState();
    expect(s.messages).toEqual([]);
    expect(s.isStreaming).toBe(false);
    expect(s.lastInput).toBeNull();
  });

  it('attaches invalid_pseudo error to the assistant message when the pseudo is missing', async () => {
    // No pseudo set in the authStore.
    await useChatStore.getState().send({
      subject: 'maths',
      question: 'Qu\'est-ce qu\'une dérivée ?',
    });

    const s = useChatStore.getState();
    expect(s.messages).toHaveLength(2);
    expect(s.messages[0]).toMatchObject({
      role: 'user',
      content: 'Qu\'est-ce qu\'une dérivée ?',
    });
    expect(s.messages[1]).toMatchObject({
      role: 'assistant',
      content: '',
      error: { code: 'invalid_pseudo', message: '' },
    });
    expect(s.isStreaming).toBe(false);
    expect(s.lastInput).toEqual({
      subject: 'maths',
      question: 'Qu\'est-ce qu\'une dérivée ?',
    });
  });

  it('retry() is a no-op when no lastInput was recorded', async () => {
    // Never call send() — lastInput is null.
    await useChatStore.getState().retry();
    const s = useChatStore.getState();
    expect(s.messages).toEqual([]);
    expect(s.isStreaming).toBe(false);
  });

  it('reset() clears messages and isStreaming', async () => {
    setAuthPseudo('ali_baba');
    // Stub fetch to a never-resolving promise so we can set isStreaming
    // and then test reset clears it.
    vi.stubGlobal(
      'fetch',
      vi.fn(() => new Promise<Response>(() => undefined)),
    );
    const sendPromise = useChatStore.getState().send({
      subject: 'maths',
      question: 'Question',
    });
    // Yield a microtask so the store transitions into isStreaming=true.
    await Promise.resolve();
    await Promise.resolve();
    expect(useChatStore.getState().isStreaming).toBe(true);

    useChatStore.getState().reset();
    const s = useChatStore.getState();
    expect(s.messages).toEqual([]);
    expect(s.isStreaming).toBe(false);
    expect(s.lastInput).toBeNull();

    // Clean up the pending promise so the test process exits.
    sendPromise.catch(() => undefined);
  });

  it('is a no-op when send() is called while already streaming (StrictMode guard)', async () => {
    setAuthPseudo('ali_baba');
    const fetchMock = vi.fn(
      () => new Promise<Response>(() => undefined),
    );
    vi.stubGlobal('fetch', fetchMock);

    const first = useChatStore.getState().send({
      subject: 'maths',
      question: 'first',
    });
    await Promise.resolve();
    await Promise.resolve();
    expect(useChatStore.getState().isStreaming).toBe(true);
    expect(fetchMock).toHaveBeenCalledTimes(1);

    // Second send() while the first is still in flight must be ignored.
    await useChatStore.getState().send({
      subject: 'maths',
      question: 'second',
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(useChatStore.getState().messages[0]?.content).toBe('first');

    first.catch(() => undefined);
  });
});
