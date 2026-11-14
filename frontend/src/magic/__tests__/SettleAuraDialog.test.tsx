/**
 * Coverage for the Settle your aura dialog (#5123, Screen 4 of the approved demo) and
 * the drift conversion offer ceremony (#4733) that is its Atone exit:
 * DriftConversionOfferGate + dialog with real hooks
 * (usePendingDriftConversionOffers / useConvertDrift / useDeclineDriftConversion)
 * and a mocked api transport - same pattern as EntryFlourishOfferDialog.test.tsx.
 */

import { render, screen, waitFor, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { vi } from 'vitest';
import type { ReactNode } from 'react';
import { DriftConversionOfferGate } from '../components/DriftConversionOfferGate';
import { SettleAuraDialog } from '../components/SettleAuraDialog';
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
import type { CharacterAura } from '../auraQueries';
import { throwApiError } from '@/lib/errors';

// The aura endpoints go through apiFetch; the gate reads the account's auras and the
// dialog's Accept posts to the aura's accept action.
const apiFetchMock = vi.hoisted(() => vi.fn());
vi.mock('@/evennia_replacements/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/evennia_replacements/api')>()),
  apiFetch: (...args: unknown[]) => apiFetchMock(...args),
}));

/** A primal character whose abyssal has grown past who they are. */
const UNSETTLED_AURA: CharacterAura = {
  id: 7,
  character: 55,
  shares: [
    { affinity_id: 1, affinity_name: 'Primal', percent: '58.00', settled_percent: '66.00' },
    { affinity_id: 2, affinity_name: 'Abyssal', percent: '42.00', settled_percent: '34.00' },
  ],
  dominant_affinity: 'Primal',
  dominant_affinity_display: 'Primal',
  unsettled: true,
  unsettled_line: 'Your Domination has grown strong enough to make you unsettled.',
  mire_share_words: 'none',
  glimpse_state: 'NOT_STARTED',
  updated_at: '2026-11-14T00:00:00Z',
};
const SETTLED_AURA: CharacterAura = { ...UNSETTLED_AURA, unsettled: false, unsettled_line: '' };

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

function renderGate(
  offers: DriftConversionOffer[],
  sceneId: number | null = 101,
  auras: CharacterAura[] = []
) {
  vi.mocked(api.getPendingDriftConversionOffers).mockResolvedValue(paginated(offers));
  apiFetchMock.mockImplementation(async (_url: string, init?: RequestInit) =>
    init?.method === 'POST'
      ? new Response(JSON.stringify({ detail: 'You become more abyssal.', aura: SETTLED_AURA }), {
          status: 200,
        })
      : new Response(JSON.stringify(auras), { status: 200 })
  );
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  });
  function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  }
  const view = render(<DriftConversionOfferGate sceneId={sceneId} />, { wrapper: Wrapper });
  return { ...view, client };
}

describe('SettleAuraDialog Atone exit (via DriftConversionOfferGate)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('auto-opens as Settle your aura with the cap remaining and mode-labelled pills', async () => {
    renderGate([OFFER]);

    const dialog = await screen.findByRole('dialog');
    expect(dialog).toHaveTextContent('Settle your aura');
    expect(screen.getByTestId('settle-exit-atone')).toHaveTextContent('Atone');
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
    // The same words the telnet verb and the action send: the tier leads the line.
    expect(await screen.findByTestId('drift-result')).toHaveTextContent(
      /^Partial Success: 8 Ruin became 4 Dawnlight\.$/
    );
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

  it('shows a refused offering as the plain sentence, never a field name', async () => {
    const user = userEvent.setup();
    const SENTENCE = 'You are not carrying everything you offered.';
    // The convert view's refusal body, run through the same error reader the api uses.
    vi.mocked(api.convertDrift).mockImplementation(() =>
      throwApiError(
        new Response(JSON.stringify({ detail: SENTENCE }), { status: 400 }),
        'Failed to perform the rite'
      )
    );
    renderGate([OFFER]);

    await screen.findByRole('dialog');
    await user.click(screen.getByTestId('drift-component-501'));
    await user.click(screen.getByTestId('drift-perform-20'));

    const error = await screen.findByTestId('drift-error');
    expect(error).toHaveTextContent(new RegExp(`^${SENTENCE}$`));
    expect(error).not.toHaveTextContent('component_ids');
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

  it('Not now posts { offer_id } and closes', async () => {
    const user = userEvent.setup();
    vi.mocked(api.declineDriftConversion).mockResolvedValue({ detail: 'ok' });
    renderGate([OFFER]);

    await screen.findByRole('dialog');
    await user.click(screen.getByRole('button', { name: 'Not now' }));

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

/**
 * The light theme is the default; a pale amber text or a near-black amber tint is only
 * readable on the dark one. Each themed element keeps those under `dark:` and carries a
 * dark amber text and a pale surface for light (the repo's `text-amber-700/800
 * dark:text-amber-300|400`, `bg-amber-50 dark:bg-amber-950/..` pairs). jsdom has no
 * stylesheet, so this pins the class pairs; contrast on a real page needs the live run.
 */
const DARK_ONLY =
  /^(text-amber-(100|200|300|400)|bg-amber-950(\/\d+)?|text-red-200|bg-red-950(\/\d+)?)$/;

function lightThemeClasses(element: HTMLElement): string[] {
  return Array.from(element.classList).filter((c) => !c.includes(':'));
}

describe('SettleAuraDialog - readable in the light theme', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('pulses only the glow behind the strip, never its words', async () => {
    renderGate([OFFER]);

    const strip = await screen.findByTestId('drift-conversion-gate-strip');
    const label = screen.getByTestId('drift-conversion-gate-label');
    const glow = screen.getByTestId('drift-conversion-gate-glow');
    expect(strip).not.toHaveClass('animate-pulse');
    expect(label).not.toHaveClass('animate-pulse');
    expect(label).toHaveTextContent('Conversion offer');
    expect(glow).toHaveClass('animate-pulse', 'motion-reduce:animate-none');
    expect(glow).toHaveAttribute('aria-hidden', 'true');
  });

  it('keeps pale amber text and dark tints under dark: on the strip and the error', async () => {
    const user = userEvent.setup();
    vi.mocked(api.convertDrift).mockRejectedValue(new Error('Nope.'));
    renderGate([OFFER]);

    await screen.findByRole('dialog');
    await user.click(screen.getByTestId('drift-component-501'));
    await user.click(screen.getByTestId('drift-perform-20'));
    const themed = [
      screen.getByTestId('drift-conversion-gate-strip'),
      screen.getByTestId('drift-cap-20'),
      screen.getByTestId('drift-source-20-30'),
      screen.getByTestId('drift-component-501'),
      await screen.findByTestId('drift-error'),
    ];
    for (const element of themed) {
      const light = lightThemeClasses(element);
      expect(light.filter((c) => DARK_ONLY.test(c))).toEqual([]);
    }
    expect(screen.getByTestId('drift-conversion-gate-strip')).toHaveClass(
      'bg-amber-50',
      'text-amber-800',
      'dark:bg-amber-950/40',
      'dark:text-amber-300'
    );
  });

  it('fills the selected pill in the primary pair and outlines the rest', async () => {
    const user = userEvent.setup();
    renderGate([OFFER]);

    await screen.findByRole('dialog');
    await user.click(screen.getByTestId('drift-component-502'));
    const chosen = screen.getByTestId('drift-component-502');
    const other = screen.getByTestId('drift-component-501');
    expect(chosen).toHaveAttribute('aria-pressed', 'true');
    expect(chosen).toHaveClass('bg-primary', 'text-primary-foreground');
    expect(other).toHaveAttribute('aria-pressed', 'false');
    expect(other).not.toHaveClass('bg-primary');
    expect(other).toHaveClass('border-input', 'bg-transparent');
  });
});

describe('SettleAuraDialog - the approved Screen 4 box', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('is headed by the unsettled sentence once the aura is known', async () => {
    renderGate([OFFER], 101, [UNSETTLED_AURA]);

    const dialog = await screen.findByRole('dialog');
    expect(dialog).toBeInTheDocument();
    expect(
      await screen.findByRole('dialog', {
        name: 'Your Domination has grown strong enough to make you unsettled.',
      })
    ).toBeInTheDocument();
  });

  it('names one held source in the system line', async () => {
    const one: DriftConversionOffer = {
      ...OFFER,
      caps: [{ ...OFFER.caps[0], sources: [OFFER.caps[0].sources[0]] }],
    };
    renderGate([one]);

    await screen.findByRole('dialog');
    expect(screen.getByTestId('drift-system-line-20')).toHaveTextContent(
      /^The Ruin you gained turns to Dawnlight\.$/
    );
    // One source is a plain chip, not a picker.
    expect(screen.getByTestId('drift-source-20-30').tagName).toBe('SPAN');
    expect(screen.queryByRole('group', { name: 'Source for Dawnlight' })).not.toBeInTheDocument();
  });

  it('names two held sources in the system line', async () => {
    renderGate([OFFER]);

    await screen.findByRole('dialog');
    expect(screen.getByTestId('drift-system-line-20')).toHaveTextContent(
      /^The Ruin and Spite you gained turns to Dawnlight\.$/
    );
  });

  it('holds Perform the rite in a right-aligned row inside the Atone exit, and Not now below', async () => {
    renderGate([OFFER]);

    const dialog = await screen.findByRole('dialog');
    const row = screen.getByTestId('drift-actions-20');
    expect(row).toHaveClass('justify-end');
    expect(screen.getByTestId('settle-exit-atone')).toContainElement(row);
    const buttons = Array.from(row.querySelectorAll('button')).map((b) => b.textContent);
    expect(buttons).toEqual(['Perform the rite']);
    // Not now appears once, in the dialog's own footer.
    expect(screen.getAllByRole('button', { name: 'Not now' })).toHaveLength(1);
    expect(dialog).toContainElement(screen.getByTestId('settle-not-now'));
  });
});

describe('SettleAuraDialog - Atone and Accept exits (#5123)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows the unsettled sentence and both exits while an offer is open', async () => {
    renderGate([OFFER], 101, [UNSETTLED_AURA]);

    await screen.findByTestId('settle-exit-accept');
    expect(screen.getByTestId('settle-exit-atone')).toBeInTheDocument();
    expect(screen.getByRole('dialog')).toHaveTextContent(
      'Your Domination has grown strong enough to make you unsettled.'
    );
    expect(screen.getByText('Accept the changes to your Aura')).toBeInTheDocument();
    expect(screen.getByTestId('settle-accept-line')).toHaveTextContent(
      /^You become more abyssal\.$/
    );
    // The word the player never reads, and no figures.
    expect(screen.getByRole('dialog')).not.toHaveTextContent(/accepted/i);
    expect(screen.getByRole('dialog')).not.toHaveTextContent('42');
  });

  it('hides Atone when no offer is open and still offers Accept', async () => {
    // No offer means no gate; this is the dialog the sheet mounts.
    const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
    render(
      <SettleAuraDialog
        aura={UNSETTLED_AURA}
        offer={null}
        resultLine={null}
        onResult={vi.fn()}
        open
        onOpenChange={vi.fn()}
        onClose={vi.fn()}
      />,
      {
        wrapper: ({ children }: { children: ReactNode }) => (
          <QueryClientProvider client={client}>{children}</QueryClientProvider>
        ),
      }
    );

    expect(await screen.findByTestId('settle-exit-accept')).toBeInTheDocument();
    expect(screen.queryByTestId('settle-exit-atone')).not.toBeInTheDocument();
    expect(screen.queryByText('Atone')).not.toBeInTheDocument();
  });

  it('Accept posts to the aura accept endpoint and shows the server line', async () => {
    const user = userEvent.setup();
    renderGate([OFFER], 101, [UNSETTLED_AURA]);

    await user.click(await screen.findByTestId('settle-accept-button'));

    await waitFor(() => {
      expect(apiFetchMock).toHaveBeenCalledWith('/api/magic/character-auras/7/accept/', {
        method: 'POST',
      });
    });
    expect(await screen.findByTestId('drift-result')).toHaveTextContent(
      /^You become more abyssal\.$/
    );
  });

  it('offers no Accept once the character is settled', async () => {
    renderGate([OFFER], 101, [SETTLED_AURA]);

    await screen.findByTestId('settle-exit-atone');
    // The aura read must have been asked AND answered before absence means anything.
    await waitFor(() => {
      expect(apiFetchMock).toHaveBeenCalled();
    });
    await act(async () => {
      await apiFetchMock.mock.results[0].value;
    });
    expect(screen.queryByTestId('settle-exit-accept')).not.toBeInTheDocument();
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
