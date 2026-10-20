import * as path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test, expect, type Page } from '@playwright/test';
import { mockRestRoutes, reachReadySession, NYX, type Connection } from '../support/gameHarness';

/**
 * Real-browser evidence for #4508 (poses that arrive live in an open scene):
 * the real `/game` on the production bundle, REST and the socket answered by
 * the shared harness's fixtures. One test per expectation, E1 to E5.
 */
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, '..', '..', '..');
const shot = (name: string) => path.join(REPO_ROOT, 'docs', 'reviews', '4508', name);

const POSE =
  'Nyx turns the signet ring once on her finger and does not answer at once. Across the ' +
  'courtyard the rain has thinned to a mist, and the lamps along the gallery are being lit ' +
  'one by one. "You came sooner than I thought you would," she says, and means it.';

const ENTRY_POSE =
  'The gate swings in on a long breath of wet air, and Nyx steps through it as though the ' +
  'courtyard had been waiting for her all evening. She shakes the rain from her sleeves, ' +
  'takes in the lamps and the empty benches, and settles on the one nearest the fountain.';

const RESONANCES = [
  { id: 4, name: 'Candor' },
  { id: 5, name: 'Resolve' },
];

function framePayload(overrides: Record<string, unknown>): Record<string, unknown> {
  return {
    id: 910,
    persona: { id: 99, name: NYX.name, thumbnail_url: '' },
    content: POSE,
    mode: 'pose',
    timestamp: new Date().toISOString(),
    scene_id: 1,
    place_id: null,
    place_name: null,
    receiver_persona_ids: [],
    target_persona_ids: [],
    ...overrides,
  };
}

function sendPose(connection: Connection, overrides: Record<string, unknown>): void {
  connection.route.send(JSON.stringify(['interaction', [], framePayload(overrides)]));
}

function sendChanged(connection: Connection, interactionId: number): void {
  connection.route.send(
    JSON.stringify(['interaction_changed', [], { interaction_id: interactionId, scene_id: 1 }])
  );
}

/** The full retrieve row for a pose, as `GET /api/interactions/<id>/` returns it. */
function retrieveRow(overrides: Record<string, unknown>): Record<string, unknown> {
  return {
    ...framePayload({}),
    scene: 1,
    visibility: 'default',
    reactions: [],
    is_favorited: false,
    pose_kind: 'standard',
    endorsee_sheet_id: 77,
    endorsable_resonances: RESONANCES,
    pose_endorsers: [],
    my_pose_endorsement: null,
    entry_endorsers: [],
    entry_endorsed_by_me: false,
    ...overrides,
  };
}

async function openScene(
  page: Page,
  extraRoutes: () => Promise<void> = async () => {}
): Promise<Connection> {
  await page.setViewportSize({ width: 1600, height: 900 });
  await mockRestRoutes(page);
  await extraRoutes();
  const [connection] = await reachReadySession(page);
  // The scene feed's first page must have been answered, so a feed is cached.
  await expect
    .poll(() =>
      page.evaluate(
        () =>
          performance
            .getEntriesByType('resource')
            .filter((e) => e.name.includes('/api/interactions/?scene=1')).length
      )
    )
    .toBeGreaterThan(0);
  return connection;
}

test.describe('a pose that arrives live matches a loaded one (#4508)', () => {
  test('E1: a live pose carries its pose endorse control with no reload', async ({ page }) => {
    const connection = await openScene(page);
    sendPose(connection, {
      id: 910,
      pose_kind: 'standard',
      endorsee_sheet_id: 77,
      endorsable_resonances: RESONANCES,
    });
    const line = page.getByTestId('pose-unit').first();
    await expect(line.getByText(/signet ring/)).toBeVisible();
    const control = line.getByTestId('endorsement-control-pose');
    await expect(control).toBeVisible();
    await expect(control.getByRole('button', { name: 'Endorse', exact: true })).toBeVisible();
    await expect(line.getByTestId('endorsement-control-entry')).toHaveCount(0);
    await page.screenshot({ path: shot('e1-live-pose-endorse.png') });
  });

  test('E1 control: the same pose without the new fields has no endorse control', async ({
    page,
  }) => {
    const connection = await openScene(page);
    sendPose(connection, { id: 911 });
    const line = page.getByTestId('pose-unit').first();
    await expect(line.getByText(/signet ring/)).toBeVisible();
    await expect(line.getByTestId('endorsement-control-pose')).toHaveCount(0);
  });

  test('E2: a live entry pose shows the entrance endorse control', async ({ page }) => {
    const connection = await openScene(page);
    sendPose(connection, {
      id: 912,
      content: ENTRY_POSE,
      pose_kind: 'entry',
      endorsee_sheet_id: 77,
      endorsable_resonances: RESONANCES,
    });
    const line = page.getByTestId('pose-unit').first();
    await expect(line.getByText(/gate swings in/)).toBeVisible();
    const control = line.getByTestId('endorsement-control-entry');
    await expect(control).toBeVisible();
    await expect(control.getByRole('button', { name: 'Endorse entry' })).toBeVisible();
    await page.screenshot({ path: shot('e2-live-entry-endorse.png') });
  });

  test('E3: interaction_changed refetches the pose and it updates in place', async ({ page }) => {
    const connection = await openScene(page);
    let retrieves = 0;
    await page.route('**/api/interactions/913/', async (route) => {
      retrieves += 1;
      await route.fulfill({
        json: retrieveRow({
          id: 913,
          pose_endorsers: [
            { persona_id: 31, persona_name: 'Bram', thumbnail_url: '', resonance_id: 4 },
          ],
          reactions: [{ emoji: '🔥', count: 1, reacted_by_me: false }],
        }),
      });
    });
    sendPose(connection, {
      id: 913,
      pose_kind: 'standard',
      endorsee_sheet_id: 77,
      endorsable_resonances: RESONANCES,
    });
    const line = page.getByTestId('pose-unit').first();
    await expect(line.getByText(/signet ring/)).toBeVisible();
    await expect(line.getByTitle('Bram endorsed with Candor')).toHaveCount(0);

    sendChanged(connection, 913);
    await expect(line.getByTitle('Bram endorsed with Candor')).toBeVisible();
    await expect(line.getByText('🔥')).toBeVisible();
    expect(retrieves).toBe(1);
    await page.screenshot({ path: shot('e3-changed-pose-updated.png') });
  });

  test('E4: a 404 on the retrieve shows no error and leaves the feed intact', async ({ page }) => {
    const connection = await openScene(page);
    const errors: string[] = [];
    page.on('pageerror', (e) => errors.push(e.message));
    let retrieves = 0;
    await page.route('**/api/interactions/914/', async (route) => {
      retrieves += 1;
      await route.fulfill({ status: 404, json: { detail: 'Not found.' } });
    });
    sendPose(connection, { id: 914, endorsee_sheet_id: 77, endorsable_resonances: RESONANCES });
    const line = page.getByTestId('pose-unit').first();
    await expect(line.getByText(/signet ring/)).toBeVisible();

    sendChanged(connection, 914);
    await expect.poll(() => retrieves).toBe(1);
    await page.waitForTimeout(500);
    await expect(line.getByText(/signet ring/)).toBeVisible();
    await expect(page.getByTestId('pose-unit')).toHaveCount(1);
    await expect(page.getByRole('alert')).toHaveCount(0);
    await expect(page.getByText(/something went wrong|failed|error/i)).toHaveCount(0);
    expect(errors).toEqual([]);
  });

  test('E5: endorsing refetches the scene feed after the POST succeeds', async ({ page }) => {
    const order: string[] = [];
    const connection = await openScene(page, async () => {
      await page.route('**/api/interactions/?*', async (route) => {
        order.push('feed');
        await route.fulfill({ json: { results: [], next: null } });
      });
      await page.route('**/api/magic/pose-endorsements/', async (route) => {
        order.push('post');
        await route.fulfill({ status: 201, json: { id: 5 } });
      });
    });
    sendPose(connection, { id: 915, endorsee_sheet_id: 77, endorsable_resonances: RESONANCES });
    const line = page.getByTestId('pose-unit').first();
    await expect(line.getByText(/signet ring/)).toBeVisible();
    expect(order.filter((o) => o === 'feed').length).toBeGreaterThan(0);
    order.length = 0;

    await line.getByRole('button', { name: 'Endorse', exact: true }).click();
    await page.getByRole('menuitem', { name: 'Candor' }).click();
    await expect.poll(() => order.join(',')).toMatch(/^post,feed/);
  });

  test("E6: toggling an emoji reaction refreshes the actor's own feed after the POST", async ({
    page,
  }) => {
    const order: string[] = [];
    const connection = await openScene(page, async () => {
      await page.route('**/api/reaction-emoji/', async (route) => {
        await route.fulfill({ json: { results: [{ emoji: '🔥', valence: 1, sort_order: 1 }] } });
      });
      await page.route('**/api/interactions/?*', async (route) => {
        order.push('feed');
        await route.fulfill({ json: { results: [], next: null } });
      });
      await page.route('**/api/interaction-reactions/', async (route) => {
        order.push('post');
        await route.fulfill({ status: 201, json: { id: 3 } });
      });
    });
    sendPose(connection, { id: 920 });
    const line = page.getByTestId('pose-unit').first();
    await expect(line.getByText(/signet ring/)).toBeVisible();
    order.length = 0;

    await line.getByRole('button', { name: '🔥' }).click();
    await expect.poll(() => order.join(',')).toMatch(/^post,feed/);
  });

  test('E7: giving kudos from the play menu refreshes the feed after the POST', async ({
    page,
  }) => {
    const order: string[] = [];
    let kudosBody: Record<string, unknown> | null = null;
    const connection = await openScene(page, async () => {
      await page.route('**/api/interactions/?*', async (route) => {
        order.push('feed');
        await route.fulfill({ json: { results: [], next: null } });
      });
      await page.route('**/api/reaction-windows/react-to-interaction/', async (route) => {
        order.push('post');
        kudosBody = route.request().postDataJSON() as Record<string, unknown>;
        await route.fulfill({ status: 201, json: {} });
      });
    });
    sendPose(connection, { id: 921 });
    const line = page.getByTestId('pose-unit').first();
    await expect(line.getByText(/signet ring/)).toBeVisible();
    order.length = 0;

    await line.getByTestId('pose-avatar').click();
    await page.getByRole('menuitem', { name: 'Kudos' }).click();
    await expect.poll(() => order.join(',')).toMatch(/^post,feed/);
    expect(kudosBody).toMatchObject({ interaction_id: 921, kind: 'kudos', choice: 'kudos' });
  });

  test('E8: a live pose carrying a dramatic-moment tag shows it at once', async ({ page }) => {
    const connection = await openScene(page);
    sendPose(connection, {
      id: 922,
      dramatic_moment_tags: [{ moment_type_label: 'Defiance', character_sheet_id: null }],
    });
    const line = page.getByTestId('pose-unit').first();
    await expect(line.getByText(/signet ring/)).toBeVisible();
    await expect(line.getByTestId('dramatic-moment-badges')).toContainText('Defiance');
    await page.screenshot({ path: shot('e8-live-pose-tag.png') });
  });

  test('E9: an entrance that already has endorsers is re-read once and shows mine', async ({
    page,
  }) => {
    const connection = await openScene(page);
    let retrieves = 0;
    await page.route('**/api/interactions/923/', async (route) => {
      retrieves += 1;
      await route.fulfill({
        json: retrieveRow({
          id: 923,
          content: ENTRY_POSE,
          pose_kind: 'entry',
          entry_endorsers: [
            { persona_id: 31, persona_name: 'Bram', thumbnail_url: '', resonance_id: 4 },
          ],
          entry_endorsed_by_me: true,
        }),
      });
    });
    sendPose(connection, {
      id: 923,
      content: ENTRY_POSE,
      pose_kind: 'entry',
      endorsee_sheet_id: 77,
      endorsable_resonances: RESONANCES,
      entry_endorsers: [
        { persona_id: 31, persona_name: 'Bram', thumbnail_url: '', resonance_id: 4 },
      ],
    });
    const line = page.getByTestId('pose-unit').first();
    await expect(line.getByText(/gate swings in/)).toBeVisible();
    await expect(line.getByTestId('entry-endorsed-indicator')).toBeVisible();
    await page.waitForTimeout(500);
    expect(retrieves).toBe(1);
    await page.screenshot({ path: shot('e9-live-entrance-endorsed.png') });
  });

  test('E10: a disguised author is re-read once and then shows the entry control', async ({
    page,
  }) => {
    const connection = await openScene(page);
    let retrieves = 0;
    let release: () => void = () => {};
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    await page.route('**/api/interactions/924/', async (route) => {
      retrieves += 1;
      await gate;
      await route.fulfill({
        json: retrieveRow({
          id: 924,
          content: ENTRY_POSE,
          pose_kind: 'entry',
          endorsee_sheet_id: 77,
        }),
      });
    });
    sendPose(connection, {
      id: 924,
      content: ENTRY_POSE,
      pose_kind: 'entry',
      endorsee_sheet_id: null,
      endorsable_resonances: RESONANCES,
    });
    const line = page.getByTestId('pose-unit').first();
    await expect(line.getByText(/gate swings in/)).toBeVisible();
    await expect.poll(() => retrieves).toBe(1);
    await expect(line.getByTestId('endorsement-control-entry')).toHaveCount(0);
    release();
    await expect(
      line.getByTestId('endorsement-control-entry').getByRole('button', { name: 'Endorse entry' })
    ).toBeVisible();
    await page.waitForTimeout(500);
    expect(retrieves).toBe(1);
    await page.screenshot({ path: shot('e10-disguised-author-entry-control.png') });
  });
});
