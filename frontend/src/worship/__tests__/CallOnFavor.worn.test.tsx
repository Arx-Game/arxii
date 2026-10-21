/**
 * CallOnFavor worn pieces (#4520): the picker lists the pieces the character wears that
 * carry a facet the selected being favors, what each means, and the ease it gives. A
 * bought piece with no history is listed and adds nothing.
 */
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi } from 'vitest';
import type { InvocationOptions } from '../types';

const OPTIONS: InvocationOptions = {
  beings: [
    {
      being_id: 5,
      being_name: 'the Highwind',
      favor: 44,
      can_invoke: true,
      refusal: '',
      uses_left: 3,
      uses_per_week: 3,
      difficulty: {
        base_points: 75,
        base_band: 'daunting',
        base_band_label: 'Daunting',
        eases: [{ label: 'What you wear: riding coat', points: 20 }],
        points: 55,
        band: 'hard',
        band_label: 'Hard',
      },
      worn: {
        pieces: [
          {
            source: 'worn',
            item_name: 'riding coat',
            facet_name: 'Kestrel',
            signals: [
              { kind: 'carried', kind_name: 'Carried', points: 3, detail: 'held 150 days' },
              { kind: 'made_by_tie', kind_name: 'Made by a tie', points: 2, detail: 'Corwen' },
            ],
            points: 5,
            ease_per_point: 2,
            ease: 10,
            earning_percent: 5,
            counted: true,
          },
          {
            source: 'worn',
            item_name: 'kestrel brooch',
            facet_name: 'Kestrel',
            signals: [],
            points: 0,
            ease_per_point: 2,
            ease: 0,
            earning_percent: 0,
            counted: false,
          },
        ],
        ease: 10,
        raw_ease: 10,
        ease_cap: 40,
        items_counted_max: 3,
        earning_percent: 5,
      },
    },
  ],
  bonuses: [{ outcome_name: 'Success', success_level: 1, bonus: 10 }],
};

vi.mock('../queries', () => ({
  useInvocationOptions: () => ({ data: OPTIONS, isLoading: false, error: null }),
}));

import { CallOnFavor } from '../components/CallOnFavor';

function open() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  render(
    <QueryClientProvider client={qc}>
      <CallOnFavor value={null} onChange={() => {}} inline />
    </QueryClientProvider>
  );
  return userEvent.click(screen.getByTestId('call-on-favor'));
}

describe('CallOnFavor worn pieces', () => {
  it('shows each worn piece with what it means and the ease it gives', async () => {
    await open();
    const pieces = screen.getAllByTestId('invocation-worn-piece');
    expect(pieces).toHaveLength(2);
    expect(within(pieces[0]).getByText('riding coat')).toBeInTheDocument();
    expect(within(pieces[0]).getByText('carried, held 150 days')).toBeInTheDocument();
    expect(within(pieces[0]).getByText('made by a tie, Corwen')).toBeInTheDocument();
    expect(within(pieces[0]).getByText('Kestrel, favored')).toBeInTheDocument();
    expect(within(pieces[0]).getByTestId('invocation-worn-counts')).toHaveTextContent(
      '5 points x 2 = eased 10'
    );
  });

  it('lists a bought piece with no history as adding nothing', async () => {
    await open();
    const brooch = screen.getAllByTestId('invocation-worn-piece')[1];
    expect(within(brooch).getByText('bought; no history beyond holding it')).toBeInTheDocument();
    expect(within(brooch).getByTestId('invocation-worn-counts')).toHaveTextContent('0');
  });

  it('states the limits and the earning-rate rise', async () => {
    await open();
    const note = screen.getByTestId('invocation-worn-note');
    expect(note).toHaveTextContent('Up to 3 worn pieces count');
    expect(note).toHaveTextContent('capped at 40');
    expect(note).toHaveTextContent(
      'Earning rate with the Highwind while you wear these: 100% + 5%'
    );
  });
});
