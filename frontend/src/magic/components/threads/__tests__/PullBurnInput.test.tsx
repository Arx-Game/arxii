import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { PullBurnInput } from '../PullBurnInput';
import type { BurnPreview } from '../../../types';

const BURN: BurnPreview = {
  ceiling: 5,
  strain_units_per_point: '1.5',
  hasty_fall: false,
  available: true,
};

describe('PullBurnInput', () => {
  it('renders nothing without burn numbers', () => {
    const { container } = render(
      <PullBurnInput burn={null} value={0} onChange={vi.fn()} tier={1} />
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing when no strain check is designated', () => {
    const { container } = render(
      <PullBurnInput burn={{ ...BURN, available: false }} value={0} onChange={vi.fn()} tier={1} />
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('shows the ceiling at the pull tier', () => {
    render(<PullBurnInput burn={BURN} value={0} onChange={vi.fn()} tier={2} />);
    expect(screen.getByTestId('pull-burn-ceiling')).toHaveTextContent(
      'Burn ceiling at Tier 2: 5 resonance'
    );
    expect(screen.queryByTestId('pull-burn-hasty')).not.toBeInTheDocument();
  });

  it('shows the hasty-fall note when the burn falls at the pair rate', () => {
    render(
      <PullBurnInput burn={{ ...BURN, hasty_fall: true }} value={0} onChange={vi.fn()} tier={1} />
    );
    expect(screen.getByTestId('pull-burn-hasty')).toBeInTheDocument();
  });

  it('reports a whole number clamped to the ceiling', () => {
    const onChange = vi.fn();
    render(<PullBurnInput burn={BURN} value={0} onChange={onChange} tier={1} />);
    const input = screen.getByTestId('pull-burn-input');
    fireEvent.change(input, { target: { value: '3' } });
    expect(onChange).toHaveBeenLastCalledWith(3);
    fireEvent.change(input, { target: { value: '50' } });
    expect(onChange).toHaveBeenLastCalledWith(5);
    fireEvent.change(input, { target: { value: '-2' } });
    expect(onChange).toHaveBeenLastCalledWith(0);
  });

  it('is disabled when the ceiling is 0', () => {
    render(<PullBurnInput burn={{ ...BURN, ceiling: 0 }} value={0} onChange={vi.fn()} tier={1} />);
    expect(screen.getByTestId('pull-burn-input')).toBeDisabled();
  });
});
