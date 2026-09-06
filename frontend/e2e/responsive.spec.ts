import { test, expect } from '@playwright/test';

/*
 * Responsive e2e — s22 (360px / 768px / 1280px).
 *
 * All 4 pages must render without horizontal scroll at each viewport.
 * Bottom tab bar visible at ≤768px; header sticky 56px preserved.
 */

test.describe('Responsive audit — 360px mobile', () => {
  const urls = [
    '/fr/chat', '/en/chat',
    '/fr/upload', '/en/upload',
    '/fr/dashboard/eleve', '/en/dashboard/eleve',
    '/fr/history', '/en/history',
  ];
  for (const url of urls) {
    test(`no horizontal scroll at 360px — ${url}`, async ({ page, context }) => {
      await context.addCookies([
        { name: 'pseudo', value: 'ali_baba', url: 'http://localhost:3000' },
      ]);
      await page.setViewportSize({ width: 360, height: 720 });
      await page.goto(url);
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      );
      expect(overflow, `horizontal scroll at 360px for ${url}`).toBeLessThanOrEqual(1);
    });
  }
});

test.describe('Responsive audit — 768px tablet', () => {
  const urls = [
    '/fr/chat', '/en/chat',
    '/fr/upload', '/en/upload',
    '/fr/dashboard/eleve', '/en/dashboard/eleve',
    '/fr/history', '/en/history',
  ];
  for (const url of urls) {
    test(`no horizontal scroll at 768px — ${url}`, async ({ page, context }) => {
      await context.addCookies([
        { name: 'pseudo', value: 'ali_baba', url: 'http://localhost:3000' },
      ]);
      await page.setViewportSize({ width: 768, height: 1024 });
      await page.goto(url);
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      );
      expect(overflow, `horizontal scroll at 768px for ${url}`).toBeLessThanOrEqual(1);
    });
  }
});

test.describe('Responsive audit — 1280px desktop', () => {
  const urls = [
    '/fr/chat', '/en/chat',
    '/fr/upload', '/en/upload',
    '/fr/dashboard/eleve', '/en/dashboard/eleve',
    '/fr/history', '/en/history',
  ];
  for (const url of urls) {
    test(`no horizontal scroll at 1280px — ${url}`, async ({ page, context }) => {
      await context.addCookies([
        { name: 'pseudo', value: 'ali_baba', url: 'http://localhost:3000' },
      ]);
      await page.setViewportSize({ width: 1280, height: 800 });
      await page.goto(url);
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      );
      expect(overflow, `horizontal scroll at 1280px for ${url}`).toBeLessThanOrEqual(1);
    });
  }
});
