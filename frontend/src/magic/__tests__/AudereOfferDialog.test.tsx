/**
 * Coverage for the Audere offer ceremony (#873): AudereOfferGate + dialog with
 * real hooks (usePendingAudereOffers / useRespondToAudere) and a mocked api
 * transport — same pattern as AlterationResolveDialog.test.tsx.
 *
 * The advisory test asserts FULL string equality inside the role="alert"
 * block: the corruption advisory (including the literal "character loss"
 * sentence) must reach the player verbatim, unedited.
 */

import { render, screen, waitFor, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { vi } from 'vitest';
import type { ReactNode } from 'react';
import { AudereOfferGate } from '../components/AudereOfferGate';
import type { PaginatedPendingAudereOfferList, PendingAudereOffer } from '../types';

// ---------------------------------------------------------------------------
// Mock the api transport — real hooks run against these.
// ---------------------------------------------------------------------------

vi.mock('../api', () => ({
  getPendingAudereOffers: vi.fn(),
  respondToAudere: vi.fn(),
}));

import * as api from '../api';

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const ADVISORY =
  'Corruption stage 3 (Withering): character loss is possible if accumulated ' +
  'corruption advances to terminal stage.';

const OFFER: PendingAudereOffer = {
  id: 5,
  character_sheet_id: 3,
  character_name: 'Velenosa',
  fired_intensity: 14,
  soulfray_stage_order: 2,
  intensity_bonus: 2,
  anima_pool_bonus: 10,
  advisory_text: '',
  created_at: '2026-06-01T00:00:00Z',
};

function paginated(results: PendingAudereOffer[]): PaginatedPendingAudereOfferList {
  return { count: results.length, next: null, previous: null, results };
}

// ---------------------------------------------------------------------------
// Wrapper — QueryClientProvider only (the Audere hooks don't read Redux)
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

function renderGate(offers: PendingAudereOffer[]) {
  vi.mocked(api.getPendingAudereOffers).mockResolvedValue(paginated(offers));
  const { wrapper, client } = createWrapperWithClient();
  const view = render(<AudereOfferGate characterSheetId={3} characterId={10} encounterId={1} />, {
    wrapper,
  });
  return { ...view, client };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('AudereOfferDialog (via AudereOfferGate)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the stakes: +intensity_bonus Intensity and +anima_pool_bonus Anima', async () => {
    renderGate([OFFER]);

    // Dialog auto-opens with the offer's stakes visible.
    await screen.findByRole('alertdialog');
    expect(screen.getByText('+2')).toBeInTheDocument();
    expect(screen.getByText(/Intensity/)).toBeInTheDocument();
    expect(screen.getByText('+10')).toBeInTheDocument();
    expect(screen.getByText(/Anima maximum/)).toBeInTheDocument();
  });

  it('renders the advisory VERBATIM inside a role="alert" element', async () => {
    renderGate([{ ...OFFER, advisory_text: ADVISORY }]);

    await screen.findByRole('alertdialog');
    const alert = screen.getByRole('alert');
    expect(alert.textContent).toBe(ADVISORY);
  });

  it('renders no role="alert" element when advisory_text is empty', async () => {
    renderGate([{ ...OFFER, advisory_text: '' }]);

    await screen.findByRole('alertdialog');
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('clicking "Break Through" responds with { offer_id, accept: true } and closes on success', async () => {
    const user = userEvent.setup();
    vi.mocked(api.respondToAudere).mockResolvedValue({
      accepted: true,
      intensity_bonus_applied: 2,
      anima_pool_expanded_by: 10,
      advisory_text: '',
    });

    renderGate([OFFER]);

    await screen.findByRole('alertdialog');
    await user.click(screen.getByRole('button', { name: /break through/i }));

    await waitFor(() => {
      expect(api.respondToAudere).toHaveBeenCalledWith({ offer_id: 5, accept: true });
    });
    // The dialog closes only after the mutation succeeds.
    await waitFor(() => {
      expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    });
  });

  it('clicking "Hold Fast" responds with { offer_id, accept: false } and closes on success', async () => {
    const user = userEvent.setup();
    vi.mocked(api.respondToAudere).mockResolvedValue({
      accepted: false,
      intensity_bonus_applied: 0,
      anima_pool_expanded_by: 0,
      advisory_text: '',
    });

    renderGate([OFFER]);

    await screen.findByRole('alertdialog');
    await user.click(screen.getByRole('button', { name: /hold fast/i }));

    await waitFor(() => {
      expect(api.respondToAudere).toHaveBeenCalledWith({ offer_id: 5, accept: false });
    });
    await waitFor(() => {
      expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    });
  });

  it('a rejecting respond keeps the dialog open and shows the failure alert', async () => {
    const user = userEvent.setup();
    vi.mocked(api.respondToAudere).mockRejectedValue(new Error('500'));

    renderGate([OFFER]);

    await screen.findByRole('alertdialog');
    await user.click(screen.getByRole('button', { name: /break through/i }));

    await waitFor(() => {
      expect(api.respondToAudere).toHaveBeenCalledWith({ offer_id: 5, accept: true });
    });
    // Failure surfaces inside the still-open dialog.
    const error = await screen.findByTestId('audere-respond-error');
    expect(error).toHaveAttribute('role', 'alert');
    expect(screen.getByRole('alertdialog')).toBeInTheDocument();
  });
});

describe('AudereOfferGate — auto-open once per offer id', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('auto-opens on a new offer; dismissal leaves the strip; same id does not reopen; a new id does', async () => {
    const user = userEvent.setup();
    const { client } = renderGate([OFFER]);

    // Auto-opens without any user click.
    await screen.findByRole('alertdialog');

    // Dismiss without responding (Escape) — dialog gone, strip remains.
    await user.keyboard('{Escape}');
    await waitFor(() => {
      expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    });
    expect(screen.getByTestId('audere-gate-strip')).toBeInTheDocument();
    expect(api.respondToAudere).not.toHaveBeenCalled();

    // A refetch returning the SAME offer id (fresh object) must not reopen.
    vi.mocked(api.getPendingAudereOffers).mockResolvedValue(paginated([{ ...OFFER }]));
    await act(async () => {
      await client.refetchQueries();
    });
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    expect(screen.getByTestId('audere-gate-strip')).toBeInTheDocument();

    // A refetch returning a NEW offer id must auto-open again.
    vi.mocked(api.getPendingAudereOffers).mockResolvedValue(paginated([{ ...OFFER, id: 6 }]));
    await act(async () => {
      await client.refetchQueries();
    });
    await screen.findByRole('alertdialog');
  });

  it('re-opens the dialog when the strip is clicked', async () => {
    const user = userEvent.setup();
    renderGate([OFFER]);

    await screen.findByRole('alertdialog');
    await user.keyboard('{Escape}');
    await waitFor(() => {
      expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    });

    await user.click(screen.getByTestId('audere-gate-strip'));
    await screen.findByRole('alertdialog');
  });

  it('renders nothing when there is no offer for this character sheet', async () => {
    renderGate([{ ...OFFER, character_sheet_id: 999 }]);

    await waitFor(() => {
      expect(api.getPendingAudereOffers).toHaveBeenCalled();
    });
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    expect(screen.queryByTestId('audere-gate-strip')).not.toBeInTheDocument();
  });
});
