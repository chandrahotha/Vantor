import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

/** All 13 workspace routes in the sidebar nav, plus the account route — see
 *  `components/Shell.tsx`'s `NAV` array, which this list must track. */
const NAV_ROUTES: [label: string, href: string][] = [
  ['Dashboard', '/'],
  ['Suppliers', '/suppliers'],
  ['RFQs', '/rfqs'],
  ['Contracts', '/contracts'],
  ['Purchase orders', '/orders'],
  ['Requisitions', '/requisitions'],
  ['Approvals', '/approvals'],
  ['Negotiation simulator', '/negosim'],
  ['Spend', '/spend'],
  ['Documents', '/documents'],
  ['Governance', '/governance'],
  ['Integrations', '/integrations'],
  ['Copilot', '/copilot'],
  ['Alerts', '/notifications'],
];

test.describe('Vantor Web E2E Journey', () => {
  test.describe('sign-in screen (API reachable)', () => {
    // These assert on the screen a real deployment actually shows. The
    // previous version of this file waited for "Sign-in problem" — the error
    // state shown only when the API cannot be reached at all — so it never
    // once rendered, audited or screenshotted the real sign-in screen a user
    // sees on a working deployment.
    test('meets accessibility standards', async ({ page }) => {
      await page.goto('/');
      await expect(page.getByRole('button', { name: /log in to vantor/i })).toBeVisible({ timeout: 15_000 });

      const accessibilityScanResults = await new AxeBuilder({ page }).analyze();
      expect(accessibilityScanResults.violations).toEqual([]);
    });

    test('visual regression', async ({ page }) => {
      await page.goto('/');
      await expect(page.getByRole('button', { name: /log in to vantor/i })).toBeVisible({ timeout: 15_000 });

      await expect(page).toHaveScreenshot('signin-page.png', {
        maxDiffPixelRatio: 0.1,
      });
    });
  });

  test.describe('sign-in screen (API unreachable)', () => {
    // With no session yet, the gate always shows the normal button — it has
    // nothing to retry and nothing has failed yet (see `useBoot` in
    // components/ui.tsx). The failure surfaces the moment sign-in is actually
    // attempted, in place, rather than as a full-screen state up front.
    test('reports a failed sign-in attempt in place, not a blank screen', async ({ page }) => {
      await page.route('**/api/v1/**', (route) => route.abort());
      await page.goto('/');
      await expect(page.getByRole('button', { name: /log in to vantor/i })).toBeVisible({ timeout: 15_000 });
      await page.getByRole('button', { name: /log in to vantor/i }).click();
      await expect(page.locator('.authscreen-error-box')).toContainText(/could not reach the vantor api/i, { timeout: 15_000 });
    });
  });

  test.describe('authenticated journey', () => {
    test('signs in, reaches every nav route with no console errors, and survives a reload', async ({ page }) => {
      const consoleErrors: string[] = [];
      page.on('console', (msg) => { if (msg.type() === 'error') consoleErrors.push(`${msg.text()} (${page.url()})`); });
      page.on('pageerror', (err) => consoleErrors.push(`${err} (${page.url()})`));

      await page.goto('/');
      await expect(page.getByRole('button', { name: /log in to vantor/i })).toBeVisible({ timeout: 15_000 });
      await page.getByRole('button', { name: /log in to vantor/i }).click();
      await expect(page.locator('.userchip-card')).toBeVisible({ timeout: 15_000 });

      for (const [label, href] of NAV_ROUTES) {
        await test.step(`navigate to ${label} (${href})`, async () => {
          await page.getByRole('link', { name: label }).click();
          await expect(page).toHaveURL(new RegExp(`${href.replace('/', '\\/')}$`));
          // Every route gate renders through the same AuthScreen component, so
          // a session that silently dropped would show the sign-in screen
          // instead of the page — this is the one assertion that would catch
          // that on every single route, not just the first.
          await expect(page.getByRole('button', { name: /log in to vantor/i })).not.toBeVisible();
        });
      }

      await test.step('session survives a reload', async () => {
        await page.reload();
        await expect(page.locator('.userchip-card')).toBeVisible({ timeout: 15_000 });
        await expect(page.getByRole('button', { name: /log in to vantor/i })).not.toBeVisible();
      });

      expect(consoleErrors, `unexpected console/page errors:\n${consoleErrors.join('\n')}`).toEqual([]);
    });
  });
});
