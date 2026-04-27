/**
 * SendGemitDialog Tests
 *
 * Covers:
 *  - Dialog opens/closes on trigger
 *  - Body required — submit disabled when empty
 *  - Submit happy path → mutation called with right payload, dialog closes, toast shown
 *  - Optional era/story fields work (passed as null when blank)
 *  - Validation error shown inline
 *  - 403 closes dialog and shows permission toast
 *  - Cancel closes dialog
 */

import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { SendGemitDialog } from '../components/SendGemitDialog';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('../queries', () => ({
  useBroadcastGemit: vi.fn(),
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
// Helpers
// ---------------------------------------------------------------------------

function makeBroadcastMock() {
  const mutateMock = vi.fn();
  vi.mocked(queries.useBroadcastGemit).mockReturnValue({
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
  } as unknown as ReturnType<typeof queries.useBroadcastGemit>);
  return mutateMock;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('SendGemitDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the Broadcast Gemit button', () => {
    makeBroadcastMock();
    renderWithProviders(<SendGemitDialog />);
    expect(screen.getByRole('button', { name: /broadcast gemit/i })).toBeInTheDocument();
  });

  it('opens dialog when button is clicked', async () => {
    const user = userEvent.setup();
    makeBroadcastMock();
    renderWithProviders(<SendGemitDialog />);

    await user.click(screen.getByRole('button', { name: /broadcast gemit/i }));

    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByText(/server-wide announcement/i)).toBeInTheDocument();
  });

  it('disables submit when body is empty', async () => {
    const user = userEvent.setup();
    makeBroadcastMock();
    renderWithProviders(<SendGemitDialog />);

    await user.click(screen.getByRole('button', { name: /broadcast gemit/i }));

    expect(screen.getByRole('button', { name: /^broadcast$/i })).toBeDisabled();
  });

  it('calls mutation with body only when optional fields are blank', async () => {
    const user = userEvent.setup();
    const mutateMock = makeBroadcastMock();

    mutateMock.mockImplementation((_vars: unknown, callbacks: { onSuccess?: () => void }) => {
      callbacks?.onSuccess?.();
    });

    renderWithProviders(<SendGemitDialog />);

    await user.click(screen.getByRole('button', { name: /broadcast gemit/i }));
    await user.type(screen.getByTestId('gemit-body-input'), 'A new era begins.');
    await user.click(screen.getByRole('button', { name: /^broadcast$/i }));

    expect(mutateMock).toHaveBeenCalledWith(
      expect.objectContaining({
        body: 'A new era begins.',
        related_era: null,
        related_story: null,
      }),
      expect.any(Object)
    );
  });

  it('passes era and story IDs when provided', async () => {
    const user = userEvent.setup();
    const mutateMock = makeBroadcastMock();

    mutateMock.mockImplementation((_vars: unknown, callbacks: { onSuccess?: () => void }) => {
      callbacks?.onSuccess?.();
    });

    renderWithProviders(<SendGemitDialog />);

    await user.click(screen.getByRole('button', { name: /broadcast gemit/i }));
    await user.type(screen.getByTestId('gemit-body-input'), 'Season 3 starts now.');
    await user.type(screen.getByTestId('gemit-era-input'), '3');
    await user.type(screen.getByTestId('gemit-story-input'), '17');
    await user.click(screen.getByRole('button', { name: /^broadcast$/i }));

    expect(mutateMock).toHaveBeenCalledWith(
      expect.objectContaining({
        body: 'Season 3 starts now.',
        related_era: 3,
        related_story: 17,
      }),
      expect.any(Object)
    );
  });

  it('closes dialog and shows success toast on happy path', async () => {
    const user = userEvent.setup();
    const mutateMock = makeBroadcastMock();

    mutateMock.mockImplementation((_vars: unknown, callbacks: { onSuccess?: () => void }) => {
      callbacks?.onSuccess?.();
    });

    renderWithProviders(<SendGemitDialog />);

    await user.click(screen.getByRole('button', { name: /broadcast gemit/i }));
    await user.type(screen.getByTestId('gemit-body-input'), 'The realm shakes!');
    await user.click(screen.getByRole('button', { name: /^broadcast$/i }));

    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith('Gemit broadcast — all online accounts notified');
    });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('shows inline validation errors from DRF', async () => {
    const user = userEvent.setup();
    const mutateMock = makeBroadcastMock();

    const mockErrorResponse = {
      json: () =>
        Promise.resolve({
          body: ['Ensure this field has no more than 10000 characters.'],
        }),
    };

    mutateMock.mockImplementation(
      (_vars: unknown, callbacks: { onError?: (err: unknown) => void }) => {
        callbacks?.onError?.({ response: mockErrorResponse });
      }
    );

    renderWithProviders(<SendGemitDialog />);
    await user.click(screen.getByRole('button', { name: /broadcast gemit/i }));
    await user.type(screen.getByTestId('gemit-body-input'), 'This is too long.');
    await user.click(screen.getByRole('button', { name: /^broadcast$/i }));

    await waitFor(() => {
      expect(
        screen.getByText(/ensure this field has no more than 10000 characters/i)
      ).toBeInTheDocument();
    });
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('closes dialog and shows permission toast on 403', async () => {
    const user = userEvent.setup();
    const mutateMock = makeBroadcastMock();

    mutateMock.mockImplementation(
      (_vars: unknown, callbacks: { onError?: (err: unknown) => void }) => {
        callbacks?.onError?.({ status: 403 });
      }
    );

    renderWithProviders(<SendGemitDialog />);
    await user.click(screen.getByRole('button', { name: /broadcast gemit/i }));
    await user.type(screen.getByTestId('gemit-body-input'), 'Unauthorized gemit.');
    await user.click(screen.getByRole('button', { name: /^broadcast$/i }));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith(
        'Permission denied. Only staff can broadcast gemits.'
      );
    });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('closes dialog on Cancel button click', async () => {
    const user = userEvent.setup();
    makeBroadcastMock();
    renderWithProviders(<SendGemitDialog />);

    await user.click(screen.getByRole('button', { name: /broadcast gemit/i }));
    expect(screen.getByRole('dialog')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /cancel/i }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
});
