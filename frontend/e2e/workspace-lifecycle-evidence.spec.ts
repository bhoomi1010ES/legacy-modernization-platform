import { expect, test } from '@playwright/test';
import { mkdir } from 'node:fs/promises';
import path from 'node:path';

const jobId = process.env.SPENDWISE_JOB_ID;

test('Spendwise exposes the validated repository lifecycle without advancing a gate', async ({ page }) => {
  test.skip(!jobId, 'SPENDWISE_JOB_ID is required for read-only lifecycle evidence');

  await page.goto('/#/login');
  await page.getByRole('button', { name: /Alex Morgan/ }).click();
  await page.getByRole('button', { name: /Sign in to Platform/ }).click();
  await expect(page.getByRole('heading', { name: 'Modernization Command Center' })).toBeVisible();

  await page.goto(`/#/jobs/${jobId}`);
  await expect(page.getByRole('heading', { name: 'Spendwise Modernization' })).toBeVisible();
  const gateDialog = page.locator('.dialog-overlay');
  if (await gateDialog.isVisible()) {
    // Dismiss the read-only review modal so the screenshot exposes lifecycle
    // state. This does not invoke either approval/rejection action.
    await gateDialog.click({ position: { x: 4, y: 4 } });
    await expect(gateDialog).toBeHidden();
  }
  const workspace = page.locator('.workspace-lifecycle');
  await expect(workspace).toBeVisible();
  await expect(workspace.getByText('Repository workspace', { exact: true })).toBeVisible();
  await expect(workspace.getByText('Received', { exact: true })).toBeVisible();
  await expect(workspace.getByText('Staged', { exact: true })).toBeVisible();
  await expect(workspace.getByText('Workspace validated', { exact: true })).toBeVisible();
  await expect(workspace.getByText('Ready', { exact: true })).toBeVisible();
  await expect(page.getByText(/Awaiting G1/i).first()).toBeVisible();
  await expect(page.getByText('FAILED', { exact: true })).toHaveCount(0);

  const output = path.resolve(
    '..',
    'artifacts',
    'spendwise-acceptance',
    'screenshots',
    '03_workspace_lifecycle_ready.png',
  );
  await mkdir(path.dirname(output), { recursive: true });
  await page.screenshot({ path: output, fullPage: true });
});
