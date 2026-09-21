/**
 * The tie page (#3957) — one side of a tie, shaped by the audience the server sent.
 *
 * The page never decides what a viewer may know. It reads the nulls: no `depth` means
 * no Depth readout anywhere on the page, and an audience that is not the owner means
 * no AP field, no label doors and no tier claim. A tie the viewer may not see arrives
 * as a 404 and renders as not found, never as a refusal.
 */
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { TieNotFoundError } from '../../api';
import { TiePage } from '../TiePage';
import { makeLabel, makeTie, STREAM, TYPES } from '../../components/__tests__/fixtures';

const useTie = vi.fn();
const useTieStream = vi.fn();

vi.mock('@/relationships/queries', () => ({
  useTie: (id: number | null) => useTie(id),
  useTieStream: (id: number | null) => useTieStream(id),
  useRelationshipTypes: () => ({ data: TYPES, isLoading: false }),
  useDeclareLabel: () => ({ mutate: vi.fn(), isPending: false }),
  useShiftLabel: () => ({ mutate: vi.fn(), isPending: false }),
  useEndLabel: () => ({ mutate: vi.fn(), isPending: false }),
  useAdvanceAwareness: () => ({ mutate: vi.fn(), isPending: false }),
  useSetTieAllocation: () => ({ mutate: vi.fn(), isPending: false }),
  useAdvanceTier: () => ({ mutate: vi.fn(), isPending: false }),
  useSetTieSummary: () => ({ mutate: vi.fn(), isPending: false }),
  useTargetPersonaId: () => ({ data: 91 }),
}));

vi.mock('@/roster/queries', () => ({
  useRosterEntryQuery: () => ({
    data: { id: 9, character: { id: 5, name: 'Ilsavet du Verane' }, fullname: 'Ilsavet du Verane' },
    isLoading: false,
  }),
}));

vi.mock('@/journals/queries', () => ({
  useJournalEntries: () => ({ data: { results: [] } }),
}));

vi.mock('@/roster/usePersonaSearch', () => ({
  usePersonaSearch: () => ({ results: [], isFetching: false }),
}));

function renderPage(tieId = '77') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[`/characters/9/ties/${tieId}`]}>
        <Routes>
          <Route path="/characters/:id/ties/:tieId" element={<TiePage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  useTie.mockReturnValue({ data: makeTie(), isLoading: false, error: null });
  useTieStream.mockReturnValue({ data: STREAM, isLoading: false, error: null });
});

describe('TiePage', () => {
  it('names the other side, with the viewed character above it', () => {
    renderPage();
    expect(screen.getByRole('heading', { name: 'Corvin Ashe' })).toBeInTheDocument();
    expect(screen.getByText('Ilsavet du Verane and')).toBeInTheDocument();
  });

  it('prints the depth against the next threshold, and the tier under it', () => {
    renderPage();
    expect(screen.getByRole('button', { name: /340/ })).toHaveAttribute('aria-expanded', 'false');
    expect(screen.getByText('Tier 2')).toBeInTheDocument();
  });

  it('carries the labels and the summary', () => {
    renderPage();
    expect(screen.getByText('Lover · Clandestine')).toBeInTheDocument();
    expect(screen.getByText('Enemy · Private')).toBeInTheDocument();
    expect(screen.getByText('He was waiting at the north gate.')).toBeInTheDocument();
  });

  it('says there is no thread rather than leaving the line off', () => {
    renderPage();
    expect(screen.getByText('Thread: none yet.')).toBeInTheDocument();
  });

  it('gives the owner the write blocks', () => {
    renderPage();
    expect(screen.getByLabelText('AP this week')).toBeInTheDocument();
    expect(screen.getByText('Advance Relationship Tier')).toBeInTheDocument();
    expect(screen.getByText('Cost: 10xp * tier level.')).toBeInTheDocument();
  });

  it('gives a third party no numbers, no AP and no doors', () => {
    useTie.mockReturnValue({
      data: makeTie({
        audience: 'third_party',
        labels: [makeLabel({ id: 1, awareness: 'public', type_name: 'Rival' })],
        depth: null,
        next_tier_threshold: null,
        breakdown: null,
        thread: null,
        ap_this_week: null,
      }),
      isLoading: false,
      error: null,
    });
    renderPage();
    expect(screen.getByRole('heading', { name: 'Corvin Ashe' })).toBeInTheDocument();
    expect(screen.getByText('Rival')).toBeInTheDocument();
    expect(screen.queryByText('Depth')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('AP this week')).not.toBeInTheDocument();
    expect(screen.queryByText('Advance Relationship Tier')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Declare another' })).not.toBeInTheDocument();
    expect(screen.queryByText('Ilsavet du Verane and')).not.toBeInTheDocument();
  });

  it('renders a tie it may not see as not found', () => {
    useTie.mockReturnValue({ data: undefined, isLoading: false, error: new TieNotFoundError() });
    renderPage();
    expect(screen.getByText('Tie not found.')).toBeInTheDocument();
  });

  it('offers only the picker when declaring a new tie', () => {
    renderPage('new');
    expect(useTie).toHaveBeenCalledWith(null);
    expect(screen.getByLabelText('About a character')).toBeInTheDocument();
    expect(screen.queryByLabelText('AP this week')).not.toBeInTheDocument();
  });
});
