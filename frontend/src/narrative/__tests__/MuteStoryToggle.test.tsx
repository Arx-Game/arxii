/**
 * MuteStoryToggle Tests
 *
 * Tests that the toggle reflects current mute state and calls the correct
 * mutation (mute vs. unmute) on click.
 */

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { vi } from 'vitest';
import type { ReactNode } from 'react';
import { MuteStoryToggle } from '../components/MuteStoryToggle';

vi.mock('../queries', () => ({
  useStoryMutes: vi.fn(),
  useMuteStory: vi.fn(),
  useUnmuteStory: vi.fn(),
}));

import * as queries from '../queries';

// ---------------------------------------------------------------------------
// Wrapper
// ---------------------------------------------------------------------------

function createWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={qc}>
        <MemoryRouter>{children}</MemoryRouter>
      </QueryClientProvider>
    );
  };
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeMutationIdle(mutateFn = vi.fn()) {
  return {
    mutate: mutateFn,
    mutateAsync: vi.fn(),
    isPending: false,
    isSuccess: false,
    isError: false,
    isIdle: true,
    error: null,
    data: undefined,
    variables: undefined,
    status: 'idle' as const,
    reset: vi.fn(),
    context: undefined,
    failureCount: 0,
    failureReason: null,
    isPaused: false,
    submittedAt: 0,
  };
}

function setupMocks({
  mutes = [],
  muteMutate = vi.fn(),
  unmuteMutate = vi.fn(),
}: {
  mutes?: Array<{ id: number; story: number; muted_at: string }>;
  muteMutate?: ReturnType<typeof vi.fn>;
  unmuteMutate?: ReturnType<typeof vi.fn>;
} = {}) {
  vi.mocked(queries.useStoryMutes).mockReturnValue({
    data: { count: mutes.length, next: null, previous: null, results: mutes },
    isLoading: false,
    isSuccess: true,
    error: null,
  } as unknown as ReturnType<typeof queries.useStoryMutes>);

  vi.mocked(queries.useMuteStory).mockReturnValue(
    makeMutationIdle(muteMutate) as unknown as ReturnType<typeof queries.useMuteStory>
  );

  vi.mocked(queries.useUnmuteStory).mockReturnValue(
    makeMutationIdle(unmuteMutate) as unknown as ReturnType<typeof queries.useUnmuteStory>
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('MuteStoryToggle', () => {
  const STORY_ID = 42;
  const MUTE_ID = 7;

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders a bell icon when story is not muted', () => {
    setupMocks({ mutes: [] });
    render(<MuteStoryToggle storyId={STORY_ID} />, { wrapper: createWrapper() });

    const toggle = screen.getByTestId('mute-story-toggle');
    expect(toggle).toBeInTheDocument();
    expect(toggle).toHaveAttribute('data-muted', 'false');
  });

  it('renders a bell-off icon when story is muted', () => {
    setupMocks({
      mutes: [{ id: MUTE_ID, story: STORY_ID, muted_at: '2026-04-19T10:00:00Z' }],
    });
    render(<MuteStoryToggle storyId={STORY_ID} />, { wrapper: createWrapper() });

    const toggle = screen.getByTestId('mute-story-toggle');
    expect(toggle).toHaveAttribute('data-muted', 'true');
  });

  it('calls muteStory mutation when not muted and clicked', async () => {
    const user = userEvent.setup();
    const muteMutate = vi.fn();
    setupMocks({ mutes: [], muteMutate });

    render(<MuteStoryToggle storyId={STORY_ID} />, { wrapper: createWrapper() });
    await user.click(screen.getByTestId('mute-story-toggle'));

    expect(muteMutate).toHaveBeenCalledWith({ story: STORY_ID });
  });

  it('calls unmuteStory mutation when muted and clicked', async () => {
    const user = userEvent.setup();
    const unmuteMutate = vi.fn();
    setupMocks({
      mutes: [{ id: MUTE_ID, story: STORY_ID, muted_at: '2026-04-19T10:00:00Z' }],
      unmuteMutate,
    });

    render(<MuteStoryToggle storyId={STORY_ID} />, { wrapper: createWrapper() });
    await user.click(screen.getByTestId('mute-story-toggle'));

    expect(unmuteMutate).toHaveBeenCalledWith(MUTE_ID);
  });

  it('does not call unmute for a different storyId mute entry', async () => {
    const user = userEvent.setup();
    const muteMutate = vi.fn();
    // Mute is for story 99, not STORY_ID
    setupMocks({
      mutes: [{ id: 99, story: 99, muted_at: '2026-04-19T10:00:00Z' }],
      muteMutate,
    });

    render(<MuteStoryToggle storyId={STORY_ID} />, { wrapper: createWrapper() });
    await user.click(screen.getByTestId('mute-story-toggle'));

    // Should call mute (not muted for this story) rather than unmute
    expect(muteMutate).toHaveBeenCalledWith({ story: STORY_ID });
  });

  it('has accessible aria-label for unmuted state', () => {
    setupMocks({ mutes: [] });
    render(<MuteStoryToggle storyId={STORY_ID} />, { wrapper: createWrapper() });
    expect(screen.getByRole('button', { name: 'Mute story updates' })).toBeInTheDocument();
  });

  it('has accessible aria-label for muted state', () => {
    setupMocks({
      mutes: [{ id: MUTE_ID, story: STORY_ID, muted_at: '2026-04-19T10:00:00Z' }],
    });
    render(<MuteStoryToggle storyId={STORY_ID} />, { wrapper: createWrapper() });
    expect(screen.getByRole('button', { name: 'Unmute story updates' })).toBeInTheDocument();
  });
});
