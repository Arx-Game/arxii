/**
 * Tests for GMEncounterControls (#3067) — the GM's home for encounter
 * lifecycle actions (create, add_opponent, add/remove_participant,
 * begin_round, resolve_round, pause).
 *
 * Mocks '../queries' and '@/roster/usePersonaSearch' (mirrors YourTurn.test.tsx's
 * mock-the-hook-module idiom). Interacts with the REAL Dialog + Select
 * primitives (Radix) — jsdom's pointer-capture/scrollIntoView polyfills for
 * Radix Select already live in src/test/setup.ts (see FuryDeclaration usage
 * in YourTurn.test.tsx for the click-trigger-then-click-item pattern this
 * file mirrors), so no need to mock Select away.
 */

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import type { ReactNode } from 'react';

vi.mock('../queries', () => ({
  useThreatPools: vi.fn(),
  useOpponentDefaults: vi.fn(),
  useCreateEncounter: vi.fn(),
  useAddOpponent: vi.fn(),
  useAddParticipant: vi.fn(),
  useBeginRound: vi.fn(),
  useResolveRound: vi.fn(),
  usePauseEncounter: vi.fn(),
  useUpdateEncounterSettings: vi.fn(),
  useRemoveParticipant: vi.fn(),
  useProposeLethalDuel: vi.fn(),
}));

vi.mock('@/roster/usePersonaSearch', () => ({
  usePersonaSearch: vi.fn(),
}));

vi.mock('sonner', () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}));

import * as combatQueries from '../queries';
import { usePersonaSearch } from '@/roster/usePersonaSearch';
import { GMEncounterControls } from '../sections/GMEncounterControls';
import type { ThreatPool } from '../api';
import type { EncounterDetail, Participant, PositionNode } from '../types';

// ---------------------------------------------------------------------------
// Wrapper
// ---------------------------------------------------------------------------

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeEncounter(overrides: Partial<EncounterDetail> = {}): EncounterDetail {
  return {
    id: 1,
    is_gm: true,
    pace_mode: 'timed',
    stakes_level: 'local',
    risk_level: 'moderate',
    pace_timer_minutes: 10,
    status: 'between_rounds',
    is_paused: false,
    participants: [],
    position_nodes: [],
    ...overrides,
  } as unknown as EncounterDetail;
}

function makeParticipant(id: number, name: string): Participant {
  return { id, character_name: name } as unknown as Participant;
}

// ---------------------------------------------------------------------------
// Mocked hooks
// ---------------------------------------------------------------------------

const mockedUseThreatPools = combatQueries.useThreatPools as ReturnType<typeof vi.fn>;
const mockedUseOpponentDefaults = combatQueries.useOpponentDefaults as ReturnType<typeof vi.fn>;
const mockedUseCreateEncounter = combatQueries.useCreateEncounter as ReturnType<typeof vi.fn>;
const mockedUseAddOpponent = combatQueries.useAddOpponent as ReturnType<typeof vi.fn>;
const mockedUseAddParticipant = combatQueries.useAddParticipant as ReturnType<typeof vi.fn>;
const mockedUseBeginRound = combatQueries.useBeginRound as ReturnType<typeof vi.fn>;
const mockedUseResolveRound = combatQueries.useResolveRound as ReturnType<typeof vi.fn>;
const mockedUsePauseEncounter = combatQueries.usePauseEncounter as ReturnType<typeof vi.fn>;
const mockedUseUpdateEncounterSettings = combatQueries.useUpdateEncounterSettings as ReturnType<
  typeof vi.fn
>;
const mockedUseRemoveParticipant = combatQueries.useRemoveParticipant as ReturnType<typeof vi.fn>;
const mockedUseProposeLethalDuel = combatQueries.useProposeLethalDuel as ReturnType<typeof vi.fn>;
const mockedUsePersonaSearch = usePersonaSearch as unknown as ReturnType<typeof vi.fn>;

interface MutateOpts {
  onSuccess?: (data?: unknown) => void;
  onError?: (err: Error) => void;
}

const mockCreateMutate = vi.fn(
  (_vars: { paceMode?: string; encounterType?: string }, _opts?: MutateOpts) => {}
);
const mockAddOpponentMutate = vi.fn(
  (
    _vars: { name: string; tier: string; threatPoolId: number; positionId: number | null },
    _opts?: MutateOpts
  ) => {}
);
const mockAddParticipantMutate = vi.fn(
  (_vars: { characterSheetId: number; covenantRoleId?: number | null }, _opts?: MutateOpts) => {}
);
const mockBeginRoundMutate = vi.fn((_vars: undefined, _opts?: MutateOpts) => {});
const mockResolveRoundMutate = vi.fn((_vars: undefined, _opts?: MutateOpts) => {});
const mockPauseMutate = vi.fn((_vars: undefined, _opts?: MutateOpts) => {});
const mockUpdateSettingsMutate = vi.fn(
  (
    _vars: {
      stakesLevel?: string;
      riskLevel?: string;
      paceMode?: string;
      paceTimerMinutes?: number;
    },
    _opts?: MutateOpts
  ) => {}
);
const mockRemoveParticipantMutate = vi.fn((_vars: number, _opts?: MutateOpts) => {});
const mockProposeLethalDuelMutate = vi.fn(
  (
    _vars: {
      sceneId: number;
      challengedSheetId: number;
      opponentName: string;
      tier: string;
      threatPoolId: number;
    },
    _opts?: MutateOpts
  ) => {}
);

const defaultPools: ThreatPool[] = [
  { id: 7, name: 'Goblin Raiders', description: '' } as unknown as ThreatPool,
];

beforeEach(() => {
  vi.clearAllMocks();
  mockedUseThreatPools.mockReturnValue({ data: defaultPools });
  mockedUseOpponentDefaults.mockReturnValue({ data: undefined });
  mockedUseCreateEncounter.mockReturnValue({ mutate: mockCreateMutate, isPending: false });
  mockedUseAddOpponent.mockReturnValue({
    mutate: mockAddOpponentMutate,
    isPending: false,
    error: null,
    isError: false,
  });
  mockedUseAddParticipant.mockReturnValue({
    mutate: mockAddParticipantMutate,
    isPending: false,
    error: null,
    isError: false,
  });
  mockedUseBeginRound.mockReturnValue({ mutate: mockBeginRoundMutate, isPending: false });
  mockedUseResolveRound.mockReturnValue({ mutate: mockResolveRoundMutate, isPending: false });
  mockedUsePauseEncounter.mockReturnValue({ mutate: mockPauseMutate, isPending: false });
  mockedUseUpdateEncounterSettings.mockReturnValue({
    mutate: mockUpdateSettingsMutate,
    isPending: false,
  });
  mockedUseRemoveParticipant.mockReturnValue({
    mutate: mockRemoveParticipantMutate,
    isPending: false,
  });
  mockedUseProposeLethalDuel.mockReturnValue({
    mutate: mockProposeLethalDuelMutate,
    isPending: false,
    error: null,
    isError: false,
  });
  mockedUsePersonaSearch.mockReturnValue({ results: [], isFetching: false });
});

// ---------------------------------------------------------------------------
// No active encounter — Start Encounter affordance
// ---------------------------------------------------------------------------

describe('GMEncounterControls — no active encounter', () => {
  it('shows the Start Encounter card when the viewer can GM', () => {
    render(<GMEncounterControls sceneId={5} encounter={null} viewerCanGm={true} />, {
      wrapper: createWrapper(),
    });

    expect(screen.getByTestId('start-encounter-card')).toBeInTheDocument();
  });

  it('renders nothing when the viewer cannot GM', () => {
    render(<GMEncounterControls sceneId={5} encounter={null} viewerCanGm={false} />, {
      wrapper: createWrapper(),
    });

    expect(screen.queryByTestId('start-encounter-card')).not.toBeInTheDocument();
  });

  it('calls create with the selected pace mode', async () => {
    const user = userEvent.setup({ pointerEventsCheck: 0 });
    render(<GMEncounterControls sceneId={5} encounter={null} viewerCanGm={true} />, {
      wrapper: createWrapper(),
    });

    await user.click(screen.getByTestId('start-encounter-btn'));

    expect(mockCreateMutate).toHaveBeenCalledWith(
      { paceMode: 'timed' },
      expect.objectContaining({ onError: expect.any(Function) })
    );
  });

  it('creates with a GM-selected pace mode', async () => {
    const user = userEvent.setup({ pointerEventsCheck: 0 });
    render(<GMEncounterControls sceneId={5} encounter={null} viewerCanGm={true} />, {
      wrapper: createWrapper(),
    });

    await user.click(screen.getByTestId('start-encounter-pace-select'));
    const manualOption = await screen.findByRole('option', { name: /Manual/ });
    await user.click(manualOption);

    await user.click(screen.getByTestId('start-encounter-btn'));

    expect(mockCreateMutate).toHaveBeenCalledWith(
      { paceMode: 'manual' },
      expect.objectContaining({ onError: expect.any(Function) })
    );
  });
});

// ---------------------------------------------------------------------------
// Active encounter — GM gate
// ---------------------------------------------------------------------------

describe('GMEncounterControls — active-encounter GM gate', () => {
  it('renders full controls when the viewer is the encounter GM', () => {
    render(
      <GMEncounterControls
        sceneId={5}
        encounter={makeEncounter({ is_gm: true })}
        viewerCanGm={false}
      />,
      { wrapper: createWrapper() }
    );

    expect(screen.getByTestId('gm-encounter-controls')).toBeInTheDocument();
  });

  it('renders nothing when the viewer is not the encounter GM', () => {
    render(
      <GMEncounterControls
        sceneId={5}
        encounter={makeEncounter({ is_gm: false })}
        viewerCanGm={true}
      />,
      { wrapper: createWrapper() }
    );

    expect(screen.queryByTestId('gm-encounter-controls')).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Add opponent
// ---------------------------------------------------------------------------

describe('GMEncounterControls — add opponent', () => {
  it('submits the right payload (no position)', async () => {
    const user = userEvent.setup({ pointerEventsCheck: 0 });
    render(<GMEncounterControls sceneId={5} encounter={makeEncounter()} viewerCanGm={false} />, {
      wrapper: createWrapper(),
    });

    await user.click(screen.getByTestId('add-opponent-trigger'));
    await user.type(screen.getByTestId('add-opponent-name'), 'Goblin');

    await user.click(screen.getByTestId('add-opponent-pool-select'));
    const poolOption = await screen.findByRole('option', { name: 'Goblin Raiders' });
    await user.click(poolOption);

    await user.click(screen.getByTestId('add-opponent-submit'));

    expect(mockAddOpponentMutate).toHaveBeenCalledWith(
      { name: 'Goblin', tier: 'mook', threatPoolId: 7, positionId: null },
      expect.objectContaining({
        onSuccess: expect.any(Function),
        onError: expect.any(Function),
      })
    );
  });

  it('submits the selected tier and position', async () => {
    const user = userEvent.setup({ pointerEventsCheck: 0 });
    const encounter = makeEncounter({
      position_nodes: [{ id: 12, name: 'North Wall' } as unknown as PositionNode],
    });
    render(<GMEncounterControls sceneId={5} encounter={encounter} viewerCanGm={false} />, {
      wrapper: createWrapper(),
    });

    await user.click(screen.getByTestId('add-opponent-trigger'));
    await user.type(screen.getByTestId('add-opponent-name'), 'Ogre');

    await user.click(screen.getByTestId('add-opponent-tier-select'));
    await user.click(await screen.findByRole('option', { name: 'Boss' }));

    await user.click(screen.getByTestId('add-opponent-pool-select'));
    await user.click(await screen.findByRole('option', { name: 'Goblin Raiders' }));

    await user.click(screen.getByTestId('add-opponent-position-select'));
    await user.click(await screen.findByRole('option', { name: 'North Wall' }));

    await user.click(screen.getByTestId('add-opponent-submit'));

    expect(mockAddOpponentMutate).toHaveBeenCalledWith(
      { name: 'Ogre', tier: 'boss', threatPoolId: 7, positionId: 12 },
      expect.objectContaining({ onSuccess: expect.any(Function) })
    );
  });

  it('shows the scaling defaults preview when available', async () => {
    mockedUseOpponentDefaults.mockReturnValue({
      data: {
        max_health: 30,
        soak_value: 2,
        probing_threshold: null,
        swarm_count: null,
        body_toughness: null,
        bodies_per_attack: null,
        barrier_strength: null,
        phases: [],
        stakes_ok: false,
        stakes_message: 'Escalate the stakes first.',
      },
    });
    const user = userEvent.setup({ pointerEventsCheck: 0 });
    render(<GMEncounterControls sceneId={5} encounter={makeEncounter()} viewerCanGm={false} />, {
      wrapper: createWrapper(),
    });

    await user.click(screen.getByTestId('add-opponent-trigger'));

    expect(screen.getByTestId('add-opponent-defaults-preview')).toHaveTextContent('Health 30');
    expect(screen.getByTestId('add-opponent-stakes-warning')).toHaveTextContent(
      'Escalate the stakes first.'
    );
  });

  it('keeps submit disabled until name and threat pool are set', async () => {
    const user = userEvent.setup({ pointerEventsCheck: 0 });
    render(<GMEncounterControls sceneId={5} encounter={makeEncounter()} viewerCanGm={false} />, {
      wrapper: createWrapper(),
    });

    await user.click(screen.getByTestId('add-opponent-trigger'));

    expect(screen.getByTestId('add-opponent-submit')).toBeDisabled();
  });
});

// ---------------------------------------------------------------------------
// Add participant
// ---------------------------------------------------------------------------

describe('GMEncounterControls — add participant', () => {
  it('submits the selected character_sheet id', async () => {
    mockedUsePersonaSearch.mockReturnValue({
      results: [{ id: 99, name: 'Aerande', character_sheet: 55 }],
      isFetching: false,
    });
    const user = userEvent.setup({ pointerEventsCheck: 0 });
    render(<GMEncounterControls sceneId={5} encounter={makeEncounter()} viewerCanGm={false} />, {
      wrapper: createWrapper(),
    });

    await user.click(screen.getByTestId('add-participant-trigger'));
    await user.type(screen.getByTestId('add-participant-search'), 'Aer');
    await user.click(screen.getByTestId('add-participant-option-99'));
    await user.click(screen.getByTestId('add-participant-submit'));

    expect(mockAddParticipantMutate).toHaveBeenCalledWith(
      { characterSheetId: 55 },
      expect.objectContaining({ onSuccess: expect.any(Function) })
    );
  });

  it('keeps submit disabled until a character is selected', async () => {
    const user = userEvent.setup({ pointerEventsCheck: 0 });
    render(<GMEncounterControls sceneId={5} encounter={makeEncounter()} viewerCanGm={false} />, {
      wrapper: createWrapper(),
    });

    await user.click(screen.getByTestId('add-participant-trigger'));

    expect(screen.getByTestId('add-participant-submit')).toBeDisabled();
  });
});

// ---------------------------------------------------------------------------
// Start lethal duel (#3068)
// ---------------------------------------------------------------------------

describe('GMEncounterControls — start lethal duel', () => {
  it('shows the trigger when there is no encounter and the viewer can GM', () => {
    render(<GMEncounterControls sceneId={5} encounter={null} viewerCanGm={true} />, {
      wrapper: createWrapper(),
    });

    expect(screen.getByTestId('start-lethal-duel-trigger')).toBeInTheDocument();
  });

  it('hides the trigger when there is no encounter and the viewer cannot GM', () => {
    render(<GMEncounterControls sceneId={5} encounter={null} viewerCanGm={false} />, {
      wrapper: createWrapper(),
    });

    expect(screen.queryByTestId('start-lethal-duel-trigger')).not.toBeInTheDocument();
  });

  it('shows the trigger alongside an active encounter the viewer GMs', () => {
    render(
      <GMEncounterControls
        sceneId={5}
        encounter={makeEncounter({ is_gm: true })}
        viewerCanGm={false}
      />,
      { wrapper: createWrapper() }
    );

    expect(screen.getByTestId('start-lethal-duel-trigger')).toBeInTheDocument();
  });

  it('hides the trigger when an active encounter exists and the viewer is not its GM', () => {
    render(
      <GMEncounterControls
        sceneId={5}
        encounter={makeEncounter({ is_gm: false })}
        viewerCanGm={true}
      />,
      { wrapper: createWrapper() }
    );

    expect(screen.queryByTestId('start-lethal-duel-trigger')).not.toBeInTheDocument();
  });

  it('only offers significant-NPC tiers (elite/boss/hero_killer — no mook/swarm)', async () => {
    const user = userEvent.setup({ pointerEventsCheck: 0 });
    render(<GMEncounterControls sceneId={5} encounter={null} viewerCanGm={true} />, {
      wrapper: createWrapper(),
    });

    await user.click(screen.getByTestId('start-lethal-duel-trigger'));
    await user.click(screen.getByTestId('lethal-duel-tier-select'));

    expect(await screen.findByRole('option', { name: 'Elite' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'Boss' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'Hero Killer' })).toBeInTheDocument();
    expect(screen.queryByRole('option', { name: 'Mook' })).not.toBeInTheDocument();
    expect(screen.queryByRole('option', { name: 'Swarm' })).not.toBeInTheDocument();
  });

  it('keeps submit disabled until target, name, and threat pool are set', async () => {
    const user = userEvent.setup({ pointerEventsCheck: 0 });
    render(<GMEncounterControls sceneId={5} encounter={null} viewerCanGm={true} />, {
      wrapper: createWrapper(),
    });

    await user.click(screen.getByTestId('start-lethal-duel-trigger'));

    expect(screen.getByTestId('lethal-duel-submit')).toBeDisabled();
  });

  it('submits the right payload for the targeted PC', async () => {
    mockedUsePersonaSearch.mockReturnValue({
      results: [{ id: 21, name: 'Elenna', character_sheet: 88 }],
      isFetching: false,
    });
    const user = userEvent.setup({ pointerEventsCheck: 0 });
    render(<GMEncounterControls sceneId={5} encounter={null} viewerCanGm={true} />, {
      wrapper: createWrapper(),
    });

    await user.click(screen.getByTestId('start-lethal-duel-trigger'));
    await user.type(screen.getByTestId('lethal-duel-target-search'), 'Ele');
    await user.click(screen.getByTestId('lethal-duel-target-option-21'));

    await user.type(screen.getByTestId('lethal-duel-opponent-name'), 'The Widow Ashgrave');

    await user.click(screen.getByTestId('lethal-duel-tier-select'));
    await user.click(await screen.findByRole('option', { name: 'Boss' }));

    await user.click(screen.getByTestId('lethal-duel-pool-select'));
    await user.click(await screen.findByRole('option', { name: 'Goblin Raiders' }));

    await user.click(screen.getByTestId('lethal-duel-submit'));

    expect(mockProposeLethalDuelMutate).toHaveBeenCalledWith(
      {
        sceneId: 5,
        challengedSheetId: 88,
        opponentName: 'The Widow Ashgrave',
        tier: 'boss',
        threatPoolId: 7,
      },
      expect.objectContaining({
        onSuccess: expect.any(Function),
        onError: expect.any(Function),
      })
    );
  });
});

// ---------------------------------------------------------------------------
// Remove participant
// ---------------------------------------------------------------------------

describe('GMEncounterControls — remove participant', () => {
  it('calls the remove mutation with the participant id', async () => {
    const user = userEvent.setup({ pointerEventsCheck: 0 });
    const encounter = makeEncounter({ participants: [makeParticipant(42, 'Aerande')] });
    render(<GMEncounterControls sceneId={5} encounter={encounter} viewerCanGm={false} />, {
      wrapper: createWrapper(),
    });

    await user.click(screen.getByTestId('remove-participant-btn-42'));

    expect(mockRemoveParticipantMutate).toHaveBeenCalledWith(
      42,
      expect.objectContaining({ onError: expect.any(Function) })
    );
  });
});

// ---------------------------------------------------------------------------
// Manual round control
// ---------------------------------------------------------------------------

describe('GMEncounterControls — manual round control', () => {
  it('shows Begin Round only in MANUAL pace + between_rounds status', () => {
    render(
      <GMEncounterControls
        sceneId={5}
        encounter={makeEncounter({ pace_mode: 'manual', status: 'between_rounds' })}
        viewerCanGm={false}
      />,
      { wrapper: createWrapper() }
    );

    expect(screen.getByTestId('begin-round-btn')).toBeInTheDocument();
    expect(screen.queryByTestId('resolve-round-btn')).not.toBeInTheDocument();
  });

  it('shows Resolve Round only in MANUAL pace + declaring status', () => {
    render(
      <GMEncounterControls
        sceneId={5}
        encounter={makeEncounter({ pace_mode: 'manual', status: 'declaring' })}
        viewerCanGm={false}
      />,
      { wrapper: createWrapper() }
    );

    expect(screen.getByTestId('resolve-round-btn')).toBeInTheDocument();
    expect(screen.queryByTestId('begin-round-btn')).not.toBeInTheDocument();
  });

  it('hides both round-control buttons outside MANUAL pace', () => {
    render(
      <GMEncounterControls
        sceneId={5}
        encounter={makeEncounter({ pace_mode: 'timed', status: 'between_rounds' })}
        viewerCanGm={false}
      />,
      { wrapper: createWrapper() }
    );

    expect(screen.queryByTestId('begin-round-btn')).not.toBeInTheDocument();
    expect(screen.queryByTestId('resolve-round-btn')).not.toBeInTheDocument();
  });

  it('begin round button calls the begin_round mutation', async () => {
    const user = userEvent.setup({ pointerEventsCheck: 0 });
    render(
      <GMEncounterControls
        sceneId={5}
        encounter={makeEncounter({ pace_mode: 'manual', status: 'between_rounds' })}
        viewerCanGm={false}
      />,
      { wrapper: createWrapper() }
    );

    await user.click(screen.getByTestId('begin-round-btn'));

    expect(mockBeginRoundMutate).toHaveBeenCalledWith(
      undefined,
      expect.objectContaining({ onError: expect.any(Function) })
    );
  });

  it('resolve round button calls the resolve_round mutation', async () => {
    const user = userEvent.setup({ pointerEventsCheck: 0 });
    render(
      <GMEncounterControls
        sceneId={5}
        encounter={makeEncounter({ pace_mode: 'manual', status: 'declaring' })}
        viewerCanGm={false}
      />,
      { wrapper: createWrapper() }
    );

    await user.click(screen.getByTestId('resolve-round-btn'));

    expect(mockResolveRoundMutate).toHaveBeenCalledWith(
      undefined,
      expect.objectContaining({ onError: expect.any(Function) })
    );
  });
});

// ---------------------------------------------------------------------------
// Pause
// ---------------------------------------------------------------------------

describe('GMEncounterControls — pause toggle', () => {
  it('calls the pause mutation and shows Pause when not paused', async () => {
    const user = userEvent.setup({ pointerEventsCheck: 0 });
    render(
      <GMEncounterControls
        sceneId={5}
        encounter={makeEncounter({ is_paused: false })}
        viewerCanGm={false}
      />,
      { wrapper: createWrapper() }
    );

    expect(screen.getByTestId('pause-toggle-btn')).toHaveTextContent('Pause');
    await user.click(screen.getByTestId('pause-toggle-btn'));

    expect(mockPauseMutate).toHaveBeenCalledWith(
      undefined,
      expect.objectContaining({ onError: expect.any(Function) })
    );
  });

  it('shows Unpause when the encounter is already paused', () => {
    render(
      <GMEncounterControls
        sceneId={5}
        encounter={makeEncounter({ is_paused: true })}
        viewerCanGm={false}
      />,
      { wrapper: createWrapper() }
    );

    expect(screen.getByTestId('pause-toggle-btn')).toHaveTextContent('Unpause');
  });
});

// ---------------------------------------------------------------------------
// Settings row (#3383) — stakes/risk/pace/timer
// ---------------------------------------------------------------------------

describe('GMEncounterControls — settings row', () => {
  it('renders the current stakes/risk/pace values', () => {
    render(
      <GMEncounterControls
        sceneId={5}
        encounter={makeEncounter({
          stakes_level: 'regional',
          risk_level: 'high',
          pace_mode: 'manual',
        })}
        viewerCanGm={false}
      />,
      { wrapper: createWrapper() }
    );

    expect(screen.getByTestId('encounter-stakes-select')).toHaveTextContent('Regional');
    expect(screen.getByTestId('encounter-risk-select')).toHaveTextContent('High');
    expect(screen.getByTestId('encounter-pace-select')).toHaveTextContent('Manual');
  });

  it('fires the settings mutation when stakes changes', async () => {
    const user = userEvent.setup({ pointerEventsCheck: 0 });
    render(<GMEncounterControls sceneId={5} encounter={makeEncounter()} viewerCanGm={false} />, {
      wrapper: createWrapper(),
    });

    await user.click(screen.getByTestId('encounter-stakes-select'));
    await user.click(await screen.findByRole('option', { name: 'World' }));

    expect(mockUpdateSettingsMutate).toHaveBeenCalledWith(
      { stakesLevel: 'world' },
      expect.objectContaining({ onError: expect.any(Function) })
    );
  });

  it('fires the settings mutation when risk changes', async () => {
    const user = userEvent.setup({ pointerEventsCheck: 0 });
    render(<GMEncounterControls sceneId={5} encounter={makeEncounter()} viewerCanGm={false} />, {
      wrapper: createWrapper(),
    });

    await user.click(screen.getByTestId('encounter-risk-select'));
    await user.click(await screen.findByRole('option', { name: 'Lethal' }));

    expect(mockUpdateSettingsMutate).toHaveBeenCalledWith(
      { riskLevel: 'lethal' },
      expect.objectContaining({ onError: expect.any(Function) })
    );
  });

  it('fires the settings mutation when pace changes', async () => {
    const user = userEvent.setup({ pointerEventsCheck: 0 });
    render(
      <GMEncounterControls
        sceneId={5}
        encounter={makeEncounter({ pace_mode: 'manual' })}
        viewerCanGm={false}
      />,
      { wrapper: createWrapper() }
    );

    await user.click(screen.getByTestId('encounter-pace-select'));
    await user.click(await screen.findByRole('option', { name: /^Ready/ }));

    expect(mockUpdateSettingsMutate).toHaveBeenCalledWith(
      { paceMode: 'ready' },
      expect.objectContaining({ onError: expect.any(Function) })
    );
  });

  it('shows the timer input only in timed pace, and commits on blur', async () => {
    const user = userEvent.setup({ pointerEventsCheck: 0 });
    render(
      <GMEncounterControls
        sceneId={5}
        encounter={makeEncounter({ pace_mode: 'timed', pace_timer_minutes: 10 })}
        viewerCanGm={false}
      />,
      { wrapper: createWrapper() }
    );

    const timerInput = screen.getByTestId('encounter-timer-input');
    await user.clear(timerInput);
    await user.type(timerInput, '20');
    await user.tab();

    expect(mockUpdateSettingsMutate).toHaveBeenCalledWith(
      { paceTimerMinutes: 20 },
      expect.objectContaining({ onError: expect.any(Function) })
    );
  });

  it('hides the timer input outside timed pace', () => {
    render(
      <GMEncounterControls
        sceneId={5}
        encounter={makeEncounter({ pace_mode: 'manual' })}
        viewerCanGm={false}
      />,
      { wrapper: createWrapper() }
    );

    expect(screen.queryByTestId('encounter-timer-input')).not.toBeInTheDocument();
  });
});
