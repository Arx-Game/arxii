/**
 * MuteSettingsPage Tests
 *
 * Tests listing muted stories, the Unmute button, and the empty state.
 */

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { vi } from 'vitest';
import type { ReactNode } from 'react';
import { MuteSettingsPage } from '../pages/MuteSettingsPage';

vi.mock('../queries', () => ({
  useStoryMutes: vi.fn(),
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
  unmuteMutate = vi.fn(),
}: {
  mutes?: Array<{ id: number; story: number; muted_at: string }>;
  unmuteMutate?: ReturnType<typeof vi.fn>;
} = {}) {
  vi.mocked(queries.useStoryMutes).mockReturnValue({
    data: { count: mutes.length, next: null, previous: null, results: mutes },
    isLoading: false,
    isSuccess: true,
    error: null,
  } as unknown as ReturnType<typeof queries.useStoryMutes>);

  vi.mocked(queries.useUnmuteStory).mockReturnValue(
    makeMutationIdle(unmuteMutate) as unknown as ReturnType<typeof queries.useUnmuteStory>
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('MuteSettingsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders page heading', () => {
    setupMocks();
    render(<MuteSettingsPage />, { wrapper: createWrapper() });
    expect(screen.getByRole('heading', { name: 'Muted Stories' })).toBeInTheDocument();
  });

  it('renders empty state when no mutes exist', () => {
    setupMocks({ mutes: [] });
    render(<MuteSettingsPage />, { wrapper: createWrapper() });

    expect(screen.getByTestId('mute-empty-state')).toBeInTheDocument();
    expect(screen.getByText(/You haven't muted any stories/i)).toBeInTheDocument();
  });

  it('renders loading skeletons during fetch', () => {
    vi.mocked(queries.useStoryMutes).mockReturnValue({
      data: undefined,
      isLoading: true,
      isSuccess: false,
      error: null,
    } as unknown as ReturnType<typeof queries.useStoryMutes>);

    vi.mocked(queries.useUnmuteStory).mockReturnValue(
      makeMutationIdle() as unknown as ReturnType<typeof queries.useUnmuteStory>
    );

    const { container } = render(<MuteSettingsPage />, { wrapper: createWrapper() });
    expect(container.querySelectorAll('[data-testid="mute-row-skeleton"]').length).toBeGreaterThan(
      0
    );
  });

  it('renders a row for each muted story', () => {
    setupMocks({
      mutes: [
        { id: 1, story: 10, muted_at: '2026-04-01T00:00:00Z' },
        { id: 2, story: 20, muted_at: '2026-04-02T00:00:00Z' },
      ],
    });
    render(<MuteSettingsPage />, { wrapper: createWrapper() });

    const rows = screen.getAllByTestId('mute-row');
    expect(rows).toHaveLength(2);
    expect(screen.getByText('Story #10')).toBeInTheDocument();
    expect(screen.getByText('Story #20')).toBeInTheDocument();
  });

  it('renders Unmute button for each muted story', () => {
    setupMocks({
      mutes: [{ id: 1, story: 10, muted_at: '2026-04-01T00:00:00Z' }],
    });
    render(<MuteSettingsPage />, { wrapper: createWrapper() });
    expect(screen.getByRole('button', { name: 'Unmute' })).toBeInTheDocument();
  });

  it('calls unmuteStory mutation when Unmute is clicked', async () => {
    const user = userEvent.setup();
    const unmuteMutate = vi.fn();
    setupMocks({
      mutes: [{ id: 5, story: 42, muted_at: '2026-04-01T00:00:00Z' }],
      unmuteMutate,
    });

    render(<MuteSettingsPage />, { wrapper: createWrapper() });
    await user.click(screen.getByRole('button', { name: 'Unmute' }));

    expect(unmuteMutate).toHaveBeenCalledWith(5);
  });

  it('does not render empty state when mutes exist', () => {
    setupMocks({
      mutes: [{ id: 1, story: 10, muted_at: '2026-04-01T00:00:00Z' }],
    });
    render(<MuteSettingsPage />, { wrapper: createWrapper() });
    expect(screen.queryByTestId('mute-empty-state')).not.toBeInTheDocument();
  });
});
