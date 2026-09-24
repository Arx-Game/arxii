/**
 * Tests GameTopBar's character-select handler after #3479 decision 4 as
 * reconciled with #3812 (ADR-0294): clicking an avatar (alt, unplayed, or the
 * currently-active one) performs the puppeting/session dispatches as before
 * and ALWAYS writes this tab's browsing identity (sessionStorage + the
 * gameSlice mirror). The durable server-side selection mutation fires only
 * when the click opens a socket, and BEFORE the connect (login puppets the
 * server's selection, so the connect assertions wait for the awaited
 * mutation to settle); moving focus between two already-connected sessions
 * never fires it. `useGameSocket` and `useSelectCharacterMutation` are mocked
 * so this stays a fast unit test (real `connect()` opens a WebSocket and
 * hits the network) and so a stray mutation call is caught.
 */
import { fireEvent, screen, waitFor } from '@testing-library/react';
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
  useSelectCharacterMutation: () => ({
    mutate: mutateMock,
    mutateAsync: vi.fn(async (entryId: number) => {
      mutateMock(entryId);
    }),
  }),
}));

import { GameTopBar } from './GameTopBar';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { store } from '@/store/store';
import {
  resetGame,
  startSession,
  hydrateActiveCharacter,
  setSessionConnectionStatus,
} from '@/store/gameSlice';
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
  unread_direct: 0,
  has_ambient_unread: false,
  attention_as_of_id: 0,
  lifecycle_state: 'ALIVE',
  roster_type: 'Active',
  character_type: 'PC',
  activity_state: 'ACTIVE',
  activity_requirement: 'NONE',
  creation_provenance: 'player',
  thaw_available_at: null,
};

const bianca: MyRosterEntry = {
  id: 2,
  name: 'Bianca',
  character_id: 43,
  profile_picture_url: null,
  primary_persona_id: 8,
  active_persona_id: 8,
  unread_narrative_count: 0,
  unread_direct: 0,
  has_ambient_unread: false,
  attention_as_of_id: 0,
  lifecycle_state: 'ALIVE',
  roster_type: 'Active',
  character_type: 'PC',
  activity_state: 'ACTIVE',
  activity_requirement: 'NONE',
  creation_provenance: 'player',
  thaw_available_at: null,
};

describe('GameTopBar selection wiring (#3479 decision 4)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    store.dispatch(resetGame());
    sessionStorage.clear();
  });

  it('clicking an unplayed character selects, then connects, and writes the tab identity', async () => {
    renderWithProviders(<GameTopBar characters={[aria]} />);

    fireEvent.click(screen.getByText('Aria'));

    expect(mutateMock).toHaveBeenCalledWith(1);
    await waitFor(() => expect(connectMock).toHaveBeenCalledWith('Aria'));
    expect(store.getState().game.active).toBe('Aria');
    expect(store.getState().game.browsingEntryId).toBe(1);
    expect(readTabIdentity()?.entryId).toBe(1);
  });

  it('clicking a connected alt switches the tab identity without the mutation or a connect', () => {
    store.dispatch(startSession('Bianca'));
    store.dispatch(setSessionConnectionStatus({ character: 'Bianca', status: true }));
    store.dispatch(startSession('Aria'));

    renderWithProviders(<GameTopBar characters={[aria, bianca]} />);

    fireEvent.click(screen.getByTitle('Switch to Bianca'));

    expect(mutateMock).not.toHaveBeenCalled();
    expect(connectMock).not.toHaveBeenCalled();
    expect(store.getState().game.active).toBe('Bianca');
    expect(store.getState().game.browsingEntryId).toBe(2);
    expect(readTabIdentity()?.entryId).toBe(2);
  });

  it('the hydrated-but-disconnected active avatar is clickable and (re)selects/connects', async () => {
    // Simulates reload hydration: `active` set with no live session yet.
    store.dispatch(hydrateActiveCharacter({ name: 'Aria', entryId: 1 }));

    renderWithProviders(<GameTopBar characters={[aria]} />);

    fireEvent.click(screen.getByTitle('Connect as Aria'));

    expect(mutateMock).toHaveBeenCalledWith(1);
    await waitFor(() => expect(connectMock).toHaveBeenCalledWith('Aria'));
    expect(store.getState().game.browsingEntryId).toBe(1);
    expect(readTabIdentity()?.entryId).toBe(1);
  });
});
