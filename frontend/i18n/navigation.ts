import { createNavigation } from 'next-intl/navigation';
import { routing } from './routing';

/*
 * Locale-aware navigation helpers.
 * Use `useRouter`, `Link`, `usePathname`, and `redirect` from this module
 * instead of next/navigation in client/server components that live under
 * the [locale] segment. This is what next-intl recommends (cf. ADR 006).
 */
export const { Link, redirect, usePathname, useRouter, getPathname } =
  createNavigation(routing);
