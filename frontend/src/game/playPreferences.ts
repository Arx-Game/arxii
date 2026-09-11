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
      window.localStorage.getItem(LEGACY_STORAGE_KEY);
    const value = stored ? (JSON.parse(stored) as Partial<PlayPreferences>) : null;
    if (!value) return DEFAULT_PLAY_PREFERENCES;
    const normalized: PlayPreferences = {
      proseSize: clamp(value.proseSize, 12, 20, DEFAULT_PLAY_PREFERENCES.proseSize),
      proseFamily: value.proseFamily === 'serif' ? 'serif' : 'sans',
      measure: clamp(value.measure, 72, 110, DEFAULT_PLAY_PREFERENCES.measure),
      sidebarWidth: clamp(value.sidebarWidth, 240, 360, DEFAULT_PLAY_PREFERENCES.sidebarWidth),
      sidebarSide: value.sidebarSide === 'left' ? 'left' : 'right',
      density: value.density === 'comfortable' ? 'comfortable' : 'compact',
      readerMode: value.readerMode === 'chronological' ? 'chronological' : 'threads',
    };
    if (accountId != null && !window.localStorage.getItem(playPreferencesKey(accountId))) {
      window.localStorage.setItem(playPreferencesKey(accountId), JSON.stringify(normalized));
    }
    return normalized;
  } catch {
    return DEFAULT_PLAY_PREFERENCES;
  }
}

export function savePlayPreferences(
  preferences: PlayPreferences,
  accountId?: number | null
): boolean {
  try {
    window.localStorage.setItem(playPreferencesKey(accountId), JSON.stringify(preferences));
    return true;
  } catch {
    // Storage can be disabled; callers continue with in-memory preferences.
    return false;
  }
}

export function usePlayPreferences(accountId?: number | null) {
  const key = useMemo(() => playPreferencesKey(accountId), [accountId]);
  const [preferences, setPreferences] = useState(() => loadPlayPreferences(accountId));
  const [storageWarning, setStorageWarning] = useState(false);
  const update = useCallback(
    (patch: Partial<PlayPreferences>) => {
      setPreferences((current) => {
        const next = { ...current, ...patch };
        if (!savePlayPreferences(next, accountId)) setStorageWarning(true);
        return next;
      });
    },
    [accountId]
  );
  // Account changes should never display the previous account's layout.
  useEffect(() => {
    setPreferences(loadPlayPreferences(accountId));
    const sync = (event: Event) => {
      const detail = (event as CustomEvent<PlayPreferences>).detail;
      if (detail) setPreferences(detail);
    };
    window.addEventListener('arx-play-preferences', sync);
    return () => window.removeEventListener('arx-play-preferences', sync);
  }, [key, accountId]);
  return { preferences, update, storageWarning };
}
