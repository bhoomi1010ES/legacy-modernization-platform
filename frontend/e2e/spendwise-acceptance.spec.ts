import { expect, test, type Page, type TestInfo } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';

const repository = 'https://github.com/parthptl0911/spendwise';
const target = 'Django REST Framework';

async function shot(page: Page, name: string) {
  const output = path.resolve('..', 'artifacts', 'spendwise-acceptance', 'screenshots', `${name}.png`);
  await mkdir(path.dirname(output), { recursive: true });
  await page.screenshot({ path: output, fullPage: true });
}

test('Spendwise modernization is driven through the platform UI', async ({ page }, testInfo: TestInfo) => {
  const consoleMessages: string[] = [];
  const networkErrors: string[] = [];
  page.on('console', message => consoleMessages.push(`[${message.type()}] ${message.text()}`));
  page.on('pageerror', error => consoleMessages.push(`[pageerror] ${error.stack || error.message}`));
  page.on('requestfailed', request => networkErrors.push(`${request.method()} ${request.url()} :: ${request.failure()?.errorText}`));

  try {
    await page.goto('/#/login');
    await expect(page.getByRole('heading', { name: 'Sign in to Workspace' })).toBeVisible();
    await shot(page, '00_platform_login');

    await page.getByRole('button', { name: /Alex Morgan/ }).click();
    await page.getByRole('button', { name: /Sign in to Platform/ }).click();
    await expect(page.getByRole('heading', { name: 'Modernization Command Center' })).toBeVisible();
    await shot(page, '00_platform_dashboard');

    await page.getByRole('button', { name: /Start Modernization/ }).first().click();
    await expect(page.getByRole('heading', { name: 'Initialize Modernization Wizard' })).toBeVisible();

    await page.getByLabel('Repository URL').fill(repository);
    await page.getByLabel('Revision / Branch').fill('main');
    await expect(page.getByText(/FastAPI/i).first()).toBeVisible({ timeout: 120_000 });

    await page.getByLabel('Targeted Tech Stack & Modernization Plan').fill(
      `${target}\nConvert the actual FastAPI backend to Django REST Framework while preserving the frontend API contract, authentication behavior, validation semantics, database effects, and HTTP status codes.`,
    );
    await shot(page, '01_job_intake_ready');

    await expect.poll(() => page.locator('form').evaluate((form: HTMLFormElement) => form.checkValidity())).toBe(true);
    await page.getByRole('button', { name: 'Launch Modernization Job' }).click();
    await expect(page).toHaveURL(/#\/jobs\/[0-9a-f-]+/i, { timeout: 120_000 });
    await expect(page.getByText(repository)).toBeVisible({ timeout: 60_000 });
    await shot(page, '01_job_created');

    const jobId = page.url().split('/jobs/')[1];
    expect(jobId).toBeTruthy();
    await testInfo.attach('job-id', { body: jobId, contentType: 'text/plain' });

    await expect.poll(async () => {
      await page.goto(`/#/jobs/${jobId}`);
      await expect(page.getByRole('heading', { name: 'Spendwise Modernization' })).toBeVisible();
      return await page.locator('body').innerText();
    }, { timeout: 5 * 60 * 1000, intervals: [2_000, 5_000, 10_000] }).toMatch(/AWAITING_GATE_G1|CHARACTERIZING|AWAITING_GATE_G2|PLANNING|AWAITING_GATE_G3|CONVERTING|VERIFYING|INTEGRATING|AWAITING_GATE_G4/);

    await expect(page.getByText('FAILED', { exact: true })).toHaveCount(0);

    await shot(page, '02_analysis');
  } finally {
    const output = path.resolve('..', 'artifacts', 'spendwise-acceptance', 'diagnostics.json');
    await mkdir(path.dirname(output), { recursive: true });
    await writeFile(output, JSON.stringify({ url: page.url(), consoleMessages, networkErrors }, null, 2), 'utf8');
  }
});
