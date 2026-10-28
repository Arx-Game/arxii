import { test, expect } from '@playwright/test';

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

test('header fits a 400px viewport with and without a selected character', async ({ page }) => {
  await page.setViewportSize({ width: 400, height: 850 });
  let hasSelection = true;
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
          available_characters: [],
          pending_applications: [],
          selected_entry_id: hasSelection ? 1 : null,
          selected_entry: hasSelection ? selectedEntry : null,
        },
      });
    }
    if (pathname === '/api/roster/entries/mine/') {
      return route.fulfill({ json: hasSelection ? [selectedEntry] : [] });
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
    if (pathname === '/api/roster/entries/18/personas/') {
      return route.fulfill({ json: [] });
    }
    return route.fulfill({ status: 404, json: { detail: 'fixture only' } });
  });

  await page.goto('/login');
  await expect(page.getByRole('button', { name: 'Open menu' })).toBeVisible();
  await expect(
    page.getByRole('banner').getByText('Anastasia of House Longfellow', { exact: true }).first()
  ).toBeAttached();
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth)).toBe(400);
  await page.screenshot({ path: '../docs/reviews/4781/header-400-selected.png', fullPage: true });
  await page.getByRole('button', { name: 'Open menu' }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await expect(page.getByRole('dialog').getByRole('link', { name: 'Play' })).toBeVisible();
  await page.keyboard.press('Escape');

  hasSelection = false;
  await page.reload();
  await expect(page.getByRole('button', { name: 'Open menu' })).toBeVisible();
  await expect(page.getByRole('banner').getByText('Anastasia of House Longfellow')).toHaveCount(0);
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth)).toBe(400);
  await page.screenshot({
    path: '../docs/reviews/4781/header-400-no-selection.png',
    fullPage: true,
  });
});
