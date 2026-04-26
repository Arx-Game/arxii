/**
 * BeatFormDialog Tests — Task 9.2
 *
 * Covers:
 *  - gm_marked predicate type: no config fields
 *  - character_level_at_least: required_level field appears
 *  - aggregate_threshold: required_points field appears
 *  - story_at_milestone: milestone-type-conditional fields
 *  - Switching predicate type clears config values
 *  - Submit happy path for gm_marked
 *  - Submit happy path for aggregate_threshold
 *  - DRF validation errors surface inline
 */

import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { BeatFormDialog } from '../components/BeatFormDialog';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('../queries', () => ({
  useCreateBeat: vi.fn(),
  useUpdateBeat: vi.fn(),
  useStoryList: vi.fn(),
  useChapterList: vi.fn(),
  useEpisodeList: vi.fn(),
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

import * as queries from '../queries';
import { toast } from 'sonner';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeMutationMock(hookName: 'useCreateBeat' | 'useUpdateBeat') {
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
  const createMock = makeMutationMock('useCreateBeat');
  makeMutationMock('useUpdateBeat');

  vi.mocked(queries.useStoryList).mockReturnValue({
    data: { count: 0, results: [], next: null, previous: null },
    isLoading: false,
    isError: false,
    error: null,
  } as unknown as ReturnType<typeof queries.useStoryList>);

  vi.mocked(queries.useChapterList).mockReturnValue({
    data: { count: 0, results: [], next: null, previous: null },
    isLoading: false,
    isError: false,
    error: null,
  } as unknown as ReturnType<typeof queries.useChapterList>);

  vi.mocked(queries.useEpisodeList).mockReturnValue({
    data: { count: 0, results: [], next: null, previous: null },
    isLoading: false,
    isError: false,
    error: null,
  } as unknown as ReturnType<typeof queries.useEpisodeList>);

  return createMock;
}

const defaultProps = {
  open: true,
  onOpenChange: vi.fn(),
  episodeId: 42,
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('BeatFormDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders Create Beat dialog', () => {
    setupMocks();
    renderWithProviders(<BeatFormDialog {...defaultProps} />);
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Create Beat' })).toBeInTheDocument();
  });

  it('gm_marked is selected by default and shows no extra config', () => {
    setupMocks();
    renderWithProviders(<BeatFormDialog {...defaultProps} />);

    // gm_marked radio should be selected
    const predicateGroup = screen.getByTestId('predicate-type-group');
    const gmMarkedRadio = within(predicateGroup).getByRole('radio', { name: /gm marked/i });
    expect(gmMarkedRadio).toBeChecked();

    // No level/points fields visible
    expect(screen.queryByLabelText(/required level/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/required points/i)).not.toBeInTheDocument();
  });

  it('character_level_at_least predicate shows required_level field', async () => {
    const user = userEvent.setup();
    setupMocks();
    renderWithProviders(<BeatFormDialog {...defaultProps} />);

    const predicateGroup = screen.getByTestId('predicate-type-group');
    const levelRadio = within(predicateGroup).getByRole('radio', {
      name: /character level at least/i,
    });
    await user.click(levelRadio);

    expect(screen.getByLabelText(/required level/i)).toBeInTheDocument();
  });

  it('aggregate_threshold predicate shows required_points field', async () => {
    const user = userEvent.setup();
    setupMocks();
    renderWithProviders(<BeatFormDialog {...defaultProps} />);

    const predicateGroup = screen.getByTestId('predicate-type-group');
    const thresholdRadio = within(predicateGroup).getByRole('radio', {
      name: /aggregate threshold/i,
    });
    await user.click(thresholdRadio);

    expect(screen.getByLabelText(/required points/i)).toBeInTheDocument();
  });

  it('switching predicate type clears previous config value', async () => {
    const user = userEvent.setup();
    setupMocks();
    renderWithProviders(<BeatFormDialog {...defaultProps} />);

    const predicateGroup = screen.getByTestId('predicate-type-group');

    // Select character_level_at_least and fill required_level
    await user.click(
      within(predicateGroup).getByRole('radio', { name: /character level at least/i })
    );
    const levelInput = screen.getByLabelText(/required level/i);
    await user.type(levelInput, '10');
    expect((levelInput as HTMLInputElement).value).toBe('10');

    // Switch to aggregate_threshold — required_level field gone, required_points appears blank
    await user.click(within(predicateGroup).getByRole('radio', { name: /aggregate threshold/i }));
    expect(screen.queryByLabelText(/required level/i)).not.toBeInTheDocument();
    const pointsInput = screen.getByLabelText(/required points/i);
    expect((pointsInput as HTMLInputElement).value).toBe('');
  });

  it('story_at_milestone shows milestone-type selector', async () => {
    const user = userEvent.setup();
    setupMocks();
    renderWithProviders(<BeatFormDialog {...defaultProps} />);

    const predicateGroup = screen.getByTestId('predicate-type-group');
    await user.click(within(predicateGroup).getByRole('radio', { name: /story at milestone/i }));

    // Referenced Story and Milestone Type comboboxes should appear
    expect(screen.getByText('Referenced Story')).toBeInTheDocument();
    expect(screen.getByText('Milestone Type')).toBeInTheDocument();
  });

  it('submits gm_marked beat with correct payload', async () => {
    const user = userEvent.setup();
    const createMock = setupMocks();

    createMock.mockImplementation((_vars: unknown, callbacks: Record<string, unknown>) => {
      const cb = callbacks as { onSuccess?: (data: unknown) => void };
      cb.onSuccess?.({ id: 99 });
    });

    renderWithProviders(<BeatFormDialog {...defaultProps} />);

    const descInput = screen.getByLabelText(/internal description/i);
    await user.type(descInput, 'A GM-marked beat description');

    await user.click(screen.getByRole('button', { name: /create beat/i }));

    await waitFor(() => {
      expect(createMock).toHaveBeenCalledWith(
        expect.objectContaining({
          episode: 42,
          predicate_type: 'gm_marked',
          internal_description: 'A GM-marked beat description',
        }),
        expect.any(Object)
      );
    });

    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith('Beat created');
    });
  });

  it('submits aggregate_threshold beat with required_points', async () => {
    const user = userEvent.setup();
    const createMock = setupMocks();

    createMock.mockImplementation((_vars: unknown, callbacks: Record<string, unknown>) => {
      const cb = callbacks as { onSuccess?: (data: unknown) => void };
      cb.onSuccess?.({ id: 100 });
    });

    renderWithProviders(<BeatFormDialog {...defaultProps} />);

    const predicateGroup = screen.getByTestId('predicate-type-group');
    await user.click(within(predicateGroup).getByRole('radio', { name: /aggregate threshold/i }));

    const pointsInput = screen.getByLabelText(/required points/i);
    await user.type(pointsInput, '100');

    const descInput = screen.getByLabelText(/internal description/i);
    await user.type(descInput, 'Threshold beat');

    await user.click(screen.getByRole('button', { name: /create beat/i }));

    await waitFor(() => {
      expect(createMock).toHaveBeenCalledWith(
        expect.objectContaining({
          predicate_type: 'aggregate_threshold',
          required_points: 100,
        }),
        expect.any(Object)
      );
    });
  });

  it('surfaces DRF validation error inline', async () => {
    const user = userEvent.setup();
    const createMock = setupMocks();

    const mockErrorResponse = {
      json: () => Promise.resolve({ player_hint: ['This field is too long.'] }),
    };

    createMock.mockImplementation((_vars: unknown, callbacks: Record<string, unknown>) => {
      const cb = callbacks as { onError?: (err: unknown) => void };
      cb.onError?.({ response: mockErrorResponse });
    });

    renderWithProviders(<BeatFormDialog {...defaultProps} />);

    // Fill in the required internal description to pass HTML5 validation
    const descInput = screen.getByLabelText(/internal description/i);
    await user.type(descInput, 'Some beat description');

    await user.click(screen.getByRole('button', { name: /create beat/i }));

    await waitFor(() => {
      expect(screen.getByText(/this field is too long/i)).toBeInTheDocument();
    });

    // Dialog stays open
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('converts deadline to UTC ISO string before submission', async () => {
    const user = userEvent.setup();
    const createMock = setupMocks();

    createMock.mockImplementation((_vars: unknown, callbacks: Record<string, unknown>) => {
      const cb = callbacks as { onSuccess?: (data: unknown) => void };
      cb.onSuccess?.({ id: 101 });
    });

    renderWithProviders(<BeatFormDialog {...defaultProps} />);

    const descInput = screen.getByLabelText(/internal description/i);
    await user.type(descInput, 'Beat with deadline');

    // Fill in the deadline datetime-local input
    const deadlineInput = screen.getByLabelText(/deadline/i);
    await user.type(deadlineInput, '2026-05-01T14:00');

    await user.click(screen.getByRole('button', { name: /create beat/i }));

    await waitFor(() => {
      expect(createMock).toHaveBeenCalledWith(
        expect.objectContaining({
          // Must be a full ISO 8601 string with timezone offset, not a bare local string.
          deadline: expect.stringMatching(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$/),
        }),
        expect.any(Object)
      );
    });
  });

  it('renders in edit mode pre-populated', () => {
    setupMocks();
    const existingBeat = {
      id: 5,
      episode: 42,
      predicate_type: 'character_level_at_least' as const,
      required_level: 7,
      outcome: 'unsatisfied' as const,
      visibility: 'hinted' as const,
      internal_description: 'Must be at least level 7',
      player_hint: 'A level threshold',
      player_resolution_text: undefined,
      order: 1,
      agm_eligible: false,
      deadline: null,
      required_achievement: null,
      required_condition_template: null,
      required_codex_entry: null,
      referenced_story: null,
      referenced_milestone_type: undefined,
      referenced_chapter: null,
      referenced_episode: null,
      required_points: null,
      episode_title: 'Test Episode',
      chapter_title: 'Chapter 1',
      story_id: 1,
      story_title: 'Test Story',
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    };

    renderWithProviders(<BeatFormDialog {...defaultProps} beat={existingBeat} />);

    expect(screen.getByText('Edit Beat')).toBeInTheDocument();
    const descInput = screen.getByLabelText(/internal description/i);
    expect((descInput as HTMLInputElement).value).toBe('Must be at least level 7');
    expect(screen.getByLabelText(/required level/i)).toBeInTheDocument();
  });
});
