/**
 * MarkBeatDialog Tests
 *
 * Covers:
 *  - Dialog opens/closes on trigger
 *  - Outcome radio pre-selects "success" by default
 *  - Submit happy path → mutation called with right payload, dialog closes, toast shown
 *  - Validation error rendering
 *  - Mutation error doesn't close the dialog
 */

import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { MarkBeatDialog } from '../components/MarkBeatDialog';
import type { Beat } from '../types';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('../queries', () => ({
  useMarkBeat: vi.fn(),
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

const mockGmMarkedBeat: Beat = {
  id: 200,
  episode: 10,
  episode_title: 'Test Episode',
  chapter_title: 'Test Chapter',
  story_id: 1,
  story_title: 'Test Story',
  predicate_type: 'gm_marked',
  outcome: 'unsatisfied',
  visibility: 'hinted',
  internal_description: 'The villain escapes or is captured',
  player_hint: 'Confront the villain',
  player_resolution_text: undefined,
  order: 2,
  required_level: undefined,
  required_achievement: undefined,
  required_condition_template: undefined,
  required_codex_entry: undefined,
  referenced_story: undefined,
  referenced_milestone_type: undefined,
  referenced_chapter: undefined,
  referenced_episode: undefined,
  required_points: undefined,
  agm_eligible: false,
  deadline: undefined,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-04-19T00:00:00Z',
  can_mark: true,
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeMarkMock() {
  const mutateMock = vi.fn();
  vi.mocked(queries.useMarkBeat).mockReturnValue({
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
  } as unknown as ReturnType<typeof queries.useMarkBeat>);
  return mutateMock;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('MarkBeatDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the Mark button', () => {
    makeMarkMock();
    renderWithProviders(<MarkBeatDialog beat={mockGmMarkedBeat} />);
    expect(screen.getByRole('button', { name: /mark/i })).toBeInTheDocument();
  });

  it('opens dialog when Mark button is clicked', async () => {
    const user = userEvent.setup();
    makeMarkMock();
    renderWithProviders(<MarkBeatDialog beat={mockGmMarkedBeat} />);

    await user.click(screen.getByRole('button', { name: /mark/i }));

    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByText(/Confront the villain/i)).toBeInTheDocument();
  });

  it('pre-selects "success" outcome by default', async () => {
    const user = userEvent.setup();
    makeMarkMock();
    renderWithProviders(<MarkBeatDialog beat={mockGmMarkedBeat} />);

    await user.click(screen.getByRole('button', { name: /mark/i }));

    const radios = screen.getAllByRole('radio');
    const successRadio = radios.find(
      (r) => (r as HTMLInputElement).value === 'success'
    ) as HTMLInputElement;
    expect(successRadio).toBeChecked();
  });

  it('calls mutation with correct payload on submit', async () => {
    const user = userEvent.setup();
    const mutateMock = makeMarkMock();

    mutateMock.mockImplementation((_vars, callbacks) => {
      callbacks?.onSuccess?.({}, _vars, undefined);
    });

    renderWithProviders(<MarkBeatDialog beat={mockGmMarkedBeat} />);

    await user.click(screen.getByRole('button', { name: /mark/i }));

    // Select failure
    const radios = screen.getAllByRole('radio');
    const failureRadio = radios.find(
      (r) => (r as HTMLInputElement).value === 'failure'
    ) as HTMLInputElement;
    await user.click(failureRadio);

    const notesInput = screen.getByLabelText(/gm notes/i);
    await user.type(notesInput, 'villain escaped');

    await user.click(screen.getByRole('button', { name: /mark beat/i }));

    expect(mutateMock).toHaveBeenCalledWith(
      expect.objectContaining({
        beatId: 200,
        outcome: 'failure',
        gm_notes: 'villain escaped',
      }),
      expect.any(Object)
    );
  });

  it('closes dialog and shows toast on success', async () => {
    const user = userEvent.setup();
    const mutateMock = makeMarkMock();

    mutateMock.mockImplementation((_vars, callbacks) => {
      callbacks?.onSuccess?.({}, _vars, undefined);
    });

    renderWithProviders(<MarkBeatDialog beat={mockGmMarkedBeat} />);
    await user.click(screen.getByRole('button', { name: /mark/i }));
    await user.click(screen.getByRole('button', { name: /mark beat/i }));

    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith('Beat marked');
    });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('keeps dialog open and shows error banner on validation error', async () => {
    const user = userEvent.setup();
    const mutateMock = makeMarkMock();

    const mockErrorResponse = {
      json: () =>
        Promise.resolve({
          non_field_errors: ['Only GM_MARKED beats can be resolved via the mark endpoint.'],
        }),
    };

    mutateMock.mockImplementation((_vars, callbacks) => {
      callbacks?.onError?.({ response: mockErrorResponse }, _vars, undefined);
    });

    renderWithProviders(<MarkBeatDialog beat={mockGmMarkedBeat} />);
    await user.click(screen.getByRole('button', { name: /mark/i }));
    await user.click(screen.getByRole('button', { name: /mark beat/i }));

    await waitFor(() => {
      expect(screen.queryByRole('dialog')).toBeInTheDocument();
    });

    await waitFor(() => {
      expect(
        screen.getByText(/Only GM_MARKED beats can be resolved via the mark endpoint/i)
      ).toBeInTheDocument();
    });
  });

  it('closes dialog on Cancel button click', async () => {
    const user = userEvent.setup();
    makeMarkMock();
    renderWithProviders(<MarkBeatDialog beat={mockGmMarkedBeat} />);

    await user.click(screen.getByRole('button', { name: /mark/i }));
    expect(screen.getByRole('dialog')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /cancel/i }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
});
