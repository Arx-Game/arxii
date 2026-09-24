/**
 * Tests GameWindow's puppet-tab switch handler after #3479 decision 4 as
 * reconciled with #3812 (ADR-0294): clicking a session tab in the
 * multi-puppet tab bar activates that session (as before) and ALWAYS writes
 * this tab's browsing identity (sessionStorage + the gameSlice mirror). The
 * durable server-side selection mutation fires only when the switch opens a
 * socket, and before the connect; a switch to an already-connected session
 * never fires it. `@/roster/queries` is mocked so a stray mutation call is
 * caught. Heavy children (composer, feeds) are stubbed: this file exercises
 * only the switch wiring.
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
    requestRoomState: vi.fn(),
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

vi.mock('./CommandInput', () => ({
  CommandInput: () => null,
}));
vi.mock('./ChatWindow', () => ({
  ChatWindow: () => null,
}));
vi.mock('@/scenes/components/SceneMessages', () => ({
  SceneMessages: () => null,
}));

import { GameWindow } from './GameWindow';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { store } from '@/store/store';
import { resetGame, startSession, setSessionConnectionStatus } from '@/store/gameSlice';
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

function renderGameWindow() {
  return renderWithProviders(
    <GameWindow characters={[aria, bianca]} onModeChange={vi.fn()} personaId={null} />
  );
}

describe('GameWindow puppet-tab switch wiring (#3479 decision 4)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Bianca first, Aria second: startSession makes the most recent active,
    // so Aria is active and Bianca is the background tab to switch to.
    store.dispatch(startSession('Bianca'));
    store.dispatch(startSession('Aria'));
  });

  afterEach(() => {
    store.dispatch(resetGame());
    sessionStorage.clear();
  });

  it('switches to a connected session and writes the tab identity, never the account default', () => {
    store.dispatch(setSessionConnectionStatus({ character: 'Bianca', status: true }));
    renderGameWindow();

    fireEvent.click(screen.getByText('Bianca'));

    expect(mutateMock).not.toHaveBeenCalled();
    expect(connectMock).not.toHaveBeenCalled();
    expect(store.getState().game.active).toBe('Bianca');
    expect(store.getState().game.browsingEntryId).toBe(2);
    expect(readTabIdentity()?.entryId).toBe(2);
  });

  it('selects, then connects, a switched-to session that is not connected yet', async () => {
    renderGameWindow();

    fireEvent.click(screen.getByText('Bianca'));

    expect(mutateMock).toHaveBeenCalledWith(2);
    await waitFor(() => expect(connectMock).toHaveBeenCalledWith('Bianca'));
    expect(store.getState().game.browsingEntryId).toBe(2);
    expect(readTabIdentity()?.entryId).toBe(2);
  });
});
