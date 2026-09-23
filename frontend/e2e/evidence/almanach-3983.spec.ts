import * as path from 'node:path';
import { fileURLToPath } from 'node:url';

import { test, expect, type Locator, type Page } from '@playwright/test';

import {
  ALL_HOUSES,
  CHARTER,
  FERVOR,
  GENDERS,
  LAND_SHAPES,
  PIROPA_HOUSE_ID,
  REALM,
  REALM_ID,
  buildLadderRows,
  buildPiropaDocument,
} from './fixtures/inferna';
import { CLAIMABLE_TITLES, DRAFT_ID, FERVOR_TEMPLATE_ID, buildDraft } from './fixtures/founder';

/**
 * Review evidence for the Almanach de Catenys (#3983): renders every
 * approved plate's built surface for real — the app's own routes/
 * components, network stubbed — and screenshots it beside the plate, so the
 * `demo-fidelity-reviewer` compares the two. See
 * `.superpowers/sdd/plan-3983-b/evidence-harness-brief.md` for the full
 * screen list and `docs/reviews/almanach-3983/README.md` for the file pairs
 * and the fixture-vs-live boundary.
 *
 * Everything behind `/api/` is a fixture (`./fixtures/inferna`,
 * `./fixtures/founder`, hand-copied rather than imported at runtime from
 * `@/almanach/...` — standalone Playwright spec convention, matches
 * `game-entry.spec.ts`/`almanach-founder.spec.ts`); the pages, routes,
 * components, CSS and production build are the real app. Names/counts are
 * lifted from `staff.html`/`founder.html`'s own worked example (House
 * Piropa crowns Inferna; House Solano holds Ardor; the duchy Fervor sits
 * unclaimed with its own Arsura/Ascua seat chain plus the independently
 * claimable Solfatara/Tizón and an undefined county) so a reviewer comparing
 * a screenshot against a plate sees the same story.
 */

const DRAFT_NOTE = 'draft kept as you type';
const REVIEW_NOTE = 'Houses will be reviewed by staff before approval';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, '..', '..', '..');
const EVIDENCE_DIR = path.join(REPO_ROOT, 'docs', 'reviews', 'almanach-3983');

function evidencePath(name: string): string {
  return path.join(EVIDENCE_DIR, name);
}

/**
 * Records every `console.error` and uncaught page error so a test can fail
 * loudly rather than let a blank/broken screen through silently
 * (evidence-harness brief). Filters Chrome's own generic
 * "Failed to load resource: ... 404" line: every authenticated page here
 * also fires the app shell's own header/notification-badge polling
 * (action-requests, duel-challenges, staff-inbox, unread mail, …) that has
 * nothing to do with the Almanach screen under test and that this harness
 * deliberately doesn't mock — a 404 there is the fixture's own known
 * incompleteness, not a rendering defect. A REAL rendering error (an
 * uncaught exception, a React warning escalated to `console.error`, a
 * failed query this component actually reads) still fails the test.
 */
function trackErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on('console', (msg) => {
    if (msg.type() === 'error' && !/Failed to load resource/.test(msg.text())) {
      errors.push(msg.text());
    }
  });
  page.on('pageerror', (err) => errors.push(err.message));
  return errors;
}

async function assertTableHeaders(page: Page, headers: string[]): Promise<void> {
  const text = (
    await page.locator('table.lad thead, table.ledger thead').first().innerText()
  ).toLowerCase();
  for (const header of headers) {
    expect(text, `table headers should include "${header}"`).toContain(header.toLowerCase());
  }
}

async function assertRailHeadings(page: Page, headings: string[]): Promise<void> {
  const texts = await page.locator('aside.record h4').allTextContents();
  for (const heading of headings) {
    expect(texts, `record rail should have an "${heading}" heading`).toContain(heading);
  }
}

async function assertSavebarNote(page: Page, note: string): Promise<void> {
  await expect(page.locator('.savebar .note').first()).toContainText(note);
}

/**
 * App finding (see README "Findings for the reviewer"): the founder-
 * mounted Almanach's `.almanac` grid column carrying `main.chapter`
 * measures narrower than its content at 1280px, so `aside.record` (or one
 * of its `<li>`s) sits on top of controls near the chapter's own trailing
 * edge — confirmed on `SeatPicker`'s Claim column (F-I/F-II) and
 * `FamilyChapter`'s "add" doors (F-III onward). A normal `click()` still
 * works wherever nothing overlaps; only where it doesn't does this fall
 * back to `dispatchEvent('click')` (fires the DOM click directly on the
 * target, no coordinate hit-testing) so the founder journey's own
 * interactions can still be exercised and the screens past the overlap
 * captured, per instruction: don't fix the app, record and continue.
 */
async function safeClick(locator: Locator): Promise<void> {
  // A real `click()` attempt that fails partway (mousedown lands on the
  // overlapping `aside.record`, per the finding above) leaves the page in
  // a state where even a follow-up `dispatchEvent('click')` on the correct
  // target then hangs too — confirmed empirically. Going straight to
  // `dispatchEvent` (fires the DOM click directly on the target, no mouse
  // simulation, no actionability wait) avoids that poisoning outright.
  await locator.dispatchEvent('click');
}

const STAFF_CHARACTER = {
  id: 1,
  name: 'Archivist',
  character_id: 700,
  profile_picture_url: null,
  primary_persona_id: 700,
  active_persona_id: 700,
  unread_narrative_count: 0,
  lifecycle_state: 'ALIVE',
  roster_type: 'Active',
  character_type: 'PC',
};

/**
 * Staff Almanach routes (S-I to S-VIII): a signed-in staff account, the
 * Inferna realm/ladder/charter, House Piropa's full document, and a generic
 * 200 for the REGISTRY dispatch endpoint (`useAlmanachMutation` calls it
 * unconditionally on every render, even when a dialog never submits — see
 * `useWorldBuilderActor`). `houseDocument` lets each screen choose the
 * draft/published state the plate it matches shows.
 */
async function installStaffRoutes(
  page: Page,
  houseDocument: ReturnType<typeof buildPiropaDocument>
): Promise<void> {
  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url());
    const p = url.pathname;
    const method = route.request().method();

    if (p === '/api/user/') {
      await route.fulfill({
        json: {
          id: 1,
          username: 'staffer-e2e',
          display_name: 'Staffer',
          email: '',
          email_verified: true,
          last_login: null,
          can_create_characters: false,
          is_staff: true,
          is_gm: false,
          available_characters: [],
          pending_applications: [],
          selected_entry_id: null,
          selected_entry: null,
        },
      });
    } else if (p === '/api/roster/entries/mine/') {
      await route.fulfill({ json: [STAFF_CHARACTER] });
    } else if (p === '/api/almanach/realms/') {
      await route.fulfill({ json: { count: 1, next: null, previous: null, results: [REALM] } });
    } else if (p === `/api/almanach/realms/${REALM_ID}/ladder/`) {
      await route.fulfill({
        json: { rows: buildLadderRows(false), unclaimed_by_tier: REALM.unclaimed_by_tier },
      });
    } else if (p === `/api/almanach/realms/${REALM_ID}/charter/`) {
      await route.fulfill({ json: CHARTER });
    } else if (p === '/api/almanach/houses/') {
      await route.fulfill({
        json: { count: ALL_HOUSES.length, next: null, previous: null, results: ALL_HOUSES },
      });
    } else if (p === `/api/almanach/houses/${PIROPA_HOUSE_ID}/document/`) {
      await route.fulfill({ json: houseDocument });
    } else if (p === '/api/almanach/land-shapes/') {
      await route.fulfill({
        json: { count: LAND_SHAPES.length, next: null, previous: null, results: LAND_SHAPES },
      });
    } else if (p === '/api/character-creation/genders/') {
      await route.fulfill({ json: GENDERS });
    } else if (
      p.startsWith('/api/actions/characters/') &&
      p.endsWith('/dispatch/') &&
      method === 'POST'
    ) {
      await route.fulfill({ json: { message: 'Done.', success: true, data: null } });
    } else {
      await route.fulfill({ status: 404, json: { detail: 'Not provided by this fixture.' } });
    }
  });
}

/**
 * Founder Almanach routes (F-I to F-VI): a CG draft already at Lineage
 * stage 3 with a house-founding Upbringing, the founder-scoped realm/
 * ladder/charter/land-shapes reads, the claimable Fervor title + template,
 * and the nested house-claim GET/POST. `fervorHeld` swaps in the F-I b
 * ladder (Fervor+Arsura already held by "Candela"). Mirrors
 * `almanach-founder.spec.ts`'s own fixture/mock shape (Task 7).
 */
async function installFounderRoutes(
  page: Page,
  options: { fervorHeld?: boolean } = {}
): Promise<void> {
  const draft = buildDraft();
  let houseClaim: Record<string, unknown> | null = null;

  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url());
    const p = url.pathname;
    const method = route.request().method();

    if (p === '/api/user/') {
      await route.fulfill({
        json: {
          id: 2,
          username: 'founder-e2e',
          display_name: 'Founder E2E',
          email: '',
          email_verified: true,
          last_login: null,
          can_create_characters: true,
          is_staff: false,
          is_gm: false,
          available_characters: [],
          pending_applications: [],
          selected_entry_id: null,
          selected_entry: null,
        },
      });
    } else if (p === '/api/roster/entries/mine/') {
      await route.fulfill({ json: [] });
    } else if (p === '/api/backgrounds/') {
      await route.fulfill({ json: [] });
    } else if (p === '/api/character-creation/can-create/') {
      await route.fulfill({ json: { can_create: true, reason: '' } });
    } else if (p === '/api/character-creation/explanations/') {
      await route.fulfill({ json: {} });
    } else if (p === '/api/character-creation/drafts/' && method === 'GET') {
      await route.fulfill({ json: [draft] });
    } else if (p === `/api/character-creation/drafts/${DRAFT_ID}/` && method === 'PATCH') {
      const body = route.request().postDataJSON() as Record<string, unknown>;
      Object.assign(draft, body);
      await route.fulfill({ json: draft });
    } else if (p === '/api/character-creation/origin-templates/') {
      await route.fulfill({ json: [draft.selected_origin_template] });
    } else if (p === '/api/character-creation/families/') {
      await route.fulfill({ json: [] });
    } else if (p === '/api/character-creation/vacancies/') {
      await route.fulfill({ json: [] });
    } else if (p === '/api/character-creation/genders/') {
      await route.fulfill({ json: GENDERS });
    } else if (p === '/api/character-creation/house-titles/') {
      await route.fulfill({ json: CLAIMABLE_TITLES });
    } else if (p === `/api/character-creation/drafts/${DRAFT_ID}/house-claim/`) {
      if (method === 'GET') {
        if (houseClaim) {
          await route.fulfill({ json: houseClaim });
        } else {
          await route.fulfill({ status: 404, json: { detail: 'No house claim.' } });
        }
      } else if (method === 'POST') {
        const posted = route.request().postDataJSON() as Record<string, unknown>;
        houseClaim = {
          id: 9100,
          house_name: posted.house_name,
          title_name: 'Fervor',
          status: 'pending',
          review_note: '',
          words: posted.words,
          colors: posted.colors,
          sigil_description: posted.sigil_description,
          aspects: [],
          kin: posted.kin,
          lands: posted.lands,
          estate_name: (posted.estate as Record<string, unknown> | undefined)?.name ?? '',
          estate_description:
            (posted.estate as Record<string, unknown> | undefined)?.description ?? '',
          estate_district_id: null,
          founder_relation: posted.founder_relation,
          founder_is_heir: posted.founder_is_heir,
        };
        await route.fulfill({ status: 201, json: houseClaim });
      }
    } else if (p === '/api/almanach/realms/') {
      await route.fulfill({ json: { count: 1, next: null, previous: null, results: [REALM] } });
    } else if (p === `/api/almanach/realms/${REALM_ID}/ladder/`) {
      const rows = buildLadderRows(options.fervorHeld ?? false);
      await route.fulfill({ json: { rows, unclaimed_by_tier: REALM.unclaimed_by_tier } });
    } else if (p === `/api/almanach/realms/${REALM_ID}/charter/`) {
      await route.fulfill({ json: CHARTER });
    } else if (p === '/api/almanach/land-shapes/') {
      await route.fulfill({
        json: { count: LAND_SHAPES.length, next: null, previous: null, results: LAND_SHAPES },
      });
    } else if (p === '/api/almanach/houses/') {
      await route.fulfill({
        json: { count: ALL_HOUSES.length, next: null, previous: null, results: ALL_HOUSES },
      });
    } else {
      await route.fulfill({ status: 404, json: { detail: 'Not provided by this fixture.' } });
    }
  });
}

// ---------------------------------------------------------------------------
// Staff journey (plates S-I to S-VIII)
// ---------------------------------------------------------------------------

test.describe('Almanach de Catenys — staff', () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test('S-I realm ladder', async ({ page }) => {
    const errors = trackErrors(page);
    await installStaffRoutes(page, buildPiropaDocument(false));
    await page.goto(`/staff/almanach/realms/${REALM_ID}`);

    await expect(page.getByRole('button', { name: 'Change realm' })).toHaveText('Inferna');
    await assertTableHeaders(page, ['title', 'held by', 'sworn to', 'demesne', 'vassals']);
    await assertRailHeadings(page, ['on record', 'Charter']);
    await expect(page.getByRole('button', { name: '⊕ plant a rung' })).toBeVisible();

    await page.screenshot({ path: evidencePath('s1-built.png'), fullPage: true });
    expect(errors, errors.join('\n')).toEqual([]);
  });

  test('S-I realm ladder (phone)', async ({ page }) => {
    await page.setViewportSize({ width: 400, height: 900 });
    const errors = trackErrors(page);
    await installStaffRoutes(page, buildPiropaDocument(false));
    await page.goto(`/staff/almanach/realms/${REALM_ID}`);

    await expect(page.getByRole('button', { name: 'Change realm' })).toHaveText('Inferna');

    await page.screenshot({ path: evidencePath('s1-built-phone.png'), fullPage: true });
    expect(errors, errors.join('\n')).toEqual([]);
  });

  test('S-II plant a rung', async ({ page }) => {
    const errors = trackErrors(page);
    await installStaffRoutes(page, buildPiropaDocument(false));
    await page.goto(`/staff/almanach/realms/${REALM_ID}`);

    await page.getByRole('button', { name: 'Select Fervor' }).click();
    await page.getByRole('button', { name: '⊕ plant a rung' }).click();

    await expect(page.getByRole('heading', { name: 'Plant a rung' })).toBeVisible();
    await expect(page.getByText('Fervor', { exact: false }).first()).toBeVisible();
    await expect(page.getByRole('button', { name: 'county', exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: 'barony', exact: true })).toBeVisible();

    await page.screenshot({ path: evidencePath('s2-built.png'), fullPage: true });
    expect(errors, errors.join('\n')).toEqual([]);
  });

  test('S-III the House', async ({ page }) => {
    const errors = trackErrors(page);
    await installStaffRoutes(page, buildPiropaDocument(false));
    await page.goto(`/staff/almanach/houses/${PIROPA_HOUSE_ID}`);

    await expect(page.locator('main.chapter h3').first()).toContainText('House Piropa');
    await assertSavebarNote(page, DRAFT_NOTE);
    await assertRailHeadings(page, ['on record', 'doors']);

    await page.screenshot({ path: evidencePath('s3-built.png'), fullPage: true });
    expect(errors, errors.join('\n')).toEqual([]);
  });

  test('S-IV the Family', async ({ page }) => {
    const errors = trackErrors(page);
    await installStaffRoutes(page, buildPiropaDocument(false));
    await page.goto(`/staff/almanach/houses/${PIROPA_HOUSE_ID}`);

    await page.getByRole('button', { name: 'The Family', exact: true }).click();
    await expect(page.locator('main.chapter h3').first()).toContainText('The Family');
    await page.getByRole('button', { name: 'Marisol', exact: true }).click();
    await expect(page.getByText('hidden truth', { exact: true })).toBeVisible();
    await assertRailHeadings(page, ['on record', 'linked houses', 'doors']);

    await page.screenshot({ path: evidencePath('s4-built.png'), fullPage: true });
    expect(errors, errors.join('\n')).toEqual([]);
  });

  test('S-V Fealty', async ({ page }) => {
    const errors = trackErrors(page);
    await installStaffRoutes(page, buildPiropaDocument(false));
    await page.goto(`/staff/almanach/houses/${PIROPA_HOUSE_ID}`);

    await page.getByRole('button', { name: 'Realm', exact: true }).click();
    await expect(page.locator('main.chapter h3').first()).toContainText('Realm');
    await assertTableHeaders(page, ['vassal', 'held by', 'demesne', 'vassals']);
    await assertSavebarNote(page, DRAFT_NOTE);
    await assertRailHeadings(page, ['on record', 'doors']);

    await page.screenshot({ path: evidencePath('s5-built.png'), fullPage: true });
    expect(errors, errors.join('\n')).toEqual([]);
  });

  test('S-VI Lands', async ({ page }) => {
    const errors = trackErrors(page);
    await installStaffRoutes(page, buildPiropaDocument(false));
    await page.goto(`/staff/almanach/houses/${PIROPA_HOUSE_ID}`);

    await page.getByRole('button', { name: 'Lands', exact: false }).first().click();
    await expect(page.locator('main.chapter h3').first()).toContainText('Lands of Piropa');
    await assertTableHeaders(page, ['barony', 'in', 'hall', 'population']);
    await page.getByRole('button', { name: 'Expand Perdition' }).click();
    await expect(page.getByRole('heading', { name: /^Perdition/, level: 4 })).toBeVisible();
    await assertSavebarNote(page, DRAFT_NOTE);
    await assertRailHeadings(page, ['on record', 'doors']);

    await page.screenshot({ path: evidencePath('s6-built.png'), fullPage: true });
    expect(errors, errors.join('\n')).toEqual([]);
  });

  test('S-VII the Estate', async ({ page }) => {
    const errors = trackErrors(page);
    await installStaffRoutes(page, buildPiropaDocument(false));
    await page.goto(`/staff/almanach/houses/${PIROPA_HOUSE_ID}`);

    await page.getByRole('button', { name: 'Estate', exact: true }).click();
    await expect(page.locator('main.chapter h3').first()).toContainText('Estate');
    await expect(page.getByText('Casa Piropa')).toBeVisible();
    await assertRailHeadings(page, ['on record', 'doors']);

    await page.screenshot({ path: evidencePath('s7-built.png'), fullPage: true });
    expect(errors, errors.join('\n')).toEqual([]);
  });

  test('S-VIII Publish', async ({ page }) => {
    const errors = trackErrors(page);
    await installStaffRoutes(page, buildPiropaDocument(true));
    await page.goto(`/staff/almanach/houses/${PIROPA_HOUSE_ID}`);

    await page.getByRole('button', { name: 'published', exact: true }).click();
    await expect(page.locator('main.chapter h3').first()).toContainText('House Piropa');
    await assertTableHeaders(page, ['chapter', 'written', 'placeholder']);
    await assertSavebarNote(page, 'published');
    await expect(page.getByRole('button', { name: 'Republish' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'unpublish' })).toBeVisible();

    await page.screenshot({ path: evidencePath('s8-built.png'), fullPage: true });
    expect(errors, errors.join('\n')).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// Founder journey (plates F-I to F-VI)
// ---------------------------------------------------------------------------

async function gotoDefineHouse(page: Page): Promise<void> {
  await page.goto('/characters/create');
  await expect(page.getByText('Define a house')).toBeVisible();
}

/**
 * App finding (see README "Findings for the reviewer"): `FounderAlmanach`'s
 * `handleClaim` (`src/almanach/founder/FounderAlmanach.tsx`) calls
 * `set('title_id', …)`, `set('realm_id', …)`, `set('template_id', …)` back
 * to back — each `set` call's own `persist({ ...draft, [k]: v })`
 * (`founderDraft.ts`) spreads the SAME stale `draft` object captured when
 * `handleClaim` started, so only the LAST call's field survives; a real
 * click on "Claim Fervor" leaves `title_id`/`realm_id` reset to `null` in
 * `localStorage`, and `FounderAlmanach`'s own `template` lookup
 * (`titles.find((t) => t.id === fd.title_id)`) then permanently fails,
 * stranding the House chapter on `<p class="meta">Loading…</p>` forever —
 * confirmed by reading `localStorage['almanach-founder-900']` right after a
 * real click: `{"title_id":null,"realm_id":null,"template_id":950,...}`.
 * This is independent of, and in addition to, the S-II/F-I finding that
 * `aside.record` also overlaps the Claim button's own click target at
 * 1280px — even a click that lands cleanly still corrupts the draft.
 *
 * Neither is a harness problem, and the harness doesn't fix either: this
 * seeds the SAME `localStorage` key `handleClaim` writes to with the state
 * a *successful* claim should produce, so the House/Family/Land/Estate/
 * Record chapters — which read only the persisted draft, never how it got
 * there — can still be rendered for real and screenshotted. This is the
 * app's own declared persistence channel (`useFounderDraft`), the same
 * kind of input the route fixtures already provide; no component or route
 * behavior is touched.
 */
async function seedClaimedFervorDraft(page: Page): Promise<void> {
  const seeded = {
    realm_id: REALM_ID,
    title_id: FERVOR,
    template_id: FERVOR_TEMPLATE_ID,
    house_name: '',
    words: '',
    colors: '',
    sigil_description: '',
    backstory: '',
    aspect_picks: {},
    principles: {},
    founder_relation: 'head',
    founder_is_heir: true,
    kin: [],
    lands: {},
    estate_name: '',
    estate_description: '',
  };
  await page.addInitScript(({ key, value }) => window.localStorage.setItem(key, value), {
    key: `almanach-founder-${DRAFT_ID}`,
    value: JSON.stringify(seeded),
  });
}

async function claimFervor(page: Page): Promise<void> {
  await seedClaimedFervorDraft(page);
  await gotoDefineHouse(page);
  await expect(page.locator('#founder-house-name')).toBeVisible();
}

async function fillHouseChapter(page: Page): Promise<void> {
  await page.locator('#founder-house-name').fill('Candela');
  await page.locator('#founder-house-words').fill('Iron and Ash');
  await page.locator('#founder-house-colors').fill('Jet and gold');
  await page.locator('#founder-house-sigil').fill('A black tower wreathed in flame.');
  await page
    .locator('#founder-house-backstory')
    .fill('A frontier duchy carved from ash and ambition.');
  await safeClick(page.locator('ul.entries li', { hasText: 'The Veiled' }).getByRole('button'));
}

async function reachFamily(page: Page): Promise<void> {
  await claimFervor(page);
  await fillHouseChapter(page);
  await safeClick(page.getByRole('button', { name: 'Next', exact: true }));
  await expect(page.getByRole('heading', { name: 'The Family' })).toBeVisible();
}

async function addConsortBornIntoSolano(page: Page): Promise<void> {
  await safeClick(page.getByRole('button', { name: '⊕ a sibling · a spouse' }));
  await page.locator('#add-kin-name').fill('Dario');
  await safeClick(page.locator('#add-kin-relation'));
  await safeClick(page.getByRole('option', { name: 'spouse', exact: true }));
  await safeClick(page.locator('#add-kin-spouse'));
  await safeClick(page.getByRole('option', { name: 'Given name', exact: true }));
  await safeClick(page.locator('#add-kin-born-into'));
  await safeClick(page.getByRole('option', { name: 'Solano', exact: true }));
  await safeClick(page.getByRole('button', { name: 'Add', exact: true }));
  await expect(page.getByRole('button', { name: 'Dario', exact: true })).toBeVisible();
}

async function reachLand(page: Page): Promise<void> {
  await reachFamily(page);
  await addConsortBornIntoSolano(page);
  await safeClick(page.getByRole('button', { name: 'Next', exact: true }));
  await expect(page.getByRole('heading', { name: /^Lands of/ })).toBeVisible();
}

async function reachEstate(page: Page): Promise<void> {
  await reachLand(page);
  await page
    .locator('#founder-land-prose')
    .fill('Hill country and blackened stone, hard-won and harder held.');
  await safeClick(page.getByRole('button', { name: 'Next', exact: true }));
  await expect(page.getByRole('heading', { name: 'Estate' })).toBeVisible();
}

async function reachRecord(page: Page): Promise<void> {
  await reachEstate(page);
  await page.locator('#founder-estate-name').fill('Casa Candela');
  await page
    .locator('#founder-estate-prose')
    .fill('A narrow house on a quiet street of Perdition.');
  await safeClick(page.getByRole('button', { name: 'Next', exact: true }));
  await expect(page.getByText('Submit for review')).toBeVisible();
}

test.describe('Almanach de Catenys — founder', () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test('F-I the Seat', async ({ page }) => {
    const errors = trackErrors(page);
    await installFounderRoutes(page);
    await gotoDefineHouse(page);

    await page.getByRole('button', { name: 'Select Fervor' }).click();
    await expect(page.getByRole('button', { name: 'Change tier' })).toHaveText('Duchies');
    await expect(page.getByRole('button', { name: 'Change realm' })).toHaveText('Inferna');
    await assertTableHeaders(page, ['title', 'held by', 'sworn to', 'demesne', 'vassals']);
    await assertSavebarNote(page, REVIEW_NOTE);
    await assertRailHeadings(page, ['House Piropa', 'Inferna']);

    await page.screenshot({ path: evidencePath('f1-built.png'), fullPage: true });
    expect(errors, errors.join('\n')).toEqual([]);
  });

  test('F-I the Seat (phone)', async ({ page }) => {
    await page.setViewportSize({ width: 400, height: 900 });
    const errors = trackErrors(page);
    await installFounderRoutes(page);
    await gotoDefineHouse(page);

    await page.screenshot({ path: evidencePath('f1-built-phone.png'), fullPage: true });
    expect(errors, errors.join('\n')).toEqual([]);
  });

  test('F-I b after Fervor is held', async ({ page }) => {
    const errors = trackErrors(page);
    await installFounderRoutes(page, { fervorHeld: true });
    await gotoDefineHouse(page);

    await page.getByRole('button', { name: 'Expand Solfatara' }).click();
    await page.getByRole('button', { name: 'Select Solfatara' }).click();
    await assertRailHeadings(page, ['House Candela', 'House Piropa', 'Inferna']);
    await expect(page.getByRole('button', { name: 'Claim Solfatara' })).toBeVisible();

    await page.screenshot({ path: evidencePath('f1b-built.png'), fullPage: true });
    expect(errors, errors.join('\n')).toEqual([]);
  });

  test('F-II the House', async ({ page }) => {
    const errors = trackErrors(page);
    await installFounderRoutes(page);
    await claimFervor(page);
    await fillHouseChapter(page);

    await expect(page.getByRole('heading', { name: /^House Candela/ })).toBeVisible();
    await assertSavebarNote(page, DRAFT_NOTE);
    await assertRailHeadings(page, ['the record, so far', 'features']);

    await page.screenshot({ path: evidencePath('f2-built.png'), fullPage: true });
    expect(errors, errors.join('\n')).toEqual([]);
  });

  test('F-III the Family', async ({ page }) => {
    const errors = trackErrors(page);
    await installFounderRoutes(page);
    await reachFamily(page);
    await addConsortBornIntoSolano(page);
    await safeClick(page.getByRole('button', { name: 'Given name', exact: true }));

    await expect(page.getByRole('group', { name: 'Your place in the house' })).toBeVisible();
    await expect(page.getByText('born Solano')).toBeVisible();
    await assertSavebarNote(page, DRAFT_NOTE);
    await assertRailHeadings(page, ['the record, so far', 'features', 'linked houses']);

    await page.screenshot({ path: evidencePath('f3-built.png'), fullPage: true });
    expect(errors, errors.join('\n')).toEqual([]);
  });

  test('F-IV the Land', async ({ page }) => {
    const errors = trackErrors(page);
    await installFounderRoutes(page);
    await reachLand(page);

    await expect(page.getByRole('heading', { name: /^Fervor/, level: 4 })).toBeVisible();
    await assertTableHeaders(page, ['barony', 'in', 'hall']);
    await assertSavebarNote(page, DRAFT_NOTE);
    await assertRailHeadings(page, ['the record, so far', 'features', 'linked houses']);

    await page.screenshot({ path: evidencePath('f4-built.png'), fullPage: true });
    expect(errors, errors.join('\n')).toEqual([]);
  });

  test('F-V the Estate', async ({ page }) => {
    const errors = trackErrors(page);
    await installFounderRoutes(page);
    await reachEstate(page);

    await assertSavebarNote(page, DRAFT_NOTE);
    await assertRailHeadings(page, ['the record, so far', 'features', 'linked houses']);

    await page.screenshot({ path: evidencePath('f5-built.png'), fullPage: true });
    expect(errors, errors.join('\n')).toEqual([]);
  });

  test('F-VI the Record', async ({ page }) => {
    const errors = trackErrors(page);
    await installFounderRoutes(page);
    await reachRecord(page);

    await expect(page.getByRole('heading', { name: /^House Candela/ })).toBeVisible();
    await assertSavebarNote(page, REVIEW_NOTE);
    await page.screenshot({ path: evidencePath('f6-built.png'), fullPage: true });

    await safeClick(page.getByRole('button', { name: 'Submit for review' }));
    await expect(page.getByRole('heading', { name: 'Submitted' })).toBeVisible();
    await expect(page.getByText('House Candela')).toBeVisible();
    await expect(page.getByText('pending review')).toBeVisible();
    await page.screenshot({ path: evidencePath('f6-night-built.png'), fullPage: true });

    expect(errors, errors.join('\n')).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// Plates (the approved design) — screenshot each `.mock` reference image
// ---------------------------------------------------------------------------

/**
 * The plate source files (`staff.html`/`founder.html`, evidence-harness
 * brief) live in this session's scratchpad, not the repo — overridable via
 * `ALMANACH_PLATES_DIR` for a later run whose scratchpad path differs.
 */
const PLATES_DIR =
  process.env.ALMANACH_PLATES_DIR ??
  '/tmp/claude-1000/-workspaces-arxii/b0d08125-bc5b-4f2e-85c0-44faba4d866b/scratchpad/almanac';

test.describe('Almanach de Catenys — plates (reference)', () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test('staff plates s1-s8', async ({ page }) => {
    await page.goto(`file://${path.join(PLATES_DIR, 'staff.html')}`);
    for (const id of ['s1', 's2', 's3', 's4', 's5', 's6', 's7', 's8']) {
      await page.locator(`#${id} .mock`).screenshot({ path: evidencePath(`${id}-plate.png`) });
    }
  });

  test('founder plates f1-f6', async ({ page }) => {
    await page.goto(`file://${path.join(PLATES_DIR, 'founder.html')}`);
    for (const id of ['f1', 'f1b', 'f2', 'f3', 'f4', 'f5', 'f6']) {
      await page.locator(`#${id} .mock`).screenshot({ path: evidencePath(`${id}-plate.png`) });
    }
  });
});
