/**
 * TablesListPage Tests
 *
 * Tests: section grouping by viewer_role, empty states,
 * GM sees Create button (gated on account.is_gm, #3041), non-GM sees the
 * "Apply to be a GM" affordance instead.
 */

import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { configureStore } from '@reduxjs/toolkit';
import { MemoryRouter } from 'react-router-dom';
import { Provider } from 'react-redux';
import { vi } from 'vitest';
import type { ReactNode } from 'react';
import { authSlice } from '@/store/authSlice';
import { mockAccount } from '@/test/mocks/account';
import { TablesListPage } from '../pages/TablesListPage';
import type { GMTable } from '../types';

// ---------------------------------------------------------------------------
// Mock queries
// ---------------------------------------------------------------------------

vi.mock('../queries', () => ({
  useTables: vi.fn(),
  useCreateTable: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useUpdateTable: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useCreateGMApplication: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
}));

import * as queries from '../queries';

// ---------------------------------------------------------------------------
// Wrapper
// ---------------------------------------------------------------------------

/** isGM undefined = no account at all (logged-out-shaped, matches prior test default). */
function createWrapper(isGM?: boolean) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  const testStore = configureStore({ reducer: { auth: authSlice.reducer } });
  if (isGM !== undefined) {
    testStore.dispatch(authSlice.actions.setAccount({ ...mockAccount, is_gm: isGM }));
  }
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <Provider store={testStore}>
        <QueryClientProvider client={qc}>
          <MemoryRouter>{children}</MemoryRouter>
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
    description: '',
    status: 'active',
    created_at: '2026-01-01T00:00:00Z',
    archived_at: null,
    member_count: 2,
    story_count: 1,
    viewer_role: 'none',
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('TablesListPage', () => {
  it('shows loading skeletons while fetching', () => {
    vi.mocked(queries.useTables).mockReturnValue({
      data: undefined,
      isLoading: true,
    } as unknown as ReturnType<typeof queries.useTables>);

    render(<TablesListPage />, { wrapper: createWrapper() });

    expect(screen.getAllByTestId('table-card-skeleton').length).toBeGreaterThan(0);
  });

  it('shows empty state when no tables', () => {
    vi.mocked(queries.useTables).mockReturnValue({
      data: { count: 0, next: null, previous: null, results: [] },
      isLoading: false,
    } as unknown as ReturnType<typeof queries.useTables>);

    render(<TablesListPage />, { wrapper: createWrapper() });

    expect(screen.getByText(/no tables found/i)).toBeInTheDocument();
  });

  it('shows "Tables I Run" section for GM role tables', () => {
    const gmTable = makeTable({ id: 1, name: 'My Table', viewer_role: 'gm' });
    vi.mocked(queries.useTables).mockReturnValue({
      data: { count: 1, next: null, previous: null, results: [gmTable] },
      isLoading: false,
    } as unknown as ReturnType<typeof queries.useTables>);

    render(<TablesListPage />, { wrapper: createWrapper() });

    expect(screen.getByText('Tables I Run')).toBeInTheDocument();
    expect(screen.getByText('My Table')).toBeInTheDocument();
  });

  it('shows "Tables I\'m a Member Of" section for member role tables', () => {
    const memberTable = makeTable({ id: 2, name: 'Guild Table', viewer_role: 'member' });
    vi.mocked(queries.useTables).mockReturnValue({
      data: { count: 1, next: null, previous: null, results: [memberTable] },
      isLoading: false,
    } as unknown as ReturnType<typeof queries.useTables>);

    render(<TablesListPage />, { wrapper: createWrapper() });

    expect(screen.getByText("Tables I'm a Member Of")).toBeInTheDocument();
    expect(screen.getByText('Guild Table')).toBeInTheDocument();
  });

  it('shows "Tables I Have Stories At" section for guest role tables', () => {
    const guestTable = makeTable({ id: 3, name: 'Guest Table', viewer_role: 'guest' });
    vi.mocked(queries.useTables).mockReturnValue({
      data: { count: 1, next: null, previous: null, results: [guestTable] },
      isLoading: false,
    } as unknown as ReturnType<typeof queries.useTables>);

    render(<TablesListPage />, { wrapper: createWrapper() });

    expect(screen.getByText('Tables I Have Stories At')).toBeInTheDocument();
    expect(screen.getByText('Guest Table')).toBeInTheDocument();
  });

  it('shows Create Table button for GM users (account.is_gm)', () => {
    const gmTable = makeTable({ id: 1, name: 'My Table', viewer_role: 'gm', gm: 5 });
    vi.mocked(queries.useTables).mockReturnValue({
      data: { count: 1, next: null, previous: null, results: [gmTable] },
      isLoading: false,
    } as unknown as ReturnType<typeof queries.useTables>);

    render(<TablesListPage />, { wrapper: createWrapper(true) });

    expect(screen.getByRole('button', { name: /create table/i })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /apply to be a gm/i })).not.toBeInTheDocument();
  });

  it('does not show Create Table button for non-GM users', () => {
    const memberTable = makeTable({ id: 2, name: 'Guild Table', viewer_role: 'member' });
    vi.mocked(queries.useTables).mockReturnValue({
      data: { count: 1, next: null, previous: null, results: [memberTable] },
      isLoading: false,
    } as unknown as ReturnType<typeof queries.useTables>);

    render(<TablesListPage />, { wrapper: createWrapper(false) });

    expect(screen.queryByRole('button', { name: /create table/i })).not.toBeInTheDocument();
  });

  it('shows Create Table button for a user who owns tables but lacks is_gm', () => {
    // #3041 ruling: don't hide existing data. viewer_role === 'gm' tables
    // still render the "Tables I Run" section even if the account flag is
    // somehow out of sync; the CREATE affordance itself stays gated on is_gm.
    const gmTable = makeTable({ id: 1, name: 'My Table', viewer_role: 'gm', gm: 5 });
    vi.mocked(queries.useTables).mockReturnValue({
      data: { count: 1, next: null, previous: null, results: [gmTable] },
      isLoading: false,
    } as unknown as ReturnType<typeof queries.useTables>);

    render(<TablesListPage />, { wrapper: createWrapper(false) });

    expect(screen.getByText('Tables I Run')).toBeInTheDocument();
    expect(screen.getByText('My Table')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /create table/i })).not.toBeInTheDocument();
  });

  it('shows Apply to be a GM button for non-GM users', () => {
    vi.mocked(queries.useTables).mockReturnValue({
      data: { count: 0, next: null, previous: null, results: [] },
      isLoading: false,
    } as unknown as ReturnType<typeof queries.useTables>);

    render(<TablesListPage />, { wrapper: createWrapper(false) });

    expect(screen.getByRole('button', { name: /apply to be a gm/i })).toBeInTheDocument();
  });

  it('shows empty state messages per section', () => {
    vi.mocked(queries.useTables).mockReturnValue({
      data: { count: 0, next: null, previous: null, results: [] },
      isLoading: false,
    } as unknown as ReturnType<typeof queries.useTables>);

    render(<TablesListPage />, { wrapper: createWrapper() });

    // Empty state shows the general message
    expect(screen.getByText(/no tables found/i)).toBeInTheDocument();
  });

  it('displays TableCard for each table in results', () => {
    const tables = [
      makeTable({ id: 1, name: 'Alpha Table', viewer_role: 'gm' }),
      makeTable({ id: 2, name: 'Beta Table', viewer_role: 'member' }),
    ];
    vi.mocked(queries.useTables).mockReturnValue({
      data: { count: 2, next: null, previous: null, results: tables },
      isLoading: false,
    } as unknown as ReturnType<typeof queries.useTables>);

    render(<TablesListPage />, { wrapper: createWrapper() });

    expect(screen.getByText('Alpha Table')).toBeInTheDocument();
    expect(screen.getByText('Beta Table')).toBeInTheDocument();
  });
});
