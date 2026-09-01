import { defineConfig, devices } from '@playwright/test';

/*
 * Playwright config — s11a.
 *
 * - testDir: ./e2e (3 specs, 10 tests)
 * - webServer: starts `next dev` on port 3000 unless an existing server is running.
 *   In CI, this is what the job `frontend` relies on; locally, it can be
 *   disabled by setting CI=0 (reuseExistingServer becomes true).
 * - Reporter: list (terminal) + HTML (never opened automatically).
 * - Screenshots and traces: only on failure, to keep the artifact size sane.
 */
export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: [['list'], ['html', { open: 'never' }]],
  timeout: 30_000,
  use: {
    baseURL: 'http://localhost:3000',
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'], locale: 'fr-FR' },
    },
  ],
  webServer: {
    command: 'pnpm dev',
    url: 'http://localhost:3000/fr/',
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
    stdout: 'ignore',
    stderr: 'pipe',
  },
});
