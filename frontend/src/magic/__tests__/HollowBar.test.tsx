import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { HollowBar } from '../components/HollowBar';

describe('HollowBar', () => {
  it('renders the bar with current and max displayed', () => {
    render(<HollowBar current={12} max={20} />);

    expect(screen.getByText('12/20')).toBeInTheDocument();
  });

  it('renders percentage correctly', () => {
    const { container } = render(<HollowBar current={10} max={20} />);

    // Progress value should be (10/20) * 100 = 50%
    // Check the indicator's transform style - it should be translateX(-50%)
    const indicator = container.querySelector('[style*="translateX"]');
    expect(indicator).toHaveStyle('transform: translateX(-50%)');
  });

  it('color is green/safe at low usage', () => {
    const { container } = render(<HollowBar current={2} max={20} />);

    const indicator = container.querySelector('[style*="translateX"]');
    expect(indicator).toHaveClass('bg-green-500');
  });

  it('color is red/danger at full usage', () => {
    const { container } = render(<HollowBar current={20} max={20} />);

    const indicator = container.querySelector('[style*="translateX"]');
    expect(indicator).toHaveClass('bg-red-500');
  });

  it('handles max=0 without dividing by zero', () => {
    const { container } = render(<HollowBar current={0} max={0} />);

    expect(screen.getByText('0/0')).toBeInTheDocument();

    // Should show 0% when max is 0, which means translateX(-100%)
    const indicator = container.querySelector('[style*="translateX"]');
    expect(indicator).toHaveStyle('transform: translateX(-100%)');
  });

  it('shows amber/yellow color at mid-range usage', () => {
    const { container } = render(<HollowBar current={12} max={20} />);

    const indicator = container.querySelector('[style*="translateX"]');
    expect(indicator).toHaveClass('bg-amber-500');
  });

  it('caps percentage at 100', () => {
    const { container } = render(<HollowBar current={150} max={100} />);

    // Even if current > max, percentage should cap at 100, which means translateX(-0%)
    const indicator = container.querySelector('[style*="translateX"]');
    expect(indicator).toHaveStyle('transform: translateX(-0%)');
  });
});
