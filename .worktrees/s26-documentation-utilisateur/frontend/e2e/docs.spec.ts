import { test, expect } from '@playwright/test';

test.describe('Documentation links', () => {
  test('all internal anchors resolve to existing headings on /docs', async ({ page }) => {
    await page.goto('/fr/docs');
    await page.waitForSelector('nav[aria-label*="Navigation"]');

    const links = await page.locator('nav a[href^="#"]').all();
    const anchors: string[] = [];
    for (const link of links) {
      const href = await link.getAttribute('href');
      if (href && href.startsWith('#')) {
        anchors.push(href);
      }
    }

    const headings: string[] = [];
    const headingIds = await page.locator('article h3[id]').all();
    for (const h of headingIds) {
      const id = await h.getAttribute('id');
      if (id) headings.push(`#${id}`);
    }

    for (const anchor of anchors) {
      expect(headings, `Anchor ${anchor} missing heading`).toContain(anchor);
    }
  });

  test('/docs page renders with navigation and content in FR and EN', async ({ page }) => {
    await page.goto('/fr/docs');
    await expect(page.locator('h1')).toContainText('Guide utilisateur');
    await expect(page.locator('nav a[href="#creer-compte"]')).toBeVisible();

    await page.goto('/en/docs');
    await expect(page.locator('h1')).toContainText('User Guide');
  });
});
