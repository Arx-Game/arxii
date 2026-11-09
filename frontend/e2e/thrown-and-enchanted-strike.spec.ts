import { readFileSync } from 'node:fs';

import { test, expect, type Page } from '@playwright/test';

/**
 * Thrown and enchanted Strikes, and armor by damage type (#5026), against a live server
 * (no mocked /api/**). Runs with `--config e2e.backend.config.ts`.
 *
 * Needs the rows `integration_tests.live_seeds.seed_thrown_strike_spec` writes for
 * e2e_test_account (the real-test workflow runs it after the server starts and writes the
 * ids it made to the JSON file named by THROWN_STRIKE_SEED): "Strike Tester" in the Lane
 * with a throwable 8-damage parrying dagger and the 4-anima fire weapon technique "Wreathe
 * the blade"; a bandit archer two positions away in the Yard; a two-handed Greatsword and a
 * light armor coat for the admin half; and a staff account.
 *
 * The rolls are real, so the test checks what every outcome shares: the dagger offered
 * twice, the cast paid and recorded first, the hit roll on Thrown Combat, and (when it
 * hits) a damage row that names its parts.
 */

interface Seed {
  character_id: number;
  encounter_id: number;
  archer_id: number;
  dagger_id: number;
  technique_id: number;
  greatsword_template_id: number;
  coat_template_id: number;
  staff_username: string;
}

/** The ids the seed wrote; read when a test runs, so other configs can list this file. */
function readSeed(): Seed {
  return JSON.parse(
    readFileSync(process.env.THROWN_STRIKE_SEED ?? '/tmp/thrown-strike-seed.json', 'utf8')
  ) as Seed;
}
let SEED: Seed;
test.beforeAll(() => {
  SEED = readSeed();
});
const STAFF_PASSWORD = 'Ragged-Lantern-5026!';

interface RollLine {
  label: string;
  value: string;
  detail: string;
}
interface OutcomeRow {
  summary: string;
  roll_breakdown: { heading: string; lines: RollLine[]; result: string } | null;
}

async function logIn(page: Page, username: string, password: string) {
  await page.goto('/login');
  await page.getByPlaceholder('Username or Email').fill(username);
  await page.getByPlaceholder('Password').fill(password);
  await page.getByRole('button', { name: 'Log In', exact: true }).click();
  await page.waitForURL((url) => !url.pathname.startsWith('/login'), { timeout: 15000 });
}

async function csrfToken(page: Page): Promise<string> {
  const cookies = await page.context().cookies();
  return cookies.find((cookie) => cookie.name === 'csrftoken')?.value ?? '';
}

async function dispatch(page: Page, registryKey: string, kwargs: Record<string, unknown>) {
  const response = await page.request.post(
    `/api/actions/characters/${SEED.character_id}/dispatch/`,
    {
      headers: { 'X-CSRFToken': await csrfToken(page) },
      data: { ref: { backend: 'registry', registry_key: registryKey }, kwargs },
    }
  );
  expect(response.ok(), await response.text()).toBe(true);
  return (await response.json()) as { success: boolean; message: string | null };
}

test.describe('thrown and enchanted Strikes (#5026)', () => {
  test('the dagger is offered twice; an enchanted throw is paid, rolled twice and split by type', async ({
    page,
  }, testInfo) => {
    await logIn(page, 'e2e_test_account', 'TestPass123!');

    const encounter = await page.request.get(`/api/combat/${SEED.encounter_id}/`);
    expect(encounter.ok()).toBe(true);
    const payload = (await encounter.json()) as {
      participants: {
        strike_weapons:
          | { item_instance_id: number | null; thrown: boolean; damage_share: number | null }[]
          | null;
      }[];
    };
    const own = payload.participants.find((p) => p.strike_weapons !== null);
    const daggerRows = (own?.strike_weapons ?? []).filter(
      (w) => w.item_instance_id === SEED.dagger_id
    );
    expect(daggerRows.map((w) => [w.thrown, w.damage_share])).toEqual([
      [false, null],
      [true, 75],
    ]);

    const available = await page.request.get(
      `/api/actions/characters/${SEED.character_id}/available/?page_size=100`
    );
    expect(available.ok(), await available.text()).toBe(true);
    const actions = (await available.json()) as {
      results: {
        display_name: string;
        enchants_strike?: boolean;
        enchant_damage_types?: string[];
        cast_preview?: { effective_anima_cost: number } | null;
      }[];
    };
    const enchant = actions.results.find((a) => a.display_name === 'Wreathe the blade');
    expect(enchant?.enchants_strike).toBe(true);
    expect(enchant?.enchant_damage_types).toEqual(['fire']);
    expect(enchant?.cast_preview?.effective_anima_cost).toBe(4);

    // A slash cannot reach two positions; a throw can.
    const slash = await dispatch(page, 'combat_strike', {
      opponent_id: SEED.archer_id,
      weapon_id: SEED.dagger_id,
    });
    expect(slash.success).toBe(false);
    expect(slash.message).toContain('out of reach');

    const declared = await dispatch(page, 'combat_strike', {
      opponent_id: SEED.archer_id,
      weapon_id: SEED.dagger_id,
      thrown: true,
      technique_id: SEED.technique_id,
      confirm_soulfray_risk: false,
    });
    expect(declared.success, declared.message ?? '').toBe(true);
    expect(declared.message).toContain('You ready a throw at Bandit archer');
    expect(declared.message).toContain('enchanted with Wreathe the blade');

    const ready = await dispatch(page, 'combat_ready', {});
    expect(ready.success, ready.message ?? '').toBe(true);

    const outcomes = await page.request.get(
      `/api/checks/consequence-outcomes/?character=${SEED.character_id}&encounter=${SEED.encounter_id}`
    );
    expect(outcomes.ok()).toBe(true);
    const rows = ((await outcomes.json()) as { results: OutcomeRow[] }).results.reverse();
    await testInfo.attach('roll rows', {
      body: JSON.stringify(rows, null, 2),
      contentType: 'application/json',
    });

    const [techniqueRow, hitRow, damageRow] = rows;
    expect(techniqueRow.roll_breakdown?.heading).toBe('Technique roll: Wreathe the blade');
    expect(techniqueRow.roll_breakdown?.lines).toContainEqual(
      expect.objectContaining({ label: 'Anima', value: '4' })
    );
    expect(hitRow.roll_breakdown?.lines[0].label).toBe('Thrown Combat');
    const toHitAdded = techniqueRow.roll_breakdown?.result.includes('+2 to hit') ?? false;
    if (toHitAdded) {
      expect(hitRow.roll_breakdown?.lines).toContainEqual(
        expect.objectContaining({ label: 'Wreathe the blade', detail: 'from the technique roll' })
      );
    }
    if (hitRow.roll_breakdown?.result.startsWith('Hit')) {
      expect(damageRow.roll_breakdown?.lines[0].label).toContain('thrown');
      expect(damageRow.summary).toMatch(/damage/);
      if (techniqueRow.roll_breakdown?.result.includes('fire damage')) {
        expect(damageRow.summary).toMatch(/physical, \d+ fire/);
      }
    }

    // The dagger is still in hand: next round it is offered again.
    const after = await page.request.get(`/api/combat/${SEED.encounter_id}/`);
    const afterOwn = ((await after.json()) as typeof payload).participants.find(
      (p) => p.strike_weapons !== null
    );
    expect(
      (afterOwn?.strike_weapons ?? []).filter((w) => w.item_instance_id === SEED.dagger_id)
    ).toHaveLength(2);
  });

  test('admin refuses a throwable two-handed weapon and keeps armor that also stops fire', async ({
    page,
  }) => {
    // The admin signs in through the site's own login page.
    await logIn(page, SEED.staff_username, STAFF_PASSWORD);

    await page.goto(`/admin/arxii/itemtemplate/${SEED.greatsword_template_id}/change/`);
    await page.locator('#id_can_be_thrown').check();
    await page.locator('input[name="_continue"]').click();
    await expect(page.getByText('Only one-handed melee weapons can also be thrown.')).toBeVisible();
    await page.screenshot({ path: shotPath('admin-two-handed-refused.png'), fullPage: true });

    await page.goto(`/admin/arxii/itemtemplate/${SEED.coat_template_id}/change/`);
    const fire = page.getByLabel('Fire', { exact: true });
    await fire.check();
    await page.locator('input[name="_continue"]').click();
    await expect(page.locator('.messagelist .success')).toBeVisible();
    await page.reload();
    await expect(page.getByLabel('Fire', { exact: true })).toBeChecked();
    await page.screenshot({ path: shotPath('admin-coat-protects-fire.png'), fullPage: true });
  });
});

function shotPath(name: string): string {
  return `test-results/thrown-strike-${name}`;
}
