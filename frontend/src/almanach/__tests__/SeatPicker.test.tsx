import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';

import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { SeatPicker } from '../founder/SeatPicker';
import { TIER_RANK } from '../founder/steps';
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
    claimable: false,
    seat_domain_id: null,
    comes_with: 'Fervor',
  },
  {
    title_id: 3,
    name: 'Caldera',
    is_defined: true,
    tier: 'duchy',
    level: 56,
    parent_title_id: null,
    house_id: 9,
    house_name: 'Solano',
    state: 'Held',
    is_seat_of: '',
    sworn_to: 'Piropa (crown)',
    demesne: 0,
    vassals: 0,
    claimable: false,
    seat_domain_id: null,
    comes_with: '',
  },
] satisfies LadderRow[];

vi.mock('../queries', () => ({
  useRealms: () => ({
    data: {
      results: [
        {
          id: 1,
          name: 'Inferna',
          formal_name: 'Grand Principality of Inferna',
          default_tithe_pct: 10,
          unclaimed_by_tier: {},
        },
      ],
    },
  }),
  useLadder: () => ({ data: { rows, unclaimed_by_tier: { duchy: 2, county: 1 } } }),
}));

test('gates the Claim column by the permitted tier and marks held/comes-with rows', () => {
  renderWithProviders(
    <SeatPicker
      realmId={1}
      permittedRank={TIER_RANK.county}
      onSelectRealm={vi.fn()}
      onClaim={vi.fn()}
    />
  );

  // A county-tier founder can't claim a duchy — no button on Fervor's row.
  expect(screen.queryByRole('button', { name: /claim fervor/i })).not.toBeInTheDocument();

  // The county row is bundled into Fervor's own claim ("comes with Fervor") —
  // a dash, never a button, regardless of the founder's permitted tier. Its
  // own `vassals` count is also 0, so the row carries two dashes; either is
  // proof the trailing cell rendered `—`, not a Claim button.
  const comesWithRow = screen.getByText('comes with Fervor').closest('tr') as HTMLElement;
  expect(comesWithRow).not.toBeNull();
  expect(within(comesWithRow).getAllByText('—').length).toBeGreaterThanOrEqual(1);
  expect(within(comesWithRow).queryByRole('button', { name: /claim/i })).not.toBeInTheDocument();

  // Caldera is already held — its trailing cell reads "held", not a button.
  expect(screen.getByText('held')).toBeInTheDocument();
});

test('a duke can claim Fervor', async () => {
  const onClaim = vi.fn();
  renderWithProviders(
    <SeatPicker
      realmId={1}
      permittedRank={TIER_RANK.duchy}
      onSelectRealm={vi.fn()}
      onClaim={onClaim}
    />
  );

  const button = screen.getByRole('button', { name: /claim fervor/i });
  await userEvent.click(button);

  expect(onClaim).toHaveBeenCalledTimes(1);
  expect(onClaim.mock.calls[0][0]).toEqual(
    expect.objectContaining({ title_id: 1, name: 'Fervor' })
  );
});
