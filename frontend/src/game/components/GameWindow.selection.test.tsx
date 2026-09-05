/**
 * Tests GameWindow's puppet-tab switch handler after #3479 decision 4:
 * clicking a session tab in the multi-puppet tab bar activates that session
 * (as before) and now ALSO writes this tab's browsing identity
 * (sessionStorage + the gameSlice mirror), but it must NEVER fire the
 * durable server-side selection mutation: only the Hall picker writes the
 * account default (see CharactersBand.test.tsx, which asserts the mutation
 * still fires there). `@/roster/queries` stays mocked precisely so a
 * reintroduced `useSelectCharacterMutation` call is caught. Heavy children
 * (composer, feeds) are stubbed: this file exercises only the switch wiring.
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
import { resetGame, startSession } from '@/store/gameSlice';
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

  it('switches the active session and writes the tab identity, never the account default', () => {
    renderGameWindow();

    fireEvent.click(screen.getByText('Bianca'));

    expect(mutateMock).not.toHaveBeenCalled();
    expect(store.getState().game.active).toBe('Bianca');
    expect(store.getState().game.browsingEntryId).toBe(2);
    expect(readTabIdentity()?.entryId).toBe(2);
  });

  it('connects the switched-to session when it is not connected yet', () => {
    renderGameWindow();

    fireEvent.click(screen.getByText('Bianca'));

    expect(connectMock).toHaveBeenCalledWith('Bianca');
  });
});
