'use client';

import { create } from 'zustand';

/*
 * authStore — identity + token state for the frontend.
 *
 * s11a shipped a cookie-backed ``pseudo`` (ADR 011). s13 adds the
 * JWT pair (access + refresh + role) on top of it, with
 * localStorage as the persistence layer (POC, see research §
 * Traps 7). The cookie stays as a *transitional cache* of the
 * pseudo so the rest of the app (chat, upload) keeps reading
 * ``authStore.pseudo`` while the JWT migration lands in s15.
 *
 * Source-of-truth hierarchy (s13):
 *
 *   1. JWT ``sub`` claim is the canonical pseudo on the server.
 *   2. The frontend mirrors it into ``authStore.pseudo`` for
 *      backwards compatibility with chatStore / uploadStore.
 *   3. The cookie is a stale-by-design fallback for SSR / RSC
 *      reads. It is populated by ``setPseudo`` (legacy) and by
 *      ``setTokens`` (s13) so a refresh keeps the cookie warm.
 *
 * Storage rules:
 *
 *   - Tokens live in ``localStorage`` under the key ``ktutor.auth``
 *     (JSON-serialised). HttpOnly cookies are a s15+ concern.
 *   - ``localStorage`` may throw (``SecurityError`` in private
 *     mode); ``hydrate`` swallows the error so the app still
 *     works without persistence.
 *   - Hydration is client-side only (Next.js 16 App Router has
 *     no SSR state for Zustand). ``hydrate()`` is called in
 *     ``<Header>``'s mount ``useEffect``.
 *
 * ``isAuthenticated`` is a *derived* field. We store it on the
 * state (rather than as a getter) so that ``useAuthStore.getState()``
 * callers see a current value. The store subscribes to itself
 * once at module load and recomputes the flag whenever
 * ``hydrated`` or ``accessToken`` changes — including updates
 * issued via ``useAuthStore.setState(...)`` from tests.
 */

const PSEUDO_COOKIE = 'pseudo';
const PSEUDO_PATTERN = /^[a-zA-Z0-9_]{3,32}$/;
const AUTH_STORAGE_KEY = 'ktutor.auth';

export type Role = 'eleve' | 'parent' | 'admin';

export function isValidPseudo(value: string): boolean {
  return PSEUDO_PATTERN.test(value);
}

function readPseudoFromCookie(): string {
  if (typeof document === 'undefined') return '';
  const match = document.cookie
    .split('; ')
    .find((row) => row.startsWith(`${PSEUDO_COOKIE}=`));
  if (!match) return '';
  return decodeURIComponent(match.slice(PSEUDO_COOKIE.length + 1));
}

function writePseudoCookie(value: string): void {
  if (typeof document === 'undefined') return;
  // 30-day persistence, SameSite=Lax (default).
  const maxAge = 60 * 60 * 24 * 30;
  document.cookie = `${PSEUDO_COOKIE}=${encodeURIComponent(value)}; path=/; max-age=${maxAge}; SameSite=Lax`;
}

function clearPseudoCookie(): void {
  if (typeof document === 'undefined') return;
  document.cookie = `${PSEUDO_COOKIE}=; path=/; max-age=0; SameSite=Lax`;
}

function readAuthStorage(): {
  accessToken: string;
  refreshToken: string;
  role: Role;
  pseudo: string;
} | null {
  if (typeof window === 'undefined') return null;
  let raw: string | null = null;
  try {
    raw = window.localStorage.getItem(AUTH_STORAGE_KEY);
  } catch {
    // ``SecurityError`` in private mode, disabled storage, etc.
    // The caller treats this as "no persisted state".
    return null;
  }
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as unknown;
    if (
      parsed &&
      typeof parsed === 'object' &&
      typeof (parsed as { accessToken?: unknown }).accessToken === 'string' &&
      typeof (parsed as { refreshToken?: unknown }).refreshToken === 'string'
    ) {
      const role = (parsed as { role?: unknown }).role;
      const pseudo = (parsed as { pseudo?: unknown }).pseudo;
      return {
        accessToken: (parsed as { accessToken: string }).accessToken,
        refreshToken: (parsed as { refreshToken: string }).refreshToken,
        role: role === 'eleve' || role === 'parent' || role === 'admin' ? role : 'eleve',
        pseudo: typeof pseudo === 'string' ? pseudo : '',
      };
    }
  } catch {
    // Corrupted JSON — treat as missing.
    return null;
  }
  return null;
}

function writeAuthStorage(payload: {
  accessToken: string;
  refreshToken: string;
  role: Role;
  pseudo: string;
}): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(payload));
  } catch {
    // Best-effort. A storage failure must not break login.
  }
}

function clearAuthStorage(): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.removeItem(AUTH_STORAGE_KEY);
  } catch {
    /* ignore */
  }
}

function computeIsAuthenticated(s: { hydrated: boolean; accessToken: string | null }): boolean {
  return s.hydrated && s.accessToken !== null;
}

export interface AuthState {
  pseudo: string;
  hydrated: boolean;
  accessToken: string | null;
  refreshToken: string | null;
  role: Role | null;
  /** Derived: true when the store has hydrated AND an access token is present. */
  isAuthenticated: boolean;
  hydrate: () => void;
  setPseudo: (next: string) => boolean;
  clearPseudo: () => void;
  /** Persist a new JWT pair + role + pseudo. Used after ``POST /api/auth/login`` and ``POST /api/auth/refresh``. */
  setTokens: (payload: {
    accessToken: string;
    refreshToken: string;
    role: Role;
    pseudo: string;
  }) => void;
  /** Drop the JWT pair. Used after ``POST /api/auth/logout`` and on refresh failure. */
  clearTokens: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  pseudo: '',
  hydrated: false,
  accessToken: null,
  refreshToken: null,
  role: null,
  isAuthenticated: false,
  hydrate: () => {
    if (typeof window === 'undefined') return;
    // 1. Try localStorage (s13 — JWTs live there).
    const stored = readAuthStorage();
    if (stored) {
      set({
        pseudo: stored.pseudo,
        accessToken: stored.accessToken,
        refreshToken: stored.refreshToken,
        role: stored.role,
        hydrated: true,
        isAuthenticated: true,
      });
      return;
    }
    // 2. Fall back to the cookie (ADR 011). Pseudo is the only
    //    piece of state the legacy code path carries.
    const fromCookie = readPseudoFromCookie();
    set({
      pseudo: fromCookie,
      hydrated: true,
      accessToken: null,
      refreshToken: null,
      role: null,
      isAuthenticated: false,
    });
  },
  setPseudo: (next: string) => {
    if (!isValidPseudo(next)) return false;
    writePseudoCookie(next);
    set({ pseudo: next });
    return true;
  },
  clearPseudo: () => {
    clearPseudoCookie();
    set({ pseudo: '' });
  },
  setTokens: (payload) => {
    writeAuthStorage(payload);
    // Mirror the pseudo into the cookie for legacy readers.
    if (payload.pseudo) writePseudoCookie(payload.pseudo);
    set({
      pseudo: payload.pseudo,
      accessToken: payload.accessToken,
      refreshToken: payload.refreshToken,
      role: payload.role,
      isAuthenticated: true,
    });
  },
  clearTokens: () => {
    clearAuthStorage();
    clearPseudoCookie();
    set({
      pseudo: '',
      accessToken: null,
      refreshToken: null,
      role: null,
      isAuthenticated: false,
    });
  },
}));

/*
 * Subscribe to keep the derived ``isAuthenticated`` field in sync
 * after external ``setState`` calls (tests, devtools, future
 * migrations). Without this, a test that does
 * ``useAuthStore.setState({ hydrated: true, accessToken: 'a' })``
 * would still see ``isAuthenticated === false`` because the field
 * is plain data, not a getter.
 */
useAuthStore.subscribe((s, prev) => {
  if (s.hydrated === prev.hydrated && s.accessToken === prev.accessToken) return;
  const next = computeIsAuthenticated(s);
  if (s.isAuthenticated !== next) {
    useAuthStore.setState({ isAuthenticated: next });
  }
});

/*
 * Selector helper for components that want to read the derived
 * flag without subscribing to the whole state.
 */
function selectIsAuthenticated(state: AuthState): boolean {
  return state.hydrated && state.accessToken !== null;
}

export { selectIsAuthenticated };

export function pseudoInitial(value: string): string {
  return isValidPseudo(value) ? value : '';
}

export const PSEUDO_COOKIE_NAME = PSEUDO_COOKIE;
export const AUTH_STORAGE_KEY_NAME = AUTH_STORAGE_KEY;
