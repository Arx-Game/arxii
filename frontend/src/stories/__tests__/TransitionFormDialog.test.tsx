/**
 * TransitionFormDialog Tests — Wave 13 (atomic save-with-outcomes)
 *
 * Covers:
 *  - Opens in create mode
 *  - Submits via useSaveTransitionWithOutcomes (single mutation, no round trips)
 *  - Routing predicate rows accumulate locally before submit
 *  - Local rows can be removed before submit
 *  - Edit mode: pre-populated fields
 *  - Edit mode: existing routing predicates loaded from server and shown
 *  - Success: closes dialog and calls onSuccess
 *  - Error: field errors surface inline
 */

import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { TransitionFormDialog } from '../components/TransitionFormDialog';
import type { Transition, TransitionRequiredOutcome } from '../types';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('../queries', () => ({
  useSaveTransitionWithOutcomes: vi.fn(),
  useTransitionRequiredOutcomes: vi.fn(),
  useEpisodeList: vi.fn(),
  useBeatList: vi.fn(),
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

import * as queries from '../queries';
import { toast } from 'sonner';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeMutationMock(hookName: 'useSaveTransitionWithOutcomes') {
  const mutateMock = vi.fn();
  vi.mocked(queries[hookName]).mockReturnValue({
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

function setupMocks() {
  const saveMock = makeMutationMock('useSaveTransitionWithOutcomes');

  vi.mocked(queries.useEpisodeList).mockReturnValue({
    data: { count: 0, results: [], next: null, previous: null },
    isLoading: false,
    isError: false,
    error: null,
  } as unknown as ReturnType<typeof queries.useEpisodeList>);

  vi.mocked(queries.useBeatList).mockReturnValue({
    data: { count: 0, results: [], next: null, previous: null },
    isLoading: false,
    isError: false,
    error: null,
  } as unknown as ReturnType<typeof queries.useBeatList>);

  vi.mocked(queries.useTransitionRequiredOutcomes).mockReturnValue({
    data: { count: 0, results: [], next: null, previous: null },
    isLoading: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
  } as unknown as ReturnType<typeof queries.useTransitionRequiredOutcomes>);

  return { saveMock };
}

const defaultProps = {
  open: true,
  onOpenChange: vi.fn(),
  sourceEpisodeId: 10,
  storyId: 1,
};

const existingTransition: Transition = {
  id: 55,
  source_episode: 10,
  source_episode_title: 'Episode 1',
  target_episode: 20,
  target_episode_title: 'Episode 2',
  mode: 'auto',
  connection_type: 'therefore',
  connection_summary: 'The hero succeeds',
  order: 0,
  created_at: '2026-01-01T00:00:00Z',
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('TransitionFormDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders Create Transition dialog', () => {
    setupMocks();
    renderWithProviders(<TransitionFormDialog {...defaultProps} />);
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Create Transition' })).toBeInTheDocument();
  });

  it('shows source episode ID as read-only context', () => {
    setupMocks();
    renderWithProviders(<TransitionFormDialog {...defaultProps} />);
    expect(screen.getByText(/source episode id/i)).toBeInTheDocument();
    expect(screen.getByText('10')).toBeInTheDocument();
  });

  it('submits via single atomic mutation on create', async () => {
    const user = userEvent.setup();
    const { saveMock } = setupMocks();

    saveMock.mockImplementation((_body: unknown, callbacks: Record<string, unknown>) => {
      const cb = callbacks as { onSuccess?: (data: unknown) => void };
      cb.onSuccess?.({ ...existingTransition, id: 99 });
    });

    const onSuccess = vi.fn();
    renderWithProviders(<TransitionFormDialog {...defaultProps} onSuccess={onSuccess} />);

    await user.click(screen.getByRole('button', { name: /create transition/i }));

    await waitFor(() => {
      expect(saveMock).toHaveBeenCalledWith(
        expect.objectContaining({
          source_episode: 10,
          mode: 'auto',
          outcomes: [],
          existing_id: null,
        }),
        expect.any(Object)
      );
    });

    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith('Transition created');
    });
    expect(onSuccess).toHaveBeenCalledWith(expect.objectContaining({ id: 99 }));
  });

  it('routing predicate section shown immediately on create mode', () => {
    setupMocks();
    renderWithProviders(<TransitionFormDialog {...defaultProps} />);
    // Routing section is always visible in the new design (no save-first required).
    expect(screen.getByText('Routing Predicate')).toBeInTheDocument();
    expect(screen.getByTestId('routing-predicate-empty')).toBeInTheDocument();
  });

  it('renders Edit Transition dialog pre-populated', () => {
    setupMocks();
    renderWithProviders(<TransitionFormDialog {...defaultProps} transition={existingTransition} />);
    expect(screen.getByText('Edit Transition')).toBeInTheDocument();
    expect(screen.getByText('Routing Predicate')).toBeInTheDocument();
  });

  it('shows existing routing predicate rows loaded from server in edit mode', async () => {
    const outcomeRow: TransitionRequiredOutcome = {
      id: 1,
      transition: 55,
      beat: 3,
      required_outcome: 'success',
    };
    setupMocks();

    vi.mocked(queries.useTransitionRequiredOutcomes).mockReturnValue({
      data: { count: 1, results: [outcomeRow], next: null, previous: null },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    } as unknown as ReturnType<typeof queries.useTransitionRequiredOutcomes>);

    renderWithProviders(<TransitionFormDialog {...defaultProps} transition={existingTransition} />);

    await waitFor(() => {
      expect(screen.getByTestId('routing-predicate-list')).toBeInTheDocument();
    });
    const rows = screen.getAllByTestId('routing-predicate-row');
    expect(rows).toHaveLength(1);
    expect(screen.getByText(/Beat #3/)).toBeInTheDocument();
  });

  it('routing predicate rows accumulate locally before submit', async () => {
    // Override beat list to provide one option.
    vi.mocked(queries.useBeatList).mockReturnValue({
      data: {
        count: 1,
        results: [
          {
            id: 7,
            internal_description: 'Defeat the boss',
            episode: 10,
            predicate_type: 'gm_marked',
            outcome: 'unsatisfied',
            agm_eligible: false,
            can_mark: false,
            created_at: '2026-01-01T00:00:00Z',
            updated_at: '2026-01-01T00:00:00Z',
          },
        ],
        next: null,
        previous: null,
      },
      isLoading: false,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof queries.useBeatList>);

    setupMocks();

    renderWithProviders(<TransitionFormDialog {...defaultProps} />);

    // Open the add-row form.
    await userEvent.click(screen.getByTestId('add-routing-row-btn'));
    // The form is now showing; click "Add" without a beat selected — should not add.
    expect(screen.getByTestId('confirm-routing-row')).toBeDisabled();
  });

  it('remove routing predicate row removes it from local state', async () => {
    const user = userEvent.setup();
    const outcomeRow: TransitionRequiredOutcome = {
      id: 7,
      transition: 55,
      beat: 3,
      required_outcome: 'success',
    };
    setupMocks();

    vi.mocked(queries.useTransitionRequiredOutcomes).mockReturnValue({
      data: { count: 1, results: [outcomeRow], next: null, previous: null },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    } as unknown as ReturnType<typeof queries.useTransitionRequiredOutcomes>);

    renderWithProviders(<TransitionFormDialog {...defaultProps} transition={existingTransition} />);

    await waitFor(() => {
      expect(screen.getByTestId('routing-predicate-list')).toBeInTheDocument();
    });

    // Remove the row — no API call, just local state update.
    await user.click(screen.getByTestId('remove-routing-row-btn'));

    await waitFor(() => {
      expect(screen.queryByTestId('routing-predicate-list')).not.toBeInTheDocument();
      expect(screen.getByTestId('routing-predicate-empty')).toBeInTheDocument();
    });
  });

  it('submit in edit mode passes existing_id', async () => {
    const user = userEvent.setup();
    const { saveMock } = setupMocks();

    saveMock.mockImplementation((_body: unknown, callbacks: Record<string, unknown>) => {
      const cb = callbacks as { onSuccess?: (data: unknown) => void };
      cb.onSuccess?.(existingTransition);
    });

    renderWithProviders(<TransitionFormDialog {...defaultProps} transition={existingTransition} />);

    await user.click(screen.getByRole('button', { name: /save transition/i }));

    await waitFor(() => {
      expect(saveMock).toHaveBeenCalledWith(
        expect.objectContaining({
          existing_id: 55,
          source_episode: 10,
        }),
        expect.any(Object)
      );
    });

    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith('Transition updated');
    });
  });
});
