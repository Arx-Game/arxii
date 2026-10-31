import { test, expect, type Page } from '@playwright/test';

import { mockRestRoutes, reachReadySession } from './support/gameHarness';

/**
 * #4667 client-side proof: actual built combat rail, with isolated mocked REST.
 * This verifies rendering and query invalidation only; no live backend path is exercised.
 */
const ENCOUNTER_ID = 467;
const CHARACTER_ID = 18;
const SCREENSHOTS = process.env.EVIDENCE_DIR;
const emptyPage = { count: 0, next: null, previous: null, results: [] };

function movement(
  name: string,
  options: {
    backend?: string;
    key?: string | null;
    positionId?: number | null;
    blocked?: boolean;
    reason?: string;
  } = {}
) {
  const {
    backend = 'registry',
    key = 'move_to_position',
    positionId = 2,
    blocked = false,
    reason = '',
  } = options;
  return {
    backend,
    display_name: name,
    description: blocked ? 'A narrow gallery beyond the iron railing.' : '1 hop left this round.',
    difficulty: null,
    prerequisite_met: !blocked,
    prerequisite_reasons: blocked ? [reason] : [],
    check_type: null,
    action_template: null,
    ref: {
      backend,
      challenge_instance_id: backend === 'challenge' ? 91 : null,
      approach_id: null,
      technique_id: null,
      registry_key: key,
      position_id: positionId,
    },
    target_spec: null,
    enhancements: [],
    strain: null,
    is_movement: true,
  };
}

async function openCombat(page: Page, dispatches: unknown[]) {
  await mockRestRoutes(page, { activeEncounterId: ENCOUNTER_ID });
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
        participants: [
          {
            id: 5,
            character_sheet_id: CHARACTER_ID,
            character_name: 'Nyx',
            status: 'active',
            health: 100,
            max_health: 100,
            character_status: null,
            available_strain: null,
            fatigue: null,
            active_conditions: [],
            thumbnail_url: null,
            thumbnail_media_url: null,
            escalation_level: 0,
            intensity_modifier: 0,
            control_modifier: 0,
            current_position: { id: 1, name: 'West' },
            current_square: null,
            aftermath: null,
            reactions_used: null,
            dodge_plan: null,
          },
        ],
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
        position_nodes: [1, 2, 3].map((id) => ({
          id,
          name: ['West', 'Middle', 'Gallery'][id - 1],
          kind: id === 1 ? 'primary' : 'feature',
          elevation_anchor_id: null,
          layout_x: id * 3,
          layout_y: 1,
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
        })),
        position_edges: [
          {
            position_a_id: 1,
            position_b_id: 2,
            is_passable: true,
            blocks_flight: false,
            gating_challenge_name: 'Iron Railing',
            integrity: null,
            max_integrity: null,
          },
        ],
        position_adjacency: [],
        held_positions: [],
        pending_attacks: [],
      },
    });
  });
  await page.route(`**/api/actions/characters/${CHARACTER_ID}/available/**`, async (route) => {
    const moved = dispatches.length > 0;
    await route.fulfill({
      json: {
        count: moved ? 1 : 2,
        next: null,
        previous: null,
        results: moved
          ? [movement('Move to West', { positionId: 1 })]
          : [
              movement('Move to Middle', { positionId: 2 }),
              movement('Move to Gallery (blocked: Iron Railing)', {
                backend: 'challenge',
                key: null,
                // The server's gated entry names no place, only the challenge (#4667).
                positionId: null,
                blocked: true,
                reason: 'Gated by challenge: Iron Railing',
              }),
            ],
      },
    });
  });
  await page.route(`**/api/actions/characters/${CHARACTER_ID}/dispatch/`, async (route) => {
    dispatches.push(route.request().postDataJSON());
    await route.fulfill({
      json: { success: true, message: 'You move to Middle.', deferred: false },
    });
  });
  for (const path of ['items/inventory/', 'items/equipped-items/', 'magic/threads/']) {
    await page.route(`**/api/${path}**`, (route) => route.fulfill({ json: emptyPage }));
  }
  await reachReadySession(page);
  const sidebarNav = page.getByRole('navigation', { name: 'Sidebar modes' });
  await sidebarNav.getByRole('button', { name: 'Combat', exact: true }).click();
  await expect(page.getByTestId('combat-rail')).toBeVisible();
}

test('#4667 blocked wall is visible and successful movement refreshes actions immediately', async ({
  page,
}) => {
  const dispatches: unknown[] = [];
  let actionFetches = 0;
  page.on('request', (request) => {
    if (request.url().includes(`/api/actions/characters/${CHARACTER_ID}/available/`))
      actionFetches++;
  });
  await openCombat(page, dispatches);
  const panel = page.getByTestId('movement-section');
  const blocked = panel.getByRole('button', {
    name: /Move to Gallery.*Gated by challenge: Iron Railing/,
  });
  await expect(blocked).toBeVisible();
  await expect(blocked).toBeDisabled();
  const move = panel.getByRole('button', { name: /Move to Middle/ });
  await expect(move).toBeEnabled();
  if (SCREENSHOTS) {
    await page.screenshot({ path: `${SCREENSHOTS}/combat-movement-before.png`, fullPage: true });
    await panel.screenshot({ path: `${SCREENSHOTS}/movement-panel-before.png` });
  }
  const countBefore = actionFetches;
  await move.click();
  await expect.poll(() => dispatches.length).toBe(1);
  await expect(panel.getByRole('button', { name: /Move to West/ })).toBeVisible();
  await expect(panel.getByRole('button', { name: /Move to Middle/ })).toHaveCount(0);
  await expect.poll(() => actionFetches).toBeGreaterThan(countBefore);
  if (SCREENSHOTS) await panel.screenshot({ path: `${SCREENSHOTS}/movement-panel-after.png` });
});
