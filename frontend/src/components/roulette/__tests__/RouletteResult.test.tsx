import { render, screen } from '@testing-library/react';
import { RouletteResult } from '../RouletteResult';
import type { ConsequenceDisplay } from '../types';

describe('RouletteResult', () => {
  it('shows the "Outcome" caption when tier_name matches the label', () => {
    const consequence: ConsequenceDisplay = {
      label: 'Partial Success',
      tier_name: 'Partial Success',
      weight: 33,
      is_selected: true,
    };

    render(<RouletteResult consequence={consequence} />);

    expect(screen.getByText('Outcome')).toBeInTheDocument();
    expect(screen.getByText('Partial Success')).toBeInTheDocument();
  });

  it('shows the tier name as the caption when it differs from the label', () => {
    const consequence: ConsequenceDisplay = {
      label: 'Lose 10 gold',
      tier_name: 'Mixed',
      weight: 33,
      is_selected: true,
    };

    render(<RouletteResult consequence={consequence} />);

    expect(screen.getByText('Mixed')).toBeInTheDocument();
    expect(screen.getByText('Lose 10 gold')).toBeInTheDocument();
  });
});
