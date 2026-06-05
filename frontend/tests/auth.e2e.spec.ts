import { test, expect } from '@playwright/test';

const BASE = process.env.PLAYWRIGHT_BASE_URL ?? 'http://localhost:3001';

test('signup → login → access protected → logout', async ({ page }) => {
  const email = `playwright+${Date.now()}@example.com`;
  const password = 'StrongPass!23';

  // Signup
  await page.goto(`${BASE}/signup`);
  await page.fill('input[type="email"]', email);
  await page.fill('input[type="password"]', password);
  await page.click('button:has-text("Sign Up")');
  await page.waitForURL('**/app/**', { timeout: 10000 });
  expect(page.url()).toContain('/app');

  // Logout
  await page.click('button:has-text("Logout")');
  await page.waitForURL('**/login', { timeout: 10000 });
  expect(page.url()).toContain('/login');

  // Login
  await page.goto(`${BASE}/login`);
  await page.fill('input[type="email"]', email);
  await page.fill('input[type="password"]', password);
  await page.click('button:has-text("Sign In")');
  await page.waitForURL('**/app/**', { timeout: 10000 });
  expect(page.url()).toContain('/app');
});
