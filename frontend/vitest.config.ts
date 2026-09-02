import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import path from 'node:path';

/*
 * vitest config — s11b.
 *
 * Scope: pick up *.test.{ts,tsx} next to source files in components/
 * and lib/ (store + helpers). The setup file is intentionally
 * minimal: we don't need jest-dom matchers for the current tests,
 * but the import is here so a future test can extend without
 * reconfiguring.
 *
 * The path alias '@/*' mirrors tsconfig.json (vitest reads the same
 * tsconfig.paths via vite-tsconfig-paths would be overkill — we
 * resolve '@' explicitly).
 */
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, '.'),
    },
  },
  test: {
    environment: 'jsdom',
    include: [
      'components/**/*.test.{ts,tsx}',
      'lib/**/*.test.{ts,tsx}',
    ],
    setupFiles: ['./test/setup.ts'],
    globals: false,
  },
});
