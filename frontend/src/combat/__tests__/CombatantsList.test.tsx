/**
 * Tests for CombatantsList rail section.
 */

import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import type { ReactNode } from 'react';

// ---------------------------------------------------------------------------
// Module mocks — PersonaAvatar is used; stub it to simplify tests
// ---------------------------------------------------------------------------

vi.mock('@/components/PersonaAvatar', () => ({
  PersonaAvatar: ({ source }: { source: { name: string } }) => (
    <span data-testid="persona-avatar">{source.name[0].toUpperCase()}</span>
  ),
}));

import { CombatantsList } from '../sections/CombatantsList';
import type { EncounterDetail, Participant, Opponent } from '../types';

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

function makeParticipant(overrides: Partial<Participant> = {}): Participant {
  return {
    id: 1,
    character_name: 'Aerande',
    status: 'active',
    health: 8,
    max_health: 10,
    character_status: 'healthy',
    ...overrides,
  };
}

function makeOpponent(overrides: Partial<Opponent> = {}): Opponent {
  return {
    id: 1,
    name: 'Mire Knight',
    tier: 'elite',
    health: 5,
    max_health: 10,
    soak_value: null,
    probing_threshold: null,
    ...overrides,
  };
}

function makeEncounter(
  participants: Participant[] = [],
  opponents: Opponent[] = []
): EncounterDetail {
  return {
    id: 1,
    round_number: 1,
    is_participant: true,
    is_gm: false,
    participants,
    opponents,
    current_round_actions: [],
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

describe('CombatantsList', () => {
  it('renders PC rows from participants', () => {
    const encounter = makeEncounter(
      [
        makeParticipant({ id: 1, character_name: 'Aerande' }),
        makeParticipant({ id: 2, character_name: 'Lyris' }),
      ],
      []
    );

    render(<CombatantsList encounter={encounter} />, { wrapper: createWrapper() });

    expect(screen.getByTestId('participant-row-1')).toBeInTheDocument();
    expect(screen.getByTestId('participant-row-2')).toBeInTheDocument();
    expect(screen.getByText('Aerande')).toBeInTheDocument();
    expect(screen.getByText('Lyris')).toBeInTheDocument();
  });

  it('renders NPC rows from opponents', () => {
    const encounter = makeEncounter(
      [],
      [
        makeOpponent({ id: 10, name: 'Mire Knight' }),
        makeOpponent({ id: 11, name: 'Shadow Archer' }),
      ]
    );

    render(<CombatantsList encounter={encounter} />, { wrapper: createWrapper() });

    expect(screen.getByTestId('opponent-row-10')).toBeInTheDocument();
    expect(screen.getByTestId('opponent-row-11')).toBeInTheDocument();
    expect(screen.getByText('Mire Knight')).toBeInTheDocument();
    expect(screen.getByText('Shadow Archer')).toBeInTheDocument();
  });

  it('NPC rows have destructive styling to distinguish from PCs', () => {
    const encounter = makeEncounter(
      [makeParticipant({ id: 1 })],
      [makeOpponent({ id: 10 })]
    );

    render(<CombatantsList encounter={encounter} />, { wrapper: createWrapper() });

    const pcRow = screen.getByTestId('participant-row-1');
    const npcRow = screen.getByTestId('opponent-row-10');

    // NPC rows have border-destructive/30 class; PC rows do not
    expect(npcRow.className).toContain('border-destructive');
    expect(pcRow.className).not.toContain('border-destructive');
  });

  it('HP bar shows correct percentage for PC', () => {
    const encounter = makeEncounter(
      [makeParticipant({ id: 1, health: 5, max_health: 10 })],
      []
    );

    render(<CombatantsList encounter={encounter} />, { wrapper: createWrapper() });

    const row = screen.getByTestId('participant-row-1');
    // Inside the row there should be a fill bar with width=50%
    const fill = row.querySelector('[style*="width: 50%"]');
    expect(fill).not.toBeNull();
  });

  it('renders empty message when no combatants', () => {
    const encounter = makeEncounter([], []);

    render(<CombatantsList encounter={encounter} />, { wrapper: createWrapper() });

    expect(screen.getByTestId('combatants-empty')).toBeInTheDocument();
  });

  it('collapses content when collapsed=true', () => {
    const encounter = makeEncounter([makeParticipant({ id: 1 })], []);

    render(<CombatantsList encounter={encounter} collapsed={true} />, {
      wrapper: createWrapper(),
    });

    expect(screen.queryByTestId('participant-row-1')).not.toBeInTheDocument();
  });

  it('renders PersonaAvatar for each combatant', () => {
    const encounter = makeEncounter(
      [makeParticipant({ id: 1, character_name: 'Aerande' })],
      [makeOpponent({ id: 10, name: 'Knight' })]
    );

    render(<CombatantsList encounter={encounter} />, { wrapper: createWrapper() });

    const avatars = screen.getAllByTestId('persona-avatar');
    expect(avatars.length).toBeGreaterThanOrEqual(2);
  });
});
