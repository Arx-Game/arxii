/**
 * TitlesPanel tests (#1522) — earned-title list, empty state, loading.
 */

import { render, screen } from '@testing-library/react';
import { vi } from 'vitest';

import { TitlesPanel } from '../TitlesPanel';
import type { CharacterTitle } from '../../api';

vi.mock('../../queries', () => ({
  useCharacterTitles: vi.fn(),
}));

import * as queries from '../../queries';

function mockTitles(titles: CharacterTitle[] | undefined, isLoading = false) {
  vi.mocked(queries.useCharacterTitles).mockReturnValue({
    data: titles,
    isLoading,
  } as unknown as ReturnType<typeof queries.useCharacterTitles>);
}

function makeTitle(overrides: Partial<CharacterTitle> = {}): CharacterTitle {
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
    render(<TitlesPanel characterSheetId={1} />);
    expect(screen.getByTestId('titles-empty-state')).toBeInTheDocument();
  });

  it('renders a row per earned title', () => {
    mockTitles([makeTitle(), makeTitle({ id: 2, title: 'Storm Chaser' })]);
    render(<TitlesPanel characterSheetId={1} />);
    expect(screen.getAllByTestId('title-row')).toHaveLength(2);
    expect(screen.getByText('Hot Flex But Okay')).toBeInTheDocument();
    expect(screen.getByText('Storm Chaser')).toBeInTheDocument();
  });

  it('shows a spinner while loading', () => {
    mockTitles(undefined, true);
    const { container } = render(<TitlesPanel characterSheetId={1} />);
    expect(container.querySelector('.animate-spin')).toBeInTheDocument();
  });
});
