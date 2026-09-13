import { render, screen } from '@testing-library/react';
import { RouletteResult } from '../RouletteResult';
import type { ConsequenceDisplay } from '../types';

describe('RouletteResult', () => {
  it('hides the eyebrow when tier_name matches the label', () => {
    const consequence: ConsequenceDisplay = {
      label: 'Partial Success',
      tier_name: 'Partial Success',
      weight: 33,
      is_selected: true,
    };

    render(<RouletteResult consequence={consequence} />);

    expect(screen.getByText('Partial Success')).toBeInTheDocument();
    // Only one node should render the outcome name - the eyebrow is suppressed.
    expect(screen.getAllByText('Partial Success')).toHaveLength(1);
  });

  it('shows the eyebrow when tier_name differs from the label', () => {
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
