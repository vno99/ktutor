// Playwright snapshot script for documentation — s26
// Usage: npx playwright test frontend/e2e/docs.spec.ts --project=chromium
// Screenshots are saved to docs/user-guide/assets/ when the test passes.

import { test, expect } from '@playwright/test';
import { existsSync, mkdirSync } from 'fs';
import path from 'path';

const assetsDir = path.resolve(__dirname, '../../docs/user-guide/assets');

test('snapshots of key pages for user guide', async ({ page }) => {
  if (!existsSync(assetsDir)) mkdirSync(assetsDir, { recursive: true });

  const pages = ['/fr/', '/fr/chat', '/fr/upload', '/dashboard/eleve'];
  for (const p of pages) {
    try {
      await page.goto(p);
      await page.waitForLoadState('networkidle');
      const safeName = p.replace(/[^a-zA-Z0-9]/g, '_').replace(/^_+/, '').slice(0, 30);
      await page.screenshot({ path: `${assetsDir}/${safeName}.png`, fullPage: true });
    } catch (e) {
      console.warn(`Snapshot failed for ${p}: ${e}`);
    }
  }
});
