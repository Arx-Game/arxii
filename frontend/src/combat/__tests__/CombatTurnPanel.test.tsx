/**
 * Tests for CombatTurnPanel — Phase 7 scaffold + Phase 8 section composition.
 *
 * Mocks:
 * - @/combat/queries (useCombatEncounter, useAvailableCombos, useUpgradeCombo,
 *   useDispatchPlayerAction)
 * - @/scenes/actionQueries (fetchAvailableActions)
 * - @tanstack/react-query (useQuery — for the inline available-actions query)
 * - Section stubs: YourTurn, ResonanceBudget, VitalPools, CombatantsList,
 *   ActiveState, RoundFlow — to isolate panel smoke tests
 * - @/actions/ActionDeclarationCard (stub to keep tests fast)
 * - @/magic/queries (useCharacterResonances, useCharacterAnima)
 * - @/components/PersonaAvatar (stub)
 */

import { render, screen, within } from '@testing-library/react';
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
  useConsequenceOutcomes: vi.fn().mockReturnValue({
    data: [],
    isLoading: false,
    isError: false,
  }),
  combatKeys: {
    all: ['combat'],
    encounter: (id: number) => ['combat', 'encounter', id],
    combos: (id: number) => ['combat', 'combos', id],
    availableActions: (id: number) => ['combat', 'available-actions', id],
    consequenceOutcomes: (params: Record<string, unknown>) => [
      'combat',
      'consequence-outcomes',
      params,
    ],
  },
}));

vi.mock('@/scenes/actionQueries', () => ({
  fetchAvailableActions: vi.fn(),
}));

// Stub magic hooks used by rail sections
vi.mock('@/magic/queries', () => ({
  useCharacterResonances: vi.fn().mockReturnValue({
    data: [],
    isLoading: false,
    isError: false,
  }),
  useCharacterAnima: vi.fn().mockReturnValue({
    data: null,
    isLoading: false,
  }),
  useApplicablePulls: vi.fn().mockReturnValue({ data: [], isLoading: false }),
  useTechnique: vi.fn().mockReturnValue({ data: undefined, isLoading: false }),
  useThreads: vi.fn().mockReturnValue({ data: [], isLoading: false }),
}));

// Stub PersonaAvatar to avoid color computation in section tests
vi.mock('@/components/PersonaAvatar', () => ({
  PersonaAvatar: ({ source }: { source: { name: string } }) => (
    <span data-testid="persona-avatar">{source.name[0]?.toUpperCase()}</span>
  ),
}));

// Stub YourTurn to prevent full render complexity
vi.mock('../sections/YourTurn', () => ({
  YourTurn: ({ encounterId, roundNumber }: { encounterId: number; roundNumber: number }) => (
    <div data-testid="your-turn-stub">
      YourTurn enc={encounterId} round={roundNumber}
    </div>
  ),
}));

// Stub ActionDeclarationCard
vi.mock('@/actions/ActionDeclarationCard', () => ({
  ActionDeclarationCard: () => <div data-testid="action-declaration-card-stub" />,
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
    clashes: [],
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
  (combatQueries.useAvailableActions as ReturnType<typeof vi.fn>).mockReturnValue({
    data: [],
    isLoading: false,
    isError: false,
  });
  (combatQueries.useAvailableCombos as ReturnType<typeof vi.fn>).mockReturnValue({
    data: [],
    isLoading: false,
  });
  (combatQueries.useUpgradeCombo as ReturnType<typeof vi.fn>).mockReturnValue({
    mutate: vi.fn(),
    isPending: false,
  });
  (combatQueries.useDispatchPlayerAction as ReturnType<typeof vi.fn>).mockReturnValue({
    mutateAsync: vi.fn().mockResolvedValue({}),
    isPending: false,
  });
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

    render(<CombatTurnPanel encounterId={1} characterId={10} characterSheetId={100} />, {
      wrapper: createWrapper(),
    });

    expect(screen.getByTestId('combat-panel-loading')).toBeInTheDocument();
  });

  it('renders error state when encounter fails to load', () => {
    mockedUseCombatEncounter.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
    });

    render(<CombatTurnPanel encounterId={1} characterId={10} characterSheetId={100} />, {
      wrapper: createWrapper(),
    });

    expect(screen.getByTestId('combat-panel-error')).toBeInTheDocument();
  });

  it('renders the panel with header and YourTurn stub when participant', () => {
    mockEncounter({ round_number: 3, is_participant: true });

    render(<CombatTurnPanel encounterId={1} characterId={10} characterSheetId={100} />, {
      wrapper: createWrapper(),
    });

    expect(screen.getByTestId('combat-turn-panel')).toBeInTheDocument();
    expect(screen.getByText(/Your Turn — Round 3/)).toBeInTheDocument();
    expect(screen.getByTestId('your-turn-stub')).toBeInTheDocument();
  });

  it('shows observer badge and no YourTurn when not a participant', () => {
    mockEncounter({ is_participant: false });

    render(<CombatTurnPanel encounterId={1} characterId={10} characterSheetId={100} />, {
      wrapper: createWrapper(),
    });

    expect(screen.getByText(/Observer/i)).toBeInTheDocument();
    expect(screen.queryByTestId('your-turn-stub')).not.toBeInTheDocument();
    expect(screen.getByText(/observing this encounter/i)).toBeInTheDocument();
  });

  it('passes encounterId and roundNumber to YourTurn stub', () => {
    mockEncounter({ id: 7, round_number: 5, is_participant: true });

    render(<CombatTurnPanel encounterId={7} characterId={10} characterSheetId={100} />, {
      wrapper: createWrapper(),
    });

    expect(screen.getByTestId('your-turn-stub')).toHaveTextContent('enc=7');
    expect(screen.getByTestId('your-turn-stub')).toHaveTextContent('round=5');
  });
});

describe('CombatTurnPanel — Phase 8 rail sections', () => {
  it('renders all six sections in spec order', () => {
    mockEncounter({ is_participant: true });

    render(<CombatTurnPanel encounterId={1} characterId={10} characterSheetId={100} />, {
      wrapper: createWrapper(),
    });

    const panel = screen.getByTestId('combat-turn-panel');

    // All section testids must be present
    expect(within(panel).getByTestId('your-turn-stub')).toBeInTheDocument();
    expect(within(panel).getByTestId('resonance-budget-section')).toBeInTheDocument();
    expect(within(panel).getByTestId('vital-pools-section')).toBeInTheDocument();
    expect(within(panel).getByTestId('combatants-list-section')).toBeInTheDocument();
    expect(within(panel).getByTestId('active-state-section')).toBeInTheDocument();
    expect(within(panel).getByTestId('round-flow-section')).toBeInTheDocument();
  });

  it('sections appear in the correct top-to-bottom DOM order', () => {
    mockEncounter({ is_participant: true });

    render(<CombatTurnPanel encounterId={1} characterId={10} characterSheetId={100} />, {
      wrapper: createWrapper(),
    });

    const panel = screen.getByTestId('combat-turn-panel');
    const allChildren = Array.from(panel.querySelectorAll('[data-testid]'));
    const sectionOrder = allChildren
      .map((el) => el.getAttribute('data-testid'))
      .filter((id) =>
        [
          'your-turn-stub',
          'resonance-budget-section',
          'vital-pools-section',
          'combatants-list-section',
          'active-state-section',
          'round-flow-section',
        ].includes(id ?? '')
      );

    expect(sectionOrder).toEqual([
      'your-turn-stub',
      'resonance-budget-section',
      'vital-pools-section',
      'combatants-list-section',
      'active-state-section',
      'round-flow-section',
    ]);
  });

  it('all sections start expanded by default', () => {
    mockEncounter({ is_participant: true });

    render(<CombatTurnPanel encounterId={1} characterId={10} characterSheetId={100} />, {
      wrapper: createWrapper(),
    });

    // All toggle buttons should report aria-expanded=true
    const toggles = screen.getAllByRole('button', {
      name: /round flow|resonance budget|vital pools|combatants|active state/i,
    });
    toggles.forEach((toggle) => {
      expect(toggle).toHaveAttribute('aria-expanded', 'true');
    });
  });
});
