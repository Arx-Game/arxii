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
    claimable: false,
    seat_domain_id: null,
    comes_with: 'Fervor',
    chain_top_id: 1,
    claimant_name: '',
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
    chain_top_id: 3,
    claimant_name: '',
  },
] satisfies LadderRow[];

// An undefined chain top (final review I5): `comes_with` reports "" for
// EVERY row here, including the internal seat county — only `chain_top_id`
// tells the county apart from a second, separate claimable rung. Regression
// coverage for the bug where the county's own Claim button leaked through
// because the old `comes_with !== ''` dash gate never fired on a blank name.
const undefinedTopRows = [
  {
    title_id: 10,
    name: '',
    is_defined: false,
    tier: 'duchy',
    level: 56,
    parent_title_id: null,
    house_id: null,
    house_name: '',
    state: 'Unclaimed',
    is_seat_of: '',
    sworn_to: 'Piropa (crown)',
    demesne: 1,
    vassals: 1,
    claimable: true,
    seat_domain_id: null,
    comes_with: '',
    chain_top_id: 10,
    claimant_name: '',
  },
  {
    title_id: 11,
    name: '',
    is_defined: false,
    tier: 'county',
    level: 53,
    parent_title_id: 10,
    house_id: null,
    house_name: '',
    state: 'Unclaimed',
    is_seat_of: '',
    sworn_to: '',
    demesne: 0,
    vassals: 0,
    claimable: true,
    seat_domain_id: null,
    comes_with: '',
    chain_top_id: 10,
    claimant_name: '',
  },
] satisfies LadderRow[];

// A mutable indirection so `useLadder`'s mocked rows can swap to
// `undefinedTopRows` for the one regression test below without a second
// mock factory (the factory closes over `ladderRows`, read at call time).
let ladderRows: LadderRow[] = rows;

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
  useLadder: () => ({ data: { rows: ladderRows, unclaimed_by_tier: { duchy: 2, county: 1 } } }),
}));

test('gates the Claim column by the permitted tier and marks held/comes-with rows', () => {
  renderWithProviders(
    <SeatPicker
      realmId={1}
      permittedRank={TIER_RANK.county}
      selectedTitleId={null}
      onSelectRow={vi.fn()}
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
      selectedTitleId={null}
      onSelectRow={vi.fn()}
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

test('selecting a row by name calls onSelectRow and the row carries .sel', () => {
  const onSelectRow = vi.fn();
  renderWithProviders(
    <SeatPicker
      realmId={1}
      permittedRank={TIER_RANK.duchy}
      selectedTitleId={3}
      onSelectRow={onSelectRow}
      onSelectRealm={vi.fn()}
      onClaim={vi.fn()}
    />
  );

  // Caldera (title_id 3) is the controlled selection — its row carries `.sel`.
  const caldera = screen.getByRole('button', { name: /select caldera/i }).closest('tr');
  expect(caldera?.className).toContain('sel');

  // Clicking Fervor's own name button reports the row up to the caller —
  // `SeatPicker` doesn't own selection state itself (fix round 1, Finding 2).
  const fervor = screen.getByRole('button', { name: /select fervor/i });
  fervor.click();
  expect(onSelectRow).toHaveBeenCalledWith(expect.objectContaining({ title_id: 1 }));
});

test('an undefined chain top never leaks a Claim button onto its own internal county (I5)', () => {
  ladderRows = undefinedTopRows;
  try {
    renderWithProviders(
      <SeatPicker
        realmId={1}
        permittedRank={TIER_RANK.duchy}
        selectedTitleId={null}
        onSelectRow={vi.fn()}
        onSelectRealm={vi.fn()}
        onClaim={vi.fn()}
      />
    );

    // The undefined duchy is itself a chain top (`chain_top_id === title_id`)
    // and gets the Claim button — exactly one, never a second leaked onto
    // its own internal county.
    expect(screen.getAllByRole('button', { name: 'Claim' })).toHaveLength(1);

    // Its internal seat county (`chain_top_id: 10 !== title_id: 11`) gets the
    // dash, even though `comes_with` is blank too and `claimable`/`state`
    // alone would otherwise have let the old gate show a second button.
    const countyRow = screen
      .getByRole('button', { name: 'Select undefined county' })
      .closest('tr') as HTMLElement;
    expect(within(countyRow).queryByRole('button', { name: /claim/i })).not.toBeInTheDocument();
    // The trailing (Claim) cell specifically — the row's other dashes
    // (sworn to/demesne/vassals) would read this way regardless of I5.
    const trailingCell = countyRow.querySelector('td:last-child') as HTMLElement;
    expect(within(trailingCell).getByText('—')).toBeInTheDocument();
  } finally {
    ladderRows = rows;
  }
});
