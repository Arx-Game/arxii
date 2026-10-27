import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { PullBurnInput } from '../PullBurnInput';
import { burnStrainUnits, effectiveBurn } from '../../../burn';
import type { BurnPreview } from '../../../types';

const BURN: BurnPreview = {
  ceiling: 5,
  strain_units_per_point: '1.5',
  hasty_fall: false,
  available: true,
  resonance_name: 'Dawnlight',
  off_affinity: false,
  corruption_affinity_name: null,
  ceiling_tier_name: 'Amplified',
};

describe('PullBurnInput', () => {
  it('renders nothing without burn numbers', () => {
    const { container } = render(<PullBurnInput preview={null} value={0} onChange={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing when no strain check is designated', () => {
    const { container } = render(
      <PullBurnInput preview={{ ...BURN, available: false }} value={0} onChange={vi.fn()} />
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('labels the row with the pulled resonance as hers', () => {
    render(<PullBurnInput preview={BURN} value={0} onChange={vi.fn()} />);
    expect(screen.getByTestId('pull-burn-label')).toHaveTextContent('Dawnlight (yours)');
  });

  it('labels an off-affinity resonance', () => {
    render(
      <PullBurnInput
        preview={{ ...BURN, resonance_name: 'Ruin', off_affinity: true }}
        value={0}
        onChange={vi.fn()}
      />
    );
    expect(screen.getByTestId('pull-burn-label')).toHaveTextContent('Ruin (off-affinity)');
  });

  it('shows the ceiling at the intensity tier the server names', () => {
    render(<PullBurnInput preview={BURN} value={0} onChange={vi.fn()} tier={2} />);
    expect(screen.getByTestId('pull-burn-ceiling')).toHaveTextContent(
      'Burn ceiling at Amplified: 5 resonance'
    );
  });

  it('falls back to the pull tier when no intensity tier is named', () => {
    render(
      <PullBurnInput
        preview={{ ...BURN, ceiling_tier_name: null }}
        value={0}
        onChange={vi.fn()}
        tier={2}
      />
    );
    expect(screen.getByTestId('pull-burn-ceiling')).toHaveTextContent(
      'Burn ceiling at Tier 2: 5 resonance'
    );
  });

  it('notes the strain check and the power only once something is burned', () => {
    const { rerender } = render(
      <PullBurnInput preview={BURN} value={0} onChange={vi.fn()} powerBonus={12} />
    );
    expect(screen.queryByTestId('pull-burn-check')).not.toBeInTheDocument();
    expect(screen.queryByTestId('pull-burn-power')).not.toBeInTheDocument();
    rerender(<PullBurnInput preview={BURN} value={3} onChange={vi.fn()} powerBonus={12} />);
    expect(screen.getByTestId('pull-burn-check')).toHaveTextContent(
      'Strain check on submit. Degrees decide how much of the 3 you reach.'
    );
    expect(screen.getByTestId('pull-burn-power')).toHaveTextContent('up to +12 power');
  });

  it('warns that a raw off-affinity burn leaves corruption', () => {
    render(
      <PullBurnInput
        preview={{
          ...BURN,
          resonance_name: 'Ruin',
          off_affinity: true,
          corruption_affinity_name: 'Abyssal',
        }}
        value={2}
        onChange={vi.fn()}
      />
    );
    expect(screen.getByTestId('pull-burn-off-affinity')).toHaveTextContent(
      'Burning Ruin raw. It leaves Abyssal corruption you will need cleansed.'
    );
    expect(screen.queryByTestId('pull-burn-hasty')).not.toBeInTheDocument();
  });

  it('warns of a hasty fall instead of a raw burn', () => {
    render(
      <PullBurnInput
        preview={{
          ...BURN,
          hasty_fall: true,
          off_affinity: true,
          corruption_affinity_name: 'Abyssal',
        }}
        value={2}
        onChange={vi.fn()}
      />
    );
    expect(screen.getByTestId('pull-burn-hasty')).toHaveTextContent(
      'Hasty fall. No rite, so it leaves extra Abyssal corruption.'
    );
    expect(screen.queryByTestId('pull-burn-off-affinity')).not.toBeInTheDocument();
  });

  it('reports a whole number clamped to the ceiling', () => {
    const onChange = vi.fn();
    render(<PullBurnInput preview={BURN} value={0} onChange={onChange} />);
    const input = screen.getByTestId('pull-burn-input');
    fireEvent.change(input, { target: { value: '3' } });
    expect(onChange).toHaveBeenLastCalledWith(3);
    fireEvent.change(input, { target: { value: '50' } });
    expect(onChange).toHaveBeenLastCalledWith(5);
    fireEvent.change(input, { target: { value: '-2' } });
    expect(onChange).toHaveBeenLastCalledWith(0);
  });

  it('is disabled when the ceiling is 0', () => {
    render(<PullBurnInput preview={{ ...BURN, ceiling: 0 }} value={0} onChange={vi.fn()} />);
    expect(screen.getByTestId('pull-burn-input')).toBeDisabled();
  });
});

describe('burn helpers', () => {
  it('caps the burn at the ceiling and drops it when unavailable', () => {
    expect(effectiveBurn(BURN, 9)).toBe(5);
    expect(effectiveBurn({ ...BURN, available: false }, 3)).toBe(0);
    expect(effectiveBurn(null, 3)).toBe(0);
  });

  it('values burned points at the per-point strain, floored', () => {
    expect(burnStrainUnits(BURN, 3)).toBe(4);
    expect(burnStrainUnits(BURN, 0)).toBe(0);
  });
});
