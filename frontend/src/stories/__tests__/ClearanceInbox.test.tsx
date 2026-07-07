/**
 * ClearanceInbox tests (#2001 Task 8) — incoming/outgoing split for
 * non-staff GMs, and the staff-only escalation queue.
 *
 * See ClearanceInbox.tsx's own docstring for the split logic under test:
 * a clearance is "incoming" iff its protected_subject id appears in the
 * caller's own /api/protected-subjects/ list; everything else is "outgoing".
 * Staff see only the escalation queue.
 */

import { screen } from '@testing-library/react';
import { vi } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { ClearanceInbox } from '../components/ClearanceInbox';
import type { CustodyClearance, ProtectedSubject } from '../types';

vi.mock('../components/RequestClearanceDialog', () => ({
  RequestClearanceDialog: () => <button>Request Clearance</button>,
}));
vi.mock('../components/GrantClearanceDialog', () => ({
  GrantClearanceDialog: ({ clearanceId }: { clearanceId: number }) => (
    <button>Grant #{clearanceId}</button>
  ),
}));
vi.mock('../components/DenyClearanceDialog', () => ({
  DenyClearanceDialog: ({ clearanceId }: { clearanceId: number }) => (
    <button>Deny #{clearanceId}</button>
  ),
}));
vi.mock('../components/EscalateClearanceButton', () => ({
  EscalateClearanceButton: ({ clearanceId }: { clearanceId: number }) => (
    <button>Escalate #{clearanceId}</button>
  ),
}));
vi.mock('../components/RevokeClearanceButton', () => ({
  RevokeClearanceButton: ({ clearanceId }: { clearanceId: number }) => (
    <button>Revoke #{clearanceId}</button>
  ),
}));
vi.mock('../components/ResolveClearanceDialog', () => ({
  ResolveClearanceDialog: ({ clearanceId }: { clearanceId: number }) => (
    <button>Resolve #{clearanceId}</button>
  ),
}));

vi.mock('../queries', () => ({
  useProtectedSubjects: vi.fn(),
  useCustodyClearances: vi.fn(),
}));

const accountState: { is_staff: boolean } = { is_staff: false };
vi.mock('@/store/hooks', () => ({
  useAccount: vi.fn(() => ({
    id: 1,
    username: 'testuser',
    is_staff: accountState.is_staff,
    available_characters: [],
  })),
}));

import * as queries from '../queries';

const myProtectedSubject: ProtectedSubject = {
  id: 3,
  story: 1,
  subject_kind: 'npc_fate',
  subject_sheet: 42,
  subject_item: null,
  subject_society: null,
  subject_organization: null,
  subject_label: '',
  is_active: true,
  notes: '',
  created_at: '2026-01-01T00:00:00Z',
};

function makeClearance(overrides: Partial<CustodyClearance>): CustodyClearance {
  return {
    id: 1,
    protected_subject: 3,
    requested_by: 5,
    requesting_story: null,
    requesting_beat: null,
    scope: 'appear',
    status: 'pending',
    granted_by: null,
    staff_resolver: null,
    message: '',
    response_note: '',
    revoked_at: null,
    created_at: '2026-04-19T00:00:00Z',
    resolved_at: null,
    ...overrides,
  };
}

function mockData({
  subjects = [myProtectedSubject],
  clearances = [],
}: {
  subjects?: ProtectedSubject[];
  clearances?: CustodyClearance[];
} = {}) {
  vi.mocked(queries.useProtectedSubjects).mockReturnValue({
    data: { count: subjects.length, next: null, previous: null, results: subjects },
    isLoading: false,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  } as any);
  vi.mocked(queries.useCustodyClearances).mockReturnValue({
    data: { count: clearances.length, next: null, previous: null, results: clearances },
    isLoading: false,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  } as any);
}

describe('ClearanceInbox', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    accountState.is_staff = false;
  });

  it('buckets a clearance whose protected_subject is mine as incoming', () => {
    mockData({ clearances: [makeClearance({ id: 1, protected_subject: 3, status: 'pending' })] });
    renderWithProviders(<ClearanceInbox />);

    expect(screen.getByTestId('incoming-clearances-section')).toHaveTextContent('Incoming (1)');
    expect(screen.getByTestId('outgoing-clearances-section')).toHaveTextContent('Outgoing (0)');
  });

  it('buckets a clearance on a subject that is not mine as outgoing', () => {
    mockData({
      clearances: [makeClearance({ id: 2, protected_subject: 999, status: 'denied' })],
    });
    renderWithProviders(<ClearanceInbox />);

    expect(screen.getByTestId('incoming-clearances-section')).toHaveTextContent('Incoming (0)');
    expect(screen.getByTestId('outgoing-clearances-section')).toHaveTextContent('Outgoing (1)');
  });

  it('shows Grant/Deny for a pending incoming clearance, not for outgoing', () => {
    mockData({
      clearances: [
        makeClearance({ id: 1, protected_subject: 3, status: 'pending' }),
        makeClearance({ id: 2, protected_subject: 999, status: 'pending' }),
      ],
    });
    renderWithProviders(<ClearanceInbox />);

    expect(screen.getByText('Grant #1')).toBeInTheDocument();
    expect(screen.getByText('Deny #1')).toBeInTheDocument();
    expect(screen.queryByText('Grant #2')).not.toBeInTheDocument();
    expect(screen.queryByText('Deny #2')).not.toBeInTheDocument();
  });

  it('shows Revoke for a granted incoming clearance', () => {
    mockData({
      clearances: [makeClearance({ id: 1, protected_subject: 3, status: 'granted' })],
    });
    renderWithProviders(<ClearanceInbox />);

    expect(screen.getByText('Revoke #1')).toBeInTheDocument();
  });

  it('hides Revoke for a granted outgoing clearance (not staff)', () => {
    mockData({
      clearances: [makeClearance({ id: 2, protected_subject: 999, status: 'granted' })],
    });
    renderWithProviders(<ClearanceInbox />);

    expect(screen.queryByText('Revoke #2')).not.toBeInTheDocument();
  });

  it('shows Escalate for a denied outgoing clearance, not for incoming', () => {
    mockData({
      clearances: [
        makeClearance({ id: 1, protected_subject: 3, status: 'denied' }),
        makeClearance({ id: 2, protected_subject: 999, status: 'denied' }),
      ],
    });
    renderWithProviders(<ClearanceInbox />);

    expect(screen.queryByText('Escalate #1')).not.toBeInTheDocument();
    expect(screen.getByText('Escalate #2')).toBeInTheDocument();
  });

  it('shows only the staff escalation queue for a staff account', () => {
    accountState.is_staff = true;
    mockData({
      clearances: [makeClearance({ id: 4, protected_subject: 3, status: 'escalated' })],
    });
    renderWithProviders(<ClearanceInbox />);

    expect(screen.getByTestId('staff-escalation-section')).toBeInTheDocument();
    expect(screen.queryByTestId('incoming-clearances-section')).not.toBeInTheDocument();
    expect(screen.queryByTestId('outgoing-clearances-section')).not.toBeInTheDocument();
    expect(screen.getByText('Resolve #4')).toBeInTheDocument();
  });
});
