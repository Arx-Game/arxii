/**
 * Ties, redrawn (#3957): the real `CharacterSheetPage` cast and the real `TiePage`
 * mounted at their real routes, with `/api/**` intercepted. Fixtures mirror the demo
 * (https://claude.ai/artifact/... "Ties, Redrawn"): Ilsavet du Verane (sheet 20, roster
 * entry 1) and her tie toward Corvin Ashe (tie 7, sheet 12) — Lover, clandestine, and
 * Enemy, private — alongside four more cast cards.
 *
 * Nothing here needs a backend, so this spec also serves as the demo-fidelity evidence
 * harness (set EVIDENCE_DIR to write the screenshots the review report cites). Three
 * runs, matching the demo's "Seen by" toggle: Ilsavet herself (owner — every number and
 * every door), Corvin (the other side — the shared label and the depth, no Affection
 * row and no doors), and a stranger (three cards with no numbers; tie 7 itself 404s,
 * since nothing on it is Public).
 *
 * Run with: cd frontend && pnpm playwright test e2e/ties.spec.ts
 */

import { test, expect, type Locator, type Page } from '@playwright/test';

const EVIDENCE_DIR = process.env.EVIDENCE_DIR ?? '';

const ENTRY_ID = 1;
const SHEET_ID = 20;
const CORVIN_SHEET_ID = 12;
const TIE_ID = 7;

/** The viewer's account, mirroring the journals harness's shape for `/api/user/`. */
function accountPayload(staff = false) {
  return {
    id: 1,
    username: 'ilsavet',
    display_name: 'Ilsavet',
    email: '',
    email_verified: true,
    last_login: null,
    can_create_characters: false,
    is_staff: staff,
    is_gm: false,
    available_characters: [],
    pending_applications: [],
    selected_entry_id: null,
    selected_entry: null,
  };
}

/** `/api/roster/entries/mine/` — the `MyRosterEntry` shape. */
const ILSAVET_MINE = {
  id: ENTRY_ID,
  name: 'Ilsavet du Verane',
  character_id: SHEET_ID,
  profile_picture_url: null,
  primary_persona_id: 9,
  active_persona_id: 9,
  unread_narrative_count: 0,
  lifecycle_state: 'ALIVE',
  roster_type: 'Active',
  character_type: 'PC',
};

/** `/api/roster/entries/1/` — the `RosterEntryData` shape. */
const ILSAVET_ENTRY = {
  id: ENTRY_ID,
  character: { id: SHEET_ID, name: 'Ilsavet du Verane', galleries: [] },
  profile_picture: null,
  tenures: [],
  can_apply: false,
  fullname: 'Ilsavet du Verane',
  quote: 'Nothing in this city is lost.',
  description: '',
  creation_provenance: 'player',
  creation_provenance_display: 'Player-created',
  created_for_table_name: null,
};

let nextLabelId = 1;

/**
 * A `CharacterSheetTieLabel`. `valence` colours the chip, so every fixture carries it,
 * and `label_id` is what the cast keys the chip on (#3957) — unique per fixture row.
 */
function tieLabel(over: Record<string, unknown>) {
  return {
    label_id: nextLabelId++,
    type_name: '',
    awareness: 'public',
    valence: 'neutral',
    is_former: false,
    is_mutual: false,
    ...over,
  };
}

/** Ilsavet's cast, owner-shaped: every card, every number (#3957 demo, Screen 1). */
const OWNER_CAST = [
  {
    relationship_id: TIE_ID,
    other_name: 'Corvin Ashe',
    other_sheet_id: CORVIN_SHEET_ID,
    other_entry_id: 34,
    other_companion_id: null,
    labels: [
      tieLabel({ type_name: 'Lover', awareness: 'clandestine', valence: 'warm' }),
      tieLabel({ type_name: 'Enemy', awareness: 'private', valence: 'hostile' }),
    ],
    depth: 340,
    tier: 2,
    summary_line: '',
    thread: null,
  },
  {
    relationship_id: 8,
    other_name: 'The Widow Marrow',
    other_sheet_id: 13,
    other_entry_id: 35,
    other_companion_id: null,
    labels: [
      tieLabel({ type_name: 'Rival', is_mutual: true, valence: 'hostile' }),
      tieLabel({ type_name: 'Friend', is_former: true, valence: 'warm' }),
    ],
    depth: 610,
    tier: 2,
    summary_line: '',
    thread: 'Thread, level 2, Silence',
  },
  {
    relationship_id: 9,
    other_name: 'Tam du Verane',
    other_sheet_id: 14,
    other_entry_id: 36,
    other_companion_id: null,
    labels: [tieLabel({ type_name: 'Kin', valence: 'warm' })],
    depth: 140,
    tier: 1,
    summary_line: '',
    thread: null,
  },
  {
    relationship_id: 10,
    other_name: 'Master Orsun Hale',
    other_sheet_id: 15,
    other_entry_id: 37,
    other_companion_id: null,
    labels: [
      tieLabel({ type_name: 'Mentor', is_mutual: true }),
      tieLabel({ type_name: 'Friend', valence: 'warm' }),
    ],
    depth: 88,
    tier: 1,
    summary_line: '',
    thread: null,
  },
  {
    relationship_id: 11,
    other_name: 'Pell',
    other_sheet_id: null,
    other_entry_id: null,
    other_companion_id: 5,
    labels: [tieLabel({ type_name: 'Companion' })],
    depth: 12,
    tier: 0,
    summary_line: '',
    thread: null,
  },
];

/**
 * A stranger's cast: Corvin (no Public label) and Pell (a companion, self-only) are not
 * on the list at all; the other three keep their Public labels but trade numbers for the
 * server's summary line (#3957 demo, Screen 1's stranger-only text).
 */
const STRANGER_CAST = [
  {
    ...OWNER_CAST[1],
    depth: null,
    tier: null,
    summary_line: 'Has the seal. Says she does not.',
  },
  {
    ...OWNER_CAST[2],
    depth: null,
    tier: null,
    summary_line: 'Does not know what the shop is for.',
  },
  {
    ...OWNER_CAST[3],
    depth: null,
    tier: null,
    summary_line: 'Priced her first secret.',
  },
];

/** A minimal-but-complete `CharacterSheetPayload` (mirrors CharacterSheetPage.test.tsx's makeSheet()). */
function sheetPayload(ties: unknown[], tiesApThisWeek: number | null) {
  return {
    id: SHEET_ID,
    can_edit: false,
    identity: {
      name: 'Ilsavet du Verane',
      fullname: 'Ilsavet du Verane',
      concept: "A pawnbroker's daughter.",
      quote: 'Nothing in this city is lost.',
      age: 27,
      birthday: null,
      chronological_age: null,
      biological_age: null,
      withered_years: null,
      gender: { id: 1, name: 'Woman' },
      pronouns: { subject: 'she', object: 'her', possessive: 'hers' },
      species: { id: 2, name: 'Human' },
      heritage: null,
      beginnings: [{ id: 5, name: 'A Caretaker of Arx' }],
      family: null,
      tarot_card: null,
      origin: null,
      path: null,
      worship: null,
      worship_sincere: null,
      current_mood: null,
      vacancy: null,
    },
    appearance: {
      height_inches: null,
      height_band: 'Tall',
      build: null,
      description: '',
      form_traits: [],
    },
    stats: {},
    skills: [],
    path: null,
    distinctions: [],
    magic: null,
    story: { background: '', origin_story_state: 'NOT_STARTED', origin_slots: [] },
    actor_sheet: {
      never_do: '',
      protect: '',
      fear: '',
      enemy_public_line: '',
      enemy: null,
      introductions: [],
    },
    goals: [],
    personas: [],
    theming: {},
    profile_picture: null,
    current_residence: null,
    looks: [],
    plate_ink: 'ember',
    worn: [],
    mentors: [],
    domains: [],
    keyring: [],
    standing: { memberships: [], reputations: [] },
    covenants: [],
    ties,
    ties_ap_this_week: tiesApThisWeek,
  };
}

/** A `RelationshipLabel`, for the tie-page (not the cast) payload. */
function relationshipLabel(over: Record<string, unknown>) {
  return {
    id: 1,
    type: 3,
    type_name: '',
    type_family: 'heart',
    type_valence: 'warm',
    awareness: 'public',
    since: '1012-09-01T00:00:00Z',
    ended_at: null,
    replaced_type_name: null,
    note: '',
    is_mutual: false,
    ...over,
  };
}

const TIE_SUMMARY =
  'He was waiting at the north gate the first time as though he had happened to be there, ' +
  'and he has been happening to be there ever since. He thinks the harbor is a ledger; it ' +
  'is a throat, and he has his hand on it without knowing whose. She has let him finish ' +
  'three times now. She counts them the way he counts his corrections.';

/** Tie 7, Ilsavet -> Corvin, OWNER-shaped: every number, both labels (#3957 demo, Screens 2-3). */
function tieOwner() {
  return {
    id: TIE_ID,
    source: SHEET_ID,
    target: 91,
    target_companion: null,
    target_name: 'Corvin Ashe',
    other_sheet_id: CORVIN_SHEET_ID,
    other_entry_id: 34,
    audience: 'owner',
    // The write blocks gate on this, never on `audience` (#3957 review round 1) —
    // staff reading someone else's tie are `audience: 'staff'` but do not own the side.
    is_own_side: true,
    labels: [
      relationshipLabel({
        id: 1,
        type: 3,
        type_name: 'Lover',
        type_family: 'heart',
        type_valence: 'warm',
        awareness: 'clandestine',
        since: '1012-09-01T00:00:00Z',
        replaced_type_name: 'Friend',
        // Not flagged mutual: the demo's own Screen 2/3 markup carries no "mutual" marker
        // on this label (unlike the Widow Marrow's Rival or Orsun's Mentor).
        is_mutual: false,
      }),
      relationshipLabel({
        id: 2,
        type: 9,
        type_name: 'Enemy',
        type_family: 'contest',
        type_valence: 'hostile',
        awareness: 'private',
        since: '1012-09-22T00:00:00Z',
      }),
      // An ended label stays on the card, quieter — nothing in this feature deletes. Its
      // type id is deliberately outside the catalogue above, so it neither counts as held
      // in the picker nor collides with a type the shift select offers.
      relationshipLabel({
        id: 3,
        type: 20,
        type_name: 'Friend',
        type_family: 'company',
        type_valence: 'warm',
        awareness: 'public',
        since: '1011-01-05T00:00:00Z',
        ended_at: '1012-01-05T00:00:00Z',
      }),
    ],
    depth: 340,
    next_tier_threshold: 500,
    breakdown: {
      tier: 2,
      scenes: 48,
      invested: 184,
      their_added_depth: 108,
      affection: 41,
      conflict: 28,
    },
    summary: TIE_SUMMARY,
    ap_this_week: 9,
    // The week's whole purse, the demo's "31 / 40" beside the AP field (Screen 3).
    ap_pool: { remaining: 31, total: 40 },
    thread: null,
    is_soul_tether: false,
  };
}

/**
 * The SAME tie, OTHER_SIDE-shaped: only the shared Lover label (Enemy is Ilsavet's
 * private label, so Corvin never learns of it), the pooled depth and tier (parties-only),
 * no Affection/Conflict (self-only) and no AP (owner-only).
 */
function tieOther() {
  const owner = tieOwner();
  return {
    ...owner,
    audience: 'other_side',
    is_own_side: false,
    labels: [owner.labels[0]],
    breakdown: { ...owner.breakdown, affection: null, conflict: null },
    ap_this_week: null,
    ap_pool: null,
  };
}

/** The stream under tie 7: two capstones (different tiers), one scene, one plain entry. */
const TIE_STREAM = [
  {
    kind: 'entry',
    id: 501,
    title: 'What I did not say to Corvin',
    author_id: SHEET_ID,
    author_name: 'Ilsavet du Verane',
    body:
      'I let him finish. That is the whole of my restraint tonight, and it cost me more than ' +
      'the tolls will. If I write the rest of this down I will have to admit I was afraid of ' +
      'him, so I will not.',
    is_public: false,
    is_capstone: true,
    capstone_tier: 2,
    created_at: '2026-09-22T00:00:00Z',
    ic_timestamp: '1012-09-22T00:00:00Z',
  },
  {
    kind: 'entry',
    id: 502,
    title: 'Third correction',
    author_id: CORVIN_SHEET_ID,
    author_name: 'Corvin Ashe',
    body:
      'The Lady du Verane corrected me before the council for the third time this season. ' +
      'The third was a performance, and I have decided to admire it, since I cannot yet ' +
      'answer it.',
    is_public: true,
    is_capstone: true,
    capstone_tier: 1,
    created_at: '2026-09-18T00:00:00Z',
    ic_timestamp: '1012-09-18T00:00:00Z',
  },
  {
    kind: 'scene',
    id: 503,
    title: 'Tolls and other promises',
    author_id: null,
    author_name: 'A scene, both present',
    body: 'Forty-one poses. Credited both sides this week.',
    is_public: true,
    is_capstone: false,
    capstone_tier: null,
    created_at: '2026-09-16T00:00:00Z',
    ic_timestamp: '1012-09-16T00:00:00Z',
  },
  {
    kind: 'entry',
    id: 504,
    title: 'Corvin, at the gate',
    author_id: SHEET_ID,
    author_name: 'Ilsavet du Verane',
    body: 'He was waiting at the north gate as though he had happened to be there. He had not happened to be there.',
    is_public: true,
    is_capstone: false,
    capstone_tier: null,
    created_at: '2026-09-01T00:00:00Z',
    ic_timestamp: '1012-09-01T00:00:00Z',
  },
];

/**
 * The label catalogue `RelationshipShift`'s picker reads. `Lover` (held, so excluded
 * from its own picker) and `Betrothed` share the Heart family — the demo's own
 * "Lover becomes Betrothed" example (#3957 demo, Screen 3).
 */
const RELATIONSHIP_TYPES = [
  {
    id: 3,
    name: 'Lover',
    slug: 'lover',
    description: 'Together, and not hiding it from yourself.',
    family: 'heart',
    valence: 'warm',
    counterpart: null,
    counterpart_name: 'Lover',
    display_order: 1,
  },
  {
    id: 4,
    name: 'Betrothed',
    slug: 'betrothed',
    description: 'Promised.',
    family: 'heart',
    valence: 'warm',
    counterpart: null,
    counterpart_name: 'Betrothed',
    display_order: 2,
  },
  {
    id: 9,
    name: 'Enemy',
    slug: 'enemy',
    description: 'Open hostility. Opens antagonism when mutual.',
    family: 'contest',
    valence: 'hostile',
    counterpart: null,
    counterpart_name: 'Enemy',
    display_order: 3,
  },
  // Three more families, so the picker photograph shows what the demo's Screen 3 shows:
  // groups side by side, each type's authored line, and a counterpart where there is one.
  {
    id: 5,
    name: 'Comrade',
    slug: 'comrade',
    description: 'Stood beside in danger.',
    family: 'company',
    valence: 'warm',
    counterpart: null,
    counterpart_name: 'Comrade',
    display_order: 4,
  },
  {
    id: 6,
    name: 'Ward',
    slug: 'ward',
    description: 'In their keeping. Pairs with Guardian.',
    family: 'blood_and_oath',
    valence: 'neutral',
    counterpart: 7,
    counterpart_name: 'Guardian',
    display_order: 5,
  },
  {
    id: 8,
    name: 'Mentor',
    slug: 'mentor',
    description: 'Teaches you. Pairs with Student.',
    family: 'teaching',
    valence: 'neutral',
    counterpart: 12,
    counterpart_name: 'Student',
    display_order: 6,
  },
];

interface Scenario {
  /** `CharacterSheetPage`'s ties cast, or null if this run never visits the sheet. */
  cast: unknown[] | null;
  apThisWeek: number | null;
  /** True when the caller's own roster includes entry 1 (drives `isMyCharacter`). */
  ownEntry: boolean;
  /** The tie-7 fixture this run's `/api/relationships/relationships/7/` answers with, or
   * null to answer 404 (the "nothing on it is Public" case). */
  tie: ReturnType<typeof tieOwner> | null;
}

/**
 * Installs one `/api/**` handler answering every request this page mount makes.
 * Returns `shiftRequests`, which the POST .../shift/ branch appends every body to, so a
 * test can assert what the Relationship Shift door actually sent.
 */
async function mockApi(page: Page, scenario: Scenario): Promise<{ shiftRequests: unknown[] }> {
  const shiftRequests: unknown[] = [];
  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;

    if (path === '/api/relationships/relationships/shift/' && route.request().method() === 'POST') {
      shiftRequests.push(route.request().postDataJSON());
      return route.fulfill({ json: { success: true, message: '', data: {} } });
    }

    if (path === '/api/user/') {
      return route.fulfill({ json: accountPayload() });
    }
    if (path === '/api/roster/entries/mine/') {
      return route.fulfill({ json: scenario.ownEntry ? [ILSAVET_MINE] : [] });
    }
    if (path === `/api/roster/entries/${ENTRY_ID}/`) {
      return route.fulfill({ json: ILSAVET_ENTRY });
    }
    if (path === `/api/character-sheets/${SHEET_ID}/`) {
      return route.fulfill({ json: sheetPayload(scenario.cast ?? [], scenario.apThisWeek) });
    }
    if (path === `/api/relationships/relationships/${TIE_ID}/`) {
      if (!scenario.tie) return route.fulfill({ status: 404, json: { detail: 'Not found.' } });
      return route.fulfill({ json: scenario.tie });
    }
    if (path === `/api/relationships/relationships/${TIE_ID}/stream/`) {
      return route.fulfill({ json: TIE_STREAM });
    }
    if (path === '/api/relationships/relationships/' && url.searchParams.get('is_soul_tether')) {
      // useMyTetherBonds — no soul tether on this cast.
      return route.fulfill({ json: { count: 0, next: null, previous: null, results: [] } });
    }
    if (path === '/api/relationships/types/') {
      return route.fulfill({
        json: {
          count: RELATIONSHIP_TYPES.length,
          next: null,
          previous: null,
          results: RELATIONSHIP_TYPES,
        },
      });
    }
    if (path === `/api/roster/kin/tree/${SHEET_ID}/`) {
      // KinshipPanel, the Ties tab's own Kin rail (not part of #3957, but on the same
      // tab) — an empty tree so the panel settles instead of loading forever.
      return route.fulfill({ json: { family: null, nodes: [], parentage: [], unions: [] } });
    }
    if (path === '/api/personas/') {
      return route.fulfill({
        json: {
          count: 1,
          next: null,
          previous: null,
          results: [{ id: 91, persona_type: 'primary' }],
        },
      });
    }
    if (path === '/api/journals/entries/') {
      return route.fulfill({
        json: {
          count: 1,
          next: null,
          previous: null,
          results: [{ id: 601, title: 'What I did not say to Corvin' }],
        },
      });
    }
    if (path === '/api/narrative/my-messages/') {
      // The Header's unread-narrative badge — `throwOnError`, so this must be a real 200.
      return route.fulfill({ json: { count: 0, next: null, previous: null, results: [] } });
    }
    if (path === '/api/magic/rituals/sessions/') {
      // The Header's ritual-session inbox — `throwOnError`, likewise.
      return route.fulfill({ json: [] });
    }
    if (path.startsWith('/api/worship/')) {
      return route.fulfill({ json: [] });
    }
    if (path.startsWith('/api/vitals/')) {
      return route.fulfill({ status: 404, json: { detail: 'Not provided by this fixture.' } });
    }
    if (path === '/api/species/my-languages/') {
      return route.fulfill({ json: [] });
    }
    if (path === '/api/achievements/persona-titles/') {
      return route.fulfill({ json: [] });
    }
    if (path === '/api/roster/mail/unread-count/') {
      return route.fulfill({ json: { count: 0 } });
    }
    return route.fulfill({ status: 404, json: { detail: 'Not provided by this fixture.' } });
  });
  return { shiftRequests };
}

async function shot(page: Page, name: string): Promise<void> {
  if (!EVIDENCE_DIR) return;
  await page.screenshot({ path: `${EVIDENCE_DIR}/${name}.png`, fullPage: true });
}

/**
 * The mechanical companion to the demo-fidelity review (#3957): a `.refsheet-*` colour
 * token that resolves to the ground behind it is invisible, and three of the review's
 * six findings were exactly that. Screenshots caught them because a human looked; these
 * assertions catch the next one without anybody looking.
 *
 * Resolved values only — `getComputedStyle` in the real browser, on the real cascade, so
 * a rule that does not REACH the page fails here the way it fails the reader (#3667).
 */
function channel(value: number): number {
  const scaled = value / 255;
  return scaled <= 0.03928 ? scaled / 12.92 : ((scaled + 0.055) / 1.055) ** 2.4;
}

function luminance(rgb: string): number {
  const parts = (rgb.match(/[\d.]+/g) ?? []).slice(0, 3).map(Number);
  const [red, green, blue] = parts.length === 3 ? parts : [0, 0, 0];
  return 0.2126 * channel(red) + 0.7152 * channel(green) + 0.0722 * channel(blue);
}

function contrastRatio(ink: string, ground: string): number {
  const a = luminance(ink);
  const b = luminance(ground);
  return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
}

/**
 * One element's resolved ink and the ground actually painted behind it — the nearest
 * ancestor with a non-transparent background, which is what the eye sees.
 */
async function inkAndGround(locator: Locator): Promise<{ ink: string; ground: string }> {
  return locator.first().evaluate((element) => {
    const ink = getComputedStyle(element).color;
    let node: HTMLElement | null = element as HTMLElement;
    while (node) {
      const background = getComputedStyle(node).backgroundColor;
      if (background && !/rgba?\(0, 0, 0, 0\)|transparent/.test(background)) {
        return { ink, ground: background };
      }
      node = node.parentElement;
    }
    return { ink, ground: 'rgb(255, 255, 255)' };
  });
}

/**
 * `minimum` is 4.5 for a chip or a door — WCAG's small-text bar, and the one that tells
 * the two states apart: the paper palette measured 3.3:1 on the plate's ground while
 * the demo's own literals measure 10.4:1. An eyebrow is 13px tracked caps and its gilt
 * measures 3.5:1 on paper, so 3 is its bar; what it has to be told from is the realm
 * token resolving to 1.1:1, not from a slightly darker gold.
 */
async function expectReadable(locator: Locator, what: string, minimum = 4.5): Promise<void> {
  const { ink, ground } = await inkAndGround(locator);
  const ratio = contrastRatio(ink, ground);
  expect(ratio, `${what}: ${ink} on ${ground}`).toBeGreaterThanOrEqual(minimum);
}

/** The exact ink the demo specifies, resolved on the page. */
async function expectInk(locator: Locator, expected: string, what: string): Promise<void> {
  const { ink } = await inkAndGround(locator);
  expect(ink, what).toBe(expected);
}

test.describe('Ties, redrawn (#3957)', () => {
  test('the cast and the tie page, as the owner (Ilsavet)', async ({ page }) => {
    const { shiftRequests } = await mockApi(page, {
      cast: OWNER_CAST,
      apThisWeek: 12,
      ownEntry: true,
      tie: tieOwner(),
    });

    await page.goto(`/characters/${ENTRY_ID}`);
    await page.getByRole('button', { name: 'Ties' }).click();

    // The ledger line, and every card's name.
    await expect(page.getByText('5 ties · 12 AP this week')).toBeVisible();
    await expect(page.getByRole('link', { name: 'Corvin Ashe' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'The Widow Marrow' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Tam du Verane' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Master Orsun Hale' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Pell' })).toBeVisible();

    // Corvin's card: both labels, the numbers, no thread line (none was set).
    await expect(page.getByText('Lover · Clandestine')).toBeVisible();
    await expect(page.getByText('Enemy · Private')).toBeVisible();
    await expect(page.getByText('Depth 340 · Tier 2')).toBeVisible();

    // The Widow Marrow's card: a mutual public label, a former one, and the thread line.
    await expect(page.getByText('Rival · mutual')).toBeVisible();
    await expect(page.getByText('Friend · former')).toBeVisible();
    await expect(page.getByText('Depth 610 · Tier 2')).toBeVisible();
    await expect(page.getByText('Thread, level 2, Silence')).toBeVisible();

    // The private chip carries its own ink (`.tag.secret`'s purple), so it is readable
    // on the cast where no valence used to colour it at all — it read near-white on
    // white paper before (demo-fidelity Finding 1).
    const corvinCard = page.locator('.refsheet-face', { hasText: 'Corvin Ashe' });
    await expectReadable(corvinCard.locator('.refsheet-tag-private'), 'cast private chip');

    // A marker takes the chip whole, so valence does not show through it: clandestine is
    // the demo's gilt `.tag.shared` and a former label is muted, even though both of
    // these carry `refsheet-tag-warm` as well (#3957 re-check, new findings 1 and 2).
    await expectInk(
      corvinCard.locator('.refsheet-tag-clandestine'),
      'rgb(163, 134, 62)',
      'cast clandestine chip'
    );
    const marrowCard = page.locator('.refsheet-face', { hasText: 'The Widow Marrow' });
    await expectInk(
      marrowCard.locator('.refsheet-tag-former'),
      'rgb(113, 113, 122)',
      'cast former chip'
    );

    await shot(page, 'ties-cast-owner');

    // Open the tie page from the card.
    await page.getByRole('link', { name: 'Corvin Ashe' }).click();
    await expect(page).toHaveURL(`/characters/${ENTRY_ID}/ties/${TIE_ID}`);

    await expect(page.getByRole('heading', { name: 'Corvin Ashe' })).toBeVisible();
    await expect(page.getByText('Ilsavet du Verane and')).toBeVisible();
    await expect(page.getByRole('button', { name: /340/ })).toBeVisible();
    await expect(page.getByText('Tier 2', { exact: true })).toBeVisible();
    await expect(page.getByText(TIE_SUMMARY)).toBeVisible();
    await expect(page.getByRole('button', { name: 'Edit' })).toBeVisible();
    await expect(page.getByText('Thread: none yet.')).toBeVisible();

    // Labels and AP: the AP field, both labels' markers (bare — no date, since
    // `RelationshipLabel.since` is a posting timestamp, not in-character prose) and
    // doors, and the "Replaced Friend" gloss the demo's Screen 3 carries. Both labels
    // carry Change/End/Make public; only the private Enemy also carries Make clandestine.
    await expect(page.getByLabel('AP this week')).toHaveValue('9');
    // The week's budget beside it, bare (#3957 demo, Screen 3).
    await expect(page.getByText('31 / 40')).toBeVisible();
    await expect(page.getByText('Clandestine', { exact: true })).toBeVisible();
    await expect(page.getByText('Private', { exact: true })).toBeVisible();
    await expect(page.getByText('Replaced Friend')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Change' })).toHaveCount(2);
    await expect(page.getByRole('button', { name: 'End' })).toHaveCount(2);
    await expect(page.getByRole('button', { name: 'Make public' })).toHaveCount(2);
    await expect(page.getByRole('button', { name: 'Make clandestine' })).toHaveCount(1);

    // Advance Relationship Tier: the ratio, the cost line, and a disabled Advance (no
    // capstone picked yet).
    await expect(page.getByText('Advance Relationship Tier')).toBeVisible();
    // The depth button above prints the same "340 / 500" — this is the Advance block's
    // own ratio line, which comes second in the DOM.
    await expect(page.getByText('340 / 500').last()).toBeVisible();
    await expect(page.getByText('Cost: 10xp * tier level.')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Advance' })).toBeDisabled();

    // The plate paints its chips and its doors in its own literals: the paper palette
    // does not survive `--plate-ground` (demo-fidelity Finding 2), and the off-plate
    // eyebrows take the sheet's fallback gilt rather than the realm token that resolves
    // to near-white when no realm is set (Finding 6).
    const plate = page.locator('.refsheet-plate');
    await expectReadable(plate.locator('.refsheet-tag-warm'), 'plate warm chip');
    // By colour, not by contrast: a near-white private chip would be readable on the
    // night ground and still wrong. #c8a6f0 is the demo's own literal (`ties.html:90`),
    // and before the fix this chip took `--destructive` red from the valence rule that
    // followed it.
    await expectInk(
      plate.locator('.refsheet-tag-private'),
      'rgb(200, 166, 240)',
      'plate private chip'
    );
    // The plate's own literals for the same two markers (`ties.html:141, :143`).
    await expectInk(
      plate.locator('.refsheet-tag-clandestine'),
      'rgb(224, 194, 122)',
      'plate clandestine chip'
    );
    await expectInk(
      plate.locator('.refsheet-tag-former'),
      'rgb(201, 184, 163)',
      'plate former chip'
    );
    await expectReadable(plate.getByRole('button', { name: 'Edit' }), 'plate Edit door');
    await expectReadable(
      page.locator('.refsheet-eyebrow', { hasText: 'Advance Relationship Tier' }),
      'off-plate eyebrow',
      3
    );

    await shot(page, 'ties-page-owner');

    // Relationship Shift: Change on a label opens it (its own eyebrow, the "becomes"
    // line, the type picker); Keep as is closes it without writing; picking a type and
    // its own Change submits the shift and closes it on success. Scoped to the Lover
    // row for the opening click (Change is ambiguous across both labels), and to the
    // shift block itself once open (its own submit door is ALSO labelled "Change").
    const loverRow = page.locator('.refsheet-entry', { hasText: 'Lover' });
    // `.refsheet-block` nests: LabelsAndAp's own root also "has" this text, as an
    // ancestor of the shift block — `.last()` lands on the innermost match, the shift
    // block's own root, since a parent always precedes its descendant in DOM order.
    const shiftBlock = () =>
      page.locator('.refsheet-block', { hasText: 'Relationship Shift' }).last();

    await loverRow.getByRole('button', { name: 'Change' }).click();
    await expect(shiftBlock().getByText('Relationship Shift')).toBeVisible();
    await expect(shiftBlock().getByText('Lover becomes')).toBeVisible();
    await expect(page.getByLabel('Lover becomes')).toBeVisible();
    await shot(page, 'ties-shift-open');
    await shiftBlock().getByRole('button', { name: 'Keep as is' }).click();
    await expect(page.getByText('Relationship Shift')).toHaveCount(0);

    await loverRow.getByRole('button', { name: 'Change' }).click();
    await page.getByLabel('Lover becomes').selectOption({ label: 'Betrothed' });
    await shiftBlock().getByRole('button', { name: 'Change' }).click();
    await expect.poll(() => shiftRequests.length).toBe(1);
    expect(shiftRequests[0]).toEqual({ label_id: 1, new_type_id: 4, note: '' });
    await expect(page.getByText('Relationship Shift')).toHaveCount(0);

    // The type picker, open: five families' worth of authored lines, each type's
    // counterpart where it has one, and the awareness pills under them. Photographed
    // because the demo's Screen 3 draws it and nothing else in this harness did.
    await page.getByRole('button', { name: 'Declare another' }).click();
    const picker = page.locator('.refsheet-picker');
    await expect(picker.getByText('Betrothed')).toBeVisible();
    await expect(picker.getByText('Promised.')).toBeVisible();
    // Families in the catalogue's own order, and the counterpart line under a paired type.
    await expect(picker.getByText('Heart')).toBeVisible();
    await expect(picker.getByText('Company')).toBeVisible();
    await expect(picker.getByText('Blood and oath')).toBeVisible();
    await expect(picker.getByText('Teaching')).toBeVisible();
    // Exact: each type's authored line also ends "Pairs with Guardian."/"with Student."
    await expect(picker.getByText('with Guardian', { exact: true })).toBeVisible();
    await expect(picker.getByText('with Student', { exact: true })).toBeVisible();
    // Choosing a type raises the awareness pills, at Private — the demo's own default,
    // and the one thing about declaring that has to be visible before it is pressed.
    await picker.getByRole('button', { name: 'Betrothed' }).click();
    await expect(page.getByRole('button', { name: 'Private' })).toHaveAttribute(
      'aria-pressed',
      'true'
    );
    await shot(page, 'ties-picker-open');
    await page.getByRole('button', { name: 'Declare another' }).click();
    await expect(picker).toHaveCount(0);

    // The breakdown panel: Tier, Scenes, Invested, Their Added Depth, and — owner only —
    // Affection and Conflict. Scoped to the popover: "Scenes" also names one of the
    // stream's own filter pills further down the page.
    await page.getByRole('button', { name: /340/ }).click();
    await expect(page.getByRole('button', { name: /340/ })).toHaveAttribute(
      'aria-expanded',
      'true'
    );
    const breakdown = page.locator('.refsheet-depth-pop');
    await expect(breakdown.getByText('Scenes')).toBeVisible();
    await expect(breakdown.getByText('Invested')).toBeVisible();
    await expect(breakdown.getByText('Their Added Depth')).toBeVisible();
    await expect(breakdown.getByText('Affection')).toBeVisible();
    await expect(breakdown.getByText('Conflict')).toBeVisible();
    await expect(breakdown.getByText('41')).toBeVisible();
    await expect(breakdown.getByText('28')).toBeVisible();

    // The stream: both capstone bands, naming the writer and the tier in words the way
    // the demo does — and the black one says BOTH things, since a capstone that is also
    // a black entry is not one or the other. The scene and the plain entry follow.
    // Scoped to the stream itself — its first entry shares a title with a
    // capstone-picker door above.
    const stream = page.locator('.refsheet-stream');
    await expect(
      stream.getByText("Capstone · Ilsavet's second tier · Black journal")
    ).toBeVisible();
    await expect(stream.getByText('What I did not say to Corvin')).toBeVisible();
    await expect(stream.getByText("Capstone · Corvin's first tier")).toBeVisible();
    await expect(stream.getByText('Tolls and other promises')).toBeVisible();
    await expect(stream.getByText('Corvin, at the gate')).toBeVisible();

    await shot(page, 'ties-page-owner-breakdown');
  });

  test('the tie page, as the other side (Corvin)', async ({ page }) => {
    await mockApi(page, { cast: null, apThisWeek: null, ownEntry: false, tie: tieOther() });

    await page.goto(`/characters/${ENTRY_ID}/ties/${TIE_ID}`);

    await expect(page.getByRole('heading', { name: 'Corvin Ashe' })).toBeVisible();
    await expect(page.getByText('Ilsavet du Verane and')).toBeVisible();

    // The shared label only — Enemy is Ilsavet's private label, so Corvin never sees it.
    await expect(page.getByText('Lover · Clandestine')).toBeVisible();
    await expect(page.getByText('Enemy')).toHaveCount(0);

    // Depth and tier are parties-only, so both parties see them.
    await expect(page.getByRole('button', { name: /340/ })).toBeVisible();
    await expect(page.getByText('Tier 2', { exact: true })).toBeVisible();
    await expect(page.getByText(TIE_SUMMARY)).toBeVisible();

    // No write surface at all for the other side.
    await expect(page.getByLabel('AP this week')).toHaveCount(0);
    await expect(page.getByText('Advance Relationship Tier')).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Declare another' })).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Edit' })).toHaveCount(0);

    await shot(page, 'ties-page-other');

    // The breakdown still opens (parties-only values), but Affection/Conflict are gone —
    // those are self-only.
    await page.getByRole('button', { name: /340/ }).click();
    await expect(page.getByText('Their Added Depth')).toBeVisible();
    await expect(page.getByText('Affection')).toHaveCount(0);
    await expect(page.getByText('Conflict')).toHaveCount(0);
  });

  test('the cast, as a stranger, and the tie itself 404s', async ({ page }) => {
    await mockApi(page, { cast: STRANGER_CAST, apThisWeek: null, ownEntry: false, tie: null });

    await page.goto(`/characters/${ENTRY_ID}`);
    await page.getByRole('button', { name: 'Ties' }).click();

    // No AP line — just the count.
    await expect(page.getByText('3 ties')).toBeVisible();
    await expect(page.getByText(/AP this week/)).toHaveCount(0);

    // Corvin (no Public label) and Pell (self-only) are not on the list at all.
    await expect(page.getByText('Corvin Ashe')).toHaveCount(0);
    await expect(page.getByText('Pell')).toHaveCount(0);

    // The three remaining cards keep their Public labels but carry the summary line
    // instead of a number, and "Depth" never appears anywhere on the page.
    await expect(page.getByRole('link', { name: 'The Widow Marrow' })).toBeVisible();
    await expect(page.getByText('Has the seal. Says she does not.')).toBeVisible();
    await expect(page.getByText('Does not know what the shop is for.')).toBeVisible();
    await expect(page.getByText('Priced her first secret.')).toBeVisible();
    await expect(page.getByText(/Depth/)).toHaveCount(0);

    // Every label on the three visible cards is Public already — the stranger sees the
    // same chips the owner does — and nothing Clandestine or Private ever leaks to them.
    await expect(page.getByText('Rival · mutual')).toBeVisible();
    await expect(page.getByText('Friend · former')).toBeVisible();
    // Scoped to the card: "Kin" bare is also the rail block's own heading further down.
    const tamCard = page.locator('.refsheet-face', { hasText: 'Tam du Verane' });
    await expect(tamCard.getByText('Kin', { exact: true })).toBeVisible();
    await expect(page.getByText('Mentor · mutual')).toBeVisible();
    await expect(page.getByText('Friend', { exact: true })).toBeVisible();
    await expect(page.getByText(/Clandestine/)).toHaveCount(0);
    await expect(page.getByText(/Private/)).toHaveCount(0);

    await shot(page, 'ties-cast-stranger');

    // Tie 7 itself: nothing on it is Public, so it 404s and renders as not-found rather
    // than a refusal that would leak the tie's existence.
    await page.goto(`/characters/${ENTRY_ID}/ties/${TIE_ID}`);
    await expect(page.getByText('Tie not found.')).toBeVisible();
  });
});
