import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import type { ReactNode } from 'react';

import type { BattleParticipant, BattlePlace } from '../types';

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
  useThreatPools: vi.fn(() => ({ data: [{ id: 900, name: 'Warband' }] })),
}));

import { useDispatchPlayerAction, useThreatPools } from '@/combat/queries';
import { PlaceDetailPanel } from './PlaceDetailPanel';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>{children}</MemoryRouter>
      </QueryClientProvider>
    );
  };
}

const CHAMPION_PARTICIPANT: BattleParticipant = {
  id: 1,
  status: 'active',
  side_id: 100,
  place_id: 900,
  persona: { id: 5000, name: 'Test Persona', thumbnail_url: null, thumbnail_media_url: null },
  character_sheet_id: 501,
  is_champion: true,
  declared_this_round: false,
};

const NON_CHAMPION_PARTICIPANT: BattleParticipant = {
  ...CHAMPION_PARTICIPANT,
  is_champion: false,
};

const OPEN_PLACE: BattlePlace = {
  id: 900,
  name: 'The Ford',
  terrain_type: 'open',
  movement_cost: 1,
  x: 0,
  y: 0,
  footprint_radius: 1,
  controlled_by_id: null,
  encounter_scene_id: null,
  encounter_roster: null,
  vehicle: null,
  fortifications: [],
};

describe('PlaceDetailPanel — ChampionDuelSection (#3389 Phase 3)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockNavigate.mockClear();
    vi.mocked(useDispatchPlayerAction).mockReturnValue({
      mutateAsync: vi.fn(() => Promise.resolve()),
      isPending: false,
    } as unknown as ReturnType<typeof useDispatchPlayerAction>);
    vi.mocked(useThreatPools).mockReturnValue({
      data: [{ id: 900, name: 'Warband' }],
    } as unknown as ReturnType<typeof useThreatPools>);
  });

  it('renders nothing when the place already has an open encounter', () => {
    const place: BattlePlace = { ...OPEN_PLACE, encounter_scene_id: 42 };
    render(
      <PlaceDetailPanel
        place={place}
        sides={[]}
        units={[]}
        participants={[CHAMPION_PARTICIPANT]}
        sceneId={1}
        battleId={7}
      />,
      { wrapper: createWrapper() }
    );
    expect(screen.queryByTestId('champion-duel-section')).not.toBeInTheDocument();
  });

  it('renders nothing when the viewer is not a Champion', () => {
    render(
      <PlaceDetailPanel
        place={OPEN_PLACE}
        sides={[]}
        units={[]}
        participants={[NON_CHAMPION_PARTICIPANT]}
        sceneId={1}
        battleId={7}
      />,
      { wrapper: createWrapper() }
    );
    expect(screen.queryByTestId('champion-duel-section')).not.toBeInTheDocument();
  });

  it('renders the challenge form when the viewer is a Champion and the place has no open encounter', () => {
    render(
      <PlaceDetailPanel
        place={OPEN_PLACE}
        sides={[]}
        units={[]}
        participants={[CHAMPION_PARTICIPANT]}
        sceneId={1}
        battleId={7}
      />,
      { wrapper: createWrapper() }
    );
    expect(screen.getByTestId('champion-duel-section')).toBeInTheDocument();
  });

  it('dispatches challenge_champion_duel with battle_place_id + opponent_kwargs', async () => {
    const mockMutateAsync = vi.fn(() => Promise.resolve());
    vi.mocked(useDispatchPlayerAction).mockReturnValue({
      mutateAsync: mockMutateAsync,
      isPending: false,
    } as unknown as ReturnType<typeof useDispatchPlayerAction>);

    const user = userEvent.setup();
    render(
      <PlaceDetailPanel
        place={OPEN_PLACE}
        sides={[]}
        units={[]}
        participants={[CHAMPION_PARTICIPANT]}
        sceneId={1}
        battleId={7}
      />,
      { wrapper: createWrapper() }
    );

    await user.type(screen.getByTestId('champion-duel-name'), "Warlord's Champion");
    await user.selectOptions(screen.getByTestId('champion-duel-threat-pool'), '900');
    await user.click(screen.getByTestId('champion-duel-submit'));

    expect(mockMutateAsync).toHaveBeenCalledWith({
      ref: { backend: 'registry', registry_key: 'challenge_champion_duel' },
      kwargs: {
        battle_place_id: 900,
        opponent_kwargs: { name: "Warlord's Champion", max_health: 300, threat_pool: 900 },
      },
    });
  });

  it('sends threat_pool: null when no threat pool is picked', async () => {
    const mockMutateAsync = vi.fn(() => Promise.resolve());
    vi.mocked(useDispatchPlayerAction).mockReturnValue({
      mutateAsync: mockMutateAsync,
      isPending: false,
    } as unknown as ReturnType<typeof useDispatchPlayerAction>);

    const user = userEvent.setup();
    render(
      <PlaceDetailPanel
        place={OPEN_PLACE}
        sides={[]}
        units={[]}
        participants={[CHAMPION_PARTICIPANT]}
        sceneId={1}
        battleId={7}
      />,
      { wrapper: createWrapper() }
    );

    await user.type(screen.getByTestId('champion-duel-name'), 'Boss');
    await user.click(screen.getByTestId('champion-duel-submit'));

    expect(mockMutateAsync).toHaveBeenCalledWith({
      ref: { backend: 'registry', registry_key: 'challenge_champion_duel' },
      kwargs: {
        battle_place_id: 900,
        opponent_kwargs: { name: 'Boss', max_health: 300, threat_pool: null },
      },
    });
  });

  it('shows the server failure message on a business-rule rejection', async () => {
    const mockMutateAsync = vi.fn(() =>
      Promise.resolve({
        backend: 'registry',
        deferred: false,
        message: 'You are not a Champion.',
        success: false,
      })
    );
    vi.mocked(useDispatchPlayerAction).mockReturnValue({
      mutateAsync: mockMutateAsync,
      isPending: false,
    } as unknown as ReturnType<typeof useDispatchPlayerAction>);

    const user = userEvent.setup();
    render(
      <PlaceDetailPanel
        place={OPEN_PLACE}
        sides={[]}
        units={[]}
        participants={[CHAMPION_PARTICIPANT]}
        sceneId={1}
        battleId={7}
      />,
      { wrapper: createWrapper() }
    );

    await user.type(screen.getByTestId('champion-duel-name'), 'Boss');
    await user.click(screen.getByTestId('champion-duel-submit'));

    const feedback = await screen.findByTestId('champion-duel-feedback');
    expect(feedback).toHaveTextContent('You are not a Champion.');
    expect(feedback).toHaveClass('text-destructive');
    expect(mockNavigate).not.toHaveBeenCalled();
  });

  it('navigates to the new scene once the refetched place carries an encounter_scene_id', async () => {
    const mockMutateAsync = vi.fn(() =>
      Promise.resolve({
        backend: 'registry',
        deferred: false,
        message: 'The duel is joined!',
        success: true,
        data: { encounter_id: 55 },
      })
    );
    vi.mocked(useDispatchPlayerAction).mockReturnValue({
      mutateAsync: mockMutateAsync,
      isPending: false,
    } as unknown as ReturnType<typeof useDispatchPlayerAction>);

    const user = userEvent.setup();
    const { rerender } = render(
      <PlaceDetailPanel
        place={OPEN_PLACE}
        sides={[]}
        units={[]}
        participants={[CHAMPION_PARTICIPANT]}
        sceneId={1}
        battleId={7}
      />,
      { wrapper: createWrapper() }
    );

    await user.type(screen.getByTestId('champion-duel-name'), 'Boss');
    await user.click(screen.getByTestId('champion-duel-submit'));
    await screen.findByTestId('champion-duel-feedback');

    // Still no encounter_scene_id yet — no navigation.
    expect(mockNavigate).not.toHaveBeenCalled();

    // Simulate the invalidated battleKeys.detail refetch populating the place.
    rerender(
      <PlaceDetailPanel
        place={{ ...OPEN_PLACE, encounter_scene_id: 99 }}
        sides={[]}
        units={[]}
        participants={[CHAMPION_PARTICIPANT]}
        sceneId={1}
        battleId={7}
      />
    );

    await vi.waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/scenes/99');
    });
  });
});
