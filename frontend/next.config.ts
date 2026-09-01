import type { NextConfig } from 'next';
import createNextIntlPlugin from 'next-intl/plugin';

const withNextIntl = createNextIntlPlugin('./i18n/request.ts');

/*
 * Next.js 16 config — locked down to the few keys the project actually uses.
 * - `reactStrictMode`: true (default, kept explicit for posterity).
 * - `typedRoutes: true`: enables App Router type-safe links
 *   (cf. Next 16 — moved out of `experimental` in 16.0).
 *
 * Note: `output: 'standalone'` was considered for the future production
 * deployment but s11a ships only the dev server. The standalone build
 * also requires symlink support (EPERM on Windows without elevation), so
 * it is intentionally left out. Re-enable in the prod story.
 *
 * cf. docs/research/s11-frontend-upload-chat.md Piège #4 (reactStrictMode
 * double-invokes effects in dev; the Header is idempotent).
 */
const nextConfig: NextConfig = {
  reactStrictMode: true,
  typedRoutes: true,
  transpilePackages: [],
};

export default withNextIntl(nextConfig);
