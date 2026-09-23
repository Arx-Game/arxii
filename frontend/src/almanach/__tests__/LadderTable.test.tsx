import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { buildLadderTree } from '../ladder/tree';
import { LadderTable } from '../ladder/LadderTable';
import type { LadderRow } from '../types';

const rows = [
  {
    title_id: 1,
    name: 'Fervor',
    is_defined: true,
    tier: 'duchy',
    level: 56,
    parent_title_id: null,
    house_id: null,
    house_name: '',
    state: 'Unclaimed',
    is_seat_of: '',
    sworn_to: 'Piropa (crown)',
    demesne: 1,
    vassals: 2,
    claimable: true,
    seat_domain_id: null,
    comes_with: '',
    chain_top_id: 1,
    claimant_name: '',
  },
  {
    title_id: 2,
    name: '',
    is_defined: false,
    tier: 'county',
    level: 53,
    parent_title_id: 1,
    house_id: null,
    house_name: '',
    state: 'Unclaimed',
    is_seat_of: '',
    sworn_to: 'Fervor',
    demesne: 1,
    vassals: 0,
    claimable: true,
    seat_domain_id: null,
    comes_with: 'Fervor',
    chain_top_id: 1,
    claimant_name: '',
  },
  {
    title_id: 3,
    name: 'Perdition',
    is_defined: true,
    tier: 'barony',
    level: 46,
    parent_title_id: null,
    house_id: 9,
    house_name: 'Piropa',
    state: 'Held',
    is_seat_of: 'Piropa',
    sworn_to: 'County of Inferna',
    demesne: 1,
    vassals: 0,
    claimable: false,
    seat_domain_id: null,
    comes_with: '',
    chain_top_id: 3,
    claimant_name: '',
  },
] satisfies LadderRow[];

const contestedRow = {
  title_id: 4,
  name: 'Brasa',
  is_defined: true,
  tier: 'duchy',
  level: 56,
  parent_title_id: null,
  house_id: 20,
  house_name: 'Luxen',
  state: 'Held',
  is_seat_of: '',
  sworn_to: 'Piropa (crown)',
  demesne: 2,
  vassals: 2,
  claimable: false,
  seat_domain_id: null,
  comes_with: '',
  chain_top_id: 4,
  claimant_name: 'Piropa',
} satisfies LadderRow;

test('renders states before names, seat marks, and collapses children', async () => {
  renderWithProviders(<LadderTable rows={rows} />);
  expect(screen.getByText('Undefined')).toBeInTheDocument();
  expect(screen.getByText('seat of Piropa')).toBeInTheDocument();
  expect(screen.getAllByText('Unclaimed').length).toBe(2);
  await userEvent.click(screen.getByRole('button', { name: /collapse fervor/i }));
  expect(screen.queryByText('comes with Fervor')).not.toBeInTheDocument();
});

test(`a contested title gets the plate's cl row and "claimed by <name>" replaces sworn to`, () => {
  const { container } = renderWithProviders(<LadderTable rows={[...rows, contestedRow]} />);
  expect(screen.getByText('claimed by Piropa')).toBeInTheDocument();
  expect(container.querySelector('tr.cl')).not.toBeNull();
  expect(container.querySelector('tr.cl')?.textContent).toContain('Brasa');
});

describe('buildLadderTree', () => {
  test('nests a row under its parent_title_id and leaves unmatched parents as roots', () => {
    const tree = buildLadderTree(rows);
    expect(tree.map((node) => node.row.title_id)).toEqual([1, 3]);
    const fervor = tree.find((node) => node.row.title_id === 1);
    expect(fervor?.children.map((node) => node.row.title_id)).toEqual([2]);
    expect(fervor?.depth).toBe(0);
    expect(fervor?.children[0]?.depth).toBe(1);
    const perdition = tree.find((node) => node.row.title_id === 3);
    expect(perdition?.children).toEqual([]);
  });
});
