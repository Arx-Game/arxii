import * as path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test, expect, type Page } from '@playwright/test';

/**
 * Review evidence for character slots (#3996): the real Hall (`HallPage` at
 * `/hall` inside the real app shell, production build) with every `/api/**`
 * call answered by fixtures shaped like the serializers. Captures the
 * new-character tile with a free slot, the full state with its holders, the
 * card menu, the give-up confirm, the exempt staff Hall and the phone width.
 */
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, '..', '..', '..');
const EVIDENCE_DIR = path.join(REPO_ROOT, 'docs', 'reviews', '3996');
const shot = (name: string) => path.join(EVIDENCE_DIR, name);

function entry(id: number, name: string, provenance: 'player' | 'staff', frozen = false) {
  return {
    id,
    name,
    character_id: 40 + id,
    profile_picture_url: null,
    primary_persona_id: null,
    active_persona_id: null,
    unread_narrative_count: id === 1 ? 2 : 0,
    unread_direct: 0,
    has_ambient_unread: false,
    attention_as_of_id: 0,
    lifecycle_state: 'ALIVE',
    roster_type: 'Active',
    character_type: 'PC',
    activity_state: frozen ? 'FROZEN' : 'ACTIVE',
    activity_requirement: provenance === 'player' ? 'NONE' : 'HIGH',
    creation_provenance: provenance,
    thaw_available_at: frozen ? '2026-10-24T00:00:00Z' : null,
  };
}

const ARIA = entry(1, 'Aria Vell', 'player');
const BRAM = entry(2, 'Bram Solano', 'staff');

function slots(total: number | null, used: number, holders: object[]) {
  return { total, used, activity_total: 1, activity_used: used > 1 ? 1 : 0, holders };
}

const HOLDERS = [
  { kind: 'character', name: ARIA.name, roster_entry_id: 1, counts: true, activity: false },
  { kind: 'character', name: BRAM.name, roster_entry_id: 2, counts: true, activity: true },
];

async function mountHall(
  page: Page,
  options: {
    total: number | null;
    used: number;
    holders: object[];
    isStaff?: boolean;
    entries?: object[];
  }
) {
  const errors: string[] = [];
  page.on('pageerror', (err) => errors.push(err.message));
  const entries = options.entries ?? [ARIA, BRAM];
  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname === '/api/user/') {
      await route.fulfill({
        json: {
          id: 1,
          username: 'apostate',
          display_name: 'Apostate',
          email: 'a@example.com',
          email_verified: true,
          last_login: null,
          can_create_characters: options.total == null || options.used < options.total,
          character_slots: slots(options.total, options.used, options.holders),
          is_staff: options.isStaff ?? false,
          is_gm: false,
          available_characters: [],
          pending_applications: [],
          selected_entry_id: null,
          selected_entry: null,
        },
      });
    } else if (url.pathname === '/api/roster/entries/mine/') {
      await route.fulfill({ json: entries });
    } else if (
      url.pathname.startsWith('/api/roster/entries/') &&
      route.request().method() === 'POST'
    ) {
      await route.fulfill({ json: { ...ARIA, activity_state: 'FROZEN' } });
    } else {
      await route.fulfill({ status: 404, json: { detail: 'Not provided by this fixture.' } });
    }
  });
  await page.goto('/hall');
  await expect(page.getByText('Your Characters')).toBeVisible();
  await expect(page.getByTestId('new-character-tile')).toBeVisible();
  return errors;
}

test.describe('character slots evidence (#3996)', () => {
  test.use({ viewport: { width: 1280, height: 900 } });

  test('1 the Hall with a free slot shows the count and both start actions', async ({ page }) => {
    const errors = await mountHall(page, { total: 4, used: 2, holders: HOLDERS });
    const tile = page.getByTestId('new-character-tile');
    await expect(tile.getByText('2 of 4')).toBeVisible();
    await expect(tile.getByRole('link', { name: 'Browse the roster' })).toHaveAttribute(
      'href',
      '/roster'
    );
    await expect(tile.getByRole('link', { name: 'Create a character' })).toHaveAttribute(
      'href',
      '/characters/create'
    );
    await page.screenshot({ path: shot('1-hall-free-slot.png'), fullPage: true });
    expect(errors).toEqual([]);
  });

  test('2 the full Hall disables the actions and lists the holders with their free-up action', async ({
    page,
  }) => {
    const errors = await mountHall(page, { total: 2, used: 2, holders: HOLDERS });
    const tile = page.getByTestId('new-character-tile');
    await expect(tile.getByText('2 of 2')).toBeVisible();
    await expect(tile.getByRole('button', { name: 'Create a character' })).toBeDisabled();
    await expect(tile.getByRole('button', { name: 'Freeze' })).toBeVisible();
    await expect(tile.getByRole('button', { name: 'Give up' })).toBeVisible();
    await page.screenshot({ path: shot('2-hall-full.png'), fullPage: true });
    expect(errors).toEqual([]);
  });

  test('3 the card menu offers Freeze for an original character', async ({ page }) => {
    const errors = await mountHall(page, { total: 4, used: 2, holders: HOLDERS });
    await page.getByRole('button', { name: `Actions for ${ARIA.name}` }).click();
    await expect(page.getByRole('menuitem', { name: 'Freeze' })).toBeVisible();
    await page.screenshot({ path: shot('3-card-menu-freeze.png') });
    expect(errors).toEqual([]);
  });

  test('4 giving up a roster character asks first and states the consequence', async ({ page }) => {
    const errors = await mountHall(page, { total: 4, used: 2, holders: HOLDERS });
    await page.getByRole('button', { name: `Actions for ${BRAM.name}` }).click();
    await page.getByRole('menuitem', { name: 'Give up' }).click();
    await expect(page.getByText(`Give up ${BRAM.name}?`)).toBeVisible();
    await expect(page.getByText(/returns to the roster for other players/)).toBeVisible();
    await page.screenshot({ path: shot('4-give-up-confirm.png') });
    expect(errors).toEqual([]);
  });

  test('5 a frozen character shows Frozen on its card and Thaw in its menu', async ({ page }) => {
    const frozen = entry(1, 'Aria Vell', 'player', true);
    const errors = await mountHall(page, {
      total: 4,
      used: 1,
      holders: [{ ...HOLDERS[0], kind: 'frozen', counts: false }, HOLDERS[1]],
      entries: [frozen, BRAM],
    });
    await expect(page.getByText('Frozen', { exact: true })).toBeVisible();
    await page.getByRole('button', { name: `Actions for ${ARIA.name}` }).click();
    await expect(page.getByRole('menuitem', { name: /Thaw from/ })).toHaveAttribute(
      'aria-disabled',
      'true'
    );
    await page.screenshot({ path: shot('5-frozen-card-thaw.png') });
    expect(errors).toEqual([]);
  });

  test('6 a staff Hall shows the actions and no count', async ({ page }) => {
    const errors = await mountHall(page, { total: null, used: 5, holders: HOLDERS, isStaff: true });
    const tile = page.getByTestId('new-character-tile');
    await expect(tile.getByText(/ of /)).toHaveCount(0);
    await expect(tile.getByRole('link', { name: 'Create a character' })).toBeVisible();
    await page.screenshot({ path: shot('6-staff-no-count.png'), fullPage: true });
    expect(errors).toEqual([]);
  });
});

test.describe('character slots evidence, phone (#3996)', () => {
  test.use({ viewport: { width: 400, height: 900 } });

  test('7 the tile fits a phone width without horizontal overflow', async ({ page }) => {
    const errors = await mountHall(page, { total: 2, used: 2, holders: HOLDERS });
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth
    );
    expect(overflow).toBeLessThanOrEqual(10);
    await page.screenshot({ path: shot('7-phone-full.png'), fullPage: true });
    expect(errors).toEqual([]);
  });
});
