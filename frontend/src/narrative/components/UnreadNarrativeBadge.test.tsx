/**
 * UnreadNarrativeBadge tests (#3412 hygiene fold-in) — the badge now routes to the
 * SELECTED character's sheet (gameSlice.active) rather than always the first roster
 * entry, and no longer appends the dead `#messages` fragment.
 */

import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { Provider } from 'react-redux';
import { configureStore } from '@reduxjs/toolkit';
import { UnreadNarrativeBadge } from './UnreadNarrativeBadge';
import { gameSlice } from '@/store/gameSlice';
import type { MyRosterEntry } from '@/roster/types';

const mockUnreadCount = vi.fn(() => 0);
vi.mock('@/narrative/queries', () => ({
  useUnreadNarrativeCount: () => mockUnreadCount(),
}));

const mockRosterEntries = vi.fn(() => ({ data: [] as MyRosterEntry[] }));
vi.mock('@/roster/queries', () => ({
  useMyRosterEntriesQuery: () => mockRosterEntries(),
}));

function makeStore(active: string | null = null) {
  const store = configureStore({ reducer: { game: gameSlice.reducer } });
  if (active) {
    store.dispatch(gameSlice.actions.hydrateActiveCharacter({ name: active, entryId: 1 }));
  }
  return store;
}

function renderBadge(store: ReturnType<typeof makeStore>) {
  return render(
    <Provider store={store}>
      <MemoryRouter>
        <UnreadNarrativeBadge />
      </MemoryRouter>
    </Provider>
  );
}

const entries = [
  { id: 1, name: 'FirstChar' },
  { id: 2, name: 'SecondChar' },
] as MyRosterEntry[];

describe('UnreadNarrativeBadge', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockRosterEntries.mockReturnValue({ data: entries });
  });

  it('renders nothing when the unread count is zero', () => {
    mockUnreadCount.mockReturnValue(0);
    renderBadge(makeStore());
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
  });

  it('routes to the SELECTED character, not the first roster entry', () => {
    mockUnreadCount.mockReturnValue(3);
    renderBadge(makeStore('SecondChar'));
    const link = screen.getByRole('link');
    expect(link).toHaveAttribute('href', '/characters/2');
  });

  it('drops the dead #messages fragment', () => {
    mockUnreadCount.mockReturnValue(1);
    renderBadge(makeStore('FirstChar'));
    const link = screen.getByRole('link');
    expect(link).toHaveAttribute('href', '/characters/1');
  });

  it('falls back to the first owned character when nothing is selected', () => {
    mockUnreadCount.mockReturnValue(2);
    renderBadge(makeStore(null));
    const link = screen.getByRole('link');
    expect(link).toHaveAttribute('href', '/characters/1');
  });

  it('falls back to the roster when the account owns no characters', () => {
    mockUnreadCount.mockReturnValue(2);
    mockRosterEntries.mockReturnValue({ data: [] });
    renderBadge(makeStore(null));
    const link = screen.getByRole('link');
    expect(link).toHaveAttribute('href', '/roster');
  });
});
