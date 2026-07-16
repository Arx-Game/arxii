/** RivalButton (#2170) — declare/withdraw an IC rival, double opt-in. Mocks the hooks. */
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { RivalButton } from '../components/RivalButton';
import type { Rivalry } from '../types';

const declareMutate = vi.fn();
const withdrawMutate = vi.fn();

vi.mock('@/friends/queries', () => ({
  useRivalsQuery: vi.fn(),
  useDeclareRivalMutation: vi.fn(() => ({
    mutate: declareMutate,
    isPending: false,
    isError: false,
  })),
  useWithdrawRivalMutation: vi.fn(() => ({
    mutate: withdrawMutate,
    isPending: false,
    isError: false,
  })),
}));

import { useRivalsQuery } from '@/friends/queries';

const mockQuery = vi.mocked(useRivalsQuery);

function mockRivals(results: Rivalry[]): void {
  mockQuery.mockReturnValue({
    data: { count: results.length, next: null, previous: null, results },
    isLoading: false,
    isError: false,
  } as ReturnType<typeof useRivalsQuery>);
}

function rivalry(overrides: Partial<Rivalry>): Rivalry {
  return {
    id: 1,
    rivaler_tenure: 10,
    rival_tenure: 20,
    rivaler_entry: 100,
    rival_entry: 200,
    rival_name: 'Bob',
    is_mutual: false,
    created_at: '2026-07-01T00:00:00Z',
    ...overrides,
  } as Rivalry;
}

describe('RivalButton', () => {
  it('renders nothing without an active viewer character', () => {
    mockRivals([]);
    const { container } = render(
      <RivalButton viewerEntryId={null} targetEntryId={200} targetName="Bob" />
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('declares a rival on click', () => {
    mockRivals([]);
    render(<RivalButton viewerEntryId={100} targetEntryId={200} targetName="Bob" />);
    fireEvent.click(screen.getByRole('button', { name: /declare rival/i }));
    expect(declareMutate).toHaveBeenCalledWith({ viewer: 100, rival: 200 });
  });

  it('shows pending state for a one-way declaration and withdraws on click', () => {
    mockRivals([rivalry({ id: 7, rivaler_entry: 100, rival_entry: 200 })]);
    render(<RivalButton viewerEntryId={100} targetEntryId={200} targetName="Bob" />);
    expect(screen.getByText(/mutual once Bob declares you back/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Withdraw' }));
    expect(withdrawMutate).toHaveBeenCalledWith(7);
  });

  it('shows mutual state once both sides declared', () => {
    mockRivals([rivalry({ rivaler_entry: 100, rival_entry: 200, is_mutual: true })]);
    render(<RivalButton viewerEntryId={100} targetEntryId={200} targetName="Bob" />);
    expect(screen.getByText(/you and Bob are mutual rivals/i)).toBeInTheDocument();
  });

  it('ignores declarations toward other characters', () => {
    mockRivals([rivalry({ rivaler_entry: 100, rival_entry: 999 })]);
    render(<RivalButton viewerEntryId={100} targetEntryId={200} targetName="Bob" />);
    expect(screen.getByRole('button', { name: /declare rival/i })).toBeInTheDocument();
  });
});
