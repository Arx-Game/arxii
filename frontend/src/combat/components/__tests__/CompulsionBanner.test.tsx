import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import {
  CompulsionBanner,
  CompulsionChosenLine,
  CompulsionMark,
  compulsionCost,
} from '../CompulsionBanner';

const COMPULSION = {
  condition_name: 'Berserk',
  wants_label: 'Attack an opponent',
  check_name: 'Resist compulsion',
  against: [
    { action_key: 'flee', difficulty: 36, forbidden: true, extra_difficulty: 5 },
    { action_key: 'technique_no_target', difficulty: 31, forbidden: false, extra_difficulty: 0 },
  ],
};

describe('CompulsionBanner', () => {
  it('says what compels and what going against it needs', () => {
    render(<CompulsionBanner compulsion={COMPULSION} />);
    const banner = screen.getByTestId('compulsion-banner');
    expect(banner).toHaveTextContent('Berserk compels: attack an opponent.');
    expect(banner).toHaveTextContent(
      'Attacking is free. Any other action needs a Resist compulsion check this round. ' +
        'If the check fails, you attack instead.'
    );
  });
});

describe('CompulsionMark', () => {
  it('outlines an action against the compulsion and shows its difficulty', () => {
    render(
      <CompulsionMark compulsion={COMPULSION} actionKey="flee">
        <button type="button">Flee</button>
      </CompulsionMark>
    );
    expect(screen.getByTestId('compulsion-mark-flee')).toBeInTheDocument();
    expect(screen.getByTestId('compulsion-difficulty-flee')).toHaveTextContent(
      'Forbidden, difficulty 36'
    );
  });

  it('leaves an action the compulsion does not cost, or no compulsion, unmarked', () => {
    const { rerender } = render(
      <CompulsionMark compulsion={COMPULSION} actionKey="charge">
        <button type="button">Charge</button>
      </CompulsionMark>
    );
    expect(screen.queryByTestId('compulsion-mark-charge')).not.toBeInTheDocument();
    rerender(
      <CompulsionMark compulsion={null} actionKey="flee">
        <button type="button">Flee</button>
      </CompulsionMark>
    );
    expect(screen.queryByTestId('compulsion-mark-flee')).not.toBeInTheDocument();
    expect(compulsionCost(COMPULSION, 'technique_no_target')?.difficulty).toBe(31);
  });
});

describe('CompulsionChosenLine', () => {
  it('says what a forbidden action adds to the difficulty', () => {
    render(<CompulsionChosenLine compulsion={COMPULSION} actionKey="flee" />);
    expect(screen.getByTestId('compulsion-chosen-line')).toHaveTextContent(
      'Against Berserk. Berserk forbids Flee: Resist compulsion check, difficulty 36 ' +
        '(31 to resist, +5 because it is forbidden).'
    );
  });

  it('gives the plain check for an action that is not forbidden', () => {
    render(<CompulsionChosenLine compulsion={COMPULSION} actionKey="technique_no_target" />);
    expect(screen.getByTestId('compulsion-chosen-line')).toHaveTextContent(
      'Against Berserk. Resist compulsion check, difficulty 31.'
    );
  });
});
