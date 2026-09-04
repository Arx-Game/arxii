import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { SceneClockPips } from './SceneClockPips';

describe('SceneClockPips (#3567)', () => {
  it('renders one pip per tick, filled pips first, with an accessible label', () => {
    render(<SceneClockPips size={5} filled={2} />);

    const clock = screen.getByTestId('scene-clock');
    expect(clock).toHaveAttribute('role', 'img');
    expect(clock).toHaveAttribute('aria-label', 'Clock 2 of 5');

    expect(screen.getAllByTestId('scene-clock-pip-filled')).toHaveLength(2);
    expect(screen.getAllByTestId('scene-clock-pip-empty')).toHaveLength(3);
    expect(clock).toHaveTextContent('2/5');
  });

  it('renders no filled pips when filled is 0', () => {
    render(<SceneClockPips size={3} filled={0} />);

    expect(screen.queryAllByTestId('scene-clock-pip-filled')).toHaveLength(0);
    expect(screen.getAllByTestId('scene-clock-pip-empty')).toHaveLength(3);
  });

  it('renders every pip filled when the clock is full', () => {
    render(<SceneClockPips size={4} filled={4} />);

    expect(screen.getAllByTestId('scene-clock-pip-filled')).toHaveLength(4);
    expect(screen.queryAllByTestId('scene-clock-pip-empty')).toHaveLength(0);
  });
});
