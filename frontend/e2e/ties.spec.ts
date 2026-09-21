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

import { test, expect, type Page } from '@playwright/test';

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

/** A `CharacterSheetTieLabel`. */
function tieLabel(over: Record<string, unknown>) {
  return { type_name: '', awareness: 'public', is_former: false, is_mutual: false, ...over };
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
      tieLabel({ type_name: 'Lover', awareness: 'clandestine' }),
      tieLabel({ type_name: 'Enemy', awareness: 'private' }),
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
      tieLabel({ type_name: 'Rival', is_mutual: true }),
      tieLabel({ type_name: 'Friend', is_former: true }),
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
    labels: [tieLabel({ type_name: 'Kin' })],
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
    labels: [tieLabel({ type_name: 'Mentor', is_mutual: true }), tieLabel({ type_name: 'Friend' })],
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
    await shiftBlock().getByRole('button', { name: 'Keep as is' }).click();
    await expect(page.getByText('Relationship Shift')).toHaveCount(0);

    await loverRow.getByRole('button', { name: 'Change' }).click();
    await page.getByLabel('Lover becomes').selectOption({ label: 'Betrothed' });
    await shiftBlock().getByRole('button', { name: 'Change' }).click();
    await expect.poll(() => shiftRequests.length).toBe(1);
    expect(shiftRequests[0]).toEqual({ label_id: 1, new_type_id: 4, note: '' });
    await expect(page.getByText('Relationship Shift')).toHaveCount(0);

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

    // The stream: both capstone bands (capstone status wins the band over the private
    // one's own black-journal styling), the scene, and the plain entry. Scoped to the
    // stream itself — its first entry shares a title with a capstone-picker door above.
    const stream = page.locator('.refsheet-stream');
    await expect(stream.getByText('Capstone · tier 2')).toBeVisible();
    await expect(stream.getByText('What I did not say to Corvin')).toBeVisible();
    await expect(stream.getByText('Capstone · tier 1')).toBeVisible();
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
