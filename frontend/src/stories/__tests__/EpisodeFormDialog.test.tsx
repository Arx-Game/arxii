/**
 * EpisodeFormDialog Tests — Task E2
 *
 * Covers (Task E2 — GM/player text split + episode authoring fields):
 *  - description control relabeled to "Internal GM Description" + "not shown
 *    to players" helper, still bound to the description state key
 *  - new "The Story So Far" control bound to `summary` with a player-facing
 *    recap helper
 *  - new `resting_conclusion` textarea (player-facing) + `is_ending` checkbox
 *  - all submitted in the create body
 *  - all prefilled on edit from the existing episode
 *  - read-only maturity indicator on edit; absent in create mode
 */

import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { EpisodeFormDialog } from '../components/EpisodeFormDialog';
import type { EpisodeLike } from '../components/EpisodeFormDialog';

// ---------------------------------------------------------------------------
// Mocks — includes the ProgressionRequirementsEditor query hooks because the
// editor is embedded when the dialog is in edit mode.
// ---------------------------------------------------------------------------

vi.mock('../queries', () => ({
  useCreateEpisode: vi.fn(),
  useUpdateEpisode: vi.fn(),
  useProgressionRequirements: vi.fn(),
  useCreateProgressionRequirement: vi.fn(),
  useDeleteProgressionRequirement: vi.fn(),
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

function makeMutationMock(
  hookName:
    | 'useCreateEpisode'
    | 'useUpdateEpisode'
    | 'useCreateProgressionRequirement'
    | 'useDeleteProgressionRequirement'
) {
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
  const createMock = makeMutationMock('useCreateEpisode');
  const updateMock = makeMutationMock('useUpdateEpisode');
  makeMutationMock('useCreateProgressionRequirement');
  makeMutationMock('useDeleteProgressionRequirement');

  vi.mocked(queries.useProgressionRequirements).mockReturnValue({
    data: { count: 0, results: [], next: null, previous: null },
    isLoading: false,
    isError: false,
    error: null,
  } as unknown as ReturnType<typeof queries.useProgressionRequirements>);

  vi.mocked(queries.useBeatList).mockReturnValue({
    data: { count: 0, results: [], next: null, previous: null },
    isLoading: false,
    isError: false,
    error: null,
  } as unknown as ReturnType<typeof queries.useBeatList>);

  return { createMock, updateMock };
}

const defaultProps = {
  open: true,
  onOpenChange: vi.fn(),
  chapterId: 4,
};

const existingEpisode: EpisodeLike = {
  id: 21,
  title: 'Episode One',
  description: 'GM-only episode spoilers.',
  summary: 'They reached the gates of the city.',
  resting_conclusion: 'The party rests, content with their progress.',
  is_ending: true,
  maturity: 'pitch',
  order: 1,
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('EpisodeFormDialog — Task E2 GM/player text split + episode fields', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('relabels the description control to "Internal GM Description" with a not-shown helper', () => {
    setupMocks();
    renderWithProviders(<EpisodeFormDialog {...defaultProps} />);

    expect(screen.getByLabelText(/internal gm description/i)).toBeInTheDocument();
    expect(screen.getByText(/not shown to players/i)).toBeInTheDocument();
  });

  it('renders a "The Story So Far" control bound to summary with a recap helper', () => {
    setupMocks();
    renderWithProviders(<EpisodeFormDialog {...defaultProps} />);

    expect(screen.getByLabelText(/the story so far/i)).toBeInTheDocument();
    expect(
      screen.getByText(/player-facing recap — keep this current as the story advances/i)
    ).toBeInTheDocument();
  });

  it('renders the resting conclusion textarea and is-ending checkbox', () => {
    setupMocks();
    renderWithProviders(<EpisodeFormDialog {...defaultProps} />);

    expect(screen.getByLabelText(/resting conclusion \(player-facing\)/i)).toBeInTheDocument();
    expect(screen.getByText(/shown to players if the story rests here/i)).toBeInTheDocument();

    const ending = screen.getByLabelText(/this is an ending/i) as HTMLInputElement;
    expect(ending).toBeInTheDocument();
    expect(ending.type).toBe('checkbox');
    expect(ending).not.toBeChecked();
  });

  it('does not render a maturity indicator in create mode', () => {
    setupMocks();
    renderWithProviders(<EpisodeFormDialog {...defaultProps} />);

    expect(screen.queryByTestId('episode-maturity-indicator')).not.toBeInTheDocument();
  });

  it('submits description, summary, resting_conclusion and is_ending in the create body', async () => {
    const user = userEvent.setup();
    const { createMock } = setupMocks();
    createMock.mockImplementation((_vars: unknown, callbacks: Record<string, unknown>) => {
      const cb = callbacks as { onSuccess?: (data: unknown) => void };
      cb.onSuccess?.({ id: 30 });
    });

    renderWithProviders(<EpisodeFormDialog {...defaultProps} />);

    await user.type(screen.getByLabelText(/title/i), 'New Episode');
    await user.type(screen.getByLabelText(/internal gm description/i), 'Secret episode notes');
    await user.type(screen.getByLabelText(/the story so far/i), 'Episode recap text');
    await user.type(
      screen.getByLabelText(/resting conclusion \(player-facing\)/i),
      'A quiet resting place.'
    );
    await user.click(screen.getByLabelText(/this is an ending/i));

    await user.click(screen.getByRole('button', { name: /create episode/i }));

    await waitFor(() => {
      expect(createMock).toHaveBeenCalledWith(
        expect.objectContaining({
          chapter: 4,
          title: 'New Episode',
          description: 'Secret episode notes',
          summary: 'Episode recap text',
          resting_conclusion: 'A quiet resting place.',
          is_ending: true,
        }),
        expect.any(Object)
      );
    });

    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith('Episode created');
    });
  });

  it('prefills all new fields on edit and shows a read-only maturity indicator', () => {
    setupMocks();
    renderWithProviders(<EpisodeFormDialog {...defaultProps} episode={existingEpisode} />);

    expect((screen.getByLabelText(/internal gm description/i) as HTMLTextAreaElement).value).toBe(
      'GM-only episode spoilers.'
    );
    expect((screen.getByLabelText(/the story so far/i) as HTMLTextAreaElement).value).toBe(
      'They reached the gates of the city.'
    );
    expect(
      (screen.getByLabelText(/resting conclusion \(player-facing\)/i) as HTMLTextAreaElement).value
    ).toBe('The party rests, content with their progress.');
    expect(screen.getByLabelText(/this is an ending/i)).toBeChecked();

    const indicator = screen.getByTestId('episode-maturity-indicator');
    expect(indicator).toBeInTheDocument();
    expect(indicator).toHaveTextContent(/pitch/i);
  });

  it('submits the new fields in the update body on edit', async () => {
    const user = userEvent.setup();
    const { updateMock } = setupMocks();
    updateMock.mockImplementation((_vars: unknown, callbacks: Record<string, unknown>) => {
      const cb = callbacks as { onSuccess?: (data: unknown) => void };
      cb.onSuccess?.({ id: 21 });
    });

    renderWithProviders(<EpisodeFormDialog {...defaultProps} episode={existingEpisode} />);

    const summary = screen.getByLabelText(/the story so far/i);
    await user.clear(summary);
    await user.type(summary, 'Updated episode recap');

    // Toggle is_ending off (existing episode has it true)
    await user.click(screen.getByLabelText(/this is an ending/i));

    await user.click(screen.getByRole('button', { name: /save episode/i }));

    await waitFor(() => {
      expect(updateMock).toHaveBeenCalledWith(
        expect.objectContaining({
          id: 21,
          data: expect.objectContaining({
            description: 'GM-only episode spoilers.',
            summary: 'Updated episode recap',
            resting_conclusion: 'The party rests, content with their progress.',
            is_ending: false,
          }),
        }),
        expect.any(Object)
      );
    });
  });
});
