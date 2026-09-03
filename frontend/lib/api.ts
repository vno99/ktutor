import axios, { type AxiosError, type AxiosInstance, type InternalAxiosRequestConfig } from 'axios';

/*
 * Axios client — single point of contact with the FastAPI backend.
 *
 * `NEXT_PUBLIC_API_URL` is the convention from CLAUDE.md § Variables
 * d'Environnement. The default points to the local dev backend
 * (http://localhost:8000).
 *
 * s13 adds two interceptors:
 *
 *  - **Request**: every outgoing request that is NOT going to the
 *    auth bootstrap endpoints (``/api/auth/login``,
 *    ``/api/auth/register``, ``/api/auth/refresh``) carries
 *    ``Authorization: Bearer <access_token>`` if the authStore
 *    has one. The login/register endpoints are intentionally
 *    unauthenticated — they are how a user GETS the first token.
 *  - **Response**: a 401 on a protected endpoint triggers a single
 *    ``POST /api/auth/refresh`` call (race-safe via a module-level
 *    ``refreshPromise``) and replays the original request with the
 *    rotated access token. If the refresh itself fails, the
 *    store is cleared and the user is redirected to ``/login`` so
 *    the (public) layout can show the unauthenticated state.
 *
 * The factory pattern (``createApiClient({ store, refresh, redirect, currentPath })``)
 * exists so unit tests can inject a stub store, a stub refresh
 * function, and a stub redirect — the module-level ``apiClient``
 * is the production wiring (``store: useAuthStore``,
 * ``refresh: defaultRefresh``, ``redirect: defaultRedirect``).
 */

const baseURL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

const AUTH_BOOTSTRAP_PATHS = new Set([
  '/api/auth/login',
  '/api/auth/register',
  '/api/auth/refresh',
]);

export interface TokenPair {
  accessToken: string;
  refreshToken: string;
  role: 'eleve' | 'parent' | 'admin';
  pseudo: string;
}

export interface AuthStore {
  getState(): {
    accessToken: string | null;
    refreshToken: string | null;
    setTokens(payload: TokenPair): void;
    clearTokens(): void;
  };
}

export interface ApiClientDeps {
  store: AuthStore;
  /**
   * Performs the actual ``POST /api/auth/refresh`` call. Returns
   * the rotated token pair. Throws on failure (network error,
   * 401, malformed payload). Default: ``defaultRefresh`` which
   * uses a module-private ``apiClient`` (no interceptors, to
   * avoid recursion).
   */
  refresh?: (refreshToken: string) => Promise<TokenPair>;
  /**
   * Side-effect to perform when a refresh attempt fails. The
   * factory passes a target URL like ``"/login?next=<pathname>"``
   * so the (public) layout can re-render the login form with the
   * ``next`` query string preserved. Default: ``defaultRedirect``
   * which is a no-op in environments without ``window`` (tests).
   */
  redirect?: (target: string) => void;
  /**
   * Current path used to build the ``?next=`` query string on
   * logout-via-401. Default: ``typeof window === 'undefined' ? '/' : window.location.pathname``.
   */
  currentPath?: string;
}

async function defaultRefresh(refreshToken: string): Promise<TokenPair> {
  // The refresh call MUST NOT go through ``apiClient``: a 401 on
  // the refresh endpoint itself would loop. We use a bare axios
  // instance with no interceptors.
  const bare = axios.create({ baseURL });
  const resp = await bare.post<{
    access_token: string;
    refresh_token: string;
    expires_in: number;
  }>('/api/auth/refresh', { refresh_token: refreshToken });
  // The store only keeps the JWT pair; the ``role`` and
  // ``pseudo`` are stable across a refresh (the user is the
  // same), so we read them from the current store snapshot.
  return {
    accessToken: resp.data.access_token,
    refreshToken: resp.data.refresh_token,
    role: 'eleve', // overwritten by the caller via the store mutation below
    pseudo: '',
  };
}

function defaultRedirect(target: string): void {
  if (typeof window === 'undefined') return;
  // Use the History API instead of ``router.push`` so this module
  // does not import next/navigation (which is unavailable in
  // tests and on the server). The (public)/[locale]/layout owns
  // the routing — it reads the URL.
  window.location.assign(target);
}

export function createApiClient(deps: ApiClientDeps): AxiosInstance {
  const refresh = deps.refresh ?? defaultRefresh;
  const redirect = deps.redirect ?? defaultRedirect;
  const getCurrentPath = (): string => {
    if (deps.currentPath !== undefined) return deps.currentPath;
    if (typeof window === 'undefined') return '/';
    return window.location.pathname;
  };

  const client = axios.create({
    baseURL,
    headers: {
      Accept: 'application/json',
    },
  });

  // Request interceptor: attach the bearer if we have one.
  client.interceptors.request.use((config: InternalAxiosRequestConfig) => {
    const token = deps.store.getState().accessToken;
    if (token) {
      config.headers = config.headers ?? {};
      (config.headers as Record<string, string>).Authorization = `Bearer ${token}`;
    }
    return config;
  });

  // Response interceptor: handle 401 → refresh → retry (once).
  // The refresh promise is shared across all in-flight requests
  // (race condition protection — see task 10 / AC4 of the plan).
  let refreshPromise: Promise<TokenPair> | null = null;

  client.interceptors.response.use(
    (response) => response,
    async (error: AxiosError) => {
      const status = error.response?.status;
      const originalRequest = error.config as
        | (InternalAxiosRequestConfig & { _retried?: boolean })
        | undefined;

      // Not a 401, or no config to retry: just re-throw.
      if (status !== 401 || !originalRequest) {
        throw error;
      }

      // Don't loop on the auth bootstrap endpoints (the 401 is
      // a legitimate "wrong credentials" answer, not a stale
      // token).
      const requestUrl = originalRequest.url ?? '';
      if (AUTH_BOOTSTRAP_PATHS.has(requestUrl) || originalRequest._retried) {
        throw error;
      }

      // Mark the request as already retried BEFORE awaiting the
      // refresh so a chained error doesn't bounce it back into
      // this branch.
      originalRequest._retried = true;

      const currentRefreshToken = deps.store.getState().refreshToken;
      if (!currentRefreshToken) {
        // Nothing to refresh with — bail out and let the caller
        // see the 401. The page-level error handler will redirect.
        deps.store.getState().clearTokens();
        redirect(`/login?next=${encodeURIComponent(getCurrentPath())}`);
        throw error;
      }

      try {
        const pair = refreshPromise ?? refresh(currentRefreshToken);
        refreshPromise = pair;
        const rotated = await pair;
        // Preserve the pseudo from the previous store snapshot
        // (the refresh endpoint does NOT return it; the user is
        // the same identity). The ``role`` returned by the
        // backend can change between two refreshes, so we honour
        // what the backend says.
        const previous = deps.store.getState() as unknown as { pseudo: string; role: 'eleve' | 'parent' | 'admin' };
        deps.store.getState().setTokens({
          accessToken: rotated.accessToken,
          refreshToken: rotated.refreshToken,
          role: rotated.role || previous.role,
          pseudo: rotated.pseudo || previous.pseudo,
        });
        // Retry the original request with the new bearer.
        originalRequest.headers = originalRequest.headers ?? {};
        (originalRequest.headers as Record<string, string>).Authorization =
          `Bearer ${rotated.accessToken}`;
        return client.request(originalRequest);
      } catch (refreshError) {
        // The refresh itself failed (401, network, etc.). Wipe
        // the store and redirect to /login.
        deps.store.getState().clearTokens();
        redirect(`/login?next=${encodeURIComponent(getCurrentPath())}`);
        throw refreshError;
      } finally {
        refreshPromise = null;
      }
    },
  );

  return client;
}

/*
 * Default singleton used by the application code (uploadStore,
 * login page, etc.). Wrapped via the factory with the real
 * authStore and the real default refresh / redirect hooks.
 */
import { useAuthStore } from './stores/authStore';

export const apiClient: AxiosInstance = createApiClient({
  store: useAuthStore as unknown as AuthStore,
  refresh: defaultRefresh,
  redirect: defaultRedirect,
});

export const API_BASE_URL = baseURL;
