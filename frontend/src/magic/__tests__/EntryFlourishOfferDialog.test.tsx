/**
 * Coverage for the entry-flourish offer ceremony (#1140):
 * EntryFlourishOfferGate + dialog with real hooks
 * (usePendingEntryFlourishOffers / useRespondToEntryFlourish /
 * useCharacterResonances) and a mocked api transport — same pattern as
 * AudereOfferDialog.test.tsx.
 */

import { render, screen, waitFor, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { vi } from 'vitest';
import type { ReactNode } from 'react';
import { EntryFlourishOfferGate } from '../components/EntryFlourishOfferGate';
import type {
  PaginatedPendingEntryFlourishOfferList,
  PendingEntryFlourishOffer,
  CharacterResonance,
  EntryFlourishResult,
} from '../types';

// ---------------------------------------------------------------------------
// Mock the api transport — real hooks run against these.
// ---------------------------------------------------------------------------

vi.mock('../api', () => ({
  getPendingEntryFlourishOffers: vi.fn(),
  respondToEntryFlourish: vi.fn(),
  getCharacterResonances: vi.fn(),
}));

import * as api from '../api';

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const OFFER: PendingEntryFlourishOffer = {
  id: 9,
  character_sheet_id: 4,
  scene_id: 101,
  created_at: '2026-06-15T00:00:00Z',
};

const RESONANCES: CharacterResonance[] = [
  {
    id: 1,
    character_sheet: 4,
    resonance: 7,
    resonance_name: 'Ember',
    resonance_detail: {
      id: 7,
      name: 'Ember',
      affinity: 1,
      affinity_name: 'Fire',
      description: 'Fire resonance.',
      codex_entry_id: null,
    },
    balance: 10,
    lifetime_earned: 20,
    claimed_at: '2026-01-01T00:00:00Z',
  },
  {
    id: 2,
    character_sheet: 4,
    resonance: 8,
    resonance_name: 'Tide',
    resonance_detail: {
      id: 8,
      name: 'Tide',
      affinity: 2,
      affinity_name: 'Water',
      description: 'Water resonance.',
      codex_entry_id: null,
    },
    balance: 5,
    lifetime_earned: 5,
    claimed_at: '2026-01-01T00:00:00Z',
  },
];

const RESULT: EntryFlourishResult = {
  resonance_id: 7,
  resonance_name: 'Ember',
  granted_amount: 5,
  scene_id: 101,
};

function paginatedOffers(
  results: PendingEntryFlourishOffer[]
): PaginatedPendingEntryFlourishOfferList {
  return { count: results.length, next: null, previous: null, results };
}

// ---------------------------------------------------------------------------
// Wrapper — QueryClientProvider only (hooks don't read Redux here)
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

function renderGate(
  offers: PendingEntryFlourishOffer[],
  resonances: CharacterResonance[] = RESONANCES
) {
  vi.mocked(api.getPendingEntryFlourishOffers).mockResolvedValue(paginatedOffers(offers));
  vi.mocked(api.getCharacterResonances).mockResolvedValue(resonances);
  const { wrapper, client } = createWrapperWithClient();
  const view = render(<EntryFlourishOfferGate characterSheetId={4} />, { wrapper });
  return { ...view, client };
}

// ---------------------------------------------------------------------------
// Dialog content tests
// ---------------------------------------------------------------------------

describe('EntryFlourishOfferDialog (via EntryFlourishOfferGate)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('auto-opens and renders the claimed resonances as selectable chips', async () => {
    renderGate([OFFER]);

    await screen.findByRole('dialog');
    expect(screen.getByTestId('resonance-chip-7')).toHaveTextContent('Ember');
    expect(screen.getByTestId('resonance-chip-8')).toHaveTextContent('Tide');
  });

  it('Declare button is disabled until a resonance is selected', async () => {
    renderGate([OFFER]);

    await screen.findByRole('dialog');
    expect(screen.getByTestId('entry-flourish-confirm')).toBeDisabled();

    await userEvent.click(screen.getByTestId('resonance-chip-7'));
    expect(screen.getByTestId('entry-flourish-confirm')).not.toBeDisabled();
  });

  it('confirming calls respond with the chosen { offer_id, resonance_id } and closes on success', async () => {
    const user = userEvent.setup();
    vi.mocked(api.respondToEntryFlourish).mockResolvedValue(RESULT);

    renderGate([OFFER]);

    await screen.findByRole('dialog');
    await user.click(screen.getByTestId('resonance-chip-7'));
    await user.click(screen.getByTestId('entry-flourish-confirm'));

    await waitFor(() => {
      expect(api.respondToEntryFlourish).toHaveBeenCalledWith({ offer_id: 9, resonance_id: 7 });
    });
    // Dialog closes after success.
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });
  });

  it('a failing respond keeps the dialog open and surfaces the server message', async () => {
    const user = userEvent.setup();
    const SERVER_MESSAGE = 'This offer is no longer valid.';
    vi.mocked(api.respondToEntryFlourish).mockRejectedValue(new Error(SERVER_MESSAGE));

    renderGate([OFFER]);

    await screen.findByRole('dialog');
    await user.click(screen.getByTestId('resonance-chip-7'));
    await user.click(screen.getByTestId('entry-flourish-confirm'));

    await waitFor(() => {
      expect(api.respondToEntryFlourish).toHaveBeenCalled();
    });
    const error = await screen.findByTestId('entry-flourish-respond-error');
    expect(error).toHaveAttribute('role', 'alert');
    expect(error).toHaveTextContent(SERVER_MESSAGE);
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('renders an empty-state message when the character has no resonances', async () => {
    renderGate([OFFER], []);

    await screen.findByRole('dialog');
    expect(screen.getByTestId('entry-flourish-empty')).toBeInTheDocument();
    expect(screen.queryByTestId('entry-flourish-resonance-picker')).not.toBeInTheDocument();
  });

  it('renders nothing when there is no offer for this character sheet', async () => {
    renderGate([{ ...OFFER, character_sheet_id: 999 }]);

    await waitFor(() => {
      expect(api.getPendingEntryFlourishOffers).toHaveBeenCalled();
    });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.queryByTestId('entry-flourish-gate-strip')).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Gate auto-open tests
// ---------------------------------------------------------------------------

describe('EntryFlourishOfferGate — auto-open once per offer id', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('auto-opens on a new offer; dismissal leaves the strip; same id does not reopen; a new id does', async () => {
    const user = userEvent.setup();
    const { client } = renderGate([OFFER]);

    // Auto-opens without any user click.
    await screen.findByRole('dialog');

    // Dismiss (Escape) — dialog gone, strip remains.
    await user.keyboard('{Escape}');
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });
    expect(screen.getByTestId('entry-flourish-gate-strip')).toBeInTheDocument();
    expect(api.respondToEntryFlourish).not.toHaveBeenCalled();

    // Same offer id — must not reopen.
    vi.mocked(api.getPendingEntryFlourishOffers).mockResolvedValue(paginatedOffers([{ ...OFFER }]));
    await act(async () => {
      await client.refetchQueries();
    });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.getByTestId('entry-flourish-gate-strip')).toBeInTheDocument();

    // New offer id — must auto-open again.
    vi.mocked(api.getPendingEntryFlourishOffers).mockResolvedValue(
      paginatedOffers([{ ...OFFER, id: 10 }])
    );
    await act(async () => {
      await client.refetchQueries();
    });
    await screen.findByRole('dialog');
  });

  it('re-opens the dialog when the strip is clicked', async () => {
    const user = userEvent.setup();
    renderGate([OFFER]);

    await screen.findByRole('dialog');
    await user.keyboard('{Escape}');
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });

    await user.click(screen.getByTestId('entry-flourish-gate-strip'));
    await screen.findByRole('dialog');
  });
});
