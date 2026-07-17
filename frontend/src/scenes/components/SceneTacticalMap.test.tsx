import { render, screen } from '@testing-library/react';
import { fireEvent } from '@testing-library/react';
import { vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import type { PlayerAction } from '../actionTypes';

// ---------------------------------------------------------------------------
// Mocks — must come before importing the component under test
// ---------------------------------------------------------------------------

vi.mock('../queries', async () => {
  const actual = await vi.importActual<typeof import('../queries')>('../queries');
  return {
    ...actual,
    fetchScene: vi.fn(),
  };
});

vi.mock('../actionQueries', () => ({
  fetchAvailableActions: vi.fn(),
  createActionRequest: vi.fn(),
}));

vi.mock('@/roster/queries', () => ({
  useMyRosterEntriesQuery: vi.fn(() => ({
    data: [
      {
        id: 1,
        name: 'TestChar',
        character_id: 42,
        profile_picture_url: null,
        primary_persona_id: null,
        active_persona_id: null,
      },
    ],
  })),
}));

vi.mock('@/store/hooks', () => ({
  useAppSelector: vi.fn((selector: (state: unknown) => unknown) =>
    selector({ game: { active: 'TestChar' }, auth: {} })
  ),
}));

vi.mock('@/combat/queries', () => ({
  useDispatchPlayerAction: vi.fn(() => ({
    mutateAsync: vi.fn(() => Promise.resolve()),
    isPending: false,
  })),
}));

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

import { fetchScene, sceneKeys } from '../queries';
import { fetchAvailableActions } from '../actionQueries';
import { useDispatchPlayerAction } from '@/combat/queries';
import { toast } from 'sonner';
import { SceneTacticalMap } from './SceneTacticalMap';

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
// invalidateQueries — #2423: dispatches must refresh the scene's position
// data on a genuine success and must not on a success:false rejection.
function createWrapperWithClient() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return { Wrapper, queryClient };
}

const MOCK_SCENE = {
  id: 10,
  name: 'Test Scene',
  description: '',
  date_started: '',
  location: null,
  participants: [
    { id: 1, name: 'Alice' },
    { id: 2, name: 'Bob' },
  ],
  is_active: true,
  is_owner: false,
  positions: [
    { id: 101, name: 'North Wall' },
    { id: 102, name: 'Center' },
  ],
  position_adjacency: [
    { position_id: 101, adjacent_position_ids: [102] },
    { position_id: 102, adjacent_position_ids: [101] },
  ],
  persona_positions: [
    { persona_id: 1, position: { id: 101, name: 'North Wall' } },
    { persona_id: 2, position: null },
  ],
  personas: [
    { id: 1, name: 'Alice Persona' },
    { id: 2, name: 'Bob Persona' },
  ],
  position_nodes: [
    {
      id: 101,
      name: 'North Wall',
      kind: 'feature',
      elevation_anchor_id: null,
      layout_x: null,
      layout_y: null,
    },
    {
      id: 102,
      name: 'Center',
      kind: 'primary',
      elevation_anchor_id: null,
      layout_x: null,
      layout_y: null,
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
};

function makeMoveAction(
  registryKey: 'move_to_position' | 'take_position',
  positionId: number,
  displayName: string
): PlayerAction {
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
      registry_key: registryKey,
      position_id: positionId,
    },
    target_spec: null,
    enhancements: [],
    strain: null,
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('SceneTacticalMap', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchScene).mockResolvedValue(MOCK_SCENE);
    vi.mocked(fetchAvailableActions).mockResolvedValue({
      count: 0,
      next: null,
      previous: null,
      results: [],
    });
    vi.mocked(useDispatchPlayerAction).mockReturnValue({
      mutateAsync: vi.fn(() => Promise.resolve()),
      isPending: false,
    } as unknown as ReturnType<typeof useDispatchPlayerAction>);
  });

  it('renders nothing when the scene has no positions', async () => {
    vi.mocked(fetchScene).mockResolvedValue({
      ...MOCK_SCENE,
      position_nodes: [],
      position_edges: [],
    });

    const { container } = render(<SceneTacticalMap sceneId="10" />, {
      wrapper: createWrapper(),
    });

    await vi.waitFor(() => {
      expect(container.querySelector('[data-testid="scene-tactical-map"]')).toBeNull();
    });
    expect(screen.queryByTestId('tactical-map')).toBeNull();
  });

  it('renders the tactical map when the scene has positions', async () => {
    render(<SceneTacticalMap sceneId="10" />, { wrapper: createWrapper() });

    expect(await screen.findByTestId('tactical-map')).toBeInTheDocument();
    expect(screen.getByTestId('tactical-map-node-101')).toBeInTheDocument();
    expect(screen.getByTestId('tactical-map-node-102')).toBeInTheDocument();
  });

  it('passes move_to_position/take_position PlayerActions through as moveActions', async () => {
    const mockMutateAsync = vi.fn(() => Promise.resolve());
    vi.mocked(useDispatchPlayerAction).mockReturnValue({
      mutateAsync: mockMutateAsync,
      isPending: false,
    } as unknown as ReturnType<typeof useDispatchPlayerAction>);

    const moveAction = makeMoveAction('move_to_position', 102, 'Move to Center');
    const takeAction = makeMoveAction('take_position', 101, 'Take North Wall');
    vi.mocked(fetchAvailableActions).mockResolvedValue({
      count: 2,
      next: null,
      previous: null,
      results: [moveAction, takeAction],
    });

    render(<SceneTacticalMap sceneId="10" />, { wrapper: createWrapper() });

    const centerNode = await screen.findByTestId('tactical-map-node-102');
    fireEvent.click(centerNode);
    expect(mockMutateAsync).toHaveBeenCalledWith({ ref: moveAction.ref, kwargs: {} });

    const northWallNode = screen.getByTestId('tactical-map-node-101');
    fireEvent.click(northWallNode);
    expect(mockMutateAsync).toHaveBeenCalledWith({ ref: takeAction.ref, kwargs: {} });
  });

  // ---------------------------------------------------------------------------
  // Dispatch contract (#2423) — the endpoint resolves HTTP 200 + success:false
  // for a business-rule rejection, so a resolved promise is not itself proof
  // of success.
  // ---------------------------------------------------------------------------

  it('toasts and skips scene invalidation on a success:false move', async () => {
    const mockMutateAsync = vi.fn(() =>
      Promise.resolve({ backend: 'registry', deferred: false, success: false, message: 'Blocked.' })
    );
    vi.mocked(useDispatchPlayerAction).mockReturnValue({
      mutateAsync: mockMutateAsync,
      isPending: false,
    } as unknown as ReturnType<typeof useDispatchPlayerAction>);

    const moveAction = makeMoveAction('move_to_position', 102, 'Move to Center');
    vi.mocked(fetchAvailableActions).mockResolvedValue({
      count: 1,
      next: null,
      previous: null,
      results: [moveAction],
    });

    const { Wrapper, queryClient } = createWrapperWithClient();
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries');

    render(<SceneTacticalMap sceneId="10" />, { wrapper: Wrapper });

    const centerNode = await screen.findByTestId('tactical-map-node-102');
    fireEvent.click(centerNode);

    await vi.waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('Blocked.');
    });
    expect(invalidateSpy).not.toHaveBeenCalledWith({ queryKey: sceneKeys.detail('10') });
  });

  it('invalidates the scene query when the move dispatch resolves success:true', async () => {
    const mockMutateAsync = vi.fn(() =>
      Promise.resolve({ backend: 'registry', deferred: false, success: true })
    );
    vi.mocked(useDispatchPlayerAction).mockReturnValue({
      mutateAsync: mockMutateAsync,
      isPending: false,
    } as unknown as ReturnType<typeof useDispatchPlayerAction>);

    const moveAction = makeMoveAction('move_to_position', 102, 'Move to Center');
    vi.mocked(fetchAvailableActions).mockResolvedValue({
      count: 1,
      next: null,
      previous: null,
      results: [moveAction],
    });

    const { Wrapper, queryClient } = createWrapperWithClient();
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries');

    render(<SceneTacticalMap sceneId="10" />, { wrapper: Wrapper });

    const centerNode = await screen.findByTestId('tactical-map-node-102');
    fireEvent.click(centerNode);

    await vi.waitFor(() => {
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: sceneKeys.detail('10') });
    });
    expect(toast.error).not.toHaveBeenCalled();
  });
});
