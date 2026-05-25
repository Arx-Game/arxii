/**
 * Tests for ActiveState rail section.
 *
 * Provides mocked encounter data with clash state.
 */

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import type { ReactNode } from 'react';

import { ActiveState } from '../sections/ActiveState';
import type { EncounterDetail, ClashState } from '../types';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

function makeClash(overrides: Partial<ClashState> = {}): ClashState {
  return {
    id: 1,
    flavor: 'CLASH',
    status: 'ACTIVE',
    progress: 2,
    pc_win_threshold: 5,
    npc_win_threshold: -5,
    npc_opponent: 10,
    contributors: [],
    side_favored: 'EVEN',
    ...overrides,
  };
}

function makeEncounter(clashes: ClashState[] = []): EncounterDetail {
  return {
    id: 1,
    round_number: 1,
    is_participant: true,
    is_gm: false,
    participants: [],
    opponents: [
      {
        id: 10,
        name: 'Mire Knight',
        tier: 'elite',
        health: 10,
        max_health: 10,
        soak_value: null,
        probing_threshold: null,
      },
    ],
    current_round_actions: [],
    clashes: clashes as unknown as EncounterDetail['clashes'],
    created_at: '2026-01-01T00:00:00Z',
  };
}

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------

beforeEach(() => {
  vi.clearAllMocks();
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('ActiveState', () => {
  it('shows empty message when no clashes', () => {
    render(<ActiveState encounter={makeEncounter([])} />, { wrapper: createWrapper() });

    expect(screen.getByTestId('active-state-empty')).toBeInTheDocument();
  });

  it('renders one card per active clash', () => {
    const clashes = [
      makeClash({ id: 1 }),
      makeClash({ id: 2, flavor: 'WARD', npc_win_threshold: null }),
    ];

    render(<ActiveState encounter={makeEncounter(clashes)} />, { wrapper: createWrapper() });

    expect(screen.getByTestId('clash-card-1')).toBeInTheDocument();
    expect(screen.getByTestId('clash-card-2')).toBeInTheDocument();
  });

  it('shows flavor kind label on each card', () => {
    const clashes = [makeClash({ id: 1, flavor: 'CLASH' })];

    render(<ActiveState encounter={makeEncounter(clashes)} />, { wrapper: createWrapper() });

    expect(screen.getByTestId('clash-kind-1')).toHaveTextContent('Clash');
  });

  it('renders meter with correct width for progress', () => {
    // progress=2, npc=-5, pc=5 → range=10, position=7/10 = 70%
    const clashes = [makeClash({ id: 1, progress: 2, pc_win_threshold: 5, npc_win_threshold: -5 })];

    render(<ActiveState encounter={makeEncounter(clashes)} />, { wrapper: createWrapper() });

    const meter = screen.getByTestId('clash-meter-1');
    expect(meter).toHaveStyle({ width: '70%' });
  });

  it('renders Commit and Lend buttons per card', () => {
    const clashes = [makeClash({ id: 1 })];

    render(<ActiveState encounter={makeEncounter(clashes)} />, { wrapper: createWrapper() });

    expect(screen.getByTestId('clash-commit-btn-1')).toBeInTheDocument();
    expect(screen.getByTestId('clash-lend-btn-1')).toBeInTheDocument();
  });

  it('calls onCommitClick with clash id when Commit is clicked', async () => {
    const user = userEvent.setup();
    const onCommit = vi.fn();
    const clashes = [makeClash({ id: 5 })];

    render(<ActiveState encounter={makeEncounter(clashes)} onCommitClick={onCommit} />, {
      wrapper: createWrapper(),
    });

    await user.click(screen.getByTestId('clash-commit-btn-5'));
    expect(onCommit).toHaveBeenCalledWith(5);
  });

  it('shows opponent name on the card', () => {
    const clashes = [makeClash({ id: 1, npc_opponent: 10 })];

    render(<ActiveState encounter={makeEncounter(clashes)} />, { wrapper: createWrapper() });

    expect(screen.getByText(/Mire Knight/)).toBeInTheDocument();
  });

  it('collapses content when collapsed=true', () => {
    const clashes = [makeClash({ id: 1 })];

    render(<ActiveState encounter={makeEncounter(clashes)} collapsed={true} />, {
      wrapper: createWrapper(),
    });

    expect(screen.queryByTestId('clash-card-1')).not.toBeInTheDocument();
  });
});
