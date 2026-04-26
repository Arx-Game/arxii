/**
 * ResolveEpisodeDialog Tests
 *
 * Covers:
 *  - Dialog opens/closes on trigger
 *  - Auto transition pre-selection when exactly one AUTO transition
 *  - Submit happy path → mutation called with right payload, dialog closes, toast shown
 *  - Validation error rendering (non_field_errors banner)
 *  - Mutation error doesn't close the dialog
 */

import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { ResolveEpisodeDialog } from '../components/ResolveEpisodeDialog';
import type { GMQueueEpisodeEntry } from '../types';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('../queries', () => ({
  useResolveEpisode: vi.fn(),
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

const entryOneAuto: GMQueueEpisodeEntry = {
  story_id: 1,
  story_title: 'The Long Road',
  scope: 'character',
  episode_id: 10,
  episode_title: 'The Reckoning',
  progress_type: 'character',
  progress_id: 5,
  eligible_transitions: [{ transition_id: 1, mode: 'AUTO' }],
  open_session_request_id: null,
};

const entryMultiTransition: GMQueueEpisodeEntry = {
  ...entryOneAuto,
  eligible_transitions: [
    { transition_id: 1, mode: 'AUTO' },
    { transition_id: 2, mode: 'GM_CHOICE' },
  ],
};

const entryNoTransitions: GMQueueEpisodeEntry = {
  ...entryOneAuto,
  eligible_transitions: [],
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeResolveMock() {
  const mutateMock = vi.fn();
  vi.mocked(queries.useResolveEpisode).mockReturnValue({
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
  } as unknown as ReturnType<typeof queries.useResolveEpisode>);
  return mutateMock;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('ResolveEpisodeDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the Resolve button', () => {
    makeResolveMock();
    renderWithProviders(<ResolveEpisodeDialog entry={entryOneAuto} />);
    expect(screen.getByRole('button', { name: /resolve/i })).toBeInTheDocument();
  });

  it('opens dialog when Resolve button is clicked', async () => {
    const user = userEvent.setup();
    makeResolveMock();
    renderWithProviders(<ResolveEpisodeDialog entry={entryOneAuto} />);

    await user.click(screen.getByRole('button', { name: /resolve/i }));

    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByText(/Resolve Episode: The Reckoning/i)).toBeInTheDocument();
    expect(screen.getByText(/The Long Road/i)).toBeInTheDocument();
  });

  it('pre-selects the single AUTO transition', async () => {
    const user = userEvent.setup();
    makeResolveMock();
    renderWithProviders(<ResolveEpisodeDialog entry={entryOneAuto} />);

    await user.click(screen.getByRole('button', { name: /resolve/i }));

    const radioInputs = screen.getAllByRole('radio');
    // First radio (AUTO transition) should be pre-selected
    expect(radioInputs[0]).toBeChecked();
  });

  it('shows no pre-selection of transition options with multiple transitions', async () => {
    const user = userEvent.setup();
    makeResolveMock();
    renderWithProviders(<ResolveEpisodeDialog entry={entryMultiTransition} />);

    await user.click(screen.getByRole('button', { name: /resolve/i }));

    const radioInputs = screen.getAllByRole('radio');
    // 2 transition radios + 1 "advance to frontier" option = 3 total
    expect(radioInputs.length).toBe(3);
    // The two transition radios should NOT be checked
    // (the "frontier" radio maps to null and is the default)
    const transitionRadios = radioInputs.slice(0, 2);
    transitionRadios.forEach((r) => {
      expect(r as HTMLInputElement).not.toBeChecked();
    });
  });

  it('shows no-eligible-transitions message when empty', async () => {
    const user = userEvent.setup();
    makeResolveMock();
    renderWithProviders(<ResolveEpisodeDialog entry={entryNoTransitions} />);

    await user.click(screen.getByRole('button', { name: /resolve/i }));

    expect(screen.getByText(/No eligible transitions/i)).toBeInTheDocument();
  });

  it('calls mutation with correct payload on submit', async () => {
    const user = userEvent.setup();
    const mutateMock = makeResolveMock();

    mutateMock.mockImplementation((_vars, callbacks) => {
      callbacks?.onSuccess?.({}, _vars, undefined);
    });

    renderWithProviders(<ResolveEpisodeDialog entry={entryOneAuto} />);

    await user.click(screen.getByRole('button', { name: /resolve/i }));

    const notesInput = screen.getByLabelText(/gm notes/i);
    await user.type(notesInput, 'Story resolved!');

    await user.click(screen.getByRole('button', { name: /resolve episode/i }));

    expect(mutateMock).toHaveBeenCalledWith(
      expect.objectContaining({
        episodeId: 10,
        chosen_transition: 1,
        gm_notes: 'Story resolved!',
      }),
      expect.any(Object)
    );
  });

  it('closes dialog and shows toast on success', async () => {
    const user = userEvent.setup();
    const mutateMock = makeResolveMock();

    mutateMock.mockImplementation((_vars, callbacks) => {
      callbacks?.onSuccess?.({}, _vars, undefined);
    });

    renderWithProviders(<ResolveEpisodeDialog entry={entryOneAuto} />);
    await user.click(screen.getByRole('button', { name: /resolve/i }));
    await user.click(screen.getByRole('button', { name: /resolve episode/i }));

    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith('Episode resolved');
    });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('keeps dialog open and shows non_field_errors on validation error', async () => {
    const user = userEvent.setup();
    const mutateMock = makeResolveMock();

    const mockErrorResponse = {
      json: () =>
        Promise.resolve({
          non_field_errors: ['No active progress record found for this episode.'],
        }),
    };

    mutateMock.mockImplementation((_vars, callbacks) => {
      callbacks?.onError?.({ response: mockErrorResponse }, _vars, undefined);
    });

    renderWithProviders(<ResolveEpisodeDialog entry={entryOneAuto} />);
    await user.click(screen.getByRole('button', { name: /resolve/i }));
    await user.click(screen.getByRole('button', { name: /resolve episode/i }));

    await waitFor(() => {
      expect(screen.queryByRole('dialog')).toBeInTheDocument();
    });

    await waitFor(() => {
      expect(
        screen.getByText(/No active progress record found for this episode/i)
      ).toBeInTheDocument();
    });
  });

  it('closes dialog on Cancel button click', async () => {
    const user = userEvent.setup();
    makeResolveMock();
    renderWithProviders(<ResolveEpisodeDialog entry={entryOneAuto} />);

    await user.click(screen.getByRole('button', { name: /resolve/i }));
    expect(screen.getByRole('dialog')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /cancel/i }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
});
