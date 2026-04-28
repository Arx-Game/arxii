/**
 * Table Dialog Tests
 *
 * Covers: TableFormDialog, InviteToTableDialog, RemoveFromTableDialog,
 * LeaveTableDialog, ArchiveTableDialog
 *
 * Tests: open/close, form validation, mutation calls.
 */

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { vi } from 'vitest';
import type { ReactNode } from 'react';
import { TableFormDialog } from '../components/TableFormDialog';
import { RemoveFromTableDialog } from '../components/RemoveFromTableDialog';
import { LeaveTableDialog } from '../components/LeaveTableDialog';
import { ArchiveTableDialog } from '../components/ArchiveTableDialog';
import { InviteToTableDialog } from '../components/InviteToTableDialog';
import type { GMTable } from '../types';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('../queries', () => ({
  useCreateTable: vi.fn(),
  useUpdateTable: vi.fn(),
  useRemoveMembership: vi.fn(),
  useLeaveTable: vi.fn(),
  useArchiveTable: vi.fn(),
  useInviteToTable: vi.fn(),
}));

vi.mock('@/events/queries', () => ({
  searchPersonas: vi.fn(() => Promise.resolve([])),
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
    viewer_role: 'gm',
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// TableFormDialog — create mode
// ---------------------------------------------------------------------------

describe('TableFormDialog (create)', () => {
  beforeEach(() => {
    vi.mocked(queries.useCreateTable).mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    } as unknown as ReturnType<typeof queries.useCreateTable>);
    vi.mocked(queries.useUpdateTable).mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    } as unknown as ReturnType<typeof queries.useUpdateTable>);
  });

  it('opens dialog on trigger click', async () => {
    const user = userEvent.setup();
    render(
      <TableFormDialog mode="create" gmProfileId={5}>
        <button type="button">Create</button>
      </TableFormDialog>,
      { wrapper: createWrapper() }
    );

    await user.click(screen.getByRole('button', { name: /create/i }));
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByLabelText(/name/i)).toBeInTheDocument();
  });

  it('submit button disabled when name is empty', async () => {
    const user = userEvent.setup();
    render(
      <TableFormDialog mode="create" gmProfileId={5}>
        <button type="button">Create</button>
      </TableFormDialog>,
      { wrapper: createWrapper() }
    );

    await user.click(screen.getByRole('button', { name: /create/i }));

    const submit = screen.getByRole('button', { name: /create table/i });
    expect(submit).toBeDisabled();
  });

  it('calls createTable mutation on submit with valid data', async () => {
    const mutateFn = vi.fn();
    vi.mocked(queries.useCreateTable).mockReturnValue({
      mutate: mutateFn,
      isPending: false,
    } as unknown as ReturnType<typeof queries.useCreateTable>);

    const user = userEvent.setup();
    render(
      <TableFormDialog mode="create" gmProfileId={5}>
        <button type="button">Create</button>
      </TableFormDialog>,
      { wrapper: createWrapper() }
    );

    await user.click(screen.getByRole('button', { name: /create/i }));
    await user.type(screen.getByLabelText(/name/i), 'My New Table');
    await user.click(screen.getByRole('button', { name: /create table/i }));

    expect(mutateFn).toHaveBeenCalledWith(
      expect.objectContaining({ name: 'My New Table', gm: 5 }),
      expect.any(Object)
    );
  });

  it('closes dialog on cancel', async () => {
    const user = userEvent.setup();
    render(
      <TableFormDialog mode="create" gmProfileId={5}>
        <button type="button">Create</button>
      </TableFormDialog>,
      { wrapper: createWrapper() }
    );

    await user.click(screen.getByRole('button', { name: /create/i }));
    expect(screen.getByRole('dialog')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /cancel/i }));
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });
  });
});

// ---------------------------------------------------------------------------
// TableFormDialog — edit mode
// ---------------------------------------------------------------------------

describe('TableFormDialog (edit)', () => {
  beforeEach(() => {
    vi.mocked(queries.useCreateTable).mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    } as unknown as ReturnType<typeof queries.useCreateTable>);
    vi.mocked(queries.useUpdateTable).mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    } as unknown as ReturnType<typeof queries.useUpdateTable>);
  });

  it('pre-fills name from table prop', async () => {
    const user = userEvent.setup();
    const table = makeTable({ name: 'Existing Table' });
    render(
      <TableFormDialog mode="edit" table={table}>
        <button type="button">Edit</button>
      </TableFormDialog>,
      { wrapper: createWrapper() }
    );

    await user.click(screen.getByRole('button', { name: /edit/i }));

    await waitFor(() => {
      const nameInput = screen.getByLabelText(/name/i) as HTMLInputElement;
      expect(nameInput.value).toBe('Existing Table');
    });
  });
});

// ---------------------------------------------------------------------------
// RemoveFromTableDialog
// ---------------------------------------------------------------------------

describe('RemoveFromTableDialog', () => {
  it('calls removeMembership mutation on confirm', async () => {
    const mutateFn = vi.fn();
    vi.mocked(queries.useRemoveMembership).mockReturnValue({
      mutate: mutateFn,
      isPending: false,
    } as unknown as ReturnType<typeof queries.useRemoveMembership>);

    const user = userEvent.setup();
    const onOpenChange = vi.fn();
    render(
      <RemoveFromTableDialog
        tableId={1}
        tableName="Test Table"
        membershipId={42}
        personaName="Alice"
        open={true}
        onOpenChange={onOpenChange}
      />,
      { wrapper: createWrapper() }
    );

    expect(screen.getByText(/remove from table/i)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /remove$/i }));

    expect(mutateFn).toHaveBeenCalledWith({ membershipId: 42, tableId: 1 }, expect.any(Object));
  });

  it('closes on cancel', async () => {
    vi.mocked(queries.useRemoveMembership).mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    } as unknown as ReturnType<typeof queries.useRemoveMembership>);

    const user = userEvent.setup();
    const onOpenChange = vi.fn();
    render(
      <RemoveFromTableDialog
        tableId={1}
        tableName="Test Table"
        membershipId={42}
        personaName="Alice"
        open={true}
        onOpenChange={onOpenChange}
      />,
      { wrapper: createWrapper() }
    );

    await user.click(screen.getByRole('button', { name: /cancel/i }));
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });
});

// ---------------------------------------------------------------------------
// LeaveTableDialog
// ---------------------------------------------------------------------------

describe('LeaveTableDialog', () => {
  it('calls leaveTable mutation on confirm', async () => {
    const mutateFn = vi.fn();
    vi.mocked(queries.useLeaveTable).mockReturnValue({
      mutate: mutateFn,
      isPending: false,
    } as unknown as ReturnType<typeof queries.useLeaveTable>);

    const user = userEvent.setup();
    render(
      <LeaveTableDialog
        tableId={1}
        tableName="My Table"
        membershipId={7}
        open={true}
        onOpenChange={vi.fn()}
      />,
      { wrapper: createWrapper() }
    );

    await user.click(screen.getByRole('button', { name: /leave table/i }));

    expect(mutateFn).toHaveBeenCalledWith({ membershipId: 7, tableId: 1 }, expect.any(Object));
  });
});

// ---------------------------------------------------------------------------
// ArchiveTableDialog
// ---------------------------------------------------------------------------

describe('ArchiveTableDialog', () => {
  it('calls archiveTable mutation on confirm', async () => {
    const mutateFn = vi.fn();
    vi.mocked(queries.useArchiveTable).mockReturnValue({
      mutate: mutateFn,
      isPending: false,
    } as unknown as ReturnType<typeof queries.useArchiveTable>);

    const user = userEvent.setup();
    render(
      <ArchiveTableDialog tableId={99} tableName="Old Table" open={true} onOpenChange={vi.fn()} />,
      { wrapper: createWrapper() }
    );

    expect(screen.getByRole('heading', { name: /archive table/i })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /archive table/i }));

    expect(mutateFn).toHaveBeenCalledWith(99, expect.any(Object));
  });
});

// ---------------------------------------------------------------------------
// InviteToTableDialog
// ---------------------------------------------------------------------------

describe('InviteToTableDialog', () => {
  beforeEach(() => {
    vi.mocked(queries.useInviteToTable).mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    } as unknown as ReturnType<typeof queries.useInviteToTable>);
  });

  it('opens dialog on trigger click', async () => {
    const user = userEvent.setup();
    const table = makeTable();
    render(
      <InviteToTableDialog table={table}>
        <button type="button">Invite</button>
      </InviteToTableDialog>,
      { wrapper: createWrapper() }
    );

    await user.click(screen.getByRole('button', { name: /invite/i }));
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/search for a persona/i)).toBeInTheDocument();
  });

  it('submit button disabled until persona is selected', async () => {
    const user = userEvent.setup();
    const table = makeTable();
    render(
      <InviteToTableDialog table={table}>
        <button type="button">Invite</button>
      </InviteToTableDialog>,
      { wrapper: createWrapper() }
    );

    await user.click(screen.getByRole('button', { name: /invite/i }));

    const submit = screen.getByRole('button', { name: /^invite$/i });
    expect(submit).toBeDisabled();
  });
});
