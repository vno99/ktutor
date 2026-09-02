'use client';

import { create } from 'zustand';

/*
 * authStore — pseudo persistence.
 *
 * The `pseudo` is the tenant key for multi-tenancy in this app (real JWT
 * auth arrives in s12-s15). For s11a, the user enters a pseudo in the
 * header; the value is mirrored to a cookie so that the SSR/CSR boundary
 * is consistent and the upload/chat flows in s11b/s11c can read it.
 *
 * The store is hydrated client-side only (Next.js 16: no SSR state).
 * cf. docs/research/s11-frontend-upload-chat.md D5.
 */
const PSEUDO_COOKIE = 'pseudo';
const PSEUDO_PATTERN = /^[a-zA-Z0-9_]{3,32}$/;

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

export interface AuthState {
  pseudo: string;
  hydrated: boolean;
  hydrate: () => void;
  setPseudo: (next: string) => boolean;
  clearPseudo: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  pseudo: '',
  hydrated: false,
  hydrate: () => {
    if (typeof window === 'undefined') return;
    const fromCookie = readPseudoFromCookie();
    set({ pseudo: fromCookie, hydrated: true });
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
}));

export function pseudoInitial(value: string): string {
  return isValidPseudo(value) ? value : '';
}

export const PSEUDO_COOKIE_NAME = PSEUDO_COOKIE;
