/**
 * Coverage for the Audere Majora crossing ceremony (#543):
 * AudereMajoraOfferGate + dialog with real hooks and a mocked api transport.
 *
 * SPOILER RULE: vision_text values in fixtures must be obvious placeholders
 * ("[TEST VISION]"). UI copy is generic.
 */

import { render, screen, waitFor, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { vi } from 'vitest';
import type { ReactNode } from 'react';
import { AudereMajoraOfferGate } from '../components/AudereMajoraOfferGate';
import type {
  PaginatedPendingAudereMajoraOfferList,
  PendingAudereMajoraOffer,
} from '../types';

// ---------------------------------------------------------------------------
// Mock the api transport — real hooks run against these.
// ---------------------------------------------------------------------------

vi.mock('../api', () => ({
  getPendingAudereMajoraOffers: vi.fn(),
  respondToAudereMajora: vi.fn(),
}));

import * as api from '../api';

// ---------------------------------------------------------------------------
// Fixtures (SPOILER RULE: vision_text = obvious placeholder)
// ---------------------------------------------------------------------------

const PATH_A = {
  id: 1,
  name: 'Path of Fire',
  stage: 3,
  stage_display: 'Ascendant',
  description: 'A path of burning clarity.',
};

const PATH_B = {
  id: 2,
  name: 'Path of Ice',
  stage: 3,
  stage_display: 'Ascendant',
  description: 'A path of cold precision.',
};

const OFFER: PendingAudereMajoraOffer = {
  id: 7,
  character_sheet_id: 3,
  character_name: 'Velenosa',
  fired_intensity: 18,
  soulfray_stage_order: 3,
  boundary_level: 5,
  target_stage_display: 'Ascendant',
  vision_text: '[TEST VISION]',
  advisory_text: '',
  risk_text: '',
  eligible_paths: [PATH_A, PATH_B],
  intended_path_id: null,
  created_at: '2026-06-01T00:00:00Z',
};

function paginated(results: PendingAudereMajoraOffer[]): PaginatedPendingAudereMajoraOfferList {
  return { count: results.length, next: null, previous: null, results };
}

// ---------------------------------------------------------------------------
// Wrapper — QueryClientProvider only
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

function renderGate(offers: PendingAudereMajoraOffer[]) {
  vi.mocked(api.getPendingAudereMajoraOffers).mockResolvedValue(paginated(offers));
  const { wrapper, client } = createWrapperWithClient();
  const view = render(
    <AudereMajoraOfferGate characterSheetId={3} characterId={10} encounterId={1} />,
    { wrapper }
  );
  return { ...view, client };
}

// ---------------------------------------------------------------------------
// Dialog render tests
// ---------------------------------------------------------------------------

describe('AudereMajoraOfferDialog (via AudereMajoraOfferGate)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders vision_text in the blockquote element', async () => {
    renderGate([OFFER]);

    await screen.findByRole('alertdialog');
    const vision = screen.getByTestId('majora-vision');
    expect(vision.tagName.toLowerCase()).toBe('blockquote');
    expect(vision.textContent).toBe('[TEST VISION]');
  });

  it('renders advisory_text and risk_text each in a role="alert" block', async () => {
    renderGate([
      {
        ...OFFER,
        advisory_text: 'Advisory: high corruption risk.',
        risk_text: 'Risk: character loss possible.',
      },
    ]);

    await screen.findByRole('alertdialog');
    const alerts = screen.getAllByRole('alert');
    const texts = alerts.map((a) => a.textContent ?? '');
    expect(texts).toContain('Advisory: high corruption risk.');
    expect(texts).toContain('Risk: character loss possible.');
  });

  it('renders the eligible paths list', async () => {
    renderGate([OFFER]);

    await screen.findByRole('alertdialog');
    expect(screen.getByText('Path of Fire')).toBeInTheDocument();
    expect(screen.getByText('Path of Ice')).toBeInTheDocument();
  });

  it('preselects intended_path_id when non-null', async () => {
    renderGate([{ ...OFFER, intended_path_id: 2 }]);

    await screen.findByRole('alertdialog');
    const radios = screen.getAllByRole('radio') as HTMLInputElement[];
    const pathB = radios.find((r) => r.value === '2');
    expect(pathB?.checked).toBe(true);
  });

  it('accept button is disabled when no declaration is typed', async () => {
    renderGate([OFFER]);

    await screen.findByRole('alertdialog');
    // Select a path first
    const user = userEvent.setup();
    await user.click(screen.getAllByRole('radio')[0]);

    const acceptBtn = screen.getByRole('button', { name: /cross the threshold/i });
    expect(acceptBtn).toBeDisabled();
  });

  it('accept button is disabled when no path is selected (declaration typed)', async () => {
    renderGate([OFFER]);

    await screen.findByRole('alertdialog');
    const user = userEvent.setup();
    await user.type(screen.getByTestId('majora-declaration'), 'My declaration text here.');

    const acceptBtn = screen.getByRole('button', { name: /cross the threshold/i });
    expect(acceptBtn).toBeDisabled();
  });

  it('accept button enables once path is selected AND declaration is non-empty', async () => {
    renderGate([OFFER]);

    await screen.findByRole('alertdialog');
    const user = userEvent.setup();

    await user.click(screen.getAllByRole('radio')[0]);
    await user.type(screen.getByTestId('majora-declaration'), 'I cross freely.');

    const acceptBtn = screen.getByRole('button', { name: /cross the threshold/i });
    expect(acceptBtn).not.toBeDisabled();
  });

  it('clicking accept calls onAccept with pathId and trimmed declaration text', async () => {
    const user = userEvent.setup();
    vi.mocked(api.respondToAudereMajora).mockResolvedValue({
      accepted: true,
      level_before: 5,
      level_after: 6,
      chosen_path_name: 'Path of Fire',
      advisory_text: '',
      declaration_interaction_id: 42,
    });

    renderGate([OFFER]);

    await screen.findByRole('alertdialog');

    await user.click(screen.getAllByRole('radio')[0]);
    await user.type(screen.getByTestId('majora-declaration'), '  I cross freely.  ');
    await user.click(screen.getByRole('button', { name: /cross the threshold/i }));

    await waitFor(() => {
      expect(api.respondToAudereMajora).toHaveBeenCalledWith({
        offer_id: 7,
        accept: true,
        path_id: 1,
        declaration_text: 'I cross freely.',
      });
    });
    // Dialog closes on success.
    await waitFor(() => {
      expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    });
  });

  it('clicking "Turn Away" calls respond with accept=false and closes on success', async () => {
    const user = userEvent.setup();
    vi.mocked(api.respondToAudereMajora).mockResolvedValue({
      accepted: false,
      level_before: 5,
      level_after: 5,
      chosen_path_name: '',
      advisory_text: '',
      declaration_interaction_id: null,
    });

    renderGate([OFFER]);

    await screen.findByRole('alertdialog');
    await user.click(screen.getByRole('button', { name: /turn away/i }));

    await waitFor(() => {
      expect(api.respondToAudereMajora).toHaveBeenCalledWith({ offer_id: 7, accept: false });
    });
    await waitFor(() => {
      expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    });
  });

  it('when only advisory_text is empty, only one alert block present (risk)', async () => {
    renderGate([{ ...OFFER, advisory_text: '', risk_text: 'Risk: death possible.' }]);

    await screen.findByRole('alertdialog');
    const alerts = screen.getAllByRole('alert');
    expect(alerts).toHaveLength(1);
    expect(alerts[0].textContent).toBe('Risk: death possible.');
  });

  it('surfaces server error message and keeps dialog open', async () => {
    const user = userEvent.setup();
    const SERVER_MESSAGE = 'The crossing has closed; this offer is no longer valid.';
    vi.mocked(api.respondToAudereMajora).mockRejectedValue(new Error(SERVER_MESSAGE));

    renderGate([{ ...OFFER, intended_path_id: 1 }]);

    await screen.findByRole('alertdialog');
    await user.type(screen.getByTestId('majora-declaration'), 'I cross freely.');
    await user.click(screen.getByRole('button', { name: /cross the threshold/i }));

    await waitFor(() => {
      expect(api.respondToAudereMajora).toHaveBeenCalled();
    });
    const error = await screen.findByTestId('audere-majora-respond-error');
    expect(error).toHaveAttribute('role', 'alert');
    expect(error).toHaveTextContent(SERVER_MESSAGE);
    expect(screen.getByRole('alertdialog')).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Gate auto-open + strip tests
// ---------------------------------------------------------------------------

describe('AudereMajoraOfferGate — auto-open once per offer id', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('auto-opens on a new offer; dismissal leaves the strip; same id does not reopen; new id does', async () => {
    const user = userEvent.setup();
    const { client } = renderGate([OFFER]);

    // Auto-opens without any user click.
    await screen.findByRole('alertdialog');

    // Dismiss (Escape) — dialog gone, strip remains.
    await user.keyboard('{Escape}');
    await waitFor(() => {
      expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    });
    expect(screen.getByTestId('audere-majora-gate-strip')).toBeInTheDocument();
    expect(api.respondToAudereMajora).not.toHaveBeenCalled();

    // Same offer id on refetch must not reopen.
    vi.mocked(api.getPendingAudereMajoraOffers).mockResolvedValue(paginated([{ ...OFFER }]));
    await act(async () => {
      await client.refetchQueries();
    });
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();

    // New offer id must auto-open.
    vi.mocked(api.getPendingAudereMajoraOffers).mockResolvedValue(
      paginated([{ ...OFFER, id: 8 }])
    );
    await act(async () => {
      await client.refetchQueries();
    });
    await screen.findByRole('alertdialog');
  });

  it('renders nothing when there is no offer for this character sheet', async () => {
    renderGate([{ ...OFFER, character_sheet_id: 999 }]);

    await waitFor(() => {
      expect(api.getPendingAudereMajoraOffers).toHaveBeenCalled();
    });
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    expect(screen.queryByTestId('audere-majora-gate-strip')).not.toBeInTheDocument();
  });
});
