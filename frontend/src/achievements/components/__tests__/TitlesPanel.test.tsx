/**
 * TitlesPanel tests (#1522, #3466) — earned-title list, empty state, loading, null reward_key.
 */

import { render, screen } from '@testing-library/react';
import { vi } from 'vitest';

import { TitlesPanel } from '../TitlesPanel';
import type { PersonaTitle } from '../../api';

vi.mock('../../queries', () => ({
  usePersonaTitles: vi.fn(),
}));

import * as queries from '../../queries';

function mockTitles(titles: PersonaTitle[] | undefined, isLoading = false) {
  vi.mocked(queries.usePersonaTitles).mockReturnValue({
    data: titles,
    isLoading,
  } as unknown as ReturnType<typeof queries.usePersonaTitles>);
}

function makeTitle(overrides: Partial<PersonaTitle> = {}): PersonaTitle {
  return {
    id: 1,
    title: 'Hot Flex But Okay',
    reward_key: 'title.hot_flex',
    earned_at: '2026-06-01T00:00:00Z',
    ...overrides,
  };
}

describe('TitlesPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows the empty state when no titles are earned', () => {
    mockTitles([]);
    render(<TitlesPanel personaId={1} />);
    expect(screen.getByTestId('titles-empty-state')).toBeInTheDocument();
  });

  it('renders a row per earned title', () => {
    mockTitles([makeTitle(), makeTitle({ id: 2, title: 'Storm Chaser' })]);
    render(<TitlesPanel personaId={1} />);
    expect(screen.getAllByTestId('title-row')).toHaveLength(2);
    expect(screen.getByText('Hot Flex But Okay')).toBeInTheDocument();
    expect(screen.getByText('Storm Chaser')).toBeInTheDocument();
  });

  it('renders a deed-branch title with a null reward_key', () => {
    mockTitles([makeTitle({ title: 'Slew the Wyrm', reward_key: null })]);
    render(<TitlesPanel personaId={1} />);
    expect(screen.getByText('Slew the Wyrm')).toBeInTheDocument();
  });

  it('shows a spinner while loading', () => {
    mockTitles(undefined, true);
    const { container } = render(<TitlesPanel personaId={1} />);
    expect(container.querySelector('.animate-spin')).toBeInTheDocument();
  });
});
