/**
 * RecruitmentTab Tests (#3268)
 *
 * Covers: invites + queue rendering from mocks, mint dialog POST payload,
 * revoke DELETE, deny requires notes and sends `{review_notes}`, and that a
 * non-GM staff viewer (account.is_gm === false) sees no action buttons.
 */

import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { configureStore } from '@reduxjs/toolkit';
import { MemoryRouter } from 'react-router-dom';
import { Provider } from 'react-redux';
import { vi } from 'vitest';
import type { ReactNode } from 'react';
import { authSlice } from '@/store/authSlice';
import { mockAccount } from '@/test/mocks/account';
import { RecruitmentTab } from './RecruitmentTab';
import type { GMQueueApplication, GMRosterInvite, GMTable } from '../types';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('../queries', () => ({
  useInvites: vi.fn(),
  useGMQueue: vi.fn(),
  useMintInvite: vi.fn(),
  useRevokeInvite: vi.fn(),
  useActionGMApplication: vi.fn(),
}));

import * as queries from '../queries';

// ---------------------------------------------------------------------------
// Wrapper
// ---------------------------------------------------------------------------

/** isGM undefined = no account at all (logged-out-shaped, matches TablesListPage convention). */
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
    viewer_role: 'gm',
    ...overrides,
  };
}

function makeInvite(overrides: Partial<GMRosterInvite> = {}): GMRosterInvite {
  return {
    id: 1,
    roster_entry: 42,
    code: 'abc123code',
    created_by: 5,
    created_at: '2026-08-01T00:00:00Z',
    expires_at: null,
    is_public: true,
    invited_email: '',
    claimed_at: null,
    claimed_by: null,
    claimed_username: null,
    ...overrides,
  };
}

function makeApplication(overrides: Partial<GMQueueApplication> = {}): GMQueueApplication {
  return {
    id: 7,
    character: 99,
    character_key: 'Alaric',
    applicant_username: 'playerOne',
    status: 'pending',
    applied_date: '2026-08-10T00:00:00Z',
    application_text: 'I would love to play Alaric.',
    ...overrides,
  };
}

function mockInvitesQuery(results: GMRosterInvite[] = []) {
  vi.mocked(queries.useInvites).mockReturnValue({
    data: { count: results.length, next: null, previous: null, results },
    isLoading: false,
  } as unknown as ReturnType<typeof queries.useInvites>);
}

function mockQueueQuery(results: GMQueueApplication[] = []) {
  vi.mocked(queries.useGMQueue).mockReturnValue({
    data: { count: results.length, next: null, previous: null, results },
    isLoading: false,
  } as unknown as ReturnType<typeof queries.useGMQueue>);
}

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------

beforeEach(() => {
  vi.mocked(queries.useMintInvite).mockReturnValue({
    mutate: vi.fn(),
    isPending: false,
  } as unknown as ReturnType<typeof queries.useMintInvite>);
  vi.mocked(queries.useRevokeInvite).mockReturnValue({
    mutate: vi.fn(),
    isPending: false,
  } as unknown as ReturnType<typeof queries.useRevokeInvite>);
  vi.mocked(queries.useActionGMApplication).mockReturnValue({
    mutate: vi.fn(),
    isPending: false,
  } as unknown as ReturnType<typeof queries.useActionGMApplication>);
});

// ---------------------------------------------------------------------------
// Rendering
// ---------------------------------------------------------------------------

describe('RecruitmentTab rendering', () => {
  it('renders invites from the mocked query', () => {
    mockInvitesQuery([makeInvite({ code: 'sunny-day-1' })]);
    mockQueueQuery([]);

    render(<RecruitmentTab table={makeTable()} />, { wrapper: createWrapper(true) });

    expect(screen.getByText('sunny-day-1')).toBeInTheDocument();
    expect(screen.getByText('Public')).toBeInTheDocument();
  });

  it('renders queue applications from the mocked query', () => {
    mockInvitesQuery([]);
    mockQueueQuery([makeApplication({ character_key: 'Bramble' })]);

    render(<RecruitmentTab table={makeTable()} />, { wrapper: createWrapper(true) });

    expect(screen.getByText('Bramble')).toBeInTheDocument();
    expect(screen.getByText(/playerOne/)).toBeInTheDocument();
  });

  it('shows the create-character callout linking to /characters/create', () => {
    mockInvitesQuery([]);
    mockQueueQuery([]);

    render(<RecruitmentTab table={makeTable()} />, { wrapper: createWrapper(true) });

    const link = screen.getByRole('link', { name: /create a character/i });
    expect(link).toHaveAttribute('href', '/characters/create');
  });
});

// ---------------------------------------------------------------------------
// Mint invite
// ---------------------------------------------------------------------------

describe('Mint invite', () => {
  it('POSTs the expected payload', async () => {
    mockInvitesQuery([]);
    mockQueueQuery([]);
    const mutateFn = vi.fn();
    vi.mocked(queries.useMintInvite).mockReturnValue({
      mutate: mutateFn,
      isPending: false,
    } as unknown as ReturnType<typeof queries.useMintInvite>);

    const user = userEvent.setup();
    render(<RecruitmentTab table={makeTable()} />, { wrapper: createWrapper(true) });

    await user.click(screen.getByRole('button', { name: /mint invite/i }));
    await user.type(screen.getByLabelText(/roster entry id/i), '42');
    await user.click(screen.getByRole('button', { name: /^mint invite$/i }));

    expect(mutateFn).toHaveBeenCalledWith(
      expect.objectContaining({ roster_entry: 42, is_public: false }),
      expect.any(Object)
    );
  });
});

// ---------------------------------------------------------------------------
// Revoke invite
// ---------------------------------------------------------------------------

describe('Revoke invite', () => {
  it('calls DELETE via useRevokeInvite on confirm', async () => {
    mockInvitesQuery([makeInvite({ id: 9, code: 'revokeme' })]);
    mockQueueQuery([]);
    const mutateFn = vi.fn();
    vi.mocked(queries.useRevokeInvite).mockReturnValue({
      mutate: mutateFn,
      isPending: false,
    } as unknown as ReturnType<typeof queries.useRevokeInvite>);

    const user = userEvent.setup();
    render(<RecruitmentTab table={makeTable()} />, { wrapper: createWrapper(true) });

    await user.click(screen.getByRole('button', { name: /revoke/i }));
    const dialog = screen.getByRole('dialog');
    await user.click(within(dialog).getByRole('button', { name: /revoke invite/i }));

    expect(mutateFn).toHaveBeenCalledWith(9, expect.any(Object));
  });

  it('does not show a Revoke button on a claimed invite', () => {
    mockInvitesQuery([makeInvite({ claimed_at: '2026-08-11T00:00:00Z', claimed_username: 'p1' })]);
    mockQueueQuery([]);

    render(<RecruitmentTab table={makeTable()} />, { wrapper: createWrapper(true) });

    expect(screen.queryByRole('button', { name: /revoke/i })).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Deny requires notes
// ---------------------------------------------------------------------------

describe('Deny application', () => {
  it('requires notes and sends {review_notes} on submit', async () => {
    mockInvitesQuery([]);
    mockQueueQuery([makeApplication({ id: 12 })]);
    const mutateFn = vi.fn();
    vi.mocked(queries.useActionGMApplication).mockReturnValue({
      mutate: mutateFn,
      isPending: false,
    } as unknown as ReturnType<typeof queries.useActionGMApplication>);

    const user = userEvent.setup();
    render(<RecruitmentTab table={makeTable()} />, { wrapper: createWrapper(true) });

    await user.click(screen.getByRole('button', { name: /^deny$/i }));

    const denyButton = screen.getByRole('button', { name: /confirm deny/i });
    expect(denyButton).toBeDisabled();

    await user.type(screen.getByLabelText(/denial notes/i), 'Not a fit for this table.');
    expect(denyButton).not.toBeDisabled();

    await user.click(denyButton);

    expect(mutateFn).toHaveBeenCalledWith(
      { id: 12, action: 'deny', reviewNotes: 'Not a fit for this table.' },
      expect.any(Object)
    );
  });

  it('approve sends no notes', async () => {
    mockInvitesQuery([]);
    mockQueueQuery([makeApplication({ id: 12 })]);
    const mutateFn = vi.fn();
    vi.mocked(queries.useActionGMApplication).mockReturnValue({
      mutate: mutateFn,
      isPending: false,
    } as unknown as ReturnType<typeof queries.useActionGMApplication>);

    const user = userEvent.setup();
    render(<RecruitmentTab table={makeTable()} />, { wrapper: createWrapper(true) });

    await user.click(screen.getByRole('button', { name: /^approve$/i }));

    expect(mutateFn).toHaveBeenCalledWith({ id: 12, action: 'approve' }, expect.any(Object));
  });
});

// ---------------------------------------------------------------------------
// Non-GM staff viewer (Decision 6)
// ---------------------------------------------------------------------------

describe('Non-GM staff viewer', () => {
  it('sees no Approve/Deny/Mint/Revoke action buttons, and a pointer link', async () => {
    mockInvitesQuery([makeInvite()]);
    mockQueueQuery([makeApplication()]);

    render(<RecruitmentTab table={makeTable({ viewer_role: 'staff' })} />, {
      wrapper: createWrapper(false),
    });

    expect(screen.queryByRole('button', { name: /^approve$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^deny$/i })).not.toBeInTheDocument();

    const link = screen.getByRole('link', { name: /review roster applications/i });
    expect(link).toHaveAttribute('href', '/staff/roster-applications');
  });

  it('hides Mint invite but still shows Revoke for a staff viewer (mint requires a GMProfile; revoke staff-bypasses)', () => {
    mockInvitesQuery([makeInvite()]);
    mockQueueQuery([]);

    render(<RecruitmentTab table={makeTable({ viewer_role: 'staff' })} />, {
      wrapper: createWrapper(false),
    });

    expect(screen.queryByRole('button', { name: /mint invite/i })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /revoke/i })).toBeInTheDocument();
  });
});
