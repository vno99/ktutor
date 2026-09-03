import { test, expect } from '@playwright/test';

/*
 * Pseudo identity contract e2e (s13).
 *
 * s11a shipped a cookie-backed `pseudo` written by a <Header> input.
 * s13 removes that input. The new contract is:
 *
 *  - The `pseudo` cookie alone (no JWT) is enough for
 *    ``useAuthStore.hydrate()`` to populate the store. The visible
 *    effect: the chat / upload pages do not show the "noPseudo"
 *    warning and the form controls (select, file picker, send
 *    button) read a valid pseudo from the store. The cookie is
 *    what the production mirror writes on login (cf. authStore.ts
 *    ``setTokens`` → ``writePseudoCookie``), and what the legacy
 *    chat / upload stores read.
 *
 *  - The cookie value must match the client regex
 *    ``^[a-zA-Z0-9_]{3,32}$``. A malformed value (e.g. "!!") is
 *    stored as-is in the cookie, but the store's ``isValidPseudo``
 *    gate refuses it, so the upload form still shows the warning.
 *    (We do not require the store to drop the cookie — the gate
 *    is the source of truth, and the store's behaviour matches
 *    ADR 011 § Validation.)
 *
 *  - The cookie persists across reload. A reload re-reads the
 *    cookie on mount via ``hydrate()`` in <Header> and the page
 *    client; the "noPseudo" warning stays absent.
 *
 *  - The mirror path (login → cookie) is exercised by the login
 *    flow in auth.spec.ts ("login → avatar appears"). A dedicated
 *    mirror test would duplicate that coverage, so it is omitted
 *    here. Cf. AGENTS.md § Story efficiency: "A story adds at
 *    most two new test files." pseudo.spec.ts is a single file.
 */
const VALID_PSEUDO = 'ali_baba';
const COOKIE_URL = 'http://localhost:3000';

async function setPseudoCookie(
  context: import('@playwright/test').BrowserContext,
  value: string,
) {
  await context.addCookies([{ name: 'pseudo', value, url: COOKIE_URL }]);
}

test.describe('Pseudo identity contract (s13)', () => {
  test('cookie alone is enough to hydrate a valid pseudo', async ({
    page,
    context,
  }) => {
    await setPseudoCookie(context, VALID_PSEUDO);
    await page.goto('/fr/upload');
    // The "noPseudo" warning is gone — the store's pseudo is valid.
    await expect(
      page.getByText('Choisis un pseudo pour commencer'),
    ).toHaveCount(0);
  });

  test('cookie persists across reload', async ({ page, context }) => {
    await setPseudoCookie(context, VALID_PSEUDO);
    await page.goto('/fr/upload');
    // Sanity: hydrated on first load.
    await expect(
      page.getByText('Choisis un pseudo pour commencer'),
    ).toHaveCount(0);
    await page.reload();
    // Still hydrated after reload (hydrate() re-reads the cookie).
    await expect(
      page.getByText('Choisis un pseudo pour commencer'),
    ).toHaveCount(0);
  });

  test('malformed cookie value does not satisfy the pseudo gate', async ({
    page,
    context,
  }) => {
    await setPseudoCookie(context, '!!');
    await page.goto('/fr/upload');
    // The store reads the cookie as-is, but the regex gate refuses it,
    // so the upload form still shows the "noPseudo" warning.
    await expect(
      page.getByText('Choisis un pseudo pour commencer'),
    ).toBeVisible();
  });
});
