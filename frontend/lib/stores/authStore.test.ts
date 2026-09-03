import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { useAuthStore } from './authStore';

/*
 * Unit tests for the s13 authStore extension.
 *
 * Scope: the pure state transitions of the store. We do NOT
 * exercise the network — that lives in the apiClient test
 * (``lib/api.test.ts``). We DO exercise:
 *
 *  - ``setTokens`` writes to ``localStorage`` and updates the store
 *  - ``clearTokens`` empties ``localStorage`` and resets the store
 *  - ``hydrate`` reads ``localStorage`` and sets ``hydrated=true``
 *  - ``hydrate`` falls back to the ``pseudo`` cookie when
 *    ``localStorage`` is empty
 *  - ``hydrate`` swallows the ``localStorage`` ``SecurityError``
 *    thrown in private-mode browsers (no crash)
 *  - ``isAuthenticated`` is true only when ``hydrated`` and
 *    ``accessToken`` are both set
 *
 * The authStore is a Zustand singleton. Each test starts with a
 * known state via ``useAuthStore.setState`` to avoid bleed-through.
 */

function setStateEmpty() {
  useAuthStore.setState({
    pseudo: '',
    hydrated: false,
    accessToken: null,
    refreshToken: null,
    role: null,
  });
}

describe('authStore (tokens + hydrate)', () => {
  beforeEach(() => {
    setStateEmpty();
    // jsdom on certain CI configs exposes localStorage without a
    // ``clear`` method. We polyfill here so the suite is portable.
    try {
      window.localStorage.clear();
    } catch {
      // Best-effort: per-key removal below if ``clear`` is missing.
    }
    // Belt-and-braces: clear all keys we own.
    for (const key of ['ktutor.auth']) {
      try {
        window.localStorage.removeItem(key);
      } catch {
        /* ignore */
      }
    }
    // Reset cookie.
    document.cookie = 'pseudo=; path=/; max-age=0';
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('setTokens', () => {
    it('persists access + refresh tokens in localStorage', () => {
      useAuthStore.getState().setTokens({
        accessToken: 'access-1',
        refreshToken: 'refresh-1',
        role: 'eleve',
        pseudo: 'ali',
      });
      const raw = window.localStorage.getItem('ktutor.auth');
      expect(raw).not.toBeNull();
      const parsed = JSON.parse(raw as string);
      expect(parsed.accessToken).toBe('access-1');
      expect(parsed.refreshToken).toBe('refresh-1');
      expect(parsed.role).toBe('eleve');
      expect(parsed.pseudo).toBe('ali');
    });

    it('updates the in-memory state', () => {
      useAuthStore.getState().setTokens({
        accessToken: 'access-2',
        refreshToken: 'refresh-2',
        role: 'parent',
        pseudo: 'mum',
      });
      const s = useAuthStore.getState();
      expect(s.accessToken).toBe('access-2');
      expect(s.refreshToken).toBe('refresh-2');
      expect(s.role).toBe('parent');
      expect(s.pseudo).toBe('mum');
    });
  });

  describe('clearTokens', () => {
    it('empties the in-memory state', () => {
      useAuthStore.getState().setTokens({
        accessToken: 'a',
        refreshToken: 'r',
        role: 'eleve',
        pseudo: 'ali',
      });
      useAuthStore.getState().clearTokens();
      const s = useAuthStore.getState();
      expect(s.accessToken).toBeNull();
      expect(s.refreshToken).toBeNull();
      expect(s.role).toBeNull();
      expect(s.pseudo).toBe('');
    });

    it('removes the localStorage key', () => {
      useAuthStore.getState().setTokens({
        accessToken: 'a',
        refreshToken: 'r',
        role: 'eleve',
        pseudo: 'ali',
      });
      useAuthStore.getState().clearTokens();
      expect(window.localStorage.getItem('ktutor.auth')).toBeNull();
    });
  });

  describe('hydrate', () => {
    it('reads localStorage when present', () => {
      window.localStorage.setItem(
        'ktutor.auth',
        JSON.stringify({
          accessToken: 'stored-access',
          refreshToken: 'stored-refresh',
          role: 'eleve',
          pseudo: 'ali',
        }),
      );
      useAuthStore.getState().hydrate();
      const s = useAuthStore.getState();
      expect(s.hydrated).toBe(true);
      expect(s.accessToken).toBe('stored-access');
      expect(s.refreshToken).toBe('stored-refresh');
      expect(s.role).toBe('eleve');
      expect(s.pseudo).toBe('ali');
    });

    it('falls back to the pseudo cookie when localStorage is empty', () => {
      // No localStorage entry. The cookie holds the pseudo (ADR 011).
      document.cookie = 'pseudo=cookie-ali; path=/';
      useAuthStore.getState().hydrate();
      const s = useAuthStore.getState();
      expect(s.hydrated).toBe(true);
      expect(s.pseudo).toBe('cookie-ali');
      // No tokens — localStorage was empty.
      expect(s.accessToken).toBeNull();
      expect(s.refreshToken).toBeNull();
    });

    it('survives a SecurityError from localStorage', () => {
      const originalGetItem = window.localStorage.getItem;
      window.localStorage.getItem = vi.fn(() => {
        throw new Error('SecurityError: storage disabled');
      }) as typeof originalGetItem;
      try {
        useAuthStore.getState().hydrate();
      } finally {
        window.localStorage.getItem = originalGetItem;
      }
      const s = useAuthStore.getState();
      expect(s.hydrated).toBe(true);
      // No tokens (we never read localStorage), no crash.
      expect(s.accessToken).toBeNull();
    });
  });

  describe('isAuthenticated selector', () => {
    it('is false when not hydrated', () => {
      useAuthStore.setState({
        accessToken: 'a',
        refreshToken: 'r',
        role: 'eleve',
        pseudo: 'ali',
        hydrated: false,
      });
      expect(useAuthStore.getState().isAuthenticated).toBe(false);
    });

    it('is false when hydrated but no token', () => {
      useAuthStore.setState({
        accessToken: null,
        refreshToken: null,
        role: null,
        pseudo: '',
        hydrated: true,
      });
      expect(useAuthStore.getState().isAuthenticated).toBe(false);
    });

    it('is true when hydrated and accessToken is set', () => {
      useAuthStore.setState({
        accessToken: 'a',
        refreshToken: 'r',
        role: 'eleve',
        pseudo: 'ali',
        hydrated: true,
      });
      expect(useAuthStore.getState().isAuthenticated).toBe(true);
    });
  });
});
