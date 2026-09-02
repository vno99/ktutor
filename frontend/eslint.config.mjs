import next from 'eslint-config-next/core-web-vitals';

/*
 * ESLint flat config — Next.js 16 ships flat-config-only setups.
 * The `eslint-config-next/core-web-vitals` preset wraps the Next.js
 * recommended rules (including @next/eslint-plugin-next, react,
 * react-hooks, jsx-a11y, typescript-eslint).
 *
 * The preset's parser is wired internally; we only override the file
 * globs and ignore patterns. `ignores` covers build artifacts and the
 * Playwright e2e specs (which run via the Playwright runner, not ESLint).
 */
const config = [
  ...next,
  {
    ignores: [
      'node_modules/**',
      '.next/**',
      'out/**',
      'coverage/**',
      'playwright-report/**',
      'test-results/**',
      'lighthouseci/**',
      'next-env.d.ts',
    ],
  },
];

export default config;
