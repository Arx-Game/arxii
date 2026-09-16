import { expect, test, type Page, type Route } from '@playwright/test';
import { mockRestRoutes } from './support/gameHarness';

// #3780: the Deity Editor's three screens over a fixture pantheon that mirrors
// the approved demo (list, edit page, tracking dashboard). Every REST surface
// the pages read is answered here; the screenshots feed the demo-fidelity review.

const SHOTS = process.env.PANTHEON_SHOTS ?? '';

const TILES = [
  {
    id: 1,
    name: 'Fleshreaper',
    tradition_name: 'Church Liturgy',
    nickname: 'the Crimson',
    domain_chips: ['Carnage', 'Bloodshed', 'Ferocity'],
    resonance_pool: 48200,
    lifetime_worship: 312900,
    visibility: 'public',
    organization_name: '',
    is_active: true,
  },
  {
    id: 2,
    name: 'Lady of the Loom',
    tradition_name: 'Spiritcalling',
    nickname: 'the Patient Weaver',
    domain_chips: ['Fate', 'Weaving'],
    resonance_pool: 6410,
    lifetime_worship: 40100,
    visibility: 'obscure',
    organization_name: 'The Silken Thread',
    is_active: true,
  },
  {
    id: 3,
    name: 'Tyrant of Chains',
    tradition_name: 'Occultism',
    nickname: 'the Horned God',
    domain_chips: ['Bondage', 'Dominion'],
    resonance_pool: 190500,
    lifetime_worship: 900000,
    visibility: 'secret',
    organization_name: '',
    is_active: true,
  },
];

const PAGE = {
  id: 1,
  name: 'Fleshreaper',
  description:
    'Goddess of carnage, wanton bloodshed, feral battle, and ferocity. Ascended after the Godswar; her worshippers say she has never once shown mercy in it, and never asked to.',
  domains: 'Carnage, wanton bloodshed, feral battle, ferocity',
  tradition: 1,
  is_active: true,
  quote: '',
  nicknames: ['the Crimson', 'Old Resting Murder Face'],
  resonances: [
    { resonance: 1, resonance_name: 'Savagery', tier: 'favored' },
    { resonance: 2, resonance_name: 'Wrath', tier: 'associated' },
  ],
  facets: [],
  feast_days: [
    {
      ic_month: 9,
      ic_day: 14,
      name: 'The Long Bleeding',
      lore: 'Marks the night she is said to have fought without rest until dawn, refusing every offered mercy.',
    },
  ],
  tarot_cards: [16, 57],
  relationships: [
    {
      other_being: 4,
      other_being_name: 'Leviathan',
      valence: 'ally',
      public_story: 'Old friends since before the Godswar.',
    },
    {
      other_being: 5,
      other_being_name: 'the God of Assassins',
      valence: 'feud',
      public_story: 'No one living knows why.',
    },
  ],
  visibility: 'public',
  organization: null,
  gm_notes: 'Was a minor NPC warlord in Arx 1 (no surviving object to link to).',
  resonance_pool: 48200,
  codex_entry: 9,
};

const OPTIONS = {
  traditions: [
    { id: 1, name: 'Church Liturgy' },
    { id: 2, name: 'Spiritcalling' },
  ],
  resonances: [
    { id: 1, name: 'Savagery' },
    { id: 2, name: 'Wrath' },
    { id: 3, name: 'Stillness' },
  ],
  facets: [{ id: 1, name: 'Scythe' }],
  tarot_cards: [
    { id: 16, name: 'The Tower' },
    { id: 57, name: 'Seven of Wands' },
  ],
  organizations: [{ id: 7, name: 'The Silken Thread' }],
  beings: [
    { id: 1, name: 'Fleshreaper' },
    { id: 4, name: 'Leviathan' },
    { id: 5, name: 'the God of Assassins' },
  ],
};

const now = new Date().toISOString();

async function mockPantheon(page: Page): Promise<void> {
  await mockRestRoutes(page, { staff: true });
  await page.route('**/api/worship/admin/beings/**', async (route: Route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    if (path === '/api/worship/admin/beings/') {
      const wanted = url.searchParams.get('visibility');
      const results = wanted ? TILES.filter((t) => t.visibility === wanted) : TILES;
      await route.fulfill({ json: { count: results.length, next: null, previous: null, results } });
    } else if (path === '/api/worship/admin/beings/options/') {
      await route.fulfill({ json: OPTIONS });
    } else if (path === '/api/worship/admin/beings/1/') {
      await route.fulfill({ json: PAGE });
    } else if (path === '/api/worship/admin/beings/1/overview/') {
      await route.fulfill({
        json: {
          resonance_pool: 48200,
          lifetime_worship: 312900,
          most_devoted_name: 'Lily',
          most_devoted_favor: 940,
          site_count: 2,
          recent_activity: [
            { when: now, text: 'Lily: Offering scythe', note: '+840 pool' },
            { when: now, text: 'Marcus performed Vigil', note: 'favor +12' },
            { when: now, text: 'Marcus prayed', note: 'dire straits (soulfray)' },
            { when: now, text: 'A vision reached Renata', note: '-10 pool' },
          ],
        },
      });
    } else if (path === '/api/worship/admin/beings/1/prayers/') {
      await route.fulfill({
        json: {
          count: 4,
          next: null,
          previous: null,
          results: [
            {
              id: 1,
              character_sheet: 1,
              character_name: 'Renata',
              text: "Please, if anyone is listening. I don't even know who I'm asking anymore.",
              devotion_granted: 0,
              dire_straits: '',
              answered: true,
              place: 'The Long Watch',
              prayed_at: now,
            },
            {
              id: 2,
              character_sheet: 2,
              character_name: 'Marcus',
              text: 'Not like this. Not yet.',
              devotion_granted: 0,
              dire_straits: 'soulfray',
              answered: false,
              place: '',
              prayed_at: now,
            },
            {
              id: 3,
              character_sheet: 3,
              character_name: 'Lily',
              text: 'First blood of the week is yours, same as always.',
              devotion_granted: 1,
              dire_straits: '',
              answered: false,
              place: 'The Long Watch',
              prayed_at: now,
            },
            {
              id: 4,
              character_sheet: 4,
              character_name: 'Corin',
              text: "Rough day. Thought you'd appreciate it.",
              devotion_granted: 0,
              dire_straits: '',
              answered: false,
              place: '',
              prayed_at: now,
            },
          ],
        },
      });
    } else if (path === '/api/worship/admin/beings/1/worship/') {
      await route.fulfill({
        json: {
          contributors: [
            { character_name: 'Lily', amount: 840, reason: 'Offering: scythe', when: now },
            { character_name: 'Marcus', amount: 90, reason: 'Worship rite: Vigil', when: now },
          ],
          offerings: [
            {
              item_name: 'A notched iron scythe',
              offered_by: 'Lily',
              item_value: 420,
              amount: 840,
              ceremony_id: 3,
              when: now,
            },
            {
              item_name: 'A coin purse',
              offered_by: 'Corin',
              item_value: 50,
              amount: 50,
              ceremony_id: 4,
              when: now,
            },
          ],
          most_devoted: [
            {
              rank: 1,
              character_name: 'Lily',
              favor: 940,
              lifetime_favor: 940,
              valence: 'devotional',
            },
            { rank: 2, character_name: 'Renata', favor: 610, lifetime_favor: 700, valence: null },
          ],
        },
      });
    } else if (path === '/api/worship/admin/beings/1/sites/') {
      await route.fulfill({
        json: [
          {
            kind: 'temple',
            name: 'The Long Watch',
            place: 'Ashport',
            consecration_points: 410,
            tier_name: 'Consecrated',
            bonus_percent: 25,
            founder_name: 'Renata',
          },
          {
            kind: 'shrine',
            name: 'Household shrine',
            place: 'Velgard estate',
            consecration_points: 25,
            tier_name: 'Tended',
            bonus_percent: 10,
            founder_name: 'Lily',
          },
        ],
      });
    } else if (path === '/api/worship/admin/beings/1/visions/') {
      await route.fulfill({
        json: {
          count: 1,
          next: null,
          previous: null,
          results: [
            {
              id: 1,
              recipient: 1,
              recipient_name: 'Renata',
              body: 'A door opens in the dark, and something on the other side knows your name.',
              reveal_source: false,
              prayer: 1,
              clue: null,
              episode: null,
              resonance_spent: 10,
              sent_by_name: 'dan',
              sent_at: now,
            },
          ],
        },
      });
    } else if (path === '/api/worship/admin/beings/1/relics/') {
      await route.fulfill({
        json: [
          {
            id: 1,
            item_instance: 9,
            item_name: 'The Red Scythe',
            lore: 'Her own blade, or so the priests say.',
            created_at: now,
          },
        ],
      });
    } else if (path === '/api/worship/admin/beings/1/codex/') {
      await route.fulfill({
        json: [
          {
            id: 9,
            name: 'Fleshreaper',
            is_public: true,
            relation: "the being's page",
            organizations: [],
            clues: [],
          },
          {
            id: 10,
            name: 'The Godswar',
            is_public: false,
            relation: 'required by Fleshreaper',
            organizations: [],
            clues: ['godswar-ledger'],
          },
          {
            id: 11,
            name: 'The Long Bleeding',
            is_public: false,
            relation: "opened by a vision's clue (long-bleeding)",
            organizations: ['The Silken Thread'],
            clues: [],
          },
        ],
      });
    } else {
      await route.fulfill({ status: 404, json: { detail: 'Not provided by this fixture.' } });
    }
  });
}

test.describe('Deity Editor (#3780)', () => {
  test.use({ viewport: { width: 1280, height: 900 } });

  test('the god list: tiles by pool, filter by tier, Add God', async ({ page }) => {
    await mockPantheon(page);
    await page.goto('/staff/pantheon');
    await expect(page.getByRole('heading', { name: 'Deity Editor' })).toBeVisible();
    await expect(page.getByTestId('god-tile')).toHaveCount(3);
    await expect(page.getByTestId('god-tile').first()).toContainText('Fleshreaper');
    await expect(page.getByTestId('god-tile').first()).toContainText('48,200');
    await expect(page.getByTestId('add-god')).toHaveAttribute('href', '/staff/pantheon/new');
    if (SHOTS) await page.screenshot({ path: `${SHOTS}/screen-1-list-1280.png`, fullPage: true });

    await page.getByRole('button', { name: 'Obscure' }).click();
    await expect(page.getByTestId('god-tile')).toHaveCount(1);
    await expect(page.getByTestId('god-tile')).toContainText('Lady of the Loom');
  });

  test('the edit page: one long page of collapsible sections with highlight dots', async ({
    page,
  }) => {
    await mockPantheon(page);
    await page.goto('/staff/pantheon/1/edit');
    await expect(page.getByRole('heading', { name: 'Editing: Fleshreaper' })).toBeVisible();
    await expect(page.getByLabel('Name', { exact: true })).toHaveValue('Fleshreaper');
    // Open every section so the screenshot shows the whole page as the demo draws it.
    for (const section of ['Nicknames', 'Feast Days', 'Tarot', 'Relationships', 'GM Notes']) {
      await page.getByRole('button', { name: new RegExp(`^${section}`) }).click();
    }
    await expect(page.getByRole('button', { name: '+ Add nickname' })).toHaveAttribute(
      'title',
      /.+/
    );
    await expect(page.getByTestId('dot-identity')).toBeVisible(); // the quote is blank
    await expect(page.getByTestId('dot-nicknames')).toHaveCount(0);
    await expect(page.getByTestId('visibility-public')).toHaveAttribute('aria-checked', 'true');
    if (SHOTS) await page.screenshot({ path: `${SHOTS}/screen-2-edit-1280.png`, fullPage: true });
  });

  test('the dashboard: pool and Send Vision in the header, seven tabs', async ({ page }) => {
    await mockPantheon(page);
    await page.goto('/staff/pantheon/1');
    await expect(page.getByTestId('header-pool')).toHaveText('48,200');
    await expect(page.getByTestId('send-vision-button')).toBeVisible();
    await expect(page.getByTestId('activity-row')).toHaveCount(4);
    if (SHOTS)
      await page.screenshot({ path: `${SHOTS}/screen-3-overview-1280.png`, fullPage: true });

    for (const [tab, shot, marker] of [
      ['Worship', 'screen-4-worship-1280.png', 'devotee-row'],
      ['Temples & Shrines', 'screen-5-sites-1280.png', null],
      ['Prayers', 'screen-6-prayers-1280.png', 'prayer-card'],
      ['Visions', 'screen-7-visions-1280.png', 'vision-row'],
      ['Codex Entries', 'screen-8-codex-1280.png', 'codex-row'],
    ] as const) {
      await page.getByRole('tab', { name: tab }).click();
      if (marker) await expect(page.getByTestId(marker).first()).toBeVisible();
      if (SHOTS) await page.screenshot({ path: `${SHOTS}/${shot}`, fullPage: true });
    }
    await expect(page.getByTestId('prayer-dire')).toHaveCount(0); // the Prayers tab is no longer active
  });
});
