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

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockEpisodeScenesData = {
  count: 0,
  next: null,
  previous: null,
  results: [] as unknown[],
};

vi.mock('../queries', () => ({
  useEpisodeScenesForScene: vi.fn(),
  getStakesSummary: vi.fn(),
  crossoverKeys: {
    all: ['crossover'],
    episodeScenes: (id: number) => ['crossover', 'episode-scenes', id],
  },
}));

// Mock apiFetch so the beats query doesn't try to hit a real URL
vi.mock('@/evennia_replacements/api', () => ({
  apiFetch: vi.fn().mockResolvedValue({
    ok: true,
    json: () => Promise.resolve({ count: 0, next: null, previous: null, results: [] }),
  }),
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
      data: mockEpisodeScenesData,
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
    mockUseEpisodeScenesForScene.mockReturnValue({
      data: {
        count: 1,
        next: null,
        previous: null,
        results: [
          {
            id: 1,
            episode: 'Story Alpha - Ep 1: The Beginning',
            scene: 'Scene 1',
            episode_id: 100,
            scene_id: 42,
            order: 0,
          },
        ],
      },
      isLoading: false,
    } as never);
    renderPanel(42);
    expect(screen.getByTestId('linked-stories-panel')).toBeTruthy();
    expect(screen.getByText('Linked Stories')).toBeTruthy();
  });
});
