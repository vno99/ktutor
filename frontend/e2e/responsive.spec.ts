import { test, expect } from '@playwright/test';

/*
 * Responsive e2e (s11a).
 *
 * - 360px viewport: no horizontal scroll.
 * - 768px viewport: CTAs are side-by-side (sm:flex-row), not stacked.
 *
 * The home page is the only page in s11a; chat/upload are gated by s11b/s11c.
 */
test.describe('Home page responsive', () => {
  test('no horizontal scroll at 360px', async ({ page }) => {
    await page.setViewportSize({ width: 360, height: 720 });
    await page.goto('/fr/');
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow, 'unexpected horizontal scroll on 360px').toBeLessThanOrEqual(1);
  });

  test('CTAs are side-by-side at 768px', async ({ page }) => {
    await page.setViewportSize({ width: 768, height: 1024 });
    await page.goto('/fr/');
    const chatCta = page.getByRole('link', { name: 'Commencer à chatter' });
    const uploadCta = page.getByRole('link', { name: 'Uploader un document' });
    const chatBox = await chatCta.boundingBox();
    const uploadBox = await uploadCta.boundingBox();
    expect(chatBox, 'chat CTA has no box').not.toBeNull();
    expect(uploadBox, 'upload CTA has no box').not.toBeNull();
    // Side-by-side means the CTAs share the same vertical band.
    const sameRow =
      Math.abs((chatBox?.y ?? 0) - (uploadBox?.y ?? 0)) < 4 &&
      (chatBox?.x ?? 0) !== (uploadBox?.x ?? 0);
    expect(sameRow, `CTAs not side-by-side: chat=${JSON.stringify(chatBox)} upload=${JSON.stringify(uploadBox)}`).toBe(true);
  });
});
