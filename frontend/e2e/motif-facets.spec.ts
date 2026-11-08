import { test, expect, type Page, type Response } from '@playwright/test';

/**
 * Tying facets to a resonance (#5021), against a live server (no mocked /api/**).
 *
 * Needs the rows `integration_tests.live_seeds.seed_motif_facet_spec` writes for
 * e2e_test_account (the real-test workflow runs it after the server starts): the
 * character "Wren Facetbinder", played by that account and holding Moonsilver; the
 * facets Wolf, Silk and Moon; and the account's creation draft at the Gift stage with
 * Moonsilver as its gift resonance. Runs with `--config e2e.backend.config.ts`.
 *
 * Each test reads what it saved back from a fresh page load, so a write the page shows
 * but the server never kept fails here.
 */

const CHARACTER = 'Wren Facetbinder';

async function logIn(page: Page) {
  await page.goto('/login');
  await page.getByPlaceholder('Username or Email').fill('e2e_test_account');
  await page.getByPlaceholder('Password').fill('TestPass123!');
  await page.getByRole('button', { name: 'Log In', exact: true }).click();
  await page.waitForURL((url) => !url.pathname.startsWith('/login'), { timeout: 15000 });
}

/** Every API answer that came back 404 while the page was open. */
function watchNotFound(page: Page): string[] {
  const missing: string[] = [];
  page.on('response', (response: Response) => {
    if (response.status() === 404 && new URL(response.url()).pathname.startsWith('/api/')) {
      missing.push(response.url());
    }
  });
  return missing;
}

async function pickFacet(page: Page, scope: ReturnType<Page['getByTestId']>, name: string) {
  await scope.getByRole('button', { name: '+ Add facet' }).click();
  await page.getByRole('combobox', { name: 'Add facet' }).fill(name);
  await page.getByRole('option', { name, exact: true }).click();
}

async function openSpellbook(page: Page) {
  const entries = await page.request.get('/api/roster/entries/mine/');
  expect(entries.ok()).toBe(true);
  const mine = (await entries.json()) as { id: number; name: string }[];
  const entry = mine.find((row) => row.name === CHARACTER);
  expect(entry, `${CHARACTER} is one of the account's characters`).toBeTruthy();
  await page.goto(`/characters/${entry!.id}`);
  await page.getByRole('button', { name: 'Magic', exact: true }).click();
  const panel = page.getByTestId('motif-facet-panel');
  await expect(panel).toBeVisible({ timeout: 15000 });
  return panel;
}

test.describe('tying facets to a resonance', () => {
  test('the Spellbook Facets panel ties and unties a facet, and a reload keeps it', async ({
    page,
  }) => {
    await logIn(page);
    let panel = await openSpellbook(page);
    await expect(panel.getByText('Moonsilver')).toBeVisible();
    await expect(panel.getByTestId('motif-facet-chip')).toHaveCount(0);

    const tied = page.waitForResponse(
      (r) =>
        r.url().includes('/api/magic/motif-styles/bind-facet/') && r.request().method() === 'POST'
    );
    await pickFacet(page, panel, 'Wolf');
    expect((await tied).status()).toBe(200);
    await expect(panel.getByTestId('motif-facet-chip')).toHaveText(['Wolf']);

    // Read it back from the server, not from the page's own cache.
    await page.reload();
    panel = await openSpellbook(page);
    await expect(panel.getByTestId('motif-facet-chip')).toHaveText(['Wolf']);
    await page.screenshot({
      path: test.info().outputPath('spellbook-wolf-tied.png'),
      fullPage: true,
    });

    const untied = page.waitForResponse(
      (r) =>
        r.url().includes('/api/magic/motif-styles/unbind-facet/') && r.request().method() === 'POST'
    );
    await panel.getByRole('button', { name: 'Untie Wolf' }).click();
    expect((await untied).status()).toBe(200);
    await expect(panel.getByTestId('motif-facet-chip')).toHaveCount(0);

    await page.reload();
    panel = await openSpellbook(page);
    await expect(panel.getByTestId('motif-facet-chip')).toHaveCount(0);
    await page.screenshot({
      path: test.info().outputPath('spellbook-wolf-untied.png'),
      fullPage: true,
    });
  });

  test('the creation Gift stage saves a picked facet, and the page asks for nothing that is gone', async ({
    page,
  }) => {
    await logIn(page);
    const missing = watchNotFound(page);

    await page.goto('/characters/create');
    const field = page.getByTestId('gift-facets-field');
    await expect(field).toBeVisible({ timeout: 15000 });
    await expect(field.getByText('Facets of Moonsilver')).toBeVisible();
    await expect(field.getByText('0 of 5')).toBeVisible();

    const saved = page.waitForResponse(
      (r) => r.url().includes('/api/character-creation/drafts/') && r.request().method() === 'PATCH'
    );
    await pickFacet(page, field, 'Silk');
    expect((await saved).status()).toBe(200);
    await expect(field.getByText('1 of 5')).toBeVisible();

    // A fresh load reads the pick back from the saved draft.
    await page.reload();
    const reloaded = page.getByTestId('gift-facets-field');
    await expect(reloaded.getByRole('button', { name: 'Remove Silk' })).toBeVisible({
      timeout: 15000,
    });
    await expect(reloaded.getByText('1 of 5')).toBeVisible();
    await page.screenshot({
      path: test.info().outputPath('creation-silk-picked.png'),
      fullPage: true,
    });

    // Put the draft back the way the seed left it, through the same control.
    await reloaded.getByRole('button', { name: 'Remove Silk' }).click();
    await expect(reloaded.getByText('0 of 5')).toBeVisible();

    // The removed resonance-associations call (and anything else) never 404ed.
    expect(missing).toEqual([]);
  });
});
