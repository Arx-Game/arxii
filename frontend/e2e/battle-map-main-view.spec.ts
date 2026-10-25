import { test, expect, type Page } from '@playwright/test';

import { mockRestRoutes, reachReadySession } from './support/gameHarness';

/**
 * #4641, reworked for #4670: the battle map is the main view of a fight, in
 * the center column, and the play sidebar sits beside it. The map must open
 * with the whole room drawn, the sidebar's resize handle (a 44px grip on touch
 * screens) must never cover it, and dragging the sidebar wider must not push
 * it under the map.
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
    area_x: null,
    area_y: null,
    area_w: null,
    area_h: null,
    terrain_name: null,
    terrain_art_url: null,
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

type Side = 'right' | 'left';

async function openBattleMap(page: Page, side: Side): Promise<void> {
  // The fixture account is id 1; the stored layout picks the sidebar's side.
  await page.addInitScript((sidebarSide) => {
    window.localStorage.setItem(
      'arx:play-preferences:v2:account:1',
      JSON.stringify({ sidebarSide })
    );
  }, side);
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
        held_positions: [],
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
  await expect(page.getByTestId('combat-main-map')).toBeVisible();
  await expect(page.getByTestId('combat-tactical-map')).toBeVisible();
  await expect(page.getByTestId('tactical-map-node-1')).toBeVisible();
}

for (const side of ['right', 'left'] as const) {
  // The handle sits on the pane's edge toward the story: left edge for a
  // right-hand sidebar, right edge for a left-hand one.
  const edge = side === 'right' ? 'left' : 'right';
  // Dragging toward the story widens the sidebar.
  const widen = side === 'right' ? -60 : 60;

  test.describe(`#4670 battle map in the main column (${side} sidebar)`, () => {
    test('the map opens with the whole room drawn in the main column', async ({ page }) => {
      await openBattleMap(page, side);
      const map = await page.getByTestId('combat-main-map').boundingBox();
      const pane = await page.locator('.play-sidebar-pane').boundingBox();
      expect(map).not.toBeNull();
      expect(pane).not.toBeNull();
      for (const node of NODES) {
        const box = await page.getByTestId(`tactical-map-node-${node.id}`).boundingBox();
        expect(box, node.name).not.toBeNull();
        expect(box!.x, `${node.name} left edge`).toBeGreaterThanOrEqual(map!.x);
        expect(box!.x + box!.width, `${node.name} right edge`).toBeLessThanOrEqual(
          map!.x + map!.width
        );
      }
      // The map and the sidebar sit side by side, never over each other.
      const apart = map!.x + map!.width <= pane!.x + 1 || pane!.x + pane!.width <= map!.x + 1;
      expect(apart).toBe(true);
    });

    test('the sidebar still resizes from its edge', async ({ page }) => {
      await openBattleMap(page, side);
      const pane = page.locator('.play-sidebar-pane');
      const before = (await pane.boundingBox())!.width;
      const handle = (await page.getByTestId('sidebar-resize').boundingBox())!;
      await page.mouse.move(handle.x + handle.width / 2, handle.y + handle.height / 2);
      await page.mouse.down();
      await page.mouse.move(handle.x + handle.width / 2 + widen, handle.y + handle.height / 2, {
        steps: 5,
      });
      await page.mouse.up();
      await expect.poll(async () => (await pane.boundingBox())!.width).toBeGreaterThan(before + 40);
      // Widening the sidebar leaves the map clear of it.
      const map = (await page.getByTestId('combat-main-map').boundingBox())!;
      const widened = (await pane.boundingBox())!;
      expect(map.x + map.width <= widened.x + 1 || widened.x + widened.width <= map.x + 1).toBe(
        true
      );
    });

    test('a touch screen gets a 44px grip at the middle of the edge only', async ({ page }) => {
      await openBattleMap(page, side);
      const coarse = await page.evaluate(() => window.matchMedia('(pointer: coarse)').matches);
      test.skip(!coarse, 'this browser reports a fine pointer');
      const handle = page.getByTestId('sidebar-resize');
      await expect(handle).toHaveAttribute('data-edge', edge);
      const grip = await handle.evaluate((el, gripEdge) => {
        const style = getComputedStyle(el, '::before');
        return { width: style.width, height: style.height, inset: style[gripEdge] };
      }, edge);
      expect(grip).toEqual({ width: '44px', height: '44px', inset: '0px' });
      // The grip lives on the sidebar's edge, which is not over the map.
      const map = (await page.getByTestId('combat-main-map').boundingBox())!;
      const box = (await handle.boundingBox())!;
      const gripLeft = box.x + box.width / 2 - 22;
      const gripRight = box.x + box.width / 2 + 22;
      expect(gripRight <= map.x + 22 || gripLeft >= map.x + map.width - 22).toBe(true);
    });
  });
}
