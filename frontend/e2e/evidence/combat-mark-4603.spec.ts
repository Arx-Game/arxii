import * as path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test, expect, type Page } from '@playwright/test';
import { CHARACTER, mockRestRoutes, reachReadySession } from '../support/gameHarness';

/**
 * Real-browser evidence for #4603 (players can mark a target): the production
 * bundle on `vite preview`, REST answered by stubs that carry the real
 * `EncounterDetail` shape including `marks`. No backend runs here; the server
 * half is covered by the leading-the-fight journeys.
 */
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, '..', '..', '..');
const shot = (name: string) => path.join(REPO_ROOT, 'docs', 'reviews', '4603', name);

const ENCOUNTER_ID = 77;
const MIRA_PARTICIPANT_ID = 501;
const TOMAS_PARTICIPANT_ID = 502;
const CAPTAIN_ID = 10;
const GUARD_ID = 11;

function participant(id: number, sheetId: number, name: string): Record<string, unknown> {
  return {
    id,
    character_sheet_id: sheetId,
    character_name: name,
    status: 'active',
    health: 40,
    max_health: 50,
    character_status: 'healthy',
    available_strain: null,
    fatigue: null,
    active_conditions: [],
    thumbnail_url: '',
    thumbnail_media_url: null,
    escalation_level: null,
    intensity_modifier: null,
    control_modifier: null,
    current_position: null,
    aftermath: null,
    reactions_used: null,
    reactions_remaining: null,
  };
}

function opponent(id: number, name: string, health: number): Record<string, unknown> {
  return {
    id,
    objectdb_id: null,
    name,
    description: '',
    tier: 'elite',
    level: 5,
    health,
    max_health: 60,
    soak_value: null,
    probing_current: 0,
    probing_threshold: null,
    current_phase: 1,
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
    status: 'active',
    allegiance: null,
    active_conditions: [],
    thumbnail_url: '',
    thumbnail_media_url: null,
    current_position: null,
    mirrors_participant_id: null,
  };
}

interface Viewer {
  isParticipant: boolean;
  isGm: boolean;
}

function encounterDetail(viewer: Viewer, marked: boolean): Record<string, unknown> {
  return {
    id: ENCOUNTER_ID,
    scene: 1,
    room: null,
    encounter_type: 'party_combat',
    status: 'declaring',
    outcome: '',
    completed_at: null,
    round_number: 1,
    risk_level: 'moderate',
    stakes_level: 'local',
    pace_mode: 'standard',
    pace_timer_minutes: 0,
    is_paused: false,
    round_started_at: null,
    created_at: '2026-10-23T12:00:00Z',
    participants: [
      participant(MIRA_PARTICIPANT_ID, CHARACTER.character_id, 'Mira'),
      participant(TOMAS_PARTICIPANT_ID, 19, 'Tomas'),
    ],
    opponents: [opponent(CAPTAIN_ID, 'Bandit Captain', 52), opponent(GUARD_ID, 'Bandit Guard', 38)],
    current_round_actions: [],
    surge_beats: [],
    is_participant: viewer.isParticipant,
    is_gm: viewer.isGm,
    clashes: [],
    engagement_locks: [],
    marks: marked
      ? [
          {
            id: 1,
            participant_id: MIRA_PARTICIPANT_ID,
            opponent_id: CAPTAIN_ID,
            round_number: 1,
          },
        ]
      : [],
    pending_attacks: [],
    companion_orders: [],
    resolution_order: [MIRA_PARTICIPANT_ID, TOMAS_PARTICIPANT_ID],
    escalation_curve: null,
    escalation_curve_name: null,
    escalation_start_round: null,
    escalation_tick_narration: null,
    forced_escape: false,
    position_adjacency: [],
    position_nodes: [],
    position_edges: [],
    volatile_objects: [],
    objective: null,
    pending_selections: [],
    sustained_actions: [],
    protection_commitments: [],
    standoff: null,
    gm_standoff: null,
    standoff_summary: null,
    is_lethal: false,
    duel_winner: null,
  };
}

/**
 * Boots `/game` with the encounter stubbed. `state.marked` flips on a
 * successful `combat_mark` dispatch, like the server would after the write.
 */
async function openRail(
  page: Page,
  viewer: Viewer,
  state: { marked: boolean; dispatchBody: unknown }
): Promise<void> {
  await page.setViewportSize({ width: 1500, height: 1100 });
  await mockRestRoutes(page, { activeEncounterId: ENCOUNTER_ID });
  await page.route(`**/api/combat/${ENCOUNTER_ID}/`, async (route) => {
    await route.fulfill({ json: encounterDetail(viewer, state.marked) });
  });
  // Reads the rail makes beside the encounter itself. The harness 404s anything it
  // does not know, and several of these queries throw into the error boundary on a
  // 404, which remounts the page in a loop; each gets the empty answer a quiet
  // character would see.
  const empty = { count: 0, next: null, previous: null, results: [] };
  await page.route(`**/api/combat/${ENCOUNTER_ID}/available_combos/`, (route) =>
    route.fulfill({ json: [] })
  );
  await page.route('**/api/magic/applicable-pulls/', (route) => route.fulfill({ json: [] }));
  for (const quiet of [
    'checks/consequence-outcomes/**',
    `actions/characters/${CHARACTER.character_id}/available/`,
    'items/inventory/**',
    'magic/character-anima/**',
    'magic/threads/**',
    'magic/audere/pending/',
    'magic/audere-majora/pending/',
  ]) {
    await page.route(`**/api/${quiet}`, (route) => route.fulfill({ json: empty }));
  }
  await page.route(
    `**/api/actions/characters/${CHARACTER.character_id}/dispatch/`,
    async (route) => {
      state.dispatchBody = route.request().postDataJSON();
      state.marked = true;
      await route.fulfill({ json: { success: true, message: 'You mark Bandit Captain.' } });
    }
  );
  await reachReadySession(page);
  await page
    .getByRole('navigation', { name: 'Sidebar modes' })
    .getByRole('button', { name: 'Combat', exact: true })
    .click();
  await expect(page.getByTestId('combatants-list-section')).toBeVisible();
}

test.describe.configure({ mode: 'serial' });

/** Scrolls the combatants section to the top of the rail so the floating button never covers it. */
async function bringCombatantsIntoView(page: Page): Promise<void> {
  await page
    .getByTestId('combatants-list-section')
    .evaluate((el) => el.scrollIntoView({ block: 'start' }));
}

test('the opponent menu offers Mark', async ({ page }) => {
  const state = { marked: false, dispatchBody: null as unknown };
  await openRail(page, { isParticipant: true, isGm: false }, state);
  await bringCombatantsIntoView(page);

  await page.getByTestId(`opponent-menu-trigger-${CAPTAIN_ID}`).click();
  const mark = page.getByTestId(`opponent-combat_mark-${CAPTAIN_ID}`);
  await expect(mark).toHaveText('Mark');
  // The menu fades in; capture it once it is fully opaque.
  await expect(page.getByRole('menu')).toHaveCSS('opacity', '1');
  const box = await page.getByTestId('combatants-list-section').boundingBox();
  if (box === null) throw new Error('combatants section has no box');
  await page.screenshot({
    path: shot('01-opponent-menu-mark-4603.png'),
    clip: { x: box.x - 20, y: box.y - 10, width: box.width + 40, height: 440 },
  });
});

test('marking the captain sends combat_mark and the row reads Marked by Mira', async ({ page }) => {
  const state = { marked: false, dispatchBody: null as unknown };
  await openRail(page, { isParticipant: true, isGm: false }, state);

  await page.getByTestId(`opponent-menu-trigger-${CAPTAIN_ID}`).click();
  await page.getByTestId(`opponent-combat_mark-${CAPTAIN_ID}`).click();

  const captain = page.getByTestId(`opponent-row-${CAPTAIN_ID}`);
  await expect(captain.getByTestId('mark-badge')).toHaveText('Marked by Mira');
  expect(state.dispatchBody).toEqual({
    ref: { backend: 'registry', registry_key: 'combat_mark' },
    kwargs: { opponent_id: CAPTAIN_ID },
  });
  await expect(page.getByTestId(`opponent-row-${GUARD_ID}`).getByTestId('mark-badge')).toHaveCount(
    0
  );
  await expect(page.getByRole('menu')).toHaveCount(0);
  await bringCombatantsIntoView(page);
  await page
    .getByTestId('combatants-list-section')
    .screenshot({ path: shot('02-marked-by-badge-4603.png') });
});

test('a GM sees the badge and no menu', async ({ page }) => {
  const state = { marked: true, dispatchBody: null as unknown };
  await openRail(page, { isParticipant: false, isGm: true }, state);

  const captain = page.getByTestId(`opponent-row-${CAPTAIN_ID}`);
  await expect(captain.getByTestId('mark-badge')).toHaveText('Marked by Mira');
  await expect(page.getByTestId(`opponent-menu-trigger-${CAPTAIN_ID}`)).toHaveCount(0);
  await bringCombatantsIntoView(page);
  await page
    .getByTestId('combatants-list-section')
    .screenshot({ path: shot('03-gm-sees-the-badge-4603.png') });
});

test('the badge reads in the dark theme', async ({ page }) => {
  await page.addInitScript(() => window.localStorage.setItem('theme', 'dark'));
  const state = { marked: true, dispatchBody: null as unknown };
  await openRail(page, { isParticipant: true, isGm: false }, state);

  await expect(page.locator('html')).toHaveClass(/dark/);
  await expect(page.getByTestId(`opponent-row-${CAPTAIN_ID}`).getByTestId('mark-badge')).toHaveText(
    'Marked by Mira'
  );
  await bringCombatantsIntoView(page);
  await page
    .getByTestId('combatants-list-section')
    .screenshot({ path: shot('04-marked-by-badge-dark-4603.png') });
});
