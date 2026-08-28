/**
 * Tests the #3412 wiring in GameTopBar's character-select handler: clicking
 * an avatar (alt, unplayed, or the currently-active one) fires the durable
 * server-side selection mutation ALONGSIDE the existing puppeting/session
 * dispatches — never replacing them. `useGameSocket` and
 * `useSelectCharacterMutation` are mocked so this stays a fast unit test
 * (real `connect()` opens a WebSocket and hits the network).
 */
import { fireEvent, screen } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

const connectMock = vi.fn();
vi.mock('@/hooks/useGameSocket', () => ({
  useGameSocket: () => ({
    connect: connectMock,
    send: vi.fn(),
    disconnectAll: vi.fn(),
    executeAction: vi.fn(),
  }),
}));

const mutateMock = vi.fn();
vi.mock('@/roster/queries', () => ({
  useSelectCharacterMutation: () => ({ mutate: mutateMock }),
}));

import { GameTopBar } from './GameTopBar';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { store } from '@/store/store';
import { resetGame, startSession, hydrateActiveCharacter } from '@/store/gameSlice';
import type { MyRosterEntry } from '@/roster/types';

const aria: MyRosterEntry = {
  id: 1,
  name: 'Aria',
  character_id: 42,
  profile_picture_url: null,
  primary_persona_id: 7,
  active_persona_id: 7,
  unread_narrative_count: 0,
};

const bianca: MyRosterEntry = {
  id: 2,
  name: 'Bianca',
  character_id: 43,
  profile_picture_url: null,
  primary_persona_id: 8,
  active_persona_id: 8,
  unread_narrative_count: 0,
};

describe('GameTopBar selection wiring (#3412)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    store.dispatch(resetGame());
  });

  it('fires the select mutation with the roster entry id when clicking an unplayed character', () => {
    renderWithProviders(<GameTopBar characters={[aria]} />);

    fireEvent.click(screen.getByText('Aria'));

    expect(mutateMock).toHaveBeenCalledWith(1);
    expect(connectMock).toHaveBeenCalledWith('Aria');
    expect(store.getState().game.active).toBe('Aria');
  });

  it('fires the select mutation when clicking an alt (already-sessioned) character', () => {
    store.dispatch(startSession('Bianca'));
    store.dispatch(startSession('Aria'));

    renderWithProviders(<GameTopBar characters={[aria, bianca]} />);

    fireEvent.click(screen.getByTitle('Switch to Bianca'));

    expect(mutateMock).toHaveBeenCalledWith(2);
    expect(store.getState().game.active).toBe('Bianca');
  });

  it('the hydrated-but-disconnected active avatar is clickable and (re)selects/connects', () => {
    // Simulates reload hydration: `active` set with no live session yet.
    store.dispatch(hydrateActiveCharacter({ name: 'Aria', entryId: 1 }));

    renderWithProviders(<GameTopBar characters={[aria]} />);

    fireEvent.click(screen.getByTitle('Connect as Aria'));

    expect(mutateMock).toHaveBeenCalledWith(1);
    expect(connectMock).toHaveBeenCalledWith('Aria');
  });
});
