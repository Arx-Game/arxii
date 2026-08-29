/**
 * Plate (#3412 folio primitive) — the squared-geometry law in isolation:
 * no border radius, hairline border, `bg-card` token, no shadow.
 */
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { Plate } from '../Plate';

describe('Plate', () => {
  it('renders children inside a square-cornered, bordered, shadowless surface', () => {
    render(<Plate>Contents</Plate>);

    const el = screen.getByText('Contents');
    expect(el.className).toContain('rounded-none');
    expect(el.className).toContain('border');
    expect(el.className).toContain('bg-card');
    expect(el.className).toContain('shadow-none');
    expect(el.className).not.toMatch(/rounded-(sm|md|lg|xl|full)\b/);
  });

  it('merges a caller className without losing the squared-geometry law by default', () => {
    render(<Plate className="p-4">Padded</Plate>);

    expect(screen.getByText('Padded').className).toContain('p-4');
  });

  it('passes through arbitrary div props', () => {
    render(<Plate data-testid="my-plate">Tagged</Plate>);

    expect(screen.getByTestId('my-plate')).toBeInTheDocument();
  });
});
