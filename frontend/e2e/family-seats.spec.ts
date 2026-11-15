import { readFileSync } from 'node:fs';

import { test, expect, type Page } from '@playwright/test';

/**
 * Joining an established family through an open seat (#5130), against a live server (no
 * mocked /api/**). Runs with `--config e2e.backend.config.ts`.
 *
 * Needs the rows `integration_tests.live_seeds.seed_family_seats_spec` writes for its
 * own account, e2e_family_seats_account (the real-test workflow seeds it after the
 * server starts and writes the ids to the JSON file named by FAMILY_SEATS_SEED): a
 * creation draft at Lineage whose route offers only an established family; House
 * Vellacourt, whose title "Seraphine" holds, with two open seats, her daughter "Isaura"
 * (name fixed) and her nephew "Corwin" (name changeable); and House Brackwater, which has
 * no seat to take.
 *
 * The page and the server have to agree for any of this to show: the list reads
 * `has_open_seat`, the cards read `head_relation` and `head_name`, and the pick writes
 * `claimed_kin_slot_id` and reads `claimed_kin_slot` back.
 */

const ACCOUNT = 'e2e_family_seats_account';
const CHOOSE = 'Choose your place in the family';

interface Seed {
  draft_id: number;
  family_id: number;
  family_name: string;
  closed_family_name: string;
  head_name: string;
  locked_seat_id: number;
  locked_seat_name: string;
  open_seat_id: number;
  open_seat_name: string;
}

interface Draft {
  family: { id: number } | null;
  claimed_kin_slot: number | null;
  stage_errors: Record<string, string[]>;
}

function readSeed(): Seed {
  return JSON.parse(
    readFileSync(process.env.FAMILY_SEATS_SEED ?? '/tmp/family-seats-seed.json', 'utf8')
  ) as Seed;
}

async function logIn(page: Page) {
  await page.goto('/login');
  await page.getByPlaceholder('Username or Email').fill(ACCOUNT);
  await page.getByPlaceholder('Password').fill('TestPass123!');
  await page.getByRole('button', { name: 'Log In', exact: true }).click();
  await page.waitForURL((url) => !url.pathname.startsWith('/login'), { timeout: 15000 });
}

/** The draft as the server holds it now. */
async function savedDraft(page: Page, seed: Seed): Promise<Draft> {
  const res = await page.request.get(`/api/character-creation/drafts/${seed.draft_id}/`);
  expect(res.ok(), await res.text()).toBe(true);
  return (await res.json()) as Draft;
}

function draftSaved(page: Page) {
  return page.waitForResponse(
    (r) => r.url().includes('/api/character-creation/drafts/') && r.request().method() === 'PATCH'
  );
}

/** Lineage is stage 3 (`Stage.LINEAGE`). */
const lineageErrors = (draft: Draft) => draft.stage_errors['3'] ?? [];

test.describe('joining an established family', () => {
  test('the house is entered through its open seat, and the server keeps the pick', async ({
    page,
  }) => {
    const seed = readSeed();
    await logIn(page);
    await page.goto('/characters/create');

    // Only the house with a seat to take is offered.
    const house = page.getByText(seed.family_name, { exact: true }).first();
    await expect(house).toBeVisible({ timeout: 20000 });
    await expect(page.getByText(seed.closed_family_name)).toHaveCount(0);

    const familySaved = draftSaved(page);
    await house.click();
    expect((await familySaved).status()).toBe(200);
    // The family alone is not a place in it.
    expect(lineageErrors(await savedDraft(page, seed))).toContain(CHOOSE);

    // The seats, read from the real endpoint: what each is to the head, and the name mark.
    const locked = page.getByRole('button', { name: new RegExp(`^${seed.locked_seat_name}`) });
    const open = page.getByRole('button', { name: new RegExp(`^${seed.open_seat_name}`) });
    await expect(locked).toBeVisible({ timeout: 15000 });
    await expect(locked).toContainText(`Child of ${seed.head_name}`);
    await expect(locked).not.toContainText('*');
    await expect(open).toContainText(`${seed.open_seat_name}*`);
    await expect(open).toContainText(`Niece or nephew of ${seed.head_name}`);
    await expect(page.getByText(/no specific position/i)).toHaveCount(0);
    await expect(page.getByText(/name set/i)).toHaveCount(0);
    await expect(page.getByText(/your parents/i)).toHaveCount(0);

    // Pick the seat: the card is pressed, and the server holds the seat.
    const seatSaved = draftSaved(page);
    await locked.click();
    await expect(locked).toHaveAttribute('aria-pressed', 'true');
    expect((await seatSaved).status()).toBe(200);
    const kept = await savedDraft(page, seed);
    expect(kept.claimed_kin_slot).toBe(seed.locked_seat_id);
    expect(lineageErrors(kept)).not.toContain(CHOOSE);

    // A fresh load reads the pick back from the saved draft.
    await page.reload();
    const reloaded = page.getByRole('button', { name: new RegExp(`^${seed.locked_seat_name}`) });
    await expect(reloaded).toHaveAttribute('aria-pressed', 'true', { timeout: 20000 });
    await page.waitForTimeout(500);
    await page.screenshot({ path: 'test-results/family-seats-5130-picked.png', fullPage: true });

    // Switching seats lets go of the first, on the page and on the server.
    const switched = draftSaved(page);
    const other = page.getByRole('button', { name: new RegExp(`^${seed.open_seat_name}`) });
    await other.click();
    await expect(other).toHaveAttribute('aria-pressed', 'true');
    await expect(reloaded).toHaveAttribute('aria-pressed', 'false');
    expect((await switched).status()).toBe(200);
    expect((await savedDraft(page, seed)).claimed_kin_slot).toBe(seed.open_seat_id);
  });
});
