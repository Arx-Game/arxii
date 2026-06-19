import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
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

import { fetchScene } from '../queries';
import { fetchAvailableActions } from '../actionQueries';
import { useDispatchPlayerAction } from '@/combat/queries';
import { RoomPositionsPanel } from './RoomPositionsPanel';

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
};

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

function makeSetTheStageAction(): PlayerAction {
  return {
    backend: 'registry',
    display_name: 'Set the Stage',
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
      registry_key: 'set_the_stage',
    },
    target_spec: null,
    enhancements: [],
    strain: null,
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('RoomPositionsPanel', () => {
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

  it('renders positions from mocked scene-detail payload', async () => {
    render(<RoomPositionsPanel sceneId="10" />, { wrapper: createWrapper() });

    expect(await screen.findByText('North Wall')).toBeInTheDocument();
    expect(screen.getByText('Center')).toBeInTheDocument();
  });

  it('renders nothing when the scene has no positions', async () => {
    vi.mocked(fetchScene).mockResolvedValue({ ...MOCK_SCENE, positions: [] });

    const { container } = render(<RoomPositionsPanel sceneId="10" />, {
      wrapper: createWrapper(),
    });

    // Wait for scene to load and assert no position content
    // Give react-query a tick to resolve
    await vi.waitFor(() => {
      expect(container.querySelector('[data-testid="room-positions-panel"]')).toBeNull();
    });
  });

  it('shows persona placement for personas that have a position', async () => {
    render(<RoomPositionsPanel sceneId="10" />, { wrapper: createWrapper() });

    await screen.findByText('North Wall');
    // Persona 1 is at North Wall; their name should appear
    expect(screen.getByText('Alice Persona')).toBeInTheDocument();
  });

  it('renders a move button per move_to_position action', async () => {
    vi.mocked(fetchAvailableActions).mockResolvedValue({
      count: 2,
      next: null,
      previous: null,
      results: [makeMoveAction(101, 'Move to North Wall'), makeMoveAction(102, 'Move to Center')],
    });

    render(<RoomPositionsPanel sceneId="10" />, { wrapper: createWrapper() });

    expect(await screen.findByTestId('move-btn-101')).toBeInTheDocument();
    expect(screen.getByTestId('move-btn-102')).toBeInTheDocument();
  });

  it('renders the set-the-stage button when a set_the_stage action is present', async () => {
    vi.mocked(fetchAvailableActions).mockResolvedValue({
      count: 1,
      next: null,
      previous: null,
      results: [makeSetTheStageAction()],
    });

    render(<RoomPositionsPanel sceneId="10" />, { wrapper: createWrapper() });

    expect(await screen.findByTestId('set-the-stage-btn')).toBeInTheDocument();
    expect(screen.getByText('Set the Stage')).toBeInTheDocument();
  });

  it('dispatches the move action via useDispatchPlayerAction when a move button is clicked', async () => {
    const mockMutateAsync = vi.fn(() => Promise.resolve());
    vi.mocked(useDispatchPlayerAction).mockReturnValue({
      mutateAsync: mockMutateAsync,
      isPending: false,
    } as unknown as ReturnType<typeof useDispatchPlayerAction>);

    const moveAction = makeMoveAction(101, 'Move to North Wall');
    vi.mocked(fetchAvailableActions).mockResolvedValue({
      count: 1,
      next: null,
      previous: null,
      results: [moveAction],
    });

    const user = userEvent.setup();
    render(<RoomPositionsPanel sceneId="10" />, { wrapper: createWrapper() });

    const moveBtn = await screen.findByTestId('move-btn-101');
    await user.click(moveBtn);

    expect(mockMutateAsync).toHaveBeenCalledWith({ ref: moveAction.ref, kwargs: {} });
  });

  it('dispatches set_the_stage action when its button is clicked', async () => {
    const mockMutateAsync = vi.fn(() => Promise.resolve());
    vi.mocked(useDispatchPlayerAction).mockReturnValue({
      mutateAsync: mockMutateAsync,
      isPending: false,
    } as unknown as ReturnType<typeof useDispatchPlayerAction>);

    const stageAction = makeSetTheStageAction();
    vi.mocked(fetchAvailableActions).mockResolvedValue({
      count: 1,
      next: null,
      previous: null,
      results: [stageAction],
    });

    const user = userEvent.setup();
    render(<RoomPositionsPanel sceneId="10" />, { wrapper: createWrapper() });

    const stageBtn = await screen.findByTestId('set-the-stage-btn');
    await user.click(stageBtn);

    expect(mockMutateAsync).toHaveBeenCalledWith({ ref: stageAction.ref, kwargs: {} });
  });
});
