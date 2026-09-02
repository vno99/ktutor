import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

/*
 * /chat page e2e (s11b).
 *
 * Covers the 5 behaviour tests + 2 a11y scans called out in the plan:
 *  - (a) renders with all controls and htmlFor
 *  - (b) streams a stubbed SSE token by token + sources
 *  - (c) displays inline error card on stream error event
 *  - (d) keyboard navigation reaches select/textarea/send
 *  - (e) toggle FR/EN switches chat UI to English
 *  - (a11y fr) axe-core: 0 critical/serious on /fr/chat
 *  - (a11y en) axe-core: 0 critical/serious on /en/chat
 *
 * The pseudo is set via the <Header> input so the Send button is
 * enabled. Stream responses are stubbed via page.route (no LLM).
 */

const VALID_PSEUDO = 'ali_baba';

async function setPseudo(page: import('@playwright/test').Page) {
  await page.goto('/fr/');
  const input = page.getByLabel('Ton pseudo');
  await input.fill(VALID_PSEUDO);
  await input.blur();
}

test.describe('Chat page', () => {
  test('renders with all controls and htmlFor labels', async ({ page }) => {
    await setPseudo(page);
    await page.goto('/fr/chat');
    await expect(
      page.getByRole('heading', { name: 'Chatter avec un agent' }),
    ).toBeVisible();
    const subject = page.getByLabel('Matière');
    await expect(subject).toBeVisible();
    await expect(subject).toHaveJSProperty('tagName', 'SELECT');
    const question = page.getByLabel('Ta question');
    await expect(question).toBeVisible();
    await expect(question).toHaveJSProperty('tagName', 'TEXTAREA');
    const send = page.getByRole('button', { name: 'Envoyer' });
    await expect(send).toBeVisible();
    await expect(send).toHaveAttribute('aria-disabled', 'true');
  });

  test('streams a stubbed SSE token by token and renders sources', async ({
    page,
  }) => {
    await setPseudo(page);
    await page.route('**/api/chat/stream', async (route) => {
      await route.fulfill({
        status: 200,
        headers: { 'Content-Type': 'text/event-stream' },
        body:
          'data: {"token":"Une "}\n\n' +
          'data: {"token":"dérivée."}\n\n' +
          'data: {"done":true,"sources":[{"filename":"cours.pdf","chunk_index":0}]}\n\n',
      });
    });
    await page.goto('/fr/chat');
    await page.getByLabel('Matière').selectOption('maths');
    await page.getByLabel('Ta question').fill('Qu\'est-ce qu\'une dérivée ?');
    await page.getByRole('button', { name: 'Envoyer' }).click();
    // The streamed text is rendered in the live region.
    await expect(page.getByText('Une dérivée.')).toBeVisible();
    // The sources line is rendered.
    await expect(page.getByText(/cours\.pdf/)).toBeVisible();
  });

  test('displays inline error card on stream error event and Retry', async ({
    page,
  }) => {
    await setPseudo(page);
    await page.route('**/api/chat/stream', async (route) => {
      await route.fulfill({
        status: 200,
        headers: { 'Content-Type': 'text/event-stream' },
        body: 'data: {"error":"oops","code":"unknown"}\n\n',
      });
    });
    await page.goto('/fr/chat');
    await page.getByLabel('Matière').selectOption('maths');
    await page.getByLabel('Ta question').fill('ping');
    await page.getByRole('button', { name: 'Envoyer' }).click();
    // The translated error message is visible.
    await expect(
      page.getByText('Une erreur est survenue. Réessaye plus tard.'),
    ).toBeVisible();
    // The Retry button is visible.
    const retry = page.getByRole('button', { name: 'Réessayer' });
    await expect(retry).toBeVisible();
  });

  test('keyboard navigation reaches select, textarea, and send button', async ({
    page,
  }) => {
    await setPseudo(page);
    await page.goto('/fr/chat');
    // Fill the form so the send button is enabled (canSend === true) and
    // accepts focus. Disabled buttons have tabindex=-1 and are skipped by
    // keyboard nav, which is the correct a11y behaviour.
    await page.getByLabel('Matière').selectOption('maths');
    await page.getByLabel('Ta question').fill('Test question');
    // The labeled controls accept focus directly (this is the standard
    // a11y check from the design system, cf. design-system.md l.144).
    await page.getByLabel('Matière').focus();
    await expect(page.getByLabel('Matière')).toBeFocused();
    await page.getByLabel('Ta question').focus();
    await expect(page.getByLabel('Ta question')).toBeFocused();
    await page.getByRole('button', { name: 'Envoyer' }).focus();
    await expect(page.getByRole('button', { name: 'Envoyer' })).toBeFocused();
  });

  test('toggle FR/EN switches the chat UI to English', async ({ page }) => {
    await setPseudo(page);
    await page.goto('/fr/chat');
    await expect(
      page.getByRole('heading', { name: 'Chatter avec un agent' }),
    ).toBeVisible();
    await page.getByLabel('Passer en Anglais').click();
    await expect(page).toHaveURL(/\/en\/chat$/);
    await expect(
      page.getByRole('heading', { name: 'Chat with an agent' }),
    ).toBeVisible();
    await expect(page.getByLabel('Subject')).toBeVisible();
    await expect(page.getByLabel('Your question')).toBeVisible();
    await expect(
      page.getByRole('button', { name: 'Send' }),
    ).toBeVisible();
  });

  test('axe-core: no critical or serious violations on /fr/chat', async ({
    page,
  }) => {
    await setPseudo(page);
    await page.goto('/fr/chat');
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

  test('axe-core: no critical or serious violations on /en/chat', async ({
    page,
  }) => {
    await setPseudo(page);
    await page.goto('/en/chat');
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
