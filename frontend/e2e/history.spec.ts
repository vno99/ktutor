import { test, expect, type Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

/*
 * /history and /history/{conversation_id} pages e2e (s19).
 *
 * Covers the 5 behaviour tests + 2 a11y scans called out in the plan:
 *  - (a) renders 3 conversation cards with the right subject pill
 *  - (b) empty state with a CTA to /chat
 *  - (c) pagination — click "Suivant" updates the URL with ?offset=2
 *  - (d) click a card → /{locale}/history/{id} renders the user +
 *        assistant messages in order, with the source pills
 *  - (e) not-found on 404 — history.notFound + back button
 *  - (a11y fr) axe-core: 0 critical/serious on /fr/history
 *  - (a11y en) axe-core: 0 critical/serious on /en/history/{stubbed_id}
 *
 * The JWT is in localStorage (s13), so the test sets it directly
 * via `addInitScript` to skip the login redirect dance. The
 * apiClient interceptor reads the token on the client side before
 * each request.
 *
 * Backend responses are stubbed via page.route (no backend).
 */

const CONV_ID_MATHS = '11111111-1111-1111-1111-111111111111';
const CONV_ID_FR = '22222222-2222-2222-2222-222222222222';
const CONV_ID_MATHS_2 = '33333333-3333-3333-3333-333333333333';

const FULL_LIST_PAYLOAD = {
  items: [
    {
      id: CONV_ID_MATHS,
      subject: 'maths',
      first_question: 'Qu\'est-ce qu\'une dérivée ?',
      last_activity_at: '2026-09-04T08:22:00Z',
      message_count: 4,
    },
    {
      id: CONV_ID_FR,
      subject: 'francais',
      first_question: 'Règle du participe passé avec avoir ?',
      last_activity_at: '2026-09-02T15:00:00Z',
      message_count: 2,
    },
    {
      id: CONV_ID_MATHS_2,
      subject: 'maths',
      first_question: 'Comment résoudre une équation du second degré ?',
      last_activity_at: '2026-08-30T10:00:00Z',
      message_count: 6,
    },
  ],
  total: 3,
  limit: 20,
  offset: 0,
};

const EMPTY_PAYLOAD = {
  items: [],
  total: 0,
  limit: 20,
  offset: 0,
};

const PAGINATED_PAYLOAD = {
  items: [
    {
      id: CONV_ID_MATHS,
      subject: 'maths',
      first_question: 'Qu\'est-ce qu\'une dérivée ?',
      last_activity_at: '2026-09-04T08:22:00Z',
      message_count: 4,
    },
    {
      id: CONV_ID_FR,
      subject: 'francais',
      first_question: 'Règle du participe passé avec avoir ?',
      last_activity_at: '2026-09-02T15:00:00Z',
      message_count: 2,
    },
  ],
  total: 5,
  limit: 2,
  offset: 0,
};

const DETAIL_PAYLOAD = {
  id: CONV_ID_MATHS,
  subject: 'maths',
  first_question: 'Qu\'est-ce qu\'une dérivée ?',
  last_activity_at: '2026-09-04T08:22:00Z',
  message_count: 2,
  messages: [
    {
      id: 'm1',
      role: 'user',
      content: 'Qu\'est-ce qu\'une dérivée ?',
      sources: null,
      created_at: '2026-09-04T08:22:00Z',
    },
    {
      id: 'm2',
      role: 'assistant',
      content: 'Une dérivée mesure la variation instantanée d\'une fonction.',
      sources: [
        { filename: 'cours-derivees.pdf', chunk_index: 3 },
        { filename: 'cours-derivees.pdf', chunk_index: 7 },
      ],
      created_at: '2026-09-04T08:22:01Z',
    },
  ],
};

const AUTH_PAYLOAD = {
  accessToken: 'fake.access.token',
  refreshToken: 'fake.refresh.token',
  role: 'eleve',
  pseudo: 'ali_baba',
};

async function seedAuth(page: Page) {
  await page.addInitScript((auth) => {
    window.localStorage.setItem('ktutor.auth', JSON.stringify(auth));
  }, AUTH_PAYLOAD);
}

async function stubHistory(page: Page, payload: unknown) {
  await page.route(/\/api\/chat\/history(\/|$|\?)/, (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(payload),
    }),
  );
}

async function stubHistoryNotFound(page: Page) {
  await page.route(/\/api\/chat\/history(\/|$|\?)/, (route) =>
    route.fulfill({
      status: 404,
      contentType: 'application/json',
      body: JSON.stringify({ detail: { error: 'Conversation introuvable.', code: 'not_found' } }),
    }),
  );
}

test.describe('History list page', () => {
  test('(a) renders 3 conversation cards with the right subject pills', async ({
    page,
  }) => {
    await seedAuth(page);
    await stubHistory(page, FULL_LIST_PAYLOAD);
    await page.goto('/fr/history');
    await expect(
      page.getByRole('heading', { name: 'Mes conversations' }),
    ).toBeVisible();
    // Three cards rendered (one per data-testid).
    await expect(page.getByTestId(`history-item-${CONV_ID_MATHS}`)).toBeVisible();
    await expect(page.getByTestId(`history-item-${CONV_ID_FR}`)).toBeVisible();
    await expect(page.getByTestId(`history-item-${CONV_ID_MATHS_2}`)).toBeVisible();
    // The first_question is shown.
    await expect(
      page.getByText('Qu\'est-ce qu\'une dérivée ?').first(),
    ).toBeVisible();
    // The subject labels are rendered (via chat.subjectMaths / subjectFrancais).
    await expect(
      page.getByTestId(`history-subject-${CONV_ID_MATHS}`).getByText('Mathématiques'),
    ).toBeVisible();
    await expect(
      page.getByTestId(`history-subject-${CONV_ID_FR}`).getByText('Français'),
    ).toBeVisible();
  });

  test('(b) empty state with a CTA to /chat', async ({ page }) => {
    await seedAuth(page);
    await stubHistory(page, EMPTY_PAYLOAD);
    await page.goto('/fr/history');
    await expect(page.getByText("Tu n'as pas encore posé de question.")).toBeVisible();
    const cta = page.getByRole('link', { name: 'Démarrer une conversation' });
    await expect(cta).toBeVisible();
    await expect(cta).toHaveAttribute('href', '/fr/chat');
  });

  test('(c) pagination — Suivant button re-fetches with offset=2', async ({
    page,
  }) => {
    await seedAuth(page);
    // The stub returns 2 items with total=5 → Suivant is enabled
    // (offset+items.length=2 < total=5) and Précédent is disabled
    // (offset=0).
    let lastUrl: string | null = null;
    await page.route(/\/api\/chat\/history(\/|$|\?)/, (route) => {
      lastUrl = route.request().url();
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(PAGINATED_PAYLOAD),
      });
    });
    await page.goto('/fr/history');
    const next = page.getByTestId('history-next');
    const prev = page.getByTestId('history-prev');
    await expect(next).toBeEnabled();
    await expect(prev).toBeDisabled();
    // Click Suivant → the page re-fetches with offset=2.
    // The stub still returns the same payload (offset=0), so the
    // visible items don't change. We assert the new request URL
    // carries offset=2 — that's the proof the pagination state
    // advanced.
    const beforeUrl = lastUrl;
    await next.click();
    // Wait for the network round-trip to complete.
    await expect.poll(() => lastUrl).not.toBe(beforeUrl);
    expect(lastUrl).toContain('offset=2');
  });

  test('(d) clicking a card opens the detail page with the messages', async ({
    page,
  }) => {
    await seedAuth(page);
    // First stub the list, then the detail.
    await page.route(/\/api\/chat\/history(\/|$|\?)/, (route) => {
      const url = route.request().url();
      if (url.includes(CONV_ID_MATHS)) {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(DETAIL_PAYLOAD),
        });
      }
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(FULL_LIST_PAYLOAD),
      });
    });
    await page.goto('/fr/history');
    await page.getByTestId(`history-item-${CONV_ID_MATHS}`).click();
    await expect(page).toHaveURL(new RegExp(`/fr/history/${CONV_ID_MATHS}$`));
    // The detail header shows the first_question as the h1.
    const heading = page.getByRole('heading', { level: 1 });
    await expect(heading).toBeVisible();
    await expect(heading).toHaveText("Qu'est-ce qu'une dérivée ?");
    // The two messages are rendered in order.
    const messages = page.getByTestId(/^history-message-/);
    await expect(messages).toHaveCount(2);
    await expect(
      page.getByTestId('history-message-user').getByText("Qu'est-ce qu'une dérivée ?"),
    ).toBeVisible();
    await expect(
      page
        .getByTestId('history-message-assistant')
        .getByText('Une dérivée mesure la variation instantanée'),
    ).toBeVisible();
    // The two source pills are rendered.
    await expect(
      page.getByLabel('cours-derivees.pdf:3'),
    ).toBeVisible();
    await expect(
      page.getByLabel('cours-derivees.pdf:7'),
    ).toBeVisible();
  });

  test('(e) not-found on 404 — history.notFound + back button', async ({
    page,
  }) => {
    await seedAuth(page);
    await stubHistoryNotFound(page);
    await page.goto(`/fr/history/${CONV_ID_MATHS}`);
    // The 404 surfaces as a Card with role="alert" containing
    // the error404 translation. The first card to match is the
    // "404" Card (not the loading Card which has role="status").
    const errorCard = page.locator('[role="alert"]').first();
    await expect(errorCard).toBeVisible();
    await expect(errorCard).toContainText('Conversation introuvable.');
    const back = page.getByTestId('history-back');
    await expect(back).toBeVisible();
    await back.click();
    await expect(page).toHaveURL(/\/fr\/history$/);
  });

  test('(a11y fr) axe-core: no critical/serious on /fr/history', async ({
    page,
  }) => {
    await seedAuth(page);
    await stubHistory(page, FULL_LIST_PAYLOAD);
    await page.goto('/fr/history');
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

  test('(a11y en) axe-core: no critical/serious on /en/history/{id}', async ({
    page,
  }) => {
    await seedAuth(page);
    await page.route(/\/api\/chat\/history(\/|$|\?)/, (route) => {
      const url = route.request().url();
      if (url.includes(CONV_ID_MATHS)) {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(DETAIL_PAYLOAD),
        });
      }
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(FULL_LIST_PAYLOAD),
      });
    });
    await page.goto(`/en/history/${CONV_ID_MATHS}`);
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
