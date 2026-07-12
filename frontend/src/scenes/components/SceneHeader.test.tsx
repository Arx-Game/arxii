import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi } from 'vitest';
import type { ReactNode } from 'react';
import { SceneHeader } from './SceneHeader';
import type { SceneDetail } from '../types';

const mockUseEncounterForScene = vi.fn();
vi.mock('@/combat/queries', () => ({
  useEncounterForScene: () => mockUseEncounterForScene(),
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
