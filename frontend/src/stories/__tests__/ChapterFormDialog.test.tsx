/**
 * ChapterFormDialog Tests — Task E2
 *
 * Covers (Task E2 — GM/player text split):
 *  - description control relabeled to "Internal GM Description" + "not shown
 *    to players" helper, still bound to the description state key
 *  - new "The Story So Far" control bound to `summary` with a player-facing
 *    recap helper
 *  - both submitted in the create body
 *  - both prefilled on edit from the existing chapter
 *  - read-only maturity indicator on edit; absent in create mode
 */

import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { ChapterFormDialog } from '../components/ChapterFormDialog';
import type { ChapterLike } from '../components/ChapterFormDialog';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('../queries', () => ({
  useCreateChapter: vi.fn(),
  useUpdateChapter: vi.fn(),
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

import * as queries from '../queries';
import { toast } from 'sonner';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeMutationMock(hookName: 'useCreateChapter' | 'useUpdateChapter') {
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
  const createMock = makeMutationMock('useCreateChapter');
  const updateMock = makeMutationMock('useUpdateChapter');
  return { createMock, updateMock };
}

const defaultProps = {
  open: true,
  onOpenChange: vi.fn(),
  storyId: 3,
};

const existingChapter: ChapterLike = {
  id: 9,
  title: 'Chapter One',
  description: 'GM-only chapter spoilers.',
  summary: 'The party set out from the village.',
  maturity: 'outline',
  order: 1,
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('ChapterFormDialog — Task E2 GM/player text split', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('relabels the description control to "Internal GM Description" with a not-shown helper', () => {
    setupMocks();
    renderWithProviders(<ChapterFormDialog {...defaultProps} />);

    expect(screen.getByLabelText(/internal gm description/i)).toBeInTheDocument();
    expect(screen.getByText(/not shown to players/i)).toBeInTheDocument();
  });

  it('renders a "The Story So Far" control bound to summary with a recap helper', () => {
    setupMocks();
    renderWithProviders(<ChapterFormDialog {...defaultProps} />);

    expect(screen.getByLabelText(/the story so far/i)).toBeInTheDocument();
    expect(
      screen.getByText(/player-facing recap — keep this current as the story advances/i)
    ).toBeInTheDocument();
  });

  it('does not render a maturity indicator in create mode', () => {
    setupMocks();
    renderWithProviders(<ChapterFormDialog {...defaultProps} />);

    expect(screen.queryByTestId('chapter-maturity-indicator')).not.toBeInTheDocument();
  });

  it('submits both description and summary in the create body', async () => {
    const user = userEvent.setup();
    const { createMock } = setupMocks();
    createMock.mockImplementation((_vars: unknown, callbacks: Record<string, unknown>) => {
      const cb = callbacks as { onSuccess?: (data: unknown) => void };
      cb.onSuccess?.({ id: 12 });
    });

    renderWithProviders(<ChapterFormDialog {...defaultProps} />);

    await user.type(screen.getByLabelText(/title/i), 'New Chapter');
    await user.type(screen.getByLabelText(/internal gm description/i), 'Secret chapter notes');
    await user.type(screen.getByLabelText(/the story so far/i), 'Chapter recap text');

    await user.click(screen.getByRole('button', { name: /create chapter/i }));

    await waitFor(() => {
      expect(createMock).toHaveBeenCalledWith(
        expect.objectContaining({
          story: 3,
          title: 'New Chapter',
          description: 'Secret chapter notes',
          summary: 'Chapter recap text',
        }),
        expect.any(Object)
      );
    });

    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith('Chapter created');
    });
  });

  it('prefills description and summary on edit and shows a read-only maturity indicator', () => {
    setupMocks();
    renderWithProviders(<ChapterFormDialog {...defaultProps} chapter={existingChapter} />);

    expect((screen.getByLabelText(/internal gm description/i) as HTMLTextAreaElement).value).toBe(
      'GM-only chapter spoilers.'
    );
    expect((screen.getByLabelText(/the story so far/i) as HTMLTextAreaElement).value).toBe(
      'The party set out from the village.'
    );

    const indicator = screen.getByTestId('chapter-maturity-indicator');
    expect(indicator).toBeInTheDocument();
    expect(indicator).toHaveTextContent(/outline/i);
  });

  it('submits both description and summary in the update body on edit', async () => {
    const user = userEvent.setup();
    const { updateMock } = setupMocks();
    updateMock.mockImplementation((_vars: unknown, callbacks: Record<string, unknown>) => {
      const cb = callbacks as { onSuccess?: (data: unknown) => void };
      cb.onSuccess?.({ id: 9 });
    });

    renderWithProviders(<ChapterFormDialog {...defaultProps} chapter={existingChapter} />);

    const summary = screen.getByLabelText(/the story so far/i);
    await user.clear(summary);
    await user.type(summary, 'Updated chapter recap');

    await user.click(screen.getByRole('button', { name: /save chapter/i }));

    await waitFor(() => {
      expect(updateMock).toHaveBeenCalledWith(
        expect.objectContaining({
          id: 9,
          data: expect.objectContaining({
            description: 'GM-only chapter spoilers.',
            summary: 'Updated chapter recap',
          }),
        }),
        expect.any(Object)
      );
    });
  });
});
