/**
 * Tests for RoundFlow rail section.
 */

import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import type { ReactNode } from 'react';

import { RoundFlow } from '../sections/RoundFlow';
import type { EncounterDetail, Participant } from '../types';

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

function makeParticipant(id: number, name: string): Participant {
  return {
    id,
    character_name: name,
    status: 'active',
    health: 10,
    max_health: 10,
    character_status: 'healthy',
  };
}

function makeEncounter(
  participants: Participant[] = [],
  actedParticipantIds: number[] = [],
  roundNumber = 1
): EncounterDetail {
  const currentRoundActions = actedParticipantIds.map((pid) => ({ participant: pid }));
  return {
    id: 1,
    round_number: roundNumber,
    is_participant: true,
    is_gm: false,
    participants,
    opponents: [],
    current_round_actions: currentRoundActions,
    clashes: [],
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

describe('RoundFlow', () => {
  it('shows round number in summary line', () => {
    const encounter = makeEncounter([], [], 3);

    render(<RoundFlow encounter={encounter} />, { wrapper: createWrapper() });

    expect(screen.getByTestId('round-flow-summary')).toHaveTextContent('Round 3');
  });

  it('shows acted/total count in summary line', () => {
    const participants = [makeParticipant(1, 'Aerande'), makeParticipant(2, 'Lyris')];
    // Only participant 1 has acted
    const encounter = makeEncounter(participants, [1], 1);

    render(<RoundFlow encounter={encounter} />, { wrapper: createWrapper() });

    expect(screen.getByTestId('round-flow-summary')).toHaveTextContent('1/2 acted');
  });

  it('renders one chip per participant', () => {
    const participants = [
      makeParticipant(1, 'Aerande'),
      makeParticipant(2, 'Lyris'),
      makeParticipant(3, 'Ravan'),
    ];
    const encounter = makeEncounter(participants, [], 1);

    render(<RoundFlow encounter={encounter} />, { wrapper: createWrapper() });

    expect(screen.getByTestId('initiative-chip-1')).toBeInTheDocument();
    expect(screen.getByTestId('initiative-chip-2')).toBeInTheDocument();
    expect(screen.getByTestId('initiative-chip-3')).toBeInTheDocument();
  });

  it('acted chip has checkmark and emerald styling', () => {
    const participants = [makeParticipant(1, 'Aerande')];
    const encounter = makeEncounter(participants, [1], 1);

    render(<RoundFlow encounter={encounter} />, { wrapper: createWrapper() });

    const chip = screen.getByTestId('initiative-chip-1');
    expect(chip.className).toContain('bg-emerald-500');
    expect(chip.textContent).toContain('✓');
  });

  it('pending chip has ellipsis and muted styling', () => {
    const participants = [makeParticipant(2, 'Lyris')];
    const encounter = makeEncounter(participants, [], 1);

    render(<RoundFlow encounter={encounter} />, { wrapper: createWrapper() });

    const chip = screen.getByTestId('initiative-chip-2');
    expect(chip.className).toContain('text-muted-foreground');
    expect(chip.textContent).toContain('…');
  });

  it('declarations counter shows correct ratio', () => {
    const participants = [makeParticipant(1, 'A'), makeParticipant(2, 'B'), makeParticipant(3, 'C')];
    const encounter = makeEncounter(participants, [1, 3], 2);

    render(<RoundFlow encounter={encounter} />, { wrapper: createWrapper() });

    expect(screen.getByTestId('declarations-counter')).toHaveTextContent('2 / 3');
  });

  it('shows empty message when no participants', () => {
    const encounter = makeEncounter([], [], 1);

    render(<RoundFlow encounter={encounter} />, { wrapper: createWrapper() });

    expect(screen.getByTestId('round-flow-empty')).toBeInTheDocument();
  });

  it('collapses content when collapsed=true', () => {
    const encounter = makeEncounter([makeParticipant(1, 'A')], [], 1);

    render(<RoundFlow encounter={encounter} collapsed={true} />, { wrapper: createWrapper() });

    expect(screen.queryByTestId('initiative-chip-1')).not.toBeInTheDocument();
    expect(screen.queryByTestId('round-flow-summary')).not.toBeInTheDocument();
  });
});
