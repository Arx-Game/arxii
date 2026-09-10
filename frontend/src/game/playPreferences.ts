import { useCallback, useEffect, useMemo, useState } from 'react';

export type SidebarSide = 'left' | 'right';
export type PlayDensity = 'compact' | 'comfortable';
export type ReaderMode = 'threads' | 'chronological';

export interface PlayPreferences {
  proseSize: number;
  proseFamily: 'sans' | 'serif';
  measure: number;
  sidebarWidth: number;
  sidebarSide: SidebarSide;
  density: PlayDensity;
  readerMode: ReaderMode;
}

export const DEFAULT_PLAY_PREFERENCES: PlayPreferences = {
  proseSize: 14,
  proseFamily: 'sans',
  measure: 90,
  sidebarWidth: 280,
  sidebarSide: 'right',
  density: 'compact',
  readerMode: 'threads',
};

const STORAGE_KEY = 'arx:play-preferences:v2';
const LEGACY_STORAGE_KEY = 'arx:play-preferences:v1';

function clamp(value: unknown, minimum: number, maximum: number, fallback: number): number {
  const number = Number(value);
  return Number.isFinite(number) ? Math.min(maximum, Math.max(minimum, number)) : fallback;
}

export function playPreferencesKey(accountId?: number | null): string {
  return accountId == null ? STORAGE_KEY : `${STORAGE_KEY}:account:${accountId}`;
}

export function loadPlayPreferences(accountId?: number | null): PlayPreferences {
  try {
    const stored =
      window.localStorage.getItem(playPreferencesKey(accountId)) ??
      (accountId == null ? window.localStorage.getItem(LEGACY_STORAGE_KEY) : null);
    const value = stored ? (JSON.parse(stored) as Partial<PlayPreferences>) : null;
    if (!value) return DEFAULT_PLAY_PREFERENCES;
    return {
      proseSize: clamp(value.proseSize, 12, 20, DEFAULT_PLAY_PREFERENCES.proseSize),
      proseFamily: value.proseFamily === 'serif' ? 'serif' : 'sans',
      measure: clamp(value.measure, 72, 110, DEFAULT_PLAY_PREFERENCES.measure),
      sidebarWidth: clamp(value.sidebarWidth, 240, 360, DEFAULT_PLAY_PREFERENCES.sidebarWidth),
      sidebarSide: value.sidebarSide === 'left' ? 'left' : 'right',
      density: value.density === 'comfortable' ? 'comfortable' : 'compact',
      readerMode: value.readerMode === 'chronological' ? 'chronological' : 'threads',
    };
  } catch {
    return DEFAULT_PLAY_PREFERENCES;
  }
}

export function savePlayPreferences(preferences: PlayPreferences, accountId?: number | null): void {
  try {
    window.localStorage.setItem(playPreferencesKey(accountId), JSON.stringify(preferences));
  } catch {
    // Storage can be disabled; callers continue with in-memory preferences.
  }
}

export function usePlayPreferences(accountId?: number | null) {
  const key = useMemo(() => playPreferencesKey(accountId), [accountId]);
  const [preferences, setPreferences] = useState(() => loadPlayPreferences(accountId));
  const update = useCallback(
    (patch: Partial<PlayPreferences>) => {
      setPreferences((current) => {
        const next = { ...current, ...patch };
        savePlayPreferences(next, accountId);
        return next;
      });
    },
    [accountId]
  );
  // Account changes should never display the previous account's layout.
  useEffect(() => {
    setPreferences(loadPlayPreferences(accountId));
  }, [key, accountId]);
  return { preferences, update };
}
