/**
 * MyActiveStoriesPage Tests
 *
 * Tests rendering of story sections, filter chips, empty states, and StoryCard.
 */

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { vi } from 'vitest';
import type { ReactNode } from 'react';
import { MyActiveStoriesPage } from '../pages/MyActiveStoriesPage';
import type { MyActiveStoriesResponse } from '../types';

vi.mock('../queries', () => ({
  useMyActiveStories: vi.fn(),
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
// Fixture data
// ---------------------------------------------------------------------------

const emptyResponse: MyActiveStoriesResponse = {
  character_stories: [],
  group_stories: [],
  global_stories: [],
};

const fullResponse: MyActiveStoriesResponse = {
  character_stories: [
    {
      story_id: 1,
      story_title: 'A Knights Tale',
      scope: 'character',
      current_episode_id: 10,
      current_episode_title: 'The Journey',
      chapter_title: 'Chapter One',
      status: 'waiting_on_beats',
      status_label: 'Waiting on beats',
      chapter_order: 1,
      episode_order: 2,
      open_session_request_id: null,
      scheduled_event_id: null,
      scheduled_real_time: null,
    },
  ],
  group_stories: [
    {
      story_id: 2,
      story_title: 'The Siege of Iron Keep',
      scope: 'group',
      current_episode_id: 20,
      current_episode_title: 'Final Push',
      chapter_title: 'Chapter Two',
      status: 'ready_to_resolve',
      status_label: 'Ready to resolve',
      chapter_order: 2,
      episode_order: 1,
      open_session_request_id: null,
      scheduled_event_id: null,
      scheduled_real_time: null,
    },
  ],
  global_stories: [
    {
      story_id: 3,
      story_title: 'The Ancient Prophecy',
      scope: 'global',
      current_episode_id: 30,
      current_episode_title: 'The Awakening',
      chapter_title: 'Chapter Three',
      status: 'scheduled',
      status_label: 'Scheduled',
      chapter_order: 3,
      episode_order: 1,
      open_session_request_id: null,
      scheduled_event_id: null,
      scheduled_real_time: null,
    },
  ],
};

function setupMock(response: MyActiveStoriesResponse, loading = false) {
  vi.mocked(queries.useMyActiveStories).mockReturnValue({
    data: loading ? undefined : response,
    isLoading: loading,
    isSuccess: !loading,
    error: null,
  } as unknown as ReturnType<typeof queries.useMyActiveStories>);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('MyActiveStoriesPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders all three scope sections under the All filter', () => {
    setupMock(fullResponse);
    render(<MyActiveStoriesPage />, { wrapper: createWrapper() });

    expect(screen.getByText('Personal Stories')).toBeInTheDocument();
    expect(screen.getByText('Group Stories')).toBeInTheDocument();
    expect(screen.getByText('Global Stories')).toBeInTheDocument();
  });

  it('renders story titles in cards', () => {
    setupMock(fullResponse);
    render(<MyActiveStoriesPage />, { wrapper: createWrapper() });

    expect(screen.getByText('A Knights Tale')).toBeInTheDocument();
    expect(screen.getByText('The Siege of Iron Keep')).toBeInTheDocument();
    expect(screen.getByText('The Ancient Prophecy')).toBeInTheDocument();
  });

  it('renders scope badges on each card', () => {
    setupMock(fullResponse);
    render(<MyActiveStoriesPage />, { wrapper: createWrapper() });

    // Filter chips and scope badges both show these labels; use getAllByText
    expect(screen.getAllByText('Personal').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('Group').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('Global').length).toBeGreaterThanOrEqual(1);
  });

  it('filter chip switching shows only the matching scope', async () => {
    const user = userEvent.setup();
    setupMock(fullResponse);
    render(<MyActiveStoriesPage />, { wrapper: createWrapper() });

    // Click Personal filter
    await user.click(screen.getByRole('button', { name: 'Personal' }));

    expect(screen.getByText('A Knights Tale')).toBeInTheDocument();
    expect(screen.queryByText('The Siege of Iron Keep')).not.toBeInTheDocument();
    expect(screen.queryByText('The Ancient Prophecy')).not.toBeInTheDocument();
  });

  it('shows group empty state when Group filter is active and no group stories', async () => {
    const user = userEvent.setup();
    setupMock(emptyResponse);
    render(<MyActiveStoriesPage />, { wrapper: createWrapper() });

    await user.click(screen.getByRole('button', { name: 'Group' }));

    expect(
      screen.getByText(
        "You're not in any group stories yet. Join a covenant or table to participate."
      )
    ).toBeInTheDocument();
  });

  it('renders empty state for All filter when no stories exist', () => {
    setupMock(emptyResponse);
    render(<MyActiveStoriesPage />, { wrapper: createWrapper() });

    expect(screen.getByText("You don't have any active stories yet.")).toBeInTheDocument();
  });

  it('renders loading skeletons during fetch', () => {
    setupMock(emptyResponse, true);
    const { container } = render(<MyActiveStoriesPage />, { wrapper: createWrapper() });

    expect(container.querySelectorAll('.animate-pulse').length).toBeGreaterThan(0);
  });

  it('renders status_label text in each card', () => {
    setupMock(fullResponse);
    render(<MyActiveStoriesPage />, { wrapper: createWrapper() });

    expect(screen.getByText('Waiting on beats')).toBeInTheDocument();
    expect(screen.getByText('Ready to resolve')).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// StoryCard unit tests (via the page)
// ---------------------------------------------------------------------------

describe('StoryCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders chapter/episode breadcrumb when available', () => {
    setupMock(fullResponse);
    render(<MyActiveStoriesPage />, { wrapper: createWrapper() });

    // "Ch 1, Ep 2" for character story
    expect(screen.getByText('Ch 1, Ep 2')).toBeInTheDocument();
  });
});
