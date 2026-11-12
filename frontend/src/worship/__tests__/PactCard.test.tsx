/**
 * The pact card (#4341): this period's favor against the commitment, what earned it by source,
 * the current stage, the promises, and Renounce after a confirmation. An ended pact still
 * easing out shows how fast it eases and offers nothing.
 */

import { fireEvent, render, screen } from '@testing-library/react';
import { vi } from 'vitest';
import { PactCard } from '../components/PactCard';
import type { PactCard as PactCardData } from '../types';

const renounceMutate = vi.fn();
vi.mock('../queries', () => ({
  useRenouncePact: vi.fn(() => ({ mutate: renounceMutate, isPending: false })),
}));

const stages = [
  { name: 'Sworn', threshold: 1, effects: [], is_last: false },
  { name: 'Strained', threshold: 11, effects: [], is_last: false },
  { name: 'Soured', threshold: 21, effects: [], is_last: false },
  { name: 'Breached', threshold: 31, effects: [], is_last: true },
];

function card(overrides: Partial<PactCardData> = {}): PactCardData {
  return {
    id: 5,
    character_sheet: 3,
    being_id: 7,
    being_name: 'Hesk',
    offer_name: '[offer name]',
    period_weeks: 2,
    severity_per_miss: 10,
    earned: 6,
    required: 8,
    time_limit: new Date(Date.now() + 4.5 * 86_400_000).toISOString(),
    sources: [
      { label: 'Deeds: resonances Hesk favors, from missions and scenes', favor: 4 },
      { label: "Hesk's rite, which you performed", favor: 2 },
    ],
    stage_name: 'Sworn',
    severity: 1,
    next_stage_threshold: 11,
    promises: ['[staff-authored promise line]'],
    condition_effects: [],
    stages,
    is_active: true,
    dissolution_reason: '',
    ...overrides,
  };
}

describe('PactCard', () => {
  beforeEach(() => renounceMutate.mockReset());

  it('shows the period, its sources, the stage and the promises', () => {
    render(<PactCard card={card()} characterId={3} />);
    expect(screen.getByText('Pact: Hesk')).toBeInTheDocument();
    expect(screen.getByTestId('pact-progress')).toHaveTextContent(
      'This period: 6 of 8 favor earned, 4 days left.'
    );
    expect(screen.getByRole('progressbar')).toHaveAttribute('value', '6');
    expect(screen.getByTestId('pact-sources')).toHaveTextContent(
      'Deeds: resonances Hesk favors, from missions and scenes+4'
    );
    expect(screen.getByTestId('pact-sources')).toHaveTextContent(
      "Hesk's rite, which you performed+2"
    );
    expect(screen.getByTestId('pact-stage')).toHaveTextContent(
      'Current stage: 1. Sworn. Severity 1; stage 2 begins at 11.'
    );
    expect(screen.getByTestId('pact-card-promise')).toHaveTextContent(
      '[staff-authored promise line]'
    );
  });

  it('renounces only after the confirmation', async () => {
    render(<PactCard card={card()} characterId={3} />);
    fireEvent.click(screen.getByTestId('renounce-pact-button'));
    expect(renounceMutate).not.toHaveBeenCalled();
    // At the first stage (the pact's benefit) nothing eases out: it ends with the pact.
    expect(await screen.findByText('Sworn ends with the pact.')).toBeInTheDocument();
    fireEvent.click(await screen.findByTestId('confirm-renounce-pact'));
    expect(renounceMutate).toHaveBeenCalledWith(7, expect.any(Object));
  });

  it('offers no renounce to a reader who is not the holder', () => {
    render(<PactCard card={card()} characterId={null} />);
    expect(screen.queryByTestId('renounce-pact-button')).not.toBeInTheDocument();
  });

  it('shows an ended pact easing out, with nothing to do', () => {
    render(
      <PactCard
        card={card({
          is_active: false,
          dissolution_reason: 'renounced',
          stage_name: 'Strained',
          severity: 12,
          required: 0,
          earned: 0,
          sources: [],
        })}
        characterId={3}
      />
    );
    expect(screen.getByTestId('pact-ended')).toHaveTextContent(
      'Ended. Current stage: 2. Strained. Strained eases by 10 each period until it is gone.'
    );
    expect(screen.queryByTestId('renounce-pact-button')).not.toBeInTheDocument();
    expect(screen.queryByTestId('pact-progress')).not.toBeInTheDocument();
  });
});
