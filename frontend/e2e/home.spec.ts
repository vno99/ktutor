import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

/*
 * Home page e2e (s11a).
 *
 * - `redirect / → /fr/`: next-intl middleware must rewrite the root URL.
 * - `home renders in French by default`: title is in French.
 * - `toggle to English works and persists`: clicking EN rewrites the URL
 *   to /en/ and the title switches.
 * - `CTAs are visible and clickable`: both buttons are present and have
 *   hrefs to /chat and /upload.
 * - `axe-core: 0 critical violation on home`: the design system has zero
 *   critical or serious axe violations on the rendered page.
 */
test.describe('Home page', () => {
  test('redirects / to /fr/', async ({ page }) => {
    const response = await page.goto('/', { waitUntil: 'domcontentloaded' });
    expect(response, 'no response on /').not.toBeNull();
    expect(page.url()).toMatch(/\/fr\/?$/);
  });

  test('renders in French by default', async ({ page }) => {
    await page.goto('/fr/');
    await expect(
      page.getByRole('heading', { name: 'Bienvenue sur ktutor' }),
    ).toBeVisible();
  });

  test('toggle to English works and persists', async ({ page }) => {
    await page.goto('/fr/');
    // The EN pill: accessible name is the locale-aware aria-label
    // ("Passer en Anglais" in French). Match the EN button by its label.
    await page.getByLabel('Passer en Anglais').click();
    await expect(page).toHaveURL(/\/en\/?$/);
    await expect(
      page.getByRole('heading', { name: 'Welcome to ktutor' }),
    ).toBeVisible();
  });

  test('CTAs are visible and clickable', async ({ page }) => {
    await page.goto('/fr/');
    const chatCta = page.getByRole('link', { name: 'Commencer à chatter' });
    const uploadCta = page.getByRole('link', { name: 'Uploader un document' });
    await expect(chatCta).toBeVisible();
    // Link from @/i18n/navigation renders the locale prefix in the
    // actual `href` attribute; on /fr/ this is `/fr/chat`. The link is
    // still "the chat link" semantically.
    await expect(chatCta).toHaveAttribute('href', '/fr/chat');
    await expect(uploadCta).toBeVisible();
    await expect(uploadCta).toHaveAttribute('href', '/fr/upload');
  });

  test('axe-core: no critical or serious violations on home', async ({ page }) => {
    await page.goto('/fr/');
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
