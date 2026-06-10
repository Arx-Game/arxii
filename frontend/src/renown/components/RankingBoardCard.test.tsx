/**
 * #761 — RankingBoardCard: silent for non-boards, cloaked for outsiders,
 * names + qualitative bands (never numbers) for members.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { vi } from 'vitest';

import type { RankingBoard } from '../queries';

const useRankingBoardMock = vi.fn();

vi.mock('../queries', async () => {
  const actual = await vi.importActual<typeof import('../queries')>('../queries');
  return { ...actual, useRankingBoard: (...args: unknown[]) => useRankingBoardMock(...args) };
});

import { RankingBoardCard } from './RankingBoardCard';

function withProviders(children: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

const BOARD: RankingBoard = {
  display_id: 5,
  ranking_type: 'society_prestige',
  title: 'PLACEHOLDER Those the Society holds highest',
  cloaked: false,
  rows: [
    { persona_name: 'Alice', band_label: 'PLACEHOLDER the foremost' },
    { persona_name: 'Bob', band_label: '' },
  ],
};

describe('RankingBoardCard', () => {
  it('renders nothing when the object is not a board', () => {
    useRankingBoardMock.mockReturnValue({ data: null });
    const { container } = render(withProviders(<RankingBoardCard objectId={5} />));
    expect(container).toBeEmptyDOMElement();
  });

  it('renders names + band labels, never numbers', () => {
    useRankingBoardMock.mockReturnValue({ data: BOARD });
    render(withProviders(<RankingBoardCard objectId={5} />));
    expect(screen.getByTestId('ranking-rows')).toHaveTextContent('Alice');
    expect(screen.getByTestId('ranking-rows')).toHaveTextContent('PLACEHOLDER the foremost');
    expect(screen.getByTestId('ranking-rows').textContent).not.toMatch(/\d/);
  });

  it('renders the cloaked state for outsiders', () => {
    useRankingBoardMock.mockReturnValue({ data: { ...BOARD, cloaked: true, rows: [] } });
    render(withProviders(<RankingBoardCard objectId={5} />));
    expect(screen.getByTestId('ranking-cloaked')).toBeInTheDocument();
  });
});
