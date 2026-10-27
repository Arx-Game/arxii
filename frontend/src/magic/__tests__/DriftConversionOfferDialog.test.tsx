/**
 * Coverage for the drift conversion offer ceremony (#4733, Screen 5 of the
 * approved demo): DriftConversionOfferGate + dialog with real hooks
 * (usePendingDriftConversionOffers / useConvertDrift / useDeclineDriftConversion)
 * and a mocked api transport - same pattern as EntryFlourishOfferDialog.test.tsx.
 */

import { render, screen, waitFor, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { vi } from 'vitest';
import type { ReactNode } from 'react';
import { DriftConversionOfferGate } from '../components/DriftConversionOfferGate';
import type {
  DriftConversionOffer,
  DriftCorrectionResult,
  PaginatedDriftConversionOfferList,
} from '../types';

vi.mock('../api', () => ({
  getPendingDriftConversionOffers: vi.fn(),
  convertDrift: vi.fn(),
  declineDriftConversion: vi.fn(),
}));

import * as api from '../api';

const OFFER: DriftConversionOffer = {
  id: 12,
  scene_id: 101,
  caps: [
    {
      target_resonance: { id: 20, name: 'Dawnlight', affinity: 'Celestial' },
      cap_remaining: 12,
      focus_bonus: 0,
      sources: [
        {
          resonance_id: 30,
          resonance_name: 'Ruin',
          balance: 14,
          multiplier: '0.50',
          conversion_type: 'REDEMPTION',
          max_amount: 12,
          projected_output: 6,
        },
        {
          resonance_id: 31,
          resonance_name: 'Spite',
          balance: 5,
          multiplier: '1.50',
          conversion_type: 'FALL',
          max_amount: 5,
          projected_output: 7,
        },
      ],
      qualifying_components: [
        { item_id: 501, name: 'Ash-grey candle', mode: 'material' },
        { item_id: 502, name: 'Cracked mirror', mode: 'facet' },
        { item_id: 503, name: "Mother's ring", mode: 'keepsake' },
      ],
    },
  ],
  rite_ready: true,
  rite_not_ready_message: '',
};

const NOT_READY = 'The rite of correction is not set up yet; tell staff.';

const OFFER_NOT_READY: DriftConversionOffer = {
  ...OFFER,
  rite_ready: false,
  rite_not_ready_message: NOT_READY,
};

const OFFER_WITH_FOCUS: DriftConversionOffer = {
  ...OFFER,
  caps: [{ ...OFFER.caps[0], focus_bonus: 2 }],
};

const RESULT: DriftCorrectionResult = {
  source_resonance_id: 30,
  target_resonance_id: 20,
  attempted_amount: 12,
  converted_amount: 8,
  granted_amount: 4,
  outcome_name: 'Partial Success',
  success_level: 1,
  conversion_type: 'REDEMPTION',
  focus_bonus: 0,
};

function paginated(results: DriftConversionOffer[]): PaginatedDriftConversionOfferList {
  return { count: results.length, next: null, previous: null, results };
}

function renderGate(offers: DriftConversionOffer[], sceneId: number | null = 101) {
  vi.mocked(api.getPendingDriftConversionOffers).mockResolvedValue(paginated(offers));
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  });
  function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  }
  const view = render(<DriftConversionOfferGate sceneId={sceneId} />, { wrapper: Wrapper });
  return { ...view, client };
}

describe('DriftConversionOfferDialog (via DriftConversionOfferGate)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('auto-opens headed "Conversion offer" with the cap remaining and mode-labelled pills', async () => {
    renderGate([OFFER]);

    const dialog = await screen.findByRole('dialog');
    expect(dialog).toHaveTextContent('Conversion offer');
    expect(screen.getByTestId('drift-cap-20')).toHaveTextContent('Dawnlight');
    expect(screen.getByTestId('drift-cap-remaining-20')).toHaveTextContent('12');
    expect(screen.getByTestId('drift-component-501')).toHaveTextContent(
      'Ash-grey candle · material'
    );
    expect(screen.getByTestId('drift-component-502')).toHaveTextContent('Cracked mirror · facet');
    expect(screen.getByTestId('drift-component-503')).toHaveTextContent("Mother's ring · keepsake");
  });

  it('source pills show balance, pair rate type and projected yield', async () => {
    renderGate([OFFER]);

    await screen.findByRole('dialog');
    const ruin = screen.getByTestId('drift-source-20-30');
    expect(ruin).toHaveTextContent('Ruin');
    expect(ruin).toHaveTextContent('14');
    expect(ruin).toHaveTextContent('Redemption');
    expect(ruin).toHaveTextContent('6');
    expect(screen.getByTestId('drift-source-20-31')).toHaveTextContent('Fall');
  });

  it('defaults the amount to the source max and builds the rate line from the preview', async () => {
    const user = userEvent.setup();
    renderGate([OFFER]);

    await screen.findByRole('dialog');
    expect(screen.getByTestId('drift-amount-20')).toHaveValue(12);
    expect(screen.getByTestId('drift-rate-20')).toHaveTextContent(
      'Redemption: 12 Ruin becomes about 6 Dawnlight'
    );
    expect(screen.getByTestId('drift-rate-20')).not.toHaveTextContent('focus');

    // Switching source resets the amount to that source's max and rewrites the line.
    await user.click(screen.getByTestId('drift-source-20-31'));
    expect(screen.getByTestId('drift-amount-20')).toHaveValue(5);
    expect(screen.getByTestId('drift-rate-20')).toHaveTextContent(
      'Fall: 5 Spite becomes about 7 Dawnlight'
    );
  });

  it('scales the projected yield with a smaller amount', async () => {
    const user = userEvent.setup();
    renderGate([OFFER]);

    await screen.findByRole('dialog');
    const amount = screen.getByTestId('drift-amount-20');
    await user.clear(amount);
    await user.type(amount, '4');
    expect(screen.getByTestId('drift-rate-20')).toHaveTextContent(
      'Redemption: 4 Ruin becomes about 2 Dawnlight'
    );
  });

  it('appends the focus clause only when focus_bonus is above zero', async () => {
    renderGate([OFFER_WITH_FOCUS]);

    await screen.findByRole('dialog');
    expect(screen.getByTestId('drift-rate-20')).toHaveTextContent(
      'Redemption: 12 Ruin becomes about 6 Dawnlight; a focus adds 2'
    );
  });

  it('Perform the rite is disabled until a component is chosen and the amount is valid', async () => {
    const user = userEvent.setup();
    renderGate([OFFER]);

    await screen.findByRole('dialog');
    const perform = screen.getByTestId('drift-perform-20');
    expect(perform).toHaveTextContent('Perform the rite');
    expect(perform).toBeDisabled();

    await user.click(screen.getByTestId('drift-component-502'));
    expect(perform).not.toBeDisabled();

    // Above the source's max_amount is not valid.
    const amount = screen.getByTestId('drift-amount-20');
    await user.clear(amount);
    await user.type(amount, '13');
    expect(perform).toBeDisabled();
    await user.clear(amount);
    await user.type(amount, '0');
    expect(perform).toBeDisabled();
    await user.clear(amount);
    await user.type(amount, '9');
    expect(perform).not.toBeDisabled();
  });

  it('says the rite is not set up in place of the pills while it is not ready', async () => {
    renderGate([OFFER_NOT_READY]);

    await screen.findByRole('dialog');
    expect(screen.getByTestId('drift-not-ready-20')).toHaveTextContent(
      new RegExp(`^${NOT_READY}$`)
    );
    expect(
      screen.queryByRole('group', { name: 'Components for Dawnlight' })
    ).not.toBeInTheDocument();
    expect(screen.queryByTestId('drift-component-501')).not.toBeInTheDocument();
    expect(screen.getByTestId('drift-perform-20')).toBeDisabled();
    // What the offer holds is still shown.
    expect(screen.getByTestId('drift-cap-remaining-20')).toHaveTextContent('12');
    expect(screen.getByTestId('drift-source-20-30')).toBeInTheDocument();
  });

  it('shows the pills and no not-ready line while the rite is ready', async () => {
    renderGate([OFFER]);

    await screen.findByRole('dialog');
    expect(screen.queryByTestId('drift-not-ready-20')).not.toBeInTheDocument();
    expect(screen.getByTestId('drift-component-501')).toBeInTheDocument();
  });

  it('components are single-select', async () => {
    const user = userEvent.setup();
    renderGate([OFFER]);

    await screen.findByRole('dialog');
    await user.click(screen.getByTestId('drift-component-501'));
    await user.click(screen.getByTestId('drift-component-503'));
    expect(screen.getByTestId('drift-component-501')).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getByTestId('drift-component-503')).toHaveAttribute('aria-pressed', 'true');
  });

  it('Perform the rite posts the exact body and shows the result line', async () => {
    const user = userEvent.setup();
    vi.mocked(api.convertDrift).mockResolvedValue(RESULT);
    renderGate([OFFER]);

    await screen.findByRole('dialog');
    await user.click(screen.getByTestId('drift-component-502'));
    await user.click(screen.getByTestId('drift-perform-20'));

    await waitFor(() => {
      expect(api.convertDrift).toHaveBeenCalledWith({
        offer_id: 12,
        source_resonance_id: 30,
        target_resonance_id: 20,
        amount: 12,
        component_ids: [502],
      });
    });
    const line = await screen.findByTestId('drift-result');
    expect(line).toHaveTextContent('Partial Success');
    expect(line).toHaveTextContent('8 Ruin');
    expect(line).toHaveTextContent('4 Dawnlight');
  });

  it('says the rite fails, in the telnet words, when nothing converted', async () => {
    const user = userEvent.setup();
    vi.mocked(api.convertDrift).mockResolvedValue({
      ...RESULT,
      converted_amount: 0,
      granted_amount: 0,
      outcome_name: 'Failure',
      success_level: -1,
    });
    renderGate([OFFER]);

    await screen.findByRole('dialog');
    await user.click(screen.getByTestId('drift-component-502'));
    await user.click(screen.getByTestId('drift-perform-20'));

    expect(await screen.findByTestId('drift-result')).toHaveTextContent(
      /^The rite fails; nothing is converted\.$/
    );
  });

  it('keeps the result line after the exhausted offer leaves the inbox', async () => {
    const user = userEvent.setup();
    vi.mocked(api.convertDrift).mockResolvedValue(RESULT);
    const { client } = renderGate([OFFER]);

    await screen.findByRole('dialog');
    await user.click(screen.getByTestId('drift-component-502'));
    await user.click(screen.getByTestId('drift-perform-20'));
    await screen.findByTestId('drift-result');
    // Let the post-convert invalidation refetch settle before the inbox empties.
    await waitFor(() => {
      expect(api.getPendingDriftConversionOffers).toHaveBeenCalledTimes(2);
    });

    vi.mocked(api.getPendingDriftConversionOffers).mockResolvedValue(paginated([]));
    await act(async () => {
      await client.refetchQueries();
    });
    expect(screen.getByTestId('drift-result')).toHaveTextContent('Partial Success');
    await waitFor(() => {
      expect(screen.queryByTestId('drift-perform-20')).not.toBeInTheDocument();
    });
    expect(screen.getByTestId('drift-result')).toHaveTextContent('Partial Success');
  });

  it('a refusal keeps the dialog open and shows the backend detail', async () => {
    const user = userEvent.setup();
    const DETAIL = 'You are not carrying everything you offered.';
    vi.mocked(api.convertDrift).mockRejectedValue(new Error(DETAIL));
    renderGate([OFFER]);

    await screen.findByRole('dialog');
    await user.click(screen.getByTestId('drift-component-501'));
    await user.click(screen.getByTestId('drift-perform-20'));

    const error = await screen.findByTestId('drift-error');
    expect(error).toHaveAttribute('role', 'alert');
    expect(error).toHaveTextContent(DETAIL);
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('Decline posts { offer_id } and closes', async () => {
    const user = userEvent.setup();
    vi.mocked(api.declineDriftConversion).mockResolvedValue({ detail: 'ok' });
    renderGate([OFFER]);

    await screen.findByRole('dialog');
    await user.click(screen.getByRole('button', { name: 'Decline' }));

    await waitFor(() => {
      expect(api.declineDriftConversion).toHaveBeenCalledWith({ offer_id: 12 });
    });
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });
  });

  it('shows the offer for its own scene when the account holds offers in two scenes', async () => {
    const other: DriftConversionOffer = {
      ...OFFER,
      id: 99,
      scene_id: 202,
      caps: [
        {
          ...OFFER.caps[0],
          target_resonance: { id: 77, name: 'Hearthfire', affinity: 'Primal' },
        },
      ],
    };
    renderGate([other, OFFER], 101);

    await screen.findByRole('dialog');
    expect(screen.getByTestId('drift-cap-20')).toBeInTheDocument();
    expect(screen.queryByTestId('drift-cap-77')).not.toBeInTheDocument();
  });

  it('renders nothing when no offer belongs to the scene', async () => {
    renderGate([OFFER], 303);

    // The poll must have been asked AND answered before absence means anything.
    await waitFor(() => {
      expect(api.getPendingDriftConversionOffers).toHaveBeenCalled();
    });
    await act(async () => {
      await vi.mocked(api.getPendingDriftConversionOffers).mock.results[0].value;
    });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.queryByTestId('drift-conversion-gate-strip')).not.toBeInTheDocument();
  });

  it('does not poll until the scene is known', () => {
    renderGate([OFFER], null);

    expect(api.getPendingDriftConversionOffers).not.toHaveBeenCalled();
    expect(screen.queryByTestId('drift-conversion-gate-strip')).not.toBeInTheDocument();
  });

  it('names the target in the pill groups and flags an invalid amount', async () => {
    const user = userEvent.setup();
    renderGate([OFFER]);

    await screen.findByRole('dialog');
    expect(screen.getByRole('group', { name: 'Source for Dawnlight' })).toBeInTheDocument();
    expect(screen.getByRole('group', { name: 'Components for Dawnlight' })).toBeInTheDocument();
    const amount = screen.getByTestId('drift-amount-20');
    expect(amount).toHaveAttribute('aria-invalid', 'false');
    await user.clear(amount);
    await user.type(amount, '99');
    expect(amount).toHaveAttribute('aria-invalid', 'true');
  });

  it('clears a refusal when the selection changes', async () => {
    const user = userEvent.setup();
    vi.mocked(api.convertDrift).mockRejectedValue(new Error('Nope.'));
    renderGate([OFFER]);

    await screen.findByRole('dialog');
    await user.click(screen.getByTestId('drift-component-501'));
    await user.click(screen.getByTestId('drift-perform-20'));
    await screen.findByTestId('drift-error');

    await user.click(screen.getByTestId('drift-component-502'));
    await waitFor(() => {
      expect(screen.queryByTestId('drift-error')).not.toBeInTheDocument();
    });
  });

  it("resets a block's picks when the offer changes", async () => {
    const user = userEvent.setup();
    const { client } = renderGate([OFFER]);

    await screen.findByRole('dialog');
    await user.click(screen.getByTestId('drift-component-501'));
    expect(screen.getByTestId('drift-perform-20')).not.toBeDisabled();

    vi.mocked(api.getPendingDriftConversionOffers).mockResolvedValue(
      paginated([{ ...OFFER, id: 13 }])
    );
    await act(async () => {
      await client.refetchQueries();
    });
    await waitFor(() => {
      expect(screen.getByTestId('drift-perform-20')).toBeDisabled();
    });
  });

  it('renders nothing when there is no open offer', async () => {
    renderGate([]);

    // The poll must have been asked AND answered before absence means anything.
    await waitFor(() => {
      expect(api.getPendingDriftConversionOffers).toHaveBeenCalled();
    });
    await act(async () => {
      await vi.mocked(api.getPendingDriftConversionOffers).mock.results[0].value;
    });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.queryByTestId('drift-conversion-gate-strip')).not.toBeInTheDocument();
  });
});

describe('DriftConversionOfferGate - auto-open once per offer id', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('auto-opens; dismissal leaves the strip; same id does not reopen; a new id does', async () => {
    const user = userEvent.setup();
    const { client } = renderGate([OFFER]);

    await screen.findByRole('dialog');
    await user.keyboard('{Escape}');
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });
    expect(screen.getByTestId('drift-conversion-gate-strip')).toBeInTheDocument();
    expect(api.declineDriftConversion).not.toHaveBeenCalled();

    vi.mocked(api.getPendingDriftConversionOffers).mockResolvedValue(paginated([{ ...OFFER }]));
    await act(async () => {
      await client.refetchQueries();
    });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();

    vi.mocked(api.getPendingDriftConversionOffers).mockResolvedValue(
      paginated([{ ...OFFER, id: 13 }])
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

    await user.click(screen.getByTestId('drift-conversion-gate-strip'));
    await screen.findByRole('dialog');
  });
});
