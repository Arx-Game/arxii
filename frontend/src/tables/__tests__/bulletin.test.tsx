/**
 * Bulletin board tests
 *
 * Covers:
 *   - TableBulletin: section selector, switching, empty state, New Post button visibility
 *   - BulletinPostCard: renders post data, reply expansion toggle
 *   - CreateBulletinPostDialog: open/close, field validation, mutation call
 */

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { vi } from 'vitest';
import type { ReactNode } from 'react';
import { TableBulletin } from '../components/TableBulletin';
import { BulletinPostCard } from '../components/BulletinPostCard';
import { CreateBulletinPostDialog } from '../components/CreateBulletinPostDialog';
import type { GMTable, TableBulletinPost, TableBulletinReply } from '../types';
import type { StoryList } from '@/stories/types';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('../queries', () => ({
  useBulletinPosts: vi.fn(),
  useCreateBulletinPost: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useUpdateBulletinPost: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useDeleteBulletinPost: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useCreateBulletinReply: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useUpdateBulletinReply: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useDeleteBulletinReply: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
}));

vi.mock('@/stories/queries', () => ({
  useStoryList: vi.fn(() => ({
    data: { count: 0, next: null, previous: null, results: [] },
    isLoading: false,
  })),
}));

import * as queries from '../queries';
import * as storiesQueries from '@/stories/queries';

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
// Fixture helpers
// ---------------------------------------------------------------------------

function makeTable(overrides: Partial<GMTable> = {}): GMTable {
  return {
    id: 1,
    gm: 10,
    gm_username: 'gmUser',
    name: 'Test Table',
    description: '',
    status: 'active',
    created_at: '2026-01-01T00:00:00Z',
    archived_at: null,
    member_count: 3,
    story_count: 2,
    viewer_role: 'member',
    ...overrides,
  };
}

function makeReply(overrides: Partial<TableBulletinReply> = {}): TableBulletinReply {
  return {
    id: 1,
    post: 10,
    author_persona: 5,
    author_persona_name: 'Alice',
    body: 'A reply body',
    created_at: '2026-01-01T01:00:00Z',
    ...overrides,
  };
}

function makePost(overrides: Partial<TableBulletinPost> = {}): TableBulletinPost {
  return {
    id: 10,
    table: 1,
    story: null,
    author_persona: 3,
    author_persona_name: 'Marek',
    title: 'Test Post',
    body: 'Post body text',
    allow_replies: true,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    replies: [],
    ...overrides,
  };
}

function makeStory(id: number, title: string): StoryList {
  return {
    id,
    title,
    scope: 'group',
    status: 'active',
    privacy: 'invite_only',
    created_at: '2026-01-01T00:00:00Z',
  } as unknown as StoryList;
}

// ---------------------------------------------------------------------------
// TableBulletin tests
// ---------------------------------------------------------------------------

describe('TableBulletin', () => {
  beforeEach(() => {
    vi.mocked(queries.useBulletinPosts).mockReturnValue({
      data: { count: 0, next: null, previous: null, results: [] },
      isLoading: false,
    } as unknown as ReturnType<typeof queries.useBulletinPosts>);
  });

  it('renders Table-Wide section button', () => {
    const table = makeTable({ viewer_role: 'member' });
    render(<TableBulletin table={table} />, { wrapper: createWrapper() });

    expect(screen.getByRole('tab', { name: /table-wide/i })).toBeInTheDocument();
  });

  it('shows one section button per story', () => {
    vi.mocked(storiesQueries.useStoryList).mockReturnValue({
      data: {
        count: 2,
        next: null,
        previous: null,
        results: [makeStory(11, 'Who Am I?'), makeStory(12, 'Dark Days')],
      },
      isLoading: false,
    } as unknown as ReturnType<typeof storiesQueries.useStoryList>);

    const table = makeTable({ viewer_role: 'member' });
    render(<TableBulletin table={table} />, { wrapper: createWrapper() });

    expect(screen.getByRole('tab', { name: /table-wide/i })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /who am i\?/i })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /dark days/i })).toBeInTheDocument();
  });

  it('shows empty state when no posts', () => {
    const table = makeTable({ viewer_role: 'member' });
    render(<TableBulletin table={table} />, { wrapper: createWrapper() });

    expect(screen.getByText(/no posts in this section yet/i)).toBeInTheDocument();
  });

  it('shows New Post button for GM', () => {
    const table = makeTable({ viewer_role: 'gm' });
    render(<TableBulletin table={table} />, { wrapper: createWrapper() });

    expect(screen.getByRole('button', { name: /\+ new post/i })).toBeInTheDocument();
  });

  it('hides New Post button for member', () => {
    const table = makeTable({ viewer_role: 'member' });
    render(<TableBulletin table={table} />, { wrapper: createWrapper() });

    expect(screen.queryByRole('button', { name: /\+ new post/i })).not.toBeInTheDocument();
  });

  it('switches to a story section on click', async () => {
    const user = userEvent.setup();
    vi.mocked(storiesQueries.useStoryList).mockReturnValue({
      data: {
        count: 1,
        next: null,
        previous: null,
        results: [makeStory(11, 'Who Am I?')],
      },
      isLoading: false,
    } as unknown as ReturnType<typeof storiesQueries.useStoryList>);

    const table = makeTable({ viewer_role: 'member' });
    render(<TableBulletin table={table} />, { wrapper: createWrapper() });

    const storyTab = screen.getByRole('tab', { name: /who am i\?/i });
    await user.click(storyTab);

    // After clicking, the story tab should be selected (aria-selected=true).
    expect(storyTab).toHaveAttribute('aria-selected', 'true');
    // The Table-Wide tab should no longer be selected.
    expect(screen.getByRole('tab', { name: /table-wide/i })).toHaveAttribute(
      'aria-selected',
      'false'
    );
  });

  it('renders posts when data is returned', () => {
    vi.mocked(queries.useBulletinPosts).mockReturnValue({
      data: {
        count: 1,
        next: null,
        previous: null,
        results: [makePost({ title: 'Session Recap', body: 'Great session!' })],
      },
      isLoading: false,
    } as unknown as ReturnType<typeof queries.useBulletinPosts>);

    const table = makeTable({ viewer_role: 'member' });
    render(<TableBulletin table={table} />, { wrapper: createWrapper() });

    expect(screen.getByText('Session Recap')).toBeInTheDocument();
    expect(screen.getByText('Great session!')).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// BulletinPostCard tests
// ---------------------------------------------------------------------------

describe('BulletinPostCard', () => {
  it('renders post title and body', () => {
    const post = makePost({ title: 'My Post', body: 'Post content here' });
    render(<BulletinPostCard post={post} isGMOrStaff={false} canReply={false} />, {
      wrapper: createWrapper(),
    });

    expect(screen.getByText('My Post')).toBeInTheDocument();
    expect(screen.getByText('Post content here')).toBeInTheDocument();
  });

  it('renders author persona name', () => {
    const post = makePost({ author_persona_name: 'Marek' });
    render(<BulletinPostCard post={post} isGMOrStaff={false} canReply={false} />, {
      wrapper: createWrapper(),
    });

    expect(screen.getByText('Marek')).toBeInTheDocument();
  });

  it('shows Edit and Delete buttons for GM/staff', () => {
    const post = makePost();
    render(<BulletinPostCard post={post} isGMOrStaff={true} canReply={false} />, {
      wrapper: createWrapper(),
    });

    expect(screen.getByRole('button', { name: /^edit$/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^delete$/i })).toBeInTheDocument();
  });

  it('hides Edit and Delete buttons for non-GM/staff', () => {
    const post = makePost();
    render(<BulletinPostCard post={post} isGMOrStaff={false} canReply={false} />, {
      wrapper: createWrapper(),
    });

    expect(screen.queryByRole('button', { name: /^edit$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^delete$/i })).not.toBeInTheDocument();
  });

  it('shows reply count and first 3 replies', () => {
    const replies = [
      makeReply({ id: 1, body: 'Reply 1' }),
      makeReply({ id: 2, body: 'Reply 2' }),
      makeReply({ id: 3, body: 'Reply 3' }),
    ];
    const post = makePost({ replies });
    render(<BulletinPostCard post={post} isGMOrStaff={false} canReply={false} />, {
      wrapper: createWrapper(),
    });

    expect(screen.getByText(/3 replies/i)).toBeInTheDocument();
    expect(screen.getByText('Reply 1')).toBeInTheDocument();
    expect(screen.getByText('Reply 2')).toBeInTheDocument();
    expect(screen.getByText('Reply 3')).toBeInTheDocument();
  });

  it('collapses replies beyond 3 and shows "Show more" toggle', () => {
    const replies = [
      makeReply({ id: 1, body: 'Reply 1' }),
      makeReply({ id: 2, body: 'Reply 2' }),
      makeReply({ id: 3, body: 'Reply 3' }),
      makeReply({ id: 4, body: 'Reply 4' }),
      makeReply({ id: 5, body: 'Reply 5' }),
    ];
    const post = makePost({ replies });
    render(<BulletinPostCard post={post} isGMOrStaff={false} canReply={false} />, {
      wrapper: createWrapper(),
    });

    // Only first 3 visible; replies 4 and 5 collapsed.
    expect(screen.getByText('Reply 1')).toBeInTheDocument();
    expect(screen.queryByText('Reply 4')).not.toBeInTheDocument();
    expect(screen.getByText(/show 2 more/i)).toBeInTheDocument();
  });

  it('expands all replies when "Show more" is clicked', async () => {
    const user = userEvent.setup();
    const replies = [
      makeReply({ id: 1, body: 'Reply 1' }),
      makeReply({ id: 2, body: 'Reply 2' }),
      makeReply({ id: 3, body: 'Reply 3' }),
      makeReply({ id: 4, body: 'Reply 4' }),
    ];
    const post = makePost({ replies });
    render(<BulletinPostCard post={post} isGMOrStaff={false} canReply={false} />, {
      wrapper: createWrapper(),
    });

    await user.click(screen.getByText(/show 1 more reply/i));

    await waitFor(() => {
      expect(screen.getByText('Reply 4')).toBeInTheDocument();
    });
  });

  it('shows Reply button when canReply=true and allow_replies=true', () => {
    const post = makePost({ allow_replies: true });
    render(
      <BulletinPostCard post={post} isGMOrStaff={false} canReply={true} viewerPersonaId={7} />,
      { wrapper: createWrapper() }
    );

    expect(screen.getByRole('button', { name: /\+ reply/i })).toBeInTheDocument();
  });

  it('hides Reply button when canReply=false', () => {
    const post = makePost({ allow_replies: true });
    render(<BulletinPostCard post={post} isGMOrStaff={false} canReply={false} />, {
      wrapper: createWrapper(),
    });

    expect(screen.queryByRole('button', { name: /\+ reply/i })).not.toBeInTheDocument();
  });

  it('shows inline reply form when Reply button is clicked', async () => {
    const user = userEvent.setup();
    const post = makePost({ allow_replies: true });
    render(
      <BulletinPostCard post={post} isGMOrStaff={false} canReply={true} viewerPersonaId={7} />,
      { wrapper: createWrapper() }
    );

    await user.click(screen.getByRole('button', { name: /\+ reply/i }));

    await waitFor(() => {
      expect(screen.getByPlaceholderText(/write a reply/i)).toBeInTheDocument();
    });
  });
});

// ---------------------------------------------------------------------------
// CreateBulletinPostDialog tests
// ---------------------------------------------------------------------------

describe('CreateBulletinPostDialog', () => {
  beforeEach(() => {
    vi.mocked(queries.useCreateBulletinPost).mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    } as unknown as ReturnType<typeof queries.useCreateBulletinPost>);
  });

  it('opens dialog on trigger click', async () => {
    const user = userEvent.setup();
    render(
      <CreateBulletinPostDialog tableId={1} gmPersonaId={3} stories={[]}>
        <button type="button">New Post</button>
      </CreateBulletinPostDialog>,
      { wrapper: createWrapper() }
    );

    await user.click(screen.getByRole('button', { name: /new post/i }));
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByLabelText(/title/i)).toBeInTheDocument();
  });

  it('submit button disabled when title or body is empty', async () => {
    const user = userEvent.setup();
    render(
      <CreateBulletinPostDialog tableId={1} gmPersonaId={3} stories={[]}>
        <button type="button">New Post</button>
      </CreateBulletinPostDialog>,
      { wrapper: createWrapper() }
    );

    await user.click(screen.getByRole('button', { name: /new post/i }));

    const submit = screen.getByRole('button', { name: /create post/i });
    expect(submit).toBeDisabled();
  });

  it('closes dialog on cancel', async () => {
    const user = userEvent.setup();
    render(
      <CreateBulletinPostDialog tableId={1} gmPersonaId={3} stories={[]}>
        <button type="button">New Post</button>
      </CreateBulletinPostDialog>,
      { wrapper: createWrapper() }
    );

    await user.click(screen.getByRole('button', { name: /new post/i }));
    expect(screen.getByRole('dialog')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /cancel/i }));

    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });
  });

  it('calls createBulletinPost mutation on submit', async () => {
    const mutateFn = vi.fn();
    vi.mocked(queries.useCreateBulletinPost).mockReturnValue({
      mutate: mutateFn,
      isPending: false,
    } as unknown as ReturnType<typeof queries.useCreateBulletinPost>);

    const user = userEvent.setup();
    render(
      <CreateBulletinPostDialog tableId={1} gmPersonaId={3} stories={[]}>
        <button type="button">New Post</button>
      </CreateBulletinPostDialog>,
      { wrapper: createWrapper() }
    );

    await user.click(screen.getByRole('button', { name: /new post/i }));
    await user.type(screen.getByLabelText(/title/i), 'Session Tomorrow');
    await user.type(screen.getByLabelText(/body/i), 'We are playing at 7pm');
    await user.click(screen.getByRole('button', { name: /create post/i }));

    expect(mutateFn).toHaveBeenCalledWith(
      expect.objectContaining({
        table: 1,
        author_persona: 3,
        title: 'Session Tomorrow',
        body: 'We are playing at 7pm',
        story: null,
        allow_replies: true,
      }),
      expect.any(Object)
    );
  });

  it('renders Section combobox when stories are provided', async () => {
    const user = userEvent.setup();
    const stories = [makeStory(11, 'Who Am I?'), makeStory(12, 'The Dark Hour')];
    render(
      <CreateBulletinPostDialog tableId={1} gmPersonaId={3} stories={stories}>
        <button type="button">New Post</button>
      </CreateBulletinPostDialog>,
      { wrapper: createWrapper() }
    );

    await user.click(screen.getByRole('button', { name: /new post/i }));

    // The Section combobox should be present (Radix Select renders a combobox role).
    expect(screen.getByRole('combobox')).toBeInTheDocument();
    // Section label visible.
    expect(screen.getByLabelText(/section/i)).toBeInTheDocument();
  });
});
