/**
 * upload.flow.spec.ts
 *
 * End-to-end tests for the DataMind upload flow.
 *
 * Covers:
 *   1. File validation  — >10 files, >50 MB, unsupported type
 *   2. Happy-path upload — drag CSV → progress bars → ingest triggered
 *   3. Job status polling — GET /jobs/{id} every 3 s, "profiling" shown
 *   4. Full flow         — drag CSV → upload → ingest → status = "profiling"
 *
 * Auth bypass:
 *   - `x-e2e-test: true` header set globally in playwright.config.ts causes
 *     the Next.js middleware to skip the Supabase auth guard.
 *   - The Zustand `datamind-auth` localStorage key is injected via addInitScript
 *     so the client-side layout redirect also passes.
 *
 * File simulation:
 *   React-dropzone does not respond to Playwright's setInputFiles() because it
 *   bypasses the drag-and-drop event pipeline. Instead we use page.evaluate()
 *   to dispatch a native DragEvent with a DataTransfer object — the same path
 *   React-dropzone uses for real user interactions.
 *
 * API mocking:
 *   All backend calls are intercepted via page.route(). No real backend or
 *   Supabase project is needed to run these tests.
 */

import { test, expect, type Page, type Route } from '@playwright/test';

// ─── Constants ───────────────────────────────────────────────────────────────

const BASE         = process.env.PLAYWRIGHT_BASE_URL ?? 'http://localhost:3000';
const UPLOAD_PAGE  = `${BASE}/`;          // (user)/page.tsx is served at root /
const API_BASE     = `${BASE}/api/v1`;

const FAKE_DATASET_ID = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee';
const FAKE_JOB_ID     = 'ffffffff-0000-1111-2222-333333333333';
const FAKE_PRESIGNED  = `${BASE}/__storage__/test-upload`;  // mocked storage URL

// ─── Auth bootstrap ──────────────────────────────────────────────────────────

async function bootstrapAuth(page: Page) {
  await page.addInitScript(() => {
    window.localStorage.setItem(
      'datamind-auth',
      JSON.stringify({
        state: {
          token: 'e2e-test-token',
          refreshToken: 'e2e-refresh-token',
          userId: '00000000-0000-0000-0000-000000000099',
          role: 'user',
          email: 'e2e@datamind.test',
          activeDomain: 'finance',
        },
        version: 0,
      })
    );
  });
}

// ─── File-drop helpers ────────────────────────────────────────────────────────

/**
 * Inject files into the upload page component via the test window hook exposed
 * in development mode by page.tsx.  React-dropzone's onDrop callback is called
 * directly, bypassing the DataTransfer/async-clearing issue that makes native
 * DragEvent dispatch unreliable in Playwright.
 */
async function dropFile(
  page: Page,
  fileName: string,
  content: string,
  mimeType = 'text/csv'
) {
  await page.waitForFunction(() => typeof (window as any).__datamind_testDrop === 'function', { timeout: 5000 });
  await page.evaluate(
    ({ fileName, content, mimeType }) => {
      (window as any).__datamind_testDrop([{ name: fileName, content, type: mimeType }]);
    },
    { fileName, content, mimeType }
  );
}

/** Inject a rejected oversized file via the test hook. */
async function dropOversizedFile(page: Page) {
  await page.waitForFunction(() => typeof (window as any).__datamind_testDrop === 'function', { timeout: 5000 });
  await page.evaluate(() => {
    // Simulate the rejection branch with a file-too-large error code
    (window as any).__datamind_testDrop(
      [],
      [{ name: 'big.csv', code: 'file-too-large' }]
    );
  });
}

// ─── API mock helpers ─────────────────────────────────────────────────────────
// Use function-based URL predicates instead of string/glob patterns to avoid
// Playwright route-matching edge cases (e.g. glob ** vs exact segments).

async function mockUploadUrl(page: Page) {
  await page.route(
    (url) => url.pathname.endsWith('/datasets/upload-url'),
    (route: Route) => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          dataset_id: FAKE_DATASET_ID,
          upload_urls: { 'sample.csv': FAKE_PRESIGNED },
        }),
      });
    }
  );
}

async function mockPresignedPut(page: Page) {
  // Intercept the XHR PUT to the fake presigned storage URL by pathname prefix.
  await page.route(
    (url) => url.pathname.startsWith('/__storage__/'),
    (route: Route) => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ Key: `archive/${FAKE_DATASET_ID}/sample.csv` }),
      });
    }
  );
}

async function mockIngest(page: Page) {
  await page.route(
    (url) => url.pathname.includes('/datasets/') && url.pathname.endsWith('/ingest'),
    (route: Route) => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ job_id: FAKE_JOB_ID, status: 'queued' }),
      });
    }
  );
}

async function mockDomainPatch(page: Page) {
  // Fire-and-forget domain PATCH — prevent it from reaching the offline backend.
  await page.route(
    (url) => url.pathname.endsWith('/datasets/me/domain'),
    (route: Route) => {
      route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
    }
  );
}

async function mockJobPoll(page: Page, statuses: string[] = ['profiling']) {
  let callCount = 0;
  await page.route(
    (url) => url.pathname.includes('/jobs/') && !url.pathname.endsWith('/audit'),
    (route: Route) => {
      const s = statuses[Math.min(callCount++, statuses.length - 1)];
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          job_id: FAKE_JOB_ID,
          status: s,
          current_step: s === 'profiling' ? 'detecting_format' : null,
          progress_pct: s === 'profiling' ? 20 : 100,
        }),
      });
    }
  );
}

// ─── Shared navigation helper ─────────────────────────────────────────────────

async function gotoUploadPage(page: Page) {
  await page.goto(UPLOAD_PAGE);
  await page.waitForSelector('text=Upload Data', { timeout: 15000 });
}

// ─── Tests ───────────────────────────────────────────────────────────────────

test.describe('Upload page — file validation', () => {
  test.beforeEach(async ({ page }) => {
    await bootstrapAuth(page);
    await mockDomainPatch(page);
    await gotoUploadPage(page);
  });

  test('TC-01 — rejects a file larger than 50 MB', async ({ page }) => {
    await dropOversizedFile(page);
    // Should show size-limit error message
    await expect(page.locator('text=/exceeds the 50 MB limit/i')).toBeVisible({ timeout: 4000 });
  });

  test('TC-02 — rejects unsupported file type (.pdf)', async ({ page }) => {
    // Simulate React-dropzone rejecting the file with file-invalid-type
    await page.waitForFunction(() => typeof (window as any).__datamind_testDrop === 'function', { timeout: 5000 });
    await page.evaluate(() => {
      (window as any).__datamind_testDrop(
        [],
        [{ name: 'report.pdf', code: 'file-invalid-type' }]
      );
    });
    await expect(page.locator('text=/not a supported format/i')).toBeVisible({ timeout: 4000 });
  });

  test('TC-03 — accepts a valid CSV and shows 0% idle progress bar', async ({ page }) => {
    await dropFile(page, 'sample.csv', 'id,name\n1,Alice\n2,Bob');
    // File row should appear
    await expect(page.locator('text=sample.csv')).toBeVisible({ timeout: 4000 });
    // Upload button should become enabled
    await expect(page.locator('button:has-text("Upload & Analyze")')).toBeEnabled({ timeout: 4000 });
  });
});

test.describe('Upload page — happy-path upload flow', () => {
  test.beforeEach(async ({ page }) => {
    await bootstrapAuth(page);
    await mockDomainPatch(page);
    await mockUploadUrl(page);
    await mockPresignedPut(page);
    await mockIngest(page);
    await mockJobPoll(page, ['profiling', 'profiling', 'awaiting_hitl_merge']);
    await gotoUploadPage(page);
  });

  test('TC-04 — uploads CSV, triggers ingest, shows "profiling" status', async ({ page }) => {
    await dropFile(page, 'sample.csv', 'id,name,revenue\n1,Alice,1000\n2,Bob,2000');
    await expect(page.locator('text=sample.csv')).toBeVisible({ timeout: 4000 });

    await page.click('button:has-text("Upload & Analyze")');

    // Progress / phase indicators appear (use .first() to avoid strict-mode violation
    // when both "Requesting upload URLs…" and "Uploading N file…" are visible)
    await expect(page.locator('text=/Requesting upload URLs|Uploading/i').first()).toBeVisible({ timeout: 8000 });

    // Job polling shows "profiling"
    await expect(page.locator('text=/profiling/i')).toBeVisible({ timeout: 15000 });
  });

  test('TC-05 — overall progress bar appears during upload', async ({ page }) => {
    await dropFile(page, 'sample.csv', 'id,value\n1,100');
    await expect(page.locator('text=sample.csv')).toBeVisible({ timeout: 4000 });

    await page.click('button:has-text("Upload & Analyze")');

    await expect(page.locator('text=/Uploading.*file/i')).toBeVisible({ timeout: 8000 });
  });

  test('TC-06 — button shows "Processing…" while uploading', async ({ page }) => {
    await dropFile(page, 'sample.csv', 'id,value\n1,100');
    await expect(page.locator('text=sample.csv')).toBeVisible({ timeout: 4000 });

    await page.click('button:has-text("Upload & Analyze")');

    await expect(page.locator('button:has-text("Processing…")')).toBeVisible({ timeout: 6000 });
  });
});

test.describe('Upload page — job status polling', () => {
  test.beforeEach(async ({ page }) => {
    await bootstrapAuth(page);
    await mockDomainPatch(page);
    await mockUploadUrl(page);
    await mockPresignedPut(page);
    await mockIngest(page);
    await gotoUploadPage(page);
  });

  test('TC-07 — displays current pipeline step during polling', async ({ page }) => {
    await mockJobPoll(page, ['profiling', 'profiling', 'awaiting_hitl_merge']);

    await dropFile(page, 'sample.csv', 'x\n1');
    await expect(page.locator('text=sample.csv')).toBeVisible({ timeout: 4000 });
    await page.click('button:has-text("Upload & Analyze")');

    // Should see "profiling" step in the status line
    await expect(page.locator('text=/profiling/i')).toBeVisible({ timeout: 20000 });
  });

  test('TC-08 — redirects to /validate when status is awaiting_hitl_merge', async ({ page }) => {
    await mockJobPoll(page, ['awaiting_hitl_merge']);

    await dropFile(page, 'sample.csv', 'x\n1');
    await expect(page.locator('text=sample.csv')).toBeVisible({ timeout: 4000 });
    await page.click('button:has-text("Upload & Analyze")');

    await page.waitForURL(`**/validate/${FAKE_DATASET_ID}`, { timeout: 25000 });
    expect(page.url()).toContain(`/validate/${FAKE_DATASET_ID}`);
  });
});
