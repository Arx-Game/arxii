/**
 * The world menu is a menu (#3818). It used to be a `<Link to="/">`, and `/`
 * redirects an in-world player straight back to `/game`, so it flickered and
 * did nothing — and there was no way to reach character select while staying
 * connected. Sessions and sockets live in Redux/module scope, so navigating
 * away keeps every character tab open.
 */
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, afterEach, vi } from 'vitest';

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

const logoutMutate = vi.fn();
vi.mock('@/evennia_replacements/queries', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/evennia_replacements/queries')>()),
  useLogout: () => ({ mutate: logoutMutate }),
}));

const everywhereMock = vi.fn();
vi.mock('@/roster/queries', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/roster/queries')>()),
  useDisconnectEverywhereMutation: () => ({ mutate: everywhereMock, isPending: false }),
}));

const disconnectMock = vi.fn();
vi.mock('@/hooks/useGameSocket', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/hooks/useGameSocket')>()),
  useGameSocket: () => ({
    connect: vi.fn(),
    disconnect: disconnectMock,
    send: vi.fn(),
    executeAction: vi.fn(),
    disconnectAll: vi.fn(),
  }),
}));

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
  session_count: 0,
  room_name: null,
};

vi.mock('@/home/hall/queries', () => ({
  useClockQuery: () => ({ data: undefined }),
}));

describe('GameTopBar world menu (#3818)', () => {
  afterEach(() => {
    store.dispatch(resetGame());
    vi.clearAllMocks();
  });

  it('opens a menu with character select, roster, settings and Log Out Account', async () => {
    const user = userEvent.setup();
    renderWithProviders(<GameTopBar characters={[]} />);

    await user.click(screen.getByRole('button', { name: 'Open world menu' }));

    expect(screen.getByRole('menuitem', { name: 'Your characters' })).toHaveAttribute(
      'href',
      '/hall'
    );
    expect(screen.getByRole('menuitem', { name: 'Roster' })).toHaveAttribute('href', '/roster');
    expect(screen.getByRole('menuitem', { name: 'Settings' })).toHaveAttribute(
      'href',
      '/profile/settings'
    );
    expect(screen.getByRole('menuitem', { name: 'Log Out Account' })).toBeInTheDocument();
  });

  it('logs out through the shared logout mutation', async () => {
    const user = userEvent.setup();
    renderWithProviders(<GameTopBar characters={[]} />);

    await user.click(screen.getByRole('button', { name: 'Open world menu' }));
    await user.click(screen.getByRole('menuitem', { name: 'Log Out Account' }));

    expect(logoutMutate).toHaveBeenCalledTimes(1);
  });

  it('offers Disconnect Character for the active character, and only then', async () => {
    const user = userEvent.setup();
    renderWithProviders(<GameTopBar characters={[aria]} />);
    await user.click(screen.getByRole('button', { name: 'Open world menu' }));
    expect(screen.queryByRole('menuitem', { name: /disconnect character/i })).toBeNull();
    expect(screen.queryByRole('menuitem', { name: /leave the world/i })).toBeNull();
    await user.keyboard('{Escape}');

    store.dispatch(startSession('Aria'));
    store.dispatch(setActiveSession('Aria'));
    await user.click(screen.getByRole('button', { name: 'Open world menu' }));
    await user.click(screen.getByRole('menuitem', { name: 'Disconnect Character' }));

    // One session: no choice to make, this tab's socket closes (#4321).
    expect(disconnectMock).toHaveBeenCalledWith('Aria');
    expect(everywhereMock).not.toHaveBeenCalled();
  });

  // #4321: the choice appears only while this tab holds a socket AND the
  // server says the character has another session somewhere.
  it('offers This connection or Every connection only with a second session', async () => {
    const user = userEvent.setup();
    store.dispatch(startSession('Aria'));
    store.dispatch(setActiveSession('Aria'));
    store.dispatch(setSessionConnectionStatus({ character: 'Aria', status: true }));
    renderWithProviders(<GameTopBar characters={[{ ...aria, session_count: 2 }]} />);

    await user.click(screen.getByRole('button', { name: 'Open world menu' }));
    // The sub-menu by keyboard: ArrowRight opens it on its first item, ArrowDown
    // moves to the second, Enter selects (a pointer leaving the trigger would
    // close it again under jsdom's pointer geometry).
    screen.getByRole('menuitem', { name: 'Disconnect Character' }).focus();
    await user.keyboard('{ArrowRight}');
    expect(await screen.findByRole('menuitem', { name: 'This connection' })).toBeInTheDocument();
    await user.keyboard('{ArrowDown}{Enter}');

    expect(everywhereMock).toHaveBeenCalledWith(1);
    expect(disconnectMock).not.toHaveBeenCalled();
  });

  it('is a button, not a link to the redirecting front page', () => {
    renderWithProviders(<GameTopBar characters={[]} />);

    expect(screen.queryByRole('link', { name: 'Open world menu' })).toBeNull();
  });
});
