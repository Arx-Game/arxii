/**
 * TitlePage (#4239): held by with the holder in person, Location as realm and
 * tier, Holdings, Books, Forces, and Vassals with Create vassal domain.
 */
import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';

import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { TitlePage } from '../title/TitlePage';
import type { RungDocument } from '../types';

const doc: RungDocument = {
  title: {
    title_id: 3,
    name: 'County of Katta',
    tier: 'county',
    realm_id: 1,
    realm: 'Umbros',
    house_id: 9,
    held_by: 'House Katta',
    holder_id: 11,
    holder: 'Kathryn mar Katta',
    sworn_to: 'The Umbral Crown',
    succession: 'Umbral enatic',
    seat: 'the Katta seat',
    is_claimable: false,
    chain_top_id: 3,
    station: 'seated',
    pledged_liege: { title_id: 8, name: 'Kingdom of Umbros' },
    area_id: 70,
  },
  // a county's own land: its hinterland (#5069)
  demesne: {
    domain_id: 30,
    name: 'the Katta lands',
    description: '',
    hall: 'the Katta hall',
    population: 1000,
    population_capacity: 2400,
    capacity_override: null,
    terrain: [
      { terrain: 'plain', label: 'Plain', pips: 5 },
      { terrain: 'hill', label: 'Hill', pips: 2 },
    ],
    prosperity: 50,
    unrest: 0,
    defenses: 10,
  },
  holdings: [
    { holding_id: 1, name: 'a quarry', kind: 'Quarry', site: '', standing: 50, unsited: true },
  ],
  books: { income_week: 1900, uncollected: 5700, treasury: 42000, streams: 1 },
  forces: [
    {
      unit_id: 1,
      name: 'Katta household guard',
      owner: 'House Katta',
      quality: 'veteran',
      men: 120,
      strength: 70,
      morale: 80,
      posted_here: true,
    },
  ],
  vassals: [{ title_id: 4, name: '', held_by: '', demesne: 2, vassals: 0, population: 3200 }],
  chartered_fiefs: [
    { title_id: 5, name: 'County of Ash', tier: 'county', basis: 'By the old charter' },
  ],
  chartered_by: [{ title_id: 21, name: 'Old Umbros', tier: 'kingdom', basis: '' }],
  claims: [
    {
      claim_id: 1,
      claimant: 'Sharlotte',
      claimant_sheet_id: 44,
      house_id: null,
      basis: 'The exiled duchess',
      since: '2026-11-03',
    },
  ],
  chain: [
    { title_id: null, name: 'Umbros', tier: 'realm' },
    { title_id: 8, name: 'Kingdom of Umbros', tier: 'kingdom' },
  ],
  events: [],
};

const { mutate } = vi.hoisted(() => ({ mutate: vi.fn() }));
let currentDoc: RungDocument = doc;
let currentError: Error | null = null;
const refetch = vi.fn();

vi.mock('@/world-builder/queries', () => ({
  useRegionMapsQuery: () => ({ data: [{ id: 6, name: 'Catenys' }] }),
  useRoomSearchQuery: (term: string) => ({
    data:
      term.trim().length >= 2 ? [{ id: 77, name: 'Katta Fields', area_name: 'Fervor' }] : undefined,
  }),
}));

/** The holding house's roll as the house document draws it (#5017): members, a
 * married-in spouse from another family, one dead, one a player character, and a
 * dalliance partner the tree draws but the ruler rule refuses. */
const node = {
  tier: 'standing',
  is_deceased: false,
  believed_deceased: false,
  is_appable: false,
  sheet_id: null as number | null,
  gender: '',
  age: 30,
  description: '',
};
const houseDoc = {
  family: {
    family_id: 4,
    nodes: [
      { ...node, id: 11, name: 'Kathryn mar Katta', family_id: 4, sheet_id: 5 },
      { ...node, id: 12, name: 'Galleron', family_id: 7 },
      { ...node, id: 13, name: 'Old Marr', family_id: 4, is_deceased: true },
      { ...node, id: 14, name: 'Aldo mar Katta', family_id: 4 },
      { ...node, id: 15, name: 'Rook', family_id: 7 },
    ],
    parentage: [],
    unions: [
      { id: 1, kind: 'Marriage', member_ids: [11, 12], ended: false, confers_wedlock: true },
      { id: 2, kind: 'Dalliance', member_ids: [14, 15], ended: false, confers_wedlock: false },
    ],
  },
};

vi.mock('../queries', () => ({
  useHouseDocument: () => ({ data: houseDoc }),
  useTitleDocument: () =>
    currentError
      ? { data: undefined, error: currentError, refetch }
      : { data: currentDoc, error: null, refetch },
  useSearch: () => ({ data: undefined }),
  useHouses: () => ({ data: { results: [] } }),
  useRealmTitles: () => ({
    data: {
      results: [
        { id: 3, name: 'Duchy of Katta', tier: 'duchy' },
        { id: 8, name: 'Kingdom of Umbros', tier: 'kingdom' },
      ],
    },
  }),
  useAllHouses: () => ({
    data: {
      results: [
        { id: 9, name: 'House Katta' },
        { id: 12, name: 'House Vampa' },
      ],
    },
  }),
  useHoldingKinds: () => ({
    data: {
      results: [
        { id: 1, name: 'Quarry', description: '', site_kind: 'land', requires_field: false },
      ],
    },
  }),
  useRegionalEventKinds: () => ({
    data: {
      results: [
        { id: 1, name: 'Blight', description: '', capacity_cut_pct: 50 },
        { id: 2, name: 'Famine', description: '', capacity_cut_pct: 20 },
      ],
    },
  }),
  useAlmanachMutation: () => ({ mutate, mutateAsync: vi.fn() }),
}));

test('the Events row (#5080): the blight over the land, Close, and Open one here', async () => {
  currentDoc = {
    ...doc,
    events: [
      {
        event_id: 5,
        kind: 'Blight',
        area_id: 77,
        area: 'Duchy of Katta',
        severity_pct: 80,
        started_at: '2026-11-11T00:00:00Z',
      },
    ],
  };
  try {
    renderWithProviders(<TitlePage titleId={3} />);
    const events = screen.getByRole('heading', { name: 'Events' }).nextElementSibling!;
    const row = within(events as HTMLElement);
    expect(row.getByText('Blight', { selector: 'strong' })).toBeInTheDocument();
    expect(row.getByText(/over Duchy of Katta/)).toBeInTheDocument();
    expect(row.getByText('80%')).toBeInTheDocument();
    await userEvent.click(row.getByRole('button', { name: 'Close' }));
    expect(mutate).toHaveBeenCalledWith({ event_id: 5 });
    mutate.mockClear();
    // nothing opens until a kind is picked; then the rung's own area is struck
    expect(row.getByRole('button', { name: 'Open' })).toBeDisabled();
    await userEvent.selectOptions(row.getByLabelText('event'), 'Famine');
    const severity = row.getByLabelText('severity');
    await userEvent.clear(severity);
    await userEvent.type(severity, '40');
    await userEvent.click(row.getByRole('button', { name: 'Open' }));
    expect(mutate).toHaveBeenCalledWith({ kind_id: 2, area_id: 70, severity_pct: 40 });
  } finally {
    currentDoc = doc;
  }
});

test('the county page: holder, location, hinterland, developments, books, forces, holdings', () => {
  renderWithProviders(<TitlePage titleId={3} />);
  expect(screen.getByRole('heading', { level: 3 })).toHaveTextContent('County of Katta');
  expect(screen.getAllByRole('link', { name: 'House Katta' })[0]).toHaveAttribute(
    'href',
    '/staff/almanach/houses/9'
  );
  expect(screen.getAllByRole('link', { name: 'Kathryn mar Katta' })[0]).toHaveAttribute(
    'href',
    '/staff/almanach/people/11'
  );
  expect(screen.getByRole('heading', { name: 'Location' })).toBeInTheDocument();
  // the county's own land (#5069): its people by formula, the terrain's capacity, the mix
  const hinterland = screen.getByRole('heading', { name: 'Hinterland' }).nextElementSibling!;
  expect(within(hinterland as HTMLElement).getByText('1,000')).toBeInTheDocument();
  expect(within(hinterland as HTMLElement).getByText('2,400')).toBeInTheDocument();
  expect(within(hinterland as HTMLElement).getByText('plain, hill')).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: 'Developments' })).toBeInTheDocument();
  expect(screen.getByText('unsited')).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: 'Books' })).toBeInTheDocument();
  expect(screen.getByText('1,900 c / week')).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: 'Forces' })).toBeInTheDocument();
  expect(screen.getByText('Katta household guard')).toBeInTheDocument();
  // Holdings are the rungs beneath, held directly or by vassals, with their people
  const holdings = screen.getByRole('heading', { name: 'Holdings' }).nextElementSibling!;
  expect(within(holdings as HTMLElement).getByText('vacant')).toBeInTheDocument();
  expect(within(holdings as HTMLElement).getByText('3,200')).toBeInTheDocument();
  expect(within(holdings as HTMLElement).getByText('Vassals')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Create vassal domain' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Add vacant seats' })).toBeInTheDocument();
});

test('a duchy is its counties (#5069): no land block, no developments, no forces', () => {
  currentDoc = {
    ...doc,
    title: { ...doc.title, name: 'Duchy of Katta', tier: 'duchy' },
    demesne: null,
    holdings: [],
    vassals: [
      {
        title_id: 4,
        name: 'County of Katta',
        held_by: 'House Katta',
        demesne: 1,
        vassals: 0,
        population: 1000,
      },
      {
        title_id: 5,
        name: 'County of Ash',
        held_by: 'House Ash',
        demesne: 1,
        vassals: 0,
        population: 700,
      },
      { title_id: 6, name: '', held_by: '', demesne: 1, vassals: 0, population: 300 },
    ],
  };
  try {
    renderWithProviders(<TitlePage titleId={3} />);
    expect(screen.queryByRole('heading', { name: 'Hinterland' })).toBeNull();
    expect(screen.queryByRole('heading', { name: 'Developments' })).toBeNull();
    expect(screen.queryByRole('heading', { name: 'Forces' })).toBeNull();
    expect(screen.getByRole('heading', { name: 'Books' })).toBeInTheDocument();
    const holdings = screen.getByRole('heading', { name: 'Holdings' }).nextElementSibling!;
    const held = within(holdings as HTMLElement)
      .getByText('Held')
      .closest('tr')!;
    // the house's own county sits under Held; the other house's and the vacant one under Vassals
    expect(held.nextElementSibling).toHaveTextContent('County of Katta');
    const vassals = within(holdings as HTMLElement)
      .getByText('Vassals')
      .closest('tr')!;
    expect(vassals.nextElementSibling).toHaveTextContent('County of Ash');
    expect(vassals.nextElementSibling!.nextElementSibling).toHaveTextContent('vacant');
  } finally {
    currentDoc = doc;
  }
});

test('a barony page: its people and capacity, and staff name the capacity or hand it back', async () => {
  currentDoc = {
    ...doc,
    title: { ...doc.title, name: 'Katta Seat', tier: 'barony' },
    // a seat whose capacity staff already set by hand, so Terrain has something to clear
    demesne: {
      ...doc.demesne!,
      population_capacity: 5000,
      capacity_override: 5000,
      terrain: [{ terrain: 'plain', label: 'Plain', pips: 1 }],
    },
    vassals: [],
  };
  try {
    renderWithProviders(<TitlePage titleId={3} />);
    expect(screen.queryByRole('heading', { name: 'Hinterland' })).toBeNull();
    expect(screen.getByText('5,000')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Developments' })).toBeInTheDocument();
    const capacity = screen.getByLabelText('capacity');
    await userEvent.clear(capacity);
    await userEvent.type(capacity, '300000');
    await userEvent.click(screen.getByRole('button', { name: 'Set' }));
    expect(mutate).toHaveBeenCalledWith({ domain_id: 30, capacity: 300000 });
    mutate.mockClear();
    await userEvent.click(screen.getByRole('button', { name: 'Terrain' }));
    expect(mutate).toHaveBeenCalledWith({ domain_id: 30, capacity: null });
  } finally {
    currentDoc = doc;
  }
});

test('the rung page: Historical Charter, the claims, the chain up and the door to the map', () => {
  renderWithProviders(<TitlePage titleId={3} />);
  const charter = screen.getByRole('heading', { name: 'Historical Charter' }).nextElementSibling!;
  expect(
    within(charter as HTMLElement).getByRole('link', { name: 'County of Ash' })
  ).toHaveAttribute('href', '/staff/almanach/titles/5');
  expect(within(charter as HTMLElement).getByText('By the old charter')).toBeInTheDocument();
  expect(within(charter as HTMLElement).getByRole('link', { name: 'Old Umbros' })).toHaveAttribute(
    'href',
    '/staff/almanach/titles/21'
  );
  expect(within(charter as HTMLElement).getByText(/claimed by/)).toHaveTextContent(
    'claimed by Sharlotte'
  );
  expect(within(charter as HTMLElement).getByText('The exiled duchess')).toBeInTheDocument();
  // the way up: the realm's ladder, then the crown, as links
  const chain = screen.getByTestId('title-chain');
  expect(within(chain).getByRole('link', { name: 'Umbros' })).toHaveAttribute(
    'href',
    '/staff/almanach/realms/1'
  );
  expect(within(chain).getByRole('link', { name: 'Kingdom of Umbros' })).toHaveAttribute(
    'href',
    '/staff/almanach/titles/8'
  );
  expect(screen.getByText('pledged to Kingdom of Umbros')).toBeInTheDocument();
  // #5017: the map door is a globe, named for the screen reader only.
  expect(screen.getByRole('link', { name: 'View on the map' })).toHaveAttribute(
    'href',
    '/staff/world-builder'
  );
  expect(screen.queryByText('On the map')).toBeNull();
});

test('a titular rung says so and shows its charter even with nothing held', () => {
  currentDoc = {
    ...doc,
    title: {
      ...doc.title,
      name: 'Kingdom of Luxen',
      station: 'titular',
      house_id: null,
      held_by: '',
    },
    vassals: [],
  };
  try {
    renderWithProviders(<TitlePage titleId={3} />);
    expect(screen.getByText('Titular')).toBeInTheDocument();
    const holdings = screen.getByRole('heading', { name: 'Holdings' }).nextElementSibling!;
    expect(within(holdings as HTMLElement).getByText('nothing')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Historical Charter' })).toBeInTheDocument();
  } finally {
    currentDoc = doc;
  }
});

test('an unnamed rung is named from its own page: one field, Enter saves (#5017)', async () => {
  mutate.mockClear();
  currentDoc = { ...doc, title: { ...doc.title, name: '', house_id: null, held_by: '' } };
  try {
    renderWithProviders(<TitlePage titleId={3} />);
    // No label above and no button below: the field alone, reading Name while blank.
    expect(screen.queryByRole('button', { name: 'Name' })).toBeNull();
    expect(document.querySelector('label[for="r-name"]')).toBeNull();
    const field = screen.getByRole('textbox', { name: 'Name' });
    expect(field).toHaveAttribute('placeholder', 'Name');
    await userEvent.type(field, 'Kingdom of Umbros{enter}');
    expect(mutate).toHaveBeenCalledWith({ title_id: 3, name: 'Kingdom of Umbros' });
  } finally {
    currentDoc = doc;
  }
});

test('a named rung is renamed when the field loses focus, and an unchanged field dispatches nothing (#5017)', async () => {
  mutate.mockClear();
  renderWithProviders(<TitlePage titleId={3} />);
  expect(screen.queryByRole('button', { name: 'Rename' })).toBeNull();
  const field = screen.getByRole('textbox', { name: 'Name' });
  await userEvent.click(field);
  await userEvent.tab();
  expect(mutate).not.toHaveBeenCalled();
  await userEvent.type(field, ' II');
  await userEvent.tab();
  expect(mutate).toHaveBeenCalledWith({ title_id: 3, name: 'County of Katta II' });
  // Enter after blur saved it dispatches nothing more: the field already matches.
  mutate.mockClear();
  await userEvent.type(field, '{enter}');
  expect(mutate).not.toHaveBeenCalled();
});

test('a vacant rung seats an existing house from its page', async () => {
  mutate.mockClear();
  currentDoc = { ...doc, title: { ...doc.title, house_id: null, held_by: '', chain_top_id: 3 } };
  try {
    renderWithProviders(<TitlePage titleId={3} />);
    const seat = screen.getByRole('button', { name: 'Seat' });
    expect(seat).toBeDisabled();
    const select = screen.getByLabelText('house');
    expect(within(select).getAllByRole('option')[0]).toHaveTextContent('pick a house');
    await userEvent.selectOptions(select, 'House Vampa');
    await userEvent.click(seat);
    expect(mutate).toHaveBeenCalledWith({ title_id: 3, org_id: 12 });
  } finally {
    currentDoc = doc;
  }
});

test('a held rung says the control changes its holder, and leaves the holder out of the list (#5112)', async () => {
  mutate.mockClear();
  renderWithProviders(<TitlePage titleId={3} />);
  // Under a title that shows its house, "house / pick a house" read as a house not set.
  expect(screen.queryByLabelText('house')).toBeNull();
  const select = screen.getByLabelText('change holder');
  const options = within(select).getAllByRole('option');
  expect(options.map((o) => o.textContent)).toEqual(['pick another house', 'House Vampa']);
  await userEvent.selectOptions(select, 'House Vampa');
  await userEvent.click(screen.getByRole('button', { name: 'Seat' }));
  expect(mutate).toHaveBeenCalledWith({ title_id: 3, org_id: 12 });
});

test("a rung inside a higher title's own chain offers no house picker", () => {
  currentDoc = { ...doc, title: { ...doc.title, chain_top_id: 99 } };
  try {
    renderWithProviders(<TitlePage titleId={3} />);
    expect(screen.queryByLabelText('house')).toBeNull();
  } finally {
    currentDoc = doc;
  }
});

test('a holding is renamed from its row', async () => {
  mutate.mockClear();
  renderWithProviders(<TitlePage titleId={3} />);
  await userEvent.click(screen.getByRole('button', { name: 'Rename a quarry' }));
  const input = screen.getByLabelText('name of a quarry');
  await userEvent.clear(input);
  await userEvent.type(input, 'North quarry');
  await userEvent.click(screen.getByRole('button', { name: 'Save name of a quarry' }));
  expect(mutate).toHaveBeenCalledWith({ holding_id: 1, name: 'North quarry' });
});

test('a land holding is placed on a room found by name', async () => {
  mutate.mockClear();
  renderWithProviders(<TitlePage titleId={3} />);
  await userEvent.click(screen.getByRole('button', { name: 'Site a quarry' }));
  await userEvent.type(screen.getByLabelText('room for a quarry'), 'Katta');
  await userEvent.click(screen.getByRole('button', { name: /Katta Fields/ }));
  expect(mutate).toHaveBeenCalledWith({ holding_id: 1, room_id: 77 });
});

test('a holding is removed only after a second press', async () => {
  mutate.mockClear();
  renderWithProviders(<TitlePage titleId={3} />);
  await userEvent.click(screen.getByRole('button', { name: 'Remove a quarry' }));
  expect(mutate).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole('button', { name: 'Confirm remove a quarry' }));
  expect(mutate).toHaveBeenCalledWith({ holding_id: 1 });
});

test('a rung is moved under another from its page', async () => {
  mutate.mockClear();
  renderWithProviders(<TitlePage titleId={3} />);
  const move = screen.getByRole('button', { name: 'Move' });
  expect(move).toBeDisabled();
  await userEvent.selectOptions(screen.getByLabelText('move under'), 'Kingdom of Umbros (kingdom)');
  await userEvent.click(move);
  expect(mutate).toHaveBeenCalledWith({ title_id: 3, parent_title_id: 8 });
});

test('a vacant rung is deleted only after a second press', async () => {
  mutate.mockClear();
  currentDoc = { ...doc, title: { ...doc.title, house_id: null, held_by: '', chain_top_id: 3 } };
  try {
    renderWithProviders(<TitlePage titleId={3} />);
    await userEvent.click(screen.getByRole('button', { name: 'Delete rung' }));
    expect(mutate).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole('button', { name: 'Confirm delete County of Katta' }));
    expect(mutate).toHaveBeenCalledWith({ title_id: 3 }, expect.anything());
  } finally {
    currentDoc = doc;
  }
});

test('a held rung is vacated only after a second press', async () => {
  mutate.mockClear();
  renderWithProviders(<TitlePage titleId={3} />);
  await userEvent.click(screen.getByRole('button', { name: 'Vacate' }));
  expect(mutate).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole('button', { name: 'Confirm vacate House Katta' }));
  expect(mutate).toHaveBeenCalledWith({ title_id: 3 });
});

test('cancelling the vacate confirm dispatches nothing', async () => {
  mutate.mockClear();
  renderWithProviders(<TitlePage titleId={3} />);
  await userEvent.click(screen.getByRole('button', { name: 'Vacate' }));
  await userEvent.click(screen.getByRole('button', { name: 'Cancel' }));
  expect(mutate).not.toHaveBeenCalled();
  expect(screen.getByRole('button', { name: 'Vacate' })).toBeInTheDocument();
});

test('a vacant rung offers no Vacate', () => {
  currentDoc = { ...doc, title: { ...doc.title, house_id: null, held_by: '', chain_top_id: 3 } };
  try {
    renderWithProviders(<TitlePage titleId={3} />);
    expect(screen.queryByRole('button', { name: 'Vacate' })).toBeNull();
  } finally {
    currentDoc = doc;
  }
});

test('a held rung offers no Delete', () => {
  renderWithProviders(<TitlePage titleId={3} />);
  expect(screen.queryByRole('button', { name: 'Delete rung' })).toBeNull();
});

test('a page that fails to load says so and offers a retry instead of loading forever', async () => {
  currentError = new Error('Failed to load the domain.');
  try {
    renderWithProviders(<TitlePage titleId={8} />);
    expect(screen.getByText('Failed to load the domain.')).toBeInTheDocument();
    expect(screen.queryByText('Loading the domain…')).toBeNull();
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }));
    expect(refetch).toHaveBeenCalled();
  } finally {
    currentError = null;
  }
});

test('an unseated title reads Undefined ruler; the slot lists the family roll, spouses marked, the dead last (#5017)', async () => {
  mutate.mockClear();
  currentDoc = { ...doc, title: { ...doc.title, holder_id: null, holder: '' } };
  try {
    renderWithProviders(<TitlePage titleId={3} />);
    expect(screen.queryByText('holder')).toBeNull();
    expect(screen.queryByRole('searchbox', { name: 'holder' })).toBeNull();
    await userEvent.click(screen.getByRole('button', { name: 'Undefined ruler' }));
    const slot = screen.getByRole('group', { name: 'Ruler' });
    const names = () =>
      within(slot)
        .getAllByRole('button')
        .map((b) => b.textContent)
        .filter((t) => t !== 'Add family member' && t !== 'Cancel');
    // Rook, a dalliance partner, is on the tree and off the roll: the server would refuse him.
    expect(names()).toEqual([
      'Aldo mar Katta',
      'Galleron married in',
      'Kathryn mar Katta PC',
      'Old Marr rip',
    ]);
    // Typing narrows the roll; it is never a search of everyone by exact name.
    await userEvent.type(within(slot).getByRole('searchbox', { name: 'Family member' }), 'gal');
    expect(names()).toEqual(['Galleron married in']);
    await userEvent.click(within(slot).getByRole('button', { name: 'Galleron married in' }));
    expect(mutate).toHaveBeenCalledWith({ title_id: 3, node_id: 12 });
    expect(screen.queryByRole('group', { name: 'Ruler' })).toBeNull();
  } finally {
    currentDoc = doc;
  }
});

test('Add family member creates the person in the holding family and seats them (#5017)', async () => {
  mutate.mockClear();
  currentDoc = { ...doc, title: { ...doc.title, holder_id: null, holder: '' } };
  try {
    renderWithProviders(<TitlePage titleId={3} />);
    await userEvent.click(screen.getByRole('button', { name: 'Undefined ruler' }));
    const slot = screen.getByRole('group', { name: 'Ruler' });
    await userEvent.click(within(slot).getByRole('button', { name: 'Add family member' }));
    await userEvent.type(within(slot).getByRole('textbox', { name: 'Name' }), 'Marrow{enter}');
    expect(mutate).toHaveBeenCalledWith(
      { family_id: 4, name: 'Marrow' },
      expect.objectContaining({ onSuccess: expect.any(Function) })
    );
    const options = mutate.mock.calls.at(-1)![1] as {
      onSuccess: (r: { success: boolean; message: string; data: unknown }) => void;
    };
    options.onSuccess({
      success: true,
      message: 'Marrow is on record.',
      data: { kinsperson_id: 44 },
    });
    expect(mutate).toHaveBeenLastCalledWith({ title_id: 3, node_id: 44 });
  } finally {
    currentDoc = doc;
  }
});

test('a seated title names its ruler as a link and offers Change ruler, which lists everyone else (#5017)', async () => {
  renderWithProviders(<TitlePage titleId={3} />);
  const heldBy = screen.getByText('held by', { selector: '.field .label' }).parentElement!;
  expect(within(heldBy).getByRole('link', { name: 'Kathryn mar Katta' })).toHaveAttribute(
    'href',
    '/staff/almanach/people/11'
  );
  await userEvent.click(within(heldBy).getByRole('button', { name: 'Change ruler' }));
  const slot = screen.getByRole('group', { name: 'Ruler' });
  expect(within(slot).queryByRole('button', { name: /Kathryn/ })).toBeNull();
  expect(within(slot).getByRole('button', { name: 'Galleron married in' })).toBeInTheDocument();
  await userEvent.click(within(slot).getByRole('button', { name: 'Cancel' }));
  expect(screen.queryByRole('group', { name: 'Ruler' })).toBeNull();
});

test('the trail over the page is the way up, every step a link but the title itself (#5039)', () => {
  renderWithProviders(<TitlePage titleId={3} />);
  const trail = screen.getByRole('navigation', { name: 'Breadcrumb' });
  expect(within(trail).getByRole('link', { name: 'Almanach' })).toHaveAttribute(
    'href',
    '/staff/almanach'
  );
  expect(within(trail).getByRole('link', { name: 'Umbros' })).toHaveAttribute(
    'href',
    '/staff/almanach/realms/1'
  );
  expect(within(trail).getByRole('link', { name: 'Kingdom of Umbros' })).toHaveAttribute(
    'href',
    '/staff/almanach/titles/8'
  );
  expect(within(trail).queryByRole('link', { name: 'County of Katta' })).toBeNull();
  expect(trail).toHaveTextContent('County of Katta');
});
