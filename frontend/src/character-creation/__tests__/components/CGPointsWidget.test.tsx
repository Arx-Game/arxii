import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { CGPointsWidget } from '../../components/CGPointsWidget';

describe('CGPointsWidget', () => {
  it('displays remaining and starting points', () => {
    render(<CGPointsWidget starting={50} spent={10} remaining={40} />);
    expect(screen.getByText('CG Points Budget')).toBeInTheDocument();
    // AnimatedNumber renders the display value in a span
    expect(screen.getByText('40')).toBeInTheDocument();
    expect(screen.getByText(/\/50/)).toBeInTheDocument();
  });

  it('shows over budget warning when remaining is negative', () => {
    render(<CGPointsWidget starting={50} spent={55} remaining={-5} />);
    expect(screen.getByText('Over budget!')).toBeInTheDocument();
    expect(screen.getByText(/exceeded your budget/i)).toBeInTheDocument();
  });

  it('does not show over budget warning when within budget', () => {
    render(<CGPointsWidget starting={50} spent={10} remaining={40} />);
    expect(screen.queryByText('Over budget!')).not.toBeInTheDocument();
  });

  it('shows remaining count when within budget', () => {
    render(<CGPointsWidget starting={50} spent={10} remaining={40} />);
    expect(screen.getByText('40 remaining')).toBeInTheDocument();
  });

  it('applies destructive styling when over budget', () => {
    render(<CGPointsWidget starting={50} spent={55} remaining={-5} />);
    const value = screen.getByText('-5');
    expect(value).toHaveClass('text-destructive');
  });

  it('applies amber styling when points are low', () => {
    render(<CGPointsWidget starting={50} spent={42} remaining={8} />);
    const value = screen.getByText('8');
    expect(value).toHaveClass('text-amber-500');
  });

  it('applies default styling when points are normal', () => {
    render(<CGPointsWidget starting={50} spent={10} remaining={40} />);
    const value = screen.getByText('40');
    expect(value).toHaveClass('text-foreground');
  });

  it('handles zero budget gracefully', () => {
    render(<CGPointsWidget starting={0} spent={0} remaining={0} />);
    expect(screen.getByText('0 remaining')).toBeInTheDocument();
  });
});
