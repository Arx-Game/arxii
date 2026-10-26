import { test, expect, type Page } from '@playwright/test';

import { mockRestRoutes, reachReadySession } from './support/gameHarness';

/**
 * #4676 (slice 4 of #4651): the dodge plan in Your Turn (demo Screen 3) and a wound-up
 * attack that covers the place you stand in (demo Screen 4), on the built bundle with a
 * mocked encounter payload. The fixture is the payload the server sends a player who
 * stands on the Floor while Holy fire winds up over it: her own `dodge_plan` and the
 * pending attack's covered place. Clicking a choice sends `combat_dodge` with the
 * landing.
 */

const ENCOUNTER_ID = 91;
const ME = 18; // the harness character's sheet id
const SCREENSHOTS = process.env.EVIDENCE_DIR;

function place(id: number, name: string, area: [number, number, number, number]) {
  return {
    id,
    name,
    kind: 'feature',
    elevation_anchor_id: null,
    layout_x: null,
    layout_y: null,
    area_x: area[0],
    area_y: area[1],
    area_w: area[2],
    area_h: area[3],
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

const NODES = [
  place(1, 'Doorway', [0, 2, 2, 3]),
  place(2, 'Floor', [2, 0, 6, 7]),
  place(3, 'Stage', [8, 0, 5, 4]),
  place(4, 'Gallery', [13, 0, 4, 3]),
];
const EDGES = [
  [1, 2],
  [2, 3],
  [3, 4],
].map(([a, b]) => ({
  position_a_id: a,
  position_b_id: b,
  is_passable: true,
  blocks_flight: false,
  gating_challenge_name: null,
  integrity: null,
  max_integrity: null,
}));

function participant(id: number, sheet: number, name: string, positionId: number, plan: unknown) {
  return {
    id,
    character_sheet_id: sheet,
    character_name: name,
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
    current_position: { id: positionId, name: NODES[positionId - 1].name },
    current_square: null,
    aftermath: null,
    reactions_used: sheet === ME ? 1 : null,
    dodge_plan: plan,
  };
}

const PLAN = {
  enabled: true,
  landing_id: null,
  options: [
    { id: 2, name: 'Floor' },
    { id: 1, name: 'Doorway' },
    { id: 3, name: 'Stage' },
  ],
  cost_line: 'Each dodge costs 1 fatigue. Each dodge after the first this round is harder.',
};

async function openFight(page: Page, sent: unknown[]): Promise<void> {
  await mockRestRoutes(page, { activeEncounterId: ENCOUNTER_ID });
  await page.route(`**/api/combat/${ENCOUNTER_ID}/`, async (route) => {
    await route.fulfill({
      json: {
        id: ENCOUNTER_ID,
        scene: 1,
        encounter_type: 'party_combat',
        status: 'declaring',
        round_number: 2,
        is_participant: true,
        is_gm: false,
        participants: [
          participant(5, ME, 'Malvaine', 2, PLAN),
          participant(6, 31, 'Bram', 2, null),
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
        position_nodes: NODES,
        position_edges: EDGES,
        position_adjacency: [],
        held_positions: [],
        pending_attacks: [
          {
            id: 9,
            opponent_id: 40,
            opponent_name: 'Harrow',
            target_participant_id: 6,
            target_name: 'Bram',
            declared_round: 1,
            resolves_round: 2,
            rounds_until_landing: 0,
            downgrades: 0,
            called_out: false,
            damage_scale: 1,
            cancelled: false,
            attack_name: 'Holy fire',
            covered_position_id: 2,
            covered_position_name: 'Floor',
          },
        ],
      },
    });
  });
  await page.route(`**/api/actions/characters/${ME}/dispatch/`, async (route) => {
    sent.push(route.request().postDataJSON());
    await route.fulfill({ json: { success: true, message: null, deferred: false } });
  });
  const emptyPage = { count: 0, next: null, previous: null, results: [] };
  for (const path of ['items/inventory/', 'items/equipped-items/', 'magic/threads/']) {
    await page.route(`**/api/${path}**`, (route) => route.fulfill({ json: emptyPage }));
  }
  await reachReadySession(page);
  await expect(page.getByTestId('combat-main-map')).toBeVisible();
  const sidebarNav = page.getByRole('navigation', { name: 'Sidebar modes' });
  await sidebarNav.getByRole('button', { name: 'Combat', exact: true }).click();
  await expect(page.getByTestId('combat-rail')).toBeVisible();
}

test.describe('#4676 dodging and area attacks', () => {
  test('the map marks the covered place and Your Turn warns, plans and sends', async ({ page }) => {
    const sent: unknown[] = [];
    await openFight(page, sent);

    const telegraph = page.getByTestId('area-telegraph-2');
    await expect(telegraph).toBeVisible();
    await expect(telegraph).toContainText('Holy fire lands here at the end of this round');

    const warning = page.getByTestId('area-attack-warning');
    await expect(warning).toContainText('Holy fire will cover the whole Floor when it lands.');
    await expect(warning).toContainText(
      "Leaning aside won't help. Get out of the Floor, or take it."
    );
    await expect(warning.getByRole('button', { name: 'Leap clear to Stage' })).toBeVisible();
    await expect(warning.getByRole('button', { name: 'Brace' })).toBeVisible();

    const plan = page.getByTestId('dodge-plan');
    await expect(plan).toContainText("If you're attacked this round");
    await expect(plan.getByRole('button', { name: 'Dodge in place' })).toHaveAttribute(
      'aria-pressed',
      'true'
    );
    await expect(plan.getByRole('button', { name: 'Dodge to Stage' })).toBeVisible();
    await expect(plan.getByRole('button', { name: "Don't dodge" })).toBeVisible();
    await expect(plan).toContainText(PLAN.cost_line);
    await expect(page.getByTestId('reaction-availability')).toContainText(
      'Malvaine: 1 reaction this round'
    );

    if (SCREENSHOTS) {
      await page.screenshot({ path: `${SCREENSHOTS}/e01-game-page.png`, fullPage: true });
      await page
        .getByTestId('combat-main-map')
        .screenshot({ path: `${SCREENSHOTS}/e02-map-telegraph.png` });
      await warning.screenshot({ path: `${SCREENSHOTS}/e03-warning.png` });
      await plan.screenshot({ path: `${SCREENSHOTS}/e04-dodge-plan.png` });
    }

    await warning.getByRole('button', { name: 'Leap clear to Stage' }).click();
    await expect.poll(() => sent.length).toBe(1);
    expect(sent[0]).toMatchObject({
      ref: { backend: 'registry', registry_key: 'combat_dodge' },
      kwargs: { position_id: 3 },
    });
    await plan.getByRole('button', { name: "Don't dodge" }).click();
    await expect.poll(() => sent.length).toBe(2);
    expect(sent[1]).toMatchObject({ kwargs: { dodge: false } });
  });
});
