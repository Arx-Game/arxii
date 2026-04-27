/**
 * ApproveClaimDialog and RejectClaimDialog Tests
 *
 * Covers both dialogs in one file since they share the same fixture data
 * and parallel structure.
 *
 * Covers:
 *  - Dialog opens/closes on trigger
 *  - Submit happy path → mutation called with right payload, dialog closes, toast shown
 *  - Validation error rendering
 *  - Mutation error doesn't close the dialog
 */

import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { ApproveClaimDialog } from '../components/ApproveClaimDialog';
import { RejectClaimDialog } from '../components/RejectClaimDialog';
import type { GMQueuePendingClaim } from '../types';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('../queries', () => ({
  useApproveClaim: vi.fn(),
  useRejectClaim: vi.fn(),
}));

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

import * as queries from '../queries';
import { toast } from 'sonner';

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const mockClaim: GMQueuePendingClaim = {
  claim_id: 55,
  beat_id: 200,
  beat_internal_description: 'The villain escapes or is captured',
  story_title: 'The Long Road',
  assistant_gm_id: 7,
  requested_at: '2026-04-18T12:00:00Z',
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeApproveMock() {
  const mutateMock = vi.fn();
  vi.mocked(queries.useApproveClaim).mockReturnValue({
    mutate: mutateMock,
    mutateAsync: vi.fn(),
    isPending: false,
    isSuccess: false,
    isError: false,
    isIdle: true,
    error: null,
    data: undefined,
    variables: undefined,
    status: 'idle',
    reset: vi.fn(),
    context: undefined,
    failureCount: 0,
    failureReason: null,
    isPaused: false,
    submittedAt: 0,
  } as unknown as ReturnType<typeof queries.useApproveClaim>);
  return mutateMock;
}

function makeRejectMock() {
  const mutateMock = vi.fn();
  vi.mocked(queries.useRejectClaim).mockReturnValue({
    mutate: mutateMock,
    mutateAsync: vi.fn(),
    isPending: false,
    isSuccess: false,
    isError: false,
    isIdle: true,
    error: null,
    data: undefined,
    variables: undefined,
    status: 'idle',
    reset: vi.fn(),
    context: undefined,
    failureCount: 0,
    failureReason: null,
    isPaused: false,
    submittedAt: 0,
  } as unknown as ReturnType<typeof queries.useRejectClaim>);
  return mutateMock;
}

// ===========================================================================
// ApproveClaimDialog
// ===========================================================================

describe('ApproveClaimDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the Approve button', () => {
    makeApproveMock();
    renderWithProviders(<ApproveClaimDialog claim={mockClaim} />);
    expect(screen.getByRole('button', { name: /approve/i })).toBeInTheDocument();
  });

  it('opens dialog when Approve button is clicked', async () => {
    const user = userEvent.setup();
    makeApproveMock();
    renderWithProviders(<ApproveClaimDialog claim={mockClaim} />);

    await user.click(screen.getByRole('button', { name: /approve/i }));

    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByText(/Approve AGM claim/i)).toBeInTheDocument();
    expect(screen.getByText(/AGM #7/i)).toBeInTheDocument();
  });

  it('shows beat description in the dialog', async () => {
    const user = userEvent.setup();
    makeApproveMock();
    renderWithProviders(<ApproveClaimDialog claim={mockClaim} />);

    await user.click(screen.getByRole('button', { name: /approve/i }));

    expect(screen.getByText(/The villain escapes or is captured/i)).toBeInTheDocument();
  });

  it('calls mutation with correct payload on submit', async () => {
    const user = userEvent.setup();
    const mutateMock = makeApproveMock();

    mutateMock.mockImplementation((_vars, callbacks) => {
      callbacks?.onSuccess?.({}, _vars, undefined);
    });

    renderWithProviders(<ApproveClaimDialog claim={mockClaim} />);
    await user.click(screen.getByRole('button', { name: /approve/i }));

    const framingInput = screen.getByLabelText(/framing note/i);
    await user.type(framingInput, 'Scene at the temple');

    await user.click(screen.getByRole('button', { name: /approve claim/i }));

    expect(mutateMock).toHaveBeenCalledWith(
      expect.objectContaining({
        claimId: 55,
        framing_note: 'Scene at the temple',
      }),
      expect.any(Object)
    );
  });

  it('closes dialog and shows toast on success', async () => {
    const user = userEvent.setup();
    const mutateMock = makeApproveMock();

    mutateMock.mockImplementation((_vars, callbacks) => {
      callbacks?.onSuccess?.({}, _vars, undefined);
    });

    renderWithProviders(<ApproveClaimDialog claim={mockClaim} />);
    await user.click(screen.getByRole('button', { name: /approve/i }));
    await user.click(screen.getByRole('button', { name: /approve claim/i }));

    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith('Claim approved');
    });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('keeps dialog open on validation error', async () => {
    const user = userEvent.setup();
    const mutateMock = makeApproveMock();

    const mockErrorResponse = {
      json: () =>
        Promise.resolve({
          non_field_errors: ['Only REQUESTED claims can be approved.'],
        }),
    };

    mutateMock.mockImplementation((_vars, callbacks) => {
      callbacks?.onError?.({ response: mockErrorResponse }, _vars, undefined);
    });

    renderWithProviders(<ApproveClaimDialog claim={mockClaim} />);
    await user.click(screen.getByRole('button', { name: /approve/i }));
    await user.click(screen.getByRole('button', { name: /approve claim/i }));

    await waitFor(() => {
      expect(screen.queryByRole('dialog')).toBeInTheDocument();
    });

    await waitFor(() => {
      expect(screen.getByText(/Only REQUESTED claims can be approved/i)).toBeInTheDocument();
    });
  });
});

// ===========================================================================
// RejectClaimDialog
// ===========================================================================

describe('RejectClaimDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the Reject button', () => {
    makeRejectMock();
    renderWithProviders(<RejectClaimDialog claim={mockClaim} />);
    expect(screen.getByRole('button', { name: /reject/i })).toBeInTheDocument();
  });

  it('opens dialog when Reject button is clicked', async () => {
    const user = userEvent.setup();
    makeRejectMock();
    renderWithProviders(<RejectClaimDialog claim={mockClaim} />);

    await user.click(screen.getByRole('button', { name: /reject/i }));

    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByText(/Reject AGM claim/i)).toBeInTheDocument();
    expect(screen.getByText(/AGM #7/i)).toBeInTheDocument();
  });

  it('calls mutation with correct payload on submit', async () => {
    const user = userEvent.setup();
    const mutateMock = makeRejectMock();

    mutateMock.mockImplementation((_vars, callbacks) => {
      callbacks?.onSuccess?.({}, _vars, undefined);
    });

    renderWithProviders(<RejectClaimDialog claim={mockClaim} />);
    await user.click(screen.getByRole('button', { name: /reject/i }));

    const noteInput = screen.getByLabelText(/rejection note/i);
    await user.type(noteInput, 'Beat is reserved for main GM');

    await user.click(screen.getByRole('button', { name: /reject claim/i }));

    expect(mutateMock).toHaveBeenCalledWith(
      expect.objectContaining({
        claimId: 55,
        note: 'Beat is reserved for main GM',
      }),
      expect.any(Object)
    );
  });

  it('closes dialog and shows toast on success', async () => {
    const user = userEvent.setup();
    const mutateMock = makeRejectMock();

    mutateMock.mockImplementation((_vars, callbacks) => {
      callbacks?.onSuccess?.({}, _vars, undefined);
    });

    renderWithProviders(<RejectClaimDialog claim={mockClaim} />);
    await user.click(screen.getByRole('button', { name: /reject/i }));
    await user.click(screen.getByRole('button', { name: /reject claim/i }));

    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith('Claim rejected');
    });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('keeps dialog open on validation error', async () => {
    const user = userEvent.setup();
    const mutateMock = makeRejectMock();

    const mockErrorResponse = {
      json: () =>
        Promise.resolve({
          non_field_errors: ['Only REQUESTED claims can be rejected.'],
        }),
    };

    mutateMock.mockImplementation((_vars, callbacks) => {
      callbacks?.onError?.({ response: mockErrorResponse }, _vars, undefined);
    });

    renderWithProviders(<RejectClaimDialog claim={mockClaim} />);
    await user.click(screen.getByRole('button', { name: /reject/i }));
    await user.click(screen.getByRole('button', { name: /reject claim/i }));

    await waitFor(() => {
      expect(screen.queryByRole('dialog')).toBeInTheDocument();
    });

    await waitFor(() => {
      expect(screen.getByText(/Only REQUESTED claims can be rejected/i)).toBeInTheDocument();
    });
  });
});
