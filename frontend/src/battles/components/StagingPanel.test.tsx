import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';

import type { PlayerAction } from '@/scenes/actionTypes';
import type { BattleDetail, BattleMapBlueprint, BattleUnitTemplate } from '../types';

// ---------------------------------------------------------------------------
// Mocks — must come before importing the component under test
// ---------------------------------------------------------------------------

const mockNavigate = vi.fn();

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

vi.mock('@/scenes/queries', async () => {
  const actual = await vi.importActual<typeof import('@/scenes/queries')>('@/scenes/queries');
  return {
    ...actual,
    fetchScene: vi.fn(),
  };
});

vi.mock('@/scenes/actionQueries', () => ({
  fetchAvailableActions: vi.fn(),
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

vi.mock('../queries', async () => {
  const actual = await vi.importActual<typeof import('../queries')>('../queries');
  return {
    ...actual,
    useBattleMapBlueprintsQuery: vi.fn(),
    useBattleUnitTemplatesQuery: vi.fn(),
  };
});

import { fetchScene } from '@/scenes/queries';
import { fetchAvailableActions } from '@/scenes/actionQueries';
import { useDispatchPlayerAction } from '@/combat/queries';
import { useBattleMapBlueprintsQuery, useBattleUnitTemplatesQuery } from '../queries';
import { StagingPanel } from './StagingPanel';

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
  participants: [],
  is_active: true,
  is_owner: false,
  viewer_can_gm: true,
  positions: [],
  position_adjacency: [],
  persona_positions: [],
  active_round: null,
  personas: [
    { id: 1, name: 'Alice Persona', character_sheet: 501 },
    { id: 2, name: 'Bob Persona', character_sheet: 502 },
  ],
};

const MOCK_BLUEPRINTS: BattleMapBlueprint[] = [
  { id: 1, name: 'Siege of the Wall', description: '', is_active: true, places: [] },
];

const MOCK_TEMPLATES: BattleUnitTemplate[] = [
  {
    id: 1,
    name: 'Spearmen',
    descriptor: '',
    quality: 'trained',
    strength: 100,
    morale: 50,
    individual_count: null,
    is_active: true,
    properties: [],
    capability_values: [],
  },
];

const MOCK_BATTLE_DETAIL: BattleDetail = {
  id: 7,
  name: 'Battle for Test Scene',
  outcome: 'unresolved',
  risk_level: 'low',
  is_paused: false,
  round: null,
  sides: [
    {
      id: 100,
      role: 'attacker',
      victory_points: 0,
      victory_threshold: 10,
      covenant_id: null,
      covenant_name: null,
    },
    {
      id: 101,
      role: 'defender',
      victory_points: 0,
      victory_threshold: 10,
      covenant_id: null,
      covenant_name: null,
    },
  ],
  places: [],
  units: [],
  participants: [],
  concluded_at: null,
  created_at: '2026-07-10T00:00:00Z',
  campaign_story_id: null,
  scene_id: 1,
  deeds: [],
};

function makeStagingAction(registryKey: string, displayName: string): PlayerAction {
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
    },
    target_spec: null,
    enhancements: [],
    strain: null,
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('StagingPanel', () => {
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
    vi.mocked(useBattleMapBlueprintsQuery).mockReturnValue({
      data: { count: 1, next: null, previous: null, results: MOCK_BLUEPRINTS },
    } as unknown as ReturnType<typeof useBattleMapBlueprintsQuery>);
    vi.mocked(useBattleUnitTemplatesQuery).mockReturnValue({
      data: { count: 1, next: null, previous: null, results: MOCK_TEMPLATES },
    } as unknown as ReturnType<typeof useBattleUnitTemplatesQuery>);
  });

  it('renders nothing when no staging actions are available', async () => {
    const { container } = render(<StagingPanel sceneId={10} battle={null} detail={null} />, {
      wrapper: createWrapper(),
    });

    await vi.waitFor(() => {
      expect(container).toBeEmptyDOMElement();
    });
  });

  it('renders the create-battle form in the empty-battle state when create_battle is available', async () => {
    vi.mocked(fetchAvailableActions).mockResolvedValue({
      count: 1,
      next: null,
      previous: null,
      results: [makeStagingAction('create_battle', 'Create Battle')],
    });

    render(<StagingPanel sceneId={10} battle={null} detail={null} />, {
      wrapper: createWrapper(),
    });

    expect(await screen.findByTestId('staging-panel-create')).toBeInTheDocument();
    expect(screen.getByText('Siege of the Wall')).toBeInTheDocument();
  });

  it('dispatches create_battle with name/risk_level/blueprint_id kwargs on submit', async () => {
    const mockMutateAsync = vi.fn(() => Promise.resolve());
    vi.mocked(useDispatchPlayerAction).mockReturnValue({
      mutateAsync: mockMutateAsync,
      isPending: false,
    } as unknown as ReturnType<typeof useDispatchPlayerAction>);

    const createAction = makeStagingAction('create_battle', 'Create Battle');
    vi.mocked(fetchAvailableActions).mockResolvedValue({
      count: 1,
      next: null,
      previous: null,
      results: [createAction],
    });

    const user = userEvent.setup();
    render(<StagingPanel sceneId={10} battle={null} detail={null} />, {
      wrapper: createWrapper(),
    });

    await screen.findByTestId('staging-panel-create');
    await user.type(screen.getByTestId('staging-create-name'), 'The Bridge Skirmish');
    await user.selectOptions(screen.getByTestId('staging-create-blueprint'), '1');
    await user.click(screen.getByTestId('staging-create-submit'));

    expect(mockMutateAsync).toHaveBeenCalledWith({
      ref: createAction.ref,
      kwargs: { name: 'The Bridge Skirmish', risk_level: 'low', blueprint_id: 1 },
    });
  });

  it('renders staging forms once a battle exists, gated per action', async () => {
    vi.mocked(fetchAvailableActions).mockResolvedValue({
      count: 3,
      next: null,
      previous: null,
      results: [
        makeStagingAction('stage_battle_map', 'Stage Battle Map'),
        makeStagingAction('spawn_battle_units', 'Spawn Battle Units'),
        makeStagingAction('enlist_battle_participant', 'Enlist Battle Participant'),
      ],
    });

    render(<StagingPanel sceneId={10} battle={{ id: 7 }} detail={MOCK_BATTLE_DETAIL} />, {
      wrapper: createWrapper(),
    });

    expect(await screen.findByTestId('staging-apply-blueprint')).toBeInTheDocument();
    expect(screen.getByTestId('staging-spawn-units')).toBeInTheDocument();
    expect(screen.getByTestId('staging-enlist-participant')).toBeInTheDocument();
    expect(screen.getByText('Alice Persona')).toBeInTheDocument();
  });

  it('requires a replace confirm before re-applying a blueprint onto an already-staged battle', async () => {
    const mockMutateAsync = vi.fn(() => Promise.resolve());
    vi.mocked(useDispatchPlayerAction).mockReturnValue({
      mutateAsync: mockMutateAsync,
      isPending: false,
    } as unknown as ReturnType<typeof useDispatchPlayerAction>);

    const stageAction = makeStagingAction('stage_battle_map', 'Stage Battle Map');
    vi.mocked(fetchAvailableActions).mockResolvedValue({
      count: 1,
      next: null,
      previous: null,
      results: [stageAction],
    });

    const stagedDetail: BattleDetail = {
      ...MOCK_BATTLE_DETAIL,
      places: [
        {
          id: 900,
          name: 'North Wall',
          terrain_type: 'open',
          movement_cost: 1,
          x: 0,
          y: 0,
          footprint_radius: 1,
          controlled_by_id: null,
          encounter_scene_id: null,
          vehicle: null,
          fortifications: [],
        },
      ],
    };

    const user = userEvent.setup();
    render(<StagingPanel sceneId={10} battle={{ id: 7 }} detail={stagedDetail} />, {
      wrapper: createWrapper(),
    });

    await screen.findByTestId('staging-apply-blueprint');
    await user.selectOptions(screen.getByTestId('staging-apply-blueprint-select'), '1');
    await user.click(screen.getByTestId('staging-apply-blueprint-submit'));

    // First click only asks for confirmation — no dispatch yet.
    expect(mockMutateAsync).not.toHaveBeenCalled();
    expect(await screen.findByTestId('staging-confirm-replace')).toBeInTheDocument();

    await user.click(screen.getByTestId('staging-confirm-replace'));

    expect(mockMutateAsync).toHaveBeenCalledWith({
      ref: stageAction.ref,
      kwargs: { battle_id: 7, blueprint_id: 1, replace: true },
    });
  });

  it('shows the server message on a successful create_battle dispatch', async () => {
    const mockMutateAsync = vi.fn(() =>
      Promise.resolve({ backend: 'registry', deferred: false, message: 'Battle stood up.' })
    );
    vi.mocked(useDispatchPlayerAction).mockReturnValue({
      mutateAsync: mockMutateAsync,
      isPending: false,
    } as unknown as ReturnType<typeof useDispatchPlayerAction>);

    const createAction = makeStagingAction('create_battle', 'Create Battle');
    vi.mocked(fetchAvailableActions).mockResolvedValue({
      count: 1,
      next: null,
      previous: null,
      results: [createAction],
    });

    const user = userEvent.setup();
    render(<StagingPanel sceneId={10} battle={null} detail={null} />, {
      wrapper: createWrapper(),
    });

    await screen.findByTestId('staging-panel-create');
    await user.type(screen.getByTestId('staging-create-name'), 'The Bridge Skirmish');
    await user.click(screen.getByTestId('staging-create-submit'));

    expect(await screen.findByTestId('staging-feedback')).toHaveTextContent('Battle stood up.');
  });

  it('navigates to the new battle scene on a successful create_battle dispatch', async () => {
    const mockMutateAsync = vi.fn(() =>
      Promise.resolve({
        backend: 'registry',
        deferred: false,
        message: 'Battle stood up.',
        success: true,
        data: { battle_id: 55, scene_id: 99 },
      })
    );
    vi.mocked(useDispatchPlayerAction).mockReturnValue({
      mutateAsync: mockMutateAsync,
      isPending: false,
    } as unknown as ReturnType<typeof useDispatchPlayerAction>);

    const createAction = makeStagingAction('create_battle', 'Create Battle');
    vi.mocked(fetchAvailableActions).mockResolvedValue({
      count: 1,
      next: null,
      previous: null,
      results: [createAction],
    });

    const user = userEvent.setup();
    render(<StagingPanel sceneId={10} battle={null} detail={null} />, {
      wrapper: createWrapper(),
    });

    await screen.findByTestId('staging-panel-create');
    await user.type(screen.getByTestId('staging-create-name'), 'The Bridge Skirmish');
    await user.click(screen.getByTestId('staging-create-submit'));

    await vi.waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/scenes/99/battle');
    });
  });

  it('does not navigate when create_battle succeeds without a scene_id in data', async () => {
    const mockMutateAsync = vi.fn(() =>
      Promise.resolve({ backend: 'registry', deferred: false, message: 'Battle stood up.' })
    );
    vi.mocked(useDispatchPlayerAction).mockReturnValue({
      mutateAsync: mockMutateAsync,
      isPending: false,
    } as unknown as ReturnType<typeof useDispatchPlayerAction>);

    const createAction = makeStagingAction('create_battle', 'Create Battle');
    vi.mocked(fetchAvailableActions).mockResolvedValue({
      count: 1,
      next: null,
      previous: null,
      results: [createAction],
    });

    const user = userEvent.setup();
    render(<StagingPanel sceneId={10} battle={null} detail={null} />, {
      wrapper: createWrapper(),
    });

    await screen.findByTestId('staging-panel-create');
    await user.type(screen.getByTestId('staging-create-name'), 'The Bridge Skirmish');
    await user.click(screen.getByTestId('staging-create-submit'));

    await screen.findByTestId('staging-feedback');
    expect(mockNavigate).not.toHaveBeenCalled();
  });

  it('shows the thrown error message when a dispatch fails', async () => {
    const mockMutateAsync = vi.fn(() =>
      Promise.reject(new Error('That name is already in use for this scene.'))
    );
    vi.mocked(useDispatchPlayerAction).mockReturnValue({
      mutateAsync: mockMutateAsync,
      isPending: false,
    } as unknown as ReturnType<typeof useDispatchPlayerAction>);

    const createAction = makeStagingAction('create_battle', 'Create Battle');
    vi.mocked(fetchAvailableActions).mockResolvedValue({
      count: 1,
      next: null,
      previous: null,
      results: [createAction],
    });

    const user = userEvent.setup();
    render(<StagingPanel sceneId={10} battle={null} detail={null} />, {
      wrapper: createWrapper(),
    });

    await screen.findByTestId('staging-panel-create');
    await user.type(screen.getByTestId('staging-create-name'), 'The Bridge Skirmish');
    await user.click(screen.getByTestId('staging-create-submit'));

    expect(await screen.findByTestId('staging-feedback')).toHaveTextContent(
      'That name is already in use for this scene.'
    );
  });

  it('resets the spawn form and shows the outcome message after a successful spawn', async () => {
    const mockMutateAsync = vi.fn(() =>
      Promise.resolve({ backend: 'registry', deferred: false, message: 'Spawned 3 Spearmen.' })
    );
    vi.mocked(useDispatchPlayerAction).mockReturnValue({
      mutateAsync: mockMutateAsync,
      isPending: false,
    } as unknown as ReturnType<typeof useDispatchPlayerAction>);

    vi.mocked(fetchAvailableActions).mockResolvedValue({
      count: 1,
      next: null,
      previous: null,
      results: [makeStagingAction('spawn_battle_units', 'Spawn Battle Units')],
    });

    const user = userEvent.setup();
    render(<StagingPanel sceneId={10} battle={{ id: 7 }} detail={MOCK_BATTLE_DETAIL} />, {
      wrapper: createWrapper(),
    });

    await screen.findByTestId('staging-spawn-units');
    await user.selectOptions(screen.getByTestId('staging-spawn-template'), '1');
    await user.selectOptions(screen.getByTestId('staging-spawn-side'), '100');
    await user.click(screen.getByTestId('staging-spawn-submit'));

    expect(await screen.findByTestId('staging-feedback')).toHaveTextContent('Spawned 3 Spearmen.');
    expect(screen.getByTestId('staging-spawn-template')).toHaveValue('');
    // Side selection is left in place — a GM commonly spawns several waves in a row.
    expect(screen.getByTestId('staging-spawn-side')).toHaveValue('100');
  });

  it('renders failure styling and does not reset the form when the dispatch resolves success: false', async () => {
    const mockMutateAsync = vi.fn(() =>
      Promise.resolve({
        backend: 'registry',
        deferred: false,
        message: 'A battle with that name already exists in this scene.',
        success: false,
      })
    );
    vi.mocked(useDispatchPlayerAction).mockReturnValue({
      mutateAsync: mockMutateAsync,
      isPending: false,
    } as unknown as ReturnType<typeof useDispatchPlayerAction>);

    const createAction = makeStagingAction('create_battle', 'Create Battle');
    vi.mocked(fetchAvailableActions).mockResolvedValue({
      count: 1,
      next: null,
      previous: null,
      results: [createAction],
    });

    const user = userEvent.setup();
    render(<StagingPanel sceneId={10} battle={null} detail={null} />, {
      wrapper: createWrapper(),
    });

    await screen.findByTestId('staging-panel-create');
    await user.type(screen.getByTestId('staging-create-name'), 'The Bridge Skirmish');
    await user.click(screen.getByTestId('staging-create-submit'));

    const feedback = await screen.findByTestId('staging-feedback');
    expect(feedback).toHaveTextContent('A battle with that name already exists in this scene.');
    expect(feedback).toHaveClass('text-destructive');
    // Business-rule rejection — nothing changed server-side, so the form is not reset.
    expect(screen.getByTestId('staging-create-name')).toHaveValue('The Bridge Skirmish');
  });

  it('still treats a resolved dispatch with success: true as a normal success', async () => {
    const mockMutateAsync = vi.fn(() =>
      Promise.resolve({
        backend: 'registry',
        deferred: false,
        message: 'Battle stood up.',
        success: true,
      })
    );
    vi.mocked(useDispatchPlayerAction).mockReturnValue({
      mutateAsync: mockMutateAsync,
      isPending: false,
    } as unknown as ReturnType<typeof useDispatchPlayerAction>);

    const createAction = makeStagingAction('create_battle', 'Create Battle');
    vi.mocked(fetchAvailableActions).mockResolvedValue({
      count: 1,
      next: null,
      previous: null,
      results: [createAction],
    });

    const user = userEvent.setup();
    render(<StagingPanel sceneId={10} battle={null} detail={null} />, {
      wrapper: createWrapper(),
    });

    await screen.findByTestId('staging-panel-create');
    await user.type(screen.getByTestId('staging-create-name'), 'The Bridge Skirmish');
    await user.click(screen.getByTestId('staging-create-submit'));

    const feedback = await screen.findByTestId('staging-feedback');
    expect(feedback).toHaveTextContent('Battle stood up.');
    expect(feedback).not.toHaveClass('text-destructive');
    expect(screen.getByTestId('staging-create-name')).toHaveValue('');
  });
});
