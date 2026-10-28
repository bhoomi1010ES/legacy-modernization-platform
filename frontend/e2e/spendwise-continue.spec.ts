import { expect, test, type Page, type TestInfo } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';

const jobId = process.env.SPENDWISE_JOB_ID || 'eb2bbaa9-90ee-4e9d-b340-5e025594126c';
const repository = 'https://github.com/parthptl0911/spendwise';
const target = 'Django REST Framework';

async function shot(page: Page, name: string) {
  const output = path.resolve('..', 'artifacts', 'spendwise-acceptance', 'screenshots', `${name}.png`);
  await mkdir(path.dirname(output), { recursive: true });
  await page.screenshot({ path: output, fullPage: false });
}

async function login(page: Page) {
  await page.goto('/#/login');
  await expect(page.getByRole('heading', { name: 'Sign in to Workspace' })).toBeVisible();
  await page.getByRole('button', { name: /Alex Morgan/ }).click();
  await page.getByRole('button', { name: /Sign in to Platform/ }).click();
  await expect(page.getByRole('heading', { name: 'Modernization Command Center' })).toBeVisible();
}

test('continue the real Spendwise job through G1', async ({ page }, testInfo: TestInfo) => {
  test.setTimeout(20 * 60 * 1000);
  const consoleMessages: string[] = [];
  const networkErrors: string[] = [];
  page.on('console', message => consoleMessages.push(`[${message.type()}] ${message.text()}`));
  page.on('pageerror', error => consoleMessages.push(`[pageerror] ${error.stack || error.message}`));
  page.on('requestfailed', request => networkErrors.push(`${request.method()} ${request.url()} :: ${request.failure()?.errorText}`));

  try {
    await login(page);
    await page.goto(`/#/jobs/${jobId}`);
    await expect(page.getByRole('heading', { name: 'Spendwise Modernization' })).toBeVisible({ timeout: 60_000 });
    await expect(page.getByText(repository)).toBeVisible();
    await expect(page.getByText(target, { exact: false }).first()).toBeVisible();
    await expect(page.getByText('FAILED', { exact: true })).toHaveCount(0);
    await page.evaluate(() => {
      const review = [...document.querySelectorAll<HTMLButtonElement>('button')]
        .find(button => button.textContent?.includes('Review Gate G1'));
      if (!review) throw new Error('Review Gate G1 was not rendered.');
      review.click();
    });
    await page.waitForSelector('.gate-modal-wide');
    await page.evaluate(() => {
      const modal = document.querySelector<HTMLElement>('.gate-modal-wide');
      if (!modal) throw new Error('G1 modal was not rendered.');
      for (const item of modal.querySelectorAll<HTMLElement>('.gate-check-item')) item.click();
    });
    await page.waitForTimeout(250);
    await page.evaluate(() => {
      const element = document.querySelector<HTMLElement>('.gate-modal-wide');
      if (!element) throw new Error('G1 modal was not rendered.');
      const textarea = element.querySelector<HTMLTextAreaElement>('textarea[placeholder^="Document technical review findings"]');
      if (!textarea) throw new Error('Reviewer rationale field was not rendered.');
      const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')?.set;
      setter?.call(
        textarea,
        'Reviewed the real Spendwise FastAPI inventory, API surface, persistence evidence, target feasibility, and Django REST Framework compatibility risks.',
      );
      textarea.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText' }));
      textarea.dispatchEvent(new Event('change', { bubbles: true }));
    });
    await page.waitForTimeout(250);
    await page.evaluate(() => {
      const element = document.querySelector<HTMLElement>('.gate-modal-wide');
      if (!element) throw new Error('G1 modal was not rendered.');
      const approve = [...element.querySelectorAll<HTMLButtonElement>('button')]
        .find(button => button.textContent?.includes('Approve Gate & Continue'));
      if (!approve) throw new Error('Approve Gate & Continue was not rendered.');
      approve.click();
    });
    await page.waitForSelector('.gate-modal-wide', { state: 'detached', timeout: 60_000 });

    await expect.poll(async () => {
      await page.goto(`/#/jobs/${jobId}`);
      await expect(page.getByRole('heading', { name: 'Spendwise Modernization' })).toBeVisible();
      return await page.locator('body').innerText();
    }, { timeout: 15 * 60 * 1000, intervals: [2_000, 5_000, 10_000] }).toMatch(
      /Review Gate G2|Human decision required for G2|Characterization Suite \(Gate G2\)|CHARACTERIZING|FAILED/,
    );

    await shot(page, '04_after_g1');
    const body = await page.locator('body').innerText();
    await testInfo.attach('post-g1-state', { body, contentType: 'text/plain' });
    expect(body).not.toMatch(/\bFAILED\b/);
  } finally {
    const output = path.resolve('..', 'artifacts', 'spendwise-acceptance', 'diagnostics-continue.json');
    await mkdir(path.dirname(output), { recursive: true });
    await writeFile(output, JSON.stringify({ jobId, url: page.url(), consoleMessages, networkErrors }, null, 2), 'utf8');
  }
});
