/**
 * The waiting sheet (#5206): a submitted draft drawn in the in-game sheet's plate, section
 * row and panels. The two hooks the page reads are mocked; every panel underneath is real,
 * and none of them may ask the server for anything, since there is no character yet.
 */

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';

import { WaitingSheetPage } from '../WaitingSheetPage';
import type { WaitingSheetPayload } from '../types';
import { mockStaffAccount } from './mocks';
import { renderWithCharacterCreationProviders } from './testUtils';

const apiFetch = vi.fn();
vi.mock('@/evennia_replacements/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/evennia_replacements/api')>()),
  apiFetch: (...args: unknown[]) => apiFetch(...args),
}));

const sheetAskedFor = vi.fn();
let mockSheet: { data: WaitingSheetPayload | null | undefined; isLoading: boolean } = {
  data: undefined,
  isLoading: false,
};
let mockDraftId: number | undefined = 12;
vi.mock('../queries', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../queries')>()),
  useDraft: () => ({ data: mockDraftId ? { id: mockDraftId } : null, isLoading: false }),
  useWaitingSheet: (draftId: number | undefined) => {
    sheetAskedFor(draftId);
    return { ...mockSheet, isError: false };
  },
}));

function waitingSheet(overrides: Partial<WaitingSheetPayload> = {}): WaitingSheetPayload {
  return {
    id: null,
    can_edit: false,
    staff_edit: null,
    identity: {
      name: 'Wren',
      fullname: 'Wren Marrow',
      concept: 'A soldier with a drillmaster for a father',
      quote: 'I keep my own counsel.',
      age: 24,
      birthday: null,
      chronological_age: 24,
      biological_age: 24,
      withered_years: null,
      gender: { id: 1, name: 'Female' },
      pronouns: { subject: 'she', object: 'her', possessive: 'hers' },
      species: { id: 2, name: 'Human' },
      heritage: null,
      beginnings: [{ id: 3, name: 'Caretaker' }],
      family: { id: 4, name: 'Marrow' },
      tarot_card: null,
      origin: { id: 5, name: 'Arx' },
      path: { id: 6, name: 'Steel' },
      worship: null,
      worship_sincere: null,
      current_mood: null,
      vacancy: null,
    },
    appearance: {
      height_inches: 70,
      height_band: 'Tall',
      build: { id: 1, name: 'Lean' },
      description: '',
      form_traits: [],
    },
    stats: { strength: 30, charm: 20 },
    buffed_stats: {},
    bonuses: [
      {
        category: 'aspect',
        heading: 'Aspect',
        rows: [
          {
            target: 'martial',
            label: 'martial',
            definition: 'Fighting and soldiering.',
            total: 10,
            immune: false,
            sources: [
              { label: 'Soldier', value: 5 },
              { label: "Drillmaster's Child", value: 5 },
            ],
          },
        ],
      },
    ],
    skills: [],
    path: null,
    distinctions: [
      {
        id: -1,
        name: 'Soldier',
        rank: 1,
        notes: '',
        is_secret: false,
        feature: '',
        is_from_glimpse: false,
      },
    ],
    magic: {
      gifts: [{ name: 'Pyromancy', description: '', resonances: [], techniques: [] }],
      motif: null,
      anima_ritual: null,
      aura: null,
      resonances: [],
      ultimates: [],
    },
    story: { background: '', origin_story_state: 'not_started', origin_slots: [] },
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
    viewer_is_friend: true,
    current_residence: { id: -1, name: 'A room above the Drillyard' },
    looks: [],
    plate_ink: 'ember',
    worn: [],
    natural_weapons: [],
    combat_style: null,
    mentors: [],
    domains: [],
    keyring: [
      {
        id: -1,
        place: 'A room above the Drillyard',
        where: '',
        rung: 'Owner',
        through: '',
        granted_by: '',
      },
    ],
    standing: {
      memberships: [
        {
          organization_id: 8,
          organization: 'House Marrow',
          title: 'Cousin',
          favor: '',
          favor_note: '',
        },
      ],
      reputations: [],
    },
    covenants: [],
    ties: [],
    ties_ap_this_week: null,
    awaiting: { status: 'submitted', status_label: 'Submitted' },
    purse: { balance: 250 },
    carried: [
      { id: -1, display_name: 'A drillmaster’s whistle', quality_tier: null, suggested_value: 5 },
    ],
    xp_ledger: { earned: 0, spent: 0, locked: 20 },
    languages: [
      {
        language_id: 1,
        name: 'Arvani',
        fluency: 100,
        band: 'fluent',
        is_current: false,
        effective_fluency: 100,
        effective_band: 'fluent',
        temporary_sources: [],
      },
    ],
    secrets: [
      {
        id: -1,
        level: 'Personal',
        content: 'She deserted once.',
        provenance: '',
        found_at: null,
        can_grieve: false,
        subject: 'Wren Marrow',
        category: 'Shame',
        consequences: 'Scandal',
        author: '',
        anchored_to: [],
      },
    ],
    ...overrides,
  } as WaitingSheetPayload;
}

function renderPage(path = '/characters/create/sheet') {
  return renderWithCharacterCreationProviders(<WaitingSheetPage />, { initialEntries: [path] });
}

function sectionRow() {
  return screen.getByRole('navigation', { name: 'Character sheet sections' });
}

describe('WaitingSheetPage', () => {
  beforeEach(() => {
    apiFetch.mockClear();
    sheetAskedFor.mockClear();
    mockDraftId = 12;
    mockSheet = { data: waitingSheet(), isLoading: false };
  });

  it('draws the plate with the name, the quote and the Awaiting approval mark', () => {
    renderPage();
    expect(screen.getByRole('heading', { level: 1, name: 'Wren Marrow' })).toBeInTheDocument();
    expect(screen.getByText('I keep my own counsel.')).toBeInTheDocument();
    expect(screen.getByText('Awaiting approval')).toHaveClass('refsheet-waiting');
    expect(screen.getByText('Human. Caretaker. Marrow. 24.')).toBeInTheDocument();
    expect(sheetAskedFor).toHaveBeenCalledWith(12);
  });

  it('offers no staff edit toggle, Journal or Friend, even to staff', () => {
    renderWithCharacterCreationProviders(<WaitingSheetPage />, {
      initialEntries: ['/characters/create/sheet?draft=12'],
      account: mockStaffAccount,
    });
    expect(screen.getByText('Awaiting approval')).toBeInTheDocument();
    expect(screen.queryByRole('switch', { name: 'Edit' })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Journal' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /friend/i })).not.toBeInTheDocument();
  });

  it('offers the sections the payload fills, never Gallery', () => {
    renderPage();
    const names = within(sectionRow())
      .getAllByRole('button')
      .map((button) => button.textContent);
    expect(names).toEqual([
      'Sheet',
      'Physical',
      'Ties',
      'Distinctions',
      'Magic',
      'Knowledge',
      'Estate',
      'Growth',
    ]);
  });

  it('leaves out Ties and Knowledge when the payload has nothing for them', () => {
    mockSheet = {
      data: waitingSheet({ standing: { memberships: [], reputations: [] }, secrets: [] }),
      isLoading: false,
    };
    renderPage();
    const row = sectionRow();
    expect(within(row).queryByRole('button', { name: 'Ties' })).not.toBeInTheDocument();
    expect(within(row).queryByRole('button', { name: 'Knowledge' })).not.toBeInTheDocument();
    expect(within(row).queryByRole('button', { name: 'Gallery' })).not.toBeInTheDocument();
  });

  it('opens on the Sheet, with the Bonuses band and the languages spoken', () => {
    renderPage();
    expect(screen.getByText('Bonuses')).toBeInTheDocument();
    expect(screen.getByTestId('bonus-groups')).toHaveTextContent('martial');
    const speaks = screen.getByText('Speaks', { selector: 'dt' }).nextElementSibling;
    expect(speaks).toHaveTextContent('Arvani');
  });

  it('draws Estate from the payload: the purse, what they carry, the home and its key', async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(within(sectionRow()).getByRole('button', { name: 'Estate' }));
    // 250 coppers at 100 to the gold and 10 to the silver.
    expect(screen.getByText('2g 5s')).toBeInTheDocument();
    expect(screen.getByText('A drillmaster’s whistle')).toBeInTheDocument();
    expect(screen.getByText('1 thing.')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Keyring' })).toBeInTheDocument();
    expect(screen.getAllByText('A room above the Drillyard')).toHaveLength(2);
    // Nothing that needs a character in play.
    expect(screen.queryByRole('heading', { name: 'The law' })).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Agreements' })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'wardrobe' })).not.toBeInTheDocument();
  });

  it('draws Growth from the payload: the starting XP and the languages', async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(within(sectionRow()).getByRole('button', { name: 'Growth' }));
    const locked = screen.getByText('Locked from creation', { selector: 'dt' }).nextElementSibling;
    expect(locked).toHaveTextContent('20 XP');
    expect(screen.getByTestId('languages-list')).toHaveTextContent('Arvani');
    expect(screen.queryByRole('heading', { name: 'Messages' })).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Changes to the sheet' })).not.toBeInTheDocument();
  });

  it('draws Knowledge as the character’s own secrets, with no clues or gossip', async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(within(sectionRow()).getByRole('button', { name: 'Knowledge' }));
    expect(screen.getByText('She deserted once.')).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Clues' })).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Gossip' })).not.toBeInTheDocument();
  });

  it('draws Ties as the organizations alone', async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(within(sectionRow()).getByRole('button', { name: 'Ties' }));
    expect(screen.getByRole('link', { name: 'House Marrow' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Kin' })).not.toBeInTheDocument();
  });

  it('draws Distinctions and Magic from the payload', async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(within(sectionRow()).getByRole('button', { name: 'Distinctions' }));
    expect(screen.getByTestId('distinctions-list')).toHaveTextContent('Soldier');
    await user.click(within(sectionRow()).getByRole('button', { name: 'Magic' }));
    expect(screen.getAllByText('Pyromancy').length).toBeGreaterThan(0);
  });

  it('asks the server for nothing beyond the waiting sheet, whatever section is open', async () => {
    const user = userEvent.setup();
    renderPage();
    for (const name of [
      'Physical',
      'Ties',
      'Distinctions',
      'Magic',
      'Knowledge',
      'Estate',
      'Growth',
    ]) {
      await user.click(within(sectionRow()).getByRole('button', { name }));
    }
    expect(apiFetch).not.toHaveBeenCalled();
  });

  it('reads the draft staff name in the address', () => {
    renderPage('/characters/create/sheet?draft=31');
    expect(sheetAskedFor).toHaveBeenCalledWith(31);
  });

  it('reads Not found. when the server answers 404', () => {
    mockSheet = { data: null, isLoading: false };
    renderPage();
    expect(screen.getByText('Not found.')).toBeInTheDocument();
    expect(screen.queryByText('Awaiting approval')).not.toBeInTheDocument();
  });

  it('reads Not found. for an account with no draft', () => {
    mockDraftId = undefined;
    mockSheet = { data: undefined, isLoading: false };
    renderPage();
    expect(screen.getByText('Not found.')).toBeInTheDocument();
  });
});
