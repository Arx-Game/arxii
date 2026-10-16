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
  rate: { base: 100, chosen_bonus: 100, modifiers: 0, total: 200 },
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
        calculation: 'value 20: 2 base, x2 Silk = 4, at 200% = +8',
        credited: 8,
        counts_toward_progress: true,
        created_at: new Date().toISOString(),
      },
    ],
    terms,
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
      'value 20: 2 base, x2 Silk = 4, at 200% = +8'
    );
  });

  it('closes with the closing rite when ready', () => {
    render(<PledgeCard card={card()} characterId={3} />, { wrapper });
    fireEvent.click(screen.getByTestId('close-pledge-button'));
    expect(closeMutate).toHaveBeenCalled();
    expect(screen.getByTestId('close-pledge-button')).toHaveTextContent(
      "Close the pledge with Ombrin's rite"
    );
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
