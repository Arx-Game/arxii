/**
 * EpisodeDAG Tests — Task 10.2
 *
 * Covers:
 *  - Shows loading indicator while data is fetching
 *  - Shows empty state when story has no episodes
 *  - Renders a node per episode (data-testid="dag-episode-node")
 *  - Renders a frontier sink node when a transition has no target
 *  - Click on an episode node calls onEpisodeClick with the EpisodeLike
 *  - Tree / DAG tab toggle shows/hides the correct pane (via StoryAuthorPage)
 *
 * React Flow renders to a DOM element but requires ResizeObserver and a
 * few other browser APIs. Vitest's jsdom environment provides most of
 * these; we polyfill ResizeObserver with a no-op.
 */

import { render, screen, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { vi } from 'vitest';
import type { ReactNode } from 'react';
import { EpisodeDAG } from '../components/EpisodeDAG';
import type { EpisodeLike } from '../components/EpisodeFormDialog';
import type { EpisodeList, Transition } from '../types';

// ---------------------------------------------------------------------------
// ResizeObserver polyfill for jsdom
// ---------------------------------------------------------------------------

global.ResizeObserver = class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
};

// ---------------------------------------------------------------------------
// Mock queries
// ---------------------------------------------------------------------------

vi.mock('../queries', () => ({
  useEpisodeList: vi.fn(),
  useTransitionList: vi.fn(),
}));

import * as queries from '../queries';

// ---------------------------------------------------------------------------
// Wrapper
// ---------------------------------------------------------------------------

function createWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={qc}>
        <MemoryRouter>{children}</MemoryRouter>
      </QueryClientProvider>
    );
  };
}

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

// EpisodeList.chapter is a string (DRF PK/hyperlink representation)
const ep1: EpisodeList = {
  id: 10,
  title: 'The Beginning',
  order: 1,
  chapter: '5',
  is_active: true,
  scenes_count: 0,
};

const ep2: EpisodeList = {
  id: 11,
  title: 'The Middle',
  order: 2,
  chapter: '5',
  is_active: true,
  scenes_count: 0,
};

const transitionNormal: Transition = {
  id: 100,
  source_episode: 10,
  source_episode_title: 'The Beginning',
  target_episode: 11,
  target_episode_title: 'The Middle',
  mode: 'auto',
  connection_type: 'therefore',
  connection_summary: 'They advance',
  order: 1,
  created_at: '2026-01-01T00:00:00Z',
};

const transitionFrontier: Transition = {
  id: 101,
  source_episode: 11,
  source_episode_title: 'The Middle',
  target_episode: null,
  target_episode_title: null,
  mode: 'gm_choice',
  connection_type: 'but',
  connection_summary: 'Story paused',
  order: 1,
  created_at: '2026-01-01T00:00:00Z',
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function mockEpisodes(results: EpisodeList[]) {
  vi.mocked(queries.useEpisodeList).mockReturnValue({
    data: { count: results.length, results, next: null, previous: null },
    isLoading: false,
  } as unknown as ReturnType<typeof queries.useEpisodeList>);
}

function mockTransitions(results: Transition[]) {
  vi.mocked(queries.useTransitionList).mockReturnValue({
    data: { count: results.length, results, next: null, previous: null },
    isLoading: false,
  } as unknown as ReturnType<typeof queries.useTransitionList>);
}

function mockLoading() {
  vi.mocked(queries.useEpisodeList).mockReturnValue({
    data: undefined,
    isLoading: true,
  } as unknown as ReturnType<typeof queries.useEpisodeList>);
  vi.mocked(queries.useTransitionList).mockReturnValue({
    data: undefined,
    isLoading: true,
  } as unknown as ReturnType<typeof queries.useTransitionList>);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('EpisodeDAG', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows loading indicator while data is fetching', () => {
    mockLoading();
    const onEpisodeClick = vi.fn();
    render(<EpisodeDAG storyId={1} onEpisodeClick={onEpisodeClick} />, {
      wrapper: createWrapper(),
    });
    expect(screen.getByTestId('dag-loading')).toBeInTheDocument();
  });

  it('shows empty state when story has no episodes', () => {
    mockEpisodes([]);
    mockTransitions([]);
    const onEpisodeClick = vi.fn();
    render(<EpisodeDAG storyId={1} onEpisodeClick={onEpisodeClick} />, {
      wrapper: createWrapper(),
    });
    expect(screen.getByTestId('dag-empty')).toBeInTheDocument();
  });

  it('renders a node for each episode', () => {
    mockEpisodes([ep1, ep2]);
    mockTransitions([transitionNormal]);
    const onEpisodeClick = vi.fn();
    render(<EpisodeDAG storyId={1} onEpisodeClick={onEpisodeClick} />, {
      wrapper: createWrapper(),
    });
    const nodes = screen.getAllByTestId('dag-episode-node');
    expect(nodes).toHaveLength(2);
  });

  it('renders a frontier node when a transition has null target', () => {
    mockEpisodes([ep1, ep2]);
    mockTransitions([transitionNormal, transitionFrontier]);
    const onEpisodeClick = vi.fn();
    render(<EpisodeDAG storyId={1} onEpisodeClick={onEpisodeClick} />, {
      wrapper: createWrapper(),
    });
    expect(screen.getByTestId('dag-frontier-node')).toBeInTheDocument();
  });

  it('calls onEpisodeClick with EpisodeLike when a node is clicked', () => {
    mockEpisodes([ep1, ep2]);
    mockTransitions([transitionNormal]);
    const onEpisodeClick = vi.fn();
    render(<EpisodeDAG storyId={1} onEpisodeClick={onEpisodeClick} />, {
      wrapper: createWrapper(),
    });

    const nodes = screen.getAllByTestId('dag-episode-node');
    // Use fireEvent.click to avoid d3-zoom mousedown handler in jsdom
    fireEvent.click(nodes[0]);

    expect(onEpisodeClick).toHaveBeenCalledTimes(1);
    const arg: EpisodeLike = onEpisodeClick.mock.calls[0][0] as EpisodeLike;
    expect(arg.id).toBe(ep1.id);
    expect(arg.title).toBe(ep1.title);
  });

  it('does not call onEpisodeClick when frontier node is clicked', () => {
    mockEpisodes([ep1]);
    mockTransitions([transitionFrontier]);
    const onEpisodeClick = vi.fn();
    render(<EpisodeDAG storyId={1} onEpisodeClick={onEpisodeClick} />, {
      wrapper: createWrapper(),
    });

    const frontierNode = screen.getByTestId('dag-frontier-node');
    fireEvent.click(frontierNode);

    expect(onEpisodeClick).not.toHaveBeenCalled();
  });

  it('renders the DAG canvas container with correct test id', () => {
    mockEpisodes([ep1]);
    mockTransitions([]);
    const onEpisodeClick = vi.fn();
    render(<EpisodeDAG storyId={1} onEpisodeClick={onEpisodeClick} />, {
      wrapper: createWrapper(),
    });
    expect(screen.getByTestId('dag-canvas')).toBeInTheDocument();
  });

  it('passes storyId to useEpisodeList and useTransitionList', () => {
    mockEpisodes([]);
    mockTransitions([]);
    render(<EpisodeDAG storyId={42} onEpisodeClick={vi.fn()} />, { wrapper: createWrapper() });
    expect(queries.useEpisodeList).toHaveBeenCalledWith(expect.objectContaining({ story: 42 }));
    expect(queries.useTransitionList).toHaveBeenCalledWith(expect.objectContaining({ story: 42 }));
  });
});

describe('EpisodeDAG — edit mode', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders DAG canvas in read-only mode by default (no editMode prop)', () => {
    mockEpisodes([ep1, ep2]);
    mockTransitions([transitionNormal]);
    render(<EpisodeDAG storyId={1} onEpisodeClick={vi.fn()} />, {
      wrapper: createWrapper(),
    });
    // Canvas renders regardless of mode
    expect(screen.getByTestId('dag-canvas')).toBeInTheDocument();
  });

  it('renders DAG canvas in edit mode when editMode=true', () => {
    mockEpisodes([ep1, ep2]);
    mockTransitions([transitionNormal]);
    const onConnectEpisodes = vi.fn();
    render(
      <EpisodeDAG
        storyId={1}
        onEpisodeClick={vi.fn()}
        editMode={true}
        onConnectEpisodes={onConnectEpisodes}
      />,
      { wrapper: createWrapper() }
    );
    expect(screen.getByTestId('dag-canvas')).toBeInTheDocument();
  });
});
