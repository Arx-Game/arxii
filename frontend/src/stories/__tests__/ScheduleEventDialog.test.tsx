/**
 * ScheduleEventDialog Tests
 *
 * Covers:
 *  - Dialog opens/closes on trigger (only for OPEN requests)
 *  - Required field validation (submit disabled when name/time/persona/location absent)
 *  - Persona search renders results and allows selection
 *  - Submit happy path → mutation called with right payload, dialog closes, toast shown
 *  - Non-field validation error rendering
 *  - Mutation error doesn't close the dialog
 */

import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { ScheduleEventDialog } from '../components/ScheduleEventDialog';
import type { GMQueueAssignedRequest } from '../types';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('../queries', () => ({
  useCreateEventFromSessionRequest: vi.fn(),
}));

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

// Mock AreaDrilldownPicker to avoid area API calls in tests
vi.mock('@/events/components/AreaDrilldownPicker', () => ({
  AreaDrilldownPicker: ({
    value,
    onChange,
  }: {
    value: number | null;
    onChange: (id: number | null) => void;
  }) => (
    <div data-testid="area-picker">
      {value === null ? (
        <button type="button" onClick={() => onChange(42)}>
          Select room
        </button>
      ) : (
        <span>Room selected: {value}</span>
      )}
    </div>
  ),
}));

// Mock searchPersonas
vi.mock('@/events/queries', () => ({
  searchPersonas: vi.fn(),
}));

// Mock toLocalDatetimeValue to avoid timezone issues in tests
vi.mock('@/events/types', () => ({
  toLocalDatetimeValue: (iso: string) => iso.slice(0, 16),
}));

import * as queries from '../queries';
import * as eventsQueries from '@/events/queries';
import { toast } from 'sonner';

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const openRequest: GMQueueAssignedRequest = {
  session_request_id: 99,
  episode_id: 10,
  episode_title: 'The Reckoning',
  story_title: 'The Long Road',
  status: 'open',
  event_id: null,
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeCreateMock() {
  const mutateMock = vi.fn();
  vi.mocked(queries.useCreateEventFromSessionRequest).mockReturnValue({
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
  } as unknown as ReturnType<typeof queries.useCreateEventFromSessionRequest>);
  return mutateMock;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('ScheduleEventDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(eventsQueries.searchPersonas).mockResolvedValue([
      { id: 1, name: 'Lady Avaris' },
      { id: 2, name: 'Lord Brennan' },
    ]);
  });

  it('renders the Schedule button for OPEN requests', () => {
    makeCreateMock();
    renderWithProviders(<ScheduleEventDialog request={openRequest} />);
    expect(screen.getByRole('button', { name: /schedule/i })).toBeInTheDocument();
  });

  it('opens dialog when Schedule button is clicked', async () => {
    const user = userEvent.setup();
    makeCreateMock();
    renderWithProviders(<ScheduleEventDialog request={openRequest} />);

    await user.click(screen.getByRole('button', { name: /schedule/i }));

    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByText(/Schedule session for: The Reckoning/i)).toBeInTheDocument();
  });

  it('defaults event name to story — episode format', async () => {
    const user = userEvent.setup();
    makeCreateMock();
    renderWithProviders(<ScheduleEventDialog request={openRequest} />);

    await user.click(screen.getByRole('button', { name: /schedule/i }));

    const nameInput = screen.getByLabelText(/event name/i) as HTMLInputElement;
    expect(nameInput.value).toBe('The Long Road — The Reckoning');
  });

  it('submit is disabled until all required fields are filled', async () => {
    const user = userEvent.setup();
    makeCreateMock();
    renderWithProviders(<ScheduleEventDialog request={openRequest} />);

    await user.click(screen.getByRole('button', { name: /schedule/i }));

    const submitBtn = screen.getByRole('button', { name: /schedule event/i });
    // No time, no persona, no room — should be disabled
    expect(submitBtn).toBeDisabled();
  });

  it('shows persona search results and allows selection', async () => {
    const user = userEvent.setup();
    makeCreateMock();
    renderWithProviders(<ScheduleEventDialog request={openRequest} />);

    await user.click(screen.getByRole('button', { name: /schedule/i }));

    const personaInput = screen.getByPlaceholderText(/search for a persona/i);
    await user.type(personaInput, 'Lady');

    await waitFor(() => {
      expect(screen.getByText('Lady Avaris')).toBeInTheDocument();
    });

    await user.click(screen.getByText('Lady Avaris'));

    // Should now show the selected persona
    expect(screen.getByText('Lady Avaris')).toBeInTheDocument();
    // Input should be gone
    expect(screen.queryByPlaceholderText(/search for a persona/i)).not.toBeInTheDocument();
  });

  it('calls mutation with correct payload on submit', async () => {
    const user = userEvent.setup();
    const mutateMock = makeCreateMock();

    mutateMock.mockImplementation((_vars, callbacks) => {
      callbacks?.onSuccess?.({ event: 88 }, _vars, undefined);
    });

    renderWithProviders(<ScheduleEventDialog request={openRequest} />);

    await user.click(screen.getByRole('button', { name: /schedule/i }));

    // Fill name
    const nameInput = screen.getByLabelText(/event name/i);
    await user.clear(nameInput);
    await user.type(nameInput, 'Custom Session Name');

    // Fill time
    const timeInput = screen.getByLabelText(/scheduled time/i);
    await user.type(timeInput, '2026-05-01T18:00');

    // Select persona
    const personaInput = screen.getByPlaceholderText(/search for a persona/i);
    await user.type(personaInput, 'Lady');
    await waitFor(() => screen.getByText('Lady Avaris'));
    await user.click(screen.getByText('Lady Avaris'));

    // Select room via mocked picker
    await user.click(screen.getByRole('button', { name: /select room/i }));

    await user.click(screen.getByRole('button', { name: /schedule event/i }));

    expect(mutateMock).toHaveBeenCalledWith(
      expect.objectContaining({
        requestId: 99,
        name: 'Custom Session Name',
        host_persona: 1,
        location_id: 42,
        is_public: true,
      }),
      expect.any(Object)
    );
  });

  it('closes dialog and shows toast on success', async () => {
    const user = userEvent.setup();
    const mutateMock = makeCreateMock();

    mutateMock.mockImplementation((_vars, callbacks) => {
      callbacks?.onSuccess?.({ event: 88 }, _vars, undefined);
    });

    renderWithProviders(<ScheduleEventDialog request={openRequest} />);

    await user.click(screen.getByRole('button', { name: /schedule/i }));

    // Fill required fields minimally
    const timeInput = screen.getByLabelText(/scheduled time/i);
    await user.type(timeInput, '2026-05-01T18:00');

    const personaInput = screen.getByPlaceholderText(/search for a persona/i);
    await user.type(personaInput, 'Lady');
    await waitFor(() => screen.getByText('Lady Avaris'));
    await user.click(screen.getByText('Lady Avaris'));

    await user.click(screen.getByRole('button', { name: /select room/i }));

    await user.click(screen.getByRole('button', { name: /schedule event/i }));

    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith(expect.stringContaining('Event scheduled'));
    });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('keeps dialog open and shows error banner on validation error', async () => {
    const user = userEvent.setup();
    const mutateMock = makeCreateMock();

    const mockErrorResponse = {
      json: () =>
        Promise.resolve({
          non_field_errors: ['Only OPEN session requests can be scheduled.'],
        }),
    };

    mutateMock.mockImplementation((_vars, callbacks) => {
      callbacks?.onError?.({ response: mockErrorResponse }, _vars, undefined);
    });

    renderWithProviders(<ScheduleEventDialog request={openRequest} />);

    await user.click(screen.getByRole('button', { name: /schedule/i }));

    const timeInput = screen.getByLabelText(/scheduled time/i);
    await user.type(timeInput, '2026-05-01T18:00');

    const personaInput = screen.getByPlaceholderText(/search for a persona/i);
    await user.type(personaInput, 'Lady');
    await waitFor(() => screen.getByText('Lady Avaris'));
    await user.click(screen.getByText('Lady Avaris'));

    await user.click(screen.getByRole('button', { name: /select room/i }));

    await user.click(screen.getByRole('button', { name: /schedule event/i }));

    await waitFor(() => {
      expect(screen.queryByRole('dialog')).toBeInTheDocument();
    });

    await waitFor(() => {
      expect(screen.getByText(/Only OPEN session requests can be scheduled/i)).toBeInTheDocument();
    });
  });

  it('closes dialog on Cancel button click', async () => {
    const user = userEvent.setup();
    makeCreateMock();
    renderWithProviders(<ScheduleEventDialog request={openRequest} />);

    await user.click(screen.getByRole('button', { name: /schedule/i }));
    expect(screen.getByRole('dialog')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /cancel/i }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
});
