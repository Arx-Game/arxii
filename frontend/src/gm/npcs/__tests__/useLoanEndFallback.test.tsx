import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Provider } from 'react-redux';
import type { ReactNode } from 'react';

import type { MyRosterEntry } from '@/roster/types';
import { store } from '@/store/store';
import { hydrateActiveCharacter, resetGame } from '@/store/gameSlice';

import { fallbackEntry, useLoanEndFallback } from '../useLoanEndFallback';

const dropSession = vi.fn();
const postSelectEntry = vi.fn().mockResolvedValue({});
vi.mock('@/roster/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/roster/api')>()),
  postSelectEntry: (...args: unknown[]) => postSelectEntry(...args),
}));

function entry(id: number, name: string, roster_type: string): MyRosterEntry {
  return {
    id,
    name,
    roster_type,
    is_story_npc: roster_type === 'NPC',
    character_id: id * 10,
  } as unknown as MyRosterEntry;
}
const ilsa = entry(1, 'Ilsa', 'PC');
const mira = entry(2, 'Sergeant Mira', 'NPC');

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <Provider store={store}>
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    </Provider>
  );
}

afterEach(() => {
  store.dispatch(resetGame());
  vi.clearAllMocks();
});

describe('useLoanEndFallback', () => {
  it('prefers a PC over an NPC', () => {
    expect(fallbackEntry([mira, ilsa])).toBe(ilsa);
    expect(fallbackEntry([])).toBeNull();
  });

  it('drops the tab to the remaining character when the played NPC leaves the list', async () => {
    store.dispatch(hydrateActiveCharacter({ name: 'Sergeant Mira', entryId: 2 }));
    const { rerender } = renderHook(
      ({ characters }) =>
        useLoanEndFallback(characters, store.getState().game.active, () => false, dropSession),
      { wrapper, initialProps: { characters: [ilsa, mira] } }
    );
    expect(store.getState().game.active).toBe('Sergeant Mira');
    act(() => rerender({ characters: [ilsa] }));
    expect(store.getState().game.active).toBe('Ilsa');
    expect(store.getState().game.activeEntryId).toBe(1);
    expect(dropSession).toHaveBeenCalledWith('Sergeant Mira');
    await waitFor(() => expect(postSelectEntry).toHaveBeenCalledWith(1));
  });

  it('falls back even when the account refetch already cleared the active name', () => {
    store.dispatch(hydrateActiveCharacter({ name: 'Sergeant Mira', entryId: 2 }));
    const { rerender } = renderHook(
      ({ characters, active }: { characters: MyRosterEntry[]; active: string | null }) =>
        useLoanEndFallback(characters, active, () => false, dropSession),
      {
        wrapper,
        initialProps: { characters: [ilsa, mira], active: 'Sergeant Mira' as string | null },
      }
    );
    act(() => rerender({ characters: [ilsa], active: null }));
    expect(store.getState().game.active).toBe('Ilsa');
  });

  it('stays on a played entry whose name changes', () => {
    store.dispatch(hydrateActiveCharacter({ name: 'Sergeant Mira', entryId: 2 }));
    const { rerender } = renderHook(
      ({ characters }) =>
        useLoanEndFallback(characters, store.getState().game.active, () => false, dropSession),
      { wrapper, initialProps: { characters: [ilsa, mira] } }
    );
    act(() => rerender({ characters: [ilsa, { ...mira, name: 'The Low Gate Watch' }] }));
    expect(store.getState().game.active).toBe('The Low Gate Watch');
    expect(store.getState().game.activeEntryId).toBe(2);
    expect(postSelectEntry).not.toHaveBeenCalled();
    expect(dropSession).not.toHaveBeenCalled();
  });

  it('leaves a character the account still holds alone', () => {
    store.dispatch(hydrateActiveCharacter({ name: 'Ilsa', entryId: 1 }));
    const { rerender } = renderHook(
      ({ characters }) => useLoanEndFallback(characters, 'Ilsa', () => false, dropSession),
      { wrapper, initialProps: { characters: [ilsa, mira] } }
    );
    act(() => rerender({ characters: [ilsa] }));
    expect(store.getState().game.active).toBe('Ilsa');
    expect(postSelectEntry).not.toHaveBeenCalled();
  });
});
