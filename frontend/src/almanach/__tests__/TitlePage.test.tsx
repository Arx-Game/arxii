/**
 * TitlePage (#4239): held by with the holder in person, Location as realm and
 * tier, Holdings, Books, Forces, and Vassals with Create vassal domain.
 */
import { screen, within } from '@testing-library/react';
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
};

vi.mock('../queries', () => ({
  useTitleDocument: () => ({ data: doc }),
  useSearch: () => ({ data: undefined }),
  useHouses: () => ({ data: { results: [] } }),
  useAlmanachMutation: () => ({ mutate: vi.fn(), mutateAsync: vi.fn() }),
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
  expect(screen.getByText('1,900 c / cycle')).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: 'Forces' })).toBeInTheDocument();
  expect(screen.getByText('Katta household guard')).toBeInTheDocument();
  const vassals = screen.getByRole('heading', { name: 'Vassals' }).nextElementSibling!;
  expect(within(vassals as HTMLElement).getByText('vacant')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Create vassal domain' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Add vacant seats' })).toBeInTheDocument();
  expect(screen.getByText('unsited')).toBeInTheDocument();
});
