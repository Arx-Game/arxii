import { act, renderHook } from '@testing-library/react';
import { vi } from 'vitest';

import { useAtlasState } from '../useAtlasState';

let mockAccount: { id: number } | null = { id: 7 };

vi.mock('@/store/hooks', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/store/hooks')>();
  return {
    ...actual,
    useAccount: () => mockAccount,
  };
});

describe('useAtlasState', () => {
  beforeEach(() => {
    window.localStorage.clear();
    mockAccount = { id: 7 };
  });

  it('starts with no view when nothing was ever stored', () => {
    const { result } = renderHook(() => useAtlasState());
    expect(result.current.view).toBeNull();
  });

  it('restores the last location from localStorage on mount', () => {
    window.localStorage.setItem(
      'world-builder-atlas:7:last-location',
      JSON.stringify({ kind: 'area', id: 42 })
    );

    const { result } = renderHook(() => useAtlasState());
    expect(result.current.view).toEqual({ kind: 'area', id: 42 });
  });

  it("scopes storage per account — a different account never sees another's last location", () => {
    window.localStorage.setItem(
      'world-builder-atlas:7:last-location',
      JSON.stringify({ kind: 'area', id: 42 })
    );
    mockAccount = { id: 9 };

    const { result } = renderHook(() => useAtlasState());
    expect(result.current.view).toBeNull();
  });

  it('setView persists the new location and records a Recent entry', () => {
    const { result } = renderHook(() => useAtlasState());

    act(() => result.current.setView({ kind: 'area', id: 5 }, 'Central Ward'));

    expect(result.current.view).toEqual({ kind: 'area', id: 5 });
    expect(result.current.recents[0]).toMatchObject({ kind: 'area', id: 5, name: 'Central Ward' });
    expect(JSON.parse(window.localStorage.getItem('world-builder-atlas:7:last-location')!)).toEqual(
      {
        kind: 'area',
        id: 5,
      }
    );
  });

  it('dedupes a re-visited node in Recent instead of listing it twice', () => {
    const { result } = renderHook(() => useAtlasState());

    act(() => result.current.setView({ kind: 'area', id: 5 }, 'Central Ward'));
    act(() => result.current.setView({ kind: 'roomdoc', id: 9 }, 'Kitchen'));
    act(() => result.current.setView({ kind: 'area', id: 5 }, 'Central Ward'));

    expect(result.current.recents).toHaveLength(2);
    expect(result.current.recents[0]).toMatchObject({ kind: 'area', id: 5 });
  });

  it('toggles a bookmark on and off', () => {
    const { result } = renderHook(() => useAtlasState());
    const entry = {
      kind: 'area' as const,
      id: 5,
      name: 'Central Ward',
      visitedAt: '2026-01-01T00:00:00Z',
    };

    act(() => result.current.togglePinned(entry));
    expect(result.current.isPinned({ kind: 'area', id: 5 })).toBe(true);
    expect(result.current.pinned).toHaveLength(1);

    act(() => result.current.togglePinned(entry));
    expect(result.current.isPinned({ kind: 'area', id: 5 })).toBe(false);
    expect(result.current.pinned).toHaveLength(0);
  });

  it('degrades to in-memory-only state when localStorage throws', () => {
    const originalGetItem = window.localStorage.getItem;
    vi.spyOn(window.localStorage.__proto__, 'getItem').mockImplementation(() => {
      throw new Error('storage disabled');
    });

    const { result } = renderHook(() => useAtlasState());
    expect(result.current.view).toBeNull();

    act(() => result.current.setView({ kind: 'area', id: 1 }));
    expect(result.current.view).toEqual({ kind: 'area', id: 1 });

    (window.localStorage.getItem as unknown as { mockRestore: () => void }).mockRestore();
    void originalGetItem;
  });
});
