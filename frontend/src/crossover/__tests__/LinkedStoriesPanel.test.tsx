/**
 * LinkedStoriesPanel tests (#2075).
 *
 * Tests: renders nothing when no episode scenes, renders when data present.
 */

import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { vi } from 'vitest';
import { LinkedStoriesPanel } from '../components/LinkedStoriesPanel';
import type { EpisodeScene } from '../types';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('../queries', () => ({
  useEpisodeScenesForScene: vi.fn(),
  getStakesSummary: vi.fn(),
  crossoverKeys: {
    all: ['crossover'],
    episodeScenes: (id: number) => ['crossover', 'episode-scenes', id],
  },
}));

import { useEpisodeScenesForScene } from '../queries';

const mockUseEpisodeScenesForScene = vi.mocked(useEpisodeScenesForScene);

function renderPanel(sceneId: number) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <LinkedStoriesPanel sceneId={sceneId} />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('LinkedStoriesPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders nothing when no episode scenes (non-crossover scene)', () => {
    mockUseEpisodeScenesForScene.mockReturnValue({
      data: { count: 0, next: null, previous: null, results: [] },
      isLoading: false,
    } as never);
    renderPanel(42);
    expect(screen.queryByTestId('linked-stories-panel')).toBeNull();
  });

  it('renders nothing while loading', () => {
    mockUseEpisodeScenesForScene.mockReturnValue({
      data: undefined,
      isLoading: true,
    } as never);
    renderPanel(42);
    expect(screen.queryByTestId('linked-stories-panel')).toBeNull();
  });

  it('renders the panel when episode scenes exist', () => {
    const mockEpisodeScenes: EpisodeScene[] = [
      {
        id: 1,
        episode: 'Story Alpha - Ep 1: The Beginning',
        scene: 'Scene 1',
        episode_id: 100,
        scene_id: 42,
        order: 0,
      },
    ];
    mockUseEpisodeScenesForScene.mockReturnValue({
      data: { count: 1, next: null, previous: null, results: mockEpisodeScenes },
      isLoading: false,
    } as never);
    renderPanel(42);
    expect(screen.getByTestId('linked-stories-panel')).toBeTruthy();
    expect(screen.getByText('Linked Stories')).toBeTruthy();
  });
});
