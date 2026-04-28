/**
 * TableDetailPage Tests
 *
 * Tests: tab switching, role-aware visibility (gm sees admin actions,
 * member does not), empty states, loading state.
 */

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { Provider } from 'react-redux';
import { vi } from 'vitest';
import type { ReactNode } from 'react';
import { store } from '@/store/store';
import { TableDetailPage } from '../pages/TableDetailPage';
import type { GMTable } from '../types';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('../queries', () => ({
  useTable: vi.fn(),
  useTableMembers: vi.fn(),
  useBulletinPosts: vi.fn(() => ({
    data: { count: 0, next: null, previous: null, results: [] },
    isLoading: false,
  })),
  useCreateTable: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useUpdateTable: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useRemoveMembership: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useLeaveTable: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useArchiveTable: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useInviteToTable: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useCreateBulletinPost: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useDeleteBulletinPost: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
}));

// Mock stories queries used by TableStoryRoster and TableBulletin
vi.mock('@/stories/queries', () => ({
  useStoryList: vi.fn(() => ({
    data: { count: 0, next: null, previous: null, results: [] },
    isLoading: false,
  })),
}));

import * as queries from '../queries';

// ---------------------------------------------------------------------------
// Wrapper
// ---------------------------------------------------------------------------

function createWrapper(path = '/tables/1') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <Provider store={store}>
        <QueryClientProvider client={qc}>
          <MemoryRouter initialEntries={[path]}>
            <Routes>
              <Route path="/tables/:id" element={children} />
            </Routes>
          </MemoryRouter>
        </QueryClientProvider>
      </Provider>
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
    description: 'A test table',
    status: 'active',
    created_at: '2026-01-01T00:00:00Z',
    archived_at: null,
    member_count: 3,
    story_count: 2,
    viewer_role: 'none',
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('TableDetailPage', () => {
  it('shows loading state', () => {
    vi.mocked(queries.useTable).mockReturnValue({
      data: undefined,
      isLoading: true,
    } as unknown as ReturnType<typeof queries.useTable>);
    vi.mocked(queries.useTableMembers).mockReturnValue({
      data: undefined,
      isLoading: true,
    } as unknown as ReturnType<typeof queries.useTableMembers>);

    render(<TableDetailPage />, { wrapper: createWrapper() });

    // Loading skeletons render (animate-pulse is the Skeleton class marker)
    const skeletons = document.querySelectorAll('.animate-pulse');
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it('shows table name and GM username after load', async () => {
    const table = makeTable({
      name: 'The Thornwood',
      gm_username: 'TestGM',
      viewer_role: 'member',
    });
    vi.mocked(queries.useTable).mockReturnValue({
      data: table,
      isLoading: false,
    } as unknown as ReturnType<typeof queries.useTable>);
    vi.mocked(queries.useTableMembers).mockReturnValue({
      data: { count: 0, next: null, previous: null, results: [] },
      isLoading: false,
    } as unknown as ReturnType<typeof queries.useTableMembers>);

    render(<TableDetailPage />, { wrapper: createWrapper() });

    expect(screen.getByText('The Thornwood')).toBeInTheDocument();
    expect(screen.getByText(/TestGM/)).toBeInTheDocument();
  });

  it('shows stats strip with member and story counts', () => {
    const table = makeTable({ member_count: 5, story_count: 3, viewer_role: 'member' });
    vi.mocked(queries.useTable).mockReturnValue({
      data: table,
      isLoading: false,
    } as unknown as ReturnType<typeof queries.useTable>);
    vi.mocked(queries.useTableMembers).mockReturnValue({
      data: { count: 0, next: null, previous: null, results: [] },
      isLoading: false,
    } as unknown as ReturnType<typeof queries.useTableMembers>);

    render(<TableDetailPage />, { wrapper: createWrapper() });

    expect(screen.getByText('5')).toBeInTheDocument();
    // "Members" and "Stories" each appear in both the stats strip and tab labels
    expect(screen.getAllByText('Members').length).toBeGreaterThan(0);
    expect(screen.getByText('3')).toBeInTheDocument();
    expect(screen.getAllByText('Stories').length).toBeGreaterThan(0);
  });

  it('shows Edit / Invite / Archive buttons for GM role', () => {
    const table = makeTable({ viewer_role: 'gm' });
    vi.mocked(queries.useTable).mockReturnValue({
      data: table,
      isLoading: false,
    } as unknown as ReturnType<typeof queries.useTable>);
    vi.mocked(queries.useTableMembers).mockReturnValue({
      data: { count: 0, next: null, previous: null, results: [] },
      isLoading: false,
    } as unknown as ReturnType<typeof queries.useTableMembers>);

    render(<TableDetailPage />, { wrapper: createWrapper() });

    expect(screen.getByRole('button', { name: /edit/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /invite/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /archive/i })).toBeInTheDocument();
  });

  it('does not show admin buttons for member role', () => {
    const table = makeTable({ viewer_role: 'member' });
    vi.mocked(queries.useTable).mockReturnValue({
      data: table,
      isLoading: false,
    } as unknown as ReturnType<typeof queries.useTable>);
    vi.mocked(queries.useTableMembers).mockReturnValue({
      data: { count: 0, next: null, previous: null, results: [] },
      isLoading: false,
    } as unknown as ReturnType<typeof queries.useTableMembers>);

    render(<TableDetailPage />, { wrapper: createWrapper() });

    expect(screen.queryByRole('button', { name: /edit/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /invite/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /archive/i })).not.toBeInTheDocument();
  });

  it('shows Leave Table button for member/guest', () => {
    const table = makeTable({ viewer_role: 'member' });
    vi.mocked(queries.useTable).mockReturnValue({
      data: table,
      isLoading: false,
    } as unknown as ReturnType<typeof queries.useTable>);
    vi.mocked(queries.useTableMembers).mockReturnValue({
      data: { count: 0, next: null, previous: null, results: [] },
      isLoading: false,
    } as unknown as ReturnType<typeof queries.useTableMembers>);

    render(<TableDetailPage />, { wrapper: createWrapper() });

    expect(screen.getByRole('button', { name: /leave table/i })).toBeInTheDocument();
  });

  it('switches to Members tab', async () => {
    const user = userEvent.setup();
    const table = makeTable({ viewer_role: 'gm' });
    vi.mocked(queries.useTable).mockReturnValue({
      data: table,
      isLoading: false,
    } as unknown as ReturnType<typeof queries.useTable>);
    vi.mocked(queries.useTableMembers).mockReturnValue({
      data: { count: 0, next: null, previous: null, results: [] },
      isLoading: false,
    } as unknown as ReturnType<typeof queries.useTableMembers>);

    render(<TableDetailPage />, { wrapper: createWrapper() });

    const membersTab = screen.getByRole('tab', { name: /members/i });
    await user.click(membersTab);

    await waitFor(() => {
      expect(screen.getByText(/no active members/i)).toBeInTheDocument();
    });
  });

  it('switches to Bulletin tab and shows section selector and empty state', async () => {
    const user = userEvent.setup();
    const table = makeTable({ viewer_role: 'member' });
    vi.mocked(queries.useTable).mockReturnValue({
      data: table,
      isLoading: false,
    } as unknown as ReturnType<typeof queries.useTable>);
    vi.mocked(queries.useTableMembers).mockReturnValue({
      data: { count: 0, next: null, previous: null, results: [] },
      isLoading: false,
    } as unknown as ReturnType<typeof queries.useTableMembers>);

    render(<TableDetailPage />, { wrapper: createWrapper() });

    const bulletinTab = screen.getByRole('tab', { name: /bulletin/i });
    await user.click(bulletinTab);

    // Section selector shows Table-Wide button
    await waitFor(() => {
      expect(screen.getByRole('tab', { name: /table-wide/i })).toBeInTheDocument();
    });

    // Empty state is shown (member sees GM-authored message)
    expect(screen.getByText(/no posts in this section yet/i)).toBeInTheDocument();
  });

  it('shows New Post button for GM role on Bulletin tab', async () => {
    const user = userEvent.setup();
    const table = makeTable({ viewer_role: 'gm' });
    vi.mocked(queries.useTable).mockReturnValue({
      data: table,
      isLoading: false,
    } as unknown as ReturnType<typeof queries.useTable>);
    vi.mocked(queries.useTableMembers).mockReturnValue({
      data: { count: 0, next: null, previous: null, results: [] },
      isLoading: false,
    } as unknown as ReturnType<typeof queries.useTableMembers>);

    render(<TableDetailPage />, { wrapper: createWrapper() });

    const bulletinTab = screen.getByRole('tab', { name: /bulletin/i });
    await user.click(bulletinTab);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /\+ new post/i })).toBeInTheDocument();
    });
  });

  it('does not show New Post button for member role', async () => {
    const user = userEvent.setup();
    const table = makeTable({ viewer_role: 'member' });
    vi.mocked(queries.useTable).mockReturnValue({
      data: table,
      isLoading: false,
    } as unknown as ReturnType<typeof queries.useTable>);
    vi.mocked(queries.useTableMembers).mockReturnValue({
      data: { count: 0, next: null, previous: null, results: [] },
      isLoading: false,
    } as unknown as ReturnType<typeof queries.useTableMembers>);

    render(<TableDetailPage />, { wrapper: createWrapper() });

    const bulletinTab = screen.getByRole('tab', { name: /bulletin/i });
    await user.click(bulletinTab);

    await waitFor(() => {
      expect(screen.getByText(/no posts in this section yet/i)).toBeInTheDocument();
    });

    expect(screen.queryByRole('button', { name: /\+ new post/i })).not.toBeInTheDocument();
  });
});
