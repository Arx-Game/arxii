import { test, expect, type Page } from '@playwright/test';

import { mockRestRoutes, reachReadySession } from './support/gameHarness';

/**
 * #5026: the Strike picker on the built bundle with a mocked encounter payload (demo
 * Screen 1). The fixture is what the server sends a player whose parrying dagger can also
 * be thrown and who knows one fire weapon technique: the dagger offered twice (the throw at
 * its 75 percent share), an "Enchant with" row with the technique and its anima cost, and
 * the soulfray accept box when the cast carries a warning. Striking sends `combat_strike`
 * with the throw and the technique. The live-server half is
 * `thrown-and-enchanted-strike.spec.ts`.
 */

const ENCOUNTER_ID = 92;
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

const STRIKE_WEAPONS = [
  {
    item_instance_id: 61,
    name: 'Parrying dagger',
    gear_kind: 'One-Handed Melee',
    strike_skill: 'Melee Combat',
    thrown: false,
    damage_share: null,
  },
  {
    item_instance_id: 61,
    name: 'Parrying dagger',
    gear_kind: 'Thrown',
    strike_skill: 'Thrown Combat',
    thrown: true,
    damage_share: 75,
  },
  {
    item_instance_id: null,
    name: 'bare hands',
    gear_kind: 'Unarmed',
    strike_skill: 'Unarmed Combat',
    thrown: false,
    damage_share: null,
  },
];

function enchantment(soulfray: boolean) {
  return {
    backend: 'combat',
    display_name: 'Wreathe the blade',
    description: '',
    difficulty: null,
    prerequisite_met: true,
    prerequisite_reasons: [],
    check_type: { id: 1, name: 'Fire Magic Cast' },
    action_template: null,
    ref: {
      backend: 'combat',
      challenge_instance_id: null,
      approach_id: null,
      technique_id: 40,
      registry_key: null,
    },
    target_spec: null,
    enhancements: [],
    strain: null,
    action_category: 'physical',
    reach: 'adjacent',
    soulfray_warning: soulfray
      ? { stage_name: 'Fraying', stage_description: 'Your soul thins.', has_death_risk: false }
      : null,
    cast_preview: { intensity: 1, control: 1, effective_anima_cost: 4 },
    enchants_strike: true,
    enchant_damage_types: ['fire'],
  };
}

const ARCHER = {
  id: 77,
  objectdb_id: null,
  name: 'Bandit archer',
  tier: 'mook',
  health: 200,
  max_health: 200,
  soak_value: null,
  probing_threshold: null,
  phase_count: null,
  damage_multiplier: null,
  break_bar_current: null,
  break_bar_threshold: null,
  vulnerability_rounds_remaining: null,
  morale: null,
  max_morale: null,
  morale_state: 'steady',
  is_enraged: false,
  is_wall_broken: false,
  active_conditions: [],
  audere_state: null,
  thumbnail_url: '',
  thumbnail_media_url: null,
  current_square: null,
  current_position: { id: 4, name: 'Gallery' },
  mirrors_participant_id: null,
  status: 'active',
};

/** The three rows the live server recorded for an enchanted throw that hit (the real-test
 * run, `thrown-and-enchanted-strike.spec.ts`), newest first as the API returns them. */
function line(label: string, value: string, detail: string) {
  return { label, value, detail, lapsed: false };
}
function outcome(id: number, summary: string, breakdown: Record<string, unknown>) {
  return {
    id,
    character: ME,
    check_type: 1,
    pool: null,
    selected_consequence: null,
    modifier_total: 0,
    summary,
    outcome_display: [],
    modifiers: [],
    combat_interaction_id: 300,
    challenge_record_id: null,
    action_interaction_id: null,
    roll_breakdown: breakdown,
    combat_round: 1,
    created_at: '2026-11-09T02:43:00Z',
  };
}
const ROUND_ROWS = [
  outcome(3, '12 damage: 5 physical, 7 fire', {
    heading: 'Damage roll',
    lines: [
      line('Parrying dagger, thrown', '', 'weapon damage and quality, at the thrown share'),
      line('Thrown Combat', '30', 'strike skill'),
      line('Wreathe the blade, fire', '', 'technique part'),
    ],
    result: '12 damage: 5 physical, 7 fire',
    result_note: '',
  }),
  outcome(2, 'Hit, fair', {
    heading: "Hit roll against Bandit archer's defense",
    lines: [
      line('Thrown Combat', '30', 'strike skill for thrown'),
      line('Strength', '', 'stat for thrown'),
      line('Wreathe the blade', '+2', 'from the technique roll'),
    ],
    result: 'Hit, fair',
    result_note: 'then the damage roll',
  }),
  outcome(1, 'Success: +2 to hit, 4 fire', {
    heading: 'Technique roll: Wreathe the blade',
    lines: [
      line('Fire Magic', '30', 'technique skill'),
      line('Anima', '4', 'paid for this attack, hit or miss'),
    ],
    result: 'Success: +2 to hit, 4 fire',
    result_note: 'then the hit roll',
  }),
];

async function openFight(
  page: Page,
  sent: unknown[],
  soulfray: boolean,
  resolved = false
): Promise<void> {
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
          { ...participant(5, ME, 'Malvaine', 2, null), strike_weapons: STRIKE_WEAPONS },
        ],
        opponents: [ARCHER],
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
        pending_attacks: [],
      },
    });
  });
  await page.route(`**/api/actions/characters/${ME}/available/**`, (route) =>
    route.fulfill({
      json: { count: 1, next: null, previous: null, results: [enchantment(soulfray)] },
    })
  );
  if (resolved) {
    await page.route('**/api/checks/consequence-outcomes/**', (route) =>
      route.fulfill({ json: { count: 3, next: null, previous: null, results: ROUND_ROWS } })
    );
  }
  await page.route(`**/api/actions/characters/${ME}/dispatch/`, async (route) => {
    sent.push(route.request().postDataJSON());
    await route.fulfill({ json: { success: true, message: null, deferred: false } });
  });
  const emptyPage = { count: 0, next: null, previous: null, results: [] };
  for (const path of ['items/inventory/', 'items/equipped-items/', 'magic/threads/']) {
    await page.route(`**/api/${path}**`, (route) => route.fulfill({ json: emptyPage }));
  }
  await reachReadySession(page);
  const sidebarNav = page.getByRole('navigation', { name: 'Sidebar modes' });
  await sidebarNav.getByRole('button', { name: 'Combat', exact: true }).click();
  await expect(page.getByTestId('combat-rail')).toBeVisible();
}

test.describe('#5026 the Strike picker: throw and enchant', () => {
  test('the dagger is offered twice, the enchantment sits under it, and Strike sends both', async ({
    page,
  }) => {
    const sent: unknown[] = [];
    await openFight(page, sent, false);

    await page.getByTestId('leading-pick').click();
    const control = page.getByTestId('strike-control');
    await expect(control).toBeVisible();
    await expect(page.getByTestId('strike-weapon-61')).toContainText(
      'one-handed melee · Melee Combat'
    );
    await expect(page.getByTestId('strike-weapon-61-thrown')).toContainText(
      'Parrying dagger, thrownThrown Combat · 75% damage'
    );
    await expect(page.getByTestId('strike-enchant-none')).toContainText('No enchantment');
    await expect(page.getByTestId('strike-enchant-40')).toContainText(
      'Wreathe the bladefire · 4 anima'
    );

    await page.getByTestId('strike-weapon-61-thrown').click();
    await page.getByTestId('strike-enchant-40').click();
    await page
      .getByTestId('combatant-target-picker')
      .getByRole('button', { name: /Bandit archer/ })
      .click();
    if (SCREENSHOTS) {
      await control.screenshot({ path: `${SCREENSHOTS}/s01-strike-picker.png` });
      await page.screenshot({ path: `${SCREENSHOTS}/s02-game-page.png`, fullPage: true });
    }
    await page.getByTestId('strike-confirm-btn').click();
    await expect.poll(() => sent.length).toBe(1);
    expect(sent[0]).toMatchObject({
      ref: { backend: 'registry', registry_key: 'combat_strike' },
      kwargs: {
        opponent_id: 77,
        weapon_id: 61,
        thrown: true,
        technique_id: 40,
        confirm_soulfray_risk: false,
      },
    });
  });

  test('a cast with a soulfray warning shows the accept box and waits for it', async ({ page }) => {
    const sent: unknown[] = [];
    await openFight(page, sent, true);

    await page.getByTestId('leading-pick').click();
    await page.getByTestId('strike-enchant-40').click();
    await expect(page.getByTestId('soulfray-accept-gate')).toContainText('4 anima');
    if (SCREENSHOTS) {
      await page
        .getByTestId('strike-control')
        .screenshot({ path: `${SCREENSHOTS}/s03-soulfray-accept.png` });
    }
    await page.getByTestId('soulfray-accept-checkbox').check();
    await expect(page.getByTestId('soulfray-accept-checkbox')).toBeChecked();
  });

  test('the round shows the technique roll, the hit roll and the damage by type', async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1400, height: 1800 });
    await openFight(page, [], false, true);

    const section = page.getByTestId('outcome-roulette-section');
    await expect(section).toContainText('Technique roll: Wreathe the blade');
    await expect(section).toContainText('paid for this attack, hit or miss');
    await expect(section).toContainText('from the technique roll');
    await expect(section).toContainText('12 damage: 5 physical, 7 fire');
    await expect(section).toContainText('technique part');
    if (SCREENSHOTS) {
      await section.screenshot({ path: `${SCREENSHOTS}/s04-round-rolls.png` });
    }
  });
});
