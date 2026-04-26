/**
 * ContributeBeatDialog Tests
 *
 * Covers:
 *  - Dialog opens when "Contribute" button is clicked
 *  - Happy-path submission (mutation called, dialog closes, toast shown)
 *  - DRF field-level validation error rendering
 *  - Client-side min/max points enforcement (submit disabled when invalid)
 */

import { screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { ContributeBeatDialog } from '../components/ContributeBeatDialog';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('../queries', () => ({
  useContributeToBeat: vi.fn(),
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

const mockAggregateBeat = {
  id: 100,
  episode: 10,
  predicate_type: 'aggregate_threshold' as const,
  outcome: 'unsatisfied' as const,
  visibility: 'hinted' as const,
  internal_description: 'Players must collectively earn 50 points',
  player_hint: 'Rally the troops',
  player_resolution_text: undefined,
  order: 1,
  required_level: undefined,
  required_achievement: undefined,
  required_condition_template: undefined,
  required_codex_entry: undefined,
  referenced_story: undefined,
  referenced_milestone_type: undefined,
  referenced_chapter: undefined,
  referenced_episode: undefined,
  required_points: 50,
  agm_eligible: false,
  deadline: undefined,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-04-19T00:00:00Z',
};

const mockResolvedBeat = {
  ...mockAggregateBeat,
  outcome: 'success' as const,
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeContributeMock() {
  const mutateMock = vi.fn();
  vi.mocked(queries.useContributeToBeat).mockReturnValue({
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
  } as unknown as ReturnType<typeof queries.useContributeToBeat>);
  return mutateMock;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('ContributeBeatDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the Contribute button for aggregate beats', () => {
    makeContributeMock();
    renderWithProviders(
      <ContributeBeatDialog beat={mockAggregateBeat} characterSheetId={42} currentTotal={10} />
    );

    expect(screen.getByRole('button', { name: /contribute/i })).toBeInTheDocument();
  });

  it('opens dialog when Contribute button is clicked', async () => {
    const user = userEvent.setup();
    makeContributeMock();
    renderWithProviders(
      <ContributeBeatDialog beat={mockAggregateBeat} characterSheetId={42} currentTotal={10} />
    );

    await user.click(screen.getByRole('button', { name: /contribute/i }));

    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByText(/Rally the troops/i)).toBeInTheDocument();
    expect(screen.getByText(/10 of 50 points reached/i)).toBeInTheDocument();
  });

  it('shows remaining points hint in dialog subtitle', async () => {
    const user = userEvent.setup();
    makeContributeMock();
    renderWithProviders(
      <ContributeBeatDialog beat={mockAggregateBeat} characterSheetId={42} currentTotal={20} />
    );

    await user.click(screen.getByRole('button', { name: /contribute/i }));

    expect(screen.getByText(/30 still needed/i)).toBeInTheDocument();
  });

  it('disables the Contribute trigger button when beat is resolved', () => {
    makeContributeMock();
    renderWithProviders(
      <ContributeBeatDialog beat={mockResolvedBeat} characterSheetId={42} currentTotal={50} />
    );

    const btn = screen.getByRole('button', { name: /contribute/i });
    expect(btn).toBeDisabled();
  });

  it('calls mutation with correct payload on submit', async () => {
    const user = userEvent.setup();
    const mutateMock = makeContributeMock();

    // Make mutate call onSuccess synchronously
    mutateMock.mockImplementation((_vars, callbacks) => {
      callbacks?.onSuccess?.({}, _vars, undefined);
    });

    renderWithProviders(
      <ContributeBeatDialog beat={mockAggregateBeat} characterSheetId={42} currentTotal={10} />
    );

    await user.click(screen.getByRole('button', { name: /contribute/i }));

    // Clear the points input and type a new value
    const pointsInput = screen.getByLabelText(/points/i);
    await user.clear(pointsInput);
    await user.type(pointsInput, '5');

    // Add a source note
    const noteInput = screen.getByLabelText(/source note/i);
    await user.type(noteInput, 'siege battle');

    await user.click(screen.getByRole('button', { name: /submit contribution/i }));

    expect(mutateMock).toHaveBeenCalledWith(
      expect.objectContaining({
        beatId: 100,
        character_sheet: 42,
        points: 5,
        source_note: 'siege battle',
      }),
      expect.any(Object)
    );
  });

  it('closes dialog and shows toast on success', async () => {
    const user = userEvent.setup();
    const mutateMock = makeContributeMock();

    mutateMock.mockImplementation((_vars, callbacks) => {
      callbacks?.onSuccess?.({}, _vars, undefined);
    });

    renderWithProviders(
      <ContributeBeatDialog beat={mockAggregateBeat} characterSheetId={42} currentTotal={0} />
    );

    await user.click(screen.getByRole('button', { name: /contribute/i }));
    await user.click(screen.getByRole('button', { name: /submit contribution/i }));

    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith('Contribution recorded');
    });

    // Dialog should be closed
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('keeps dialog open and shows field errors on validation error', async () => {
    const user = userEvent.setup();
    const mutateMock = makeContributeMock();

    const mockErrorResponse = {
      json: () =>
        Promise.resolve({
          points: ['Ensure this value is greater than or equal to 1.'],
        }),
    };

    mutateMock.mockImplementation((_vars, callbacks) => {
      callbacks?.onError?.({ response: mockErrorResponse }, _vars, undefined);
    });

    renderWithProviders(
      <ContributeBeatDialog beat={mockAggregateBeat} characterSheetId={42} currentTotal={0} />
    );

    await user.click(screen.getByRole('button', { name: /contribute/i }));
    await user.click(screen.getByRole('button', { name: /submit contribution/i }));

    // Dialog should remain open
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).toBeInTheDocument();
    });

    await waitFor(() => {
      expect(
        screen.getByText(/Ensure this value is greater than or equal to 1/i)
      ).toBeInTheDocument();
    });
  });

  it('enforces max points client-side — submit disabled when points exceed remaining', async () => {
    const user = userEvent.setup();
    makeContributeMock();
    renderWithProviders(
      // currentTotal=45, required=50, remaining=5
      <ContributeBeatDialog beat={mockAggregateBeat} characterSheetId={42} currentTotal={45} />
    );

    await user.click(screen.getByRole('button', { name: /contribute/i }));

    const pointsInput = screen.getByLabelText(/points \(max 5\)/i);
    await user.clear(pointsInput);
    await user.type(pointsInput, '10');

    // Submit button should be disabled when points > remaining
    const submitBtn = screen.getByRole('button', { name: /submit contribution/i });
    expect(submitBtn).toBeDisabled();
  });

  it('enforces min 1 points client-side — submit disabled when points = 0', async () => {
    const user = userEvent.setup();
    makeContributeMock();
    renderWithProviders(
      <ContributeBeatDialog beat={mockAggregateBeat} characterSheetId={42} currentTotal={0} />
    );

    await user.click(screen.getByRole('button', { name: /contribute/i }));

    const pointsInput = screen.getByLabelText(/points/i);
    fireEvent.change(pointsInput, { target: { value: '0' } });

    const submitBtn = screen.getByRole('button', { name: /submit contribution/i });
    expect(submitBtn).toBeDisabled();
  });
});
