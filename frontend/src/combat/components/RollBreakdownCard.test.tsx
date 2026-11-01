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

describe('RollBreakdownCard: a style off its way (#4884)', () => {
  it('strikes the style through on a Strike and on a defense, never the armor share', () => {
    const strike: RollBreakdown = {
      heading: "Hit roll against Bandit's defense",
      lines: [
        {
          label: 'Melee Combat',
          value: '25',
          detail: 'strike skill for two-handed melee',
          lapsed: false,
        },
        { label: 'Agility', value: '', detail: "the style's hit stat", lapsed: false },
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
    const defense: RollBreakdown = {
      heading: 'Defense against Blade',
      lines: [
        { label: 'Dodge', value: '15', detail: 'defense skill', lapsed: false },
        {
          label: 'The Daring Dance',
          value: '',
          detail: "heavy armor is not this style's",
          lapsed: true,
        },
        { label: 'Armor, 3 of 10', value: '', detail: "the style's armor share", lapsed: false },
      ],
      result: 'Partial Success, 8 damage',
      result_note: '',
    };
    render(
      <>
        <RollBreakdownCard breakdown={strike} />
        <RollBreakdownCard breakdown={defense} />
      </>
    );

    const labels = screen.getAllByTestId('roll-line-label');
    const struck = labels.filter((el) => el.classList.contains('line-through'));
    expect(struck.map((el) => el.textContent)).toEqual(['The Daring Dance', 'The Daring Dance']);
    expect(screen.getByText("two-handed weapons are not this style's")).toBeInTheDocument();
    expect(screen.getByText("heavy armor is not this style's")).toBeInTheDocument();
    // Off-style armor keeps the style's share (owner ruling, 2026-11-01): never struck.
    const armor = labels.find((el) => el.textContent === 'Armor, 3 of 10');
    expect(armor).not.toHaveClass('line-through');
  });
});
