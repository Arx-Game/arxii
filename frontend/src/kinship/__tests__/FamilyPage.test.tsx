/**
 * FamilyPage (#4209) — one page per family. Mocks the feature's own hooks
 * wholesale (the `KinshipPanel.test.tsx` idiom) and the account hook, and renders
 * the inner page inside a router, since names link to sheets.
 */
import { fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { FamilySlots } from '@/character-creation/types';
import { FamilyPageInner } from '../pages/FamilyPage';
import type { FamilyTree, KinRelationship, KinspersonNode } from '../types';

vi.mock('@/kinship/queries', () => ({
  useFamilyTree: vi.fn(),
  useFamilySlots: vi.fn(),
  useKinRelationship: vi.fn(),
}));
vi.mock('@/store/hooks', () => ({ useAccount: vi.fn() }));

import { useFamilySlots, useFamilyTree, useKinRelationship } from '@/kinship/queries';
import { useAccount } from '@/store/hooks';

const mockTree = vi.mocked(useFamilyTree);
const mockSlots = vi.mocked(useFamilySlots);
const mockRelationship = vi.mocked(useKinRelationship);
const mockAccount = vi.mocked(useAccount);

const FAMILY_ID = 7;
const VIEWER_SHEET_ID = 77;
const KATHRYN_SHEET_ID = 20;
const KATHRYN_ENTRY_ID = 2;

function node(
  overrides: Partial<KinspersonNode> & Pick<KinspersonNode, 'id' | 'full_name' | 'short_name'>
): KinspersonNode {
  return {
    name: overrides.short_name,
    tier: 'name_only',
    family_id: FAMILY_ID,
    is_deceased: false,
    is_appable: false,
    sheet_id: null,
    roster_entry_id: null,
    gender: '',
    age: null,
    description: '',
    ...overrides,
  };
}

/** House Katta as a stranger reads it: two parents, a late daughter, a played one. */
function katta(): FamilyTree {
  return {
    family: {
      id: FAMILY_ID,
      name: 'Katta',
      kind: { id: 1, name: 'Noble', styles_as_house: true },
      influence: 0,
      description:
        'The imperial house of Umbros. PLACEHOLDER\n\nEvery Katta learns the court. PLACEHOLDER',
      is_playable: true,
      origin_realm: null,
      born_particle: 'mar',
      taken_in_particle: 'mal',
      standing: null,
      inherited: { aspects: [], features: [], liege_name: '' },
    },
    house: {
      id: 3,
      name: 'House Katta',
      description: '',
      words: 'What the dark keeps, the Katta keep. PLACEHOLDER',
      colors: 'black and silver',
      sigil_description: 'a crowned key',
      org_type_name: 'noble_family',
      society_name: 'The Umbral Court',
      family_id: FAMILY_ID,
    },
    realm_name: 'Umbros',
    nodes: [
      node({ id: 101, full_name: 'Alarysa mar Katta', short_name: 'Alarysa', tier: 'standing' }),
      node({
        id: 102,
        full_name: 'Emperor Galleron ne Valeweep mal Katta',
        short_name: 'Galleron ne Valeweep',
        tier: 'standing',
      }),
      node({
        id: 103,
        full_name: 'Princess Alyssa mar Katta',
        short_name: 'Alyssa',
        is_deceased: true,
      }),
      node({
        id: 104,
        full_name: 'Princess Kathryn mar Katta',
        short_name: 'Kathryn',
        tier: 'pc',
        sheet_id: KATHRYN_SHEET_ID,
        roster_entry_id: KATHRYN_ENTRY_ID,
        description: 'The younger daughter. PLACEHOLDER',
      }),
    ],
    parentage: [
      { child_id: 103, parent_id: 101, kind: 'biological', is_true: true, via_secret: false },
      { child_id: 103, parent_id: 102, kind: 'biological', is_true: true, via_secret: false },
      { child_id: 104, parent_id: 101, kind: 'biological', is_true: true, via_secret: false },
      { child_id: 104, parent_id: 102, kind: 'biological', is_true: true, via_secret: false },
    ],
    unions: [{ id: 1, kind: 'Marriage', member_ids: [101, 102], ended: false }],
  };
}

/** Tallow, a commoner family with no house. */
function tallow(): FamilyTree {
  const tree = katta();
  return {
    ...tree,
    family: {
      ...tree.family!,
      id: 8,
      name: 'Tallow',
      kind: { id: 2, name: 'Commoner', styles_as_house: false },
      description: 'Chandlers on the lower quay. PLACEHOLDER',
    },
    house: null,
    realm_name: 'Arx',
    nodes: [
      node({ id: 201, full_name: 'Hesper ne Marrow Tallow', short_name: 'Hesper ne Marrow' }),
      node({ id: 202, full_name: 'Tam Tallow', short_name: 'Tam' }),
    ],
    parentage: [
      { child_id: 202, parent_id: 201, kind: 'biological', is_true: true, via_secret: false },
    ],
    unions: [],
  };
}

function seats(): FamilySlots {
  return {
    slots: [
      {
        id: 1,
        name: 'A cousin of the Katta line',
        name_locked: false,
        description: "Of Alarysa's generation; raised at court. PLACEHOLDER",
        age_min: null,
        age_max: null,
        allowed_genders: [],
        family: FAMILY_ID,
      },
    ],
    pools: [
      {
        id: 1,
        family: FAMILY_ID,
        description: 'Wards of the Katta PLACEHOLDER',
        count_remaining: 2,
        age_min: null,
        age_max: null,
        allowed_genders: [],
        parent_names: ['Alarysa', 'Galleron'],
      },
    ],
  };
}

function givenTree(
  tree: FamilyTree | null,
  state: Partial<{ isLoading: boolean; isError: boolean }> = {}
) {
  mockTree.mockReturnValue({
    data: tree ?? undefined,
    isLoading: false,
    isError: false,
    ...state,
  } as ReturnType<typeof useFamilyTree>);
}

function givenSeats(payload: FamilySlots | null) {
  mockSlots.mockReturnValue({ data: payload ?? undefined } as ReturnType<typeof useFamilySlots>);
}

function givenRelationship(payload: KinRelationship | undefined) {
  mockRelationship.mockReturnValue({ data: payload } as ReturnType<typeof useKinRelationship>);
}

function givenViewer(sheetId: number | null) {
  mockAccount.mockReturnValue(
    (sheetId == null
      ? { selected_entry: null }
      : { selected_entry: { character_id: sheetId } }) as ReturnType<typeof useAccount>
  );
}

function renderPage(familyId: number | undefined = FAMILY_ID) {
  return render(
    <MemoryRouter>
      <FamilyPageInner familyId={familyId} />
    </MemoryRouter>
  );
}

describe('FamilyPage', () => {
  beforeEach(() => {
    mockTree.mockReset();
    mockSlots.mockReset();
    mockRelationship.mockReset();
    mockAccount.mockReset();
    givenSeats(null);
    givenRelationship(undefined);
    givenViewer(VIEWER_SHEET_ID);
  });

  it('opens a house-styled family on its gate: kind and realm, name, words, arms, description', () => {
    givenTree(katta());
    renderPage();
    expect(screen.getByText('Noble House · Umbros')).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 1, name: 'House Katta' })).toBeInTheDocument();
    expect(screen.getByText(/What the dark keeps, the Katta keep/)).toBeInTheDocument();
    expect(
      screen.getByText('Colours: black and silver · Sigil: a crowned key')
    ).toBeInTheDocument();
    const description = screen.getByRole('region', { name: 'Description' });
    expect(within(description).getAllByRole('paragraph')).toHaveLength(2);
  });

  it('opens a commoner family on a plain head by its bare name', () => {
    givenTree(tallow());
    renderPage();
    expect(screen.getByText('Commoner Family · Arx')).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 1, name: 'Tallow' })).toBeInTheDocument();
    expect(screen.queryByText(/House Tallow/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Colours:/)).not.toBeInTheDocument();
  });

  it('prints the roll in full-formal names, one list per generation, with the dagger and the link', () => {
    givenTree(katta());
    const { container } = renderPage();
    const roll = screen.getByRole('region', { name: 'The roll' });
    expect(within(roll).getAllByRole('list')).toHaveLength(2);
    expect(within(roll).getByText('Alarysa mar Katta')).toBeInTheDocument();
    expect(within(roll).getByText('Emperor Galleron ne Valeweep mal Katta')).toBeInTheDocument();
    expect(within(roll).getByText('Princess Alyssa mar Katta †')).toBeInTheDocument();
    expect(within(roll).getByRole('link', { name: 'Princess Kathryn mar Katta' })).toHaveAttribute(
      'href',
      `/characters/${KATHRYN_ENTRY_ID}`
    );
    // No definition tier anywhere on the page.
    expect(container.textContent).not.toMatch(/standing|name only|\bpc\b/);
  });

  it('prints the tree in short names and links the played one', () => {
    givenTree(katta());
    renderPage();
    const tree = screen.getByRole('region', { name: 'The tree' });
    expect(within(tree).getByText('Galleron ne Valeweep')).toBeInTheDocument();
    expect(within(tree).getByText('Alyssa †')).toBeInTheDocument();
    expect(within(tree).queryByText(/mar Katta/)).not.toBeInTheDocument();
    expect(within(tree).getByRole('link', { name: 'Kathryn' })).toHaveAttribute(
      'href',
      `/characters/${KATHRYN_ENTRY_ID}`
    );
  });

  it('selects a person: the full name as a link, the blurb, and the relatedness to the viewer', () => {
    givenTree(katta());
    givenRelationship({ label: 'cousin' });
    const { container } = renderPage();
    fireEvent.click(container.querySelector('[data-node-id="104"]')!);
    const selected = screen.getByRole('region', { name: 'Selected' });
    expect(
      within(selected).getByRole('link', { name: 'Princess Kathryn mar Katta' })
    ).toBeInTheDocument();
    expect(within(selected).getByText('The younger daughter. PLACEHOLDER')).toBeInTheDocument();
    expect(within(selected).getByText('Related as cousin.')).toBeInTheDocument();
    expect(mockRelationship).toHaveBeenLastCalledWith(VIEWER_SHEET_ID, KATHRYN_SHEET_ID);
  });

  it('prints no relatedness line when there is no label, no sheet, or no viewer character', () => {
    givenTree(katta());
    givenRelationship({ label: null });
    const { container, unmount } = renderPage();
    fireEvent.click(container.querySelector('[data-node-id="104"]')!);
    expect(screen.queryByText(/Related as/)).not.toBeInTheDocument();
    expect(screen.queryByText(/No determinable relationship/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Nobody on the roster/)).not.toBeInTheDocument();

    // An unplayed person: no query at all, nothing printed.
    fireEvent.click(container.querySelector('[data-node-id="101"]')!);
    expect(screen.getByRole('region', { name: 'Selected' })).toHaveTextContent('Alarysa mar Katta');
    expect(mockRelationship).toHaveBeenLastCalledWith(VIEWER_SHEET_ID, undefined);
    unmount();

    // A viewer with no character of their own: the line stays off even with a label.
    givenViewer(null);
    givenRelationship({ label: 'sibling' });
    const second = renderPage();
    fireEvent.click(second.container.querySelector('[data-node-id="104"]')!);
    expect(screen.queryByText(/Related as/)).not.toBeInTheDocument();
  });

  it('lists the open seats with their chip and count, and drops the section when there are none', () => {
    givenTree(katta());
    givenSeats(seats());
    const { unmount } = renderPage();
    const open = screen.getByRole('region', { name: 'Open seats' });
    expect(within(open).getByText('A cousin of the Katta line')).toBeInTheDocument();
    expect(within(open).getByText('open')).toBeInTheDocument();
    expect(within(open).getByText(/raised at court/)).toBeInTheDocument();
    expect(within(open).getByText('Wards of the Katta PLACEHOLDER')).toBeInTheDocument();
    expect(within(open).getByText('2 seats')).toBeInTheDocument();
    unmount();

    givenSeats({ slots: [], pools: [] });
    renderPage();
    expect(screen.queryByRole('region', { name: 'Open seats' })).not.toBeInTheDocument();
  });

  it('says so when there is no family to read', () => {
    givenTree(null, { isError: true });
    renderPage();
    expect(screen.getByText('No family by that name is recorded.')).toBeInTheDocument();
    renderPage(undefined);
    expect(screen.getAllByText('No family by that name is recorded.')).toHaveLength(2);
  });
});
