import * as path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test, expect, type Page, type Route } from '@playwright/test';

/**
 * Review evidence for #4229 (staff edit mode, piece E): the real `/characters/:entry`
 * sheet on the production bundle, signed in as staff, every `/api/**` call answered by
 * fixtures shaped like the serializers. Staff turn edit mode on with the header's own
 * toggle, then give a bare sheet an identity, a tie to a searched character, a covenant
 * role and a mentor bond in the rows band; each save answers with the refreshed sheet.
 */
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, '..', '..', '..');
const EVIDENCE_DIR = path.join(REPO_ROOT, 'docs', 'reviews', '4229');
const shot = (name: string) => path.join(EVIDENCE_DIR, name);

const ENTRY_ID = 1;
const SHEET_ID = 20;

const ACCOUNT = {
  id: 1,
  username: 'staff-e2e',
  display_name: 'Staff E2E',
  email: '',
  email_verified: true,
  last_login: null,
  can_create_characters: true,
  is_staff: true,
  is_gm: false,
  available_characters: [],
  pending_applications: [],
  selected_entry_id: null,
  selected_entry: null,
};

const ENTRY = {
  id: ENTRY_ID,
  character: { id: SHEET_ID, name: 'Kathryn mar Katta', galleries: [] },
  profile_picture: null,
  tenures: [],
  can_apply: false,
  fullname: 'Kathryn mar Katta',
  quote: '',
  description: '',
  creation_provenance: 'staff',
  creation_provenance_display: 'Staff-created',
  created_for_table_name: null,
};

interface GroupRows {
  personas: { id: number; name: string; persona_type: string; guise: Record<string, string> }[];
  ties: {
    other: number;
    other_name: string;
    toward: {
      id: number;
      tier: number;
      summary: string;
      labels: { id: number; type: number; name: string; awareness: string; waiting: boolean }[];
    } | null;
    back: null;
  }[];
  covenant_roles: {
    id: number;
    covenant: number;
    covenant_name: string;
    role: number;
    role_name: string;
    rank: number;
    rank_name: string;
    standing: string;
    engaged: boolean;
    is_secondary: boolean;
  }[];
  mentor_bonds: {
    id: number;
    covenant_name: string;
    other_name: string;
    as_mentor: boolean;
    warning: string;
  }[];
}

const BARE: GroupRows = { personas: [], ties: [], covenant_roles: [], mentor_bonds: [] };
const NO_GUISE = {
  concept: '',
  quote: '',
  never_do: '',
  protect: '',
  fear: '',
  background: '',
};

function stored(group: GroupRows) {
  return {
    rows: {
      stats: {},
      skills: {},
      specializations: {},
      distinctions: [],
      form: {},
      markings: [],
      beginnings: null,
      path: null,
      class_level: null,
      public_being: null,
      secret_being: null,
      has_vitals: true,
      has_gift: true,
      has_aura: false,
      kin_node: null,
      residences: [],
      properties: [],
      reputations: [],
      titles: [],
      noble_titles: [],
      ...group,
    },
    prose: {
      description: '',
      background: '',
      concept: '',
      real_concept: '',
      quote: '',
      never_do: '',
      protect: '',
      fear: '',
      obituary: '',
      glimpse: '',
    },
    name: 'Kathryn mar Katta',
    ic_birth_year: null,
    true_height_inches: null,
    weight_pounds: null,
    marital_status: 'single',
    vocation: '',
    social_rank: 10,
    build: null,
    gender: null,
    pronouns: null,
    species: null,
    heritage: null,
    origin_realm: null,
    family: null,
    tarot_card: null,
    tarot_reversed: false,
  };
}

function sheetPayload(group: GroupRows) {
  return {
    id: SHEET_ID,
    can_edit: true,
    staff_edit: stored(group),
    identity: {
      name: 'Kathryn mar Katta',
      fullname: 'Kathryn mar Katta',
      concept: '',
      quote: '',
      age: 24,
      birthday: null,
      chronological_age: null,
      biological_age: null,
      withered_years: null,
      gender: null,
      pronouns: { subject: 'she', object: 'her', possessive: 'hers' },
      species: null,
      heritage: null,
      beginnings: [],
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
      height_band: '',
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
    beats: [],
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
    ties: [],
    ties_ap_this_week: null,
  };
}

const STAFF_OPTIONS = {
  stats: [],
  skills: [],
  specializations: [],
  distinctions: [],
  form_traits: [],
  beginnings: [],
  paths: [],
  beings: [],
  marking_regions: [],
  marking_kinds: [],
  enemy_kinds: [],
  enemy_degrees: [],
  enemy_power_tiers: [],
};

const ESTATE_OPTIONS = {
  open_positions: [],
  families: [],
  rooms: [],
  grant_profiles: [],
  house_claims: [],
  vacancies: [],
  organizations: [],
};

const CHARACTERS = [{ id: 81, name: 'Ser Aldric Venn' }];

function groupOptions(character: string) {
  return {
    characters: character
      ? CHARACTERS.filter((c) => c.name.toLowerCase().includes(character.toLowerCase()))
      : [],
    faces: [{ id: 90, name: 'Kathryn mar Katta' }],
    relationship_types: [
      { id: 50, name: 'Rival' },
      { id: 51, name: 'Confidant' },
    ],
    awareness: [
      { value: 'private', label: 'Private' },
      { value: 'clandestine', label: 'Clandestine' },
      { value: 'public', label: 'Public' },
    ],
    tiers: [{ id: 1, name: 'Acquainted' }],
    title_rewards: [{ id: 55, name: 'Warden of Lamps' }],
    deeds: [],
    noble_titles: [],
    covenants: [
      {
        id: 60,
        name: 'The Lantern Oath',
        roles: [{ id: 61, name: 'Vanguard' }],
        ranks: [{ id: 62, name: 'Sworn' }],
      },
    ],
  };
}

/** The sheet as the server would answer after each staff save. */
async function mockSheet(page: Page) {
  let group: GroupRows = { ...BARE };
  const writes: { path: string; body: unknown }[] = [];
  await page.route('**/api/**', async (route: Route) => {
    const request = route.request();
    const url = new URL(request.url());
    const p = url.pathname;
    const base = `/api/character-sheets/${SHEET_ID}`;
    if (p === '/api/user/') return route.fulfill({ json: ACCOUNT });
    if (p === '/api/roster/entries/mine/') return route.fulfill({ json: [] });
    if (p === `/api/roster/entries/${ENTRY_ID}/`) return route.fulfill({ json: ENTRY });
    if (p === `${base}/`) return route.fulfill({ json: sheetPayload(group) });
    if (p === `${base}/staff-options/`) return route.fulfill({ json: STAFF_OPTIONS });
    if (p === `${base}/staff-estate-options/`) return route.fulfill({ json: ESTATE_OPTIONS });
    if (p === `${base}/staff-group-options/`) {
      return route.fulfill({ json: groupOptions(url.searchParams.get('character') ?? '') });
    }
    if (request.method() !== 'GET' && p.startsWith(`${base}/staff-`)) {
      const body = request.postDataJSON() as Record<string, string | number | boolean | null>;
      writes.push({ path: p.slice(base.length + 1, -1), body });
      if (p === `${base}/staff-personas/`) {
        group = {
          ...group,
          personas: [
            { id: 91, name: String(body.name), persona_type: 'established', guise: NO_GUISE },
          ],
        };
      }
      if (p === `${base}/staff-tie-labels/`) {
        group = {
          ...group,
          ties: [
            {
              other: 81,
              other_name: 'Ser Aldric Venn',
              toward: {
                id: 5,
                tier: 0,
                summary: '',
                labels: [
                  { id: 6, type: 50, name: 'Rival', awareness: 'clandestine', waiting: true },
                ],
              },
              back: null,
            },
          ],
        };
      }
      if (p === `${base}/staff-covenant-roles/`) {
        group = {
          ...group,
          covenant_roles: [
            {
              id: 7,
              covenant: 60,
              covenant_name: 'The Lantern Oath',
              role: 61,
              role_name: 'Vanguard',
              rank: 62,
              rank_name: 'Sworn',
              standing: 'core',
              engaged: false,
              is_secondary: false,
            },
          ],
        };
      }
      if (p === `${base}/staff-mentor-bonds/`) {
        group = {
          ...group,
          mentor_bonds: [
            {
              id: 8,
              covenant_name: 'The Lantern Oath',
              other_name: 'Ser Aldric Venn',
              as_mentor: false,
              warning:
                "Both parties are outside the covenant band — the in-band partner required for a Mentor's Vow is absent.",
            },
          ],
        };
      }
      return route.fulfill({ json: sheetPayload(group) });
    }
    if (p === `/api/roster/kin/tree/${SHEET_ID}/`) {
      return route.fulfill({ json: { family: null, nodes: [], parentage: [], unions: [] } });
    }
    if (
      p === '/api/relationships/types/' ||
      p === '/api/relationships/relationships/' ||
      p === '/api/personas/' ||
      p === '/api/journals/entries/' ||
      p === '/api/narrative/my-messages/'
    ) {
      return route.fulfill({ json: { count: 0, next: null, previous: null, results: [] } });
    }
    if (p === '/api/roster/mail/unread-count/') return route.fulfill({ json: { count: 0 } });
    if (p.startsWith('/api/vitals/')) {
      return route.fulfill({ status: 404, json: { detail: 'Not provided by this fixture.' } });
    }
    if (request.method() === 'GET') return route.fulfill({ json: [] });
    return route.fulfill({ status: 404, json: { detail: 'Not provided by this fixture.' } });
  });
  return writes;
}

test.describe('Staff edit mode, piece E (#4229) on the production bundle', () => {
  test('staff fit a bare sheet into a group: identity, tie, covenant and bond', async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    const writes = await mockSheet(page);
    const errors: string[] = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await page.goto(`/characters/${ENTRY_ID}`);
    await page.getByRole('switch', { name: 'Edit' }).click();

    const band = page.getByTestId('staff-rows-band');
    const identities = band.getByRole('region', { name: 'Identities' });
    await expect(identities.getByRole('button', { name: 'Add identity' })).toBeVisible();
    await identities.scrollIntoViewIfNeeded();
    await page.screenshot({ path: shot('01-bare-sheet-group-editors-1280.png'), fullPage: true });

    await identities.getByRole('textbox', { name: 'New identity name' }).fill('The Grey Lady');
    await identities.getByRole('button', { name: 'Add identity' }).click();
    await expect(identities.getByText('The Grey Lady')).toBeVisible();

    const ties = band.getByRole('region', { name: 'Ties', exact: true });
    await ties.getByRole('textbox', { name: 'Find a character' }).fill('aldric');
    await ties.getByRole('button', { name: 'Find' }).click();
    await ties.getByRole('combobox', { name: 'Character' }).selectOption('81');
    await ties.getByRole('combobox', { name: 'Relationship' }).selectOption('50');
    await ties.getByRole('combobox', { name: 'Awareness' }).selectOption('clandestine');
    await ties.getByRole('button', { name: 'Declare' }).click();
    await expect(ties.getByText('(binds at pickup)')).toBeVisible();

    const covenants = band.getByRole('region', { name: 'Covenants' });
    await covenants.getByRole('combobox', { name: 'Covenant' }).selectOption('60');
    await covenants.getByRole('combobox', { name: 'Role' }).selectOption('61');
    await covenants.getByRole('button', { name: 'Swear in' }).click();
    await expect(covenants.getByRole('button', { name: 'Engage' })).toBeVisible();

    const mentors = band.getByRole('region', { name: 'Mentor bonds' });
    await mentors.getByRole('combobox', { name: 'Bond covenant' }).selectOption('60');
    await mentors.getByRole('combobox', { name: 'Bond character' }).selectOption('81');
    await mentors.getByRole('combobox', { name: 'This character is' }).selectOption('sidekick');
    await mentors.getByRole('button', { name: 'Bond' }).click();
    await expect(mentors.getByText(/outside the covenant band/)).toBeVisible();

    await identities.scrollIntoViewIfNeeded();
    await page.screenshot({ path: shot('02-filled-group-rows-1280.png'), fullPage: true });
    expect(writes).toEqual([
      { path: 'staff-personas', body: { name: 'The Grey Lady' } },
      {
        path: 'staff-tie-labels',
        body: { other: 81, direction: 'toward', type: 50, awareness: 'clandestine' },
      },
      {
        path: 'staff-covenant-roles',
        body: { covenant: 60, covenant_role: 61, rank: null },
      },
      { path: 'staff-mentor-bonds', body: { covenant: 60, other: 81, as_mentor: false } },
    ]);
    expect(errors).toEqual([]);
  });

  test('at phone width', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 1100 });
    await mockSheet(page);
    await page.goto(`/characters/${ENTRY_ID}`);
    await page.getByRole('switch', { name: 'Edit' }).click();
    const ties = page
      .getByTestId('staff-rows-band')
      .getByRole('region', { name: 'Ties', exact: true });
    await expect(ties.getByRole('button', { name: 'Declare' })).toBeVisible();
    await ties.scrollIntoViewIfNeeded();
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth
    );
    expect(overflow).toBeLessThanOrEqual(0);
    await page.screenshot({ path: shot('03-group-editors-390.png'), fullPage: true });
  });
});
