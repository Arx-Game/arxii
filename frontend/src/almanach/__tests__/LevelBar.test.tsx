import { screen } from '@testing-library/react';

import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { LevelBar } from '../ladder/LevelBar';
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
  },
] satisfies LadderRow[];

function buttonLabels() {
  return screen.getAllByRole('button').map((button) => button.textContent?.trim());
}

test('lists only the tiers present among the rows, with no phantom March and "Ducal" for duchy', () => {
  renderWithProviders(
    <LevelBar rows={rows} unclaimedByTier={{}} pressedTier="duchy" onPressTier={() => {}} />
  );
  // No Kingdom (no kingdom-tier row in this fixture) and no March (no march-tier row either).
  expect(buttonLabels()).toEqual(['Ducal', 'County', 'Barony']);
});

test('folds a march row into the County button instead of a separate March button', () => {
  const withMarch: LadderRow[] = [
    ...rows,
    {
      title_id: 4,
      name: 'Ashgate',
      is_defined: true,
      tier: 'march',
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
      comes_with: '',
    },
  ];
  renderWithProviders(
    <LevelBar
      rows={withMarch}
      unclaimedByTier={{ county: 1, march: 1 }}
      pressedTier="duchy"
      onPressTier={() => {}}
    />
  );
  // Exactly one bar entry per displayed tier — no separate "March" button —
  // and the County button carries the folded county+march count (1 + 1 = 2).
  expect(buttonLabels()).toEqual(['Ducal', 'County2', 'Barony']);
  expect(screen.queryByText('March')).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: /^county/i })).toHaveTextContent('2');
});
