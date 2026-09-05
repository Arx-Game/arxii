import { render, screen, within, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import type { ReactNode } from 'react';
import type { PlayerAction } from '@/scenes/actionTypes';

// ---------------------------------------------------------------------------
// Mocks — must come before importing the component under test
// ---------------------------------------------------------------------------

vi.mock('../queries', async () => {
  const actual = await vi.importActual<typeof import('../queries')>('../queries');
  return {
    ...actual,
    useCombatEncounter: vi.fn(),
    useDispatchPlayerAction: vi.fn(),
  };
});

vi.mock('@/scenes/actionQueries', async () => {
  const { useQuery } = await import('@tanstack/react-query');
  const fetchAvailableActions = vi.fn();
  return {
    fetchAvailableActions,
    useAvailableActionsQuery: (
      characterId: number | null,
      options: { enabled?: boolean; staleTime?: number; refetchInterval?: number } = {}
    ) =>
      useQuery({
        queryKey: ['available-actions', characterId ?? 0],
        queryFn: () => fetchAvailableActions(characterId),
        enabled: (options.enabled ?? true) && characterId !== null && characterId > 0,
        staleTime: options.staleTime ?? 10_000,
        refetchInterval: options.refetchInterval,
      }),
  };
});

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

import { combatKeys, useCombatEncounter, useDispatchPlayerAction } from '../queries';
import { fetchAvailableActions } from '@/scenes/actionQueries';
import { toast } from 'sonner';
import { CombatTacticalMap } from './CombatTacticalMap';
import type { EncounterDetail } from '../types';
import { makeGMPlaceAction } from '@/test/utils/playerActionFixtures';

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

// Exposes the QueryClient (unlike createWrapper above) so a test can spy on
// invalidateQueries — #2423: the move dispatch must refresh the encounter on
// a genuine success and must not on a success:false rejection.
function createWrapperWithClient() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return { Wrapper, queryClient };
}

function makeMoveAction(positionId: number, displayName: string): PlayerAction {
  return {
    backend: 'registry',
    display_name: displayName,
    description: '',
    difficulty: null,
    prerequisite_met: true,
    prerequisite_reasons: [],
    check_type: { id: 1, name: 'Standard' },
    action_template: null,
    ref: {
      backend: 'registry',
      challenge_instance_id: null,
      approach_id: null,
      technique_id: null,
      registry_key: 'move_to_position',
      position_id: positionId,
    },
    target_spec: null,
    enhancements: [],
    strain: null,
  };
}

const BASE_ENCOUNTER = {
  id: 7,
  scene: 42,
  round_number: 1,
  is_participant: true,
  is_gm: false,
  current_round_actions: [],
  surge_beats: [],
  clashes: [],
  engagement_locks: [],
  resolution_order: [],
  forced_escape: false,
  position_adjacency: [],
  is_lethal: false,
  duel_winner: null,
  created_at: '2026-05-24T00:00:00Z',
  outcome: '',
  completed_at: null,
  escalation_curve_name: null,
  escalation_start_round: null,
  escalation_tick_narration: null,
} as unknown as EncounterDetail;

function makeEncounter(overrides: Partial<EncounterDetail>): EncounterDetail {
  return { ...BASE_ENCOUNTER, ...overrides } as EncounterDetail;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('CombatTacticalMap', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useDispatchPlayerAction).mockReturnValue({
      mutateAsync: vi.fn(() => Promise.resolve()),
      isPending: false,
    } as unknown as ReturnType<typeof useDispatchPlayerAction>);
    vi.mocked(fetchAvailableActions).mockResolvedValue({
      count: 0,
      next: null,
      previous: null,
      results: [],
    });
  });

  it('renders the tactical map with the encounter position graph', () => {
    vi.mocked(useCombatEncounter).mockReturnValue({
      data: makeEncounter({
        participants: [],
        opponents: [],
        position_nodes: [
          {
            id: 101,
            name: 'North Wall',
            kind: 'feature',
            elevation_anchor_id: null,
            layout_x: null,
            layout_y: null,
            rampart_element: null,
            rampart_integrity: null,
            rampart_max_integrity: null,
            rampart_crack_state: null,
          },
          {
            id: 102,
            name: 'Center',
            kind: 'primary',
            elevation_anchor_id: null,
            layout_x: null,
            layout_y: null,
            rampart_element: null,
            rampart_integrity: null,
            rampart_max_integrity: null,
            rampart_crack_state: null,
          },
        ],
        position_edges: [
          {
            position_a_id: 101,
            position_b_id: 102,
            is_passable: true,
            blocks_flight: false,
            gating_challenge_name: null,
          },
        ],
      }),
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof useCombatEncounter>);

    render(<CombatTacticalMap encounterId={7} characterId={10} />, { wrapper: createWrapper() });

    expect(screen.getByTestId('tactical-map')).toBeInTheDocument();
    expect(screen.getByTestId('tactical-map-node-101')).toBeInTheDocument();
    expect(screen.getByTestId('tactical-map-node-102')).toBeInTheDocument();
  });

  it('builds occupants from participant and opponent current_position', () => {
    vi.mocked(useCombatEncounter).mockReturnValue({
      data: makeEncounter({
        participants: [
          {
            id: 1,
            character_sheet_id: 10,
            character_name: 'Aerande',
            status: 'active',
            health: 10,
            max_health: 10,
            character_status: null,
            available_strain: null,
            fatigue: null,
            active_conditions: [],
            thumbnail_url: 'https://example.com/aerande.png',
            thumbnail_media_url: null,
            escalation_level: null,
            intensity_modifier: null,
            control_modifier: null,
            current_position: { id: 101, name: 'North Wall' },
            aftermath: null,
          },
        ],
        opponents: [
          {
            id: 2,
            objectdb_id: null,
            name: 'Rival Knight',
            tier: 'mook',
            health: 10,
            max_health: 10,
            soak_value: null,
            probing_threshold: null,
            phase_count: null,
            damage_multiplier: null,
            break_bar_current: null,
            break_bar_threshold: null,
            vulnerability_rounds_remaining: null,
            morale: null,
            max_morale: null,
            morale_state: null,
            is_enraged: false,
            is_wall_broken: false,
            current_phase: 0,
            status: 'active',
            active_conditions: [],
            thumbnail_url: 'https://example.com/rival.png',
            thumbnail_media_url: null,
            current_position: { id: 101, name: 'North Wall' },
            mirrors_participant_id: null,
          },
        ],
        position_nodes: [
          {
            id: 101,
            name: 'North Wall',
            kind: 'feature',
            elevation_anchor_id: null,
            layout_x: null,
            layout_y: null,
            rampart_element: null,
            rampart_integrity: null,
            rampart_max_integrity: null,
            rampart_crack_state: null,
          },
        ],
        position_edges: [],
      }),
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof useCombatEncounter>);

    render(<CombatTacticalMap encounterId={7} characterId={10} />, { wrapper: createWrapper() });

    const node = screen.getByTestId('tactical-map-node-101');
    expect(within(node).getByAltText('Aerande')).toBeInTheDocument();
    expect(within(node).getByAltText('Rival Knight')).toBeInTheDocument();
  });

  // ---------------------------------------------------------------------------
  // Tactical overlays (#3555): the encounter's engagement locks and declared
  // cover maneuver resolve into occupant marks and a lock link on the map.
  // ---------------------------------------------------------------------------

  const overlayParticipants = [
    {
      id: 1,
      character_sheet_id: 10,
      character_name: 'Aerande',
      status: 'active',
      health: 10,
      max_health: 10,
      character_status: null,
      available_strain: null,
      fatigue: null,
      active_conditions: [],
      thumbnail_url: null,
      thumbnail_media_url: null,
      escalation_level: null,
      intensity_modifier: null,
      control_modifier: null,
      current_position: { id: 101, name: 'North Wall' },
      aftermath: null,
    },
    {
      id: 3,
      character_sheet_id: 30,
      character_name: 'Sir Alaric',
      status: 'active',
      health: 10,
      max_health: 10,
      character_status: null,
      available_strain: null,
      fatigue: null,
      active_conditions: [],
      thumbnail_url: null,
      thumbnail_media_url: null,
      escalation_level: null,
      intensity_modifier: null,
      control_modifier: null,
      current_position: { id: 101, name: 'North Wall' },
      aftermath: null,
    },
  ];
  const overlayOpponents = [
    {
      id: 2,
      objectdb_id: null,
      name: 'Rival Knight',
      tier: 'mook',
      health: 10,
      max_health: 10,
      soak_value: null,
      probing_threshold: null,
      phase_count: null,
      damage_multiplier: null,
      break_bar_current: null,
      break_bar_threshold: null,
      vulnerability_rounds_remaining: null,
      morale: null,
      max_morale: null,
      morale_state: null,
      is_enraged: false,
      is_wall_broken: false,
      current_phase: 0,
      status: 'active',
      active_conditions: [],
      thumbnail_url: null,
      thumbnail_media_url: null,
      current_position: { id: 102, name: 'Center' },
      mirrors_participant_id: null,
    },
  ];
  const overlayNodes = [101, 102].map((id) => ({
    id,
    name: id === 101 ? 'North Wall' : 'Center',
    kind: 'feature',
    elevation_anchor_id: null,
    layout_x: null,
    layout_y: null,
    rampart_element: null,
    rampart_integrity: null,
    rampart_max_integrity: null,
    rampart_crack_state: null,
  }));
  const overlayEdges = [
    {
      position_a_id: 101,
      position_b_id: 102,
      is_passable: true,
      blocks_flight: false,
      gating_challenge_name: null,
    },
  ];

  it('marks both sides of an engagement lock and links their positions', () => {
    vi.mocked(useCombatEncounter).mockReturnValue({
      data: makeEncounter({
        participants: overlayParticipants,
        opponents: overlayOpponents,
        position_nodes: overlayNodes,
        position_edges: overlayEdges,
        engagement_locks: [
          {
            id: 5,
            opponent_id: 2,
            participant_id: 1,
            status: 'active',
            initiated_by: 'pc_challenge',
            started_round: 1,
          },
        ],
      } as Partial<EncounterDetail>),
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof useCombatEncounter>);

    render(<CombatTacticalMap encounterId={7} characterId={10} />, { wrapper: createWrapper() });

    const wall = screen.getByTestId('tactical-map-node-101');
    expect(within(wall).getByTestId('occupant-mark-locked')).toHaveAttribute(
      'title',
      'Aerande: locked with Rival Knight'
    );
    const center = screen.getByTestId('tactical-map-node-102');
    expect(within(center).getByTestId('occupant-mark-locked')).toHaveAttribute(
      'title',
      'Rival Knight: locked with Aerande'
    );
    expect(screen.getByTestId('rf__edge-link-lock-5')).toBeInTheDocument();
  });

  it('marks the coverer and the covered ally from a declared cover maneuver', () => {
    vi.mocked(useCombatEncounter).mockReturnValue({
      data: makeEncounter({
        participants: overlayParticipants,
        opponents: overlayOpponents,
        position_nodes: overlayNodes,
        position_edges: overlayEdges,
        current_round_actions: [
          {
            participant: 3,
            participant_name: 'Sir Alaric',
            is_ready: true,
            maneuver: 'cover',
            focused_ally_target: 1,
            combo_upgrade: null,
          },
        ],
      } as Partial<EncounterDetail>),
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof useCombatEncounter>);

    render(<CombatTacticalMap encounterId={7} characterId={10} />, { wrapper: createWrapper() });

    const wall = screen.getByTestId('tactical-map-node-101');
    expect(within(wall).getByTestId('occupant-mark-covering')).toHaveAttribute(
      'title',
      'Sir Alaric: covering Aerande'
    );
    expect(within(wall).getByTestId('occupant-mark-covered')).toHaveAttribute(
      'title',
      'Aerande: covered by Sir Alaric'
    );
    expect(screen.queryByTestId(/^rf__edge-link-/)).not.toBeInTheDocument();
  });

  // ---------------------------------------------------------------------------
  // Dispatch contract (#2423) — the endpoint resolves HTTP 200 + success:false
  // for a business-rule rejection, so a resolved promise is not itself proof
  // of success.
  // ---------------------------------------------------------------------------

  function renderWithMoveAction(mockMutateAsync: ReturnType<typeof vi.fn>) {
    vi.mocked(useDispatchPlayerAction).mockReturnValue({
      mutateAsync: mockMutateAsync,
      isPending: false,
    } as unknown as ReturnType<typeof useDispatchPlayerAction>);

    const moveAction = makeMoveAction(102, 'Move to Center');
    vi.mocked(fetchAvailableActions).mockResolvedValue({
      count: 1,
      next: null,
      previous: null,
      results: [moveAction],
    });

    vi.mocked(useCombatEncounter).mockReturnValue({
      data: makeEncounter({
        participants: [],
        opponents: [],
        position_nodes: [
          {
            id: 101,
            name: 'North Wall',
            kind: 'feature',
            elevation_anchor_id: null,
            layout_x: null,
            layout_y: null,
            rampart_element: null,
            rampart_integrity: null,
            rampart_max_integrity: null,
            rampart_crack_state: null,
          },
          {
            id: 102,
            name: 'Center',
            kind: 'primary',
            elevation_anchor_id: null,
            layout_x: null,
            layout_y: null,
            rampart_element: null,
            rampart_integrity: null,
            rampart_max_integrity: null,
            rampart_crack_state: null,
          },
        ],
        position_edges: [
          {
            position_a_id: 101,
            position_b_id: 102,
            is_passable: true,
            blocks_flight: false,
            gating_challenge_name: null,
          },
        ],
      }),
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof useCombatEncounter>);

    const { Wrapper, queryClient } = createWrapperWithClient();
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries');

    render(<CombatTacticalMap encounterId={7} characterId={10} />, { wrapper: Wrapper });

    return { invalidateSpy };
  }

  it('toasts and skips encounter invalidation on a success:false move', async () => {
    const mockMutateAsync = vi.fn(() =>
      Promise.resolve({ backend: 'registry', deferred: false, success: false, message: 'Blocked.' })
    );
    const { invalidateSpy } = renderWithMoveAction(mockMutateAsync);

    const centerNode = await screen.findByTestId('tactical-map-node-102');
    fireEvent.click(centerNode);

    await vi.waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('Blocked.');
    });
    expect(invalidateSpy).not.toHaveBeenCalledWith({ queryKey: combatKeys.encounter(7) });
  });

  it('invalidates the encounter query on a success:true move', async () => {
    const mockMutateAsync = vi.fn(() =>
      Promise.resolve({ backend: 'registry', deferred: false, success: true })
    );
    const { invalidateSpy } = renderWithMoveAction(mockMutateAsync);

    const centerNode = await screen.findByTestId('tactical-map-node-102');
    fireEvent.click(centerNode);

    await vi.waitFor(() => {
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: combatKeys.encounter(7) });
    });
    expect(toast.error).not.toHaveBeenCalled();
  });

  // ---------------------------------------------------------------------------
  // GM-place target picker (#3385)
  // ---------------------------------------------------------------------------

  it('dispatches gm_place_in_position with the selected target on node click', async () => {
    const user = userEvent.setup({ pointerEventsCheck: 0 });
    const mockMutateAsync = vi.fn(() =>
      Promise.resolve({ backend: 'registry', deferred: false, success: true })
    );
    vi.mocked(useDispatchPlayerAction).mockReturnValue({
      mutateAsync: mockMutateAsync,
      isPending: false,
    } as unknown as ReturnType<typeof useDispatchPlayerAction>);

    const gmPlaceAction = makeGMPlaceAction(102);
    vi.mocked(fetchAvailableActions).mockResolvedValue({
      count: 1,
      next: null,
      previous: null,
      results: [gmPlaceAction],
    });

    vi.mocked(useCombatEncounter).mockReturnValue({
      data: makeEncounter({
        participants: [
          {
            id: 1,
            character_sheet_id: 10,
            character_name: 'Aerande',
            status: 'active',
            health: 10,
            max_health: 10,
            character_status: null,
            available_strain: null,
            fatigue: null,
            active_conditions: [],
            thumbnail_url: null,
            thumbnail_media_url: null,
            escalation_level: null,
            intensity_modifier: null,
            control_modifier: null,
            current_position: null,
            aftermath: null,
          },
        ],
        opponents: [],
        position_nodes: [
          {
            id: 101,
            name: 'North Wall',
            kind: 'feature',
            elevation_anchor_id: null,
            layout_x: null,
            layout_y: null,
            rampart_element: null,
            rampart_integrity: null,
            rampart_max_integrity: null,
            rampart_crack_state: null,
          },
          {
            id: 102,
            name: 'Center',
            kind: 'primary',
            elevation_anchor_id: null,
            layout_x: null,
            layout_y: null,
            rampart_element: null,
            rampart_integrity: null,
            rampart_max_integrity: null,
            rampart_crack_state: null,
          },
        ],
        position_edges: [],
      }),
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof useCombatEncounter>);

    render(<CombatTacticalMap encounterId={7} characterId={10} />, { wrapper: createWrapper() });

    await user.click(await screen.findByTestId('gm-place-toggle'));
    await user.click(screen.getByTestId('gm-place-target-select'));
    await user.click(await screen.findByRole('option', { name: 'Aerande' }));

    const centerNode = screen.getByTestId('tactical-map-node-102');
    fireEvent.click(centerNode);

    await vi.waitFor(() => {
      expect(mockMutateAsync).toHaveBeenCalledWith({
        ref: gmPlaceAction.ref,
        kwargs: { target_object_id: 10 },
      });
    });
  });

  it('does not show the Place toggle when no gm_place_in_position action is available', async () => {
    vi.mocked(useCombatEncounter).mockReturnValue({
      data: makeEncounter({
        participants: [],
        opponents: [],
        position_nodes: [],
        position_edges: [],
      }),
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof useCombatEncounter>);

    render(<CombatTacticalMap encounterId={7} characterId={10} />, { wrapper: createWrapper() });

    expect(screen.queryByTestId('gm-place-toggle')).not.toBeInTheDocument();
  });
});
