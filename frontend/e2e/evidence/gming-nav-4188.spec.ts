import * as path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test, expect, type Page, type Route } from '@playwright/test';

/**
 * Review evidence for #4188: the real header and the real GM Dashboard on the
 * production bundle, every `/api/**` call answered by fixtures shaped like the
 * serializers. The demo's Style B screens are the approved design.
 *
 * Readings: signed out (C1: World is lore, no GMing), a signed-in player (C2),
 * a GM with things waiting (B1: the GMing menu and its one badge), staff who is
 * also a GM (B2: the Staff section), staff with no GMProfile (Decision 8), the
 * Dashboard opening on "Waiting on you" (B3) and its zero state (Decision 10),
 * and the phone sheet (D). Every name and count is placeholder copy.
 */
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, '..', '..', '..');
const EVIDENCE_DIR = path.join(REPO_ROOT, 'docs', 'reviews', '4188');
const shot = (name: string) => path.join(EVIDENCE_DIR, name);

type Viewer = 'out' | 'player' | 'gm' | 'gm-quiet' | 'staff' | 'staff-gm';

const IS_GM: Record<Viewer, boolean> = {
  out: false,
  player: false,
  gm: true,
  'gm-quiet': true,
  staff: false,
  'staff-gm': true,
};
const IS_STAFF: Record<Viewer, boolean> = {
  out: false,
  player: false,
  gm: false,
  'gm-quiet': false,
  staff: true,
  'staff-gm': true,
};

/** The demo's four counts (2, 1, 3, 1) plus the two rows the spec added. */
const WAITING = {
  story_offers: 2,
  crossover_invites: 1,
  sheet_update_requests: 3,
  claims_to_approve: 1,
  my_claims: 0,
  session_requests: 0,
  total: 7,
};
const QUIET = {
  story_offers: 0,
  crossover_invites: 0,
  sheet_update_requests: 0,
  claims_to_approve: 0,
  my_claims: 0,
  session_requests: 0,
  total: 0,
};

function accountPayload(viewer: Viewer) {
  return {
    id: 1,
    username: 'walk-e2e',
    display_name: 'Walk E2E',
    email: '',
    email_verified: true,
    last_login: null,
    can_create_characters: true,
    character_slots: { total: null, used: 0, activity_total: 0, activity_used: 0, holders: [] },
    is_staff: IS_STAFF[viewer],
    is_gm: IS_GM[viewer],
    available_characters: [],
    pending_applications: [],
    selected_entry_id: null,
    selected_entry: null,
  };
}

const DASHBOARD = {
  episodes_ready_to_run: [{ episode_id: 1 }],
  pending_agm_claims: [{ claim_id: 1 }],
  assigned_session_requests: [],
  waiting_for_gm: [{ progress_id: 1 }, { progress_id: 2 }],
  open_group_requests: [],
  my_tables: [{ id: 1, name: 'The Lantern Table', membership_count: 5 }],
  pending_story_offers: [
    { id: 1, story__title: 'A Debt in Three Coins', created_at: '2026-10-12T00:00:00Z' },
    { id: 2, story__title: 'The Salt Road', created_at: '2026-10-13T00:00:00Z' },
  ],
  evidence_summary: {
    level: 'starting',
    stories_running: 1,
    beats_completed_by_risk: {},
    last_active_at: '2026-10-13T00:00:00Z',
  },
  pending_applications: 0,
  open_invites: 0,
};

async function mockApp(page: Page, viewer: Viewer) {
  await page.route('**/api/**', async (route: Route) => {
    const url = new URL(route.request().url());
    const p = url.pathname;
    if (p === '/api/user/') {
      // Signed out, the real endpoint answers 200 with an empty body (`fetchAccount`).
      return viewer === 'out'
        ? route.fulfill({ status: 200, body: '', contentType: 'application/json' })
        : route.fulfill({ json: accountPayload(viewer) });
    }
    if (p === '/api/gm/attention/') {
      if (!IS_GM[viewer]) {
        return route.fulfill({ status: 403, json: { detail: 'You must be a GM.' } });
      }
      return route.fulfill({ json: viewer === 'gm-quiet' ? QUIET : WAITING });
    }
    if (p === '/api/gm/dashboard/') {
      if (!IS_GM[viewer]) {
        return route.fulfill({ status: 403, json: { detail: 'You must be a GM.' } });
      }
      return route.fulfill({ json: DASHBOARD });
    }
    if (p === '/api/roster/entries/mine/') return route.fulfill({ json: [] });
    if (p === '/api/roster/mail/unread-count/') return route.fulfill({ json: { count: 0 } });
    if (p === '/api/gm/prompt-filters/') return route.fulfill({ json: [] });
    if (p.startsWith('/api/staff/')) return route.fulfill({ json: { count: 4, results: [] } });
    if (route.request().method() === 'GET') return route.fulfill({ json: [] });
    return route.fulfill({ status: 404, json: { detail: 'Not provided by this fixture.' } });
  });
}

const gmingTrigger = (page: Page) => page.getByRole('button', { name: /gming/i });
const worldTrigger = (page: Page) => page.getByRole('button', { name: /^world/i });

async function openHeaderOn(page: Page, viewer: Viewer, route = '/codex') {
  await page.setViewportSize({ width: 1280, height: 720 });
  await mockApp(page, viewer);
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto(route);
  await expect(page.getByRole('link', { name: /play/i })).toBeVisible();
  return errors;
}

test.describe('The GMing nav group (#4188) on the production bundle', () => {
  test('C1 signed out: World is lore, no GMing, no Crossover', async ({ page }) => {
    const errors = await openHeaderOn(page, 'out');
    await expect(gmingTrigger(page)).toHaveCount(0);
    await worldTrigger(page).click();
    const header = page.locator('header');
    await expect(header.getByRole('link', { name: 'Codex' })).toBeVisible();
    await expect(header.getByRole('link', { name: 'Realms' })).toBeVisible();
    await expect(page.getByRole('link', { name: /crossover/i })).toHaveCount(0);
    await expect(page.getByRole('link', { name: 'Story Workload' })).toHaveCount(0);
    await page.screenshot({ path: shot('01-c1-signed-out-world-1280.png') });
    expect(errors).toEqual([]);
  });

  test('C2 signed in, not a GM: no GMing, Inbox present', async ({ page }) => {
    await openHeaderOn(page, 'player');
    await expect(page.getByRole('link', { name: /inbox/i })).toBeVisible();
    await expect(gmingTrigger(page)).toHaveCount(0);
    await expect(page.getByRole('link', { name: 'Story Workload' })).toHaveCount(0);
    await page.screenshot({ path: shot('02-c2-player-1280.png') });
  });

  test('B1 a GM: the GMing menu, its four rows and one badge', async ({ page }) => {
    const errors = await openHeaderOn(page, 'gm');
    await expect(page.getByTestId('gm-attention-badge')).toHaveText('7');
    await gmingTrigger(page).click();
    await expect(page.getByRole('link', { name: 'Dashboard' })).toHaveAttribute(
      'href',
      '/gm/dashboard'
    );
    await expect(page.getByRole('link', { name: 'Story Builder' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Tables' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Lead GM Queue' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Story Workload' })).toHaveCount(0);
    await page.screenshot({ path: shot('03-b1-gm-menu-1280.png') });
    expect(errors).toEqual([]);
  });

  test('B2 staff who is also a GM: one menu, the Staff section too', async ({ page }) => {
    await openHeaderOn(page, 'staff-gm');
    await gmingTrigger(page).click();
    await expect(page.getByRole('link', { name: 'Dashboard' })).toBeVisible();
    await expect(page.locator('header p', { hasText: /^Staff$/ })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Story Workload' })).toHaveAttribute(
      'href',
      '/stories/staff-workload'
    );
    await expect(gmingTrigger(page)).toHaveCount(1);
    await page.screenshot({ path: shot('04-b2-staff-gm-menu-1280.png') });
  });

  test('Decision 8, staff with no GMProfile: the Staff section alone, no badge', async ({
    page,
  }) => {
    await openHeaderOn(page, 'staff');
    await expect(page.getByTestId('gm-attention-badge')).toHaveCount(0);
    await gmingTrigger(page).click();
    await expect(page.getByRole('link', { name: 'Story Workload' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Dashboard' })).toHaveCount(0);
    await expect(page.getByRole('link', { name: 'Lead GM Queue' })).toHaveCount(0);
    await page.screenshot({ path: shot('05-staff-only-menu-1280.png') });
  });

  test('B3 the Dashboard opens on "Waiting on you", each non-zero row a door', async ({ page }) => {
    const errors = await openHeaderOn(page, 'gm', '/gm/dashboard');
    const strip = page.getByTestId('waiting-on-you');
    await expect(strip).toBeVisible();
    await expect(page.getByTestId('waiting-story_offers')).toHaveAttribute(
      'href',
      '/stories/my-offers'
    );
    await expect(page.getByTestId('waiting-crossover_invites')).toHaveAttribute(
      'href',
      '/crossover/inbox'
    );
    await expect(page.getByTestId('waiting-sheet_update_requests')).toHaveAttribute(
      'href',
      '/gm/update-requests'
    );
    await expect(page.getByTestId('waiting-claims_to_approve')).toHaveAttribute(
      'href',
      '/stories/gm-queue'
    );
    await expect(page.getByTestId('waiting-session_requests')).not.toHaveAttribute('href');
    await expect(page.getByText(/Pending Story Offers/)).toHaveCount(0);
    await expect(page.getByText('Pending AGM claims')).toHaveCount(0);
    await expect(page.getByText('Episodes ready to run')).toBeVisible();
    // The strip is the first thing under the title.
    const stripTop = await strip.boundingBox();
    const tilesTop = await page.getByText('Episodes ready to run').boundingBox();
    expect(stripTop && tilesTop && stripTop.y < tilesTop.y).toBe(true);
    await page.screenshot({ path: shot('06-b3-dashboard-strip-1280.png'), fullPage: true });
    expect(errors).toEqual([]);

    // The row is a real door: it reaches the offers page.
    await page.getByTestId('waiting-story_offers').click();
    await expect(page).toHaveURL(/\/stories\/my-offers$/);
  });

  test('Decision 10, nothing waiting: no badge, a strip of zeros with no links', async ({
    page,
  }) => {
    await openHeaderOn(page, 'gm-quiet', '/gm/dashboard');
    await expect(page.getByTestId('gm-attention-badge')).toHaveCount(0);
    const strip = page.getByTestId('waiting-on-you');
    await expect(strip).toBeVisible();
    await expect(strip.locator('a')).toHaveCount(0);
    await expect(page.getByTestId('waiting-my_claims')).toContainText('0');
    await page.screenshot({ path: shot('07-quiet-dashboard-1280.png'), fullPage: true });
  });

  test('D phone: the sheet mirrors the group and its count', async ({ page }) => {
    await mockApp(page, 'staff-gm');
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/codex');
    await page.getByRole('button', { name: /open menu/i }).click();
    const sheet = page.getByRole('dialog');
    await expect(sheet.getByText('GMing (7)')).toBeVisible();
    // Let the sheet finish sliding in before the shot.
    await page.waitForTimeout(600);
    await expect(sheet.getByRole('link', { name: 'Dashboard' })).toBeVisible();
    await expect(sheet.locator('p', { hasText: /^Staff$/ })).toBeVisible();
    await expect(sheet.getByRole('link', { name: 'Story Workload' })).toBeVisible();
    await expect(sheet.getByRole('link', { name: /crossover/i })).toHaveCount(0);
    await page.screenshot({ path: shot('08-d-phone-sheet-390.png') });
  });
});
