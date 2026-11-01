import { render, screen } from '@testing-library/react';
import { RollBreakdownCard, type RollBreakdown } from './RollBreakdownCard';

const lines = [
  {
    label: 'Melee Combat',
    value: '25',
    detail: 'strike skill for one-handed melee',
    lapsed: false,
  },
];

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

  it('strikes through a lapsed style skill and says why', () => {
    const offStyle: RollBreakdown = {
      heading: "Hit roll against Bandit's defense",
      lines: [
        ...lines,
        {
          label: 'The Daring Dance',
          value: '',
          detail: "two-handed weapons are not this style's",
          lapsed: true,
        },
      ],
      result: 'Hit, poor',
      result_note: '',
    };
    render(<RollBreakdownCard breakdown={offStyle} />);
    const [skill, style] = screen.getAllByTestId('roll-line-label');
    expect(skill).not.toHaveClass('line-through');
    expect(style).toHaveTextContent('The Daring Dance');
    expect(style).toHaveClass('line-through');
    expect(screen.getByText("two-handed weapons are not this style's")).toBeInTheDocument();
  });
});
