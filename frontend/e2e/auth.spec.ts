import { test, expect, type Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

/*
 * Auth e2e (s13).
 *
 * Covers the nominal Header-affordance transitions and one a11y
 * scan on /login. The Header replaces the legacy pseudo input
 * with an avatar + <details> menu when a JWT is present, and a
 * "Se connecter" link when it is not (cf. task 14 / Header.tsx).
 *
 * The flow:
 *  (a) Cold visit on /fr/ → "Se connecter" visible, no avatar.
 *  (b) Click "Se connecter" → land on /fr/login, see the form.
 *  (c) Submit valid credentials (stubbed POST /api/auth/login) →
 *      redirect to /fr/chat, avatar visible, no "Se connecter".
 *  (d) Open the avatar menu → see "Mon espace" + "Se déconnecter".
 *  (e) Click "Se déconnecter" (stubbed 204) → back to (a).
 *
 * Network stubs: we mock POST /api/auth/login to return a fake
 * token pair, and POST /api/auth/logout to return 204. Real
 * cryptography is out of scope for this e2e (it would require
 * the backend up + the right env). The shape of the assertions
 * (avatar present, "Se connecter" absent) is what we verify.
 *
 * The a11y scan is on /fr/login only — /register follows the
 * same pattern, and a separate scan would be redundant for the
 * design-system guard (the same components are used).
 */

const LOGIN_PAYLOAD = {
  access_token: 'fake.access.token',
  refresh_token: 'fake.refresh.token',
  expires_in: 1800,
  role: 'eleve',
  pseudo: 'ali',
};

async function stubLogin(page: Page) {
  await page.route('**/api/auth/login', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(LOGIN_PAYLOAD),
    }),
  );
}

async function stubLogout(page: Page) {
  await page.route('**/api/auth/logout', (route) =>
    route.fulfill({ status: 204, body: '' }),
  );
}

test.describe('Auth header affordance (s13)', () => {
  test('shows the "Se connecter" CTA when not authenticated', async ({ page }) => {
    await page.goto('/fr/');
    const cta = page.getByRole('link', { name: 'Se connecter' });
    await expect(cta).toBeVisible();
    await expect(page.getByRole('button', { name: /avatar de/i })).toHaveCount(0);
  });

  test('navigates to /login when the CTA is clicked', async ({ page }) => {
    await page.goto('/fr/');
    await page.getByRole('link', { name: 'Se connecter' }).click();
    await expect(page).toHaveURL(/\/fr\/login$/);
    await expect(
      page.getByRole('heading', { name: 'Se connecter' }),
    ).toBeVisible();
  });

  test('login → avatar appears, "Se connecter" disappears', async ({ page }) => {
    await stubLogin(page);
    await page.goto('/fr/login');
    await page.getByLabel('Pseudo').fill('ali');
    await page.getByLabel('Mot de passe').fill('some-password');
    await page.getByRole('button', { name: 'Se connecter' }).click();
    // The CTA "Se connecter" in the Header is no longer visible.
    await expect(page.getByRole('link', { name: 'Se connecter' })).toHaveCount(0);
    // The avatar summary is now present.
    await expect(page.getByRole('button', { name: /avatar de ali/i })).toBeVisible();
  });

  test('avatar menu exposes logout, which clears the avatar', async ({ page }) => {
    await stubLogin(page);
    await stubLogout(page);
    await page.goto('/fr/login');
    await page.getByLabel('Pseudo').fill('ali');
    await page.getByLabel('Mot de passe').fill('some-password');
    await page.getByRole('button', { name: 'Se connecter' }).click();
    const avatar = page.getByRole('button', { name: /avatar de ali/i });
    await expect(avatar).toBeVisible();
    // Open the native <details> menu and click "Se déconnecter".
    await avatar.click();
    await page.getByRole('menuitem', { name: 'Se déconnecter' }).click();
    // After logout, the "Se connecter" CTA is back.
    await expect(page.getByRole('link', { name: 'Se connecter' })).toBeVisible();
  });
});

test.describe('Auth a11y (s13)', () => {
  test('login page has no critical/serious axe violations', async ({ page }) => {
    await page.goto('/fr/login');
    const results = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa'])
      .analyze();
    const critical = results.violations.filter(
      (v) => v.impact === 'critical' || v.impact === 'serious',
    );
    expect(critical, JSON.stringify(critical, null, 2)).toEqual([]);
  });
});
