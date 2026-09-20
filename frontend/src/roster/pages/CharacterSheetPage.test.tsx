/**
 * Tests for the Reference Sheet (#3898).
 *
 * These replace the tests for the old tabbed sheet, whose assertions encoded the
 * design this issue changed: a vitals panel on the front page, and a covenant line
 * under the name. Both moved — condition to Physical, covenant to its own rail block
 * under Ties — so the old tests could only have been "fixed" by asserting the thing the
 * redesign removed.
 *
 * What is worth pinning here is the gating, because it is the part a future change
 * could quietly break without anything else failing: which sections a viewer is
 * offered, and that a viewer who is not the owner cannot land on one of the three
 * that only the player reads.
 */

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Routes, Route } from 'react-router-dom';
import { vi } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { CharacterSheetPage } from './CharacterSheetPage';
import type { UseQueryResult } from '@tanstack/react-query';
import type { RosterEntryData } from '../types';
import type { CharacterSheetPayload } from '@/character_sheets/api';

const mutate = vi.fn();

/** Two looks, the first worn — the shape the payload arrives in. */
const LOOKS = [
  {
    tenure_media_id: 5,
    url: 'http://img/a.png',
    title: 'At rest',
    look: 'At rest',
    is_current: true,
  },
  {
    tenure_media_id: 6,
    url: 'http://img/b.png',
    title: 'Guarded',
    look: 'Guarded',
    is_current: false,
  },
];

vi.mock('../queries', () => ({
  useRosterEntryQuery: vi.fn(),
  useMyRosterEntriesQuery: vi.fn(),
  useWearLook: () => ({ mutate, isPending: false }),
}));
vi.mock('@/character_sheets/queries', () => ({
  useCharacterSheetQuery: vi.fn(),
}));
vi.mock('@/vitals/vitalsQueries', () => ({
  useCharacterVitalsQuery: () => ({ data: null }),
}));
vi.mock('@/achievements/queries', () => ({
  usePersonaTitles: () => ({ data: [{ id: 1, title: 'Warden of the Lower Stair' }] }),
}));
vi.mock('@/inventory/hooks/useInventory', () => ({
  useEquippedItems: () => ({ data: [] }),
  useInventory: () => ({ data: [] }),
}));
let browsingEntryId: number | null = null;
vi.mock('../useBrowsingIdentity', () => ({
  useBrowsingIdentity: () => ({ entryId: browsingEntryId }),
}));
vi.mock('@/species/queries', () => ({
  useMyLanguages: () => ({ data: [{ language_id: 1, name: 'Arvani', is_current: true }] }),
}));
// The other sections each own a tree of queries that are not what these tests are
// about; stub them so a section switch renders a marker instead of a panel.
vi.mock('@/character_sheets/components/sheet/panels', () => ({
  TiesPanel: () => <div data-testid="ties-panel" />,
  DistinctionsPanel: () => <div data-testid="distinctions-panel" />,
  MagicPanel: () => <div data-testid="magic-panel" />,
  KnowledgePanel: () => <div data-testid="knowledge-panel" />,
  EstatePanel: () => <div data-testid="estate-panel" />,
  GrowthPanel: () => <div data-testid="growth-panel" />,
}));
vi.mock('@/worship/components/WorshipSection', () => ({
  WorshipSection: () => <div data-testid="worship-section" />,
}));
vi.mock('@/components/character', () => ({
  ApplicationSlot: () => <div data-testid="application-slot" />,
}));
vi.mock('@/narrative/components/MessagesSection', () => ({
  MessagesSection: () => <div data-testid="messages-section" />,
}));
vi.mock('@/friends/components/FriendButton', () => ({
  FriendButton: () => <button type="button">Friend</button>,
}));
vi.mock('@/friends/components/RivalButton', () => ({
  RivalButton: () => <button type="button">Rival</button>,
}));
vi.mock('@/character_sheets/components/OriginStoryEditorDialog', () => ({
  OriginStoryEditorDialog: () => <div data-testid="origin-story-editor" />,
}));
vi.mock('@/character_sheets/components/MaturationPanel', () => ({
  MaturationPanel: () => <div data-testid="maturation-panel" />,
}));
vi.mock('@/character_sheets/components/StatPointPanel', () => ({
  StatPointPanel: () => <div data-testid="stat-point-panel" />,
}));

import { useRosterEntryQuery, useMyRosterEntriesQuery } from '../queries';
import { useCharacterSheetQuery } from '@/character_sheets/queries';

const mockUseRosterEntryQuery = vi.mocked(useRosterEntryQuery);
const mockUseMyRosterEntriesQuery = vi.mocked(useMyRosterEntriesQuery);
const mockUseCharacterSheetQuery = vi.mocked(useCharacterSheetQuery);

const ENTRY: RosterEntryData = {
  id: 1,
  character: { id: 42, name: 'Ilsavet du Verane', galleries: [] },
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

/** A payload with every gated section empty — what a stranger actually receives. */
function makeSheet(overrides: Partial<CharacterSheetPayload> = {}): CharacterSheetPayload {
  return {
    id: 42,
    can_edit: false,
    identity: {
      name: 'Ilsavet du Verane',
      fullname: 'Ilsavet du Verane',
      concept: 'A pawnbroker&apos;s daughter.',
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
    ...overrides,
  };
}

function mountSheet() {
  return renderWithProviders(
    <Routes>
      <Route path="/:id" element={<CharacterSheetPage />} />
    </Routes>,
    { initialEntries: ['/1'] }
  );
}

function setEntry(data: RosterEntryData | undefined, isLoading = false) {
  mockUseRosterEntryQuery.mockReturnValue({
    data,
    isLoading,
    isError: false,
    error: null,
    isPending: isLoading,
    isSuccess: !isLoading,
  } as unknown as UseQueryResult<RosterEntryData, Error>);
}

function setOwnership(isMine: boolean) {
  mockUseMyRosterEntriesQuery.mockReturnValue({
    data: isMine ? [{ id: 1, primary_persona_id: 9 }] : [],
    isLoading: false,
    isSuccess: true,
    error: null,
  } as unknown as ReturnType<typeof useMyRosterEntriesQuery>);
}

describe('CharacterSheetPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    browsingEntryId = null;
    setOwnership(false);
    mockUseCharacterSheetQuery.mockReturnValue({
      data: makeSheet(),
    } as unknown as ReturnType<typeof useCharacterSheetQuery>);
  });

  it('shows loading state', () => {
    setEntry(undefined, true);
    mountSheet();
    expect(screen.getByText(/Loading.../i)).toBeInTheDocument();
  });

  it('shows not found when no entry', () => {
    setEntry(undefined);
    mountSheet();
    expect(screen.getByText(/Character not found/i)).toBeInTheDocument();
  });

  it('leads with the name and its titles composed into one heading', () => {
    setEntry(ENTRY);
    mountSheet();
    const heading = screen.getByRole('heading', { level: 1 });
    expect(heading).toHaveTextContent('Ilsavet du Verane');
    expect(heading).toHaveTextContent('Warden of the Lower Stair');
  });

  it('offers a stranger the five public sections and none of the private ones', () => {
    setEntry(ENTRY);
    mountSheet();
    const nav = screen.getByRole('navigation', { name: /sections/i });
    expect(within(nav).getAllByRole('button')).toHaveLength(5);
    expect(within(nav).queryByRole('button', { name: 'Knowledge' })).not.toBeInTheDocument();
    expect(within(nav).queryByRole('button', { name: 'Estate' })).not.toBeInTheDocument();
    expect(within(nav).queryByRole('button', { name: 'Growth' })).not.toBeInTheDocument();
    expect(within(nav).queryByText(/Yours only/i)).not.toBeInTheDocument();
  });

  it('offers the owner all eight sections, set apart by the yours-only break', () => {
    setEntry(ENTRY);
    setOwnership(true);
    mountSheet();
    const nav = screen.getByRole('navigation', { name: /sections/i });
    expect(within(nav).getAllByRole('button')).toHaveLength(8);
    expect(within(nav).getByText(/Yours only/i)).toBeInTheDocument();
  });

  it('keeps condition off the front page', () => {
    setEntry(ENTRY);
    setOwnership(true);
    mountSheet();
    // The front is the character in their own words; health lives on Physical.
    expect(screen.queryByText(/^Health$/)).not.toBeInTheDocument();
    expect(screen.queryByTestId('vitals-panel')).not.toBeInTheDocument();
  });

  it('opens a private section for the owner', async () => {
    setEntry(ENTRY);
    setOwnership(true);
    mountSheet();
    await userEvent.click(screen.getByRole('button', { name: 'Estate' }));
    expect(screen.getByTestId('estate-panel')).toBeInTheDocument();
  });

  it('renders no gated band when the payload carried none of it', () => {
    setEntry(ENTRY);
    mountSheet();
    // Render-or-vanish: a stranger gets no guidelines band and no abilities band,
    // and no empty-state card standing in for either.
    expect(screen.queryByText(/Goals and guidelines/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/^Abilities$/)).not.toBeInTheDocument();
  });

  it('shows the guidelines band when the viewer is allowed the answers', () => {
    setEntry(ENTRY);
    mockUseCharacterSheetQuery.mockReturnValue({
      data: makeSheet({
        actor_sheet: {
          never_do: 'Sell a secret she was given freely.',
          protect: '',
          fear: '',
          enemy_public_line: '',
          enemy: null,
          introductions: [],
        },
      }),
    } as unknown as ReturnType<typeof useCharacterSheetQuery>);
    mountSheet();
    expect(screen.getByText(/Goals and guidelines/i)).toBeInTheDocument();
    expect(screen.getByText(/Sell a secret she was given freely/i)).toBeInTheDocument();
  });

  it("speaks the active character's languages, and nobody else's", async () => {
    // Regression (#3898 review): the page passed a hardcoded null here, so the row was
    // dead for every viewer including the owner — and a preview harness that fed the
    // panel directly could not have shown it. The row must come from the real hook, and
    // only for the ACTIVE character: the endpoint is scoped to that character, so an
    // owned alt would otherwise be captioned with the active one's languages.
    setEntry(ENTRY);
    setOwnership(true);
    browsingEntryId = ENTRY.id;
    mountSheet();
    expect(screen.getByText('Arvani')).toBeInTheDocument();
  });

  it('omits the speaks row when the viewed character is not the active one', () => {
    setEntry(ENTRY);
    setOwnership(true);
    browsingEntryId = 999;
    mountSheet();
    expect(screen.queryByText('Arvani')).not.toBeInTheDocument();
  });

  it('shows the Beginning from beginnings, and the realm as its own row', () => {
    // Regression (#3898 review): "Beginning" was bound to `identity.origin`, which is
    // the realm the character is FROM (`Profile.origin_realm`), not their Beginnings
    // archetype. The two are different fields and must not be interchangeable.
    setEntry(ENTRY);
    mockUseCharacterSheetQuery.mockReturnValue({
      data: makeSheet({
        identity: {
          ...makeSheet().identity,
          beginnings: [{ id: 5, name: 'A Caretaker of Arx' }],
          origin: { id: 9, name: 'Arx, the Lantern Ward' },
        },
      }),
    } as unknown as ReturnType<typeof useCharacterSheetQuery>);
    mountSheet();
    expect(screen.getByText('A Caretaker of Arx')).toBeInTheDocument();
    expect(screen.getByText('Arx, the Lantern Ward')).toBeInTheDocument();
  });

  it('wears a look when the owner clicks one', async () => {
    setEntry(ENTRY);
    setOwnership(true);
    mockUseCharacterSheetQuery.mockReturnValue({
      data: makeSheet({ looks: LOOKS }),
    } as unknown as ReturnType<typeof useCharacterSheetQuery>);
    mountSheet();
    await userEvent.click(screen.getByRole('button', { name: 'Guarded' }));
    expect(mutate).toHaveBeenCalledWith(6);
  });

  it('only shows a look to a viewer who does not own the character', async () => {
    setEntry(ENTRY);
    setOwnership(false);
    mockUseCharacterSheetQuery.mockReturnValue({
      data: makeSheet({ looks: LOOKS }),
    } as unknown as ReturnType<typeof useCharacterSheetQuery>);
    mountSheet();
    await userEvent.click(screen.getByRole('button', { name: 'Guarded' }));
    // Clicking swaps the frame locally and writes nothing: a stranger flipping
    // through someone's images must never change what that character wears.
    expect(mutate).not.toHaveBeenCalled();
  });

  it("carries the sheet's plate ink onto the root, where the tokens are declared", () => {
    // `--plate-ground` and `--plate-accent` are declared by `.refsheet[data-ink=...]`,
    // so a root without the attribute leaves the plate with no ground at all. The
    // payload carried `plate_ink` from the first day and nothing read it.
    setEntry(ENTRY);
    mockUseCharacterSheetQuery.mockReturnValue({
      data: makeSheet({ plate_ink: 'verdigris' }),
    } as unknown as ReturnType<typeof useCharacterSheetQuery>);
    const { container } = mountSheet();
    expect(container.querySelector('.refsheet')).toHaveAttribute('data-ink', 'verdigris');
  });

  it('offers the Journal door to a stranger, alongside the Friend/Rival buttons', () => {
    setEntry(ENTRY);
    setOwnership(false);
    mountSheet();
    expect(screen.getByRole('link', { name: 'Journal' })).toHaveAttribute(
      'href',
      '/journals?writer=42'
    );
    expect(screen.getByRole('button', { name: 'Friend' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Rival' })).toBeInTheDocument();
  });

  it('offers the owner the Journal door too, but never the Friend/Rival buttons', () => {
    setEntry(ENTRY);
    setOwnership(true);
    mountSheet();
    expect(screen.getByRole('link', { name: 'Journal' })).toHaveAttribute(
      'href',
      '/journals?writer=42'
    );
    expect(screen.queryByRole('button', { name: 'Friend' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Rival' })).not.toBeInTheDocument();
  });

  it('falls back to the default ink before the payload arrives', () => {
    setEntry(ENTRY);
    mockUseCharacterSheetQuery.mockReturnValue({
      data: undefined,
    } as unknown as ReturnType<typeof useCharacterSheetQuery>);
    const { container } = mountSheet();
    expect(container.querySelector('.refsheet')).toHaveAttribute('data-ink', 'ember');
  });
});
