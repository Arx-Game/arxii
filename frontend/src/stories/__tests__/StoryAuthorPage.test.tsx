/**
 * StoryAuthorPage Tests — Task 9.1
 *
 * Covers:
 *  - Sidebar lists user's stories
 *  - New Story button opens StoryFormDialog in create mode
 *  - StoryFormDialog creates story with correct payload
 *  - StoryFormDialog opens in edit mode pre-populated
 *  - Delete story fires mutation after confirm
 *  - Empty sidebar state
 *  - 403 Access Denied fallback
 *  - Loading skeleton
 *  - Selecting a story from sidebar loads main pane
 */

import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { vi } from 'vitest';
import type { ReactNode } from 'react';
import { StoryAuthorPage } from '../pages/StoryAuthorPage';
import type { Story, StoryList } from '../types';

// ---------------------------------------------------------------------------
// Mock API
// ---------------------------------------------------------------------------

vi.mock('../api', () => ({
  listStories: vi.fn(),
  getStory: vi.fn(),
  createStory: vi.fn(),
  updateStory: vi.fn(),
  deleteStory: vi.fn(),
  listChapters: vi.fn().mockResolvedValue({ count: 0, results: [], next: null, previous: null }),
  listEpisodes: vi.fn().mockResolvedValue({ count: 0, results: [], next: null, previous: null }),
  listBeats: vi.fn().mockResolvedValue({ count: 0, results: [], next: null, previous: null }),
  listTransitions: vi.fn().mockResolvedValue({ count: 0, results: [], next: null, previous: null }),
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

import * as api from '../api';
import { toast } from 'sonner';

// ---------------------------------------------------------------------------
// Wrapper
// ---------------------------------------------------------------------------

function createWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
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

const storyList: StoryList[] = [
  {
    id: 1,
    title: 'Who Am I?',
    scope: 'character',
    status: 'active',
    privacy: 'public',
    owners_count: 1,
    active_gms_count: 1,
    participants_count: 2,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  },
  {
    id: 2,
    title: 'The Guild Wars',
    scope: 'group',
    status: 'active',
    privacy: 'public',
    owners_count: 2,
    active_gms_count: 1,
    participants_count: 5,
    created_at: '2026-01-02T00:00:00Z',
    updated_at: '2026-01-02T00:00:00Z',
  },
];

const storyDetail: Story = {
  id: 1,
  title: 'Who Am I?',
  description: 'A personal identity story.',
  scope: 'character',
  status: 'active',
  privacy: 'public',
  owners: ['player1'],
  active_gms: [],
  trust_requirements: '',
  character_sheet: 1,
  chapters_count: 0,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  completed_at: null,
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function mockStoryListSuccess(stories: StoryList[]) {
  vi.mocked(api.listStories).mockResolvedValue({
    count: stories.length,
    results: stories,
    next: null,
    previous: null,
  });
}

function mockStoryListLoading() {
  vi.mocked(api.listStories).mockReturnValue(new Promise(() => {}));
}

function make403Error(): Error & { status: number } {
  const err = new Error('Forbidden') as Error & { status: number };
  err.status = 403;
  return err;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('StoryAuthorPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.listChapters).mockResolvedValue({
      count: 0,
      results: [],
      next: null,
      previous: null,
    });
  });

  it('renders the page heading', async () => {
    mockStoryListSuccess([]);
    render(<StoryAuthorPage />, { wrapper: createWrapper() });
    await waitFor(() => expect(screen.getByText('Story Author')).toBeInTheDocument());
  });

  it('renders story list in sidebar', async () => {
    mockStoryListSuccess(storyList);
    render(<StoryAuthorPage />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(screen.getByTestId('stories-sidebar-list')).toBeInTheDocument();
    });

    const items = screen.getAllByTestId('story-sidebar-item');
    expect(items).toHaveLength(2);
    expect(screen.getByText('Who Am I?')).toBeInTheDocument();
    expect(screen.getByText('The Guild Wars')).toBeInTheDocument();
  });

  it('renders empty state when no stories', async () => {
    mockStoryListSuccess([]);
    render(<StoryAuthorPage />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(screen.getByTestId('stories-sidebar-empty')).toBeInTheDocument();
    });
  });

  it('renders loading skeleton during pending state', () => {
    mockStoryListLoading();
    render(<StoryAuthorPage />, { wrapper: createWrapper() });
    expect(screen.getByTestId('author-loading')).toBeInTheDocument();
  });

  it('renders Access Denied page on 403 error', async () => {
    vi.mocked(api.listStories).mockRejectedValue(make403Error());
    render(<StoryAuthorPage />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(screen.getByText('Access Denied')).toBeInTheDocument();
    });
    expect(screen.getByText(/only accessible to Lead GMs/i)).toBeInTheDocument();
  });

  it('shows "select a story" placeholder when none selected', async () => {
    mockStoryListSuccess(storyList);
    render(<StoryAuthorPage />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(screen.getByTestId('no-story-selected')).toBeInTheDocument();
    });
  });

  it('selects story and loads main pane', async () => {
    const user = userEvent.setup();
    mockStoryListSuccess(storyList);
    vi.mocked(api.getStory).mockResolvedValue(storyDetail);

    render(<StoryAuthorPage />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(screen.getAllByTestId('story-sidebar-item')[0]).toBeInTheDocument();
    });

    await user.click(screen.getAllByTestId('story-sidebar-item')[0]);

    await waitFor(() => {
      expect(screen.getByTestId('story-main-pane')).toBeInTheDocument();
    });

    const mainPane = screen.getByTestId('story-main-pane');
    // The story heading (h2) in the main pane
    expect(within(mainPane).getByRole('heading', { name: /who am i/i })).toBeInTheDocument();
    expect(within(mainPane).getByText('A personal identity story.')).toBeInTheDocument();
  });

  it('New Story button opens create dialog', async () => {
    const user = userEvent.setup();
    mockStoryListSuccess(storyList);

    render(<StoryAuthorPage />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(screen.getByTestId('new-story-btn')).toBeInTheDocument();
    });

    await user.click(screen.getByTestId('new-story-btn'));

    const dialog = screen.getByRole('dialog');
    expect(dialog).toBeInTheDocument();
    // Dialog title should say "Create Story" (as the heading element)
    expect(screen.getByRole('heading', { name: 'Create Story' })).toBeInTheDocument();
  });

  it('StoryFormDialog submits create payload correctly', async () => {
    const user = userEvent.setup();
    mockStoryListSuccess([]);
    vi.mocked(api.createStory).mockResolvedValue({ ...storyDetail, id: 10, title: 'New Story' });

    render(<StoryAuthorPage />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(screen.getByTestId('new-story-btn')).toBeInTheDocument();
    });

    await user.click(screen.getByTestId('new-story-btn'));

    const titleInput = screen.getByLabelText(/title/i);
    await user.type(titleInput, 'New Story');

    await user.click(screen.getByRole('button', { name: /create story/i }));

    await waitFor(() => {
      expect(api.createStory).toHaveBeenCalledWith(
        expect.objectContaining({ title: 'New Story', scope: 'character' })
      );
    });

    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith('Story created');
    });
  });

  it('Edit Story button opens edit dialog pre-populated', async () => {
    const user = userEvent.setup();
    mockStoryListSuccess(storyList);
    vi.mocked(api.getStory).mockResolvedValue(storyDetail);

    render(<StoryAuthorPage />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(screen.getAllByTestId('story-sidebar-item')[0]).toBeInTheDocument();
    });

    await user.click(screen.getAllByTestId('story-sidebar-item')[0]);

    await waitFor(() => {
      expect(screen.getByTestId('edit-story-btn')).toBeInTheDocument();
    });

    await user.click(screen.getByTestId('edit-story-btn'));

    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByText('Edit Story')).toBeInTheDocument();

    // Title should be pre-populated
    const titleInput = screen.getByLabelText(/title/i);
    expect((titleInput as HTMLInputElement).value).toBe('Who Am I?');
  });

  it('Delete story fires mutation after confirm', async () => {
    const user = userEvent.setup();
    mockStoryListSuccess(storyList);
    vi.mocked(api.getStory).mockResolvedValue(storyDetail);
    vi.mocked(api.deleteStory).mockResolvedValue(undefined);

    render(<StoryAuthorPage />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(screen.getAllByTestId('story-sidebar-item')[0]).toBeInTheDocument();
    });

    await user.click(screen.getAllByTestId('story-sidebar-item')[0]);

    await waitFor(() => {
      expect(screen.getByTestId('delete-story-btn')).toBeInTheDocument();
    });

    await user.click(screen.getByTestId('delete-story-btn'));

    // Confirm dialog should appear
    await waitFor(() => {
      expect(screen.getByRole('alertdialog')).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /delete story/i }));

    await waitFor(() => {
      expect(api.deleteStory).toHaveBeenCalledWith(1);
    });

    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith('Story deleted');
    });
  });

  it('shows Tree tab by default and DAG tab when toggled', async () => {
    const user = userEvent.setup();
    mockStoryListSuccess(storyList);
    vi.mocked(api.getStory).mockResolvedValue(storyDetail);

    render(<StoryAuthorPage />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(screen.getAllByTestId('story-sidebar-item')[0]).toBeInTheDocument();
    });
    await user.click(screen.getAllByTestId('story-sidebar-item')[0]);

    await waitFor(() => {
      expect(screen.getByTestId('author-view-tabs')).toBeInTheDocument();
    });

    // Tree tab is selected by default — tree is visible
    expect(screen.getByTestId('tab-tree')).toBeInTheDocument();
    expect(screen.getByTestId('tab-dag')).toBeInTheDocument();
    expect(screen.getByTestId('story-author-tree')).toBeInTheDocument();

    // Switch to DAG tab
    await user.click(screen.getByTestId('tab-dag'));

    // DAG canvas or empty/loading state should be present
    await waitFor(() => {
      const dagCanvas = document.querySelector('[data-testid^="dag-"]');
      expect(dagCanvas).toBeInTheDocument();
    });
  });
});
