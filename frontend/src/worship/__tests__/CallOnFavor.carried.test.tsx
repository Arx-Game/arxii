/**
 * CallOnFavor keepsakes and Relic (#4530): a keepsake of the being she carries and the
 * being's Relic are listed with the worn pieces, each with the ease it gives.
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
        eases: [{ label: 'What you wear or carry: frayed climbing rope', points: 15 }],
        points: 60,
        band: 'hard',
        band_label: 'Hard',
      },
      worn: {
        pieces: [
          {
            source: 'keepsake',
            item_name: 'frayed climbing rope',
            facet_name: '',
            signals: [
              { kind: 'keepsake', kind_name: 'Keepsake', points: 1, detail: 'stands for Highwind' },
              {
                kind: 'keepsake_match',
                kind_name: 'Keepsake match',
                points: 2,
                detail: 'stands for Highwind',
              },
            ],
            points: 3,
            ease_per_point: 3,
            ease: 9,
            earning_percent: 0,
            counted: true,
          },
          {
            source: 'relic',
            item_name: 'cliff lantern',
            facet_name: '',
            signals: [
              {
                kind: 'keepsake',
                kind_name: 'Keepsake',
                points: 2,
                detail: 'relic of the Highwind',
              },
            ],
            points: 2,
            ease_per_point: 3,
            ease: 6,
            earning_percent: 0,
            counted: true,
          },
        ],
        ease: 15,
        raw_ease: 15,
        ease_cap: 40,
        items_counted_max: 3,
        earning_percent: 0,
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

describe('CallOnFavor keepsakes and Relic', () => {
  it('lists a keepsake of the being and its Relic with the ease each gives', async () => {
    await open();
    expect(screen.getByTestId('invocation-worn')).toHaveTextContent(
      'What you wear or carry for the Highwind'
    );
    const [rope, lantern] = screen.getAllByTestId('invocation-worn-piece');
    expect(within(rope).getByText('keepsake of the Highwind')).toBeInTheDocument();
    expect(within(rope).getByTestId('invocation-worn-counts')).toHaveTextContent(
      '3 points x 3 = eased 9'
    );
    expect(within(lantern).getByText('relic of the Highwind')).toBeInTheDocument();
    expect(within(lantern).getByTestId('invocation-worn-counts')).toHaveTextContent(
      '2 points x 3 = eased 6'
    );
  });
});
