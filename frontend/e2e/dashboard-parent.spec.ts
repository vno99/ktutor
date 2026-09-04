import { test, expect, type Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { writeFileSync } from 'node:fs';

/*
 * /dashboard/parent + /dashboard/parent/[child_pseudo] e2e (s17).
 *
 * Covers the 6 behaviour tests + 2 a11y scans called out in the
 * plan:
 *  - (a) Parent list page renders 2 Child cards for a parent
 *        linked to 2 eleves
 *  - (b) Empty state Card when the parent has no children linked
 *  - (c) Redirects to /login when unauthenticated
 *  - (d) Eleve who hits the parent list sees a 403 Card
 *  - (e) Parent child-detail page renders the read-only
 *        dashboard (no CTA on empty, no "Voir les détails" on
 *        subject cards) — the AC #6 / AC #3 test
 *  - (f) 403 on a child the parent is NOT linked to
 *  - (g/h) axe-core: 0 critical/serious on /fr/dashboard/parent
 *        and /fr/dashboard/parent/<child>
 *
 * The JWT pair is injected into localStorage via addInitScript.
 * The apiClient interceptor reads the bearer on every request.
 * The backend is stubbed via page.route — no live server.
 *
 * The page-level role check is enforced server-side by the
 * require_role(["parent", "admin"]) dependency. For the
 * 403-as-eleve test, we drive the stub to return 403 just like
 * the real API would.
 */

const PARENT_PAYLOAD = {
  children: [
    {
      pseudo: 'bob',
      linked_at: '2026-08-12T10:00:00Z',
      dashboard: {
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
      },
    },
    {
      pseudo: 'charlie',
      linked_at: '2026-08-25T10:00:00Z',
      dashboard: {
        subjects: [],
        global: {
          score_avg: 0,
          exercises_count: 0,
          last_activity_at: null,
        },
      },
    },
  ],
};

const EMPTY_PAYLOAD = { children: [] };

const CHILD_DASHBOARD_PAYLOAD = {
  subjects: [
    {
      name: 'maths',
      score_avg: 0.75,
      exercises_count: 3,
      last_activity_at: '2026-09-04T08:22:00Z',
    },
  ],
  global: {
    score_avg: 0.75,
    exercises_count: 3,
    last_activity_at: '2026-09-04T08:22:00Z',
  },
};

const PARENT_AUTH = {
  accessToken: 'fake.parent.token',
  refreshToken: 'fake.parent.refresh',
  role: 'parent',
  pseudo: 'alice',
};

const ELEVE_AUTH = {
  accessToken: 'fake.eleve.token',
  refreshToken: 'fake.eleve.refresh',
  role: 'eleve',
  pseudo: 'bob',
};

async function seedAuth(page: Page, auth = PARENT_AUTH) {
  await page.addInitScript((a) => {
    window.localStorage.setItem('ktutor.auth', JSON.stringify(a));
  }, auth);
}

async function stubParent(page: Page, payload: unknown) {
  await page.route('**/api/dashboard/parent', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(payload),
    }),
  );
}

async function stubChild(page: Page, payload: unknown) {
  await page.route('**/api/dashboard/eleve**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(payload),
    }),
  );
}

async function stubChild403(page: Page) {
  await page.route('**/api/dashboard/eleve**', (route) =>
    route.fulfill({
      status: 403,
      contentType: 'application/json',
      body: JSON.stringify({ detail: { error: 'Accès refusé.', code: 'forbidden' } }),
    }),
  );
}

test.describe('Parent list page', () => {
  test('(a) renders 2 Child cards for a parent linked to 2 eleves', async ({
    page,
  }) => {
    await seedAuth(page);
    await stubParent(page, PARENT_PAYLOAD);
    await page.goto('/fr/dashboard/parent');
    await expect(
      page.getByRole('heading', { name: 'Mes enfants' }),
    ).toBeVisible();
    // Two cards (anchors with the child pseudo in their href).
    const bob = page.locator('a[href="/fr/dashboard/parent/bob"]');
    const charlie = page.locator('a[href="/fr/dashboard/parent/charlie"]');
    await expect(bob).toBeVisible();
    await expect(charlie).toBeVisible();
    // Bob's card has the success-rate label and the percentage.
    await expect(bob.getByText('69 %').first()).toBeVisible();
  });

  test('(b) empty state when the parent has no children linked', async ({
    page,
  }) => {
    await seedAuth(page);
    await stubParent(page, EMPTY_PAYLOAD);
    await page.goto('/fr/dashboard/parent');
    await expect(
      page.getByText('Aucun enfant lié à ton compte.'),
    ).toBeVisible();
  });

  test('(c) redirects to /login when unauthenticated', async ({ page }) => {
    // No localStorage seed → AuthGuard sees !isAuthenticated.
    await page.goto('/fr/dashboard/parent');
    await expect(page).toHaveURL(/\/fr\/login\?next=%2Ffr%2Fdashboard%2Fparent$/);
  });

  test('(d) eleve who hits the parent list sees the 403 Card', async ({
    page,
  }) => {
    // Stub the parent endpoint to return 403 (mimics
    // require_role(["parent", "admin"])).
    await seedAuth(page, ELEVE_AUTH);
    await page.route('**/api/dashboard/parent', (route) =>
      route.fulfill({
        status: 403,
        contentType: 'application/json',
        body: JSON.stringify({
          detail: { error: 'Accès refusé.', code: 'forbidden' },
        }),
      }),
    );
    await page.goto('/fr/dashboard/parent');
    await expect(
      page.getByText('Cette page est réservée aux parents.'),
    ).toBeVisible();
  });

  test('(g) axe-core: no critical/serious violations on /fr/dashboard/parent', async ({
    page,
  }) => {
    await seedAuth(page);
    await stubParent(page, PARENT_PAYLOAD);
    await page.goto('/fr/dashboard/parent');
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

test.describe('Parent child-detail page', () => {
  test('(e) renders read-only dashboard for a linked child (AC #3 + #6)', async ({
    page,
  }) => {
    await seedAuth(page);
    await stubChild(page, CHILD_DASHBOARD_PAYLOAD);

    // The apiClient must hit /api/dashboard/eleve?pseudo=bob for
    // BOTH the ParentChildClient pre-fetch AND the DashboardClient
    // mount fetch. Review finding #2: the DashboardClient must
    // accept a `pseudo` prop (s17 fix) that drives the query
    // string. Without it, the second request (from DashboardClient
    // mount) returns the JWT-caller's own dashboard. We collect
    // every /api/dashboard/eleve request and verify all of them
    // carry the child pseudo.
    const eleveRequests: string[] = [];
    page.on('request', (req) => {
      if (req.url().includes('/api/dashboard/eleve')) {
        eleveRequests.push(req.url());
      }
    });

    await page.goto('/fr/dashboard/parent/bob');

    // Wait for the readOnly pastille to confirm the DashboardClient
    // has mounted (its useEffect fires after the pastille renders).
    await expect(
      page.getByText('Vue parent — lecture seule'),
    ).toBeVisible();
    // Give the React effect a tick to fire the second request.
    await page.waitForTimeout(500);

    expect(eleveRequests.length).toBeGreaterThanOrEqual(2);
    for (const url of eleveRequests) {
      const parsed = new URL(url);
      expect(parsed.searchParams.get('pseudo')).toBe('bob');
    }

    // The "Voir les détails" button is removed from the DOM in
    // readOnly mode. The eleve page does NOT show this pastille.
    await expect(
      page.getByRole('button', { name: 'Voir les détails' }),
    ).toHaveCount(0);
    // The Refresh button stays (parent can refresh).
    await expect(
      page.getByRole('button', { name: 'Rafraîchir' }),
    ).toBeVisible();
  });

  test('(f) 403 when the parent is NOT linked to the child', async ({
    page,
  }) => {
    await seedAuth(page);
    await stubChild403(page);
    await page.goto('/fr/dashboard/parent/dave');
    // The custom 403 Card message.
    await expect(
      page.getByText("Cet enfant n'est pas lié à ton compte."),
    ).toBeVisible();
    // The "Back to list" link is unique to the 403 Card.
    await expect(
      page.getByRole('alert').getByRole('link', { name: 'Retour à la liste' }),
    ).toBeVisible();
  });

  test('(h) axe-core: no critical/serious violations on /fr/dashboard/parent/<child>', async ({
    page,
  }) => {
    await seedAuth(page);
    await stubChild(page, CHILD_DASHBOARD_PAYLOAD);
    await page.goto('/fr/dashboard/parent/bob');
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
