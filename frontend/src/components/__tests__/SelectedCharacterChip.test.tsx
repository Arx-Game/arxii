/**
 * SelectedCharacterChip (#3412, presence-aware since #3859) — the docked-portrait
 * chip's own contract in isolation: portrait/name render, the real
 * `PersonaSwitcher` works from this mount point (not just inside `/game`'s
 * `GameTopBar`), the buttons follow the character's LIVE session in the store
 * rather than the route ("Enter the world" with no session, "Return to the
 * world" + "Disconnect Character" with one), and the sub-line states presence as a
 * fact the store can back. The chip deliberately has NO clear-selection
 * control (Apostate ruling 2026-08-28 — "step away" read as logout; "Clear
 * Active Character" lands in the Hall's "Your Characters" band in slice 2).
 *
 * `PersonaSwitcher`'s OWN underlying queries (`@/game/personaQueries`) are
 * mocked here — same technique as `PersonaSwitcher.test.tsx` — so this test
 * exercises the real switcher component end to end from the chip, proving
 * it isn't coupled to `GameTopBar`/`/game` in any way. The socket hook is
 * mocked so "Leave the world" can be asserted as the one call it makes.
 */
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { Provider } from 'react-redux';
import { MemoryRouter } from 'react-router-dom';
import { configureStore } from '@reduxjs/toolkit';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { SwitchablePersona } from '@/game/personaQueries';
import { SelectedCharacterChip } from '../SelectedCharacterChip';
import type { MyRosterEntry } from '@/roster/types';
import {
  gameSlice,
  setSessionConnectionStatus,
  setSessionRoom,
  startSession,
} from '@/store/gameSlice';

const { state, setActiveMutate, selectMutate, disconnectMock, everywhereMock } = vi.hoisted(() => ({
  state: { personas: [] as SwitchablePersona[] },
  setActiveMutate: vi.fn(),
  selectMutate: vi.fn(),
  disconnectMock: vi.fn(),
  everywhereMock: vi.fn(),
}));

vi.mock('@/game/personaQueries', () => ({
  useCharacterPersonasQuery: () => ({ data: state.personas }),
  useSetActivePersonaMutation: () => ({ mutate: setActiveMutate, isPending: false }),
  useSetPersonaProfileMutation: () => ({
    mutate: vi.fn(),
    reset: vi.fn(),
    isPending: false,
    isError: false,
    error: null,
  }),
}));

vi.mock('@/roster/queries', () => ({
  useSelectCharacterMutation: () => ({ mutate: selectMutate, isPending: false }),
  useDisconnectEverywhereMutation: () => ({ mutate: everywhereMock, isPending: false }),
}));

vi.mock('@/hooks/useGameSocket', () => ({
  useGameSocket: () => ({ disconnect: disconnectMock }),
}));

function persona(
  id: number,
  name: string,
  type: SwitchablePersona['persona_type']
): SwitchablePersona {
  return {
    id,
    name,
    persona_type: type,
    is_fake_name: type === 'temporary',
    thumbnail_url: null,
    thumbnail_media_url: null,
    guise_concept: '',
    guise_quote: '',
    guise_never_do: '',
    guise_protect: '',
    guise_fear: '',
    guise_background: '',
  };
}

const aria: MyRosterEntry = {
  id: 1,
  name: 'Aria',
  character_id: 42,
  profile_picture_url: null,
  loan: null,
  npc_notes: null,
  is_crowd_voice: false,
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

function makeStore() {
  return configureStore({ reducer: { game: gameSlice.reducer } });
}

/** A store in which Aria has a live, in-world session in the named room. */
function storeWithAriaLive(roomName: string | null = 'Quiet courtyard') {
  const store = makeStore();
  store.dispatch(startSession('Aria'));
  store.dispatch(setSessionConnectionStatus({ character: 'Aria', status: true }));
  if (roomName) {
    store.dispatch(
      setSessionRoom({
        character: 'Aria',
        room: {
          id: 2,
          name: roomName,
          description: 'Rain rests on the stones.',
          thumbnail_url: null,
          characters: [],
          objects: [],
          exits: [],
          is_owner: false,
          is_public: true,
          hub: null,
          viewer_place_id: null,
        },
      })
    );
  }
  return store;
}

function Wrapper({
  children,
  store = makeStore(),
  path = '/',
}: {
  children: ReactNode;
  store?: ReturnType<typeof makeStore>;
  path?: string;
}) {
  return (
    <Provider store={store}>
      <MemoryRouter initialEntries={[path]}>{children}</MemoryRouter>
    </Provider>
  );
}

describe('SelectedCharacterChip (#3412, #3859)', () => {
  beforeEach(() => {
    disconnectMock.mockClear();
    everywhereMock.mockClear();
    setActiveMutate.mockClear();
    selectMutate.mockClear();
  });

  it('renders the portrait, name, and an Enter-the-world link to /game when there is no session', () => {
    state.personas = [persona(7, 'Aria', 'primary')];

    render(
      <Wrapper>
        <SelectedCharacterChip entry={aria} />
      </Wrapper>
    );

    // "Aria" legitimately appears twice: the chip's own name span, and
    // PersonaSwitcher's single-persona fallback (no switcher UI, just the
    // worn persona's name) — the primary persona here shares the character's
    // name, same as most characters' own primary face.
    expect(screen.getAllByText('Aria')).toHaveLength(2);
    expect(screen.getByRole('link', { name: /enter the world/i })).toHaveAttribute('href', '/game');
    expect(screen.queryByRole('button', { name: /disconnect character/i })).not.toBeInTheDocument();
  });

  it('lets the player switch which face the character presents as, from this mount point', async () => {
    // Two faces — PersonaSwitcher renders the actual switching dropdown
    // (single-face collapses to a bare name, per PersonaSwitcher.test.tsx).
    state.personas = [persona(7, 'Aria', 'primary'), persona(8, 'The Veiled Lady', 'established')];
    const user = userEvent.setup();

    render(
      <Wrapper>
        <SelectedCharacterChip entry={{ ...aria, active_persona_id: 7 }} />
      </Wrapper>
    );

    await user.click(screen.getByTitle('Switch which identity you are presenting as'));
    await user.click(screen.getByText('The Veiled Lady'));

    expect(setActiveMutate).toHaveBeenCalledWith(8);
  });

  it('says "Not in the world" for an ALIVE character with no session, and drops the fragment on /game', () => {
    state.personas = [persona(7, 'Aria', 'primary')];

    const { unmount } = render(
      <Wrapper path="/tidings">
        <SelectedCharacterChip entry={aria} />
      </Wrapper>
    );
    expect(screen.getByText(/Not in the world/)).toBeInTheDocument();
    expect(screen.queryByText(/Currently Offscreen/)).not.toBeInTheDocument();
    unmount();

    // On /game the top bar already carries the connection state; the chip
    // must not restate it. Only the worn-persona line remains.
    render(
      <Wrapper path="/game">
        <SelectedCharacterChip entry={aria} />
      </Wrapper>
    );
    expect(screen.queryByText(/in the world/i)).not.toBeInTheDocument();
    expect(screen.getByText(/as Aria/)).toBeInTheDocument();
  });

  // #3859 — the fact the chip used to get wrong: navigating from /game to the
  // Hall keeps the character's socket open (ADR-0295), and the chip claimed
  // "Enter the world" / "Currently Offscreen" over a live session.
  it('reads the live session: "In the world" with the room, a Return link, and a Disconnect button', () => {
    state.personas = [persona(7, 'Aria', 'primary')];

    render(
      <Wrapper store={storeWithAriaLive()} path="/hall">
        <SelectedCharacterChip entry={aria} />
      </Wrapper>
    );

    expect(screen.getByText(/In the world, Quiet courtyard/)).toBeInTheDocument();
    expect(screen.queryByText(/Not in the world/)).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: /return to the world/i })).toHaveAttribute(
      'href',
      '/game'
    );
    expect(screen.queryByRole('link', { name: /enter the world/i })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /disconnect character/i })).toBeInTheDocument();
  });

  it('says "In the world" without a room while the session is still entering', () => {
    state.personas = [persona(7, 'Aria', 'primary')];

    render(
      <Wrapper store={storeWithAriaLive(null)} path="/hall">
        <SelectedCharacterChip entry={aria} />
      </Wrapper>
    );

    expect(screen.getByText(/· In the world$/)).toBeInTheDocument();
  });

  it('"Disconnect Character" with one session closes that character\'s socket and nothing else', async () => {
    state.personas = [persona(7, 'Aria', 'primary')];
    const user = userEvent.setup();

    render(
      <Wrapper store={storeWithAriaLive()} path="/hall">
        <SelectedCharacterChip entry={aria} />
      </Wrapper>
    );

    await user.click(screen.getByRole('button', { name: /disconnect character/i }));

    expect(disconnectMock).toHaveBeenCalledTimes(1);
    expect(disconnectMock).toHaveBeenCalledWith('Aria');
    expect(everywhereMock).not.toHaveBeenCalled();
    // Disconnecting never clears the selection (ruled vocabulary: "quit"
    // leaves the grid but stays selected; "Clear Active Character" is the
    // character list's control).
    expect(selectMutate).not.toHaveBeenCalled();
  });

  // #4321: presence is a server fact. A tab that opened no socket reads the
  // roster payload's session_count/room_name, so a second tab or device never
  // says "Not in the world" about a character standing in a room elsewhere.
  it('states presence from the server when this tab holds no socket, and disconnects everywhere', async () => {
    state.personas = [persona(7, 'Aria', 'primary')];
    const user = userEvent.setup();
    const elsewhere: MyRosterEntry = { ...aria, session_count: 1, room_name: 'Quiet courtyard' };

    render(
      <Wrapper path="/hall">
        <SelectedCharacterChip entry={elsewhere} />
      </Wrapper>
    );

    expect(screen.getByText(/In the world, Quiet courtyard/)).toBeInTheDocument();
    expect(screen.queryByText(/Not in the world/)).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: /return to the world/i })).toHaveAttribute(
      'href',
      '/game'
    );

    // No socket here means no "this connection" to close: one press, every
    // session, no prompt.
    await user.click(screen.getByRole('button', { name: /disconnect character/i }));
    expect(screen.queryByRole('menuitem')).not.toBeInTheDocument();
    expect(everywhereMock).toHaveBeenCalledWith(1);
    expect(disconnectMock).not.toHaveBeenCalled();
  });

  it('offers This connection or Every connection only with a local socket and another session', async () => {
    state.personas = [persona(7, 'Aria', 'primary')];
    const user = userEvent.setup();

    render(
      <Wrapper store={storeWithAriaLive()} path="/hall">
        <SelectedCharacterChip entry={{ ...aria, session_count: 2 }} />
      </Wrapper>
    );

    await user.click(screen.getByRole('button', { name: /disconnect character/i }));
    expect(screen.getByRole('menuitem', { name: 'This connection' })).toBeInTheDocument();
    await user.click(screen.getByRole('menuitem', { name: 'Every connection' }));

    expect(everywhereMock).toHaveBeenCalledWith(1);
    expect(disconnectMock).not.toHaveBeenCalled();
  });

  it('shows the degraded state label instead of a presence claim for a CAPTURED character (#3412 review IMPORTANT-1)', () => {
    state.personas = [persona(7, 'Aria', 'primary')];
    const captured: MyRosterEntry = { ...aria, lifecycle_state: 'CAPTURED' };

    render(
      <Wrapper path="/tidings">
        <SelectedCharacterChip entry={captured} />
      </Wrapper>
    );

    expect(screen.getByText(/Held captive/)).toBeInTheDocument();
    expect(screen.queryByText(/Not in the world/)).not.toBeInTheDocument();
  });

  it('keeps "Enter the world" rendered for a DEAD docked character (spectator/ghost entry stays allowed)', () => {
    state.personas = [persona(7, 'Aria', 'primary')];
    const dead: MyRosterEntry = { ...aria, lifecycle_state: 'DEAD' };

    render(
      <Wrapper path="/tidings">
        <SelectedCharacterChip entry={dead} />
      </Wrapper>
    );

    expect(screen.getByText(/· Dead/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /enter the world/i })).toHaveAttribute('href', '/game');
  });

  it('carries no clear-selection control (ruled: clearing lives with the character list)', () => {
    state.personas = [persona(7, 'Aria', 'primary')];

    render(
      <Wrapper>
        <SelectedCharacterChip entry={aria} />
      </Wrapper>
    );

    expect(screen.queryByTitle('Step away')).not.toBeInTheDocument();
    expect(selectMutate).not.toHaveBeenCalled();
  });
});
