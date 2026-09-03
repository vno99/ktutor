import { describe, it, expect, beforeEach, vi } from 'vitest';
import { createApiClient } from './api';
import { useAuthStore } from './stores/authStore';

/*
 * Unit tests for the JWT-aware axios factory (s13).
 *
 * The api module exposes a ``createApiClient({ store, refresh, redirect })``
 * factory so the interceptor logic can be exercised without a real
 * network or a real Zustand store. The tests below cover the four
 * behaviours the plan demands (task 10, AC1-AC4):
 *
 *   (a) request with token in store → ``Authorization: Bearer <token>``
 *       header is set on outgoing requests.
 *   (b) 401 on a protected endpoint + refresh OK → the original
 *       request is retried with the new access token, exactly once.
 *   (c) 401 on a protected endpoint + refresh KO → ``clearTokens``
 *       is called and ``redirect`` is invoked with the current path.
 *   (d) Race condition: 3 parallel 401s on different endpoints share
 *       a single ``/api/auth/refresh`` call, then all three are
 *       retried with the rotated pair.
 *
 * The factory is a pure function: each test builds its own client
 * (and its own store snapshot) so the test order does not matter.
 */

function makeStoreSnapshot() {
  // Real Zustand store — we seed it through its public API and read
  // back through ``getState``. The factory accepts any object that
  // exposes ``getState()`` and ``clearTokens()``, so a hand-rolled
  // mock would work too, but using the real store catches
  // integration regressions.
  useAuthStore.setState({
    pseudo: '',
    hydrated: true,
    accessToken: null,
    refreshToken: null,
    role: null,
  });
  return useAuthStore;
}

beforeEach(() => {
  makeStoreSnapshot();
});

describe('createApiClient — request interceptor', () => {
  it('adds Authorization header when a token is present', async () => {
    useAuthStore.getState().setTokens({
      accessToken: 'a1',
      refreshToken: 'r1',
      role: 'eleve',
      pseudo: 'ali',
    });
    const refresh = vi.fn();
    const redirect = vi.fn();
    const client = createApiClient({ store: useAuthStore, refresh, redirect });
    // Mock the underlying adapter so we can capture the request config
    // without making a real network call.
    const adapter = vi.fn(async (config: unknown) => ({
      data: { ok: true },
      status: 200,
      statusText: 'OK',
      headers: {},
      config: config as never,
    }));
    client.defaults.adapter = adapter as never;
    await client.get('/api/chat/history');
    expect(adapter).toHaveBeenCalledTimes(1);
    const sentConfig = (adapter.mock.calls[0] as unknown as [unknown])[0] as {
      headers?: Record<string, string>;
    };
    expect(sentConfig.headers?.Authorization).toBe('Bearer a1');
  });

  it('does NOT add Authorization when no token is present', async () => {
    useAuthStore.setState({ accessToken: null });
    const refresh = vi.fn();
    const redirect = vi.fn();
    const client = createApiClient({ store: useAuthStore, refresh, redirect });
    const adapter = vi.fn(async (config: unknown) => ({
      data: {},
      status: 200,
      statusText: 'OK',
      headers: {},
      config: config as never,
    }));
    client.defaults.adapter = adapter as never;
    await client.post('/api/auth/login', { pseudo: 'ali', password: 'p' });
    const sentConfig = (adapter.mock.calls[0] as unknown as [unknown])[0] as {
      headers?: Record<string, string>;
    };
    expect(sentConfig.headers?.Authorization).toBeUndefined();
  });
});

function make401() {
  // Build an Axios-shaped error and reject with it (NOT throw) so
  // axios attaches the request config to the error. Throwing from
  // an async adapter discards the config attachment.
  return Object.assign(new Error('Unauthorized'), {
    response: { status: 401, data: { error: 'bad', code: 'invalid_token' } },
    config: undefined as unknown,
  });
}

describe('createApiClient — 401 + refresh interceptor', () => {
  it('refreshes the token and retries the request on 401', async () => {
    useAuthStore.getState().setTokens({
      accessToken: 'old-access',
      refreshToken: 'old-refresh',
      role: 'eleve',
      pseudo: 'ali',
    });
    const refresh = vi.fn().mockResolvedValue({
      accessToken: 'new-access',
      refreshToken: 'new-refresh',
      role: 'eleve',
      pseudo: 'ali',
    });
    const redirect = vi.fn();
    const client = createApiClient({ store: useAuthStore, refresh, redirect });
    // First call returns 401, second call (after refresh) returns 200.
    let call = 0;
    client.defaults.adapter = vi.fn(async (config) => {
      call += 1;
      if (call === 1) {
        const err = make401();
        (err as { config: unknown }).config = config;
        return Promise.reject(err);
      }
      return {
        data: { ok: true },
        status: 200,
        statusText: 'OK',
        headers: {},
        config,
      };
    });
    const resp = await client.get('/api/chat/history');
    expect(refresh).toHaveBeenCalledTimes(1);
    expect(refresh).toHaveBeenCalledWith('old-refresh');
    expect(call).toBe(2);
    // The retried request must carry the new access token.
    const retriedConfig = ((client.defaults.adapter as unknown as { mock: { calls: unknown[][] } })
      .mock.calls[1] ?? [])[0] as { headers?: Record<string, string> };
    expect(retriedConfig.headers?.Authorization).toBe('Bearer new-access');
    expect(resp.status).toBe(200);
    // The store was updated with the new pair.
    const s = useAuthStore.getState();
    expect(s.accessToken).toBe('new-access');
    expect(s.refreshToken).toBe('new-refresh');
  });

  it('does NOT trigger refresh on the /api/auth/login endpoint', async () => {
    useAuthStore.setState({ accessToken: null });
    const refresh = vi.fn();
    const redirect = vi.fn();
    const client = createApiClient({ store: useAuthStore, refresh, redirect });
    client.defaults.adapter = vi.fn(async (config) => {
      const err = Object.assign(new Error('Unauthorized'), {
        response: { status: 401, data: { error: 'bad', code: 'invalid_credentials' } },
        config,
      });
      return Promise.reject(err);
    });
    await expect(client.post('/api/auth/login', { pseudo: 'a', password: 'b' })).rejects.toBeDefined();
    expect(refresh).not.toHaveBeenCalled();
    expect(redirect).not.toHaveBeenCalled();
  });

  it('does NOT trigger refresh on the /api/auth/refresh endpoint', async () => {
    useAuthStore.getState().setTokens({
      accessToken: 'a',
      refreshToken: 'r',
      role: 'eleve',
      pseudo: 'ali',
    });
    const refresh = vi.fn();
    const redirect = vi.fn();
    const client = createApiClient({ store: useAuthStore, refresh, redirect });
    client.defaults.adapter = vi.fn(async (config) => {
      const err = Object.assign(new Error('Unauthorized'), {
        response: { status: 401, data: { error: 'bad', code: 'invalid_token' } },
        config,
      });
      return Promise.reject(err);
    });
    await expect(client.post('/api/auth/refresh', { refresh_token: 'r' })).rejects.toBeDefined();
    expect(refresh).not.toHaveBeenCalled();
  });

  it('clears tokens and redirects when the refresh itself fails', async () => {
    useAuthStore.getState().setTokens({
      accessToken: 'old',
      refreshToken: 'bad',
      role: 'eleve',
      pseudo: 'ali',
    });
    const refresh = vi.fn().mockRejectedValue(new Error('refresh failed'));
    const redirect = vi.fn();
    const client = createApiClient({ store: useAuthStore, refresh, redirect, currentPath: '/chat' });
    client.defaults.adapter = vi.fn(async (config) => {
      const err = Object.assign(new Error('Unauthorized'), {
        response: { status: 401, data: { error: 'bad', code: 'invalid_token' } },
        config,
      });
      return Promise.reject(err);
    });
    await expect(client.get('/api/chat/history')).rejects.toBeDefined();
    const s = useAuthStore.getState();
    expect(s.accessToken).toBeNull();
    expect(s.refreshToken).toBeNull();
    expect(redirect).toHaveBeenCalledTimes(1);
    expect(redirect).toHaveBeenCalledWith(expect.stringContaining('/login'));
  });

  it('shares a single refresh call when 3 parallel 401s fire', async () => {
    useAuthStore.getState().setTokens({
      accessToken: 'old',
      refreshToken: 'shared-refresh',
      role: 'eleve',
      pseudo: 'ali',
    });
    let resolveRefresh!: (v: { accessToken: string; refreshToken: string; role: 'eleve'; pseudo: string }) => void;
    const refresh = vi.fn(
      () =>
        new Promise<{
          accessToken: string;
          refreshToken: string;
          role: 'eleve';
          pseudo: string;
        }>((resolve) => {
          resolveRefresh = resolve;
        }),
    );
    const redirect = vi.fn();
    const client = createApiClient({ store: useAuthStore, refresh, redirect });
    let call = 0;
    client.defaults.adapter = vi.fn(async (config) => {
      call += 1;
      if (call <= 3) {
        const err = Object.assign(new Error('Unauthorized'), {
          response: { status: 401, data: { error: 'bad', code: 'invalid_token' } },
          config,
        });
        return Promise.reject(err);
      }
      return {
        data: { ok: true },
        status: 200,
        statusText: 'OK',
        headers: {},
        config,
      };
    });
    const p1 = client.get('/api/a');
    const p2 = client.get('/api/b');
    const p3 = client.get('/api/c');
    // Yield to the microtask queue so the response interceptor's
    // 401 handler runs (and the first one kicks off the shared
    // ``refresh()`` call) BEFORE we resolve the refresh promise.
    // Without this, the test resolves the promise before the
    // first interceptor tick, and the resolve callback is never
    // wired up.
    await new Promise((r) => setTimeout(r, 0));
    // Resolve the single shared refresh.
    resolveRefresh!({
      accessToken: 'rotated',
      refreshToken: 'rotated-r',
      role: 'eleve',
      pseudo: 'ali',
    });
    const [r1, r2, r3] = await Promise.all([p1, p2, p3]);
    expect(refresh).toHaveBeenCalledTimes(1);
    expect(r1.status).toBe(200);
    expect(r2.status).toBe(200);
    expect(r3.status).toBe(200);
    // The store has the rotated pair.
    const s = useAuthStore.getState();
    expect(s.accessToken).toBe('rotated');
    expect(s.refreshToken).toBe('rotated-r');
  });
});
