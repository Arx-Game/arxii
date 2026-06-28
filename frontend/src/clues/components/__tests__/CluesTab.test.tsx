/**
 * CluesTab tests (#1575) — held-clue list, empty state, loading.
 */

import { render, screen } from '@testing-library/react';
import { vi } from 'vitest';

import { CluesTab } from '../CluesTab';
import type { HeldClue } from '../../api';

vi.mock('../../queries', () => ({
  useHeldClues: vi.fn(),
}));

import * as queries from '../../queries';

function mockClues(clues: HeldClue[] | undefined, isLoading = false) {
  vi.mocked(queries.useHeldClues).mockReturnValue({
    data: clues,
    isLoading,
  } as unknown as ReturnType<typeof queries.useHeldClues>);
}

function makeClue(overrides: Partial<HeldClue> = {}): HeldClue {
  return {
    id: 1,
    name: 'Torn Journal Page',
    description: 'A page ripped from a diary.',
    target_kind: 'codex',
    found_at: '2026-06-01T00:00:00Z',
    ...overrides,
  };
}

describe('CluesTab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows the empty state when no clues are held', () => {
    mockClues([]);
    render(<CluesTab characterSheetId={1} />);
    expect(screen.getByTestId('clues-empty-state')).toBeInTheDocument();
  });

  it('renders a row per held clue with name and description', () => {
    mockClues([
      makeClue(),
      makeClue({ id: 2, name: 'Bloodied Glove', description: 'A glove stained dark.' }),
    ]);
    render(<CluesTab characterSheetId={1} />);
    expect(screen.getAllByTestId('clue-row')).toHaveLength(2);
    expect(screen.getByText('Torn Journal Page')).toBeInTheDocument();
    expect(screen.getByText('A page ripped from a diary.')).toBeInTheDocument();
    expect(screen.getByText('Bloodied Glove')).toBeInTheDocument();
    expect(screen.getByText('A glove stained dark.')).toBeInTheDocument();
  });

  it('shows a spinner while loading', () => {
    mockClues(undefined, true);
    const { container } = render(<CluesTab characterSheetId={1} />);
    expect(container.querySelector('.animate-spin')).toBeInTheDocument();
  });
});
