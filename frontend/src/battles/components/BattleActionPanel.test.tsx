import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';

import type { BattleDetail } from '../types';

// ---------------------------------------------------------------------------
// Mocks — must come before importing the component under test
// ---------------------------------------------------------------------------

vi.mock('@/roster/queries', () => ({
  useMyRosterEntriesQuery: vi.fn(() => ({
    data: [
      {
        id: 1,
        name: 'TestChar',
        character_id: 501,
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

vi.mock('@/scenes/actionQueries', () => ({
  useCastableTechniques: vi.fn(() => ({
    data: [
      {
        id: 900,
        name: 'Shield Bash',
        description: '',
        anima_cost: 0,
        tier: 1,
        intensity: 1,
        control: 1,
        hostile: true,
      },
    ],
  })),
}));

vi.mock('@/scenes/queries', async () => {
  const actual = await vi.importActual<typeof import('@/scenes/queries')>('@/scenes/queries');
  return {
    ...actual,
    fetchScene: vi.fn(),
  };
});

import { useDispatchPlayerAction } from '@/combat/queries';
import { useCastableTechniques } from '@/scenes/actionQueries';
import { fetchScene } from '@/scenes/queries';
import { BattleActionPanel } from './BattleActionPanel';

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

const MY_PARTICIPANT = {
  id: 1,
  status: 'active' as const,
  side_id: 100,
  place_id: 900,
  persona: { id: 5000, name: 'Test Persona', thumbnail_url: null, thumbnail_media_url: null },
  character_sheet_id: 501,
  is_champion: false,
  declared_this_round: false,
};

const ENEMY_UNIT = {
  id: 200,
  name: 'Goblin Raiders',
  descriptor: '',
  quality: 'trained' as const,
  status: 'active' as const,
  strength: 80,
  morale: 60,
  individual_count: null,
  side_id: 101,
  place_id: 900,
};

const OWN_PLACE = {
  id: 900,
  name: 'The Ford',
  terrain_type: 'open' as const,
  movement_cost: 1,
  x: 0,
  y: 0,
  footprint_radius: 1,
  controlled_by_id: null,
  encounter_scene_id: null,
  encounter_roster: null,
  vehicle: null,
  fortifications: [
    {
      id: 300,
      kind: 'wall',
      integrity: 50,
      max_integrity: 100,
      breached: false,
      defending_side_id: 100,
    },
  ],
};

const MOCK_BATTLE_DETAIL: BattleDetail = {
  id: 7,
  name: 'Battle for Test Scene',
  outcome: 'unresolved',
  risk_level: 'low',
  is_paused: false,
  round: { number: 1, status: 'declaring' },
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
  places: [OWN_PLACE],
  units: [ENEMY_UNIT],
  participants: [MY_PARTICIPANT],
  concluded_at: null,
  created_at: '2026-07-09T08:00:00Z',
  campaign_story_id: null,
  scene_id: 1,
  deeds: [],
};

const MOCK_SCENE_NOT_GM = {
  id: 1,
  name: 'Test Scene',
  description: '',
  date_started: '',
  location: null,
  participants: [],
  is_active: true,
  is_owner: false,
  viewer_can_gm: false,
  positions: [],
  position_adjacency: [],
  persona_positions: [],
  active_round: null,
  personas: [],
  position_nodes: [],
  position_edges: [],
};

const MOCK_SCENE_GM = { ...MOCK_SCENE_NOT_GM, viewer_can_gm: true };

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('BattleActionPanel — BattleDeclarationSection (#3389 Phase 1)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchScene).mockResolvedValue(MOCK_SCENE_NOT_GM);
    vi.mocked(useDispatchPlayerAction).mockReturnValue({
      mutateAsync: vi.fn(() => Promise.resolve()),
      isPending: false,
    } as unknown as ReturnType<typeof useDispatchPlayerAction>);
    vi.mocked(useCastableTechniques).mockReturnValue({
      data: [
        {
          id: 900,
          name: 'Shield Bash',
          description: '',
          anima_cost: 0,
          tier: 1,
          intensity: 1,
          control: 1,
          hostile: true,
        },
      ],
    } as unknown as ReturnType<typeof useCastableTechniques>);
  });

  it('renders nothing when the viewer has no ACTIVE participant row in this battle', () => {
    const { container } = render(
      <BattleActionPanel
        sceneId={1}
        battle={{ id: 7 }}
        detail={{ ...MOCK_BATTLE_DETAIL, participants: [] }}
      />,
      { wrapper: createWrapper() }
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing when the round is not open for declarations', () => {
    const { container } = render(
      <BattleActionPanel
        sceneId={1}
        battle={{ id: 7 }}
        detail={{ ...MOCK_BATTLE_DETAIL, round: { number: 1, status: 'resolving' } }}
      />,
      { wrapper: createWrapper() }
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('renders the declaration form for an ACTIVE participant in a DECLARING round', () => {
    render(<BattleActionPanel sceneId={1} battle={{ id: 7 }} detail={MOCK_BATTLE_DETAIL} />, {
      wrapper: createWrapper(),
    });
    expect(screen.getByTestId('battle-declaration-section')).toBeInTheDocument();
    expect(screen.getByText('Shield Bash')).toBeInTheDocument();
  });

  it('shows the already-declared note when declared_this_round is true', () => {
    const detail: BattleDetail = {
      ...MOCK_BATTLE_DETAIL,
      participants: [{ ...MY_PARTICIPANT, declared_this_round: true }],
    };
    render(<BattleActionPanel sceneId={1} battle={{ id: 7 }} detail={detail} />, {
      wrapper: createWrapper(),
    });
    expect(screen.getByTestId('battle-declaration-already-declared')).toBeInTheDocument();
  });

  it('STRIKE (default kind): dispatches declare_battle_action with technique_id/action_kind/scope/target_unit', async () => {
    const mockMutateAsync = vi.fn(() => Promise.resolve());
    vi.mocked(useDispatchPlayerAction).mockReturnValue({
      mutateAsync: mockMutateAsync,
      isPending: false,
    } as unknown as ReturnType<typeof useDispatchPlayerAction>);

    const user = userEvent.setup();
    render(<BattleActionPanel sceneId={1} battle={{ id: 7 }} detail={MOCK_BATTLE_DETAIL} />, {
      wrapper: createWrapper(),
    });

    await user.selectOptions(screen.getByTestId('battle-declaration-technique'), '900');
    await user.selectOptions(screen.getByTestId('battle-declaration-target-unit'), '200');
    await user.click(screen.getByTestId('battle-declaration-submit'));

    expect(mockMutateAsync).toHaveBeenCalledWith({
      ref: { backend: 'registry', registry_key: 'declare_battle_action' },
      kwargs: {
        technique_id: 900,
        action_kind: 'strike',
        scope: 'unit',
        target_unit: 200,
      },
    });
  });

  it('BREACH: switches to the fortification target shape, sourced from the selected place', async () => {
    const user = userEvent.setup();
    render(<BattleActionPanel sceneId={1} battle={{ id: 7 }} detail={MOCK_BATTLE_DETAIL} />, {
      wrapper: createWrapper(),
    });

    await user.selectOptions(screen.getByTestId('battle-declaration-kind'), 'breach');
    expect(screen.getByTestId('battle-declaration-fortification-place')).toBeInTheDocument();

    await user.selectOptions(screen.getByTestId('battle-declaration-fortification-place'), '900');
    expect(screen.getByTestId('battle-declaration-target-fortification')).toBeInTheDocument();
    expect(screen.getByText('wall (50/100)')).toBeInTheDocument();
  });

  it('REPOSITION: forces PLACE scope and renders dx/dy inputs, dispatched as kwargs', async () => {
    const mockMutateAsync = vi.fn(() => Promise.resolve());
    vi.mocked(useDispatchPlayerAction).mockReturnValue({
      mutateAsync: mockMutateAsync,
      isPending: false,
    } as unknown as ReturnType<typeof useDispatchPlayerAction>);

    const user = userEvent.setup();
    render(<BattleActionPanel sceneId={1} battle={{ id: 7 }} detail={MOCK_BATTLE_DETAIL} />, {
      wrapper: createWrapper(),
    });

    await user.selectOptions(screen.getByTestId('battle-declaration-kind'), 'reposition');
    expect(screen.getByTestId('battle-declaration-scope')).toHaveValue('place');
    expect(screen.getByTestId('battle-declaration-scope')).toBeDisabled();

    await user.selectOptions(screen.getByTestId('battle-declaration-technique'), '900');
    await user.selectOptions(screen.getByTestId('battle-declaration-target-place'), '900');
    await user.type(screen.getByTestId('battle-declaration-reposition-dx'), '2');
    await user.type(screen.getByTestId('battle-declaration-reposition-dy'), '-1');
    await user.click(screen.getByTestId('battle-declaration-submit'));

    expect(mockMutateAsync).toHaveBeenCalledWith({
      ref: { backend: 'registry', registry_key: 'declare_battle_action' },
      kwargs: {
        technique_id: 900,
        action_kind: 'reposition',
        scope: 'place',
        target_place: 900,
        reposition_dx: '2',
        reposition_dy: '-1',
      },
    });
  });

  it('MOVE: scope toggles between self-move (unit) and commander order (place)', async () => {
    const user = userEvent.setup();
    render(<BattleActionPanel sceneId={1} battle={{ id: 7 }} detail={MOCK_BATTLE_DETAIL} />, {
      wrapper: createWrapper(),
    });

    await user.selectOptions(screen.getByTestId('battle-declaration-kind'), 'move');
    expect(screen.getByTestId('battle-declaration-scope')).toHaveValue('unit');
    expect(screen.getByTestId('battle-declaration-scope')).not.toBeDisabled();
    expect(screen.queryByTestId('battle-declaration-move-unit')).not.toBeInTheDocument();

    await user.selectOptions(screen.getByTestId('battle-declaration-move-kind'), 'order');
    expect(screen.getByTestId('battle-declaration-scope')).toHaveValue('place');
    expect(screen.getByTestId('battle-declaration-move-unit')).toBeInTheDocument();
  });

  it('shows the server failure message on a business-rule rejection (isDispatchFailure)', async () => {
    const mockMutateAsync = vi.fn(() =>
      Promise.resolve({
        backend: 'registry',
        deferred: false,
        message: 'No active round to declare into.',
        success: false,
      })
    );
    vi.mocked(useDispatchPlayerAction).mockReturnValue({
      mutateAsync: mockMutateAsync,
      isPending: false,
    } as unknown as ReturnType<typeof useDispatchPlayerAction>);

    const user = userEvent.setup();
    render(<BattleActionPanel sceneId={1} battle={{ id: 7 }} detail={MOCK_BATTLE_DETAIL} />, {
      wrapper: createWrapper(),
    });

    await user.selectOptions(screen.getByTestId('battle-declaration-technique'), '900');
    await user.selectOptions(screen.getByTestId('battle-declaration-target-unit'), '200');
    await user.click(screen.getByTestId('battle-declaration-submit'));

    const feedback = await screen.findByTestId('battle-declaration-feedback');
    expect(feedback).toHaveTextContent('No active round to declare into.');
    expect(feedback).toHaveClass('text-destructive');
  });
});

describe('BattleActionPanel — BattleLifecycleSection (#3389 Phase 2)', () => {
  const detailNoParticipants: BattleDetail = { ...MOCK_BATTLE_DETAIL, participants: [] };

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useDispatchPlayerAction).mockReturnValue({
      mutateAsync: vi.fn(() => Promise.resolve()),
      isPending: false,
    } as unknown as ReturnType<typeof useDispatchPlayerAction>);
    vi.mocked(useCastableTechniques).mockReturnValue({
      data: [],
    } as unknown as ReturnType<typeof useCastableTechniques>);
  });

  it('renders nothing when the viewer is not the scene GM (viewer_can_gm=false)', async () => {
    vi.mocked(fetchScene).mockResolvedValue(MOCK_SCENE_NOT_GM);
    const { container } = render(
      <BattleActionPanel sceneId={1} battle={{ id: 7 }} detail={detailNoParticipants} />,
      { wrapper: createWrapper() }
    );
    await vi.waitFor(() => {
      expect(container).toBeEmptyDOMElement();
    });
  });

  it('renders the lifecycle section when viewer_can_gm=true, independent of participant standing', async () => {
    vi.mocked(fetchScene).mockResolvedValue(MOCK_SCENE_GM);
    render(<BattleActionPanel sceneId={1} battle={{ id: 7 }} detail={detailNoParticipants} />, {
      wrapper: createWrapper(),
    });
    expect(await screen.findByTestId('battle-lifecycle-section')).toBeInTheDocument();
  });

  it('Begin Round is enabled when there is no open round', async () => {
    vi.mocked(fetchScene).mockResolvedValue(MOCK_SCENE_GM);
    render(
      <BattleActionPanel
        sceneId={1}
        battle={{ id: 7 }}
        detail={{ ...detailNoParticipants, round: null }}
      />,
      { wrapper: createWrapper() }
    );
    expect(await screen.findByTestId('battle-lifecycle-begin')).not.toBeDisabled();
  });

  it('Begin Round is disabled while a round is DECLARING', async () => {
    vi.mocked(fetchScene).mockResolvedValue(MOCK_SCENE_GM);
    render(
      <BattleActionPanel
        sceneId={1}
        battle={{ id: 7 }}
        detail={{ ...detailNoParticipants, round: { number: 1, status: 'declaring' } }}
      />,
      { wrapper: createWrapper() }
    );
    expect(await screen.findByTestId('battle-lifecycle-begin')).toBeDisabled();
  });

  it('Resolve Round is enabled only while the round is DECLARING, and dispatches resolve_battle_round', async () => {
    const mockMutateAsync = vi.fn(() => Promise.resolve());
    vi.mocked(useDispatchPlayerAction).mockReturnValue({
      mutateAsync: mockMutateAsync,
      isPending: false,
    } as unknown as ReturnType<typeof useDispatchPlayerAction>);
    vi.mocked(fetchScene).mockResolvedValue(MOCK_SCENE_GM);

    const user = userEvent.setup();
    render(
      <BattleActionPanel
        sceneId={1}
        battle={{ id: 7 }}
        detail={{ ...detailNoParticipants, round: { number: 1, status: 'declaring' } }}
      />,
      { wrapper: createWrapper() }
    );

    const resolveButton = await screen.findByTestId('battle-lifecycle-resolve');
    expect(resolveButton).not.toBeDisabled();
    await user.click(resolveButton);

    expect(mockMutateAsync).toHaveBeenCalledWith({
      ref: { backend: 'registry', registry_key: 'resolve_battle_round' },
      kwargs: {},
    });
  });

  it('Conclude Battle requires a confirm step before dispatching conclude_battle', async () => {
    const mockMutateAsync = vi.fn(() => Promise.resolve());
    vi.mocked(useDispatchPlayerAction).mockReturnValue({
      mutateAsync: mockMutateAsync,
      isPending: false,
    } as unknown as ReturnType<typeof useDispatchPlayerAction>);
    vi.mocked(fetchScene).mockResolvedValue(MOCK_SCENE_GM);

    const user = userEvent.setup();
    render(<BattleActionPanel sceneId={1} battle={{ id: 7 }} detail={detailNoParticipants} />, {
      wrapper: createWrapper(),
    });

    const concludeButton = await screen.findByTestId('battle-lifecycle-conclude');
    await user.click(concludeButton);
    expect(mockMutateAsync).not.toHaveBeenCalled();
    expect(await screen.findByTestId('battle-lifecycle-confirm-conclude')).toBeInTheDocument();

    await user.click(screen.getByTestId('battle-lifecycle-confirm-conclude'));
    expect(mockMutateAsync).toHaveBeenCalledWith({
      ref: { backend: 'registry', registry_key: 'conclude_battle' },
      kwargs: {},
    });
  });

  it('Conclude Battle is disabled once the battle already has concluded_at set', async () => {
    vi.mocked(fetchScene).mockResolvedValue(MOCK_SCENE_GM);
    render(
      <BattleActionPanel
        sceneId={1}
        battle={{ id: 7 }}
        detail={{ ...detailNoParticipants, concluded_at: '2026-08-26T00:00:00Z' }}
      />,
      { wrapper: createWrapper() }
    );
    expect(await screen.findByTestId('battle-lifecycle-conclude')).toBeDisabled();
  });

  it('shows the server failure message on a lifecycle business-rule rejection', async () => {
    const mockMutateAsync = vi.fn(() =>
      Promise.resolve({
        backend: 'registry',
        deferred: false,
        message: "Only the battle's GM or staff can do that.",
        success: false,
      })
    );
    vi.mocked(useDispatchPlayerAction).mockReturnValue({
      mutateAsync: mockMutateAsync,
      isPending: false,
    } as unknown as ReturnType<typeof useDispatchPlayerAction>);
    vi.mocked(fetchScene).mockResolvedValue(MOCK_SCENE_GM);

    const user = userEvent.setup();
    render(
      <BattleActionPanel
        sceneId={1}
        battle={{ id: 7 }}
        detail={{ ...detailNoParticipants, round: null }}
      />,
      { wrapper: createWrapper() }
    );

    await user.click(await screen.findByTestId('battle-lifecycle-begin'));

    const feedback = await screen.findByTestId('battle-lifecycle-feedback');
    expect(feedback).toHaveTextContent("Only the battle's GM or staff can do that.");
    expect(feedback).toHaveClass('text-destructive');
  });
});
