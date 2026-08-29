/**
 * CountChip (#3412 folio primitive) — square, PRIMARY-colored (never
 * destructive red, ruled 2026-08-28), tabular-nums count with a mandatory
 * title/aria-label carrying the full accessible sentence, not just the digit.
 */
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { CountChip } from '../CountChip';

describe('CountChip', () => {
  it('renders the count with a title/aria-label carrying the full fact', () => {
    render(<CountChip count={4} label="tidings waiting" />);

    const el = screen.getByText('4');
    expect(el).toHaveAttribute('title', '4 tidings waiting');
    expect(el).toHaveAttribute('aria-label', '4 tidings waiting');
  });

  it('is square and primary-colored, never destructive red', () => {
    render(<CountChip count={1} label="unread" />);

    const el = screen.getByText('1');
    expect(el.className).toContain('rounded-none');
    expect(el.className).toContain('bg-primary');
    expect(el.className).toContain('text-primary-foreground');
    expect(el.className).not.toMatch(/destructive/);
  });

  it('renders nothing at a zero or negative count', () => {
    const { container: zero } = render(<CountChip count={0} label="unread" />);
    expect(zero).toBeEmptyDOMElement();

    const { container: negative } = render(<CountChip count={-1} label="unread" />);
    expect(negative).toBeEmptyDOMElement();
  });
});
