/**
 * Tests for useAccountQuery's reload-hydration effect (#3412).
 *
 * Mirrors GameTopBar.test.tsx's idiom: the real Redux store (imported
 * directly), reset between tests via resetGame(). Only `./api` is mocked
 * (vi.fn(), no msw) — mirrors consent/__tests__/queries.test.ts.
 */
import type { ReactNode } from 'react';
import { renderHook, waitFor } from '@testing-library/react';
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
import type { AccountData } from './types';
import { store } from '@/store/store';
import { resetGame, startSession, setSessionConnectionStatus } from '@/store/gameSlice';

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
  });

  afterEach(() => {
    store.dispatch(resetGame());
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
      },
    });

    const { result } = renderHook(() => useAccountQuery(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    await waitFor(() => expect(store.getState().game.active).toBe('Aria'));
    expect(store.getState().game.sessions['Aria']).toBeUndefined();
  });
});
