import { expect, test, type Page, type TestInfo } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';

const jobId = process.env.SPENDWISE_JOB_ID || 'eb2bbaa9-90ee-4e9d-b340-5e025594126c';

async function login(page: Page) {
  await page.goto('/#/login');
  await page.getByRole('button', { name: /Alex Morgan/ }).click();
  await page.getByRole('button', { name: /Sign in to Platform/ }).click();
  await expect(page.getByRole('heading', { name: 'Modernization Command Center' })).toBeVisible();
}

test('wait for and review real Spendwise characterization evidence', async ({ page }, testInfo: TestInfo) => {
  test.setTimeout(20 * 60 * 1000);
  const consoleMessages: string[] = [];
  const networkErrors: string[] = [];
  page.on('console', message => consoleMessages.push(`[${message.type()}] ${message.text()}`));
  page.on('pageerror', error => consoleMessages.push(`[pageerror] ${error.stack || error.message}`));
  page.on('requestfailed', request => networkErrors.push(`${request.method()} ${request.url()} :: ${request.failure()?.errorText}`));

  try {
    await login(page);
    await page.goto(`/#/jobs/${jobId}`);
    await expect(page.getByRole('heading', { name: 'Spendwise Modernization' })).toBeVisible();
    await expect(page.locator('.page-heading .badge').first()).toContainText(/Awaiting G2|FAILED/, { timeout: 60_000 });

    const status = (await page.locator('.page-heading .badge').first().innerText()).trim();
    expect(status, `Characterization ended in ${status}`).not.toBe('FAILED');
    await expect(page.getByRole('button', { name: 'Review Gate G2' })).toBeVisible();

    await page.goto('/#/characterization');
    await expect(page.getByRole('heading', { name: 'Characterization & schema review' })).toBeVisible();
    await page.getByLabel('Modernization job').selectOption(jobId);
    await expect(page.getByRole('heading', { name: /Baseline coverage:/ })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Test-case review' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Schema inventory & differences' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Data-mapping review' })).toBeVisible();
    const output = path.resolve('..', 'artifacts', 'spendwise-acceptance', 'screenshots', '05_characterization_schema_g2.png');
    await mkdir(path.dirname(output), { recursive: true });
    await page.screenshot({ path: output, fullPage: false });
    const body = await page.locator('body').innerText();
    await testInfo.attach('g2-characterization-review', { body, contentType: 'text/plain' });
    await expect(page.getByText('REAL EXECUTION (DOCKER)', { exact: true })).toBeVisible();
    await expect(page.getByText('UNAVAILABLE', { exact: true })).toHaveCount(0);
  } finally {
    const output = path.resolve('..', 'artifacts', 'spendwise-acceptance', 'diagnostics-g2-review.json');
    await mkdir(path.dirname(output), { recursive: true });
    await writeFile(output, JSON.stringify({ jobId, url: page.url(), consoleMessages, networkErrors }, null, 2), 'utf8');
  }
});
