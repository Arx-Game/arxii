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
import { resetGame, setActiveSession, startSession } from '@/store/gameSlice';
import type { MyRosterEntry } from '@/roster/types';

const logoutMutate = vi.fn();
vi.mock('@/evennia_replacements/queries', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/evennia_replacements/queries')>()),
  useLogout: () => ({ mutate: logoutMutate }),
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
  creation_provenance: 'PLAYER',
  thaw_available_at: null,
};

vi.mock('@/home/hall/queries', () => ({
  useClockQuery: () => ({ data: undefined }),
}));

describe('GameTopBar world menu (#3818)', () => {
  afterEach(() => {
    store.dispatch(resetGame());
    vi.clearAllMocks();
  });

  it('opens a menu with character select, roster, settings and log out', async () => {
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
    expect(screen.getByRole('menuitem', { name: 'Log out' })).toBeInTheDocument();
  });

  it('logs out through the shared logout mutation', async () => {
    const user = userEvent.setup();
    renderWithProviders(<GameTopBar characters={[]} />);

    await user.click(screen.getByRole('button', { name: 'Open world menu' }));
    await user.click(screen.getByRole('menuitem', { name: 'Log out' }));

    expect(logoutMutate).toHaveBeenCalledTimes(1);
  });

  it('offers to leave the world as the active character, and only then', async () => {
    const user = userEvent.setup();
    renderWithProviders(<GameTopBar characters={[aria]} />);
    await user.click(screen.getByRole('button', { name: 'Open world menu' }));
    expect(screen.queryByRole('menuitem', { name: /leave the world/i })).toBeNull();
    await user.keyboard('{Escape}');

    store.dispatch(startSession('Aria'));
    store.dispatch(setActiveSession('Aria'));
    await user.click(screen.getByRole('button', { name: 'Open world menu' }));
    await user.click(screen.getByRole('menuitem', { name: 'Leave the world as Aria' }));

    expect(disconnectMock).toHaveBeenCalledWith('Aria');
  });

  it('is a button, not a link to the redirecting front page', () => {
    renderWithProviders(<GameTopBar characters={[]} />);

    expect(screen.queryByRole('link', { name: 'Open world menu' })).toBeNull();
  });
});
