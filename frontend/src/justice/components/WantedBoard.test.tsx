/**
 * WantedBoard "Standing sentences" tests (#2378 Task 8) — the `records` array
 * from the wanted endpoint.
 *
 * Mirrors MotifStylePanel.test.tsx's idiom: mock the '../queries' module
 * (no msw), render with providers, assert on data-testid hooks.
 */

import { screen } from '@testing-library/react';
import { vi } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { WantedBoard } from './WantedBoard';
import type { WantedBoardData } from '../api';
import type { usePardonMutation, useSubmitEvidenceMutation, useWantedList } from '../queries';

vi.mock('../queries', () => ({
  useWantedList: vi.fn(),
  usePardonMutation: vi.fn(),
  useSubmitEvidenceMutation: vi.fn(),
}));

import * as justiceQueries from '../queries';

const emptyBoard: WantedBoardData = {
  wanted: [],
  held: [],
  viewer_can_pardon: false,
  records: [],
};

function setupMocks(data: WantedBoardData | undefined) {
  vi.mocked(justiceQueries.useWantedList).mockReturnValue({
    data,
    isLoading: false,
  } as unknown as ReturnType<typeof useWantedList>);

  vi.mocked(justiceQueries.usePardonMutation).mockReturnValue({
    isPending: false,
    isError: false,
    error: null,
    isSuccess: false,
    mutate: vi.fn(),
  } as unknown as ReturnType<typeof usePardonMutation>);

  vi.mocked(justiceQueries.useSubmitEvidenceMutation).mockReturnValue({
    isPending: false,
    isError: false,
    error: null,
    isSuccess: false,
    mutate: vi.fn(),
  } as unknown as ReturnType<typeof useSubmitEvidenceMutation>);
}

describe('WantedBoard standing sentences', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders nothing when wanted, held, and records are all empty', () => {
    setupMocks(emptyBoard);
    const { container } = renderWithProviders(<WantedBoard areaId={1} viewerEntryId={null} />);

    expect(container).toBeEmptyDOMElement();
  });

  it('renders the standing-sentences section even with no wanted/held rows', () => {
    setupMocks({
      ...emptyBoard,
      records: [{ kind: 'exile', persona_name: 'Velenosa', until: '2026-09-25T00:00:00Z' }],
    });
    renderWithProviders(<WantedBoard areaId={1} viewerEntryId={null} />);

    expect(screen.getByTestId('standing-sentences')).toBeInTheDocument();
    const row = screen.getByTestId('standing-sentence-row');
    expect(row).toHaveTextContent('Exile');
    expect(row).toHaveTextContent('Velenosa');
  });

  it('renders a null until as "permanently"', () => {
    setupMocks({
      ...emptyBoard,
      records: [{ kind: 'banishment', persona_name: 'Ariel', until: null }],
    });
    renderWithProviders(<WantedBoard areaId={1} viewerEntryId={null} />);

    expect(screen.getByTestId('standing-sentence-row')).toHaveTextContent('permanently');
  });

  it('lists every record row, kind + name + until', () => {
    setupMocks({
      ...emptyBoard,
      records: [
        { kind: 'humiliation', persona_name: 'Thorne', until: '2026-09-02T00:00:00Z' },
        { kind: 'execution', persona_name: 'Marek', until: '2026-08-31T00:00:00Z' },
      ],
    });
    renderWithProviders(<WantedBoard areaId={1} viewerEntryId={null} />);

    const rows = screen.getAllByTestId('standing-sentence-row');
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent('Public Humiliation');
    expect(rows[0]).toHaveTextContent('Thorne');
    expect(rows[1]).toHaveTextContent('Execution');
    expect(rows[1]).toHaveTextContent('Marek');
  });
});
