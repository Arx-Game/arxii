import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { CastResonancePicker } from './CastResonancePicker';
import type { CastResonanceOption } from '../types';

const ARDERI: CastResonanceOption = {
  resonance_id: 3,
  name: 'Arderi',
  color_hex: '#d4a017',
  is_default: true,
  kindled_strength: null,
  reasons: [],
  stronger: false,
  adds_corruption: false,
};

const PRAEDARI: CastResonanceOption = {
  resonance_id: 9,
  name: 'Praedari',
  color_hex: '#7a1f3d',
  is_default: false,
  kindled_strength: 'Blazing',
  reasons: ['Someone is at your mercy.'],
  stronger: true,
  adds_corruption: true,
};

describe('CastResonancePicker', () => {
  it('draws the demo options with their cues and reports the pick', () => {
    const onSelect = vi.fn();
    render(
      <CastResonancePicker options={[ARDERI, PRAEDARI]} selectedId={null} onSelect={onSelect} />
    );

    expect(screen.getByText('Work it in:')).toBeInTheDocument();
    const usual = screen.getByTestId('cast-resonance-3');
    const praedari = screen.getByTestId('cast-resonance-9');
    expect(usual).toHaveTextContent('Arderi');
    expect(usual).toHaveTextContent('your usual');
    expect(usual).not.toHaveTextContent('Kindled');
    expect(usual).not.toHaveTextContent('Stronger');
    expect(usual).not.toHaveTextContent('Adds corruption.');
    expect(praedari).not.toHaveTextContent('your usual');
    expect(screen.getByTestId('cast-resonance-kindled-9')).toHaveTextContent('Kindled, Blazing');
    expect(praedari).toHaveTextContent('Someone is at your mercy.');
    expect(praedari).toHaveTextContent('Stronger here than Arderi.');
    expect(praedari).toHaveTextContent('Adds corruption.');
    expect(screen.getByTestId('cast-resonance-swatch-9')).toHaveStyle({
      backgroundColor: '#7a1f3d',
    });

    // Nothing picked means the usual one.
    expect(usual).toHaveAttribute('aria-pressed', 'true');
    expect(praedari).toHaveAttribute('aria-pressed', 'false');
    fireEvent.click(praedari);
    expect(onSelect).toHaveBeenCalledWith(9);
  });

  it('marks the picked option and releases the usual one', () => {
    render(<CastResonancePicker options={[ARDERI, PRAEDARI]} selectedId={9} onSelect={vi.fn()} />);
    expect(screen.getByTestId('cast-resonance-9')).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByTestId('cast-resonance-3')).toHaveAttribute('aria-pressed', 'false');
  });

  it('draws nothing for a single option', () => {
    render(<CastResonancePicker options={[ARDERI]} selectedId={null} onSelect={vi.fn()} />);
    expect(screen.queryByTestId('cast-resonance-picker')).not.toBeInTheDocument();
  });
});
