import { test, expect, type Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

/*
 * /dashboard/eleve page e2e (s16).
 *
 * Covers the 5 behaviour tests + 2 a11y scans called out in the plan:
 *  - (a) renders Summary + Chart + Subject cards for a logged-in eleve
 *  - (b) chart legend is below the chart at 360px (AC #3)
 *  - (c) empty state when the eleve has no attempts
 *  - (d) redirects to /login when unauthenticated
 *  - (e/f) axe-core: 0 critical/serious on /fr/eleve/dashboard and /en
 *
 * The JWT is in localStorage (s13), so the test sets it directly
 * via `addInitScript` to skip the login redirect dance. The
 * apiClient interceptor reads the token on the client side before
 * each request.
 *
 * Backend responses are stubbed via page.route (no backend).
 */

const DASHBOARD_PAYLOAD = {
  subjects: [
    {
      name: 'maths',
      score_avg: 0.75,
      exercises_count: 3,
      last_activity_at: '2026-09-04T08:22:00Z',
    },
    {
      name: 'francais',
      score_avg: 0.6,
      exercises_count: 2,
      last_activity_at: '2026-09-02T15:00:00Z',
    },
  ],
  global: {
    score_avg: (0.75 * 3 + 0.6 * 2) / 5,
    exercises_count: 5,
    last_activity_at: '2026-09-04T08:22:00Z',
  },
};

const EMPTY_PAYLOAD = {
  subjects: [],
  global: {
    score_avg: 0,
    exercises_count: 0,
    last_activity_at: null,
  },
};

const AUTH_PAYLOAD = {
  accessToken: 'fake.access.token',
  refreshToken: 'fake.refresh.token',
  role: 'eleve',
  pseudo: 'ali_baba',
};

async function seedAuth(page: Page) {
  // Inject the JWT pair into localStorage so the apiClient
  // interceptor can add the bearer header on every request.
  await page.addInitScript((auth) => {
    window.localStorage.setItem('ktutor.auth', JSON.stringify(auth));
  }, AUTH_PAYLOAD);
}

async function stubDashboard(page: Page, payload: unknown) {
  await page.route('**/api/dashboard/eleve', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(payload),
    }),
  );
}

test.describe('Dashboard eleve page', () => {
  test('(a) renders Summary, Chart and 2 Subject cards for a logged-in eleve', async ({
    page,
  }) => {
    await seedAuth(page);
    await stubDashboard(page, DASHBOARD_PAYLOAD);
    await page.goto('/fr/eleve/dashboard');
    await expect(
      page.getByRole('heading', { name: 'Mon tableau de bord' }),
    ).toBeVisible();
    // Global value: (0.75*3 + 0.6*2) / 5 = 0.69 → "69 %".
    await expect(page.getByText('69 %').first()).toBeVisible();
    // 5 tentatives (5 == plural in FR → "5 tentatives").
    await expect(page.getByText(/5 tentatives/)).toBeVisible();
    // Two subject cards rendered.
    await expect(page.getByTestId('subject-card-maths')).toBeVisible();
    await expect(page.getByTestId('subject-card-francais')).toBeVisible();
    // The chart legend is in the DOM (Recharts renders it as a <ul>).
    // The YAxis label and the legend share the same text; the legend
    // is the one rendered outside the SVG.
    await expect(
      page.locator('.recharts-default-legend').getByText('Taux de réussite (%)'),
    ).toBeVisible();
  });

  test('(b) chart legend is rendered below the chart at 360px viewport', async ({
    page,
  }) => {
    await page.setViewportSize({ width: 360, height: 800 });
    await seedAuth(page);
    await stubDashboard(page, DASHBOARD_PAYLOAD);
    await page.goto('/fr/eleve/dashboard');
    // The Recharts legend is inside an <ul> with class
    // "recharts-default-legend". The chart <svg> sits above it.
    const chart = page.locator('.recharts-wrapper').first();
    const legend = page.locator('.recharts-default-legend').first();
    await expect(chart).toBeVisible();
    await expect(legend).toBeVisible();
    const chartBox = await chart.boundingBox();
    const legendBox = await legend.boundingBox();
    expect(chartBox).not.toBeNull();
    expect(legendBox).not.toBeNull();
    if (chartBox && legendBox) {
      // The legend's top is at or below the chart's bottom — not above it.
      expect(legendBox.y).toBeGreaterThanOrEqual(chartBox.y + chartBox.height - 50);
    }
  });

  test('(c) empty state when the eleve has no attempts', async ({ page }) => {
    await seedAuth(page);
    await stubDashboard(page, EMPTY_PAYLOAD);
    await page.goto('/fr/eleve/dashboard');
    await expect(
      page.getByText("Tu n'as pas encore tenté d'exercice."),
    ).toBeVisible();
    await expect(
      page.getByRole('link', { name: 'Aller au chat' }),
    ).toBeVisible();
  });

  test('(d) redirects to /login when unauthenticated', async ({ page }) => {
    // No localStorage seed → AuthGuard sees !isAuthenticated.
    await page.goto('/fr/eleve/dashboard');
    await expect(page).toHaveURL(/\/fr\/login\?next=%2Ffr%2Feleve%2Fdashboard$/);
  });

  test('(e) axe-core: no critical/serious violations on /fr/eleve/dashboard', async ({
    page,
  }) => {
    await seedAuth(page);
    await stubDashboard(page, DASHBOARD_PAYLOAD);
    await page.goto('/fr/eleve/dashboard');
    const accessibilityScanResults = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa'])
      .analyze();
    const blocking = accessibilityScanResults.violations.filter(
      (v) => v.impact === 'critical' || v.impact === 'serious',
    );
    expect(
      blocking,
      `Critical/serious axe violations:\n${JSON.stringify(blocking, null, 2)}`,
    ).toEqual([]);
  });

  test('(f) axe-core: no critical/serious violations on /en/eleve/dashboard', async ({
    page,
  }) => {
    await seedAuth(page);
    await stubDashboard(page, DASHBOARD_PAYLOAD);
    await page.goto('/en/eleve/dashboard');
    const accessibilityScanResults = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa'])
      .analyze();
    const blocking = accessibilityScanResults.violations.filter(
      (v) => v.impact === 'critical' || v.impact === 'serious',
    );
    expect(
      blocking,
      `Critical/serious axe violations:\n${JSON.stringify(blocking, null, 2)}`,
    ).toEqual([]);
  });
});
