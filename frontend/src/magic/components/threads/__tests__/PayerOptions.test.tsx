import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { PayerOptions } from '../PayerOptions';
import type { PayerOption, Thread } from '../../../types';

const effect = (kind: string, value: number, snippet = '') => ({
  kind,
  authored_value: value,
  level_multiplier: 1,
  scaled_value: value,
  vital_target: null,
  source_thread_id: 1,
  source_thread_level: 3,
  source_tier: 2,
  narrative_snippet: snippet,
  inactive: false,
  inactive_reason: null,
});

const option = (
  id: number,
  name: string,
  balance: number,
  effects: PayerOption['effects'],
  levelRead = 3
): PayerOption => ({
  resonance_id: id,
  resonance_name: name,
  cost: 3,
  balance,
  affordable: balance >= 3,
  effects,
  level_read: levelRead,
});

const makeThread = (overrides: Partial<Thread> = {}): Thread =>
  ({
    id: 1,
    owner: 100,
    resonance: 1,
    resonance_name: 'Fury',
    resonances: [
      { resonance_id: 1, resonance_name: 'Fury', amount: 30, leads: true },
      { resonance_id: 2, resonance_name: 'Domination', amount: 10, leads: false },
    ],
    target_kind: 'GIFT',
    name: 'Pyromancy',
    level: 3,
    ...overrides,
  }) as Thread;

const OPTIONS = [
  option(1, 'Fury', 22, [
    effect('FLAT_BONUS', 4),
    effect('INTENSITY_BUMP', 2, 'The flames answer your anger before you call them.'),
  ]),
  option(2, 'Domination', 14, [effect('FLAT_BONUS', 2)], 2),
  option(3, 'Wonder', 9, []),
];

describe('PayerOptions', () => {
  it('lists each payer of a multi-resonance thread with its own perks, starting on the leader', () => {
    render(
      <PayerOptions
        thread={makeThread()}
        options={OPTIONS}
        selectedResonanceId={1}
        onSelect={vi.fn()}
      />
    );
    expect(screen.getByRole('radiogroup')).toBeInTheDocument();
    expect(screen.getByTestId('payer-1-1')).toHaveAttribute('aria-checked', 'true');
    expect(screen.getByTestId('payer-1-2')).toHaveAttribute('aria-checked', 'false');
    expect(screen.getByTestId('payer-1-1')).toHaveTextContent('3 Fury · you have 22');
    expect(screen.getByTestId('payer-perks-1-1')).toHaveTextContent('Bonus to this cast+4');
    expect(screen.getByTestId('payer-perks-1-1')).toHaveTextContent('Intensity+2');
    expect(screen.getByTestId('payer-perks-1-1')).toHaveTextContent(
      'The flames answer your anger before you call them.'
    );
    // Each payer reads its own perks, never a sum.
    expect(screen.getByTestId('payer-perks-1-2')).toHaveTextContent('Bonus to this cast+2');
    expect(screen.getByTestId('payer-perks-1-2')).not.toHaveTextContent('+4');
    // A held resonance the thread never took in pays with no perks.
    expect(screen.getByTestId('payer-no-perks-1')).toHaveTextContent('No perks on this thread');
  });

  it('reports the payer picked', () => {
    const onSelect = vi.fn();
    render(
      <PayerOptions
        thread={makeThread()}
        options={OPTIONS}
        selectedResonanceId={1}
        onSelect={onSelect}
      />
    );
    fireEvent.click(screen.getByTestId('payer-1-2'));
    expect(onSelect).toHaveBeenCalledWith(2);
  });

  it('cannot pick a payer that cannot afford the cost', () => {
    const onSelect = vi.fn();
    render(
      <PayerOptions
        thread={makeThread()}
        options={[OPTIONS[0], option(2, 'Domination', 1, [])]}
        selectedResonanceId={1}
        onSelect={onSelect}
      />
    );
    expect(screen.getByTestId('payer-1-2')).toBeDisabled();
  });

  it('shows no choice on a thread with one resonance', () => {
    const single = makeThread({
      resonances: [{ resonance_id: 1, resonance_name: 'Fury', amount: 30, leads: true }],
    });
    render(
      <PayerOptions thread={single} options={OPTIONS} selectedResonanceId={1} onSelect={vi.fn()} />
    );
    expect(screen.queryByRole('radiogroup')).not.toBeInTheDocument();
    expect(screen.getByTestId('payer-fixed-1')).toHaveTextContent('Pays with Fury');
    expect(screen.getByTestId('payer-fixed-1')).toHaveTextContent('3 Fury · you have 22');
    expect(screen.getByTestId('payer-fixed-1')).toHaveTextContent('Bonus to this cast+4');
    expect(screen.queryByText('Domination')).not.toBeInTheDocument();
  });

  it('opens Inspect perks for the payer, showing the source and the level read', () => {
    render(
      <PayerOptions
        thread={makeThread()}
        options={OPTIONS}
        selectedResonanceId={1}
        onSelect={vi.fn()}
      />
    );
    // A payer with no perks has nothing to inspect.
    expect(screen.queryByTestId('payer-inspect-1-3')).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId('payer-inspect-1-2'));
    const panel = screen.getByTestId('perk-inspect');
    expect(panel).toHaveTextContent('Domination through Pyromancy');
    expect(panel).toHaveTextContent('Domination pull perk for Gift threads, tier 2');
    expect(panel).toHaveTextContent('2 (thread is 3; Domination is not its leading resonance)');
  });
});
