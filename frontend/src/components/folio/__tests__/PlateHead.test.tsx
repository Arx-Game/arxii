/**
 * PlateHead (#3412 folio primitive) — the Cinzel identity/heading voice:
 * `.theme-heading` composition, small uppercase tracked label, muted. `as`
 * lets a caller pick real heading semantics without changing the look.
 */
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { PlateHead } from '../PlateHead';

describe('PlateHead', () => {
  it('renders as a plain element by default, composing .theme-heading', () => {
    render(<PlateHead>Your Characters</PlateHead>);

    const el = screen.getByText('Your Characters');
    expect(el.tagName).toBe('DIV');
    expect(el.className).toContain('theme-heading');
    expect(el.className).toContain('uppercase');
    expect(el.className).toContain('tracking-[0.24em]');
    expect(el.className).toContain('text-muted-foreground');
  });

  it('renders as the given element when `as` is set, keeping the same voice', () => {
    render(<PlateHead as="h2">Tidings</PlateHead>);

    const el = screen.getByRole('heading', { level: 2, name: 'Tidings' });
    expect(el.className).toContain('theme-heading');
  });
});
