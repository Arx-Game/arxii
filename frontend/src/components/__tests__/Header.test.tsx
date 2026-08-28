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
import { authSlice } from '@/store/authSlice';
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

    expect(screen.getByRole('link', { name: /crossover/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /codex/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /tidings/i })).toBeInTheDocument();
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
      primary_persona_id: 7,
      active_persona_id: 7,
      unread_narrative_count: 0,
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
