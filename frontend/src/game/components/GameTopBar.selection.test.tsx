/**
 * Tests GameTopBar's character-select handler after #3479 decision 4
 * (superseding the #3412 wiring this file used to pin down): clicking an
 * avatar (alt, unplayed, or the currently-active one) is tab-local. It still
 * performs the puppeting/session dispatches, and now ALSO writes this tab's
 * browsing identity (sessionStorage + the gameSlice mirror), but it must
 * NEVER fire the durable server-side selection mutation: only the Hall
 * picker writes the account default (see CharactersBand.test.tsx, which
 * asserts the mutation still fires there). `@/roster/queries` stays mocked
 * precisely so a reintroduced `useSelectCharacterMutation` call is caught.
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
import { readTabIdentity } from '@/store/browsingIdentity';
import type { MyRosterEntry } from '@/roster/types';

const aria: MyRosterEntry = {
  id: 1,
  name: 'Aria',
  character_id: 42,
  profile_picture_url: null,
  primary_persona_id: 7,
  active_persona_id: 7,
  unread_narrative_count: 0,
  lifecycle_state: 'ALIVE',
  roster_type: 'Active',
  character_type: 'PC',
};

const bianca: MyRosterEntry = {
  id: 2,
  name: 'Bianca',
  character_id: 43,
  profile_picture_url: null,
  primary_persona_id: 8,
  active_persona_id: 8,
  unread_narrative_count: 0,
  lifecycle_state: 'ALIVE',
  roster_type: 'Active',
  character_type: 'PC',
};

describe('GameTopBar selection wiring (#3479 decision 4)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    store.dispatch(resetGame());
    sessionStorage.clear();
  });

  it('clicking an unplayed character connects and writes the tab identity, never the account default', () => {
    renderWithProviders(<GameTopBar characters={[aria]} />);

    fireEvent.click(screen.getByText('Aria'));

    expect(mutateMock).not.toHaveBeenCalled();
    expect(connectMock).toHaveBeenCalledWith('Aria');
    expect(store.getState().game.active).toBe('Aria');
    expect(store.getState().game.browsingEntryId).toBe(1);
    expect(readTabIdentity()?.entryId).toBe(1);
  });

  it('clicking an alt (already-sessioned) character switches the tab identity without the mutation', () => {
    store.dispatch(startSession('Bianca'));
    store.dispatch(startSession('Aria'));

    renderWithProviders(<GameTopBar characters={[aria, bianca]} />);

    fireEvent.click(screen.getByTitle('Switch to Bianca'));

    expect(mutateMock).not.toHaveBeenCalled();
    expect(store.getState().game.active).toBe('Bianca');
    expect(store.getState().game.browsingEntryId).toBe(2);
    expect(readTabIdentity()?.entryId).toBe(2);
  });

  it('the hydrated-but-disconnected active avatar is clickable and (re)connects without the mutation', () => {
    // Simulates reload hydration: `active` set with no live session yet.
    store.dispatch(hydrateActiveCharacter({ name: 'Aria', entryId: 1 }));

    renderWithProviders(<GameTopBar characters={[aria]} />);

    fireEvent.click(screen.getByTitle('Connect as Aria'));

    expect(mutateMock).not.toHaveBeenCalled();
    expect(connectMock).toHaveBeenCalledWith('Aria');
    expect(store.getState().game.browsingEntryId).toBe(1);
    expect(readTabIdentity()?.entryId).toBe(1);
  });
});
