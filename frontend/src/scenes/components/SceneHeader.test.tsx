import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import type { ReactNode } from 'react';
import { SceneHeader } from './SceneHeader';
import type { SceneDetail } from '../types';

const mockUseEncounterForScene = vi.fn();
const mockUseDispatchPlayerAction = vi.fn();
vi.mock('@/combat/queries', () => ({
  useEncounterForScene: () => mockUseEncounterForScene(),
  useDispatchPlayerAction: () => mockUseDispatchPlayerAction(),
}));

const mockUseSceneStakesSummaryQuery = vi.fn();
vi.mock('../queries', async () => {
  const actual = await vi.importActual<typeof import('../queries')>('../queries');
  return {
    ...actual,
    useSceneStakesSummaryQuery: (...args: [string, boolean]) =>
      mockUseSceneStakesSummaryQuery(...args),
  };
});

vi.mock('@/roster/queries', () => ({
  useMyRosterEntriesQuery: () => ({
    data: [{ id: 1, name: 'TestChar', character_id: 42 }],
  }),
}));

vi.mock('@/store/hooks', () => ({
  useAppSelector: (selector: (state: unknown) => unknown) =>
    selector({ game: { active: 'TestChar' }, auth: {} }),
}));

const mockUseAvailableActionsQuery = vi.fn();
vi.mock('../actionQueries', () => ({
  useAvailableActionsQuery: () => mockUseAvailableActionsQuery(),
}));

// Only the fields SceneHeader actually reads are filled in — cast covers the
// rest of SceneDetail's shape, which this test doesn't exercise.
const SCENE = {
  id: 9,
  name: 'Test Scene',
  description: '',
  is_active: true,
  is_owner: false,
  participants: [],
  active_round: null,
  clock: null,
} as unknown as SceneDetail;

function renderWrapped(scene: SceneDetail = SCENE) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>{children}</MemoryRouter>
      </QueryClientProvider>
    );
  }
  return render(<SceneHeader scene={scene} />, { wrapper: Wrapper });
}

beforeEach(() => {
  mockUseSceneStakesSummaryQuery.mockReturnValue({ data: undefined, isLoading: false });
});

describe('SceneHeader combat badge', () => {
  it('shows an In Combat badge (not a link — combat renders in-scene, #2197) when the scene has an active encounter', () => {
    mockUseEncounterForScene.mockReturnValue({ data: { id: 1 }, isLoading: false, isError: false });

    renderWrapped();

    const badge = screen.getByTestId('scene-header-combat-badge');
    expect(badge).toHaveTextContent('In Combat');
    expect(badge.closest('a')).toBeNull();
  });

  it('does not show the badge when there is no active encounter', () => {
    mockUseEncounterForScene.mockReturnValue({ data: null, isLoading: false, isError: false });

    renderWrapped();

    expect(screen.queryByTestId('scene-header-combat-badge')).not.toBeInTheDocument();
  });
});

const BASE_SCENE: SceneDetail = {
  id: 1,
  name: 'S',
  description: '',
  date_started: '',
  participants: [],
  is_active: true,
  is_owner: false,
  viewer_can_gm: false,
  positions: [],
  position_adjacency: [],
  persona_positions: [],
  active_round: null,
  declared_risk: null,
  clock: null,
} as unknown as SceneDetail;

describe('SceneHeader round-state badge (#2158)', () => {
  it('shows round number and status to every viewer, not just the GM', () => {
    mockUseEncounterForScene.mockReturnValue({ data: null, isLoading: false, isError: false });

    renderWrapped({
      ...BASE_SCENE,
      is_active: true,
      viewer_can_gm: false,
      active_round: {
        mode: 'strict',
        advance_quorum_pct: 100,
        max_actions_per_round: 1,
        per_target_repeat_lock: false,
        status: 'declaring',
        round_number: 3,
        is_danger: false,
      },
    });

    expect(screen.getByText(/round 3/i)).toBeInTheDocument();
    expect(screen.getByText(/declaring/i)).toBeInTheDocument();
  });

  it('renders nothing when there is no active round', () => {
    mockUseEncounterForScene.mockReturnValue({ data: null, isLoading: false, isError: false });

    renderWrapped({ ...BASE_SCENE, active_round: null });
    expect(screen.queryByText(/round/i)).not.toBeInTheDocument();
  });
});

/**
 * Grant GM control (#2113, fixed for #3155). `DispatchActionView` resolves
 * HTTP 200 even for a business-rule rejection (e.g. target not found) — a
 * `dispatchAction(...).then(...)` that ignores `isDispatchFailure(result)`
 * reports the rejection reason as a success and clears the input as if it
 * landed.
 */
describe('SceneHeader grant GM control (#3155)', () => {
  const GRANT_ACTION = {
    ref: { backend: 'registry' as const, registry_key: 'grant_scene_gm' },
    display_name: 'Grant GM',
  };

  function renderGrantControl(mutateAsync: ReturnType<typeof vi.fn>) {
    mockUseEncounterForScene.mockReturnValue({ data: null, isLoading: false, isError: false });
    mockUseAvailableActionsQuery.mockReturnValue({ data: { results: [GRANT_ACTION] } });
    mockUseDispatchPlayerAction.mockReturnValue({ mutateAsync, isPending: false });

    return renderWrapped({
      ...BASE_SCENE,
      is_owner: true,
      is_active: true,
    });
  }

  it('reports the server rejection reason and keeps the input on success: false', async () => {
    const user = userEvent.setup();
    const mutateAsync = vi.fn().mockResolvedValue({
      success: false,
      message: 'No character named "Nobody" is in this scene.',
    });
    renderGrantControl(mutateAsync);

    await user.type(screen.getByLabelText('Grant GM target character name'), 'Nobody');
    await user.click(screen.getByRole('button', { name: /grant gm/i }));

    expect(
      await screen.findByText('No character named "Nobody" is in this scene.')
    ).toBeInTheDocument();
    // The refused grant must not clear the input as if it landed.
    expect(screen.getByLabelText('Grant GM target character name')).toHaveValue('Nobody');
  });

  it('reports success and clears the input on success: true', async () => {
    const user = userEvent.setup();
    const mutateAsync = vi.fn().mockResolvedValue({
      success: true,
      message: 'GM status granted to Bram.',
    });
    renderGrantControl(mutateAsync);

    await user.type(screen.getByLabelText('Grant GM target character name'), 'Bram');
    await user.click(screen.getByRole('button', { name: /grant gm/i }));

    expect(await screen.findByText('GM status granted to Bram.')).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByLabelText('Grant GM target character name')).toHaveValue('');
    });
  });
});

describe('SceneHeader declared-risk badge (#3433)', () => {
  it.each([
    ['low', 'LOW stakes'],
    ['moderate', 'MODERATE stakes'],
    ['high', 'HIGH stakes'],
    ['extreme', 'EXTREME stakes'],
  ] as const)('renders "%s" stakes as "%s"', (risk, expectedText) => {
    mockUseEncounterForScene.mockReturnValue({ data: null, isLoading: false, isError: false });

    renderWrapped({ ...BASE_SCENE, declared_risk: risk });

    const badge = screen.getByTestId('scene-header-risk-badge');
    expect(badge).toHaveTextContent(expectedText);
  });

  it('renders nothing when declared_risk is null (absent or undeclared/NONE)', () => {
    mockUseEncounterForScene.mockReturnValue({ data: null, isLoading: false, isError: false });

    renderWrapped({ ...BASE_SCENE, declared_risk: null });

    expect(screen.queryByTestId('scene-header-risk-badge')).not.toBeInTheDocument();
  });
});

describe('SceneHeader stakes-summary opt-in panel (#3561)', () => {
  it('is closed by default and does not fetch the summary', () => {
    mockUseEncounterForScene.mockReturnValue({ data: null, isLoading: false, isError: false });

    renderWrapped({ ...BASE_SCENE, declared_risk: 'high' });

    expect(screen.queryByTestId('scene-header-stakes-panel')).not.toBeInTheDocument();
    expect(mockUseSceneStakesSummaryQuery).toHaveBeenCalledWith('1', false);
  });

  it('opens the panel on click and shows each stake plus the effective risk', async () => {
    const user = userEvent.setup();
    mockUseEncounterForScene.mockReturnValue({ data: null, isLoading: false, isError: false });
    mockUseSceneStakesSummaryQuery.mockReturnValue({
      data: {
        declared_risk: 'high',
        effective_risk: 'extreme',
        is_ready: true,
        stakes: [
          {
            id: 11,
            player_summary: 'A dueling scar, worn for all to see.',
            severity: 4,
            severity_label: 'Dire',
          },
        ],
      },
      isLoading: false,
    });

    renderWrapped({ ...BASE_SCENE, declared_risk: 'high' });

    await user.click(screen.getByTestId('scene-header-risk-badge'));

    const panel = await screen.findByTestId('scene-header-stakes-panel');
    expect(panel).toHaveTextContent('What is wagered');
    expect(panel).toHaveTextContent('A dueling scar, worn for all to see.');
    expect(panel).toHaveTextContent('Dire');
    expect(panel).toHaveTextContent('extreme');
    expect(mockUseSceneStakesSummaryQuery).toHaveBeenCalledWith('1', true);
  });

  it('shows a locked message when the scene runs no beat (empty stakes)', async () => {
    const user = userEvent.setup();
    mockUseEncounterForScene.mockReturnValue({ data: null, isLoading: false, isError: false });
    mockUseSceneStakesSummaryQuery.mockReturnValue({
      data: { declared_risk: null, effective_risk: null, is_ready: true, stakes: [] },
      isLoading: false,
    });

    renderWrapped({ ...BASE_SCENE, declared_risk: 'high' });

    await user.click(screen.getByTestId('scene-header-risk-badge'));

    const panel = await screen.findByTestId('scene-header-stakes-panel');
    expect(panel).toHaveTextContent('Locked while the scene runs.');
    expect(screen.queryByTestId('scene-header-stakes-list')).not.toBeInTheDocument();
  });

  it('toggles the panel closed on a second click', async () => {
    const user = userEvent.setup();
    mockUseEncounterForScene.mockReturnValue({ data: null, isLoading: false, isError: false });
    mockUseSceneStakesSummaryQuery.mockReturnValue({
      data: { declared_risk: 'high', effective_risk: 'high', is_ready: true, stakes: [] },
      isLoading: false,
    });

    renderWrapped({ ...BASE_SCENE, declared_risk: 'high' });

    const badge = screen.getByTestId('scene-header-risk-badge');
    await user.click(badge);
    expect(await screen.findByTestId('scene-header-stakes-panel')).toBeInTheDocument();

    await user.click(badge);
    expect(screen.queryByTestId('scene-header-stakes-panel')).not.toBeInTheDocument();
  });
});

describe('SceneHeader scene clock pips (#3567)', () => {
  it('shows the clock with one filled pip when the scene carries one', () => {
    mockUseEncounterForScene.mockReturnValue({ data: null, isLoading: false, isError: false });

    renderWrapped({ ...BASE_SCENE, clock: { size: 3, filled: 1 } });

    const clock = screen.getByTestId('scene-clock');
    expect(clock).toHaveAttribute('aria-label', 'Clock 1 of 3');
    expect(screen.getAllByTestId('scene-clock-pip-filled')).toHaveLength(1);
  });

  it('does not render the clock when the scene carries none', () => {
    mockUseEncounterForScene.mockReturnValue({ data: null, isLoading: false, isError: false });

    renderWrapped({ ...BASE_SCENE, clock: null });

    expect(screen.queryByTestId('scene-clock')).not.toBeInTheDocument();
  });
});
