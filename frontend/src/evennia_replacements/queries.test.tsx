/**
 * Tests for useAccountQuery's reload-hydration effect (#3412).
 *
 * Mirrors GameTopBar.test.tsx's idiom: the real Redux store (imported
 * directly), reset between tests via resetGame(). Only `./api` is mocked
 * (vi.fn(), no msw) — mirrors consent/__tests__/queries.test.ts.
 */
import type { ReactNode } from 'react';
import { renderHook, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Provider } from 'react-redux';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

vi.mock('./api', () => ({
  fetchAccount: vi.fn(),
  fetchRegistrationStatus: vi.fn(),
  postLogin: vi.fn(),
  postLogout: vi.fn(),
  postRegister: vi.fn(),
}));

import { fetchAccount } from './api';
import { useAccountQuery } from './queries';
import type { AccountData, AvailableCharacter } from './types';
import type { MyRosterEntry } from '@/roster/types';
import { store } from '@/store/store';
import {
  resetGame,
  startSession,
  setSessionConnectionStatus,
  clearBrowsingIdentity,
} from '@/store/gameSlice';
import { clearTabIdentity, readTabIdentity, writeTabIdentity } from '@/store/browsingIdentity';

function availableCharacter(id: number, name: string): AvailableCharacter {
  return {
    id,
    name,
    portrait_url: null,
    character_type: 'PC',
    roster_status: 'Active',
    personas: [],
    last_location: null,
    currently_puppeted_in_session: false,
  };
}

function rosterEntry(id: number, name: string): MyRosterEntry {
  return {
    id,
    name,
    character_id: id * 10,
    profile_picture_url: null,
    primary_persona_id: 1,
    active_persona_id: 1,
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
}

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <Provider store={store}>
        <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
      </Provider>
    );
  };
}

const BASE_ACCOUNT: AccountData = {
  id: 1,
  username: 'tester',
  display_name: 'Tester',
  last_login: null,
  email: 't@example.com',
  email_verified: true,
  can_create_characters: true,
  character_slots: { total: 4, used: 0, activity_total: 1, activity_used: 0, holders: [] },
  is_staff: false,
  is_gm: false,
  available_characters: [],
  pending_applications: [],
  selected_entry_id: null,
  selected_entry: null,
};

describe('useAccountQuery hydration (#3412)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    store.dispatch(resetGame());
    // #3479: hydration now branches on this tab's sessionStorage identity --
    // each test is a fresh tab unless it seeds one itself.
    sessionStorage.clear();
  });

  afterEach(() => {
    store.dispatch(resetGame());
    sessionStorage.clear();
  });

  it('hydrates gameSlice.active/activeEntryId from selected_entry on a successful fetch', async () => {
    vi.mocked(fetchAccount).mockResolvedValue({
      ...BASE_ACCOUNT,
      selected_entry_id: 7,
      selected_entry: {
        id: 7,
        name: 'Aria',
        character_id: 42,
        profile_picture_url: null,
        primary_persona_id: 1,
        active_persona_id: 1,
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
      },
    });

    const { result } = renderHook(() => useAccountQuery(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    await waitFor(() => expect(store.getState().game.active).toBe('Aria'));
    expect(store.getState().game.activeEntryId).toBe(7);
  });

  it('does not touch gameSlice.active when selected_entry is null (never selected)', async () => {
    vi.mocked(fetchAccount).mockResolvedValue(BASE_ACCOUNT);

    const { result } = renderHook(() => useAccountQuery(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(store.getState().game.active).toBeNull();
    expect(store.getState().game.activeEntryId).toBeNull();
  });

  // #3412 review fix (finding 2): the explicit-clear path (mutate(null) on
  // useSelectCharacterMutation, then the account refetch it triggers) must
  // actually null the slice mirror — a `selected_entry: null` payload is now
  // mirrored just as faithfully as a real selection, in both directions.
  it('clears an already-active gameSlice selection when the fetch carries no selection', async () => {
    store.dispatch(startSession('Bianca'));
    vi.mocked(fetchAccount).mockResolvedValue(BASE_ACCOUNT);

    const { result } = renderHook(() => useAccountQuery(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    await waitFor(() => expect(store.getState().game.active).toBeNull());
    expect(store.getState().game.activeEntryId).toBeNull();
  });

  // Clearing the mirror must NOT tear down a live session — selection isn't
  // presence in either direction. The WebSocket/session data (owned by
  // `sessions`, independent of the `active` pointer) survives orphaned; the
  // /game surface can still work off it once re-selected.
  it('leaves the live session itself untouched when clearing the active mirror', async () => {
    store.dispatch(startSession('Bianca'));
    store.dispatch(setSessionConnectionStatus({ character: 'Bianca', status: true }));
    vi.mocked(fetchAccount).mockResolvedValue(BASE_ACCOUNT);

    const { result } = renderHook(() => useAccountQuery(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    await waitFor(() => expect(store.getState().game.active).toBeNull());
    expect(store.getState().game.sessions['Bianca']).toBeDefined();
    expect(store.getState().game.sessions['Bianca'].isConnected).toBe(true);
  });

  it('does not create a session for the hydrated character (selection is not presence)', async () => {
    vi.mocked(fetchAccount).mockResolvedValue({
      ...BASE_ACCOUNT,
      selected_entry_id: 7,
      selected_entry: {
        id: 7,
        name: 'Aria',
        character_id: 42,
        profile_picture_url: null,
        primary_persona_id: 1,
        active_persona_id: 1,
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
      },
    });

    const { result } = renderHook(() => useAccountQuery(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    await waitFor(() => expect(store.getState().game.active).toBe('Aria'));
    expect(store.getState().game.sessions['Aria']).toBeUndefined();
  });
});

// Per-tab browsing identity (#3479): useAccountQuery's hydration effect now
// seeds this tab's `sessionStorage` identity only once, instead of
// unconditionally re-mirroring the account's durable selection on every
// `['account']` refetch -- the exact chokepoint that let one tab's selection
// stomp another tab's `active` (see the #3479 ledger's hydration row).
describe('useAccountQuery per-tab hydration (#3479)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    store.dispatch(resetGame());
    sessionStorage.clear();
  });

  afterEach(() => {
    store.dispatch(resetGame());
    sessionStorage.clear();
  });

  it('seeds an empty tab from the account default', async () => {
    vi.mocked(fetchAccount).mockResolvedValue({
      ...BASE_ACCOUNT,
      available_characters: [availableCharacter(7, 'Aria')],
      selected_entry_id: 7,
      selected_entry: rosterEntry(7, 'Aria'),
    });

    const { result } = renderHook(() => useAccountQuery(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    await waitFor(() => expect(store.getState().game.browsingEntryId).toBe(7));
    expect(store.getState().game.active).toBe('Aria');
    expect(store.getState().game.activeEntryId).toBe(7);
    expect(readTabIdentity()?.entryId).toBe(7);
  });

  it('never overwrites a tab that already has an identity', async () => {
    vi.mocked(fetchAccount).mockResolvedValue({
      ...BASE_ACCOUNT,
      available_characters: [availableCharacter(5, 'Aria'), availableCharacter(8, 'Zara')],
      selected_entry_id: 5,
      selected_entry: rosterEntry(5, 'Aria'),
    });

    const { result } = renderHook(() => useAccountQuery(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    await waitFor(() => expect(store.getState().game.browsingEntryId).toBe(5));
    const seededTabId = readTabIdentity()?.tabId;

    // A different default surfaces -- as if another tab (or the Hall) changed
    // the account-wide selection and this tab's own refetch mirrored it in.
    vi.mocked(fetchAccount).mockResolvedValue({
      ...BASE_ACCOUNT,
      available_characters: [availableCharacter(5, 'Aria'), availableCharacter(8, 'Zara')],
      selected_entry_id: 8,
      selected_entry: rosterEntry(8, 'Zara'),
    });
    await result.current.refetch();
    await waitFor(() => expect(result.current.data?.selected_entry_id).toBe(8));

    expect(store.getState().game.browsingEntryId).toBe(5);
    expect(store.getState().game.active).toBe('Aria');
    expect(store.getState().game.activeEntryId).toBe(5);
    expect(readTabIdentity()?.entryId).toBe(5);
    expect(readTabIdentity()?.tabId).toBe(seededTabId);
  });

  // Whole-branch review (Critical): the effect used to key on Redux's
  // browsingEntryId as well as on the account payload, so the Hall's "Clear
  // Active Character" (clearTabIdentity + clearBrowsingIdentity, then the
  // select mutation) re-ran it against the still-cached account and seeded
  // the just-cleared character straight back. A Redux-only change must not
  // re-seed; only a new account payload may.
  it('does not re-seed a tab that cleared its identity until the account refetches', async () => {
    vi.mocked(fetchAccount).mockResolvedValue({
      ...BASE_ACCOUNT,
      available_characters: [availableCharacter(7, 'Aria')],
      selected_entry_id: 7,
      selected_entry: rosterEntry(7, 'Aria'),
    });

    const { result } = renderHook(() => useAccountQuery(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    await waitFor(() => expect(store.getState().game.browsingEntryId).toBe(7));

    act(() => {
      clearTabIdentity();
      store.dispatch(clearBrowsingIdentity());
    });
    // Let any effect re-run settle before asserting nothing came back.
    await act(async () => {
      await Promise.resolve();
    });

    expect(store.getState().game.browsingEntryId).toBeNull();
    expect(readTabIdentity()).toBeNull();

    // The clearing mutation's refetch lands with no selection: the tab stays
    // clear, now in step with the column.
    vi.mocked(fetchAccount).mockResolvedValue({
      ...BASE_ACCOUNT,
      available_characters: [availableCharacter(7, 'Aria')],
      selected_entry_id: null,
      selected_entry: null,
    });
    await result.current.refetch();
    await waitFor(() => expect(result.current.data?.selected_entry_id).toBeNull());

    expect(store.getState().game.browsingEntryId).toBeNull();
    expect(store.getState().game.active).toBeNull();
    expect(readTabIdentity()).toBeNull();
  });

  it('clears and reseeds when the stored id is no longer owned', async () => {
    // Simulates a tab that already had an identity for a character the
    // account no longer owns (e.g. retired) -- not among available_characters.
    writeTabIdentity(99);
    vi.mocked(fetchAccount).mockResolvedValue({
      ...BASE_ACCOUNT,
      available_characters: [availableCharacter(3, 'Nyx')],
      selected_entry_id: 3,
      selected_entry: rosterEntry(3, 'Nyx'),
    });

    const { result } = renderHook(() => useAccountQuery(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    await waitFor(() => expect(store.getState().game.browsingEntryId).toBe(3));
    expect(store.getState().game.active).toBe('Nyx');
    expect(store.getState().game.activeEntryId).toBe(3);
    expect(readTabIdentity()?.entryId).toBe(3);
  });

  // #3479 review round 1 (Critical): sessionStorage is per-tab but survives
  // a reload of that same tab; Redux does not. Before this fix, the "stored
  // and still owned" branch returned early unconditionally, so a reload left
  // a warm sessionStorage identity stranded next to a cold, un-hydrated
  // Redux (`browsingEntryId`/`active`/`activeEntryId` all null) -- the tab
  // rendered as if nothing were selected. This test deliberately seeds
  // sessionStorage itself (no `beforeEach` here clears it after that seed)
  // and never dispatches into Redux first, to reproduce that exact cold-
  // Redux/warm-storage state.
  it('resolves this tab identity from sessionStorage after a cold Redux reload', async () => {
    writeTabIdentity(5);
    vi.mocked(fetchAccount).mockResolvedValue({
      ...BASE_ACCOUNT,
      available_characters: [availableCharacter(5, 'Aria'), availableCharacter(8, 'Zara')],
      // The account's durable default differs from the stored id -- the
      // stored id must win regardless.
      selected_entry_id: 8,
      selected_entry: rosterEntry(8, 'Zara'),
    });

    const { result } = renderHook(() => useAccountQuery(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    await waitFor(() => expect(store.getState().game.browsingEntryId).toBe(5));
    expect(store.getState().game.active).toBe('Aria');
    expect(store.getState().game.activeEntryId).toBe(5);
    expect(readTabIdentity()?.entryId).toBe(5);
  });
});
