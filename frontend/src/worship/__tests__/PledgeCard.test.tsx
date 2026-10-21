/**
 * The pledge card (#4333 slice 2): three labelled parts, progress, each credit with its
 * calculation, and the closing rite once the target is met.
 */

import { fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { vi } from 'vitest';
import { PledgeCard } from '../components/PledgeCard';
import { timeLeft } from '../pledgeText';
import type { PledgeCard as PledgeCardData } from '../types';

const closeMutate = vi.fn();
vi.mock('@/inventory/hooks/useInventory', () => ({ useInventory: () => ({ data: [] }) }));
vi.mock('../queries', () => ({
  useClosePledge: vi.fn(() => ({ mutate: closeMutate, isPending: false })),
}));

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

const terms = {
  being_id: 4,
  being_name: 'Ombrin',
  rate: { base: 100, chosen_bonus: 100, modifiers: 0, worn_bonus: 0, total: 200 },
  lines: [{ label: 'Deeds that grant [favored resonance] (favored)', amount: '100% of amount' }],
  weekly_deed_cap: 8,
};

function card(overrides: Partial<PledgeCardData> = {}): PledgeCardData {
  return {
    id: 9,
    character_sheet: 3,
    pledge: {
      id: 2,
      being: 4,
      being_name: 'Ombrin',
      name: '[staff-authored pledge name]',
      description: '[staff-authored pledge description]',
      favor_target: 20,
      span_weeks: 2,
      closing_rite_name: "Ombrin's rite",
    },
    state: 'ready',
    progress: 20,
    target: 20,
    time_limit: new Date(Date.now() + 4.5 * 86_400_000).toISOString(),
    close_attempts: 0,
    retry_available: false,
    favor: 34,
    credits: [
      {
        id: 1,
        source: 'sacrifice',
        label: 'Sacrificed [item] (Silk facet, favored)',
        calculation:
          'carried 1 (held 30 days), own work 1 (made by the holder) = 2, x2 Silk = 4 points, eased 40. Success: 4 base, at 200% = +8',
        credited: 8,
        counts_toward_progress: true,
        created_at: new Date().toISOString(),
      },
    ],
    terms,
    requests: [],
    ...overrides,
  };
}

describe('PledgeCard', () => {
  it('shows the labelled parts, the progress and each credit with its calculation', () => {
    render(<PledgeCard card={card()} characterId={3} />, { wrapper });

    expect(screen.getByText('Pledge text · staff-authored')).toBeInTheDocument();
    expect(screen.getByText('Ready to close')).toBeInTheDocument();
    expect(screen.getByText('Favor target · staff-authored')).toBeInTheDocument();
    expect(screen.getByText('4 days left')).toBeInTheDocument();
    expect(screen.getByTestId('pledge-progress')).toHaveTextContent(
      '20 of 20 favor earned with Ombrin since pledging'
    );
    expect(
      screen.getByText('What earns favor with Ombrin for you · system-generated')
    ).toBeInTheDocument();
    expect(screen.getByText('200% · Chosen')).toBeInTheDocument();
    expect(screen.getByTestId('pledge-credits')).toHaveTextContent(
      'carried 1 (held 30 days), own work 1 (made by the holder) = 2, x2 Silk = 4 points, eased 40. Success: 4 base, at 200% = +8'
    );
  });

  it('closes with the closing rite when ready', () => {
    render(<PledgeCard card={card()} characterId={3} />, { wrapper });
    fireEvent.click(screen.getByTestId('close-pledge-button'));
    expect(closeMutate).toHaveBeenCalledWith({ itemIds: [] }, expect.anything());
    expect(screen.getByTestId('close-pledge-button')).toHaveTextContent(
      "Close the pledge with Ombrin's rite"
    );
  });

  it('lists what the pledge asks for with the count given and the points each', () => {
    render(
      <PledgeCard
        card={card({
          requests: [
            {
              id: 1,
              asked_for: 'weathervane pin',
              hint: '[staff-authored hint]',
              quantity: 1,
              given: 0,
              points: 3,
              where: 'pledge',
            },
            {
              id: 2,
              asked_for: 'any cheap item with the Kestrel facet',
              hint: '[staff-authored hint]',
              quantity: 2,
              given: 1,
              points: 2,
              where: 'closing rite',
            },
          ],
        })}
        characterId={3}
      />,
      { wrapper }
    );

    const rows = screen.getAllByTestId('pledge-request');
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent('weathervane pin');
    expect(rows[0]).toHaveTextContent('0 of 1');
    expect(rows[1]).toHaveTextContent('at the closing rite');
    expect(rows[1]).toHaveTextContent('1 of 2');
    expect(screen.getByTestId('pledge-requests')).toHaveTextContent(
      'cannot come out as a Critical Failure'
    );
  });

  it('shows no requests table when the pledge asks for nothing', () => {
    render(<PledgeCard card={card()} characterId={3} />, { wrapper });
    expect(screen.queryByTestId('pledge-requests')).not.toBeInTheDocument();
  });

  it('offers no close before the target or to a non-owner', () => {
    const { rerender } = render(
      <PledgeCard card={card({ state: 'open', progress: 6 })} characterId={3} />,
      { wrapper }
    );
    expect(screen.queryByTestId('close-pledge-button')).not.toBeInTheDocument();
    rerender(<PledgeCard card={card()} characterId={null} />);
    expect(screen.queryByTestId('close-pledge-button')).not.toBeInTheDocument();
  });

  it('notes the retry after a failed first close', () => {
    render(<PledgeCard card={card({ retry_available: true, close_attempts: 1 })} />, {
      wrapper,
    });
    expect(screen.getByText(/one more try is left within the span/)).toBeInTheDocument();
  });

  it('counts time left in days, then hours', () => {
    const now = Date.UTC(2026, 9, 15);
    expect(timeLeft(new Date(now + 2 * 86_400_000 + 5).toISOString(), now)).toBe('2 days left');
    expect(timeLeft(new Date(now + 5 * 3_600_000).toISOString(), now)).toBe('5 hours left');
    expect(timeLeft(new Date(now - 1).toISOString(), now)).toBe('span ended');
  });
});
