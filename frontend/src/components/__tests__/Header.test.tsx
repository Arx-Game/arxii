/**
 * Header smoke test — verify navigation links are present.
 */

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { ReactNode } from 'react';
import { Provider } from 'react-redux';
import { configureStore } from '@reduxjs/toolkit';
import { Header } from '../Header';
import { authSlice, setAccount } from '@/store/authSlice';
import type { AccountData } from '@/evennia_replacements/types';
import { gameSlice, hydrateActiveCharacter } from '@/store/gameSlice';
import { rouletteSlice } from '@/store/rouletteSlice';
import type { MyRosterEntry } from '@/roster/types';

function setupUser() {
  return { user: userEvent.setup() };
}

// Mock the queries that Header uses
vi.mock('@/staff/queries', () => ({
  useOpenSubmissionCount: () => ({
    data: undefined,
  }),
}));

// The account menu (`ProfileDropdown`'s `useLogout`) wants a QueryClient and the
// game socket once a viewer is signed in; the #4188 cases below sign one in, so
// stub it out the way the other query-backed pieces are. Its own behaviour is
// covered by ProfileDropdown.test.tsx.
vi.mock('../UserNav', () => ({
  UserNav: () => <span data-testid="user-nav-stub" />,
}));

// #4188 — the GMing badge's count. `mockAttention` is overridden per test.
const mockAttention = vi.fn((_enabled: boolean) => ({
  data: undefined as { total: number } | undefined,
}));
vi.mock('@/gm/queries', () => ({
  useGMAttention: (enabled: boolean) => mockAttention(enabled),
}));

vi.mock('@/narrative/components/UnreadNarrativeBadge', () => ({
  UnreadNarrativeBadge: () => <div data-testid="unread-badge" />,
}));

vi.mock('@/mail/queries', () => ({
  useUnreadMailCount: () => 0,
}));

vi.mock('@/rituals/queries', () => ({
  useRitualSessionInbox: () => ({
    data: [],
  }),
}));

// #3412 — the docked-portrait chip's roster lookup + selection-clearing
// mutation. No QueryClientProvider is mounted in this file's Wrapper (every
// other query hook here is mocked out the same way), so a real
// `useMyRosterEntriesQuery` would throw "No QueryClient set". Empty by
// default; the chip-specific describe block below overrides this per test
// via `mockRosterEntries`.
const mockRosterEntries = vi.fn(() => ({ data: [] as MyRosterEntry[] }));
const mockSelectMutate = vi.fn();
vi.mock('@/roster/queries', () => ({
  useMyRosterEntriesQuery: () => mockRosterEntries(),
  useSelectCharacterMutation: () => ({ mutate: mockSelectMutate, isPending: false }),
}));

// PersonaSwitcher pulls in its own react-query hooks (personaQueries.ts) —
// stubbed out for the same QueryClientProvider-less-Wrapper reason. Its own
// behavior is covered by PersonaSwitcher.test.tsx.
vi.mock('@/game/components/PersonaSwitcher', () => ({
  PersonaSwitcher: () => <span data-testid="persona-switcher-stub" />,
}));

// SelectedCharacterChip (#3412 slice 2 restyle) also reads
// `useCharacterPersonasQuery` directly now (to resolve the worn persona's
// name for its sub-line) — same QueryClientProvider-less-Wrapper reason as
// PersonaSwitcher above. Empty by default; falls back to the entry's own
// name (`SelectedCharacterChip`'s `wornName` fallback), which is what these
// tests assert on.
vi.mock('@/game/personaQueries', () => ({
  useCharacterPersonasQuery: () => ({ data: [] }),
}));

function makeStore() {
  return configureStore({
    reducer: {
      auth: authSlice.reducer,
      game: gameSlice.reducer,
      roulette: rouletteSlice.reducer,
    },
  });
}

/** A signed-in viewer; `is_gm` and `is_staff` decide what the header shows (#4188). */
function makeAccount(overrides: Partial<AccountData> = {}): AccountData {
  return {
    id: 1,
    username: 'viewer',
    display_name: 'Viewer',
    last_login: null,
    email: '',
    email_verified: true,
    can_create_characters: true,
    character_slots: { total: null, used: 0, activity_total: 0, activity_used: 0, holders: [] },
    is_staff: false,
    is_gm: false,
    is_guide: false,
    available_characters: [],
    pending_applications: [],
    selected_entry_id: null,
    selected_entry: null,
    ...overrides,
  };
}

function storeFor(account: AccountData | null) {
  const store = makeStore();
  if (account) store.dispatch(setAccount(account));
  return store;
}

function Wrapper({
  children,
  store = makeStore(),
}: {
  children: ReactNode;
  store?: ReturnType<typeof makeStore>;
}) {
  return (
    <Provider store={store}>
      <MemoryRouter>{children}</MemoryRouter>
    </Provider>
  );
}

describe('Header', () => {
  beforeEach(() => {
    mockRosterEntries.mockReturnValue({ data: [] });
    mockSelectMutate.mockClear();
    mockAttention.mockReset();
    mockAttention.mockReturnValue({ data: undefined });
  });

  it('renders direct nav links and dropdown triggers', () => {
    render(
      <Wrapper>
        <Header />
      </Wrapper>
    );

    // Play is a direct link, always visible
    expect(screen.getByRole('link', { name: /play/i })).toBeInTheDocument();

    // Dropdown group triggers are present as buttons
    expect(screen.getByRole('button', { name: /characters/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /story/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /world/i })).toBeInTheDocument();
  });

  it('renders dropdown links when a group is opened', async () => {
    const { user } = setupUser();
    render(
      <Wrapper>
        <Header />
      </Wrapper>
    );

    // Open the Characters dropdown
    await user.click(screen.getByRole('button', { name: /characters/i }));

    // Links inside the dropdown are now visible
    expect(screen.getByRole('link', { name: /roster/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /progression/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /threads/i })).toBeInTheDocument();
  });

  it('renders dropdown content inside its own nav item so it opens under the trigger', async () => {
    const { user } = setupUser();
    render(
      <Wrapper>
        <Header />
      </Wrapper>
    );

    const trigger = screen.getByRole('button', { name: /characters/i });
    await user.click(trigger);

    // The panel must be a descendant of the trigger's list item — a shared
    // viewport outside the item renders every dropdown at the same spot on
    // the page instead of under its trigger (unclickable on hover-out).
    const item = trigger.closest('li');
    expect(item).not.toBeNull();
    expect(item).toContainElement(screen.getByRole('link', { name: /roster/i }));
  });

  it('renders Story dropdown links when opened', async () => {
    const { user } = setupUser();
    render(
      <Wrapper>
        <Header />
      </Wrapper>
    );

    await user.click(screen.getByRole('button', { name: /story/i }));

    expect(screen.getByRole('link', { name: /scenes/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /events/i })).toBeInTheDocument();
    // My Stories and Books are auth-only — not logged in, so absent
  });

  it('renders World dropdown links when opened', async () => {
    const { user } = setupUser();
    render(
      <Wrapper>
        <Header />
      </Wrapper>
    );

    await user.click(screen.getByRole('button', { name: /world/i }));

    // World is the lore shelf (#4188): Crossover left for the GM Dashboard strip.
    expect(screen.queryByRole('link', { name: /crossover/i })).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: /codex/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /tidings/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /journals/i })).toHaveAttribute('href', '/journals');
    // The Realms hub (#3725): one plain link, no per-realm jumps under it.
    expect(screen.getByRole('link', { name: /realms/i })).toHaveAttribute('href', '/realms');
  });

  // ---------------------------------------------------------------------------
  // GMing group (#4188): story design and tracking, one badge, World is lore.
  // ---------------------------------------------------------------------------

  describe('GMing group (#4188)', () => {
    it('shows no GMing group to a signed-out visitor, and never asks for the count', () => {
      render(
        <Wrapper store={storeFor(null)}>
          <Header />
        </Wrapper>
      );

      expect(screen.queryByRole('button', { name: /gming/i })).not.toBeInTheDocument();
      expect(mockAttention).toHaveBeenCalledWith(false);
    });

    it('shows no GMing group to a signed-in player who is neither GM nor staff', () => {
      render(
        <Wrapper store={storeFor(makeAccount())}>
          <Header />
        </Wrapper>
      );

      expect(screen.queryByRole('button', { name: /gming/i })).not.toBeInTheDocument();
      expect(screen.getByRole('link', { name: /inbox/i })).toBeInTheDocument();
      expect(mockAttention).toHaveBeenCalledWith(false);
    });

    it('gives a GM the four GM rows and no Staff section', async () => {
      const { user } = setupUser();
      render(
        <Wrapper store={storeFor(makeAccount({ is_gm: true }))}>
          <Header />
        </Wrapper>
      );

      await user.click(screen.getByRole('button', { name: /gming/i }));

      expect(screen.getByRole('link', { name: 'Dashboard' })).toHaveAttribute(
        'href',
        '/gm/dashboard'
      );
      expect(screen.getByRole('link', { name: 'Story Builder' })).toHaveAttribute(
        'href',
        '/gm/story-builder'
      );
      expect(screen.getByRole('link', { name: 'Tables' })).toHaveAttribute('href', '/tables');
      expect(screen.getByRole('link', { name: 'Lead GM Queue' })).toHaveAttribute(
        'href',
        '/stories/gm-queue'
      );
      expect(screen.queryByRole('link', { name: 'Story Workload' })).not.toBeInTheDocument();
      expect(screen.queryByText('Staff')).not.toBeInTheDocument();
      expect(mockAttention).toHaveBeenCalledWith(true);
    });

    it('carries one count on the trigger when something is waiting, none at zero', () => {
      mockAttention.mockReturnValue({ data: { total: 7 } });
      const { unmount } = render(
        <Wrapper store={storeFor(makeAccount({ is_gm: true }))}>
          <Header />
        </Wrapper>
      );

      expect(screen.getByTestId('gm-attention-badge')).toHaveTextContent('7');
      unmount();

      mockAttention.mockReturnValue({ data: { total: 0 } });
      render(
        <Wrapper store={storeFor(makeAccount({ is_gm: true }))}>
          <Header />
        </Wrapper>
      );

      expect(screen.queryByTestId('gm-attention-badge')).not.toBeInTheDocument();
    });

    it('gives staff who are not GMs only the Staff section, with Story Workload', async () => {
      const { user } = setupUser();
      render(
        <Wrapper store={storeFor(makeAccount({ is_staff: true }))}>
          <Header />
        </Wrapper>
      );

      await user.click(screen.getByRole('button', { name: /gming/i }));

      expect(screen.getByText('Staff', { selector: 'p' })).toBeInTheDocument();
      expect(screen.getByRole('link', { name: 'Story Workload' })).toHaveAttribute(
        'href',
        '/stories/staff-workload'
      );
      expect(screen.queryByRole('link', { name: 'Dashboard' })).not.toBeInTheDocument();
      expect(screen.queryByRole('link', { name: 'Lead GM Queue' })).not.toBeInTheDocument();
      // The GMing badge needs a GMProfile; staff without one never ask for it.
      expect(mockAttention).toHaveBeenCalledWith(false);
    });

    it('gives staff who are also GMs one menu holding both', async () => {
      const { user } = setupUser();
      render(
        <Wrapper store={storeFor(makeAccount({ is_staff: true, is_gm: true }))}>
          <Header />
        </Wrapper>
      );

      await user.click(screen.getByRole('button', { name: /gming/i }));

      expect(screen.getByRole('link', { name: 'Dashboard' })).toBeInTheDocument();
      expect(screen.getByRole('link', { name: 'Story Workload' })).toBeInTheDocument();
      expect(screen.getAllByRole('button', { name: /gming/i })).toHaveLength(1);
    });

    it('has no loose Story Workload link in the top bar for staff', () => {
      render(
        <Wrapper store={storeFor(makeAccount({ is_staff: true }))}>
          <Header />
        </Wrapper>
      );

      // Closed menu: the only staff door in the bar is the Staff link itself.
      expect(screen.queryByRole('link', { name: 'Story Workload' })).not.toBeInTheDocument();
      expect(screen.getByRole('link', { name: /^staff/i })).toHaveAttribute('href', '/staff');
    });

    it('mirrors the group and its count in the phone sheet', async () => {
      const { user } = setupUser();
      mockAttention.mockReturnValue({ data: { total: 3 } });
      render(
        <Wrapper store={storeFor(makeAccount({ is_gm: true, is_staff: true }))}>
          <Header />
        </Wrapper>
      );

      await user.click(screen.getByRole('button', { name: /open menu/i }));

      const sheet = screen.getByRole('dialog');
      expect(sheet).toHaveTextContent('GMing (3)');
      expect(sheet).toHaveTextContent('Dashboard');
      expect(sheet).toHaveTextContent('Story Workload');
      expect(sheet).not.toHaveTextContent('Crossover');
    });
  });

  // ---------------------------------------------------------------------------
  // Docked-portrait chip (#3412) — the app-wide chrome surface for the
  // account's durable server-side character selection.
  // ---------------------------------------------------------------------------

  describe('docked-portrait chip (#3412)', () => {
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

    it("renders no chip when there is no selection (byte-for-byte today's header)", () => {
      mockRosterEntries.mockReturnValue({ data: [aria] });
      const store = makeStore();

      render(
        <Wrapper store={store}>
          <Header />
        </Wrapper>
      );

      expect(screen.queryByText('Aria')).not.toBeInTheDocument();
      expect(screen.queryByText(/enter the world/i)).not.toBeInTheDocument();
    });

    it('renders the chip (portrait, name, persona switcher, enter-the-world) when a selection exists', () => {
      mockRosterEntries.mockReturnValue({ data: [aria] });
      const store = makeStore();
      store.dispatch(hydrateActiveCharacter({ name: 'Aria', entryId: 1 }));

      render(
        <Wrapper store={store}>
          <Header />
        </Wrapper>
      );

      expect(screen.getByText('Aria')).toBeInTheDocument();
      expect(screen.getByTestId('persona-switcher-stub')).toBeInTheDocument();
      const enterLink = screen.getByRole('link', { name: /enter the world/i });
      expect(enterLink).toHaveAttribute('href', '/game');
      // No clear-selection control in the chip (Apostate ruling 2026-08-28 —
      // "step away" read as logout; "Clear Active Character" lands in the
      // Hall's "Your Characters" band in slice 2).
      expect(screen.queryByTitle('Step away')).not.toBeInTheDocument();
      expect(mockSelectMutate).not.toHaveBeenCalled();
    });

    it('does not render the chip when the roster entry for the active name has not loaded yet', () => {
      // `active` set (e.g. hydration in flight) but the roster query hasn't
      // resolved the matching entry yet — no chip until there's data to show.
      mockRosterEntries.mockReturnValue({ data: [] });
      const store = makeStore();
      store.dispatch(hydrateActiveCharacter({ name: 'Aria', entryId: 1 }));

      render(
        <Wrapper store={store}>
          <Header />
        </Wrapper>
      );

      expect(screen.queryByText('Aria')).not.toBeInTheDocument();
    });
  });
});
