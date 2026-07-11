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
  useEndEncounter: vi.fn(),
  useJoinMutation: vi.fn().mockReturnValue({ mutate: vi.fn(), isPending: false }),
  useLeaveMutation: vi.fn().mockReturnValue({ mutate: vi.fn(), isPending: false }),
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
  // AudereOfferGate hooks — no pending offers in panel smoke tests.
  usePendingAudereOffers: vi.fn().mockReturnValue({ data: undefined, isLoading: false }),
  useRespondToAudere: vi.fn().mockReturnValue({ mutate: vi.fn(), isPending: false }),
  // AudereMajoraOfferGate hooks — no pending crossing offers in panel smoke tests.
  usePendingAudereMajoraOffers: vi.fn().mockReturnValue({ data: undefined, isLoading: false }),
  useRespondToAudereMajora: vi.fn().mockReturnValue({ mutate: vi.fn(), isPending: false }),
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

// Stub ConditionBadge — the real one dispatches to Redux (no Provider here).
vi.mock('../components/ConditionBadge', () => ({
  ConditionBadge: ({ condition }: { condition: { id: number; name: string } }) => (
    <span data-testid={`condition-badge-stub-${condition.id}`}>{condition.name}</span>
  ),
}));

import * as combatQueries from '@/combat/queries';
import { CombatTurnPanel } from '../CombatTurnPanel';
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

const mockedUseCombatEncounter = combatQueries.useCombatEncounter as ReturnType<typeof vi.fn>;

function mockEncounter(overrides?: Partial<EncounterDetail>) {
  const encounter: EncounterDetail = {
    id: 1,
    scene: 1,
    round_number: 1,
    is_participant: true,
    is_gm: false,
    participants: [],
    opponents: [],
    current_round_actions: [],
    clashes: [],
    engagement_locks: [],
    created_at: '2026-05-24T00:00:00Z',
    outcome: '',
    completed_at: null,
    escalation_curve_name: null,
    escalation_start_round: null,
    escalation_tick_narration: null,
    forced_escape: false,
    resolution_order: [],
    position_adjacency: [],
    position_nodes: [],
    position_edges: [],
    is_lethal: false,
    duel_winner: null,
    surge_beats: [],
    ...overrides,
  };
  mockedUseCombatEncounter.mockReturnValue({
    data: encounter,
    isLoading: false,
    isError: false,
  });
  return encounter;
}

/**
 * Viewer participant fixture. The viewer's own row is matched by character_sheet_id
 * (= the characterSheetId prop passed in these tests), not by health presence. (#918)
 */
function makeParticipant(overrides: Partial<Participant> = {}): Participant {
  return {
    id: 1,
    character_sheet_id: 100,
    character_name: 'Aerande',
    status: 'active',
    health: 8,
    max_health: 10,
    character_status: 'healthy',
    available_strain: null,
    fatigue: null,
    active_conditions: [],
    thumbnail_url: '',
    thumbnail_media_url: null,
    escalation_level: null,
    intensity_modifier: null,
    control_modifier: null,
    current_position: null,
    ...overrides,
  };
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
  (combatQueries.useEndEncounter as ReturnType<typeof vi.fn>).mockReturnValue({
    mutate: vi.fn(),
    isPending: false,
  });
  (combatQueries.useJoinMutation as ReturnType<typeof vi.fn>).mockReturnValue({
    mutate: vi.fn(),
    isPending: false,
  });
  (combatQueries.useLeaveMutation as ReturnType<typeof vi.fn>).mockReturnValue({
    mutate: vi.fn(),
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

  it('shows the Audere active strip when the viewer participant carries the Audere condition', () => {
    mockEncounter({
      is_participant: true,
      participants: [
        makeParticipant({
          active_conditions: [
            { id: 7, name: 'Audere', display_priority: 10 } as unknown as {
              [key: string]: unknown;
            },
          ],
        }),
      ],
    });

    render(<CombatTurnPanel encounterId={1} characterId={10} characterSheetId={100} />, {
      wrapper: createWrapper(),
    });

    expect(screen.getByTestId('audere-active-strip')).toBeInTheDocument();
  });

  it('hides the Audere active strip when no Audere condition is active', () => {
    mockEncounter({
      is_participant: true,
      participants: [
        makeParticipant({
          active_conditions: [
            { id: 8, name: 'Bleeding Out', display_priority: 5 } as unknown as {
              [key: string]: unknown;
            },
          ],
        }),
      ],
    });

    render(<CombatTurnPanel encounterId={1} characterId={10} characterSheetId={100} />, {
      wrapper: createWrapper(),
    });

    expect(screen.queryByTestId('audere-active-strip')).not.toBeInTheDocument();
  });

  it('keys the Audere strip off the viewer own row, not the first participant', () => {
    // A non-viewer participant listed first carries Audere; the viewer's own row
    // does not. The strip reflects the VIEWER's conditions (matched by sheet id),
    // so it stays hidden — the old health-presence heuristic would have picked the
    // first row and shown it. (#918)
    mockEncounter({
      is_participant: true,
      participants: [
        makeParticipant({
          id: 2,
          character_sheet_id: 2002,
          character_name: 'Other',
          active_conditions: [
            { id: 7, name: 'Audere', display_priority: 10 } as unknown as {
              [key: string]: unknown;
            },
          ],
        }),
        makeParticipant({ id: 1, character_sheet_id: 100, character_name: 'Self' }),
      ],
    });

    render(<CombatTurnPanel encounterId={1} characterId={10} characterSheetId={100} />, {
      wrapper: createWrapper(),
    });

    expect(screen.queryByTestId('audere-active-strip')).not.toBeInTheDocument();
  });

  it('shows the Audere strip when the viewer own row carries Audere even if listed last', () => {
    mockEncounter({
      is_participant: true,
      participants: [
        makeParticipant({ id: 2, character_sheet_id: 2002, character_name: 'Other' }),
        makeParticipant({
          id: 1,
          character_sheet_id: 100,
          character_name: 'Self',
          active_conditions: [
            { id: 7, name: 'Audere', display_priority: 10 } as unknown as {
              [key: string]: unknown;
            },
          ],
        }),
      ],
    });

    render(<CombatTurnPanel encounterId={1} characterId={10} characterSheetId={100} />, {
      wrapper: createWrapper(),
    });

    expect(screen.getByTestId('audere-active-strip')).toBeInTheDocument();
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

describe('CombatTurnPanel — encounter outcome banner (#876)', () => {
  it('renders the outcome banner in place of live sections when completed', () => {
    mockEncounter({
      status: 'completed',
      outcome: 'victory',
      completed_at: '2026-06-12T00:00:00Z',
    });

    render(<CombatTurnPanel encounterId={1} characterId={10} characterSheetId={100} />, {
      wrapper: createWrapper(),
    });

    const banner = screen.getByRole('status');
    expect(banner).toHaveTextContent('Victory');
    // Live sections are replaced by the banner.
    expect(screen.queryByTestId('your-turn-stub')).not.toBeInTheDocument();
    expect(screen.queryByTestId('round-flow-section')).not.toBeInTheDocument();
  });

  it('does not render the banner while the encounter is active', () => {
    mockEncounter({ status: 'declaring' });

    render(<CombatTurnPanel encounterId={1} characterId={10} characterSheetId={100} />, {
      wrapper: createWrapper(),
    });

    expect(screen.queryByRole('status')).not.toBeInTheDocument();
    expect(screen.queryByText('Victory')).not.toBeInTheDocument();
    expect(screen.getByTestId('round-flow-section')).toBeInTheDocument();
  });

  it('falls back to Abandoned for a completed encounter with an empty outcome', () => {
    mockEncounter({
      status: 'completed',
      outcome: '',
      completed_at: '2026-06-12T00:00:00Z',
    });

    render(<CombatTurnPanel encounterId={1} characterId={10} characterSheetId={100} />, {
      wrapper: createWrapper(),
    });

    expect(screen.getByRole('status')).toHaveTextContent('Abandoned');
  });
});

describe('CombatTurnPanel — forced escape banner wiring (#983)', () => {
  it('renders the ForcedEscapeBanner in live panel state when forced_escape is true', () => {
    mockEncounter({ is_participant: true, forced_escape: true });

    render(<CombatTurnPanel encounterId={1} characterId={10} characterSheetId={100} />, {
      wrapper: createWrapper(),
    });

    const banner = screen.getByRole('alert');
    expect(banner).toHaveTextContent(/you must run/i);
    // Wired into the live panel alongside the normal sections, not in place of them.
    expect(screen.getByTestId('round-flow-section')).toBeInTheDocument();
  });

  it('does not render the ForcedEscapeBanner when forced_escape is false', () => {
    mockEncounter({ is_participant: true, forced_escape: false });

    render(<CombatTurnPanel encounterId={1} characterId={10} characterSheetId={100} />, {
      wrapper: createWrapper(),
    });

    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(screen.queryByText(/you must run/i)).not.toBeInTheDocument();
  });
});

describe('CombatTurnPanel — Open Encounter join/leave', () => {
  it('shows Join button for non-participant in open encounter between rounds', () => {
    mockEncounter({
      encounter_type: 'open_encounter',
      status: 'between_rounds',
      is_participant: false,
    });
    render(<CombatTurnPanel encounterId={1} characterId={10} characterSheetId={100} />, {
      wrapper: createWrapper(),
    });
    expect(screen.getByTestId('open-encounter-join-btn')).toBeInTheDocument();
  });

  it('shows Leave button for participant in open encounter between rounds', () => {
    mockEncounter({
      encounter_type: 'open_encounter',
      status: 'between_rounds',
      is_participant: true,
    });
    render(<CombatTurnPanel encounterId={1} characterId={10} characterSheetId={100} />, {
      wrapper: createWrapper(),
    });
    expect(screen.getByTestId('open-encounter-leave-btn')).toBeInTheDocument();
  });

  it('hides both buttons for party_combat encounters', () => {
    mockEncounter({
      encounter_type: 'party_combat',
      status: 'between_rounds',
      is_participant: false,
    });
    render(<CombatTurnPanel encounterId={1} characterId={10} characterSheetId={100} />, {
      wrapper: createWrapper(),
    });
    expect(screen.queryByTestId('open-encounter-join-btn')).not.toBeInTheDocument();
    expect(screen.queryByTestId('open-encounter-leave-btn')).not.toBeInTheDocument();
  });

  it('hides join button when encounter is not between_rounds', () => {
    mockEncounter({
      encounter_type: 'open_encounter',
      status: 'declaring',
      is_participant: false,
    });
    render(<CombatTurnPanel encounterId={1} characterId={10} characterSheetId={100} />, {
      wrapper: createWrapper(),
    });
    expect(screen.queryByTestId('open-encounter-join-btn')).not.toBeInTheDocument();
  });
});
