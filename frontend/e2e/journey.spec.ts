import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

test.describe('Vantor Web E2E Journey', () => {
  test('sign-in page meets accessibility standards', async ({ page }) => {
    await page.goto('/');
    
    // Wait for the offline auth screen (since Keycloak is unreachable in this env)
    await page.waitForSelector('text="Sign-in problem"');

    // Run accessibility audit
    const accessibilityScanResults = await new AxeBuilder({ page }).analyze();
    expect(accessibilityScanResults.violations).toEqual([]);
  });

  test('sign-in page visual regression', async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('text="Sign-in problem"');
    
    // Check visual regression
    await expect(page).toHaveScreenshot('signin-page.png', {
      maxDiffPixelRatio: 0.1,
    });
  });
});
