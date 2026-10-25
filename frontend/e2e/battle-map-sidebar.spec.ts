import { test, expect, type Page } from '@playwright/test';

import { mockRestRoutes, reachReadySession } from './support/gameHarness';

/**
 * #4641: the battle map in the play sidebar. The sidebar's resize handle used
 * to be a 44px strip over the pane's inner edge, on top of the map's zoom and
 * fit buttons, and the map opened showing three of a room's ten positions.
 */

const ENCOUNTER_ID = 77;
const ROOM = [
  'Yard',
  'Lane',
  'Barn',
  'Above Lane',
  'Well',
  'Gate',
  'Orchard',
  'Loft',
  'Ditch',
  'Path',
];

function positionNode(id: number, name: string) {
  return {
    id,
    name,
    kind: id === 1 ? 'primary' : 'feature',
    elevation_anchor_id: null,
    layout_x: null,
    layout_y: null,
    rampart_element: null,
    rampart_integrity: null,
    rampart_max_integrity: null,
    rampart_crack_state: null,
    is_roofed: false,
    screens_ranged: false,
  };
}

const NODES = ROOM.map((name, index) => positionNode(index + 1, name));
// Two rings around the yard: five positions off it, four more beyond those.
const LINKS: [number, number][] = [
  [1, 2],
  [1, 3],
  [1, 4],
  [1, 5],
  [1, 6],
  [2, 7],
  [3, 8],
  [4, 9],
  [5, 10],
];
const EDGES = LINKS.map(([a, b]) => ({
  position_a_id: a,
  position_b_id: b,
  is_passable: true,
  blocks_flight: false,
  gating_challenge_name: null,
  integrity: null,
  max_integrity: null,
}));

async function openBattleMap(page: Page): Promise<void> {
  await mockRestRoutes(page, { activeEncounterId: ENCOUNTER_ID });
  // Registered after the harness's catch-all, so it wins for this path.
  await page.route(`**/api/combat/${ENCOUNTER_ID}/`, async (route) => {
    await route.fulfill({
      json: {
        id: ENCOUNTER_ID,
        scene: 1,
        encounter_type: 'party_combat',
        status: 'declaring',
        round_number: 1,
        is_participant: true,
        is_gm: false,
        participants: [],
        opponents: [],
        current_round_actions: [],
        surge_beats: [],
        clashes: [],
        engagement_locks: [],
        resolution_order: [],
        forced_escape: false,
        is_lethal: false,
        duel_winner: null,
        outcome: '',
        completed_at: null,
        position_nodes: NODES,
        position_edges: EDGES,
        position_adjacency: [],
      },
    });
  });
  // The Your Turn panel mounts first and reads these; a 404 from either
  // throws into the page's error boundary.
  const emptyPage = { count: 0, next: null, previous: null, results: [] };
  for (const path of ['items/inventory/', 'items/equipped-items/', 'magic/threads/']) {
    await page.route(`**/api/${path}**`, (route) => route.fulfill({ json: emptyPage }));
  }
  await reachReadySession(page);
  await page
    .getByRole('navigation', { name: 'Sidebar modes' })
    .getByRole('button', { name: 'Combat', exact: true })
    .click();
  await page.getByTestId('rail-tab-map').click();
  await expect(page.getByTestId('tactical-map-node-1')).toBeVisible();
}

test.describe('#4641 battle map in the sidebar', () => {
  test('the map opens with the whole room inside the visible sidebar', async ({ page }) => {
    await openBattleMap(page);
    const pane = await page.locator('.play-sidebar-pane').boundingBox();
    expect(pane).not.toBeNull();
    for (const node of NODES) {
      const box = await page.getByTestId(`tactical-map-node-${node.id}`).boundingBox();
      expect(box, node.name).not.toBeNull();
      expect(box!.x, `${node.name} left edge`).toBeGreaterThanOrEqual(pane!.x);
      expect(box!.x + box!.width, `${node.name} right edge`).toBeLessThanOrEqual(
        pane!.x + pane!.width
      );
    }
  });

  test('the zoom and fit buttons take a real mouse click', async ({ page }) => {
    await openBattleMap(page);
    const yard = page.getByTestId('tactical-map-node-1');
    const before = await yard.boundingBox();
    // A plain click, no force: it fails if anything sits over the button.
    await page.locator('.react-flow__controls-zoomin').click();
    await expect.poll(async () => (await yard.boundingBox())!.width).toBeGreaterThan(before!.width);
    await page.locator('.react-flow__controls-fitview').click();
    await expect
      .poll(async () => (await yard.boundingBox())!.width)
      .toBeLessThan(before!.width + 1);
  });

  test('the sidebar still resizes from its edge', async ({ page }) => {
    await openBattleMap(page);
    const pane = page.locator('.play-sidebar-pane');
    const before = (await pane.boundingBox())!.width;
    const handle = (await page.getByTestId('sidebar-resize').boundingBox())!;
    await page.mouse.move(handle.x + handle.width / 2, handle.y + handle.height / 2);
    await page.mouse.down();
    await page.mouse.move(handle.x + handle.width / 2 - 60, handle.y + handle.height / 2, {
      steps: 5,
    });
    await page.mouse.up();
    await expect.poll(async () => (await pane.boundingBox())!.width).toBeGreaterThan(before + 40);
  });

  test('a touch screen gets a 44px grip at the middle of the edge only', async ({ page }) => {
    await openBattleMap(page);
    const coarse = await page.evaluate(() => window.matchMedia('(pointer: coarse)').matches);
    test.skip(!coarse, 'this browser reports a fine pointer');
    const handle = page.getByTestId('sidebar-resize');
    const grip = await handle.evaluate((el) => {
      const style = getComputedStyle(el, '::before');
      return { width: style.width, height: style.height, left: style.left };
    });
    expect(grip).toEqual({ width: '44px', height: '44px', left: '0px' });
    // The grip sits at mid-height, clear of the map's buttons at the foot.
    const controls = (await page.locator('.react-flow__controls').boundingBox())!;
    const box = (await handle.boundingBox())!;
    expect(controls.y).toBeGreaterThan(box.y + box.height / 2 + 22);
  });
});
