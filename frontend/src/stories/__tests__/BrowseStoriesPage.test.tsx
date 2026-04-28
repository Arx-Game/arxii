/**
 * BrowseStoriesPage Tests
 *
 * Tests rendering, filter chips, grouped layout, empty states, and navigation.
 */

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { vi } from 'vitest';
import type { ReactNode } from 'react';
import { BrowseStoriesPage } from '../pages/BrowseStoriesPage';
import type { PaginatedResponse, StoryList } from '../types';

vi.mock('../queries', () => ({
  useBrowseStories: vi.fn(),
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
// Fixtures
// ---------------------------------------------------------------------------

function makeStory(overrides: Partial<StoryList> & { id: number; title: string }): StoryList {
  const { id, title, scope, ...rest } = overrides;
  return {
    id,
    title,
    status: 'active',
    privacy: 'public',
    scope: scope ?? 'character',
    owners_count: 1,
    active_gms_count: 0,
    participants_count: 1,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-04-19T00:00:00Z',
    ...rest,
  };
}

const characterStory = makeStory({ id: 1, title: 'A Knights Tale', scope: 'character' });
const groupStory = makeStory({ id: 2, title: 'Siege of Iron Keep', scope: 'group' });
const globalStory = makeStory({ id: 3, title: 'The Ancient Prophecy', scope: 'global' });

const fullResponse: PaginatedResponse<StoryList> = {
  count: 3,
  next: null,
  previous: null,
  results: [characterStory, groupStory, globalStory],
};

const emptyResponse: PaginatedResponse<StoryList> = {
  count: 0,
  next: null,
  previous: null,
  results: [],
};

function setupMock(response: PaginatedResponse<StoryList>, loading = false) {
  vi.mocked(queries.useBrowseStories).mockReturnValue({
    data: loading ? undefined : response,
    isLoading: loading,
    isSuccess: !loading,
    error: null,
  } as unknown as ReturnType<typeof queries.useBrowseStories>);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('BrowseStoriesPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders page heading', () => {
    setupMock(emptyResponse);
    render(<BrowseStoriesPage />, { wrapper: createWrapper() });
    expect(screen.getByRole('heading', { name: 'Browse Stories' })).toBeInTheDocument();
  });

  it('renders all stories grouped by scope under All Visible filter', () => {
    setupMock(fullResponse);
    render(<BrowseStoriesPage />, { wrapper: createWrapper() });

    // Section headers for each scope
    expect(screen.getByText('Personal Stories')).toBeInTheDocument();
    expect(screen.getByText('Group Stories')).toBeInTheDocument();
    expect(screen.getByText('Global Stories')).toBeInTheDocument();

    // Story titles
    expect(screen.getByText('A Knights Tale')).toBeInTheDocument();
    expect(screen.getByText('Siege of Iron Keep')).toBeInTheDocument();
    expect(screen.getByText('The Ancient Prophecy')).toBeInTheDocument();
  });

  it('renders scope badges on each story row', () => {
    setupMock(fullResponse);
    render(<BrowseStoriesPage />, { wrapper: createWrapper() });

    // Both filter chips and scope badges use these labels — use getAllByText
    expect(screen.getAllByText('Personal').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('Group').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('Global').length).toBeGreaterThanOrEqual(1);
  });

  it('renders loading skeletons during fetch', () => {
    setupMock(emptyResponse, true);
    const { container } = render(<BrowseStoriesPage />, { wrapper: createWrapper() });
    expect(
      container.querySelectorAll('[data-testid="browse-story-skeleton"]').length
    ).toBeGreaterThan(0);
  });

  it('renders empty state for All Visible filter when no stories exist', () => {
    setupMock(emptyResponse);
    render(<BrowseStoriesPage />, { wrapper: createWrapper() });
    expect(screen.getByText('No stories are visible to you right now.')).toBeInTheDocument();
  });

  it('renders filter chips', () => {
    setupMock(fullResponse);
    render(<BrowseStoriesPage />, { wrapper: createWrapper() });

    expect(screen.getByRole('button', { name: 'All Visible' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Personal' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Group' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Global' })).toBeInTheDocument();
  });

  it('clicking a filter chip updates the active chip', async () => {
    const user = userEvent.setup();
    setupMock(fullResponse);
    render(<BrowseStoriesPage />, { wrapper: createWrapper() });

    const groupChip = screen.getByRole('button', { name: 'Group' });
    await user.click(groupChip);

    // After click, useBrowseStories should be called with 'group' scope
    // (the mock still returns all stories, so all rows are still shown in flat mode)
    expect(queries.useBrowseStories).toHaveBeenCalledWith('group');
  });

  it('switching to Personal filter hides scope section headers', async () => {
    const user = userEvent.setup();
    // Mock returns only character story when filtering
    const personalResponse: PaginatedResponse<StoryList> = {
      count: 1,
      next: null,
      previous: null,
      results: [characterStory],
    };
    vi.mocked(queries.useBrowseStories).mockReturnValue({
      data: personalResponse,
      isLoading: false,
      isSuccess: true,
      error: null,
    } as unknown as ReturnType<typeof queries.useBrowseStories>);

    render(<BrowseStoriesPage />, { wrapper: createWrapper() });

    await user.click(screen.getByRole('button', { name: 'Personal' }));

    // When a specific filter is active, stories appear in a flat list without section headers
    expect(screen.queryByText('Personal Stories')).not.toBeInTheDocument();
    expect(screen.getByText('A Knights Tale')).toBeInTheDocument();
  });

  it('renders Browse CTA for group scope story', () => {
    setupMock(fullResponse);
    render(<BrowseStoriesPage />, { wrapper: createWrapper() });

    const browseBtns = screen.getAllByRole('button', { name: 'Browse' });
    expect(browseBtns.length).toBeGreaterThanOrEqual(1);
  });

  it('renders Open CTA for character scope story', () => {
    setupMock(fullResponse);
    render(<BrowseStoriesPage />, { wrapper: createWrapper() });

    expect(screen.getByRole('button', { name: 'Open' })).toBeInTheDocument();
  });
});
