import { readFileSync } from 'node:fs';

import { test, expect, type Locator, type Page } from '@playwright/test';

/**
 * IC missives (#3289), against a live server (no mocked /api/**). Runs with
 * `--config e2e.backend.config.ts`.
 *
 * Needs the rows `integration_tests.live_seeds.seed_missive_spec` writes for
 * e2e_test_account (the real-test workflow runs it after the server starts and writes the
 * ids it made to the JSON file named by MISSIVE_SEED): "Quill Lettersend" with 1000
 * coppers and a brass locket, wearing her face "the Inkwell"; and one letter already
 * delivered to her own name from "the Lantern Man" by Courier, with 25 coppers riding
 * along.
 *
 * Each step reads back what the server kept through `/api/missives/` and the purse.
 */

interface Seed {
  character_id: number;
  roster_entry_id: number;
  received_missive_id: number;
  character_name: string;
  addressed_face_name: string;
  worn_face_name: string;
  writer_face_name: string;
}

interface AttachmentRow {
  id: number;
  kind: string;
  label: string;
  resolution: string;
}

interface MissiveRow {
  id: number;
  direction: string;
  counterpart_name: string;
  own_persona_id: number;
  own_persona_name: string;
  body: string;
  in_reply_to: number | null;
  attachments: AttachmentRow[];
}

/** The documented row fields (src/world/messengers/serializers.py); nothing else. */
const ROW_FIELDS = [
  'attachments',
  'body',
  'counterpart_name',
  'direction',
  'ic_date',
  'id',
  'in_reply_to',
  'is_read',
  'method_name',
  'own_persona_id',
  'own_persona_name',
  'sent_at',
];

/** The ids the seed wrote; read when a test runs, so other configs can list this file. */
function readSeed(): Seed {
  return JSON.parse(
    readFileSync(process.env.MISSIVE_SEED ?? '/tmp/missive-seed.json', 'utf8')
  ) as Seed;
}
let SEED: Seed;
test.beforeAll(() => {
  SEED = readSeed();
});

async function logIn(page: Page) {
  await page.goto('/login');
  await page.getByPlaceholder('Username or Email').fill('e2e_test_account');
  await page.getByPlaceholder('Password').fill('TestPass123!');
  await page.getByRole('button', { name: 'Log In', exact: true }).click();
  await page.waitForURL((url) => !url.pathname.startsWith('/login'), { timeout: 15000 });
}

function missivesButton(page: Page): Locator {
  return page.getByRole('button', { name: /^Missives/ });
}

/** Play Quill in this tab, unless the reloaded page already does. */
async function enterAsQuill(page: Page) {
  const name = SEED.character_name;
  const characterButton = page
    .locator(
      `button[title="Connect as ${name}"], button[title="Switch to ${name}"], ` +
        `button[title="${name}"], button:has-text("${name}")`
    )
    .first();
  const button = missivesButton(page);
  await button.or(characterButton).first().waitFor({ timeout: 30000 });
  if (!(await button.isVisible())) await characterButton.click();
  await expect(button).toBeVisible({ timeout: 30000 });
}

async function openDrawer(page: Page): Promise<Locator> {
  await missivesButton(page).click();
  const drawer = page.getByRole('dialog', { name: 'Missives' });
  await expect(drawer).toBeVisible();
  return drawer;
}

/** One heading's group of letters in the drawer. */
function group(drawer: Locator, heading: string): Locator {
  return drawer.locator('section', {
    has: drawer.page().getByRole('heading', { name: heading, exact: true }),
  });
}

async function missiveRows(page: Page): Promise<MissiveRow[]> {
  const res = await page.request.get(`/api/missives/?entry_id=${SEED.roster_entry_id}`);
  expect(res.ok(), await res.text()).toBe(true);
  return ((await res.json()) as { results: MissiveRow[] }).results;
}

async function purseBalance(page: Page): Promise<number> {
  const res = await page.request.get(`/api/currency/purse/${SEED.character_id}/`);
  expect(res.ok(), await res.text()).toBe(true);
  return ((await res.json()) as { balance: number }).balance;
}

test.describe.configure({ mode: 'serial' });

test.describe('IC missives (#3289)', () => {
  test('a waiting letter is read and its coin accepted', async ({ page }) => {
    await logIn(page);
    await page.goto('/game');
    await enterAsQuill(page);
    const before = await purseBalance(page);

    const drawer = await openDrawer(page);
    const received = group(drawer, `To ${SEED.addressed_face_name}`);
    const letter = received.getByRole('button', { name: SEED.writer_face_name });
    await expect(letter).toBeVisible();
    await letter.click();
    await expect(received.getByText('Meet me under the bridge at dusk.')).toBeVisible();
    await expect(received.getByText('2s 5c (Waiting)')).toBeVisible();
    await page.screenshot({
      path: test.info().outputPath('01-received-letter-open.png'),
      fullPage: true,
    });

    await received.getByRole('button', { name: 'Accept', exact: true }).click();
    await expect(page.getByText('You accept what came with the missive.')).toBeVisible();
    await expect(received.getByText('2s 5c (Accepted)')).toBeVisible();

    // Read back from the server: the coin is hers and the letter says so.
    const row = (await missiveRows(page)).find((r) => r.id === SEED.received_missive_id);
    expect(row?.direction).toBe('received');
    expect(row?.attachments.map((a) => [a.kind, a.resolution])).toEqual([['coin', 'accepted']]);
    expect(await purseBalance(page)).toBe(before + 25);
    await page.screenshot({
      path: test.info().outputPath('02-coin-accepted.png'),
      fullPage: true,
    });
  });

  test('a new letter goes out with coin and the locket', async ({ page }) => {
    await logIn(page);
    await page.goto('/game');
    await enterAsQuill(page);

    let drawer = await openDrawer(page);
    await drawer.getByRole('button', { name: 'New missive', exact: true }).click();
    const compose = page.getByRole('dialog', { name: 'New missive' });
    await compose.getByLabel('To', { exact: true }).fill('Lantern');
    await compose.getByRole('button', { name: SEED.writer_face_name, exact: true }).click();
    await compose.getByLabel('Message').fill('I will be there.');
    await compose.getByLabel('Coin').fill('5c');
    await compose.getByLabel('brass locket').check();
    await compose.getByRole('button', { name: 'Send', exact: true }).click();
    await expect(page.getByText('Your missive to the Lantern Man is on its way.')).toBeVisible();

    // A fresh load, so what the drawer shows comes back from the server.
    await page.reload();
    await enterAsQuill(page);
    drawer = await openDrawer(page);
    const sent = group(drawer, 'Sent');
    await sent.getByRole('button', { name: SEED.writer_face_name }).first().click();
    await expect(sent.getByText('I will be there.')).toBeVisible();
    await expect(sent.getByText('5c (Waiting)')).toBeVisible();
    await expect(sent.getByText('brass locket (Waiting)')).toBeVisible();
    await page.screenshot({
      path: test.info().outputPath('03-sent-letter-waiting.png'),
      fullPage: true,
    });

    const res = await page.request.get(`/api/missives/?entry_id=${SEED.roster_entry_id}`);
    expect(res.ok()).toBe(true);
    const raw = ((await res.json()) as { results: Record<string, unknown>[] }).results;
    const row = raw.find((r) => r.body === 'I will be there.');
    expect(row, 'the new letter is listed').toBeTruthy();
    expect(Object.keys(row!).sort()).toEqual(ROW_FIELDS);
    const typed = row as unknown as MissiveRow;
    expect(typed.direction).toBe('sent');
    expect(typed.counterpart_name).toBe(SEED.writer_face_name);
    expect(typed.attachments.map((a) => [a.kind, a.label, a.resolution])).toEqual([
      ['coin', '5c', 'pending'],
      ['item', 'brass locket', 'pending'],
    ]);
  });

  test('a reply goes out under the face the letter was written to', async ({ page }) => {
    await logIn(page);
    await page.goto('/game');
    await enterAsQuill(page);

    const addressed = (await missiveRows(page)).find((r) => r.id === SEED.received_missive_id);
    expect(addressed, 'the received letter is listed').toBeTruthy();

    const drawer = await openDrawer(page);
    const received = group(drawer, `To ${SEED.addressed_face_name}`);
    await received.getByRole('button', { name: SEED.writer_face_name }).click();
    await received.getByRole('button', { name: 'Reply', exact: true }).click();

    const compose = page.getByRole('dialog', { name: `Reply to ${SEED.writer_face_name}` });
    // She wears the Inkwell, but the reply comes from the face the letter was written to.
    const from = compose.getByLabel('From');
    await expect(from).toHaveValue(String(addressed!.own_persona_id));
    await expect(from.locator('option:checked')).toHaveText(SEED.addressed_face_name);
    await page.screenshot({
      path: test.info().outputPath('04-reply-from-addressed-face.png'),
      fullPage: true,
    });
    await compose.getByLabel('Message').fill('Until dusk.');
    await compose.getByRole('button', { name: 'Send', exact: true }).click();
    await expect(page.getByText('Your missive to the Lantern Man is on its way.')).toBeVisible();

    const sent = group(drawer, 'Sent');
    await expect(sent.getByRole('button', { name: SEED.writer_face_name })).toHaveCount(2);

    const reply = (await missiveRows(page)).find((r) => r.body === 'Until dusk.');
    expect(reply?.direction).toBe('sent');
    expect(reply?.in_reply_to).toBe(SEED.received_missive_id);
    expect(reply?.own_persona_name).toBe(SEED.addressed_face_name);
    await page.screenshot({
      path: test.info().outputPath('05-reply-sent.png'),
      fullPage: true,
    });
  });
});
