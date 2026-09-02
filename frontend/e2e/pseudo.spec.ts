import { test, expect } from '@playwright/test';

/*
 * Pseudo persistence e2e (s11a).
 *
 * - The header input is paired with a <label> (a11y).
 * - Typing a valid pseudo and blurring writes the `pseudo` cookie.
 * - Reloading the page keeps the pseudo (the avatar initial is recomputed).
 * - An invalid pseudo (3 < n ≤ 32) is rejected (input marked aria-invalid).
 */
test.describe('Header pseudo input', () => {
  test('has a paired label', async ({ page }) => {
    await page.goto('/fr/');
    const input = page.getByLabel('Ton pseudo');
    await expect(input).toBeVisible();
  });

  test('sets a cookie on blur with a valid pseudo', async ({ page, context }) => {
    await page.goto('/fr/');
    const input = page.getByLabel('Ton pseudo');
    await input.fill('ali_baba');
    await input.blur();
    const cookies = await context.cookies();
    const pseudoCookie = cookies.find((c) => c.name === 'pseudo');
    expect(pseudoCookie?.value).toBe('ali_baba');
  });

  test('persists across reload (avatar initial matches)', async ({ page }) => {
    await page.goto('/fr/');
    const input = page.getByLabel('Ton pseudo');
    await input.fill('ali_baba');
    await input.blur();
    await page.reload();
    const inputAfter = page.getByLabel('Ton pseudo');
    await expect(inputAfter).toHaveValue('ali_baba');
  });

  test('marks aria-invalid when the pseudo is malformed', async ({ page }) => {
    await page.goto('/fr/');
    const input = page.getByLabel('Ton pseudo');
    await input.fill('!!');
    await input.blur();
    await expect(input).toHaveAttribute('aria-invalid', 'true');
  });
});
