import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { StrainSlider } from '../StrainSlider';

describe('StrainSlider', () => {
  it('renders the slider with cap as max', () => {
    render(<StrainSlider value={0} cap={4} baseEffectiveCost={3} onChange={vi.fn()} />);
    const slider = screen.getByRole('slider');
    expect(slider).toHaveAttribute('aria-valuemax', '4');
    expect(slider).toHaveAttribute('aria-valuenow', '0');
  });

  it('shows the effective-cost readout including strain', () => {
    render(<StrainSlider value={2} cap={4} baseEffectiveCost={3} onChange={vi.fn()} />);
    // 3 (base) + 2 (strain) = 5
    expect(screen.getByText('Effective cost: 5 anima')).toBeInTheDocument();
  });

  it('renders the Soulfray over-pool warning when projected exceeds currentAnima', () => {
    render(
      <StrainSlider value={4} cap={4} baseEffectiveCost={3} currentAnima={5} onChange={vi.fn()} />
    );
    // 3 + 4 = 7 > 5 — warning fires
    expect(screen.getByText(/Insufficient anima/i)).toBeInTheDocument();
  });

  it('does NOT render the warning when projected fits in currentAnima', () => {
    render(
      <StrainSlider value={1} cap={4} baseEffectiveCost={3} currentAnima={10} onChange={vi.fn()} />
    );
    // 3 + 1 = 4 <= 10 — no warning
    expect(screen.queryByText(/Insufficient anima/i)).not.toBeInTheDocument();
  });
});
