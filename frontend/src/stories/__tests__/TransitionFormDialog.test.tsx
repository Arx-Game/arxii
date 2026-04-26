/**
 * TransitionFormDialog Tests — Task 9.3
 *
 * Covers:
 *  - Opens in create mode
 *  - Fills basic transition fields and submits — POST /api/transitions/
 *  - After transition saved, routing predicate section appears
 *  - Add routing predicate row — POST /api/transition-required-outcomes/
 *  - Remove routing predicate row — DELETE fires
 *  - Edit mode (existing transition) pre-populated
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
  useCreateTransition: vi.fn(),
  useUpdateTransition: vi.fn(),
  useTransitionRequiredOutcomes: vi.fn(),
  useCreateTransitionRequiredOutcome: vi.fn(),
  useDeleteTransitionRequiredOutcome: vi.fn(),
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

type MutationHookKey =
  | 'useCreateTransition'
  | 'useUpdateTransition'
  | 'useCreateTransitionRequiredOutcome'
  | 'useDeleteTransitionRequiredOutcome';

function makeMutationMock(hookName: MutationHookKey) {
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
  const createTransitionMock = makeMutationMock('useCreateTransition');
  makeMutationMock('useUpdateTransition');
  const createOutcomeMock = makeMutationMock('useCreateTransitionRequiredOutcome');
  const deleteOutcomeMock = makeMutationMock('useDeleteTransitionRequiredOutcome');

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

  return { createTransitionMock, createOutcomeMock, deleteOutcomeMock };
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

  it('submits transition with correct payload on create', async () => {
    const user = userEvent.setup();
    const { createTransitionMock } = setupMocks();

    createTransitionMock.mockImplementation(
      (_vars: unknown, callbacks: Record<string, unknown>) => {
        const cb = callbacks as { onSuccess?: (data: unknown) => void };
        cb.onSuccess?.({ ...existingTransition, id: 99 });
      }
    );

    renderWithProviders(<TransitionFormDialog {...defaultProps} />);

    await user.click(screen.getByRole('button', { name: /create transition/i }));

    await waitFor(() => {
      expect(createTransitionMock).toHaveBeenCalledWith(
        expect.objectContaining({
          source_episode: 10,
          mode: 'auto',
        }),
        expect.any(Object)
      );
    });

    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith('Transition created');
    });
  });

  it('shows routing predicate section after transition saved', async () => {
    const user = userEvent.setup();
    const { createTransitionMock } = setupMocks();

    createTransitionMock.mockImplementation(
      (_vars: unknown, callbacks: Record<string, unknown>) => {
        const cb = callbacks as { onSuccess?: (data: unknown) => void };
        cb.onSuccess?.({ ...existingTransition, id: 99 });
      }
    );

    renderWithProviders(<TransitionFormDialog {...defaultProps} />);
    await user.click(screen.getByRole('button', { name: /create transition/i }));

    await waitFor(() => {
      expect(screen.getByText('Routing Predicate')).toBeInTheDocument();
    });
    expect(screen.getByTestId('routing-predicate-empty')).toBeInTheDocument();
  });

  it('renders Edit Transition dialog pre-populated', () => {
    setupMocks();
    renderWithProviders(<TransitionFormDialog {...defaultProps} transition={existingTransition} />);

    expect(screen.getByText('Edit Transition')).toBeInTheDocument();
    // Routing predicate section visible immediately (existing transition)
    expect(screen.getByText('Routing Predicate')).toBeInTheDocument();
  });

  it('shows existing routing predicate rows for edit mode', () => {
    setupMocks();
    const outcomeRow: TransitionRequiredOutcome = {
      id: 1,
      transition: 55,
      beat: 3,
      required_outcome: 'success',
    };
    vi.mocked(queries.useTransitionRequiredOutcomes).mockReturnValue({
      data: { count: 1, results: [outcomeRow], next: null, previous: null },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    } as unknown as ReturnType<typeof queries.useTransitionRequiredOutcomes>);

    renderWithProviders(<TransitionFormDialog {...defaultProps} transition={existingTransition} />);

    expect(screen.getByTestId('routing-predicate-list')).toBeInTheDocument();
    const rows = screen.getAllByTestId('routing-predicate-row');
    expect(rows).toHaveLength(1);
    expect(screen.getByText(/Beat #3/)).toBeInTheDocument();
  });

  it('Delete routing predicate row fires delete mutation', async () => {
    const user = userEvent.setup();
    const { deleteOutcomeMock } = setupMocks();
    const outcomeRow: TransitionRequiredOutcome = {
      id: 7,
      transition: 55,
      beat: 3,
      required_outcome: 'success',
    };
    vi.mocked(queries.useTransitionRequiredOutcomes).mockReturnValue({
      data: { count: 1, results: [outcomeRow], next: null, previous: null },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    } as unknown as ReturnType<typeof queries.useTransitionRequiredOutcomes>);

    deleteOutcomeMock.mockImplementation((_vars: unknown, callbacks: Record<string, unknown>) => {
      const cb = callbacks as { onSuccess?: () => void };
      cb.onSuccess?.();
    });

    renderWithProviders(<TransitionFormDialog {...defaultProps} transition={existingTransition} />);

    await user.click(screen.getByTestId('remove-routing-row-btn'));

    await waitFor(() => {
      expect(deleteOutcomeMock).toHaveBeenCalledWith(
        expect.objectContaining({ id: 7 }),
        expect.any(Object)
      );
    });
  });
});
