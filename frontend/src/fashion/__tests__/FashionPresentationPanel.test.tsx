/**
 * FashionPresentationPanel tests (#514).
 *
 * Covers: list renders presenters + acclaim; the present button fires the
 * present mutation; the Judge button is hidden for the viewer's own row;
 * an API error message is surfaced inline.
 */
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

import type { FashionPresentation } from '../types';

const useEventPresentationsQueryMock = vi.fn();
const presentMutate = vi.fn();
const judgeMutate = vi.fn();
const usePresentOutfitMutationMock = vi.fn();
const useJudgePresentationMutationMock = vi.fn();

vi.mock('../queries', () => ({
  useEventPresentationsQuery: (...a: unknown[]) => useEventPresentationsQueryMock(...a),
  usePresentOutfitMutation: (...a: unknown[]) => usePresentOutfitMutationMock(...a),
  useJudgePresentationMutation: (...a: unknown[]) => useJudgePresentationMutationMock(...a),
}));

vi.mock('@/store/hooks', () => ({
  useAppSelector: () => 'Alice', // active character name
}));

vi.mock('@/roster/queries', () => ({
  useMyRosterEntriesQuery: () => ({
    data: [{ id: 1, name: 'Alice', character_id: 3, profile_picture_url: null, primary_persona_id: null }],
  }),
}));

vi.mock('@/inventory/hooks/useOutfits', () => ({
  useOutfits: () => ({ data: [] }),
}));

import { FashionPresentationPanel } from '../FashionPresentationPanel';

const PRESENTATIONS: FashionPresentation[] = [
  {
    id: 10,
    event: 9,
    presenter: 3, // Alice — the viewer
    outfit: null,
    perceiving_society: 1,
    base_score: 5,
    acclaim: 8,
    created_at: '2026-06-14T00:00:00Z',
  },
  {
    id: 11,
    event: 9,
    presenter: 4, // someone else
    outfit: null,
    perceiving_society: 1,
    base_score: 3,
    acclaim: 15,
    created_at: '2026-06-14T00:00:00Z',
  },
];

function mutationStub(overrides: Record<string, unknown> = {}) {
  return { mutate: vi.fn(), isPending: false, error: null, ...overrides };
}

describe('FashionPresentationPanel', () => {
  beforeEach(() => {
    useEventPresentationsQueryMock.mockReset();
    usePresentOutfitMutationMock.mockReset();
    useJudgePresentationMutationMock.mockReset();
    presentMutate.mockReset();
    judgeMutate.mockReset();
    usePresentOutfitMutationMock.mockReturnValue(mutationStub({ mutate: presentMutate }));
    useJudgePresentationMutationMock.mockReturnValue(mutationStub({ mutate: judgeMutate }));
  });

  it('renders presenters + acclaim', () => {
    useEventPresentationsQueryMock.mockReturnValue({ data: PRESENTATIONS, isLoading: false });
    render(<FashionPresentationPanel eventId={9} />);
    const rows = screen.getByTestId('fashion-rows');
    expect(rows).toHaveTextContent('Alice');
    expect(rows).toHaveTextContent('Acclaim: 8');
    expect(rows).toHaveTextContent('Presenter #4');
    expect(rows).toHaveTextContent('Acclaim: 15');
  });

  it('hides the Judge button on the viewer own row but shows it for others', () => {
    useEventPresentationsQueryMock.mockReturnValue({ data: PRESENTATIONS, isLoading: false });
    render(<FashionPresentationPanel eventId={9} />);
    // Only one Judge button — for presenter #4, not the viewer's own row.
    const judgeButtons = screen.getAllByRole('button', { name: 'Judge' });
    expect(judgeButtons).toHaveLength(1);
    fireEvent.click(judgeButtons[0]);
    expect(judgeMutate).toHaveBeenCalledWith({ presentation: 11 });
  });

  it('disables Present once the viewer has already presented', () => {
    useEventPresentationsQueryMock.mockReturnValue({ data: PRESENTATIONS, isLoading: false });
    render(<FashionPresentationPanel eventId={9} />);
    const presentBtn = screen.getByRole('button', { name: 'Already presented' });
    expect(presentBtn).toBeDisabled();
  });

  it('fires the present mutation when the viewer has not yet presented', () => {
    useEventPresentationsQueryMock.mockReturnValue({
      data: [PRESENTATIONS[1]], // only the other presenter
      isLoading: false,
    });
    render(<FashionPresentationPanel eventId={9} />);
    fireEvent.click(screen.getByRole('button', { name: 'Present my look' }));
    expect(presentMutate).toHaveBeenCalledWith({ event: 9 });
  });

  it('surfaces an API error message', () => {
    useEventPresentationsQueryMock.mockReturnValue({ data: PRESENTATIONS, isLoading: false });
    useJudgePresentationMutationMock.mockReturnValue(
      mutationStub({ mutate: judgeMutate, error: new Error('You cannot judge your own presentation.') })
    );
    render(<FashionPresentationPanel eventId={9} />);
    expect(screen.getByTestId('fashion-error')).toHaveTextContent(
      'You cannot judge your own presentation.'
    );
  });
});
