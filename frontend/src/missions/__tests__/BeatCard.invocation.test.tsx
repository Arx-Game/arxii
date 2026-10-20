/**
 * BeatCard Call on favor (#4333): a rolled option offers the picker; the chosen being and
 * line ride the resolve request; the result shows the invocation lines and the breakdown.
 */
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { BeatView, ResolvedBeat } from '../types';
import type { InvocationOptions } from '@/worship/types';

const BEAT: BeatView = {
  instance_id: 7,
  template_name: 'PLACEHOLDER mission',
  node_key: 'entry',
  flavor_text: '[staff-authored mission node text]',
  options: [
    {
      option_id: 31,
      approach_id: null,
      label: '[option label]',
      kind: 'check',
      check_type_name: 'Investigation',
      base_risk: 0,
      reasons: [],
      rolls_check: true,
    },
    {
      option_id: 32,
      approach_id: null,
      label: '[branch label]',
      kind: 'branch',
      check_type_name: null,
      base_risk: 0,
      reasons: [],
      rolls_check: false,
    },
  ],
  is_paused: false,
  track: null,
};

const OPTIONS: InvocationOptions = {
  beings: [
    {
      being_id: 5,
      being_name: 'Ombrin',
      favor: 44,
      can_invoke: true,
      refusal: '',
      uses_left: 3,
      uses_per_week: 3,
      difficulty: {
        base_points: 75,
        base_band: 'daunting',
        base_band_label: 'Daunting',
        eases: [
          { label: "You are Ombrin's Chosen", points: 30 },
          { label: 'Favor 44 (30 or more)', points: 15 },
          { label: 'Favor invocation modifiers for Ombrin', points: 0 },
        ],
        points: 30,
        band: 'easy',
        band_label: 'Easy',
      },
      worn: null,
    },
    {
      being_id: 6,
      being_name: 'River Spirit',
      favor: 0,
      can_invoke: false,
      refusal: 'You have no favor with River Spirit to call on.',
      uses_left: 3,
      uses_per_week: 3,
      difficulty: null,
      worn: null,
    },
  ],
  bonuses: [
    { outcome_name: 'Critical Success', success_level: 2, bonus: 15 },
    { outcome_name: 'Success', success_level: 1, bonus: 10 },
    { outcome_name: 'Partial Success', success_level: 0, bonus: 5 },
    { outcome_name: 'Failure', success_level: -1, bonus: 0 },
    { outcome_name: 'Critical Failure', success_level: -2, bonus: 0 },
  ],
};

const RESOLVED: ResolvedBeat = {
  instance_id: 7,
  outcome_name: 'Success',
  story_text: '[staff-authored outcome text]',
  is_terminal: false,
  next_beat: null,
  epilogue: '',
  invocation: {
    call_line: 'Ysmay Dunhollow calls on Ombrin: [player line]',
    outcome_line: "Ysmay Dunhollow's invocation: Success.",
    bonus: 10,
    bonus_label: "Ombrin's favor (invocation: Success)",
    check_type_name: 'Investigation',
    points_before_bonus: 48,
    total_points: 58,
    roller_rank: 'Expert',
    target_rank: 'Expert',
    rank_difference: 0,
    rank_difference_without_bonus: -1,
  },
};

const resolveMutate = vi.fn();

vi.mock('../queries', async () => {
  const actual = await vi.importActual<typeof import('../queries')>('../queries');
  return {
    ...actual,
    useBeat: () => ({ data: BEAT, isLoading: false }),
    useResolveBeat: () => ({ mutate: resolveMutate, isPending: false, error: null }),
  };
});

vi.mock('@/worship/queries', () => ({
  useInvocationOptions: () => ({ data: OPTIONS, isLoading: false, error: null }),
}));

import { BeatCard } from '../components/BeatCard';

function withProviders(children: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

describe('BeatCard Call on favor', () => {
  beforeEach(() => resolveMutate.mockReset());

  it('offers Call on favor on a rolled option only', () => {
    render(withProviders(<BeatCard instanceId={7} roomKey="Gate" />));
    const options = screen.getAllByTestId('beat-option');
    expect(within(options[0]).getByTestId('call-on-favor')).toBeInTheDocument();
    expect(within(options[1]).queryByTestId('call-on-favor')).not.toBeInTheDocument();
  });

  it('shows the difficulty, the bonuses and refusals, then sends the choice', async () => {
    const user = userEvent.setup();
    render(withProviders(<BeatCard instanceId={7} roomKey="Gate" />));

    await user.click(screen.getByTestId('call-on-favor'));
    const dialog = await screen.findByTestId('call-on-favor-dialog');
    expect(within(dialog).getByTestId('invocation-result')).toHaveTextContent('30, Easy');
    expect(within(dialog).getByText("You are Ombrin's Chosen")).toBeInTheDocument();
    expect(within(dialog).getByText('-30')).toBeInTheDocument();
    expect(within(dialog).getByText('3 of 3 left this week')).toBeInTheDocument();
    expect(within(dialog).getByTestId('invocation-bonuses')).toHaveTextContent(
      'Critical Success +15 · Success +10 · Partial Success +5 · Failure and Critical Failure: none'
    );
    expect(within(dialog).getByTestId('invocation-being-refused')).toHaveTextContent(
      'River Spirit: You have no favor with River Spirit to call on.'
    );

    await user.type(within(dialog).getByTestId('invocation-line'), 'A hush falls');
    await user.click(within(dialog).getByTestId('invocation-confirm'));

    await waitFor(() =>
      expect(screen.getByTestId('invocation-chosen')).toHaveTextContent(
        'Invoking Ombrin first (Easy)'
      )
    );

    await user.click(screen.getByText('[option label]'));
    expect(resolveMutate).toHaveBeenCalledWith(
      expect.objectContaining({
        instanceId: 7,
        option_id: 31,
        invoke_being_id: 5,
        invoke_line: 'A hush falls',
      }),
      expect.anything()
    );
  });

  it('shows the invocation lines and the breakdown in the result', async () => {
    resolveMutate.mockImplementation(
      (_vars: unknown, opts?: { onSuccess?: (r: ResolvedBeat) => void }) =>
        opts?.onSuccess?.(RESOLVED)
    );
    const user = userEvent.setup();
    render(withProviders(<BeatCard instanceId={7} roomKey="Gate" />));

    await user.click(screen.getByText('[option label]'));

    expect(screen.getByTestId('invocation-call-line')).toHaveTextContent(
      'Ysmay Dunhollow calls on Ombrin: [player line]'
    );
    expect(screen.getByTestId('invocation-outcome-line')).toHaveTextContent(
      "Ysmay Dunhollow's invocation: Success."
    );
    const breakdown = screen.getByTestId('invocation-breakdown');
    expect(breakdown).toHaveTextContent("Ombrin's favor (invocation: Success)");
    expect(breakdown).toHaveTextContent('+10');
    expect(breakdown).toHaveTextContent('58, rank Expert');
    expect(breakdown).toHaveTextContent('rank Expert');
    expect(screen.getByTestId('invocation-rank-difference')).toHaveTextContent(
      '0 (would be -1 without the bonus)'
    );
  });
});
