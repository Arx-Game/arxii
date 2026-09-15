/**
 * Coverage for the witness reaction pop-up (#2987): WitnessReactionOfferGate +
 * WitnessReactionDialog with real hooks (usePendingWitnessWindows /
 * useReactToWindow) and a mocked transport - same pattern as
 * EntryFlourishOfferDialog.test.tsx. apiFetch is mocked for the pending GET;
 * the shared reactToWindow transport (@/scenes/queries) is mocked for the
 * react POST, so the URL and payload it receives are asserted at that seam.
 */

import { render, screen, waitFor, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { vi } from 'vitest';
import type { ReactNode } from 'react';

vi.mock('@/evennia_replacements/api', () => ({
  apiFetch: vi.fn(),
}));

vi.mock('@/scenes/queries', () => ({
  reactToWindow: vi.fn(),
}));

import { apiFetch } from '@/evennia_replacements/api';
import { reactToWindow } from '@/scenes/queries';
import { WitnessReactionOfferGate } from '../components/WitnessReactionOfferGate';
import type { PaginatedPendingReactionWindowList, PendingReactionWindow } from '../queries';

// ---------------------------------------------------------------------------
// Fixtures - the witness kind's three choices, no reactor data anywhere.
// ---------------------------------------------------------------------------

const WINDOW: PendingReactionWindow = {
  id: 5,
  interaction_id: 33,
  scene_id: 101,
  kind: 'witness',
  choices: [
    { slug: 'report', label: 'Report it' },
    { slug: 'intervene', label: 'Step in' },
    { slug: 'ignore', label: 'Look away' },
  ],
};

const PERSONA_ID = 7;

function paginatedWindows(results: PendingReactionWindow[]): PaginatedPendingReactionWindowList {
  return { count: results.length, next: null, previous: null, results };
}

function mockPending(results: PendingReactionWindow[]) {
  vi.mocked(apiFetch).mockResolvedValue({
    ok: true,
    json: async () => paginatedWindows(results),
  } as Response);
}

// ---------------------------------------------------------------------------
// Wrapper - QueryClientProvider only (hooks don't read Redux here)
// ---------------------------------------------------------------------------

function createWrapperWithClient() {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  }
  return { wrapper: Wrapper, client };
}

function renderGate(windows: PendingReactionWindow[], personaId: number | null = PERSONA_ID) {
  mockPending(windows);
  const { wrapper, client } = createWrapperWithClient();
  const view = render(<WitnessReactionOfferGate personaId={personaId} />, { wrapper });
  return { ...view, client };
}

// ---------------------------------------------------------------------------
// Dialog content tests
// ---------------------------------------------------------------------------

describe('WitnessReactionDialog (via WitnessReactionOfferGate)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('auto-opens and renders the three choices from the payload', async () => {
    renderGate([WINDOW]);

    await screen.findByRole('dialog');
    expect(screen.getByTestId('witness-choice-report')).toHaveTextContent('Report it');
    expect(screen.getByTestId('witness-choice-intervene')).toHaveTextContent('Step in');
    expect(screen.getByTestId('witness-choice-ignore')).toHaveTextContent('Look away');
  });

  it('choosing posts the slug to the window react endpoint and dismisses the dialog', async () => {
    const user = userEvent.setup();
    vi.mocked(reactToWindow).mockResolvedValue(undefined);

    renderGate([WINDOW]);

    await screen.findByRole('dialog');
    await user.click(screen.getByTestId('witness-choice-report'));

    await waitFor(() => {
      // reactToWindow POSTs to /api/reaction-windows/{id}/react/.
      expect(reactToWindow).toHaveBeenCalledWith(WINDOW.id, {
        persona_id: PERSONA_ID,
        choice: 'report',
      });
    });
    // Dialog closes after a choice.
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });
  });

  it('a failing react keeps the dialog open and surfaces the server message', async () => {
    const user = userEvent.setup();
    const SERVER_MESSAGE = 'This window has settled.';
    vi.mocked(reactToWindow).mockRejectedValue(new Error(SERVER_MESSAGE));

    renderGate([WINDOW]);

    await screen.findByRole('dialog');
    await user.click(screen.getByTestId('witness-choice-ignore'));

    await waitFor(() => {
      expect(reactToWindow).toHaveBeenCalled();
    });
    const error = await screen.findByTestId('witness-reaction-error');
    expect(error).toHaveAttribute('role', 'alert');
    expect(error).toHaveTextContent(SERVER_MESSAGE);
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('never renders reactor attribution - no persona names or reactor lists appear', async () => {
    renderGate([WINDOW]);

    const dialog = await screen.findByRole('dialog');
    // The payload carries no reactor fields; pin that none leak into the DOM
    // through any future serializer growth being rendered wholesale.
    expect(dialog.textContent).not.toMatch(/reacted|witnessed by|reactor/i);
    expect(screen.queryByTestId('witness-reactor-list')).not.toBeInTheDocument();
  });

  it('renders nothing when there is no pending window or no acting persona', async () => {
    const { unmount } = renderGate([]);

    await waitFor(() => {
      expect(apiFetch).toHaveBeenCalled();
    });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.queryByTestId('witness-reaction-gate-strip')).not.toBeInTheDocument();
    unmount();

    // No persona resolved: never polls, never renders.
    vi.clearAllMocks();
    renderGate([WINDOW], null);
    expect(apiFetch).not.toHaveBeenCalled();
    expect(screen.queryByTestId('witness-reaction-gate-strip')).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Gate auto-open tests - once-per-id bookkeeping mirrors EntryFlourishOfferGate
// ---------------------------------------------------------------------------

describe('WitnessReactionOfferGate - auto-open once per window id', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('auto-opens on a new window; dismissal leaves the strip; same id does not reopen; a new id does', async () => {
    const user = userEvent.setup();
    const { client } = renderGate([WINDOW]);

    // Auto-opens without any user click.
    await screen.findByRole('dialog');

    // Dismiss (Escape) - dialog gone, strip remains, nothing was posted.
    await user.keyboard('{Escape}');
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });
    expect(screen.getByTestId('witness-reaction-gate-strip')).toBeInTheDocument();
    expect(reactToWindow).not.toHaveBeenCalled();

    // Same window id - must not reopen.
    mockPending([{ ...WINDOW }]);
    await act(async () => {
      await client.refetchQueries();
    });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.getByTestId('witness-reaction-gate-strip')).toBeInTheDocument();

    // New window id - must auto-open again.
    mockPending([{ ...WINDOW, id: 6 }]);
    await act(async () => {
      await client.refetchQueries();
    });
    await screen.findByRole('dialog');
  });

  it('re-opens the dialog when the strip is clicked', async () => {
    const user = userEvent.setup();
    renderGate([WINDOW]);

    await screen.findByRole('dialog');
    await user.keyboard('{Escape}');
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });

    await user.click(screen.getByTestId('witness-reaction-gate-strip'));
    await screen.findByRole('dialog');
  });
});
