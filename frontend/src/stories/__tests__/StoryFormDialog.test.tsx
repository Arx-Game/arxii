/**
 * StoryFormDialog Tests — Task E2
 *
 * Covers (Task E2 — GM/player text split):
 *  - description control relabeled to "Internal GM Description" + "not shown
 *    to players" helper, still bound to the description state key
 *  - new "The Story So Far" control bound to `summary` with a player-facing
 *    recap helper
 *  - both submitted in the create body
 *  - both prefilled on edit from the existing object
 *  - read-only maturity indicator on edit; absent in create mode
 */

import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { StoryFormDialog } from '../components/StoryFormDialog';
import type { Story } from '../types';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('../queries', () => ({
  useCreateStory: vi.fn(),
  useUpdateStory: vi.fn(),
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

import * as queries from '../queries';
import { toast } from 'sonner';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeMutationMock(hookName: 'useCreateStory' | 'useUpdateStory') {
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
  const createMock = makeMutationMock('useCreateStory');
  const updateMock = makeMutationMock('useUpdateStory');
  return { createMock, updateMock };
}

const defaultProps = {
  open: true,
  onOpenChange: vi.fn(),
};

const existingStory: Story = {
  id: 7,
  title: 'Who Am I?',
  description: 'GM-only spoilers about the twist.',
  summary: 'The hero awoke with no memory.',
  maturity: 'plot',
  scope: 'character',
  status: 'active',
  privacy: 'public',
  owners: ['player1'],
  active_gms: [],
  trust_requirements: '',
  character_sheet: 1,
  chapters_count: 0,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  completed_at: null,
  primary_table: null,
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('StoryFormDialog — Task E2 GM/player text split', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('relabels the description control to "Internal GM Description" with a not-shown helper', () => {
    setupMocks();
    renderWithProviders(<StoryFormDialog {...defaultProps} />);

    expect(screen.getByLabelText(/internal gm description/i)).toBeInTheDocument();
    expect(screen.getByText(/not shown to players/i)).toBeInTheDocument();
  });

  it('renders a "The Story So Far" control bound to summary with a recap helper', () => {
    setupMocks();
    renderWithProviders(<StoryFormDialog {...defaultProps} />);

    expect(screen.getByLabelText(/the story so far/i)).toBeInTheDocument();
    expect(
      screen.getByText(/player-facing recap — keep this current as the story advances/i)
    ).toBeInTheDocument();
  });

  it('does not render a maturity indicator in create mode', () => {
    setupMocks();
    renderWithProviders(<StoryFormDialog {...defaultProps} />);

    expect(screen.queryByTestId('story-maturity-indicator')).not.toBeInTheDocument();
  });

  it('submits both description and summary in the create body', async () => {
    const user = userEvent.setup();
    const { createMock } = setupMocks();
    createMock.mockImplementation((_vars: unknown, callbacks: Record<string, unknown>) => {
      const cb = callbacks as { onSuccess?: (data: unknown) => void };
      cb.onSuccess?.({ id: 11 });
    });

    renderWithProviders(<StoryFormDialog {...defaultProps} />);

    await user.type(screen.getByLabelText(/title/i), 'New Story');
    await user.type(screen.getByLabelText(/internal gm description/i), 'Secret GM notes');
    await user.type(screen.getByLabelText(/the story so far/i), 'Public recap text');

    await user.click(screen.getByRole('button', { name: /create story/i }));

    await waitFor(() => {
      expect(createMock).toHaveBeenCalledWith(
        expect.objectContaining({
          title: 'New Story',
          description: 'Secret GM notes',
          summary: 'Public recap text',
        }),
        expect.any(Object)
      );
    });

    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith('Story created');
    });
  });

  it('prefills description and summary on edit and shows a read-only maturity indicator', () => {
    setupMocks();
    renderWithProviders(<StoryFormDialog {...defaultProps} story={existingStory} />);

    expect((screen.getByLabelText(/internal gm description/i) as HTMLTextAreaElement).value).toBe(
      'GM-only spoilers about the twist.'
    );
    expect((screen.getByLabelText(/the story so far/i) as HTMLTextAreaElement).value).toBe(
      'The hero awoke with no memory.'
    );

    const indicator = screen.getByTestId('story-maturity-indicator');
    expect(indicator).toBeInTheDocument();
    expect(indicator).toHaveTextContent(/plot/i);
  });

  it('submits both description and summary in the update body on edit', async () => {
    const user = userEvent.setup();
    const { updateMock } = setupMocks();
    updateMock.mockImplementation((_vars: unknown, callbacks: Record<string, unknown>) => {
      const cb = callbacks as { onSuccess?: (data: unknown) => void };
      cb.onSuccess?.({ id: 7 });
    });

    renderWithProviders(<StoryFormDialog {...defaultProps} story={existingStory} />);

    const summary = screen.getByLabelText(/the story so far/i);
    await user.clear(summary);
    await user.type(summary, 'Updated recap');

    await user.click(screen.getByRole('button', { name: /save story/i }));

    await waitFor(() => {
      expect(updateMock).toHaveBeenCalledWith(
        expect.objectContaining({
          id: 7,
          data: expect.objectContaining({
            description: 'GM-only spoilers about the twist.',
            summary: 'Updated recap',
          }),
        }),
        expect.any(Object)
      );
    });
  });
});
