import { test, expect } from '@playwright/test';

const VALID_PSEUDO = 'ali_baba';

async function setPseudo(
  _page: import('@playwright/test').Page,
  context: import('@playwright/test').BrowserContext,
) {
  await context.addCookies([
    {
      name: 'pseudo',
      value: VALID_PSEUDO,
      url: 'http://localhost:3000',
    },
  ]);
}

test.describe('i18n toggle', () => {
  test('toggle EN on chat translates visible strings', async ({
    page,
    context,
  }) => {
    await setPseudo(page, context);
    await page.goto('/fr/chat');
    // Verify French title
    await expect(
      page.getByRole('heading', { name: 'Chatter avec un agent' }),
    ).toBeVisible();

    // Click EN in LanguageSwitcher
    await page.getByLabel('Passer en Anglais').click();

    // URL should be /en/chat
    await expect(page).toHaveURL(/\/en\/chat$/);

    // Title should be in English
    await expect(
      page.getByRole('heading', { name: 'Chat with an agent' }),
    ).toBeVisible();

    // Labels should be translated
    await expect(page.getByLabel('Subject')).toBeVisible();
    await expect(page.getByLabel('Your question')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Send' })).toBeVisible();
  });

  test('cookie NEXT_LOCALE=en persists after reload', async ({
    page,
    context,
  }) => {
    await setPseudo(page, context);
    await page.goto('/fr/chat');
    await page.getByLabel('Passer en Anglais').click();
    await expect(page).toHaveURL(/\/en\/chat$/);

    // Check cookie
    const cookies = await context.cookies();
    const localeCookie = cookies.find(
      (c) => c.name === 'NEXT_LOCALE',
    );
    expect(localeCookie).toBeDefined();
    expect(localeCookie?.value).toBe('en');

    // Reload and verify still EN
    await page.reload();
    await expect(page).toHaveURL(/\/en\/chat$/);
    await expect(
      page.getByRole('heading', { name: 'Chat with an agent' }),
    ).toBeVisible();
  });
});
