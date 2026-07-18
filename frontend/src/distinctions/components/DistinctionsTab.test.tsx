/**
 * DistinctionsTab tests (#1446) — sheet-level distinctions list, secret badging, empty state.
 *
 * The server already filters secret rows for non-privileged viewers (`_build_distinctions`,
 * src/world/character_sheets/serializers.py:501) — this component only renders whatever
 * `useCharacterSheetQuery` returns, adding a `Secret` badge on rows where `is_secret` is true.
 */

import { render, screen } from '@testing-library/react';
import { vi } from 'vitest';

import { DistinctionsTab } from './DistinctionsTab';
import type { CharacterSheetPayload, CharacterSheetDistinction } from '@/character_sheets/api';

vi.mock('@/character_sheets/queries', () => ({
  useCharacterSheetQuery: vi.fn(),
}));

import * as queries from '@/character_sheets/queries';

function mockPayload(distinctions: CharacterSheetDistinction[] | undefined, isLoading = false) {
  vi.mocked(queries.useCharacterSheetQuery).mockReturnValue({
    data: distinctions === undefined ? undefined : ({ distinctions } as CharacterSheetPayload),
    isLoading,
  } as unknown as ReturnType<typeof queries.useCharacterSheetQuery>);
}

function makeDistinction(
  overrides: Partial<CharacterSheetDistinction> = {}
): CharacterSheetDistinction {
  return {
    id: 1,
    name: 'Iron Will',
    rank: 2,
    notes: 'Forged in the siege of Whitehold.',
    is_secret: false,
    is_from_glimpse: false,
    ...overrides,
  };
}

describe('DistinctionsTab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows the empty state when there are no distinctions', () => {
    mockPayload([]);
    render(<DistinctionsTab characterId={1} />);
    expect(screen.getByTestId('distinctions-empty-state')).toBeInTheDocument();
  });

  it('renders a row per distinction with rank, and badges only the secret one', () => {
    mockPayload([
      makeDistinction(),
      makeDistinction({ id: 2, name: 'Hidden Oath', rank: 1, is_secret: true }),
    ]);
    render(<DistinctionsTab characterId={1} />);

    const rows = screen.getAllByTestId('distinction-row');
    expect(rows).toHaveLength(2);

    expect(screen.getByText('Iron Will')).toBeInTheDocument();
    expect(screen.getByText('Rank 2')).toBeInTheDocument();
    expect(screen.getByText('Hidden Oath')).toBeInTheDocument();
    expect(screen.getByText('Rank 1')).toBeInTheDocument();

    expect(screen.getAllByText('Secret')).toHaveLength(1);
  });

  it('shows a spinner while loading', () => {
    mockPayload(undefined, true);
    const { container } = render(<DistinctionsTab characterId={1} />);
    expect(container.querySelector('.animate-spin')).toBeInTheDocument();
  });
});
