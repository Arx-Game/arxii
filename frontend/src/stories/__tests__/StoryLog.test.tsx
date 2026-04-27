/**
 * StoryLog Tests
 *
 * Tests timeline rendering of beat and episode entries, empty state,
 * and internal description reveal toggle.
 */

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { vi } from 'vitest';
import type { ReactNode } from 'react';
import { StoryLog } from '../components/StoryLog';
import type { StoryLogResponse } from '../types';

vi.mock('../queries', () => ({
  useStoryLog: vi.fn(),
}));

import * as queries from '../queries';

// ---------------------------------------------------------------------------
// Wrapper
// ---------------------------------------------------------------------------

function createWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  };
}

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const beatEntry: StoryLogResponse['entries'][number] = {
  entry_type: 'beat_completion',
  beat_id: 100,
  episode_id: 10,
  recorded_at: '2026-04-19T12:00:00Z',
  outcome: 'success',
  visibility: 'visible',
  player_hint: null,
  player_resolution_text: 'The sword was found.',
  internal_description: null,
  gm_notes: null,
};

const episodeEntry: StoryLogResponse['entries'][number] = {
  entry_type: 'episode_resolution',
  episode_id: 10,
  episode_title: 'The Journey',
  resolved_at: '2026-04-19T15:00:00Z',
  transition_id: 7,
  target_episode_id: 11,
  target_episode_title: 'The Destination',
  connection_type: 'sequential',
  connection_summary: 'The path leads onward.',
  internal_notes: null,
};

const beatEntryWithInternal: StoryLogResponse['entries'][number] = {
  entry_type: 'beat_completion',
  beat_id: 200,
  episode_id: 10,
  recorded_at: '2026-04-18T10:00:00Z',
  outcome: 'failure',
  visibility: 'visible',
  player_hint: null,
  player_resolution_text: null,
  internal_description: 'The GM was unsatisfied with the roll.',
  gm_notes: 'House rule applied.',
};

function setupMock(data: StoryLogResponse, loading = false) {
  vi.mocked(queries.useStoryLog).mockReturnValue({
    data: loading ? undefined : data,
    isLoading: loading,
    isSuccess: !loading,
    error: null,
  } as unknown as ReturnType<typeof queries.useStoryLog>);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('StoryLog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders empty state when entries array is empty', () => {
    setupMock({ entries: [] });
    render(<StoryLog storyId={1} />, { wrapper: createWrapper() });

    expect(
      screen.getByText(/Story log is empty\. Beats will appear here as they resolve\./i)
    ).toBeInTheDocument();
  });

  it('renders a list of mixed entries', () => {
    setupMock({ entries: [beatEntry, episodeEntry] });
    render(<StoryLog storyId={1} />, { wrapper: createWrapper() });

    // Beat entry shows resolution text
    expect(screen.getByText('The sword was found.')).toBeInTheDocument();

    // Episode entry shows episode title
    expect(screen.getByText('Episode resolved: The Journey')).toBeInTheDocument();
  });

  it('BeatCompletion entry shows the right outcome pill', () => {
    setupMock({ entries: [beatEntry] });
    render(<StoryLog storyId={1} />, { wrapper: createWrapper() });

    expect(screen.getByText('Success')).toBeInTheDocument();
  });

  it('EpisodeResolution entry shows the transition info', () => {
    setupMock({ entries: [episodeEntry] });
    render(<StoryLog storyId={1} />, { wrapper: createWrapper() });

    expect(screen.getByText('sequential: The path leads onward.')).toBeInTheDocument();
    expect(screen.getByText('Next: The Destination')).toBeInTheDocument();
  });

  it('shows loading skeletons while loading', () => {
    setupMock({ entries: [] }, true);
    const { container } = render(<StoryLog storyId={1} />, { wrapper: createWrapper() });

    expect(container.querySelectorAll('.animate-pulse').length).toBeGreaterThan(0);
  });

  it('shows internal description reveal toggle when internal_description is non-null', async () => {
    const user = userEvent.setup();
    setupMock({ entries: [beatEntryWithInternal] });
    render(<StoryLog storyId={1} />, { wrapper: createWrapper() });

    // Toggle should be present
    const toggleBtn = screen.getByRole('button', { name: /show internal notes/i });
    expect(toggleBtn).toBeInTheDocument();

    // Click reveals the internal description
    await user.click(toggleBtn);

    await waitFor(() => {
      expect(screen.getByText('The GM was unsatisfied with the roll.')).toBeInTheDocument();
    });

    // Clicking again collapses
    await user.click(screen.getByRole('button', { name: /hide internal notes/i }));

    await waitFor(() => {
      expect(screen.queryByText('The GM was unsatisfied with the roll.')).not.toBeInTheDocument();
    });
  });

  it('does not show reveal toggle when internal_description is null', () => {
    setupMock({ entries: [beatEntry] });
    render(<StoryLog storyId={1} />, { wrapper: createWrapper() });

    expect(screen.queryByRole('button', { name: /show internal notes/i })).not.toBeInTheDocument();
  });

  it('renders failure outcome badge for failed beats', () => {
    const failedBeat = { ...beatEntry, outcome: 'failure' as const };
    setupMock({ entries: [failedBeat] });
    render(<StoryLog storyId={1} />, { wrapper: createWrapper() });

    expect(screen.getByText('Failure')).toBeInTheDocument();
  });
});
