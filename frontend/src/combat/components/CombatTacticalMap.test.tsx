import { render, screen, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import type { ReactNode } from 'react';

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

vi.mock('@/scenes/actionQueries', () => ({
  fetchAvailableActions: vi.fn(),
}));

import { useCombatEncounter, useDispatchPlayerAction } from '../queries';
import { fetchAvailableActions } from '@/scenes/actionQueries';
import { CombatTacticalMap } from './CombatTacticalMap';
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
});
