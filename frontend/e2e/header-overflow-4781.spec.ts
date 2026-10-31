import { test, expect, type Page } from '@playwright/test';

// Set EVIDENCE_DIR to save screenshots; a plain run writes nothing.
const SCREENSHOTS = process.env.EVIDENCE_DIR;

const selectedEntry = {
  id: 1,
  name: 'Anastasia of House Longfellow',
  character_id: 18,
  profile_picture_url: null,
  primary_persona_id: 7,
  active_persona_id: 7,
  unread_narrative_count: 0,
  unread_direct: 0,
  has_ambient_unread: false,
  attention_as_of_id: 0,
  lifecycle_state: 'ALIVE',
  roster_type: 'Active',
  character_type: 'PC',
  session_count: 0,
  room_name: null,
};

async function mockApi(page: Page, hasSelection: () => boolean) {
  await page.route('**/api/**', async (route) => {
    const pathname = new URL(route.request().url()).pathname;
    if (pathname === '/api/user/') {
      return route.fulfill({
        json: {
          id: 1,
          username: 'header-fixture',
          display_name: 'Header Fixture',
          email: '',
          email_verified: true,
          last_login: null,
          can_create_characters: true,
          character_slots: {
            total: null,
            used: 0,
            activity_total: 0,
            activity_used: 0,
            holders: [],
          },
          is_staff: false,
          is_gm: false,
          is_guide: false,
          available_characters: hasSelection() ? [selectedEntry] : [],
          pending_applications: [],
          selected_entry_id: hasSelection() ? 1 : null,
          selected_entry: hasSelection() ? selectedEntry : null,
        },
      });
    }
    if (pathname === '/api/roster/entries/mine/') {
      return route.fulfill({ json: hasSelection() ? [selectedEntry] : [] });
    }
    if (pathname === '/api/mail/unread-count/') {
      return route.fulfill({ json: { count: 0 } });
    }
    if (pathname === '/api/roster/mail/unread-count/') {
      return route.fulfill({ json: { count: 0 } });
    }
    if (pathname === '/api/magic/rituals/sessions/') {
      return route.fulfill({ json: [] });
    }
    if (pathname === '/api/narrative/my-messages/') {
      return route.fulfill({ json: { results: [], next: null, previous: null } });
    }
    if (pathname === '/api/personas/') {
      return route.fulfill({
        json: {
          results: [
            {
              id: 7,
              name: 'Anastasia of House Longfellow the Magnificent',
              persona_type: 'primary',
            },
          ],
        },
      });
    }
    return route.fulfill({ status: 404, json: { detail: 'fixture only' } });
  });
}

test('header fits a 400px viewport with and without a selected character', async ({ page }) => {
  await page.setViewportSize({ width: 400, height: 850 });
  let hasSelection = true;
  await mockApi(page, () => hasSelection);

  await page.goto('/login');
  await expect(page.getByRole('button', { name: 'Open menu' })).toBeVisible();
  await expect(
    page.getByRole('banner').getByText('Anastasia of House Longfellow', { exact: true }).first()
  ).toBeAttached();
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth)).toBe(400);
  await expect(page.getByRole('link', { name: 'Enter the world' })).toBeVisible();
  const selectedName = page
    .getByRole('banner')
    .getByText('Anastasia of House Longfellow', { exact: true })
    .first();
  await expect(selectedName).toBeVisible();
  await expect(selectedName).toHaveCSS('text-overflow', 'ellipsis');
  await expect(selectedName).toHaveCSS('white-space', 'nowrap');
  const nameFits = await selectedName.evaluate(
    (element) => element.scrollWidth <= element.clientWidth
  );
  expect(nameFits).toBe(false);
  const selectedPersona = page
    .getByText('as Anastasia of House Longfellow the Magnificent · Not in the world', {
      exact: true,
    })
    .first();
  await expect(selectedPersona).toBeVisible();
  await expect(selectedPersona).toHaveCSS('text-overflow', 'ellipsis');
  await expect(selectedPersona).toHaveCSS('white-space', 'nowrap');
  const personaFits = await selectedPersona.evaluate(
    (element) => element.scrollWidth <= element.clientWidth
  );
  expect(personaFits).toBe(false);
  await page.goto('/threads');
  await expect(page.getByRole('link', { name: 'Enter the world' })).toBeVisible();
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth)).toBe(400);
  if (SCREENSHOTS) {
    await page.screenshot({ path: `${SCREENSHOTS}/header-400-selected.png`, fullPage: true });
  }
  await page.getByRole('button', { name: 'Open menu' }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await expect(page.getByRole('dialog').getByRole('link', { name: 'Play' })).toBeVisible();
  await page.keyboard.press('Escape');

  for (const route of ['/', '/threads', '/threads/7']) {
    await page.goto(route);
    await expect(page.getByRole('button', { name: 'Open menu' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Enter the world' })).toBeVisible();
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth)).toBe(400);
  }

  hasSelection = false;
  await page.reload();
  await expect(page.getByRole('button', { name: 'Open menu' })).toBeVisible();
  await expect(page.getByRole('banner').getByText('Anastasia of House Longfellow')).toHaveCount(0);
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth)).toBe(400);
  for (const route of ['/', '/threads', '/threads/7']) {
    await page.goto(route);
    await expect(page.getByRole('button', { name: 'Open menu' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Enter the world' })).toHaveCount(0);
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth)).toBe(400);
  }
  if (SCREENSHOTS) {
    await page.goto('/threads');
    await page.screenshot({ path: `${SCREENSHOTS}/header-400-no-selection.png`, fullPage: true });
  }
});

test('from md up the chip still sits between the title and the nav', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await mockApi(page, () => true);
  await page.goto('/threads');
  const banner = page.getByRole('banner');
  const title = banner.getByRole('heading', { level: 1 });
  const chipName = banner.getByText('Anastasia of House Longfellow', { exact: true });
  const play = banner.getByRole('link', { name: 'Play', exact: true });
  await expect(chipName).toHaveCount(1);
  await expect(play).toBeVisible();
  const [titleBox, chipBox, playBox] = await Promise.all([
    title.boundingBox(),
    chipName.boundingBox(),
    play.boundingBox(),
  ]);
  expect(titleBox && chipBox && playBox).toBeTruthy();
  expect(titleBox!.x).toBeLessThan(chipBox!.x);
  expect(chipBox!.x).toBeLessThan(playBox!.x);
  // One row: the chip and the nav are beside the title, not wrapped under it.
  expect(chipBox!.y).toBeLessThan(titleBox!.y + titleBox!.height);
  expect(playBox!.y).toBeLessThan(titleBox!.y + titleBox!.height);
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth)).toBe(1280);
  if (SCREENSHOTS) await page.screenshot({ path: `${SCREENSHOTS}/header-1280-selected.png` });
});
