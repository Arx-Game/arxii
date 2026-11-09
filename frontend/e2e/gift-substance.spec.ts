import { test, expect, type Page } from '@playwright/test';

/**
 * A gift's substance (#5018), against a live server (no mocked /api/**).
 *
 * Needs the rows `integration_tests.live_seeds.seed_gift_substance_spec` writes for
 * e2e_test_account: "Vesper Shade", a level-10 shadow caster in an ordinary-lit hall, with
 * the scene "Shadows in the Hall" running there and the account as its GM. Runs with
 * `--config e2e.backend.config.ts`.
 *
 * Each step reads back what the server kept: the card's cost comes from the server, and
 * the call-up and the GM's mark are read again after a fresh load.
 */

const SCENE_NAME = 'Shadows in the Hall';
const TECHNIQUE = 'Veil of Dusk';

async function logIn(page: Page) {
  await page.goto('/login');
  await page.getByPlaceholder('Username or Email').fill('e2e_test_account');
  await page.getByPlaceholder('Password').fill('TestPass123!');
  await page.getByRole('button', { name: 'Log In', exact: true }).click();
  await page.waitForURL((url) => !url.pathname.startsWith('/login'), { timeout: 15000 });
}

async function sceneId(page: Page): Promise<number> {
  const res = await page.request.get(`/api/scenes/?search=${encodeURIComponent(SCENE_NAME)}`);
  expect(res.ok()).toBe(true);
  const body = (await res.json()) as { results?: { id: number; name: string }[] };
  const scene = (body.results ?? []).find((row) => row.name === SCENE_NAME);
  expect(scene, `${SCENE_NAME} is running`).toBeTruthy();
  return scene!.id;
}

async function openCast(page: Page, id: number) {
  await page.goto(`/scenes/${id}`);
  await page.locator('button:has(svg.lucide-swords)').click();
  await page.getByRole('button', { name: /Cast/ }).click();
  await expect(page.getByTestId('gift-call-up-row')).toBeVisible({ timeout: 15000 });
}

test.describe.configure({ mode: 'serial' });

test.describe('a gift substance in a social scene', () => {
  test('the card shows the free call-up and the power it brings', async ({ page }) => {
    await logIn(page);
    const id = await sceneId(page);
    await openCast(page, id);

    const row = page.getByTestId('gift-call-up-row');
    await expect(row.getByRole('button', { name: 'Call up shadow' })).toBeEnabled();
    await expect(row).toContainText('free, your control covers it');

    await page
      .getByRole('button', { name: new RegExp(TECHNIQUE) })
      .first()
      .click();
    const lines = page.getByTestId('surroundings-lines').last();
    await expect(lines).toContainText('Calls up shadow: free, your control covers it');
    await expect(lines).toContainText('Shadow here after the call-up');
    await expect(lines).toContainText('+5 power');
    await page.screenshot({
      path: test.info().outputPath('01-cast-card-free-call-up.png'),
      fullPage: true,
    });
  });

  test('the scene GM sees Present here in the Stage tab', async ({ page }) => {
    await logIn(page);
    const id = await sceneId(page);
    await page.goto(`/scenes/${id}`);
    await page.getByRole('tab', { name: 'Stage' }).click();
    await page.getByTestId('gm-stage-mode-select').selectOption('present');
    const present = page.getByTestId('gm-stage-present-here');
    await expect(present.getByTestId('gm-stage-substance-select')).toContainText('shadow');
    await present.getByTestId('gm-stage-substance-select').selectOption({ label: 'shadow' });
    const marked = page.waitForResponse(
      (r) => r.url().includes('/dispatch/') && r.request().method() === 'POST'
    );
    await present.getByTestId('gm-stage-mark-present').click();
    expect((await marked).status()).toBe(200);
    await expect(present.getByText('Marked in this scene')).toBeVisible();
    await page.screenshot({
      path: test.info().outputPath('02-gm-present-here.png'),
      fullPage: true,
    });

    // The mark comes off again, so the next test starts in ordinary light.
    const removed = page.waitForResponse(
      (r) => r.url().includes('/dispatch/') && r.request().method() === 'POST'
    );
    await present.getByRole('button', { name: 'Remove' }).click();
    expect((await removed).status()).toBe(200);
    await expect(present.getByText('Marked in this scene')).toHaveCount(0);
  });

  test('calling it up with no technique is free and the room keeps it', async ({ page }) => {
    await logIn(page);
    const id = await sceneId(page);
    await openCast(page, id);

    const called = page.waitForResponse(
      (r) => r.url().includes('/dispatch/') && r.request().method() === 'POST'
    );
    await page.getByRole('button', { name: 'Call up shadow' }).click();
    const response = await called;
    expect(response.status()).toBe(200);
    expect(((await response.json()) as { message: string }).message).toBe(
      'You call up shadow. Cost: free.'
    );
    await page.screenshot({
      path: test.info().outputPath('03-called-up-free.png'),
      fullPage: true,
    });

    // Read it back from the server: shadow is now here, nothing more to call up.
    await openCast(page, id);
    await expect(page.getByTestId('gift-call-up-row')).toContainText('shadow is already here');
  });
});
