/**
 * PromoteMaturityButton Tests — Task E3
 *
 * Covers:
 *  - renders the current maturity and a next-stage promote control
 *    (pitch → "Promote to Outline", outline → "Promote to Plot")
 *  - at plot, the control is disabled / max-reached (no promotion)
 *  - clicking calls usePromoteEpisode().mutate with {episodeId, storyId, target}
 *  - a 400 body { "target": "<message>" } surfaces INLINE (visible text,
 *    not just a toast)
 *  - success path clears any prior inline error (relies on hook invalidation —
 *    no manual refetch)
 *
 * Mirrors the BeatFormDialog test harness: mock `../queries` so the
 * promote hook returns a controllable mock mutation, mock `sonner`, and
 * drive the error path via the mutation's onError callback (same technique
 * BeatFormDialog/MarkBeatDialog tests use).
 */

import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { PromoteMaturityButton } from '../components/PromoteMaturityButton';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('../queries', () => ({
  usePromoteEpisode: vi.fn(),
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

import * as queries from '../queries';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makePromoteMock() {
  const mutateMock = vi.fn();
  vi.mocked(queries.usePromoteEpisode).mockReturnValue({
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
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  } as any);
  return mutateMock;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('PromoteMaturityButton — Task E3', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the current maturity and a "Promote to Outline" control at pitch', () => {
    makePromoteMock();
    renderWithProviders(
      <PromoteMaturityButton episode={{ id: 7, maturity: 'pitch' }} storyId={3} />
    );

    expect(screen.getByTestId('promote-maturity-current')).toHaveTextContent(/pitch/i);
    expect(screen.getByRole('button', { name: /promote to outline/i })).toBeInTheDocument();
  });

  it('renders a "Promote to Plot" control at outline', () => {
    makePromoteMock();
    renderWithProviders(
      <PromoteMaturityButton episode={{ id: 8, maturity: 'outline' }} storyId={3} />
    );

    expect(screen.getByTestId('promote-maturity-current')).toHaveTextContent(/outline/i);
    expect(screen.getByRole('button', { name: /promote to plot/i })).toBeInTheDocument();
  });

  it('shows a disabled max-reached control at plot (no promotion possible)', () => {
    makePromoteMock();
    renderWithProviders(
      <PromoteMaturityButton episode={{ id: 9, maturity: 'plot' }} storyId={3} />
    );

    expect(screen.getByTestId('promote-maturity-current')).toHaveTextContent(/plot/i);
    const maxBtn = screen.getByRole('button', { name: /plot \(max\)/i });
    expect(maxBtn).toBeInTheDocument();
    expect(maxBtn).toBeDisabled();
  });

  it('calls mutate with {episodeId, storyId, target} for the next stage', async () => {
    const user = userEvent.setup();
    const mutateMock = makePromoteMock();

    renderWithProviders(
      <PromoteMaturityButton episode={{ id: 7, maturity: 'pitch' }} storyId={3} />
    );

    await user.click(screen.getByRole('button', { name: /promote to outline/i }));

    await waitFor(() => {
      expect(mutateMock).toHaveBeenCalledWith(
        { episodeId: 7, storyId: 3, target: 'outline' },
        expect.any(Object)
      );
    });
  });

  it('surfaces a 400 { target: "<message>" } gate error INLINE', async () => {
    const user = userEvent.setup();
    const mutateMock = makePromoteMock();

    const gateMessage =
      'Cannot promote to PLOT: episode needs a resting conclusion and either ' +
      'an outbound transition or an explicit ending.';
    const mockErrorResponse = {
      json: () => Promise.resolve({ target: gateMessage }),
    };

    mutateMock.mockImplementation((_vars: unknown, callbacks: Record<string, unknown>) => {
      const cb = callbacks as { onError?: (err: unknown) => void };
      cb.onError?.({ response: mockErrorResponse });
    });

    renderWithProviders(
      <PromoteMaturityButton episode={{ id: 8, maturity: 'outline' }} storyId={3} />
    );

    await user.click(screen.getByRole('button', { name: /promote to plot/i }));

    await waitFor(() => {
      expect(screen.getByText(gateMessage)).toBeInTheDocument();
    });
  });

  it('clears a prior inline error on a successful retry (relies on invalidation)', async () => {
    const user = userEvent.setup();
    const mutateMock = makePromoteMock();

    const gateMessage = 'Cannot promote to PLOT: episode needs a resting conclusion.';
    const mockErrorResponse = {
      json: () => Promise.resolve({ target: gateMessage }),
    };

    // First click → error
    mutateMock.mockImplementationOnce((_vars: unknown, callbacks: Record<string, unknown>) => {
      const cb = callbacks as { onError?: (err: unknown) => void };
      cb.onError?.({ response: mockErrorResponse });
    });
    // Second click → success
    mutateMock.mockImplementationOnce((_vars: unknown, callbacks: Record<string, unknown>) => {
      const cb = callbacks as { onSuccess?: (data: unknown) => void };
      cb.onSuccess?.({ id: 8 });
    });

    renderWithProviders(
      <PromoteMaturityButton episode={{ id: 8, maturity: 'outline' }} storyId={3} />
    );

    await user.click(screen.getByRole('button', { name: /promote to plot/i }));
    await waitFor(() => {
      expect(screen.getByText(gateMessage)).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /promote to plot/i }));
    await waitFor(() => {
      expect(screen.queryByText(gateMessage)).not.toBeInTheDocument();
    });
  });
});
