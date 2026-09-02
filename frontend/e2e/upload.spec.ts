import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

/*
 * /upload page e2e (s11c).
 *
 * Covers the 5 behaviour tests + 2 a11y scans called out in the plan:
 *  - (a) renders with all controls and htmlFor; Envoyer disabled when
 *        pseudo is missing
 *  - (b) uploads a stubbed file successfully and shows the success
 *        card; inspects the FormData (3 fields: pseudo, subject, file)
 *  - (c) displays 413 error card on file too large
 *  - (d) displays 415 error card on unsupported extension — this is
 *        the AC9(b) vs AC9(a) discrimination test (same code
 *        "invalid_file", different HTTP status)
 *  - (e) displays 201 manual_review_needed as a warning card
 *  - (a11y fr) axe-core: 0 critical/serious on /fr/upload
 *  - (a11y en) axe-core: 0 critical/serious on /en/upload
 *
 * The pseudo is set via the <Header> input so the Send button is
 * enabled. Upload responses are stubbed via page.route (no backend).
 */

const VALID_PSEUDO = 'ali_baba';

async function setPseudo(page: import('@playwright/test').Page) {
  await page.goto('/fr/');
  const input = page.getByLabel('Ton pseudo');
  await input.fill(VALID_PSEUDO);
  await input.blur();
}

test.describe('Upload page', () => {
  test('(a) renders with all controls and htmlFor labels', async ({ page }) => {
    await setPseudo(page);
    await page.goto('/fr/upload');
    await expect(
      page.getByRole('heading', { name: 'Uploader un document' }),
    ).toBeVisible();
    const subject = page.getByLabel('Matière');
    await expect(subject).toBeVisible();
    await expect(subject).toHaveJSProperty('tagName', 'SELECT');
    // The drop zone is a <label htmlFor="upload-file">.
    const dropZone = page.locator('label[for="upload-file"]');
    await expect(dropZone).toBeVisible();
    // The send button is visible but disabled.
    const send = page.getByRole('button', { name: 'Envoyer' });
    await expect(send).toBeVisible();
    await expect(send).toHaveAttribute('aria-disabled', 'true');
  });

  test('(b) uploads a stubbed file successfully and shows the success card', async ({
    page,
  }) => {
    await setPseudo(page);
    await page.route('**/api/documents/upload', async (route) => {
      // The browser sends a multipart/form-data payload — axios injects
      // the boundary automatically. We assert the multipart body
      // contains the three fields we expect (pseudo, subject, file)
      // and their values. Playwright 1.49 doesn't expose parsed
      // formData on the route, so we inspect the raw body string.
      const body = route.request().postData() ?? '';
      expect(body).toContain('name="pseudo"');
      expect(body).toContain(VALID_PSEUDO);
      expect(body).toContain('name="subject"');
      expect(body).toContain('maths');
      expect(body).toContain('name="file"');
      expect(body).toContain('cours.pdf');
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify({
          document_id: 'doc-1',
          status: 'indexed',
          chunks_count: 12,
          ocr_confidence: null,
        }),
      });
    });
    await page.goto('/fr/upload');
    await page.getByLabel('Matière').selectOption('maths');
    await page
      .locator('input#upload-file')
      .setInputFiles({
        name: 'cours.pdf',
        mimeType: 'application/pdf',
        buffer: Buffer.from('%PDF-1.4 fake'),
      });
    await page.getByRole('button', { name: 'Envoyer' }).click();
    // Success card.
    await expect(
      page.getByText('Document indexé : cours.pdf (12 chunks)'),
    ).toBeVisible();
    await expect(
      page.getByRole('button', { name: 'Uploader un autre document' }),
    ).toBeVisible();
  });

  test('(c) displays 413 error card on file too large', async ({ page }) => {
    await setPseudo(page);
    await page.route('**/api/documents/upload', async (route) => {
      await route.fulfill({
        status: 413,
        contentType: 'application/json',
        body: JSON.stringify({
          error: 'Fichier trop volumineux.',
          code: 'invalid_file',
        }),
      });
    });
    await page.goto('/fr/upload');
    await page.getByLabel('Matière').selectOption('maths');
    await page
      .locator('input#upload-file')
      .setInputFiles({
        name: 'big.pdf',
        mimeType: 'application/pdf',
        buffer: Buffer.from('%PDF-1.4'),
      });
    await page.getByRole('button', { name: 'Envoyer' }).click();
    await expect(
      page.getByText('Fichier trop volumineux (max 20 MB).'),
    ).toBeVisible();
    // The machine code is rendered.
    await expect(page.getByText(/Code\s*:\s*invalid_file/)).toBeVisible();
    // The retry button is visible.
    await expect(page.getByRole('button', { name: 'Réessayer' })).toBeVisible();
  });

  test('(d) displays 415 error card on unsupported extension (AC9(b))', async ({
    page,
  }) => {
    await setPseudo(page);
    await page.route('**/api/documents/upload', async (route) => {
      await route.fulfill({
        status: 415,
        contentType: 'application/json',
        body: JSON.stringify({
          error: 'Extension .docx non supportée.',
          code: 'invalid_file',
        }),
      });
    });
    await page.goto('/fr/upload');
    await page.getByLabel('Matière').selectOption('maths');
    // Force a .docx even though the picker only allows the supported
    // set: setInputFiles bypasses the accept filter.
    await page
      .locator('input#upload-file')
      .setInputFiles({
        name: 'bad.docx',
        mimeType: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        buffer: Buffer.from('fake'),
      });
    await page.getByRole('button', { name: 'Envoyer' }).click();
    // The 415 message is the AC9(b) one — NOT the 413 "trop volumineux".
    await expect(
      page.getByText('Extension non supportée. Formats acceptés : PDF, image, texte.'),
    ).toBeVisible();
    // The code is still invalid_file but the message differs from 413.
    await expect(page.getByText(/Code\s*:\s*invalid_file/)).toBeVisible();
  });

  test('(e) displays 201 manual_review_needed as a warning card', async ({
    page,
  }) => {
    await setPseudo(page);
    await page.route('**/api/documents/upload', async (route) => {
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify({
          document_id: 'doc-2',
          status: 'manual_review_needed',
          chunks_count: 0,
          ocr_confidence: 0.3,
        }),
      });
    });
    await page.goto('/fr/upload');
    await page.getByLabel('Matière').selectOption('maths');
    await page
      .locator('input#upload-file')
      .setInputFiles({
        name: 'scan.pdf',
        mimeType: 'application/pdf',
        buffer: Buffer.from('%PDF-1.4'),
      });
    await page.getByRole('button', { name: 'Envoyer' }).click();
    await expect(
      page.getByText(/OCR est peu fiable/),
    ).toBeVisible();
    await expect(
      page.getByRole('button', { name: 'Uploader un autre document' }),
    ).toBeVisible();
  });

  test('axe-core: no critical or serious violations on /fr/upload', async ({
    page,
  }) => {
    await setPseudo(page);
    await page.goto('/fr/upload');
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

  test('axe-core: no critical or serious violations on /en/upload', async ({
    page,
  }) => {
    await setPseudo(page);
    await page.goto('/en/upload');
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
