import { render, screen } from '@testing-library/react';
import { RollBreakdownCard, type RollBreakdown } from './RollBreakdownCard';

const lines = [{ label: 'Melee Combat', value: '25', detail: 'strike skill for one-handed melee' }];

describe('RollBreakdownCard', () => {
  it('notes "then the damage roll" beside a hit', () => {
    const hit: RollBreakdown = {
      heading: "Hit roll against Bandit's defense",
      lines,
      result: 'Hit, good',
      result_note: 'then the damage roll',
    };
    render(<RollBreakdownCard breakdown={hit} />);
    expect(screen.getByTestId('roll-result')).toHaveTextContent('Hit, good');
    expect(screen.getByTestId('roll-result-note')).toHaveTextContent('then the damage roll');
  });

  it('has no note beside a miss', () => {
    const miss: RollBreakdown = {
      heading: "Hit roll against Bandit's defense",
      lines,
      result: 'Miss',
      result_note: '',
    };
    render(<RollBreakdownCard breakdown={miss} />);
    expect(screen.getByTestId('roll-result')).toHaveTextContent('Miss');
    expect(screen.queryByTestId('roll-result-note')).not.toBeInTheDocument();
  });
});
