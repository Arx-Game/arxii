/**
 * HonorList tests (#3466 Task 10) — the honors a deed has received, and what people
 * wrote about it.
 */
import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';

import { HonorList } from '../HonorList';
import type { LegendHonor } from '../../api';

function makeHonor(overrides: Partial<LegendHonor> = {}): LegendHonor {
  return {
    id: 1,
    honorer: { id: 9, name: 'Bar' },
    value_added: 10,
    hares_spent: 1,
    established_deed: false,
    created_at: '2026-08-30T00:00:00Z',
    journal: { id: 4, title: 'A Great Deed', body: 'They spoke of it for years.' },
    ...overrides,
  };
}

describe('HonorList', () => {
  it('shows the empty state when no honors exist', () => {
    render(<HonorList honors={[]} />);
    expect(screen.getByTestId('honor-list-empty')).toBeInTheDocument();
  });

  it('renders a row per honor with the honorer name and journal', () => {
    render(
      <HonorList
        honors={[
          makeHonor(),
          makeHonor({
            id: 2,
            honorer: { id: 10, name: 'Quill' },
            journal: { id: 5, title: 'A Second Voice', body: 'Another account.' },
          }),
        ]}
      />
    );
    expect(screen.getAllByTestId('honor-row')).toHaveLength(2);
    expect(screen.getByText('Bar')).toBeInTheDocument();
    expect(screen.getByText('A Great Deed')).toBeInTheDocument();
    expect(screen.getByText('They spoke of it for years.')).toBeInTheDocument();
    expect(screen.getByText('Quill')).toBeInTheDocument();
    expect(screen.getByText('A Second Voice')).toBeInTheDocument();
  });

  it('marks the honor that established the deed', () => {
    render(<HonorList honors={[makeHonor({ established_deed: true })]} />);
    expect(screen.getByText(/established/i)).toBeInTheDocument();
  });

  it('shows hares spent and value added per honor', () => {
    render(<HonorList honors={[makeHonor({ hares_spent: 2, value_added: 15 })]} />);
    const row = screen.getByTestId('honor-row');
    expect(row).toHaveTextContent('2');
    expect(row).toHaveTextContent('15');
  });
});
