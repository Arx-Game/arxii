/**
 * Tests for CombatTurnPanel — Task 7.1 scaffold + slot composition.
 *
 * Mocks:
 * - @/combat/queries (useCombatEncounter, useAvailableCombos, useUpgradeCombo,
 *   useDispatchPlayerAction)
 * - @/scenes/actionQueries (fetchAvailableActions)
 * - @tanstack/react-query (useQuery — for the inline available-actions query)
 * - @/combat/sections/YourTurn (stub to isolate panel smoke tests)
 * - @/actions/ActionDeclarationCard (stub to keep tests fast)
 */

import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import type { ReactNode } from 'react';

// ---------------------------------------------------------------------------
// Module mocks — hoisted before imports
// ---------------------------------------------------------------------------

vi.mock('@/combat/queries', () => ({
  useCombatEncounter: vi.fn(),
  useAvailableCombos: vi.fn(),
  useUpgradeCombo: vi.fn(),
  useDispatchPlayerAction: vi.fn(),
  useAvailableActions: vi.fn().mockReturnValue({
    data: [],
    isLoading: false,
    isError: false,
  }),
  combatKeys: {
    all: ['combat'],
    encounter: (id: number) => ['combat', 'encounter', id],
    combos: (id: number) => ['combat', 'combos', id],
    availableActions: (id: number) => ['combat', 'available-actions', id],
  },
}));

vi.mock('@/scenes/actionQueries', () => ({
  fetchAvailableActions: vi.fn(),
}));

// Stub YourTurn to prevent full render complexity
vi.mock('../sections/YourTurn', () => ({
  YourTurn: ({ encounterId, roundNumber }: { encounterId: number; roundNumber: number }) => (
    <div data-testid="your-turn-stub">
      YourTurn enc={encounterId} round={roundNumber}
    </div>
  ),
}));

import * as combatQueries from '@/combat/queries';
import { CombatTurnPanel } from '../CombatTurnPanel';
import type { EncounterDetail } from '../types';

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

const mockedUseCombatEncounter = combatQueries.useCombatEncounter as ReturnType<typeof vi.fn>;

function mockEncounter(overrides?: Partial<EncounterDetail>) {
  const encounter: EncounterDetail = {
    id: 1,
    round_number: 1,
    is_participant: true,
    is_gm: false,
    participants: [],
    opponents: [],
    current_round_actions: [],
    created_at: '2026-05-24T00:00:00Z',
    ...overrides,
  };
  mockedUseCombatEncounter.mockReturnValue({
    data: encounter,
    isLoading: false,
    isError: false,
  });
  return encounter;
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

describe('CombatTurnPanel — render smoke', () => {
  it('renders loading state while encounter is loading', () => {
    mockedUseCombatEncounter.mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
    });

    render(
      <CombatTurnPanel encounterId={1} characterId={10} characterSheetId={100} />,
      { wrapper: createWrapper() }
    );

    expect(screen.getByTestId('combat-panel-loading')).toBeInTheDocument();
  });

  it('renders error state when encounter fails to load', () => {
    mockedUseCombatEncounter.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
    });

    render(
      <CombatTurnPanel encounterId={1} characterId={10} characterSheetId={100} />,
      { wrapper: createWrapper() }
    );

    expect(screen.getByTestId('combat-panel-error')).toBeInTheDocument();
  });

  it('renders the panel with header and YourTurn stub when participant', () => {
    mockEncounter({ round_number: 3, is_participant: true });

    render(
      <CombatTurnPanel encounterId={1} characterId={10} characterSheetId={100} />,
      { wrapper: createWrapper() }
    );

    expect(screen.getByTestId('combat-turn-panel')).toBeInTheDocument();
    expect(screen.getByText(/Your Turn — Round 3/)).toBeInTheDocument();
    expect(screen.getByTestId('your-turn-stub')).toBeInTheDocument();
  });

  it('shows observer badge and no YourTurn when not a participant', () => {
    mockEncounter({ is_participant: false });

    render(
      <CombatTurnPanel encounterId={1} characterId={10} characterSheetId={100} />,
      { wrapper: createWrapper() }
    );

    expect(screen.getByText(/Observer/i)).toBeInTheDocument();
    expect(screen.queryByTestId('your-turn-stub')).not.toBeInTheDocument();
    expect(screen.getByText(/observing this encounter/i)).toBeInTheDocument();
  });

  it('passes encounterId and roundNumber to YourTurn stub', () => {
    mockEncounter({ id: 7, round_number: 5, is_participant: true });

    render(
      <CombatTurnPanel encounterId={7} characterId={10} characterSheetId={100} />,
      { wrapper: createWrapper() }
    );

    expect(screen.getByTestId('your-turn-stub')).toHaveTextContent('enc=7');
    expect(screen.getByTestId('your-turn-stub')).toHaveTextContent('round=5');
  });
});
