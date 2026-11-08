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
    name: 'Duchy of Katta',
    tier: 'duchy',
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
  },
  demesne: {
    domain_id: 30,
    name: 'the Katta lands',
    description: '',
    hall: 'the Katta hall',
    population: 1000,
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
  vassals: [{ title_id: 4, name: '', held_by: '', demesne: 2, vassals: 0 }],
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

vi.mock('../queries', () => ({
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
  useAlmanachMutation: () => ({ mutate, mutateAsync: vi.fn() }),
}));

test('the rung page: holder, location, holdings, books, forces, vassals', () => {
  renderWithProviders(<TitlePage titleId={3} />);
  expect(screen.getByRole('heading', { level: 3 })).toHaveTextContent('Duchy of Katta');
  expect(screen.getAllByRole('link', { name: 'House Katta' })[0]).toHaveAttribute(
    'href',
    '/staff/almanach/houses/9'
  );
  expect(screen.getAllByRole('link', { name: 'Kathryn mar Katta' })[0]).toHaveAttribute(
    'href',
    '/staff/almanach/people/11'
  );
  expect(screen.getByRole('heading', { name: 'Location' })).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: 'Books' })).toBeInTheDocument();
  expect(screen.getByText('1,900 c / week')).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: 'Forces' })).toBeInTheDocument();
  expect(screen.getByText('Katta household guard')).toBeInTheDocument();
  const vassals = screen.getByRole('heading', { name: 'Present Holdings' }).nextElementSibling!;
  expect(within(vassals as HTMLElement).getByText('vacant')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Create vassal domain' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Add vacant seats' })).toBeInTheDocument();
  expect(screen.getByText('unsited')).toBeInTheDocument();
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
  expect(screen.getByRole('link', { name: 'On the map' })).toHaveAttribute(
    'href',
    '/staff/world-builder'
  );
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
    const holdings = screen.getByRole('heading', { name: 'Present Holdings' }).nextElementSibling!;
    expect(within(holdings as HTMLElement).getByText('nothing')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Historical Charter' })).toBeInTheDocument();
  } finally {
    currentDoc = doc;
  }
});

test('an unnamed rung is named from its own page', async () => {
  mutate.mockClear();
  currentDoc = { ...doc, title: { ...doc.title, name: '', house_id: null, held_by: '' } };
  try {
    renderWithProviders(<TitlePage titleId={3} />);
    const save = screen.getByRole('button', { name: 'Name' });
    expect(save).toBeDisabled();
    await userEvent.type(
      screen.getByLabelText('name', { selector: '#r-name' }),
      'Kingdom of Umbros'
    );
    await userEvent.click(save);
    expect(mutate).toHaveBeenCalledWith({ title_id: 3, name: 'Kingdom of Umbros' });
  } finally {
    currentDoc = doc;
  }
});

test('a named rung offers Rename, enabled only once the name changes', async () => {
  mutate.mockClear();
  renderWithProviders(<TitlePage titleId={3} />);
  const rename = screen.getByRole('button', { name: 'Rename' });
  expect(rename).toBeDisabled();
  await userEvent.type(screen.getByLabelText('name', { selector: '#r-name' }), ' II');
  await userEvent.click(rename);
  expect(mutate).toHaveBeenCalledWith({ title_id: 3, name: 'Duchy of Katta II' });
});

test('a vacant rung seats an existing house from its page', async () => {
  mutate.mockClear();
  currentDoc = { ...doc, title: { ...doc.title, house_id: null, held_by: '', chain_top_id: 3 } };
  try {
    renderWithProviders(<TitlePage titleId={3} />);
    const seat = screen.getByRole('button', { name: 'Seat' });
    expect(seat).toBeDisabled();
    await userEvent.selectOptions(screen.getByLabelText('house'), 'House Vampa');
    await userEvent.click(seat);
    expect(mutate).toHaveBeenCalledWith({ title_id: 3, org_id: 12 });
  } finally {
    currentDoc = doc;
  }
});

test('a held rung can change hands but leaves its own holder out of the list', () => {
  renderWithProviders(<TitlePage titleId={3} />);
  const options = within(screen.getByLabelText('house')).getAllByRole('option');
  expect(options.map((o) => o.textContent)).toEqual(['pick a house', 'House Vampa']);
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
    await userEvent.click(screen.getByRole('button', { name: 'Confirm delete Duchy of Katta' }));
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
