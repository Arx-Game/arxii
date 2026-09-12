/**
 * Switching characters selects BEFORE it connects (#3812).
 *
 * Login now puppets the server's durable selection the moment a socket
 * authenticates, so the select POST has to land before the socket opens or
 * the new socket briefly puppets the previous character until its own `@ic`
 * corrects it. The local session switch stays immediate; only the connect
 * waits. A failed select never blocks: the socket still opens and its
 * `@ic <name>` still carries the intent.
 */
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest';

import { GameTopBar } from './GameTopBar';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { store } from '@/store/store';
import {
  resetGame,
  setActiveSession,
  setSessionConnectionStatus,
  startSession,
} from '@/store/gameSlice';
import type { MyRosterEntry } from '@/roster/types';

const calls: string[] = [];
const mockMutateAsync = vi.fn(async (entryId: number) => {
  calls.push(`select:${entryId}`);
});
const mockConnect = vi.fn(async (name: string) => {
  calls.push(`connect:${name}`);
});

vi.mock('@/roster/queries', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/roster/queries')>()),
  useSelectCharacterMutation: () => ({ mutateAsync: mockMutateAsync, mutate: vi.fn() }),
}));

vi.mock('@/hooks/useGameSocket', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/hooks/useGameSocket')>()),
  useGameSocket: () => ({
    connect: mockConnect,
    send: vi.fn(),
    executeAction: vi.fn(),
    disconnectAll: vi.fn(),
  }),
}));

vi.mock('@/home/hall/queries', () => ({
  useClockQuery: () => ({ data: undefined }),
}));

function entry(id: number, name: string): MyRosterEntry {
  return {
    id,
    name,
    character_id: 40 + id,
    profile_picture_url: null,
    primary_persona_id: id,
    active_persona_id: id,
    unread_narrative_count: 0,
    unread_direct: 0,
    has_ambient_unread: false,
    attention_as_of_id: 0,
    lifecycle_state: 'ALIVE',
    roster_type: 'Active',
    character_type: 'PC',
  };
}

const aria = entry(1, 'Aria');
const bianca = entry(2, 'Bianca');

describe('GameTopBar character switch ordering (#3812)', () => {
  beforeEach(() => {
    calls.length = 0;
    store.dispatch(startSession('Aria'));
    store.dispatch(setActiveSession('Aria'));
  });

  afterEach(() => {
    store.dispatch(resetGame());
    vi.clearAllMocks();
  });

  it('persists the selection first, then opens the socket', async () => {
    renderWithProviders(<GameTopBar characters={[aria, bianca]} />);

    await userEvent.click(screen.getByTitle('Connect as Bianca'));

    expect(mockMutateAsync).toHaveBeenCalledWith(2);
    expect(mockConnect).toHaveBeenCalledWith('Bianca');
    expect(calls).toEqual(['select:2', 'connect:Bianca']);
    expect(store.getState().game.active).toBe('Bianca');
  });

  it('still connects when the select POST fails', async () => {
    mockMutateAsync.mockRejectedValueOnce(new Error('offline'));
    renderWithProviders(<GameTopBar characters={[aria, bianca]} />);

    await userEvent.click(screen.getByTitle('Connect as Bianca'));

    expect(mockConnect).toHaveBeenCalledWith('Bianca');
  });

  it('does not reconnect a session that is already connected', async () => {
    store.dispatch(startSession('Bianca'));
    store.dispatch(setSessionConnectionStatus({ character: 'Bianca', status: true }));
    store.dispatch(setActiveSession('Aria')); // startSession may have made Bianca active
    renderWithProviders(<GameTopBar characters={[aria, bianca]} />);

    await userEvent.click(screen.getByTitle('Switch to Bianca'));

    expect(mockMutateAsync).toHaveBeenCalledWith(2);
    expect(mockConnect).not.toHaveBeenCalled();
    expect(store.getState().game.active).toBe('Bianca');
  });
});
