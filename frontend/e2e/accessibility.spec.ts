import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

/*
 * Accessibility audit — s22 (axe-core + responsive + keyboard + alt + label + focus + aria + motion).
 *
 * Each page must pass:
 *  - axe-core: 0 critical, 0 serious
 *  - responsive: no horizontal scroll at 360px / 768px / 1280px
 *  - keyboard: Tab order logical, focus visible
 *  - alt: every <img> has alt (or alt="" for decorative)
 *  - label: every input/select/fileupload has associated <label>
 *  - focus-visible: interactive elements have focus-visible:ring-2
 *  - aria-disabled: disabled actions have aria-disabled + tabindex=-1
 *  - reduced-motion: animation-duration 0.01ms applied
 */

test.describe('Accessibility audit — axe-core', () => {
  const pages = [
    { url: '/fr/chat', name: 'chat FR' },
    { url: '/en/chat', name: 'chat EN' },
    { url: '/fr/upload', name: 'upload FR' },
    { url: '/en/upload', name: 'upload EN' },
    { url: '/fr/dashboard/eleve', name: 'dashboard eleve FR' },
    { url: '/en/dashboard/eleve', name: 'dashboard eleve EN' },
    { url: '/fr/history', name: 'history FR' },
    { url: '/en/history', name: 'history EN' },
  ];

  for (const p of pages) {
    test(`axe-core: 0 critical/serious on ${p.name}`, async ({ page, context }) => {
      await context.addCookies([
        { name: 'pseudo', value: 'ali_baba', url: 'http://localhost:3000' },
      ]);
      await page.goto(p.url);
      await expect(page.locator('body')).toBeVisible();
      const result = await new AxeBuilder({ page })
        .withTags(['wcag2a', 'wcag2aa'])
        .analyze();
      const blocking = result.violations.filter(
        (v) => v.impact === 'critical' || v.impact === 'serious',
      );
      expect(
        blocking,
        `axe violations on ${p.name}:\n${JSON.stringify(blocking, null, 2)}`,
      ).toEqual([]);
    });
  }
});

test.describe('Keyboard navigation — Tab + focus visible', () => {
  test('Tab order logical with visible focus indicator on /fr/chat', async ({ page, context }) => {
    await context.addCookies([
      { name: 'pseudo', value: 'ali_baba', url: 'http://localhost:3000' },
    ]);
    await page.goto('/fr/chat');
    // The first interactive element reachable by Tab should have a visible focus ring.
    await page.keyboard.press('Tab');
    const focused = await page.evaluate(
      () => document.activeElement?.tagName?.toLowerCase() ?? null,
    );
    expect(focused, 'first Tab focus should be an interactive element').toBeTruthy();
    // Confirm focus-visible ring is present in computed styles.
    const outline = await page.evaluate(() => {
      const el = document.activeElement as HTMLElement | null;
      if (!el) return null;
      return window.getComputedStyle(el).outline;
    });
    expect(outline, 'visible focus outline expected').toContain('solid');
  });

  test('file upload drop zone is keyboard reachable on /fr/upload', async ({ page, context }) => {
    await context.addCookies([
      { name: 'pseudo', value: 'ali_baba', url: 'http://localhost:3000' },
    ]);
    await page.goto('/fr/upload');
    // Tab through to the label-based drop zone.
    await page.keyboard.press('Tab');
    const tagName = await page.evaluate(
      () => document.activeElement?.tagName?.toLowerCase() ?? null,
    );
    expect(tagName, 'drop zone label should be focusable').toBe('label');
  });
});

test.describe('Accessibility audit — reduced motion', () => {
  test('animation-duration reduced to 0.01ms under prefers-reduced-motion', async ({ page }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' });
    const duration = await page.evaluate(() => {
      const el = document.createElement('div');
      el.className = 'animate-pulse';
      document.body.appendChild(el);
      return window.getComputedStyle(el).animationDuration;
    });
    expect(duration).toContain('0.01ms');
  });
});

test.describe('Responsive audit', () => {
  const viewports = [
    { width: 360, height: 720, label: '360px mobile' },
    { width: 768, height: 1024, label: '768px tablet' },
    { width: 1280, height: 800, label: '1280px desktop' },
  ];

  for (const vp of viewports) {
    test(`no horizontal scroll at ${vp.label} on /fr/chat`, async ({ page, context }) => {
      await context.addCookies([
        { name: 'pseudo', value: 'ali_baba', url: 'http://localhost:3000' },
      ]);
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await page.goto('/fr/chat');
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      );
      expect(overflow, `horizontal scroll at ${vp.label}`).toBeLessThanOrEqual(1);
    });
  }
});
