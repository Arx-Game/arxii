/**
 * SessionRequestStatusCard Tests
 *
 * Covers the status-display states:
 *  - No session request and no event → renders nothing
 *  - Open session request → "Session pending" message
 *  - Scheduled session request → "Session scheduled" message
 *  - Scheduled event with real_time → formatted date
 *  - Resolved session request → "Session resolved"
 */

import { screen } from '@testing-library/react';
import { vi } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { SessionRequestStatusCard } from '../components/SessionRequestStatusCard';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('../queries', () => ({
  useSessionRequest: vi.fn(),
}));

import * as queries from '../queries';

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const baseEntry = {
  story_id: 1,
  story_title: 'A Knights Tale',
  scope: 'character' as const,
  current_episode_id: 10,
  current_episode_title: 'The Journey',
  chapter_title: 'Chapter One',
  status: 'waiting_on_beats',
  status_label: 'Waiting on beats',
  chapter_order: 1,
  episode_order: 2,
  open_session_request_id: null,
  scheduled_event_id: null,
  scheduled_real_time: null,
};

function mockSessionRequest(status: string) {
  vi.mocked(queries.useSessionRequest).mockReturnValue({
    data: { id: 5, episode: 10, status, event: null, open_to_any_gm: false },
    isLoading: false,
    isSuccess: true,
    error: null,
  } as unknown as ReturnType<typeof queries.useSessionRequest>);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('SessionRequestStatusCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Default: no session request data
    vi.mocked(queries.useSessionRequest).mockReturnValue({
      data: undefined,
      isLoading: false,
      isSuccess: false,
      error: null,
    } as unknown as ReturnType<typeof queries.useSessionRequest>);
  });

  it('renders nothing when no session request and no event', () => {
    const { container } = renderWithProviders(
      <SessionRequestStatusCard
        activeEntry={{ ...baseEntry, open_session_request_id: null, scheduled_event_id: null }}
      />
    );
    expect(container.firstChild).toBeNull();
  });

  it('shows pending message for an open session request', () => {
    mockSessionRequest('open');
    renderWithProviders(
      <SessionRequestStatusCard activeEntry={{ ...baseEntry, open_session_request_id: 5 }} />
    );

    expect(screen.getByText(/Session pending — your GM has been notified/i)).toBeInTheDocument();
  });

  it('shows scheduled message when session request status is scheduled', () => {
    mockSessionRequest('scheduled');
    renderWithProviders(
      <SessionRequestStatusCard activeEntry={{ ...baseEntry, open_session_request_id: 5 }} />
    );

    expect(
      screen.getByText(/Session scheduled — your GM is finalising the event/i)
    ).toBeInTheDocument();
  });

  it('shows resolved message when session request status is resolved', () => {
    mockSessionRequest('resolved');
    renderWithProviders(
      <SessionRequestStatusCard activeEntry={{ ...baseEntry, open_session_request_id: 5 }} />
    );

    expect(screen.getByText(/Session resolved/i)).toBeInTheDocument();
  });

  it('shows fallback message while session request data is loading', () => {
    // useSessionRequest returns undefined data (loading)
    renderWithProviders(
      <SessionRequestStatusCard activeEntry={{ ...baseEntry, open_session_request_id: 5 }} />
    );

    expect(screen.getByText(/Episode ready — GM scheduling required/i)).toBeInTheDocument();
  });

  it('shows scheduled event panel with formatted date when scheduled_event_id is set', () => {
    renderWithProviders(
      <SessionRequestStatusCard
        activeEntry={{
          ...baseEntry,
          open_session_request_id: null,
          scheduled_event_id: 99,
          scheduled_real_time: '2026-06-15T18:00:00Z',
        }}
      />
    );

    // Component shows "Scheduled for <formatted date>" when real_time is available
    expect(screen.getByText(/scheduled for/i)).toBeInTheDocument();
    expect(screen.getByText(/Your GM will run this session/i)).toBeInTheDocument();
  });

  it('shows generic scheduled message when event exists but no real_time', () => {
    renderWithProviders(
      <SessionRequestStatusCard
        activeEntry={{
          ...baseEntry,
          open_session_request_id: null,
          scheduled_event_id: 99,
          scheduled_real_time: null,
        }}
      />
    );

    expect(screen.getByText(/Session has been scheduled/i)).toBeInTheDocument();
  });
});
