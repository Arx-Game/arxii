import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';

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
    sworn_to_house_id: 9,
    sworn_to_title_id: null,
    demesne: 1,
    vassals: 2,
    population: 4200,
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
    sworn_to_house_id: null,
    sworn_to_title_id: 1,
    demesne: 1,
    vassals: 0,
    population: 1000,
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
    sworn_to_house_id: null,
    sworn_to_title_id: 7,
    demesne: 1,
    vassals: 0,
    population: 1000,
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
  sworn_to_house_id: 9,
  sworn_to_title_id: null,
  demesne: 2,
  vassals: 2,
  population: 2500,
  claimable: false,
  seat_domain_id: null,
  comes_with: '',
  chain_top_id: 4,
  claimant_name: 'Piropa',
} satisfies LadderRow;

test('a titular or potential rung shows its state where the holder would be', () => {
  const titular = {
    ...rows[0],
    title_id: 90,
    name: 'Old Inferna',
    state: 'Titular',
    population: 1000,
    claimable: false,
  };
  const potential = {
    ...rows[0],
    title_id: 91,
    name: '',
    is_defined: false,
    state: 'Potential',
    population: 1000,
    claimable: false,
  };
  renderWithProviders(<LadderTable rows={[titular, potential]} />);
  expect(screen.getByText('Titular')).toBeInTheDocument();
  expect(screen.getByText('Potential')).toBeInTheDocument();
  expect(screen.queryByText('Unclaimed')).not.toBeInTheDocument();
});

test('renders states before names, seat marks, and collapses children', async () => {
  renderWithProviders(<LadderTable rows={rows} />);
  expect(screen.getByText('Undefined')).toBeInTheDocument();
  expect(screen.getByText('seat of Piropa')).toBeInTheDocument();
  expect(screen.getAllByText('Unclaimed').length).toBe(2);
  await userEvent.click(screen.getByRole('button', { name: /collapse fervor/i }));
  expect(screen.queryByText('comes with Fervor')).not.toBeInTheDocument();
});

test('every row carries its people, summed over the land beneath a duchy (#5069)', () => {
  renderWithProviders(<LadderTable rows={rows} />);
  expect(screen.getByRole('columnheader', { name: /population/ })).toBeInTheDocument();
  const fervor = screen.getByRole('button', { name: /collapse fervor/i }).closest('tr')!;
  expect(within(fervor).getByText('4,200')).toBeInTheDocument();
});

test(`a contested title gets the plate's cl row and "claimed by <name>" replaces sworn to`, () => {
  const { container } = renderWithProviders(<LadderTable rows={[...rows, contestedRow]} />);
  expect(screen.getByText('claimed by Piropa')).toBeInTheDocument();
  expect(container.querySelector('tr.cl')).not.toBeNull();
  expect(container.querySelector('tr.cl')?.textContent).toContain('Brasa');
});

describe('with rowHref', () => {
  const href = (row: LadderRow) => `/staff/almanach/titles/${row.title_id}`;

  test('a defined name and the Undefined chip both link to the rung page', () => {
    renderWithProviders(<LadderTable rows={rows} rowHref={href} />);
    expect(screen.getByRole('link', { name: 'Fervor' })).toHaveAttribute(
      'href',
      '/staff/almanach/titles/1'
    );
    expect(screen.getByRole('link', { name: 'Open undefined county' })).toHaveAttribute(
      'href',
      '/staff/almanach/titles/2'
    );
  });

  test('the tier label selects the row instead of the name', async () => {
    const onSelectRow = vi.fn();
    renderWithProviders(<LadderTable rows={rows} rowHref={href} onSelectRow={onSelectRow} />);
    await userEvent.click(screen.getByRole('button', { name: 'Select Fervor' }));
    expect(onSelectRow).toHaveBeenCalledWith(expect.objectContaining({ title_id: 1 }));
  });
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

test("the staff ladder opens a rung's house and what it is sworn to; a player's stays text (#5106)", () => {
  const { unmount } = renderWithProviders(<LadderTable rows={rows} linked />);
  // Held by: the house's own page.
  expect(screen.getByRole('link', { name: 'Piropa' })).toHaveAttribute(
    'href',
    '/staff/almanach/houses/9'
  );
  // Sworn to: a house where the name is a house, a title where it is a title.
  expect(screen.getByRole('link', { name: 'Piropa (crown)' })).toHaveAttribute(
    'href',
    '/staff/almanach/houses/9'
  );
  expect(screen.getByRole('link', { name: 'County of Inferna' })).toHaveAttribute(
    'href',
    '/staff/almanach/titles/7'
  );
  unmount();

  renderWithProviders(<LadderTable rows={rows} />);
  expect(screen.getByText('Piropa (crown)')).toBeInTheDocument();
  expect(screen.queryByRole('link', { name: 'Piropa (crown)' })).not.toBeInTheDocument();
  expect(screen.queryByRole('link', { name: 'Piropa' })).not.toBeInTheDocument();
});
