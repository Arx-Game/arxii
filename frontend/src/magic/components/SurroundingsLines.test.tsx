import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { SurroundingsLine } from '@/scenes/actionTypes';
import { SurroundingsLines } from './SurroundingsLines';

const line = (overrides: Partial<SurroundingsLine>): SurroundingsLine => ({
  kind: 'source',
  text: '',
  amount: 0,
  anima: 0,
  detail: '',
  ...overrides,
});

describe('SurroundingsLines', () => {
  it('shows a heading, each source with its points, and the power they add', () => {
    render(
      <SurroundingsLines
        lines={[
          line({ kind: 'heading', text: 'Fire around you' }),
          line({ text: 'The forge · Trace', amount: 1 }),
          line({ text: 'Ember-lined coat, worn · carries fire', amount: 2 }),
          line({ kind: 'power', text: 'Fire adds', amount: 3 }),
        ]}
      />
    );

    expect(screen.getByText('Fire around you')).toBeInTheDocument();
    expect(screen.getByText('The forge · Trace').nextSibling).toHaveTextContent('1');
    expect(screen.getByText('Fire adds').nextSibling).toHaveTextContent('+3 power');
  });

  it('shows a source that works against her in the warning colour, with the minus', () => {
    render(
      <SurroundingsLines
        lines={[line({ kind: 'power', text: 'Something here works against your ice', amount: -6 })]}
      />
    );

    const power = screen.getByText('-6 power');
    expect(power).toHaveClass('text-amber-700');
  });
});
