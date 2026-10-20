/**
 * Pledge yourself (#4333 slice 2): the pledge's authored text, its favor target and the
 * system-generated list of what earns favor, then `pledge_take` with the prayer.
 */

import { fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { vi } from 'vitest';
import { PledgeDialog } from '../components/PledgeDialog';

const takeMutate = vi.fn();
vi.mock('../queries', () => ({
  usePledges: vi.fn(() => ({
    data: [
      {
        id: 2,
        being: 4,
        being_name: 'Ombrin',
        name: '[staff-authored pledge name]',
        description: '[staff-authored pledge description]',
        favor_target: 20,
        span_weeks: 2,
        closing_rite_name: "Ombrin's rite",
      },
    ],
  })),
  useServiceTerms: vi.fn(() => ({
    data: {
      being_id: 4,
      being_name: 'Ombrin',
      rate: { base: 100, chosen_bonus: 100, modifiers: 0, total: 200 },
      lines: [
        { label: 'Deeds that grant [favored resonance] (favored)', amount: '100% of amount' },
        {
          label: 'Sacrifices at a shrine or temple of Ombrin',
          amount: 'a check, eased by what each item means to you; 3 a week',
        },
      ],
      weekly_deed_cap: 8,
    },
  })),
  useTakePledge: vi.fn(() => ({ mutate: takeMutate, isPending: false })),
}));
vi.mock('@/character-creation/queries', () => ({
  useWorshippedBeings: vi.fn(() => ({ data: [{ id: 4, name: 'Ombrin' }] })),
}));

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe('PledgeDialog', () => {
  it('shows the parts and pledges with the prayer', () => {
    render(<PledgeDialog characterId={3} defaultBeingId={4} fixedBeing />, { wrapper });
    fireEvent.click(screen.getByTestId('pledge-button'));

    expect(screen.getByText('Pledge yourself to Ombrin')).toBeInTheDocument();
    expect(screen.getByText('[staff-authored pledge description]')).toBeInTheDocument();
    expect(screen.getByTestId('earning-rate')).toHaveTextContent(
      'Your earning rate: 200% (100% + 100% Chosen + 0% favor-earning modifiers)'
    );
    expect(screen.getByText(/capped at 8 a week/)).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText(/\[staff-authored pledge name\]/));
    expect(screen.getByTestId('favor-target')).toHaveTextContent(
      '20 favor earned with Ombrin within 2 game weeks of pledging'
    );
    fireEvent.change(screen.getByLabelText(/Prayer/), {
      target: { value: '[player-written prayer]' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Pledge' }));
    expect(takeMutate).toHaveBeenCalledWith(
      { pledge: 2, prayer: '[player-written prayer]' },
      expect.anything()
    );
  });
});
